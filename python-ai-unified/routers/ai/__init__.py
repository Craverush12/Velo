"""Assembles the unified ``/ai/*`` router from its sub-routers.

The parent app mounts this under prefix ``/ai`` (see merge plan §4), so each
sub-router uses prefix "" (or a small group prefix like "/quality",
"/diagnostic") to produce the documented unified paths.

Routes implemented (41 total: the 40 from the task's router groups +
/domain-analyzer to fully cover the documented endpoint map):
  enhance      : /enhance/stream, /enhance/chat                        (2)
  refine       : /refine, /refine/chat, /refine/chat/stream            (3)
  clarify      : /clarify, /clarify/chat/mcq                           (2)
  recommendation: /recommendation                                      (1)
  media        : /media/enhance, /transcribe                           (2)
  quality      : /quality/{metrics,accuracy,performance,
                 mode-distribution,health,analyze-prompt}              (6)
  moderation   : /moderation/{check,examples,check/batch,
                 document/classify,document/upload,cache,stats,health}  (9)
  context_docs : /context/{upload,retrieve,{id}/info,{id}},
                 /embeddings/generate                                  (5)
  prompt_find  : /prompt/find                                          (1)
  diagnostic   : /diagnostic/{domain,intent,web-search,rag-strategies,
                 target-ai,complexity,all,health}                      (8)
  health       : /health, /domain-analyzer                            (2)
"""

from __future__ import annotations

import importlib
import logging

from fastapi import APIRouter

ai_router = APIRouter()

logger = logging.getLogger("thinkvelocity.unified.routers.ai")

_ROUTER_MODULES = (
    "enhance",
    "refine",
    "clarify",
    "recommendation",
    "media",
    "quality",
    "moderation",
    "context_docs",
    "prompt_find",
    "diagnostic",
    "health",
)

mounted_router_modules: list[str] = []
skipped_router_modules: dict[str, str] = {}

for module_name in _ROUTER_MODULES:
    try:
        module = importlib.import_module(f"{__name__}.{module_name}")
        router = getattr(module, "router")
    except ImportError as exc:
        skipped_router_modules[module_name] = str(exc)
        logger.warning("Skipped /ai/%s router: %s", module_name, exc)
        continue
    except AttributeError as exc:
        skipped_router_modules[module_name] = str(exc)
        logger.warning("Skipped /ai/%s router: missing router object", module_name)
        continue

    ai_router.include_router(router)
    mounted_router_modules.append(module_name)

__all__ = ["ai_router", "mounted_router_modules", "skipped_router_modules"]
