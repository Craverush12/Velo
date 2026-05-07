import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()

from api.enhance import router as enhance_router
from api.refine import router as refine_router
from api.context import router as context_router
from api.mcp import router as mcp_router

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
app.include_router(context_router)
app.include_router(mcp_router)

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
    }


@app.on_event("startup")
def startup():
    Path(os.getenv("STORAGE_PATH", "storage/data")).mkdir(parents=True, exist_ok=True)
