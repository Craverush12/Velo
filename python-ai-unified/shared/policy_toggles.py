"""Enterprise DLP rule toggles (pol1..pol7) — ported from PromptEnhancement."""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from shared.legacy_compat import policy_keys_for_verdict

logger = logging.getLogger(__name__)

_DECISION_ALLOW = "ALLOW"

CATEGORY_TOGGLE_KEYS: dict[str, list[str]] = {
    "sensitive_data": ["sensitive_data", "dlp_sensitive_data", "pol1", "pol2", "pol3", "pol4", "pol5"],
    "pii": ["pol1"],
    "violence": ["violence", "dlp_violence", "pol7"],
    "illegal_activities": ["illegal_activities", "dlp_illegal_activities"],
    "self_harm": ["self_harm", "dlp_self_harm"],
    "hate_speech": ["hate_speech", "dlp_hate_speech"],
    "sexual_content": ["sexual_content", "dlp_sexual_content"],
    "medical_misinformation": ["medical_misinformation", "dlp_medical_misinformation"],
    "cybercrime": ["cybercrime", "dlp_cybercrime", "illegal_activities", "dlp_illegal_activities"],
    "malware": ["pol6"],
    "fraud": ["pol6"],
    "illicit": ["pol6"],
    "csam": ["pol7"],
    "credentials": ["pol2"],
    "confidential": ["pol3"],
    "legal_risk": ["pol3"],
    "financial_sensitive": ["pol3"],
}

PII_LABEL_POLICY_KEYS: dict[str, list[str]] = {
    "ssn": ["pol1"],
    "email": ["pol1"],
    "phone": ["pol1"],
    "ip_address": ["pol1"],
    "credit_card": ["pol4"],
}

REGEX_LABEL_POLICY_KEYS: dict[str, list[str]] = {
    "violence": ["pol7"],
    "malware": ["pol6"],
    "csam": ["pol7"],
    "fraud": ["pol6"],
    "illicit": ["pol6"],
    "credentials": ["pol2"],
}

RAG_LABEL_POLICY_KEYS: dict[str, list[str]] = {
    "violence": ["pol7"],
    "malware": ["pol6"],
    "csam": ["pol7"],
    "fraud": ["pol6"],
    "illicit": ["pol6"],
    "pii": ["pol1"],
    "confidential": ["pol3"],
    "borderline": ["pol5"],
}

POLICY_TOGGLE_PROMPT_RULES: dict[str, dict[str, str]] = {
    "pol1": {
        "name": "Hide Personal Information",
        "detect": "Names, emails, phone numbers, and personal identifiers.",
    },
    "pol2": {
        "name": "Block Passwords and API Keys",
        "detect": "Passwords, OTPs, API keys, tokens, private keys, seed phrases, and secrets.",
    },
    "pol3": {
        "name": "Protect Confidential Project Data",
        "detect": "Internal proprietary source code, internal architecture details, and private implementation details.",
    },
    "pol4": {
        "name": "Allow Only Approved Usage",
        "detect": "Credit card numbers, IBANs, SWIFT/BIC codes, CVV, and bank account numbers.",
    },
    "pol5": {
        "name": "Check Prompt Quality and Compliance",
        "detect": "Regulated medical/PHI data and diagnosis/treatment identifiers tied to a person.",
    },
    "pol6": {
        "name": "Malicious Domain Filtering",
        "detect": "Malicious/phishing/C2 domains or URLs used for cyber abuse.",
    },
    "pol7": {
        "name": "Violence and Harm Filtering",
        "detect": "Direct threats, instructions, or actionable requests involving violence or physical harm.",
    },
}


def is_rule_enabled(toggle_map: dict[str, bool], keys: list[str]) -> bool:
    """Rule is enabled by default; when scoped keys exist, enabled if any mapped key is ON."""
    if not toggle_map:
        return True

    scoped_values = [bool(toggle_map[key]) for key in keys if key in toggle_map]
    if not scoped_values:
        return True

    return any(scoped_values)


def is_category_enabled(toggle_map: dict[str, bool], category: str) -> bool:
    normalized_category = str(category or "").lower()
    keys = CATEGORY_TOGGLE_KEYS.get(normalized_category, [normalized_category])
    return is_rule_enabled(toggle_map, keys)


