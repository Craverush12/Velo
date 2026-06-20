"""Enterprise policy + project document context fetch from Nest backend."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import unicodedata
from pathlib import Path
from typing import Any

import httpx
import numpy as np

from shared.settings import get_settings

logger = logging.getLogger(__name__)

_embedding_model = None


def _tokenize(text: str) -> set[str]:
    if not isinstance(text, str) or not text.strip():
        return set()
    normalized = unicodedata.normalize("NFKC", text).lower()
    normalized = re.sub(r"[\u2010\u2011\u2012\u2013\u2014\u2015\-_/]", " ", normalized)
    tokens = re.findall(r"[^\W_]+", normalized, flags=re.UNICODE)
    return {token for token in tokens if len(token) > 2}


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _safe_basename(path_value: Any) -> str:
    raw = _safe_str(path_value).strip()
    if not raw:
        return ""
    try:
        return Path(raw).name
    except Exception:
        return raw.split("/")[-1].split("\\")[-1]


def _to_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _to_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _to_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _parse_response_payload(response: httpx.Response) -> Any:
    try:
        return response.json()
    except Exception:
        return response.text.strip() if response.text else ""


def _normalized_lines(text: str) -> list[str]:
    if not isinstance(text, str) or not text.strip():
        return []
    return [line.strip() for line in text.splitlines() if line.strip()]


def _cosine_similarity(vec1: np.ndarray, vec2: np.ndarray) -> float:
    denom = float(np.linalg.norm(vec1) * np.linalg.norm(vec2))
    if denom == 0:
        return 0.0
    return float(np.dot(vec1, vec2) / denom)


def _get_embedding_model():
    global _embedding_model
    if _embedding_model is not None:
        return _embedding_model
    try:
        from sentence_transformers import SentenceTransformer

        _embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info("Enterprise context embedding model loaded: all-MiniLM-L6-v2")
    except Exception as exc:
        logger.warning("Embedding model unavailable for enterprise context search: %s", exc)
        _embedding_model = None
    return _embedding_model


class EnterprisePromptContextBuilder:
    def __init__(self) -> None:
        settings = get_settings()
        self.base_url = (
            settings.ENTERPRISE_BACKEND_BASE_URL
            or os.getenv("ENTERPRISE_BACKEND_BASE_URL", "")
        ).rstrip("/")
        self.policy_endpoint = (
            settings.ENTERPRISE_POLICY_ENDPOINT
            or os.getenv("ENTERPRISE_POLICY_ENDPOINT", "/public-context/company-policy")
        )
        self.contents_endpoint = (
            settings.ENTERPRISE_CONTENTS_ENDPOINT
            or os.getenv("ENTERPRISE_CONTENTS_ENDPOINT", "/public-context/contents")
        )
        self.max_docs = _to_int(os.getenv("ENTERPRISE_CONTEXT_MAX_DOCS", "100"), 100)
        self.max_matches = _to_int(os.getenv("ENTERPRISE_CONTEXT_MAX_MATCHES", "3"), 3)
        self.embedding_threshold = _to_float(os.getenv("ENTERPRISE_CONTEXT_EMBEDDING_THRESHOLD", "0.35"), 0.35)
        self.lexical_threshold = _to_float(os.getenv("ENTERPRISE_CONTEXT_LEXICAL_THRESHOLD", "0.08"), 0.08)

    def _is_project_policy_doc(self, item: dict[str, Any]) -> bool:
        label = (
            _safe_str(item.get("file_name"))
            or _safe_str(item.get("title"))
            or _safe_str(item.get("name"))
        ).strip().lower()
        if not label:
            return False
        return (
            "project context" in label
            or "project policy" in label
            or label.startswith("project context")
        )

    def _has_project_anchor_overlap(
        self,
        prompt: str,
        project_docs: list[dict[str, Any]],
        all_matched_docs: list[dict[str, Any]],
    ) -> bool:
        prompt_tokens = _tokenize(prompt)
        if not prompt_tokens or not project_docs:
            return False

        labels = [
            _safe_str(doc.get("file_name")) or _safe_str(doc.get("title")) or _safe_str(doc.get("name"))
            for doc in all_matched_docs
        ]
        if not labels:
            return False

        token_df: dict[str, int] = {}
        for label in labels:
            for token in {t for t in _tokenize(label) if len(t) >= 4}:
                token_df[token] = token_df.get(token, 0) + 1

        rarity_cutoff = max(1, int(len(labels) * 0.35))
        salient_prompt_tokens = {
            token for token in prompt_tokens if len(token) >= 4 and token_df.get(token, 9999) <= rarity_cutoff
        }
        if not salient_prompt_tokens:
            salient_prompt_tokens = {token for token in prompt_tokens if len(token) >= 6}
        if not salient_prompt_tokens:
            return False

        project_anchor_tokens: set[str] = set()
        for doc in project_docs:
            label = _safe_str(doc.get("file_name")) or _safe_str(doc.get("title")) or _safe_str(doc.get("name"))
            project_anchor_tokens.update({token for token in _tokenize(label) if len(token) >= 4})
        if not project_anchor_tokens:
            return False
        return bool(salient_prompt_tokens.intersection(project_anchor_tokens))

    def _should_keep_project_policy(
        self,
        prompt: str,
        project_docs: list[dict[str, Any]],
        all_matched_docs: list[dict[str, Any]],
    ) -> bool:
        if not project_docs:
            return False

        non_project_docs = [doc for doc in all_matched_docs if not self._is_project_policy_doc(doc)]
        max_project_score = max(_to_float(doc.get("score"), 0.0) for doc in project_docs)
        max_non_project_score = (
            max(_to_float(doc.get("score"), 0.0) for doc in non_project_docs) if non_project_docs else 0.0
        )

        min_abs_default = max(self.embedding_threshold + 0.10, self.lexical_threshold + 0.20)
        min_abs_score = _to_float(os.getenv("ENTERPRISE_PROJECT_POLICY_MIN_SCORE"), min_abs_default)
        min_relative_gap = _to_float(os.getenv("ENTERPRISE_PROJECT_POLICY_MIN_GAP", "0.12"), 0.12)
        require_anchor = _to_bool(os.getenv("ENTERPRISE_PROJECT_POLICY_REQUIRE_ANCHOR", "true"), True)

        if max_project_score < min_abs_score:
            return False
        if non_project_docs and (max_project_score - max_non_project_score) < min_relative_gap:
            return False
        if not require_anchor:
            return True
        return self._has_project_anchor_overlap(prompt, project_docs, all_matched_docs)

    def _limit_project_policy_matches(self, matched_docs: list[dict[str, Any]], prompt: str) -> list[dict[str, Any]]:
        if not matched_docs:
            return []

        project_docs = [doc for doc in matched_docs if self._is_project_policy_doc(doc)]
        if not project_docs:
            return matched_docs

        if not self._should_keep_project_policy(prompt, project_docs, matched_docs):
            return [doc for doc in matched_docs if not self._is_project_policy_doc(doc)]

        if len(project_docs) <= 1:
            return matched_docs

        best_project_doc = max(project_docs, key=lambda doc: _to_float(doc.get("score"), 0.0))
        limited: list[dict[str, Any]] = []
        kept_project = False
        for doc in matched_docs:
            if self._is_project_policy_doc(doc):
                if not kept_project and doc is best_project_doc:
                    limited.append(doc)
                    kept_project = True
                continue
            limited.append(doc)
        return limited

    def _build_headers(self, auth_token: str | None) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if auth_token and auth_token.strip():
            token = auth_token.strip()
            headers["Authorization"] = token if token.lower().startswith("bearer ") else f"Bearer {token}"
        internal_key = os.getenv("ENTERPRISE_INTERNAL_API_KEY")
        if internal_key:
            headers["X-Internal-Key"] = internal_key
        return headers

    def _extract_policy_text(self, payload: dict[str, Any]) -> str:
        if not isinstance(payload, dict):
            return ""

        parts: list[str] = []
        moderation_parts: list[str] = []

        description = _safe_str(payload.get("description"))
        if description:
            parts.append(description)

        context_value = payload.get("context")
        if isinstance(context_value, list):
            parts.extend([_safe_str(item) for item in context_value if _safe_str(item)])
        elif isinstance(context_value, str) and context_value.strip():
            parts.append(context_value.strip())

        moderation_result = payload.get("moderationResult")
        if isinstance(moderation_result, str):
            try:
                moderation_result = json.loads(moderation_result)
            except Exception:
                moderation_result = None

        if isinstance(moderation_result, dict):
            doc_summary = _safe_str(moderation_result.get("document_summary"))
            if doc_summary:
                moderation_parts.append(doc_summary)
            mod_context = moderation_result.get("context")
            if isinstance(mod_context, list):
                moderation_parts.extend([_safe_str(item) for item in mod_context if _safe_str(item)])
            elif isinstance(mod_context, str) and mod_context.strip():
                moderation_parts.append(mod_context.strip())

        if moderation_parts:
            parts = moderation_parts

        seen: set[str] = set()
        normalized: list[str] = []
        for item in parts:
            key = item.strip().lower()
            if key and key not in seen:
                seen.add(key)
                normalized.append(item.strip())
        return "\n".join(normalized)

    def _extract_policy_name(self, payload: dict[str, Any]) -> str:
        for value in (payload.get("fileName"), payload.get("title"), payload.get("name"), payload.get("description")):
            text = _safe_str(value).strip()
            if text:
                return text
        return ""

    def _extract_documents(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        items = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            return []

        docs: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue

            text_parts: list[str] = []
            moderation_parts: list[str] = []

            context_value = item.get("context")
            if isinstance(context_value, list):
                text_parts.extend([_safe_str(value) for value in context_value if _safe_str(value)])
            elif isinstance(context_value, str) and context_value.strip():
                text_parts.append(context_value.strip())

            moderation_result = item.get("moderationResult")
            if isinstance(moderation_result, str):
                try:
                    moderation_result = json.loads(moderation_result)
                except Exception:
                    moderation_result = None

            if isinstance(moderation_result, dict):
                mr_context = moderation_result.get("context")
                if isinstance(mr_context, list):
                    moderation_parts.extend([_safe_str(value) for value in mr_context if _safe_str(value)])
                elif isinstance(mr_context, str) and mr_context.strip():
                    moderation_parts.append(mr_context.strip())
                doc_summary = _safe_str(moderation_result.get("document_summary"))
                if doc_summary:
                    moderation_parts.append(doc_summary)

            if moderation_parts:
                text_parts = moderation_parts
            else:
                description = _safe_str(item.get("description"))
                if description:
                    text_parts.append(description)

            combined = "\n".join(part.strip() for part in text_parts if part and part.strip())
            if not combined:
                continue

            docs.append(
                {
                    "id": item.get("id"),
                    "title": _safe_str(item.get("title")) or _safe_str(item.get("documentTitle")) or _safe_str(item.get("name")),
                    "file_name": (
                        _safe_str(item.get("title"))
                        or _safe_str(item.get("documentTitle"))
                        or _safe_str(item.get("name"))
                        or _safe_str(item.get("fileName"))
                        or _safe_basename(item.get("filePath"))
                        or "untitled"
                    ),
                    "text": combined,
                }
            )
        return docs

    def _build_project_policy_text(self, matched_docs: list[dict[str, Any]]) -> str:
        lines: list[str] = []
        seen: set[str] = set()
        for item in matched_docs:
            for raw_line in _safe_str(item.get("text")).splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                key = line.lower()
                if key in seen:
                    continue
                seen.add(key)
                lines.append(line)
                if len("\n".join(lines)) >= 2000:
                    return "\n".join(lines)[:2000]
        return "\n".join(lines)[:2000]

    def _merge_policy_guidance(self, company_policy: str, project_policy: str) -> str:
        merged: list[str] = []
        seen: set[str] = set()
        for line in [*_normalized_lines(company_policy), *_normalized_lines(project_policy)]:
            key = line.lower()
            if key not in seen:
                seen.add(key)
                merged.append(line)
                if len("\n".join(merged)) >= 2000:
                    return "\n".join(merged)[:2000]
        return "\n".join(merged)[:2000]

    async def _fetch_policy(
        self,
        client: httpx.AsyncClient,
        headers: dict[str, str],
        enterprise_id: str | None,
    ) -> dict[str, str]:
        custom_url = os.getenv("ENTERPRISE_POLICY_API_URL")
        url = custom_url.format(enterprise_id=enterprise_id) if custom_url else f"{self.base_url}{self.policy_endpoint}"
        params = {"enterpriseId": enterprise_id} if enterprise_id else {}
        response = await client.get(url, headers=headers, params=params)
        if response.status_code == 404:
            return {"text": "", "name": ""}
        response.raise_for_status()
        payload = _parse_response_payload(response)
        if isinstance(payload, str):
            return {"text": payload[:2000], "name": ""}
        if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
            payload = payload["data"]
        policy_payload = payload if isinstance(payload, dict) else {}
        return {
            "text": self._extract_policy_text(policy_payload),
            "name": self._extract_policy_name(policy_payload),
        }

    async def _fetch_documents(
        self,
        client: httpx.AsyncClient,
        headers: dict[str, str],
        enterprise_id: str | None,
        team_id: str | None,
    ) -> list[dict[str, Any]]:
        custom_url = os.getenv("ENTERPRISE_CONTENTS_API_URL")
        url = (
            custom_url.format(enterprise_id=enterprise_id, team_id=team_id or "")
            if custom_url
            else f"{self.base_url}{self.contents_endpoint}"
        )
        params: dict[str, Any] = {"page": 1, "limit": self.max_docs}
        if enterprise_id:
            params["enterpriseId"] = enterprise_id
        if team_id:
            params["teamId"] = team_id
        response = await client.get(url, headers=headers, params=params)
        if response.status_code == 404:
            return []
        response.raise_for_status()
        payload = _parse_response_payload(response)
        if not isinstance(payload, dict):
            return []
        return self._extract_documents(payload)

    def _rank_documents(self, prompt: str, docs: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str]:
        if not docs:
            return [], "none"

        texts = [doc["text"] for doc in docs]
        model = _get_embedding_model()
        if model is not None:
            try:
                vectors = model.encode([prompt, *texts], show_progress_bar=False)
                query_vec = vectors[0]
                ranked = []
                for index, doc in enumerate(docs):
                    score = _cosine_similarity(query_vec, vectors[index + 1])
                    ranked.append({**doc, "score": round(score, 4)})
                ranked.sort(key=lambda item: (-float(item.get("score", 0.0)), _safe_str(item.get("file_name")).lower()))
                filtered = [item for item in ranked if item["score"] >= self.embedding_threshold]
                return filtered[: self.max_matches], "embedding"
            except Exception as exc:
                logger.warning("Embedding ranking failed; using lexical fallback: %s", exc)

        prompt_tokens = _tokenize(prompt)
        ranked = []
        for doc in docs:
            doc_tokens = _tokenize(doc["text"])
            if not prompt_tokens or not doc_tokens:
                score = 0.0
            else:
                intersection = len(prompt_tokens.intersection(doc_tokens))
                union = len(prompt_tokens.union(doc_tokens))
                score = intersection / union if union else 0.0
            ranked.append({**doc, "score": round(score, 4)})
        ranked.sort(key=lambda item: (-float(item.get("score", 0.0)), _safe_str(item.get("file_name")).lower()))
        filtered = [item for item in ranked if item["score"] >= self.lexical_threshold]
        return filtered[: self.max_matches], "lexical"

    def _build_matched_content_sources(
        self,
        *,
        matched_docs: list[dict[str, Any]],
        docs: list[dict[str, Any]],
        policy_text: str,
        company_policy_name: str,
    ) -> dict[str, Any]:
        return {
            "project_policies": [
                {
                    "document_id": str(item.get("id") or f"project_policy_{idx + 1}"),
                    "document_name": _safe_str(item.get("file_name") or item.get("title") or "project_policy"),
                    "source_type": "project_policy",
                    "text": _safe_str(item.get("text")),
                    "score": item.get("score", 0.0),
                }
                for idx, item in enumerate(matched_docs)
            ],
            "company_policies": [
                {
                    "document_id": "company_policy_1",
                    "document_name": company_policy_name or "Company policy",
                    "source_type": "company_policy",
                    "text": policy_text,
                    "score": 1.0,
                }
            ]
            if policy_text
            else [],
            "documents": [
                {
                    "document_id": str(item.get("id") or f"document_{idx + 1}"),
                    "document_name": _safe_str(item.get("file_name") or item.get("title") or "document"),
                    "source_type": "document",
                    "text": _safe_str(item.get("text")),
                    "score": item.get("score", 0.0),
                }
                for idx, item in enumerate(docs)
            ],
            "retrieved_chunks": [],
            "public_context": [],
            "internal_knowledge_docs": [],
            "workspace_context": [],
        }

    async def build_context(
        self,
        prompt: str,
        enterprise_id: str | None,
        team_id: str | None,
        auth_token: str | None = None,
    ) -> dict[str, Any]:
        if not self.base_url:
            return {
                "company_policy": "",
                "matched_contexts": [],
                "combined_context": "",
                "context_mode": "prompt_only",
                "search_method": "none",
                "reason": "enterprise_backend_url_missing",
            }

        normalized_prompt = _safe_str(prompt).strip()
        if not normalized_prompt:
            return {
                "company_policy": "",
                "matched_contexts": [],
                "combined_context": "",
                "context_mode": "prompt_only",
                "search_method": "none",
                "reason": "empty_prompt",
            }

        if not enterprise_id and not auth_token:
            return {
                "company_policy": "",
                "matched_contexts": [],
                "combined_context": "",
                "context_mode": "prompt_only",
                "search_method": "none",
                "reason": "enterprise_id_and_auth_missing",
            }

        headers = self._build_headers(auth_token)
        timeout = _to_float(os.getenv("ENTERPRISE_CONTEXT_HTTP_TIMEOUT", "10"), 10.0)
        policy_text = ""
        company_policy_name = ""
        docs: list[dict[str, Any]] = []

        try:
            async with httpx.AsyncClient(timeout=timeout, verify=False) as client:
                policy_result, docs_result = await asyncio.gather(
                    self._fetch_policy(client, headers, enterprise_id),
                    self._fetch_documents(client, headers, enterprise_id, team_id),
                )
                policy_text = _safe_str(policy_result.get("text"))
                company_policy_name = _safe_str(policy_result.get("name"))
                docs = docs_result or []
        except Exception as exc:
            logger.warning("Enterprise context fetch failed: %s", exc)

        matched_docs, search_method = self._rank_documents(normalized_prompt, docs)
        if not matched_docs and docs:
            matched_docs = [{**item, "score": item.get("score", 0)} for item in docs[: self.max_matches]]
            search_method = "fallback_no_threshold"

        matched_docs = self._limit_project_policy_matches(matched_docs, normalized_prompt)

        context_sections: list[str] = []
        project_policy_text = self._build_project_policy_text(matched_docs)
        merged_policy = self._merge_policy_guidance(policy_text, project_policy_text)
        if merged_policy:
            context_sections.append(f"Policy guidance:\n{merged_policy}")

        if matched_docs:
            doc_lines = []
            for item in matched_docs:
                doc_label = (
                    _safe_str(item.get("title"))
                    or _safe_str(item.get("document_title"))
                    or _safe_str(item.get("name"))
                    or _safe_str(item.get("file_name"))
                    or "document"
                )
                doc_lines.append(
                    f"[{doc_label}] (score={item.get('score', 0)}):\n{_safe_str(item.get('text'))[:900]}"
                )
            context_sections.append("Relevant enterprise context:\n" + "\n\n".join(doc_lines))

        if policy_text and matched_docs:
            context_mode = "policy_plus_context"
        elif matched_docs:
            context_mode = "context_only"
        elif policy_text:
            context_mode = "policy_only"
        else:
            context_mode = "prompt_only"

        return {
            "company_policy": policy_text,
            "company_policy_names": [company_policy_name]
            if company_policy_name
            else (["Company policy"] if policy_text else []),
            "project_policy": project_policy_text,
            "matched_contexts": matched_docs,
            "matched_content_sources": self._build_matched_content_sources(
                matched_docs=matched_docs,
                docs=docs,
                policy_text=policy_text,
                company_policy_name=company_policy_name,
            ),
            "combined_context": "\n\n".join(context_sections).strip(),
            "context_mode": context_mode,
            "search_method": search_method,
            "enterprise_id": enterprise_id,
            "team_id": team_id,
            "documents_considered": len(docs),
        }
