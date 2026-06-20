"""Claim-level citation building (ported from PromptEnhancement orchestrator)."""

from __future__ import annotations

import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)


def tokenize_claim(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[A-Za-z0-9_']+", str(text).lower())
        if len(token) > 2
    }


def normalize_source_type(value: Any) -> str:
    source_type = str(value or "").strip().lower()
    if source_type in {
        "project_policy",
        "company_policy",
        "document",
        "workspace_context",
        "public_context",
        "internal_knowledge_doc",
    }:
        return source_type
    if source_type in {"enterprise_context", "project_policies"}:
        return "project_policy"
    if source_type in {"attachment_context", "uploaded_document", "documents"}:
        return "document"
    if source_type in {"internal_knowledge_docs", "internal_knowledge"}:
        return "internal_knowledge_doc"
    if source_type:
        logger.warning(
            "[CITATION] unsupported source type '%s'; falling back to workspace_context",
            source_type,
        )
    return "workspace_context"


def _is_project_policy_name(value: Any) -> bool:
    label = str(value or "").strip().lower()
    if not label:
        return False
    return "project context" in label or "project policy" in label


def extract_retrieved_chunks(
    *,
    enterprise_context: str = "",
    document_context: str = "",
    matched_content_sources: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    seen_chunk_keys: set[str] = set()
    seen_content_keys: set[str] = set()

    def split_content_segments(text: str, target_size: int = 360) -> list[str]:
        normalized = str(text or "").strip()
        if not normalized:
            return []
        if len(normalized) <= target_size:
            return [normalized]

        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", normalized) if s.strip()]
        if not sentences:
            return [normalized]

        segments: list[str] = []
        current = ""
        for sentence in sentences:
            next_chunk = f"{current} {sentence}".strip() if current else sentence
            if current and len(next_chunk) > target_size:
                segments.append(current)
                current = sentence
            else:
                current = next_chunk
        if current:
            segments.append(current)
        return segments if segments else [normalized]

    def append_chunk(chunk: dict[str, Any]) -> None:
        chunk_key = f"{chunk.get('documentId')}::{chunk.get('chunkId')}::{chunk.get('sourceType')}"
        if chunk_key in seen_chunk_keys:
            return

        content_fingerprint = re.sub(r"\s+", " ", str(chunk.get("content") or "")).strip().lower()[:260]
        content_key = f"{str(chunk.get('documentName') or '').strip().lower()}::{content_fingerprint}"
        if content_fingerprint and content_key in seen_content_keys:
            return

        seen_chunk_keys.add(chunk_key)
        if content_fingerprint:
            seen_content_keys.add(content_key)
        chunks.append(chunk)

    source_buckets = matched_content_sources if isinstance(matched_content_sources, dict) else {}
    for bucket_name, bucket_items in source_buckets.items():
        if not isinstance(bucket_items, list):
            continue

        for idx, item in enumerate(bucket_items):
            if not isinstance(item, dict):
                continue
            snippet = str(item.get("content") or item.get("text") or "").strip()
            if not snippet:
                continue

            source_type = normalize_source_type(item.get("source_type") or bucket_name)
            document_id = (
                str(item.get("document_id") or item.get("id") or f"{bucket_name}_{idx + 1}").strip()
                or f"{bucket_name}_{idx + 1}"
            )
            chunk_id = (
                str(item.get("chunk_id") or f"{bucket_name}_chunk_{idx + 1}").strip()
                or f"{bucket_name}_chunk_{idx + 1}"
            )
            document_name = (
                str(
                    item.get("document_name")
                    or item.get("documentName")
                    or item.get("file_name")
                    or item.get("title")
                    or "document"
                ).strip()
                or "document"
            )

            try:
                score = float(item.get("score") or 0.0)
            except Exception:
                score = 0.0

            for segment_idx, segment in enumerate(split_content_segments(snippet)):
                segment_chunk_id = chunk_id if segment_idx == 0 else f"{chunk_id}_part_{segment_idx + 1}"
                append_chunk(
                    {
                        "chunkId": segment_chunk_id,
                        "documentId": document_id,
                        "documentName": document_name,
                        "content": segment,
                        "page": item.get("page") or item.get("page_number"),
                        "score": round(score, 4),
                        "sourceType": source_type,
                    }
                )

    enterprise_pattern = re.compile(
        r"\[([^\]]+)\]\s*\(score=([^)]+)\):\s*\n(.*?)(?=\n\[[^\]]+\]\s*\(score=|\Z)",
        flags=re.DOTALL,
    )
    for idx, match in enumerate(enterprise_pattern.finditer(str(enterprise_context or ""))):
        document_name = str(match.group(1) or "document").strip() or "document"
        raw_score = str(match.group(2) or "0").strip()
        snippet = str(match.group(3) or "").strip()
        if not snippet:
            continue
        try:
            score = float(raw_score)
        except Exception:
            score = 0.0

        for segment_idx, segment in enumerate(split_content_segments(snippet)):
            segment_chunk_id = f"enterprise_{idx + 1}" if segment_idx == 0 else f"enterprise_{idx + 1}_part_{segment_idx + 1}"
            append_chunk(
                {
                    "chunkId": segment_chunk_id,
                    "documentId": f"enterprise_doc_{idx + 1}",
                    "documentName": document_name,
                    "content": segment,
                    "page": None,
                    "score": round(score, 4),
                    "sourceType": "project_policy" if _is_project_policy_name(document_name) else "document",
                }
            )

    attachment_pattern = re.compile(
        r"---\s*(.*?)\s*\|\s*Chunk\s*(\d+)\s*---\s*\n(.*?)(?=\n---\s*.*?\|\s*Chunk\s*\d+\s*---|\Z)",
        flags=re.DOTALL,
    )
    for idx, match in enumerate(attachment_pattern.finditer(str(document_context or ""))):
        document_name = str(match.group(1) or "attached_document").strip() or "attached_document"
        chunk_number = str(match.group(2) or str(idx + 1)).strip()
        snippet = str(match.group(3) or "").strip()
        if not snippet:
            continue

        for segment_idx, segment in enumerate(split_content_segments(snippet)):
            segment_chunk_id = f"attachment_{chunk_number}" if segment_idx == 0 else f"attachment_{chunk_number}_part_{segment_idx + 1}"
            append_chunk(
                {
                    "chunkId": segment_chunk_id,
                    "documentId": f"attachment_doc_{document_name}",
                    "documentName": document_name,
                    "content": segment,
                    "page": None,
                    "score": 0.5,
                    "sourceType": "document",
                }
            )

    project_by_doc: dict[str, float] = {}
    for chunk in chunks:
        if str(chunk.get("sourceType") or "").strip().lower() != "project_policy":
            continue
        document_id = str(chunk.get("documentId") or "").strip()
        if not document_id:
            continue
        score = float(chunk.get("score") or 0.0)
        previous = project_by_doc.get(document_id)
        if previous is None or score > previous:
            project_by_doc[document_id] = score

    if len(project_by_doc) <= 1:
        return chunks

    best_project_doc_id = max(project_by_doc.items(), key=lambda pair: pair[1])[0]
    filtered_chunks: list[dict[str, Any]] = []
    for chunk in chunks:
        if str(chunk.get("sourceType") or "").strip().lower() != "project_policy":
            filtered_chunks.append(chunk)
            continue
        document_id = str(chunk.get("documentId") or "").strip()
        if document_id == best_project_doc_id:
            filtered_chunks.append(chunk)

    return filtered_chunks


def build_claim_level_citations(
    enhanced_prompt: str,
    retrieved_chunks: list[dict[str, Any]],
) -> dict[str, Any]:
    if not enhanced_prompt or not retrieved_chunks:
        return {
            "annotated_text": enhanced_prompt,
            "citations": [],
            "context_used": [],
        }

    sentence_pattern = re.compile(r"[^.!?\n]+[.!?]?")
    inline_citation_pattern = re.compile(r"\[\d+\]")

    chunk_tokens = [tokenize_claim(chunk.get("content", "")) for chunk in retrieved_chunks]
    chunk_citation_ids: dict[str, int] = {}
    citations_by_id: dict[int, dict[str, Any]] = {}
    context_used: list[dict[str, Any]] = []
    chunk_usage_counts: dict[str, int] = {}

    def _env_float(name: str, default: float) -> float:
        raw = os.getenv(name)
        if raw is None:
            return default
        try:
            return float(raw)
        except Exception:
            return default

    min_source_score_default = _env_float("CITATION_MIN_SOURCE_SCORE", 0.12)
    min_sentence_match_score = _env_float("CITATION_MIN_SENTENCE_MATCH", 0.22)

    def _chunk_base_score(chunk: dict[str, Any]) -> float:
        try:
            return max(0.0, min(1.0, float(chunk.get("score") or 0.0)))
        except Exception:
            return 0.0

    def score_sentence(sentence_text: str) -> tuple[int | None, float]:
        sentence_tokens = tokenize_claim(sentence_text)
        if len(sentence_tokens) < 4:
            return None, 0.0

        candidates: list[tuple[int, float, bool]] = []
        lower_sentence = str(sentence_text).lower()

        for idx, chunk in enumerate(retrieved_chunks):
            tokens = chunk_tokens[idx]
            if not tokens:
                continue

            source_type = str(chunk.get("sourceType") or "workspace_context").strip().lower()
            base_score = _chunk_base_score(chunk)
            if source_type in {
                "project_policy",
                "document",
                "workspace_context",
                "public_context",
                "internal_knowledge_doc",
            }:
                if base_score < min_source_score_default:
                    continue

            overlap = len(sentence_tokens.intersection(tokens))
            overlap_ratio = overlap / max(len(sentence_tokens), 1)
            containment_bonus = 0.15 if lower_sentence in str(chunk.get("content", "")).lower() else 0.0
            chunk_id = str(chunk.get("chunkId") or f"chunk_{idx + 1}")
            reuse_penalty = min(0.18, 0.08 * chunk_usage_counts.get(chunk_id, 0))
            score = (0.7 * overlap_ratio) + (0.3 * base_score) + containment_bonus - reuse_penalty
            is_unused = chunk_usage_counts.get(chunk_id, 0) == 0
            candidates.append((idx, score, is_unused))

        if not candidates:
            return None, 0.0

        viable_unused = [item for item in candidates if item[2] and item[1] >= min_sentence_match_score]
        if viable_unused:
            best_idx, best_score, _ = max(viable_unused, key=lambda item: item[1])
            return best_idx, best_score

        best_idx, best_score, _ = max(candidates, key=lambda item: item[1])
        if best_score < min_sentence_match_score:
            return None, best_score
        return best_idx, best_score

    def annotate_sentence(sentence_text: str) -> str:
        stripped = sentence_text.strip()
        if not stripped:
            return sentence_text
        if inline_citation_pattern.search(stripped):
            return sentence_text

        best_idx, confidence = score_sentence(stripped)
        if best_idx is None:
            return sentence_text

        chunk = retrieved_chunks[best_idx]
        chunk_id = str(chunk.get("chunkId") or f"chunk_{best_idx + 1}")
        chunk_usage_counts[chunk_id] = chunk_usage_counts.get(chunk_id, 0) + 1
        base_score = _chunk_base_score(chunk)
        citation_id = chunk_citation_ids.get(chunk_id)
        if citation_id is None:
            citation_id = len(chunk_citation_ids) + 1
            chunk_citation_ids[chunk_id] = citation_id
            citations_by_id[citation_id] = {
                "id": citation_id,
                "document": str(chunk.get("documentName") or "document"),
                "documentName": str(chunk.get("documentName") or "document"),
                "snippet": str(chunk.get("content") or "")[:600],
                "source_type": chunk.get("sourceType") or "workspace_context",
                "sourceType": chunk.get("sourceType") or "workspace_context",
                "page": chunk.get("page"),
                "chunk_id": chunk_id,
                "source_ref": f"{chunk.get('documentId') or 'doc'}::{chunk_id}",
                "score": round(float(chunk.get("score") or 0.0), 4),
                "claim": stripped,
            }

        fused_confidence = round(max(0.0, min(1.0, (0.65 * confidence) + (0.35 * base_score))), 4)
        context_used.append(
            {
                "id": f"claim_{len(context_used) + 1}",
                "document_name": str(chunk.get("documentName") or "document"),
                "type": chunk.get("sourceType") or "workspace_context",
                "matched_keywords": sorted(list(tokenize_claim(stripped)))[:8],
                "confidence": fused_confidence,
                "source_ref": f"{chunk.get('documentId') or 'doc'}::{chunk_id}",
                "snippet": str(chunk.get("content") or "")[:400],
                "claim": stripped,
                "citation_id": citation_id,
                "chunk_id": chunk_id,
            }
        )

        trailing_len = len(sentence_text) - len(sentence_text.rstrip())
        trailing_ws = sentence_text[len(sentence_text) - trailing_len :] if trailing_len > 0 else ""
        sentence_core = sentence_text.rstrip()
        return f"{sentence_core} [{citation_id}]{trailing_ws}"

    annotated_lines: list[str] = []
    for line in str(enhanced_prompt).split("\n"):
        if inline_citation_pattern.search(line):
            annotated_lines.append(line)
            continue

        cursor = 0
        pieces: list[str] = []
        for match in sentence_pattern.finditer(line):
            start, end = match.span()
            pieces.append(line[cursor:start])
            pieces.append(annotate_sentence(match.group(0)))
            cursor = end
        pieces.append(line[cursor:])
        annotated_lines.append("".join(pieces))

    citations = [citations_by_id[key] for key in sorted(citations_by_id.keys())]
    return {
        "annotated_text": "\n".join(annotated_lines),
        "citations": citations,
        "context_used": context_used,
    }
