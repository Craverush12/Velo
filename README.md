# ThinkVelocity

A lean, self-hosted prompt engineering assistant. Single FastAPI service with a browser UI — no database, no heavy infrastructure required.

---

## What it does

**Enhance** — paste a rough prompt, get back a production-grade version. The LLM applies prompt engineering techniques (chain-of-thought, persona injection, constraint definition, few-shot examples, etc.) and returns an annotated result showing exactly what changed and why.

**Refine** — iteratively improve an existing enhanced prompt through a guided, context-aware Q&A loop. Neuro prepares the most important clarification questions, shows useful memory patterns, then finalizes a stronger prompt from the original prompt, previous draft, answers, and context.

**CoThinker** — voice-first collaborative thinking partner. Speak your idea, CoThinker has a real conversation with you (not a form-fill interrogation), confirms 10 key dimensions of your prompt through natural dialogue, and only generates the final enhanced prompt once it has what it needs. Uses Groq Whisper for speech-to-text and Microsoft edge-tts for high-quality voice output. Optionally queries the web in real-time mid-conversation to ground recommendations in current tools and best practices.

**Brain (Memory)** — a knowledge graph of your prompt history, visualised as a live network. Prompts cluster by domain and intent.

**Profile (Personalization)** — tell Velocity how you work in natural language. It extracts reusable preferences such as style, tone, tools, formats, and things to avoid, then safely injects that profile into future prompt enhancement.

**Neuro Orchestrator + NeuroPrompt Signal** — infers the user's goal, context needs, smallest useful next action, workflow hints, memory candidates, and product signals. It also scores prompts with a brain-response-inspired heuristic for clarity, attention, structure, output grounding, multimodal readiness, and personal fit. This is not fMRI prediction.

**Research / Build / Media modes** — mode-specific workflows that route the same prompt surface toward evidence-heavy research, implementation-ready build work, or media/design prompt generation.

**Uploads** — attach text, images, and documents as prompt context. Video and 3D uploads are intentionally rejected in this release.

**Settings modal** — Connectors, Diagnostics, and Version now live behind the persistent top-right settings button so the workspace, sidebar, prompt, uploads, and Neuro state remain stable.

**MCP server** — exposes Enhance and Refine as tools over the Model Context Protocol so Claude Desktop, Cursor, and other MCP clients can call ThinkVelocity directly.

---

## Quick start

### Requirements