def is_verdict_enabled_by_toggles(verdict: dict[str, Any], toggle_map: dict[str, bool]) -> bool:
    """Return True when the verdict should remain after applying enterprise toggles."""
    if not toggle_map:
        return True

    decision = str(verdict.get("decision", _DECISION_ALLOW)).upper()
    if decision == _DECISION_ALLOW:
        return True

    policy_keys = policy_keys_for_verdict(verdict)
    dlp_keys = [key for key in policy_keys if key.startswith("pol")]
    if dlp_keys:
        return any(bool(toggle_map.get(policy_key, True)) for policy_key in dlp_keys)

    category = str(verdict.get("category", "")).lower()
    return is_category_enabled(toggle_map, category)


def build_toggle_llm_instructions(toggle_map: dict[str, bool]) -> str:
    """Tell the LLM which DLP rules are OFF so it does not flag disabled categories."""
    if not toggle_map:
        return ""

    off_lines: list[str] = []
    for policy_key, policy_meta in POLICY_TOGGLE_PROMPT_RULES.items():
        if policy_key in toggle_map and not bool(toggle_map[policy_key]):
            off_lines.append(
                f"- {policy_key} ({policy_meta['name']}): {policy_meta['detect']}"
            )

    if not off_lines:
        return ""

    return (
        "\n\nThe following enterprise Data Protection Rules are turned OFF. "
        "Do NOT flag, redact, block, or require approval for content that would "
        "only violate these disabled rules. Return ALLOW for such content.\n"
        + "\n".join(off_lines)
    )


def apply_toggle_map_to_verdict(
    verdict: dict[str, Any],
    toggle_map: dict[str, bool],
    *,
    enterprise_id: str,
    user_id: str,
) -> dict[str, Any]:
    """Downgrade a verdict to ALLOW when all matched DLP toggles are OFF."""
    if not toggle_map or is_verdict_enabled_by_toggles(verdict, toggle_map):
        return verdict

    return {
        "decision": _DECISION_ALLOW,
        "category": "benign",
        "confidence": 1.0,
        "reason": "Matched content is allowed because the related Data Protection Rule is turned off.",
        "redacted_text": None,
        "method": "toggle_filter",
        "enterprise_id": enterprise_id,
        "user_id": user_id,
        "cached": False,
        "toggle_filtered": True,
        "original_decision": verdict.get("decision"),
        "original_category": verdict.get("category"),
    }


async def fetch_active_toggle_map(
    enterprise_id: str | None,
    team_id: str | None = None,
) -> dict[str, bool]:
    """Fetch enterprise/team rule toggle map from NestJS; empty dict when unavailable."""
    if not enterprise_id or enterprise_id in {"default", "anonymous"}:
        return {}

    base_url = os.getenv("ENTERPRISE_BACKEND_BASE_URL", "").rstrip("/")
    if not base_url:
        return {}

    endpoint = os.getenv(
        "ENTERPRISE_RULE_TOGGLES_ENDPOINT",
        "/public-context/rules/active-map",
    )

    async def _fetch_scope(scope_type: str, scope_ref: str) -> dict[str, bool]:
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                response = await client.get(
                    f"{base_url}{endpoint}",
                    params={
                        "enterpriseId": enterprise_id,
                        "scopeType": scope_type,
                        "scopeRef": scope_ref,
                    },
                    headers={"Accept": "application/json"},
                )
                if response.status_code != 200:
                    logger.info(
                        "[MODERATION][TOGGLES] scope=%s:%s unavailable | status=%s",
                        scope_type,
                        scope_ref,
                        response.status_code,
                    )
                    return {}

                payload = response.json()
                raw_map = payload.get("activeToggleMap") if isinstance(payload, dict) else None
                if not isinstance(raw_map, dict):
                    return {}

                return {str(key): bool(value) for key, value in raw_map.items()}
        except Exception as exc:  # noqa: BLE001
            logger.info(
                "[MODERATION][TOGGLES] scope=%s:%s fetch error: %s",
                scope_type,
                scope_ref,
                exc,
            )
            return {}

    merged_map = await _fetch_scope("ENTERPRISE", "global")
    if team_id:
        merged_map.update(await _fetch_scope("TEAM", str(team_id)))
    return merged_map
