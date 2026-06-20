"""Credential / secret disclosure detection — ported from PromptEnhancement RegexContentModerator."""

from __future__ import annotations

import re

# Assignment-style disclosure patterns (not keyword-only mentions).
_CREDENTIAL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"\b(?:my\s+)?(?:password|passowrd|pasword|passwrd|p@ssword|pwd|passwords|passcode|pin|otp|credential(?:s)?)\b"
        r"\s*(?:for\s+\w+\s+)?(?:is|=|:)\s*([\"']?)(?!\1\b)[^\s\"'`]{4,}\1",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:api\s*key|access\s*token|secret\s*key|private\s*key|auth\s*token|token)\b\s*(?:is|=|:)\s*\S{8,}",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:password|passowrd|pasword|passwrd|p@ssword|pwd|passwords|passcode|pin|otp|credential(?:s)?|token|secret|api\s*key)\b"
        r"(?:\s+(?:for|of|to|id|is)\s+\w+)*(?:\s+is)?\s+"
        r"(?!(?:strength|reset|manager|policy|length|field|input|hint|label|help|kya|honi|chahiye|ko|ka|ke|ki|hai|nahi|wala|the|a|an|my|our|your|their)\b)"
        r"[A-Za-z0-9@#$%^&*._\-]{6,}\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bBearer\s+[A-Za-z0-9\-_.]{16,}\b", re.IGNORECASE),
    re.compile(
        r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b",
        re.IGNORECASE,
    ),
]

_GENERIC_VALUE_WORDS = frozenset({
    "password", "passcode", "credential", "credentials", "token", "secret",
    "mail", "email", "account", "login", "reset", "forgot", "change",
    "strong", "weak", "secure", "example", "sample", "test", "demo",
    "passwords", "credential", "pan", "pancard", "pan-card", "aadhaar",
    "aadhar", "card", "wrong", "wring", "forgotten", "security", "key",
})


def _is_likely_sensitive_disclosure(text: str) -> bool:
    """True only for likely secret disclosure, not plain keyword mentions."""
    if not text:
        return False

    raw = text.strip()
    if re.search(r"\bbearer\s+[a-z0-9\-_.]{16,}\b", raw, re.IGNORECASE):
        return True
    if re.search(
        r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b",
        raw,
    ):
        return True

    implicit_match = re.search(
        r"\b(?:password|passowrd|pasword|passwrd|p@ssword|pwd|passwords|passcode|pin|otp|credential(?:s)?|token|secret|api\s*key)\b"
        r"(?:\s+(?:for|of|to|id|is)\s+\w+)*\s+(?:is\s+)?([A-Za-z0-9@#$%^&*._\-]{6,})\s*$",
        raw,
        re.IGNORECASE,
    )
    if implicit_match:
        implicit_value = implicit_match.group(1).strip().strip(".,;")
        if implicit_value.lower() not in _GENERIC_VALUE_WORDS:
            has_digit = any(ch.isdigit() for ch in implicit_value)
            has_symbol = any(ch in "_-@#$%^&*+=!?." for ch in implicit_value)
            if has_digit or has_symbol or len(implicit_value) >= 6:
                return True

    value_match = re.search(r"(?:is|=|:)\s*([\"']?)([^\s\"'`]{2,})\1", raw, re.IGNORECASE)
    if not value_match:
        return False

    value = value_match.group(2).strip().strip(".,;")
    if value.lower() in _GENERIC_VALUE_WORDS or len(value) < 4:
        return False

    has_digit = any(ch.isdigit() for ch in value)
    has_symbol = any(ch in "_-@#$%^&*+=!?." for ch in value)
    if has_digit or has_symbol:
        return True
    return len(value) >= 6


def _classify_credential_type(matched_text: str) -> str:
    lower_data = matched_text.lower()
    if any(x in lower_data for x in ["password", "passwords", "passcode", "pin", "credential"]):
        return "password"
    if any(x in lower_data for x in ["api", "token", "secret", "key", "bearer", "eyj"]):
        return "api_key"
    if any(x in lower_data for x in ["otp"]):
        return "otp"
    return "credential"


def _mask_credential_value(matched_text: str, data_type: str) -> str:
    value_only = (
        matched_text.split("=")[-1].split(":")[-1].strip()
        if ("=" in matched_text or ":" in matched_text)
        else matched_text
    )
    if len(value_only) <= 4:
        return "****"
    if data_type in {"password", "api_key", "otp", "credential"}:
        return f"{value_only[:2]}{'*' * max(len(value_only) - 2, 2)}"
    return f"{value_only[:3]}{'*' * max(len(value_only) - 3, 2)}"


def scan_credential_disclosure(prompt: str) -> tuple[str | None, str | None, str]:
    """Scan for pol2 credential disclosure.

    Returns (credential_type, matched_text, redacted_prompt) or (None, None, original).
    """
    for pattern in _CREDENTIAL_PATTERNS:
        match = pattern.search(prompt)
        if not match:
            continue
        matched_text = match.group(0)
        if not _is_likely_sensitive_disclosure(matched_text):
            continue

        cred_type = _classify_credential_type(matched_text)
        masked = _mask_credential_value(matched_text, cred_type)
        redacted = prompt[: match.start()] + f"[REDACTED:{cred_type.upper()}]" + prompt[match.end() :]
        return cred_type, matched_text, redacted

    return None, None, prompt