- Python 3.11+
- A [Groq API key](https://console.groq.com) (free tier works)

### 1. Clone and install

```bash
git clone <your-repo-url>
cd ThinkVelocity
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Open `.env` and set at minimum:

```env
GROQ_API_KEY=your_groq_key_here
```

See the full environment variable reference below.

### 3. Run

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Open [http://localhost:8000](http://localhost:8000).

---

## Environment variables

### Required

| Variable | Description |
|---|---|
| `GROQ_API_KEY` | Groq API key. Powers all LLM calls and speech-to-text. Get one free at [console.groq.com](https://console.groq.com). |

### Models

| Variable | Default | Description |
|---|---|---|
| `ENHANCE_MODEL` | `llama-3.3-70b-versatile` | Model used for the Enhance pipeline |
| `REFINE_MODEL` | `llama-3.3-70b-versatile` | Model used for the Refine pipeline |
| `LLM_MODEL` | `llama-3.3-70b-versatile` | Fallback model if specific model vars are not set |

Any Groq-hosted model works. `llama-3.3-70b-versatile` is the recommended default — it handles structured JSON output reliably and is fast enough for voice-loop latency.

### Application

| Variable | Default | Description |
|---|---|---|
| `APP_ENV` | `development` | Environment label. Set to `production` for deployed instances. |
| `ENABLE_REMOTE_TEST_RUNNER` | `false` | Set to `true` only during deployment verification if you need `POST /diagnostics/tests` in production. |

### Storage

| Variable | Default | Description |
|---|---|---|
| `STORAGE_BACKEND` | `local` | Where prompts and sessions are persisted. The current runtime supports local JSON storage only. |
| `STORAGE_PATH` | `storage/data` | Path for local JSON storage. Created automatically on startup. When running in Docker, set to `/data` and mount a volume there. |

For Lightsail, keep `STORAGE_BACKEND=local` and use a persistent Docker volume or `/var/lib/thinkvelocity`.

### MCP client

| Variable | Default | Description |
|---|---|---|
| `VELOCITY_USER_ID` | `anonymous` | Username attached to stored prompts. |
| `VELOCITY_API_URL` | `http://localhost:8000` | URL of this server as seen by the MCP client. Use your Railway/Render URL in production. |

### CoThinker — web search (optional)

| Variable | Description |
|---|---|
| `SERPER_API_KEY` | Enables real-time web search inside CoThinker conversations. When set, CoThinker can look up current tools, frameworks, and domain best practices mid-conversation and use that information to give sharper recommendations. Get a free key (2500 queries/month) at [serper.dev](https://serper.dev). If not set, CoThinker works normally without search — the feature degrades gracefully. |

---

## CoThinker — how it works

CoThinker runs as a voice call. The flow per turn:

1. Click **Start Speaking** — browser captures audio via MediaRecorder + Web Audio API
2. After 1.8 seconds of silence, recording stops automatically (silence detection via RMS threshold on the audio analyser node)
3. Audio is posted to `/cothinker/transcribe` → Groq Whisper (`whisper-large-v3`) returns a transcript
4. Transcript goes to `/cothinker/turn` → LLM responds conversationally and extracts any confirmed fields from what you said as structured JSON
5. If the LLM decides a web search would help, it signals this and the server queries Serper, injects results into a second LLM call, and returns a grounded reply — all transparently
6. Reply is posted to `/cothinker/speak` → Microsoft `en-US-GuyNeural` via edge-tts returns audio
7. Audio plays back. The checklist on screen updates in real-time as fields are confirmed.
8. Once 8+ of 10 fields are confirmed (or you say "go" / "generate"), CoThinker calls `/cothinker/finalize` → produces a full enhanced prompt using the same output schema as the Enhance pipeline

**The 10 things CoThinker confirms through conversation** (not as a form — extracted from natural dialogue):

| Field | What it captures |
|---|---|
| Target AI | Which model the prompt will be used with |
| Core Goal | The single most important thing the prompt must do |
| Task Type | Category of work (code, writing, analysis, research, etc.) |
| Domain | Field or industry |
| Audience | Who reads or uses the output |
| Output Format | What the result looks like |
| Constraints | What the AI must or must not do |
| Context | Background information the AI needs |
| Tone | Voice and style |
| Success Criteria | What makes the output excellent, not just okay |

Session state is kept server-side (in-memory, 1-hour TTL). The `session_id` returned on the first turn is sent with every subsequent turn — the browser handles this automatically.

You can also type instead of speaking using the text input below the mic button. Clicking the mic while CoThinker is speaking interrupts playback immediately.

---

## API reference

```
POST /enhance                          — enhance a prompt
POST /refine                           — refine with clarification answers
POST /refine/prepare                   — prepare guided refinement questions and context patterns
POST /refine/finalize                  — finalize guided refinement and return memory candidates
POST /intent/confirm                   — classify intent before enhancement
POST /intent/update                    — normalize a client-edited intent confirmation
GET  /context/{user_id}               — get stored user context
PATCH /context/{user_id}              — update stored user context
GET  /history/{user_id}               — prompt history
POST /personalization/{user_id}/extract — extract and optionally save profile preferences
POST /neuro/score                     — NeuroPrompt Signal heuristic scorecard
POST /neuro/state                     — infer Neuro goal state and context needs
POST /neuro/decide                    — choose the smallest useful next action
POST /uploads                         — upload text/images/documents as context
GET  /uploads/{upload_id}             — read upload metadata
DELETE /uploads/{upload_id}           — delete uploaded context

POST /cothinker/turn                   — one dialogue turn
POST /cothinker/transcribe             — audio → transcript (Groq Whisper)
POST /cothinker/speak                  — text → audio (edge-tts)
POST /cothinker/finalize               — conversation → enhanced prompt

GET  /diagnostics/systems             — system health check
GET  /diagnostics/mcp-tools           — MCP tool manifest
POST /diagnostics/tests               — run test suite (disabled in production unless ENABLE_REMOTE_TEST_RUNNER=true)

GET  /health                           — service health + model info
GET  /ready                            — deployment readiness: Groq key configured + storage writable
```

All LLM calls use Groq JSON mode. System prompts live in `core/prompts/` as `.md` files, loaded with explicit UTF-8 decoding.

---

## MCP integration

ThinkVelocity exposes `enhance_prompt` and `refine_prompt` as MCP tools over stdio.

### Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "thinkvelo": {
      "command": "python",
      "args": ["/absolute/path/to/ThinkVelocity/mcp/stdio.py"],
      "env": {
        "VELOCITY_API_URL": "http://localhost:8000",
        "VELOCITY_USER_ID": "your-username"
      }
    }
  }
}
```

The FastAPI server must be running before the MCP client connects.

### Install helper

```bash
python mcp/stdio.py --install
```

This writes the config to discovered Claude Desktop / Cursor config paths automatically.

---

## Docker

### Run locally with Docker Compose

```bash
docker compose up --build
```

Prompt data is stored in a named Docker volume mounted at `/data`.

### Environment

Pass variables via `docker-compose.yml` or a `.env` file at the project root. The compose file already wires up `GROQ_API_KEY` and sets `STORAGE_PATH=/data`.

### Railway / Heroku-style platforms

A `railway.toml` and `Procfile` are included. Set `GROQ_API_KEY` and any other required vars in the platform dashboard. The server binds to `$PORT` automatically.

---

## Running tests

```bash
pytest tests/
```

Or with the standard runner:

```bash
python -m unittest discover -s tests
```

Tests cover: output validator, refine backend, intent classifier, prompt contracts, health endpoint, and storage. They hit the real Groq API, so `GROQ_API_KEY` must be set.

---

## Project structure

```
ThinkVelocity/
├── main.py                          — FastAPI app, router registration, startup
├── requirements.txt
├── api/
│   ├── enhance.py                   — POST /enhance
│   ├── refine.py                    — POST /refine
│   ├── cothinker.py                 — POST /cothinker/* (voice loop + finalize)
│   ├── intent.py                    — POST /intent/confirm, POST /intent/update
│   ├── context.py                   — GET/PATCH /context
│   ├── diagnostics.py               — GET /diagnostics/*
│   └── mcp.py                       — MCP HTTP bridge
├── core/
│   ├── llm.py                       — Groq client, complete(), complete_multi_turn()
│   ├── contracts.py                 — Shared types (PromptMode, TargetAI, etc.)
│   ├── output_validator.py          — JSON parse + schema validation + repair
│   ├── prompts/
│   │   ├── enhance_system.md        — Enhance system prompt
│   │   ├── refine_system.md         — Refine system prompt
│   │   ├── cothinker_system.md      — CoThinker dialogue system prompt
│   │   └── cothinker_finalize_system.md  — CoThinker → enhanced prompt
│   └── ...
├── mcp/
│   ├── stdio.py                     — MCP stdio server entry point
│   └── tools.py                     — Tool definitions
├── static/
│   └── index.html                   — Single-file browser UI (no build step)
├── storage/
│   └── store.py                     — JSON storage (local / S3 / LightSail)
└── tests/
```

---

## Tech stack

| Layer | Choice |
|---|---|
| Backend | FastAPI + Uvicorn |
| LLM | Groq API — `llama-3.3-70b-versatile` |
| Speech-to-text | Groq Whisper REST API — `whisper-large-v3` |
| Text-to-speech | edge-tts — `en-US-GuyNeural` (Microsoft neural voice, free) |
| Web search | Serper.dev — Google Search via REST (optional) |
| Storage | JSON files — local disk, S3, or LightSail |
| Frontend | Vanilla JS + CSS, single HTML file, no build step |
| MCP | Model Context Protocol stdio server |
