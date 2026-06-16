"""
ThinkVelocity middleware package.

Exposes log-scrubbing utilities for the Python (FastAPI) services.

Usage:
    from configs.middleware import LogScrubberMiddleware, scrub_string, scrub_dict
    app.add_middleware(LogScrubberMiddleware)
"""

from .log_scrubber import (
    LogScrubberMiddleware,
    ScrubFilter,
    scrub_dict,
    scrub_string,
)

__all__ = [
    "LogScrubberMiddleware",
    "ScrubFilter",
    "scrub_dict",
    "scrub_string",
]
