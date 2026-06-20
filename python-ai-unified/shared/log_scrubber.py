"""
shared/log_scrubber.py — Vendored log scrubber for the unified python-ai service.
SOC2 CC6.7 — No sensitive data in logs.

This is a SELF-CONTAINED copy of configs/middleware/log_scrubber.py so the
unified service scrubs secrets even when deployed in isolation (Docker image
without the repo's configs/ directory on sys.path).

CANONICAL SOURCE: configs/middleware/log_scrubber.py. Keep this copy in sync,
or replace both with a pip-installable shared package (see T-052). Any change
to the redaction patterns MUST be mirrored in the canonical file.

Provides:
    scrub_string(text)            -> str
    scrub_dict(d)                 -> Any   (recursive, redacts sensitive keys)
    ScrubFilter                   -> logging.Filter (attach to root logger)
    LogScrubberMiddleware         -> Starlette middleware (safe request logging)
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# ---------------------------------------------------------------------------
# Compiled patterns — created once at import, never per-call
# ---------------------------------------------------------------------------

# JWT bearer tokens (header.payload.signature)
_RE_JWT = re.compile(r'eyJ[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+')

# Groq API keys
_RE_GROQ = re.compile(r'gsk_[A-Za-z0-9]{20,}')

# OpenAI / generic sk- keys
_RE_OPENAI = re.compile(r'sk-[A-Za-z0-9]{20,}')

# Anthropic API keys
_RE_ANTHROPIC = re.compile(r'sk-ant-[A-Za-z0-9\-_]{20,}')

# SendGrid API keys
_RE_SENDGRID = re.compile(r'SG\.[A-Za-z0-9\-_]{22,}\.[A-Za-z0-9\-_]{43,}')

# Razorpay key IDs and secrets
_RE_RAZORPAY_KEY = re.compile(r'rzp_(live|test)_[A-Za-z0-9]{14,}')

# Razorpay payment signatures (40-char hex)
_RE_RAZORPAY_SIG = re.compile(
    r'(razorpay_signature|payment_signature)[=:\s"\']+[a-f0-9]{40}',
    re.IGNORECASE,
)

# AWS access key IDs
_RE_AWS_KEY = re.compile(r'AKIA[A-Z0-9]{16}')

# AWS secret access keys
_RE_AWS_SECRET = re.compile(
    r'(aws_secret_access_key|aws_secret)[=:\s"\']+[A-Za-z0-9\/+]{40}',
    re.IGNORECASE,
)

# 6-digit OTP codes in auth context
_RE_OTP = re.compile(
    r'\b(otp|one.?time.?pass(?:word)?|verification.?code)[=:\s"\']+\d{6}\b',
    re.IGNORECASE,
)

# UUID v4 refresh tokens
_RE_UUID_TOKEN = re.compile(
    r'(refresh_token|refresh|token_id)[=:\s"\']+[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}',
    re.IGNORECASE,
)

# Credit card PAN (13–19 digits, optionally separated by spaces or dashes)
_RE_PAN = re.compile(r'\b(?:\d[ \-]?){13,18}\d\b')

# Email addresses — will be partially masked
_RE_EMAIL = re.compile(
    r'\b([A-Za-z0-9._%+\-]+)@([A-Za-z0-9.\-]+\.[A-Za-z]{2,})\b'
)

# Python-specific: Django/Flask secret key in settings output
_RE_DJANGO_SECRET = re.compile(
    r"(SECRET_KEY\s*=\s*['\"])[^'\"]{20,}(['\"])",
    re.IGNORECASE,
)

# DSN / database URL (contains password)
_RE_DATABASE_URL = re.compile(
    r'(postgres(?:ql)?|mysql|mongodb)://[^:]+:[^@]+@',
    re.IGNORECASE,
)

# Field names whose values should ALWAYS be fully redacted
_SENSITIVE_FIELD_RE = re.compile(
    r'^(password|passwd|pwd|secret|token|api[_\-]?key|auth|credential|'
    r'authorization|private[_\-]?key|access[_\-]?key|refresh[_\-]?token|'
    r'otp|pin|card[_\-]?number|cvv|ssn|passphrase)$',
    re.IGNORECASE,
)


def scrub_string(text: str) -> str:
    """Scrub a string of all known sensitive patterns. Safe for hot paths."""
    if not isinstance(text, str):
        return text

    # Order matters: apply most specific patterns first
    text = _RE_JWT.sub('[JWT_REDACTED]', text)
    text = _RE_ANTHROPIC.sub('[ANTHROPIC_KEY_REDACTED]', text)
    text = _RE_GROQ.sub('[GROQ_KEY_REDACTED]', text)
    text = _RE_OPENAI.sub('[OPENAI_KEY_REDACTED]', text)
    text = _RE_SENDGRID.sub('[SENDGRID_KEY_REDACTED]', text)
    text = _RE_RAZORPAY_KEY.sub('[RAZORPAY_KEY_REDACTED]', text)
    text = _RE_RAZORPAY_SIG.sub(r'\1=[RAZORPAY_SIG_REDACTED]', text)
    text = _RE_AWS_KEY.sub('[AWS_KEY_ID_REDACTED]', text)
    text = _RE_AWS_SECRET.sub(r'\1=[AWS_SECRET_REDACTED]', text)
    text = _RE_OTP.sub(r'\1=[OTP_REDACTED]', text)
    text = _RE_UUID_TOKEN.sub(r'\1=[REFRESH_TOKEN_REDACTED]', text)
    text = _RE_PAN.sub('[PAN_REDACTED]', text)
    text = _RE_DJANGO_SECRET.sub(r'\1[SECRET_KEY_REDACTED]\2', text)
    text = _RE_DATABASE_URL.sub(
        lambda m: m.group(0).split('://')[0] + '://[CREDENTIALS_REDACTED]@',
        text,
    )
    # Partial email masking: user@domain.tld → u***@***.tld
    text = _RE_EMAIL.sub(
        lambda m: f"{m.group(1)[0]}***@***.{m.group(2).rsplit('.', 1)[-1]}",
        text,
    )
    return text


def scrub_dict(d: Any, _depth: int = 0) -> Any:
    """Recursively scrub a dict/list. Sensitive keys → '[REDACTED]'."""
    if _depth > 10:
        return '[DEPTH_LIMIT]'

    if d is None:
        return d

    if isinstance(d, str):
        return scrub_string(d)

    if isinstance(d, (int, float, bool)):
        return d

    if isinstance(d, list):
        return [scrub_dict(item, _depth + 1) for item in d]

    if isinstance(d, dict):
        out: dict[str, Any] = {}
        for key, value in d.items():
            if _SENSITIVE_FIELD_RE.match(str(key)):
                out[key] = '[REDACTED]'
            else:
                out[key] = scrub_dict(value, _depth + 1)
        return out

    return d


class ScrubFilter(logging.Filter):
    """logging.Filter that scrubs sensitive patterns from every LogRecord."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        record.msg = scrub_string(str(record.msg))
        if record.args:
            if isinstance(record.args, dict):
                record.args = scrub_dict(record.args)
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    scrub_string(a) if isinstance(a, str) else a
                    for a in record.args
                )
        if record.exc_text:
            record.exc_text = scrub_string(record.exc_text)
        return True  # always allow through (just scrubbed)


_logger = logging.getLogger('thinkvelocity.access')


class LogScrubberMiddleware(BaseHTTPMiddleware):
    """
    Starlette middleware that logs each request as a single-line JSON with
    SAFE fields only. NEVER logs request body, Authorization header, or query
    parameter values. ScrubFilter provides defence-in-depth on the JSON itself.
    """

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        start_ns = time.perf_counter_ns()
        response: Response = await call_next(request)
        duration_ms = (time.perf_counter_ns() - start_ns) / 1_000_000
        safe_path = scrub_string(request.url.path)

        log_entry = {
            'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'level': (
                'error' if response.status_code >= 500
                else 'warn' if response.status_code >= 400
                else 'info'
            ),
            'method': request.method,
            'path': safe_path,
            'status_code': response.status_code,
            'duration_ms': round(duration_ms, 2),
            'user_agent': scrub_string(request.headers.get('user-agent', '')),
            'request_id': request.headers.get('x-request-id', '')
                          or request.headers.get('x-correlation-id', ''),
            # Intentionally omitted: request body, Authorization header,
            # query parameter values (may contain tokens).
        }
        _logger.info(json.dumps(log_entry))
        return response
