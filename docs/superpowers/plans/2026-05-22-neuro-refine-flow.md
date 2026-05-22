# Neuro Unified Workspace Execution Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`. This plan is designed for parallel completion by focused subagents with clear file ownership. Avoid creating new test files by default; verify with existing tests, API route smoke checks, and browser QA unless a regression cannot be covered otherwise.

**Goal:** Redesign ThinkVelocity into a quieter unified workspace where Neuro drives the right workflow, Refine asks only useful questions, uploads become context, settings live in a persistent top-right modal, and Research / Build / Media modes guide users to their desired outcome with minimal UI noise.

**Architecture:** Treat the product as a bounded state machine: `User Input + Mode + Uploads + Memory -> NeuroGoalState -> NeuroDecision -> Workflow Execution -> Artifact + Memory/Product Signals`. Settings are not a workspace page. Connectors, diagnostics, and version move into a settings modal. Compare is lazy: model comparison controls render only after the user clicks Compare.

**Verification Strategy:** Existing unit tests, route smoke checks for `/uploads`, `/neuro/state`, `/refine/prepare`, `/refine/finalize`, and browser QA for desktop/mobile overflow and flow persistence.

---

## Product Direction

### What Changes

Current UI has too many page-like surfaces:

```text
Enhance
Memory
Profile
Connectors
Diagnostics
Version
Right panel tabs: Annotations / Signal / Metadata / Raw
```

New UI should feel like one persistent command surface:

```text
Left: primary workflow navigation
Center: current work and artifact
Right: quiet Neuro context panel
Top right: Settings modal
```

### Primary Modes

Only three main modes:

```text
Research
Build
Media
```

Each mode triggers a different workflow:

- **Research:** clarify intent, gather context, use memory/sources when needed, produce research-ready prompt or answer scaffold.
- **Build:** optimize for implementation-ready prompts, code-agent instructions, acceptance criteria, files, tasks, and structured plans.
- **Media:** optimize for image/audio/design/video-adjacent prompt generation, visual constraints, format, style, aspect ratio, and platform fit. Accept images and files as context, but reject video and 3D uploads in this phase.

### Settings Modal

Move these into Settings:

```text
Connectors
Diagnostics
Version / Release
API status
Model config
User/Profile settings
```

Settings opens from a persistent top-right gear button. It should be a modal or drawer, not a workspace page. Opening and closing it must not reset the current prompt, uploads, Neuro state, refine session, or generated artifact.

### Right Neuro Panel

The attached screenshot shows the current panel is too page-like and noisy. Replace it with a quieter contextual panel:

```text
Neuro
- Goal
- Context
- Next step
- Signal
```

No always-visible `Annotations / Signal / Metadata / Raw` tab row. Advanced details should live behind a small “Inspect” disclosure inside the panel.

---

## Subagent-Driven Strategy

Run this as five focused subagents plus one integrator.

### Subagent A: Backend Neuro + Refine

Owns:

- `core/neuro_state.py`
- `core/prompts/neuro_goal_state_system.md`
- `core/prompts/neuro_orchestrator_system.md`
- `core/prompts/refine_prepare_system.md`
- `api/neuro.py`
- `api/refine.py`

Must not touch:

- `static/index.html`
- upload storage implementation
- release docs except endpoint notes handed to integrator

### Subagent B: Uploads API

Owns:

- `api/uploads.py`
- `main.py`
- `storage/store.py` only if upload metadata persistence is needed
- `requirements.txt` only if absolutely required

Must not touch:

- Neuro/refine prompt logic
- UI except endpoint contract notes

### Subagent C: Unified UI Shell

Owns:

- `static/index.html`

Focus:

- persistent workspace
- top-right settings modal
- moving Connectors/Diagnostics/Version into settings
- right Neuro panel redesign
- compare drawer behavior
- mobile responsiveness

Must not touch:

- backend routes
- docs except notes to integrator

### Subagent D: Mode Workflows + Upload UI

Owns:

- `static/index.html`

Focus:

- Research / Build / Media workflow behavior
- upload chips and attachment context
- guided Refine UI
- action-card Signal UI

Coordination:

- Must coordinate with Subagent C because both touch `static/index.html`.
- Recommended order: Subagent C lands shell first; Subagent D builds workflow components on top.

### Subagent E: Documentation + Release

Owns:

- `README.md`
- `docs/deployment/lightsail.md`
- Version content inside `static/index.html` only after UI owner has finished

### Integrator

Owns:

- conflict resolution
- final browser QA
- local route smoke
- live deploy
- release confirmation

---

## Phase 1: Backend Neuro + Refine Core

### Objective

Create the operating layer without overbuilding UI.

### Implementation

