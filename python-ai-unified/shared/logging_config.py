"""
shared/logging_config.py — Structured logging for the unified python-ai service.

Honors the LOG_LEVEL setting and attaches the existing ThinkVelocity log
scrubber (configs/middleware/log_scrubber.ScrubFilter) to the root logger so
secrets (Groq/OpenAI keys, JWTs, DB URLs, PII) never reach any log handler.

If the scrubber import path is unavailable at runtime (service deployed in
isolation without configs/ on sys.path), logging is still configured and we
degrade gracefully without the scrubber.
"""

from __future__ import annotations

import logging
import sys
from typing import Optional

from .settings import settings

_configured = False


def _attach_scrub_filter(root: logging.Logger) -> bool:
    """Attach the shared ScrubFilter to the root logger. Returns success.

    Prefers the vendored copy (shared/log_scrubber.py) so the scrubber works
    in isolated deploys (Docker image without the repo's configs/ on path),
    falling back to the canonical configs/middleware copy for local dev.
    """
    try:
        from .log_scrubber import ScrubFilter  # type: ignore  # vendored, self-contained
    except Exception:  # noqa: BLE001
        try:
            from configs.middleware.log_scrubber import ScrubFilter  # type: ignore
        except Exception:  # noqa: BLE001 - isolated deploy without either source
            return False

    for existing in root.filters:
        if isinstance(existing, ScrubFilter):
            return True
    root.addFilter(ScrubFilter())
    return True


def configure_logging(level: Optional[str] = None) -> None:
    """
    Configure root logging once, honoring LOG_LEVEL, and install the scrubber.

    Idempotent: safe to call multiple times (e.g. at import and in lifespan).
    """
    global _configured
    if _configured:
        return

    log_level_name = (level or settings.LOG_LEVEL or "INFO").upper()
    log_level = getattr(logging, log_level_name, logging.INFO)

    root = logging.getLogger()
    root.setLevel(log_level)

    # Avoid duplicate handlers on repeated configuration.
    if not any(
        isinstance(h, logging.StreamHandler) for h in root.handlers
    ):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s [%(name)s] %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S%z",
            )
        )
        root.addHandler(handler)

    scrubbed = _attach_scrub_filter(root)

    logging.getLogger("thinkvelocity.logging").info(
        "logging configured: level=%s scrubber=%s",
        log_level_name,
        "on" if scrubbed else "unavailable",
    )
    _configured = True


# Configure at import so any module logging immediately is covered.
configure_logging()
