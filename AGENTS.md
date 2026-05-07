# ThinkVelocity — Build Instructions

## What This Is
Lean prompt engineering SaaS. Single FastAPI service. Two core LLM functions.
Build spec is split across two files in this repo — read BOTH before writing anything.

## Spec Files (read in this order)
1. `THINKVELO_BUILD.md` — base architecture, all file specs, directory structure
2. `THINKVELO_BUILD_V2_PATCH.md` — replaces the system prompts, adds annotated output JSON schema, adds memory graph to HTML

Where the patch says "REPLACEMENT:" — that section fully overrides the corresponding section in the base spec.

## Environment
- Local only. No Postgres. No Redis. No Docker required.
- LLM: Groq API via `groq` Python SDK. Key is in `.env`.
- Storage: JSON files in `storage/data/`. Auto-created at startup.
- Server runs on `http://localhost:8000`

## Execution Order
Build tasks in this exact order. Complete and verify each before the next.
Do not start `static/index.html` until all API endpoints return correct responses.

## Hard Rules
- No placeholder code. Every file must be complete and runnable.
- No inter-service calls. Single FastAPI app only.
- System prompts live in `core/prompts/` as `.md` files. Load them with `Path(__file__).parent`.
- Use `response_format={"type": "json_object"}` on all Groq calls.
- CORS must allow all origins (local dev, HTML file opens directly in browser).