Create `core/neuro_state.py` with:

```python
NeuroGoalState
NeuroTriggerPolicy
NeuroDecision
RefineQuestion
RefinePrepareResult
NeuroActionCard
NeuroMemoryCandidate
```

Core policy fields:

```text
user_final_goal
immediate_task
success_definition
selected_mode: research | build | media
target_ai
confidence
can_act_now
blocking_gaps
fastest_next_action
trigger_policy
product_signals
```

Create prompts:

```text
core/prompts/neuro_goal_state_system.md
core/prompts/neuro_orchestrator_system.md
core/prompts/refine_prepare_system.md
```

Important prompt rule:

```text
Only ask, show, search, connect, save, or escalate when it materially helps the user reach the final goal faster.
```

Add routes:

```text
POST /neuro/state
POST /neuro/decide
POST /refine/prepare
POST /refine/finalize
```

Keep compatible:

```text
POST /refine
POST /neuro/score
```

### Acceptance Criteria

- `/neuro/state` returns a valid goal state for Research / Build / Media.
- `/neuro/decide` returns a minimal next action.
- `/refine/prepare` returns 1-3 questions with `why_it_matters`.
- `/refine/finalize` returns refined prompt, changes summary, and optional memory candidates.
- Existing refine/neuro tests still pass.

### Verification

```powershell
python -m unittest tests.test_neuro_backend tests.test_refine_backend tests.test_output_validator
```

Route smoke:

```powershell
Invoke-WebRequest -Uri "http://127.0.0.1:8000/neuro/state" -Method POST -ContentType "application/json" -Body '{"user_input":"Refine this into a build-ready agent prompt.","selected_mode":"build","prompt_mode":"build"}'

Invoke-WebRequest -Uri "http://127.0.0.1:8000/refine/prepare" -Method POST -ContentType "application/json" -Body '{"original_prompt":"Build a dashboard from API data.","user_id":"sandbox-user","prompt_mode":"build","incognito":true}'
```

---

## Phase 2: Uploads API

### Objective

Accept useful context uploads for Research / Build / Media workflows while rejecting video and 3D files.

### Supported Upload Types

Allow:

```text
text/plain
text/markdown
application/json
text/csv
application/pdf
application/vnd.openxmlformats-officedocument.wordprocessingml.document
application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
image/png
image/jpeg
image/webp
image/gif
```

Reject:

```text
video/*
model/*
application/octet-stream unless extension is explicitly allowed
.mp4 .mov .avi .mkv .webm
.glb .gltf .obj .fbx .stl .blend
```

### API Design

Create:

```text
POST /uploads
GET /uploads/{upload_id}
DELETE /uploads/{upload_id}
```

Upload response:

```json
{
  "upload_id": "uuid",
  "filename": "brief.pdf",
  "content_type": "application/pdf",
  "kind": "document",
  "size_bytes": 12345,
  "text_preview": "first useful extracted text",
  "status": "ready"
}
```

### Storage Strategy

Initial implementation:

```text
storage/uploads/{user_id}/{upload_id}/original
storage/uploads/{user_id}/{upload_id}/metadata.json
```

Keep metadata bounded and safe:

```text
max upload size: 15MB
max text preview stored: 12,000 chars
filename sanitized
user_id validated through existing pattern
```

For images:

```text
store metadata and file path
do not attempt heavy image analysis in this phase
send as attachment metadata/context to Neuro
```

For PDFs/DOCX/XLSX:

```text
extract text only if current dependencies already support it
otherwise store file and return metadata with "text_preview": ""
```

### Acceptance Criteria

- Text/image/document upload succeeds.
- Video upload returns 415.
- 3D file upload returns 415.
- Oversized upload returns 413.
- Upload metadata can be passed into `/neuro/state` and `/refine/prepare`.

### Verification

```powershell
Invoke-WebRequest -Uri "http://127.0.0.1:8000/uploads" -Method POST -Form @{file=Get-Item ".\README.md"; user_id="sandbox-user"}
```

Reject check:

```powershell
Invoke-WebRequest -Uri "http://127.0.0.1:8000/uploads" -Method POST -Form @{file=Get-Item ".\sample.mp4"; user_id="sandbox-user"}
```

Expected: 415 for video.

---

## Phase 3: Unified Persistent UI Shell

### Objective

Reduce noise and remove settings-like pages from the main workspace.

### Sidebar

Sidebar should contain only primary workflow navigation:

```text
Research
Build
Media
Memory
Profile
```

Remove from sidebar:

```text
Connectors
Diagnostics
Version
```

### Topbar

Top-right:

```text
Incognito
Settings gear
Status dot
```

Settings gear opens a modal/drawer:

```text
Settings
- Connectors
- Diagnostics
- Version
- API / Model
- User profile
```

### Settings Modal

Implementation in `static/index.html`:

```html
<button class="settings-btn" id="settingsBtn" onclick="openSettings()" title="Settings">...</button>
<div class="settings-overlay" id="settingsOverlay" onclick="closeSettings()"></div>
<aside class="settings-modal" id="settingsModal">
  ...
</aside>
```

Behavior:

- Modal overlays current workspace.
- Closing returns to the exact current workflow.
- No `showView('connectors')`, `showView('diagnostics')`, or `showView('version')` as primary pages.
- Existing settings content can be reused inside modal panels.

### Right Neuro Panel

Replace noisy tabs with one compact panel:

```text
Neuro
Goal: ...
Context: ...
Next: ...
Signal: ...
[Inspect]
```

`Inspect` reveals:

```text
Raw state
metadata
annotations
debug JSON
```

This directly addresses the screenshot: no large empty “Annotations appear after enhancement” panel.

### Acceptance Criteria

- Connectors/Diagnostics/Version no longer appear as primary sidebar items.
- Settings opens from top-right and persists across workflows.
- Switching settings tabs does not reset current prompt, uploads, or generated result.
- Right panel is compact and useful even before enhancement.

---

## Phase 4: Mode Workflows

### Objective

Make Research / Build / Media real workflow modes, not cosmetic tabs.

### Research Mode

Default behavior:

```text
Goal: understand, investigate, synthesize
Neuro asks about scope/freshness only if needed
Memory may be used silently
Search/source context only when freshness or factual grounding matters
Output optimized for citations/context-ready prompts
```

UI:

```text
Prompt box placeholder: "What do you want to understand or investigate?"
Upload hint: notes, PDFs, articles, CSVs
Refine questions prioritize scope, source type, depth, recency
```

### Build Mode

Default behavior:

```text
Goal: produce executable instructions or implementation artifacts
Neuro prioritizes environment, constraints, acceptance criteria, files
Uploads treated as specs/assets/context
Output optimized for Codex/Cursor/Claude code-agent use
```

UI:

```text
Prompt box placeholder: "What do you want to build, fix, or ship?"
Upload hint: specs, screenshots, logs, code snippets
Refine questions prioritize stack, target files, acceptance tests, constraints
```

### Media Mode

Default behavior:

```text
Goal: create visual/audio/design prompts and assets
Accept images and documents
Reject video and 3D files in this phase
Output optimized for visual constraints, style, ratio, subject clarity
```

UI:

```text
Prompt box placeholder: "What media output do you want to create?"
Upload hint: images, references, brand notes
Refine questions prioritize subject, format, style, aspect ratio, platform
```

### Acceptance Criteria

- Mode switch changes placeholder, helper copy, Neuro goal state mode, and refine question priorities.
- Mode state persists across settings open/close.
- Mode is sent as `prompt_mode`: `research`, `build`, or `media`.
- Existing backend currently uses `fast_build`; if not renamed immediately, add adapter:

```text
UI "Build" -> backend "fast_build"
```

Docs should call the user-facing mode “Build.”

---

## Phase 5: Compare Drawer

### Objective

Hide model comparison controls until the user explicitly asks for comparison.

### Current Problem

Model A / Model B selects are always visible, adding noise.

### New Behavior

Default:

```text
[Compare] button only
```

On click:

```text
open compare drawer/row
show Model A
show Model B
show Run Compare
show Close
```

The first click should not immediately run comparison. It should reveal controls.

Second action:

```text
Run Compare
```

### Acceptance Criteria

- Model selectors are hidden on initial page load.
- Clicking Compare reveals selector UI.
- User can change models.
- Run Compare triggers comparison.
- Closing drawer keeps current prompt/result intact.

---

## Phase 6: Guided Refine UI

### Objective

Make Improve/Refine a guided, context-aware flow.

### UI Steps

When user clicks Refine:

```text
1. Neuro prepares context.
2. Panel shows "What I understood."
3. Panel shows "Useful history" only if useful.
4. Panel asks 1-3 targeted questions.
5. User answers or skips with assumptions.
6. Final refined prompt is generated.
7. UI shows what changed and memory learned.
```

### Layout

Use center workspace, not a tiny modal:

```text
Refine Prompt
What I understood
Questions
Generate improved version
```

Right Neuro panel mirrors:

```text
Goal
Questions
Signal
Memory
```

### Acceptance Criteria

- No generic “Anything else?” as a core question.
- Every question has `why_it_matters`.
- User can use chips or custom answer.
- Incognito hides/suppresses memory learning.
- Final prompt includes clarification answers.

---

## Phase 7: Upload UI Integration

### Objective

