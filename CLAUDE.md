# ThinkVelocity Agent Notes

## What This Is
Lean prompt-engineering SaaS. Single FastAPI service with two core LLM functions: enhance and refine.

## Current Source Of Truth
- Runtime prompts: `core/prompts/enhance_system.md` and `core/prompts/refine_system.md`
- Shared contracts: `core/contracts.py`
- Browser UI: `static/index.html`
- MCP runtime: `mcp/tools.py` and `mcp/stdio.py`
- Historical build specs: `outdated/`

Do not rebuild from the historical specs unless the user explicitly asks for archaeology. They are superseded by the runtime code and README.

## Environment
- Local-first; no Postgres, Redis, or Docker required.
- LLM: Groq API via the `groq` Python SDK. Key is in `.env`.
- Storage: JSON files in `storage/data/`, auto-created at startup.
- Server runs on `http://localhost:8000`.

## Hard Rules
- No placeholder code. Every file must be complete and runnable.
- Single FastAPI app only; no inter-service calls.
- System prompts live in `core/prompts/` as `.md` files.
- Load prompt files with explicit UTF-8 decoding.
- Use `response_format={"type": "json_object"}` on all Groq calls.
- CORS must allow all origins for local dev and direct HTML usage.
