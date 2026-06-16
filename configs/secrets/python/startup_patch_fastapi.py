"""
startup_patch_fastapi.py — FastAPI integration pattern for AWS Secrets Manager.

─────────────────────────────────────────────────────────────────────────────
PROBLEM
─────────────────────────────────────────────────────────────────────────────
Pydantic BaseSettings (v1 and v2) reads environment variables at class
*definition* time — i.e., the moment Python imports the module that contains
the Settings class.  This means:

    from config import settings   ← Settings() already evaluated here

Any os.environ mutation AFTER that import is too late for the settings object
already in memory (though os.environ is correct for everything else).

─────────────────────────────────────────────────────────────────────────────
SOLUTION
─────────────────────────────────────────────────────────────────────────────
Call init_secrets() as the FIRST executable statement in main.py / app.py,
before ANY other project import.  The pattern is shown below.

─────────────────────────────────────────────────────────────────────────────
COPY THIS BLOCK TO THE TOP OF main.py (python-ai service)
─────────────────────────────────────────────────────────────────────────────

    # ── Secret bootstrap — MUST be first, before any project imports ──────
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from configs.secrets.python.secrets_loader import init_secrets
    init_secrets("thinkvelocity/production/python-ai")
    # ── End secret bootstrap ──────────────────────────────────────────────

    # All other imports follow AFTER the block above:
    from fastapi import FastAPI
    from dotenv import load_dotenv
    load_dotenv()          # no-op for keys already injected by init_secrets
    ...

─────────────────────────────────────────────────────────────────────────────
COPY THIS BLOCK TO THE TOP OF main.py (extension-api service)
─────────────────────────────────────────────────────────────────────────────

    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from configs.secrets.python.secrets_loader import init_secrets
    init_secrets("thinkvelocity/production/extension-api")

    from fastapi import FastAPI
    from dotenv import load_dotenv
    load_dotenv()
    ...

─────────────────────────────────────────────────────────────────────────────
RUNNABLE DEMO MINI-APP
─────────────────────────────────────────────────────────────────────────────
This file doubles as a standalone demo you can run directly to verify the
loader works in your environment:

    python configs/secrets/python/startup_patch_fastapi.py

It will print which source was used and whether the key variables are set.
"""

from __future__ import annotations

# ── Step 1: inject secrets before any project code is imported ──────────────
import os
import sys

# When running this file directly, make the project root importable.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)
))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from configs.secrets.python.secrets_loader import get_source, init_secrets  # noqa: E402

# Change the service name to match whichever service this main.py belongs to.
SERVICE_SECRET_NAME = "thinkvelocity/production/python-ai"
init_secrets(SERVICE_SECRET_NAME)

# ── Step 2: now it's safe to import anything that reads env vars ─────────────
# Example: pydantic Settings, config modules, ORM init, etc.
# from config import settings    ← will see the SM values because they are
#                                   already in os.environ at this point.

# ── Step 3: build the FastAPI app as normal ──────────────────────────────────
try:
    from fastapi import FastAPI

    app = FastAPI(title="python-ai demo", version="1.0.0")

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "secrets_source": get_source(),
            "groq_key_set": bool(os.getenv("GROQ_API_KEY")),
            "db_url_set": bool(os.getenv("DATABASE_URL")),
            "redis_url_set": bool(os.getenv("REDIS_URL")),
        }

except ImportError:
    app = None  # FastAPI not installed in this environment; that's fine for a demo


# ── CLI self-test ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    print("\n=== ThinkVelocity — Secrets Loader Self-Test ===")
    print(f"  Service secret name : {SERVICE_SECRET_NAME}")
    print(f"  Secrets source      : {get_source()}")
    print(f"  GROQ_API_KEY set    : {bool(os.getenv('GROQ_API_KEY'))}")
    print(f"  DATABASE_URL set    : {bool(os.getenv('DATABASE_URL'))}")
    print(f"  REDIS_URL set       : {bool(os.getenv('REDIS_URL'))}")
    print(f"  APP_ENV             : {os.getenv('APP_ENV', '(not set)')}")
    print(f"  AWS_REGION          : {os.getenv('AWS_REGION', '(not set)')}")
    print("=================================================\n")

    if app is not None:
        print("FastAPI app created successfully.")
        print("Run with:  uvicorn configs.secrets.python.startup_patch_fastapi:app --reload")
    else:
        print("FastAPI not installed; skipping app creation.")
