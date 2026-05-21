# NeuroPrompt + Personalization Task List

Date: 2026-05-21

## Coordination Rules

- Backend lane owns API contracts, storage schema, context injection, and MCP tool wiring.
- Frontend lane owns `static/index.html` only.
- Tests/docs lane owns tests, smoke scripts, README, deployment notes, and this task list.
- Shared files are `main.py` and `api/diagnostics.py`; only one lane should edit each in a single pass.
- Real TRIBE v2 inference remains a later gated lab. The live sprint ships NeuroPrompt Signal and personalization first.

## Subagent Lanes

| Lane | Suggested Subagent | Ownership | Status |
|---|---|---|---|
| Backend | Backend Worker | `api/personalization.py`, `api/neuro.py`, `core/*contracts.py`, `core/context_loader.py`, `storage/store.py`, `mcp/tools.py`, `main.py` | In progress |
| Frontend | Frontend Worker | `static/index.html` Profile page, NeuroPrompt card, Signal tab, diagnostics cards | In progress |
| Tests/Docs | Verification Worker | `tests/test_personalization_backend.py`, `tests/test_neuro_backend.py`, `scripts/smoke_api.sh`, docs | In progress |
| TRIBE Lab | Research Worker | Optional `requirements-tribe.txt`, `/tribe/status`, `/tribe/analyze`, license gate | Pending |

## Task Checklist

- [x] Add structured personalization contracts and extraction endpoint.
- [x] Include saved profile context before the first enhancement, not only after history exists.
- [x] Add NeuroPrompt scoring contracts and `/neuro/score`.
- [x] Surface personalization metadata in Enhance results when non-incognito profile data is active.
- [x] Add MCP `score_neuroprompt` tool.
- [x] Add Profile UI page using Velocity/Figma-inspired bento styling.
- [x] Add NeuroPrompt Signal card and Signal details tab after enhancement.
- [x] Add diagnostics entries for personalization and NeuroPrompt scoring.
- [x] Add backend tests for profile extraction and NeuroPrompt scoring.
- [x] Add smoke flags for personalization and NeuroPrompt scoring.
- [ ] Run full test suite.
- [ ] Run browser/UI smoke after starting the dev server.
- [ ] Add real TRIBE v2 lab only after license/runtime decision.

## Acceptance Criteria

- A new user can save personalization notes before any prompt history exists.
- Enhance uses saved preferences when incognito is off.
- Incognito mode omits profile context and does not write memory.
- NeuroPrompt Signal renders without blocking the enhanced prompt.
- Diagnostics can verify personalization and NeuroPrompt endpoints.
- TRIBE v2 is not marketed as live fMRI prediction in this sprint.
