"""Enterprise context fetch + citation enrichment for enhance/refine responses."""

from __future__ import annotations

import logging
import re
from typing import Any

from shared.citation_builder import (
    build_claim_level_citations,
    extract_retrieved_chunks,
    normalize_source_type,
)
from shared.enterprise_prompt_context import EnterprisePromptContextBuilder

logger = logging.getLogger(__name__)

_CONSUMER_ENTERPRISE_IDS = frozenset({"default", "consumer", "none"})


def _empty_enterprise_context() -> dict[str, Any]:
    return {
        "company_policy": "",
        "company_policy_names": [],
        "project_policy": "",
        "matched_contexts": [],
        "matched_content_sources": {},
        "combined_context": "",
        "context_mode": "prompt_only",
        "search_method": "none",
    }


async def resolve_enterprise_context(
    prompt: str,
    *,
    enterprise_id: str | None,
    team_id: str | None,
    auth_token: str | None,
) -> dict[str, Any]:
    """Fetch enterprise policy + matched project documents from Nest backend."""
    normalized_eid = str(enterprise_id or "").strip()
    if normalized_eid.lower() in _CONSUMER_ENTERPRISE_IDS:
        normalized_eid = ""

    token = str(auth_token or "").strip()
    if not normalized_eid and not token:
        return _empty_enterprise_context()

    builder = EnterprisePromptContextBuilder()
    try:
        result = await builder.build_context(
            prompt=prompt,
            enterprise_id=normalized_eid or None,
            team_id=str(team_id).strip() if team_id else None,
            auth_token=token or None,
        )
        return result if isinstance(result, dict) else _empty_enterprise_context()
    except Exception as exc:
        logger.warning("Enterprise context fetch failed: %s", exc)
        return _empty_enterprise_context()


def _extract_project_policy_names(
    enterprise_ctx: dict[str, Any],
    combined_context: str,
) -> list[str]:
    names: list[str] = []
    try:
        names = [
            str(name).strip()
            for name in re.findall(
                r"^\[([^\]]+)\]\s*\(score=",
                str(combined_context),
                flags=re.MULTILINE,
            )
            if str(name).strip()
        ]
        names = list(dict.fromkeys(names))
    except Exception:
        names = []

    if names:
        return names

    matched_sources = enterprise_ctx.get("matched_content_sources")
    if not isinstance(matched_sources, dict):
        return []

    entries = matched_sources.get("project_policies")
    if not isinstance(entries, list):
        return []

    extracted: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        label = str(
            entry.get("document_name")
            or entry.get("file_name")
            or entry.get("title")
            or entry.get("name")
            or ""
        ).strip()
        if label:
            extracted.append(label)
    return list(dict.fromkeys(extracted))