Make uploads feel like context, not a separate feature.

### UI

Add attach button near prompt box:

```text
[Attach]
```

After upload:

```text
chips:
brief.pdf
reference.png
notes.md
```

Each chip:

```text
filename
kind
remove button
```

Rejected files show clear error:

```text
Video and 3D files are not supported yet. Upload images, text, PDFs, docs, sheets, or CSVs.
```

### Workflow Use

Uploads are included in:

```text
/neuro/state
/refine/prepare
/enhance
agentic work context later
```

Initial backend may pass only metadata + text preview into LLM. Do not send raw binary to Groq unless explicitly supported later.

### Acceptance Criteria

- Text file upload appears as context chip.
- Image upload appears as context chip.
- Video/3D rejection is clear.
- Removing upload updates state.
- Refine prepare can see uploaded context metadata.

---

## Phase 8: Action-Card Signal UI

### Objective

Make Neuro Signal actionable but not noisy.

### UI

In right Neuro panel:

```text
Signal 82
Top improvement:
Add acceptance criteria
Why: ...
Patch: ...
[Copy]
```

Full list behind:

```text
View all suggestions
```

Do not add Apply yet unless patch insertion is reliable. Copy is enough.

### Acceptance Criteria

- Existing score still renders.
- Action cards render when present.
- Empty action cards do not show blank UI.
- Long patch text wraps on mobile.

---

## Phase 9: Memory + Product Signals

### Objective

Capture useful learning without silently overfitting user profile.

### Rules

Save only when:

```text
incognito=false
refinement succeeds
candidate has key + value
candidate is not duplicate
```

Do not promote to stable preference from one event. Store as candidate:

```json
{
  "type": "pattern",
  "key": "prefers_acceptance_criteria",
  "value": "User often wants acceptance criteria in build prompts.",
  "evidence": "Refine answer",
  "product_signal": "Offer acceptance criteria chip in Build mode."
}
```

### Bounded Storage

Keep:

```text
max 30 candidates
dedupe by key + value
newest first
```

### Acceptance Criteria

- Incognito writes nothing.
- Duplicate candidate is not appended.
- Context endpoint exposes candidates safely.
- Product signals can be shown in Settings > Diagnostics or hidden under Inspect.

---

## Phase 10: Release Documentation

### Objective

Update docs after behavior works.

### README

Add:

```text
Unified Workspace
Neuro Operating Layer
Guided Refine Flow
Research / Build / Media modes
Uploads as context
Settings modal
Lazy model comparison
```

### Deployment Runbook

Add smoke checks:

```bash
curl -fsS -X POST https://your-domain.example/neuro/state \
  -H 'Content-Type: application/json' \
  --data '{"user_input":"Refine this into a build-ready prompt.","selected_mode":"build","prompt_mode":"fast_build"}'

curl -fsS -X POST https://your-domain.example/refine/prepare \
  -H 'Content-Type: application/json' \
  --data '{"original_prompt":"Build a dashboard from API data.","user_id":"demo-user","prompt_mode":"fast_build","incognito":true}'
```

### Version Modal

Since Version moves into Settings, update release copy there:

```text
Neuro Operating Layer
Guided Refine Flow
Uploads API
Research / Build / Media workflows
Persistent settings modal
Lazy model compare
Unified low-noise interface
```

---

## Final QA Matrix

### API

```text
/ready
/health
/uploads text success
/uploads image success
/uploads video reject
/uploads 3D reject
/neuro/state
/neuro/decide
/refine/prepare
/refine/finalize
/neuro/score
```

### UI Desktop

```text
Settings button top-right
Connectors/Diagnostics/Version inside settings
Sidebar has primary workflow only
Research/Build/Media modes persist
Compare controls hidden until clicked
Upload chips render
Refine flow works
Right Neuro panel is compact
No giant empty annotation panel
```

### UI Mobile

```text
No horizontal overflow
Settings modal usable
Upload chips wrap
Compare drawer usable
Refine questions readable
Neuro panel collapses or stacks cleanly
```

### Deployment

```text
local tests pass
local browser QA pass
live /ready ok
live route smoke pass
live browser mobile overflow 0
```

---

## Execution Order

1. Subagent A: Backend Neuro + Refine.
2. Subagent B: Uploads API.
3. Subagent C: Unified shell + settings modal.
4. Subagent D: Modes, uploads UI, refine UI, compare drawer, action cards.
5. Subagent E: Docs and release copy.
6. Integrator: merge, resolve `static/index.html`, QA, deploy.

Important sequencing:

```text
Backend routes before UI wiring.
Settings shell before moving settings content.
Compare drawer before mode workflow polish.
Docs last.
Deploy only after browser QA.
```

