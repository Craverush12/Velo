import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from core.prompt_metadata import prompt_metadata
from core.scheduler import create_scheduler
from storage import store

load_dotenv()

from api.enhance import router as enhance_router
from api.refine import router as refine_router
from api.intent import router as intent_router
from api.context import router as context_router
from api.mcp import router as mcp_router
from api.diagnostics import router as diagnostics_router
from api.cothinker import router as cothinker_router
from api.personalization import router as personalization_router
from api.neuro import router as neuro_router
from api.agentic import router as agentic_router
from api.connectors import router as connectors_router
from api.profile import router as profile_router
from api.uploads import router as uploads_router

app = FastAPI(title="ThinkVelocity", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(enhance_router)
app.include_router(refine_router)
app.include_router(intent_router)
app.include_router(context_router)
app.include_router(mcp_router)
app.include_router(diagnostics_router)
app.include_router(cothinker_router)
app.include_router(personalization_router)
app.include_router(neuro_router)
app.include_router(agentic_router)
app.include_router(connectors_router)
app.include_router(profile_router)
app.include_router(uploads_router)

_STATIC = Path(__file__).parent / "static"
if _STATIC.exists():
    app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")


@app.get("/")
def index():
    return FileResponse(str(_STATIC / "index.html"))


@app.get("/health")
def health():
    return {
        "status": "ok",
        "model": os.getenv("LLM_MODEL", "llama-3.3-70b-versatile"),
        "env": os.getenv("APP_ENV", "development"),
        **prompt_metadata(),
    }


@app.get("/ready")
def ready():
    storage = store.storage_healthcheck()
    groq_configured = bool(os.getenv("GROQ_API_KEY"))
    ok = storage["ok"] and groq_configured
    return {
        "status": "ok" if ok else "not_ready",
        "checks": {
            "groq_api_key": groq_configured,
            "storage": storage,
        },
    }


@app.on_event("startup")
async def startup():
    store.storage_path()
    app.state.velocity_scheduler = create_scheduler()
    app.state.velocity_scheduler.start()


@app.on_event("shutdown")
async def shutdown():
    scheduler = getattr(app.state, "velocity_scheduler", None)
    if scheduler is not None:
        await scheduler.shutdown()