def _build_citation_events(citations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for citation in citations:
        if not isinstance(citation, dict):
            continue
        events.append(
            {
                "event": "citation",
                "citationId": citation.get("id"),
                "sourceType": citation.get("sourceType") or citation.get("source_type"),
                "documentName": citation.get("documentName") or citation.get("document"),
                "snippet": citation.get("snippet", ""),
            }
        )
    return events


def _build_citation_maps(citations: list[dict[str, Any]], annotated_text: str) -> list[dict[str, Any]]:
    maps: list[dict[str, Any]] = []
    for citation in citations:
        if not isinstance(citation, dict):
            continue
        citation_id = citation.get("id")
        marker = f"[{citation_id}]"
        start = annotated_text.find(marker)
        if start >= 0:
            maps.append(
                {
                    "citation_id": citation_id,
                    "marker": marker,
                    "offset": start,
                    "document": citation.get("documentName") or citation.get("document"),
                }
            )
    return maps


def enrich_complete_payload_with_citations(
    payload: dict[str, Any],
    enterprise_ctx: dict[str, Any] | None,
) -> dict[str, Any]:
    """Apply enterprise citations to an enhance complete payload."""
    if not isinstance(payload, dict):
        return payload
    if not enterprise_ctx:
        return payload

    combined_context = str(enterprise_ctx.get("combined_context") or "")
    matched_content_sources = (
        enterprise_ctx.get("matched_content_sources")
        if isinstance(enterprise_ctx.get("matched_content_sources"), dict)
        else {}
    )
    company_policy_names = list(enterprise_ctx.get("company_policy_names") or [])
    if not company_policy_names and enterprise_ctx.get("company_policy"):
        company_policy_names = ["Company policy"]

    enterprise_used = bool(combined_context)
    document_used = bool(enterprise_ctx.get("matched_contexts"))
    context_injection = dict(payload.get("context_injection") or {})
    context_injection.update(
        {
            "enterprise_context_used": enterprise_used,
            "enterprise_context_length": len(combined_context),
            "enterprise_context_status": "success" if enterprise_used else "not_fetched",
            "document_context_used": document_used,
            "document_context_length": len(enterprise_ctx.get("matched_contexts") or []),
            "document_context_status": "success" if document_used else "not_fetched",
        }
    )
    payload["context_injection"] = context_injection

    if not combined_context and not matched_content_sources:
        return payload

    enhanced_prompt = str(payload.get("enhanced_prompt") or "")
    retrieved_chunks = extract_retrieved_chunks(
        enterprise_context=combined_context,
        document_context="",
        matched_content_sources=matched_content_sources,
    )

    if not retrieved_chunks:
        project_names = _extract_project_policy_names(enterprise_ctx, combined_context)
        if project_names:
            payload["project_policy_names"] = project_names
            payload["used_documents"] = [
                {"id": f"project_policy_{index + 1}", "name": name, "type": "project_policy"}
                for index, name in enumerate(project_names)
            ]
            payload["citations"] = [
                {
                    "id": index + 1,
                    "document": name,
                    "snippet": "",
                    "source_type": "project_policy",
                    "chunk_id": f"project_policy_{index + 1}",
                    "source_ref": f"project_policy_{index + 1}",
                }
                for index, name in enumerate(project_names)
            ]
        payload["company_policy_names"] = company_policy_names
        payload["matched_content_sources"] = matched_content_sources
        return payload

    citation_result = build_claim_level_citations(enhanced_prompt, retrieved_chunks)
    annotated_text = citation_result.get("annotated_text") or enhanced_prompt
    citations = citation_result.get("citations") or []
    context_used = citation_result.get("context_used") or []

    payload["enhanced_prompt"] = annotated_text
    payload["citations"] = citations
    payload["context_used"] = context_used
    payload["retrieved_chunks"] = retrieved_chunks
    payload["matched_content_sources"] = matched_content_sources
    payload["company_policy_names"] = company_policy_names
    payload["citation_events"] = _build_citation_events(citations)
    payload["citation_maps"] = _build_citation_maps(citations, annotated_text)

    project_names = _extract_project_policy_names(enterprise_ctx, combined_context)
    payload["project_policy_names"] = project_names

    used_documents: list[dict[str, Any]] = []
    seen_doc_ids: set[str] = set()

    if project_names:
        for index, name in enumerate(project_names):
            doc_id = f"project_policy_{index + 1}"
            if doc_id in seen_doc_ids:
                continue
            seen_doc_ids.add(doc_id)
            used_documents.append({"id": doc_id, "name": name, "type": "project_policy"})

    for chunk in retrieved_chunks:
        document_id = str(chunk.get("documentId") or "").strip()
        if not document_id or document_id in seen_doc_ids:
            continue
        seen_doc_ids.add(document_id)
        used_documents.append(
            {
                "id": document_id,
                "name": str(chunk.get("documentName") or "document"),
                "type": str(chunk.get("sourceType") or "workspace_context"),
            }
        )

    payload["used_documents"] = used_documents
    return payload


def enrich_refine_payload_with_citations(
    payload: dict[str, Any],
    *,
    enterprise_ctx: dict[str, Any] | None,
    carry_forward: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply citation remap to refine response with optional carry-forward."""
    if not isinstance(payload, dict):
        return payload

    carry = carry_forward if isinstance(carry_forward, dict) else {}
    previous_citations = carry.get("previous_citations") if isinstance(carry.get("previous_citations"), list) else []
    previous_retrieved_chunks = carry.get("retrieved_chunks") if isinstance(carry.get("retrieved_chunks"), list) else []
    previous_context_used = carry.get("context_used") if isinstance(carry.get("context_used"), list) else []
    matched_content_sources = carry.get("matched_content_sources") if isinstance(carry.get("matched_content_sources"), dict) else {}

    if enterprise_ctx and isinstance(enterprise_ctx.get("matched_content_sources"), dict):
        if not matched_content_sources:
            matched_content_sources = enterprise_ctx["matched_content_sources"]

    enterprise_context_text = str(enterprise_ctx.get("combined_context") or "") if enterprise_ctx else ""

    retrieved_chunks: list[dict[str, Any]] = []
    if previous_retrieved_chunks:
        retrieved_chunks = list(previous_retrieved_chunks)
    else:
        retrieved_chunks = extract_retrieved_chunks(
            enterprise_context=enterprise_context_text,
            document_context="",
            matched_content_sources=matched_content_sources,
        )

    if not retrieved_chunks and previous_citations:
        rebuilt: list[dict[str, Any]] = []
        for idx, citation in enumerate(previous_citations):
            if not isinstance(citation, dict):
                continue
            snippet = str(citation.get("snippet") or "").strip()
            if not snippet:
                continue
            rebuilt.append(
                {
                    "chunkId": str(
                        citation.get("chunkId")
                        or citation.get("chunk_id")
                        or f"fallback_chunk_{idx + 1}"
                    ),
                    "documentId": str(
                        citation.get("sourceRef")
                        or citation.get("source_ref")
                        or citation.get("documentName")
                        or citation.get("document")
                        or f"fallback_doc_{idx + 1}"
                    ),
                    "documentName": str(citation.get("documentName") or citation.get("document") or "document"),
                    "content": snippet,
                    "page": citation.get("page"),
                    "score": float(citation.get("score") or 0.0),
                    "sourceType": normalize_source_type(
                        citation.get("sourceType") or citation.get("source_type") or "workspace_context"
                    ),
                }
            )
        retrieved_chunks = rebuilt

    refined_text = str(payload.get("refined_prompt") or payload.get("enhanced_prompt") or "")
    remap_result = build_claim_level_citations(refined_text, retrieved_chunks)
    remapped_text = remap_result.get("annotated_text") or refined_text
    remapped_citations = remap_result.get("citations") or []
    remapped_context_used = remap_result.get("context_used") or []

    if not remapped_citations and previous_citations:
        remapped_citations = previous_citations
        remapped_context_used = previous_context_used

    payload["refined_prompt"] = remapped_text
    payload["enhanced_prompt"] = remapped_text
    payload["citations"] = remapped_citations
    payload["context_used"] = remapped_context_used
    payload["retrieved_chunks"] = retrieved_chunks
    payload["matched_content_sources"] = matched_content_sources
    payload["citation_events"] = _build_citation_events(remapped_citations)
    payload["citation_maps"] = _build_citation_maps(remapped_citations, remapped_text)

    if carry.get("used_documents"):
        payload["used_documents"] = carry["used_documents"]
    if carry.get("company_policy_names"):
        payload["company_policy_names"] = carry["company_policy_names"]
    if carry.get("project_policy_names"):
        payload["project_policy_names"] = carry["project_policy_names"]
    elif enterprise_ctx:
        payload["project_policy_names"] = _extract_project_policy_names(
            enterprise_ctx,
            enterprise_context_text,
        )

    if enterprise_ctx and enterprise_context_text:
        context_injection = dict(payload.get("context_injection") or {})
        context_injection.update(
            {
                "enterprise_context_used": True,
                "enterprise_context_length": len(enterprise_context_text),
                "enterprise_context_status": "success",
                "document_context_used": bool(enterprise_ctx.get("matched_contexts")),
                "document_context_length": len(enterprise_ctx.get("matched_contexts") or []),
                "document_context_status": "success"
                if enterprise_ctx.get("matched_contexts")
                else "not_fetched",
            }
        )
        payload["context_injection"] = context_injection

    return payload
