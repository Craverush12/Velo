from __future__ import annotations

import hmac
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import create_engine, text as sql_text

from core import admin_auth
from core.connectors_catalog import connector_catalog_summary
from core.prompt_metadata import prompt_metadata
from core.prompt_modes import prompt_versions
from core.source_catalog import load_source_catalog
from storage import store as velocity_store
from storage.admin_store import AdminStore, get_default_store
from storage.db import normalize_database_url
from storage.prompt_trace_store import PromptTraceStore, get_default_store as get_default_trace_store

_PROD_ENGINE = None


def _prod_engine():
    global _PROD_ENGINE
    if _PROD_ENGINE is None:
        url = os.getenv("ADMIN_DATABASE_URL", "").strip() or os.getenv("DATABASE_URL", "").strip()
        if url:
            try:
                _PROD_ENGINE = create_engine(normalize_database_url(url), pool_pre_ping=True, future=True)
            except Exception:
                pass
    return _PROD_ENGINE


router = APIRouter(prefix="/admin/api", tags=["admin"])

MANAGED_ENTITY_TYPES = {
    "announcements",
    "faqs",
    "feature-flags",
    "pricing-plans",
    "usage-limits",
    "prompt-templates",
}


class LoginRequest(BaseModel):
    email: str
    password: str


class ManagedEntityWrite(BaseModel):
    slug: str = Field(..., min_length=3, max_length=160)
    title: str = Field(..., min_length=1, max_length=255)
    status: str = "draft"
    payload: dict[str, Any] = Field(default_factory=dict)


class ManagedEntityPatch(BaseModel):
    slug: str | None = Field(default=None, min_length=3, max_length=160)
    title: str | None = Field(default=None, min_length=1, max_length=255)
    status: str | None = None
    payload: dict[str, Any] | None = None


class RuntimeConfigPatch(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)


class AdminUserCreate(BaseModel):
    email: str
    display_name: str
    password: str = Field(..., min_length=10)
    role: str

    @field_validator("role", mode="before")
    @classmethod
    def valid_role(cls, value: str) -> str:
        return admin_auth.normalize_role(value)


class AdminUserPatch(BaseModel):
    display_name: str | None = None
    password: str | None = Field(default=None, min_length=10)
    role: str | None = None
    status: str | None = None

    @field_validator("role", mode="before")
    @classmethod
    def valid_role(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return admin_auth.normalize_role(value)


class UserContextPatch(BaseModel):
    personalization_notes: str | None = None
    preferences: dict[str, Any] | None = None


class TestRunRequest(BaseModel):
    suite: str = "all"


def get_admin_store() -> AdminStore:
    return get_default_store()


def get_prompt_trace_store() -> PromptTraceStore:
    return get_default_trace_store()


def _bootstrap_if_configured(store: AdminStore) -> None:
    if store.count_active_admin_users() > 0:
        return
    email = os.getenv("ADMIN_BOOTSTRAP_EMAIL", "").strip()
    password = os.getenv("ADMIN_BOOTSTRAP_PASSWORD", "")
    if email and password:
        store.ensure_bootstrap_admin(email, password)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
    return forwarded or (request.client.host if request.client else "")


def _user_agent(request: Request) -> str:
    return request.headers.get("user-agent", "")


def _parse_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def require_admin(permission: str | None = None, *, csrf: bool = False):
    def dependency(
        request: Request,
        x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
        store: AdminStore = Depends(get_admin_store),
    ) -> dict[str, Any]:
        _bootstrap_if_configured(store)
        token = request.cookies.get(admin_auth.SESSION_COOKIE_NAME)
        if not token:
            raise HTTPException(status_code=401, detail="Admin login required")
        session = store.get_session_by_hash(admin_auth.hash_token(token))
        if not session or session.get("revoked_at"):
            raise HTTPException(status_code=401, detail="Admin session is invalid")
        if _parse_iso(session["expires_at"]) <= admin_auth.now_utc():
            raise HTTPException(status_code=401, detail="Admin session expired")
        admin = store.get_admin_by_id(session["admin_user_id"])
        if not admin or admin.get("status") != "active":
            raise HTTPException(status_code=401, detail="Admin account is inactive")
        if csrf:
            provided = admin_auth.hash_token(x_csrf_token or "")
            if not hmac.compare_digest(provided, session["csrf_hash"]):
                raise HTTPException(status_code=403, detail="CSRF token is missing or invalid")
        if permission and not admin_auth.role_has_permission(admin["role"], permission):
            raise HTTPException(status_code=403, detail="Admin role does not have permission")
        return {"admin": store.public_admin(admin), "session": session}

    return dependency


def require_prompt_trace_reader(permission: str = "operations:view"):
    def dependency(
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
        store: AdminStore = Depends(get_admin_store),
    ) -> dict[str, Any]:
        configured_token = os.getenv("PROMPT_ANALYTICS_API_TOKEN", "").strip()
        if configured_token and authorization:
            scheme, _, token = authorization.partition(" ")
            if scheme.lower() == "bearer" and hmac.compare_digest(token.strip(), configured_token):
                return {
                    "auth_type": "bearer",
                    "admin": {
                        "id": "prompt-analytics-token",
                        "email": "prompt-analytics-token",
                        "role": "analytics_reader",
                    },
                }
        return require_admin(permission)(request=request, x_csrf_token=None, store=store)

    return dependency


def _audit(
    *,
    store: AdminStore,
    request: Request,
    actor: dict[str, Any],
    action: str,
    entity_type: str,
    entity_id: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> None:
    store.record_audit(
        actor=actor,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before=before,
        after=after,
        ip_address=_client_ip(request),
        user_agent=_user_agent(request),
    )


@router.post("/login")
def login(request: Request, response: Response, body: LoginRequest, store: AdminStore = Depends(get_admin_store)):
    _bootstrap_if_configured(store)
    if store.count_active_admin_users() == 0:
        raise HTTPException(
            status_code=503,
            detail="No admin user exists. Set ADMIN_BOOTSTRAP_EMAIL and ADMIN_BOOTSTRAP_PASSWORD, then restart.",
        )
    admin = store.get_admin_by_email(body.email)
    if not admin or admin.get("status") != "active" or not admin_auth.verify_password(body.password, admin["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid admin credentials")

    session_token = admin_auth.generate_token()
    csrf_token = admin_auth.generate_token()
    store.create_session(
        admin_user_id=admin["id"],
        session_hash=admin_auth.hash_token(session_token),
        csrf_hash=admin_auth.hash_token(csrf_token),
        expires_at=admin_auth.session_expires_at(),
        ip_address=_client_ip(request),
        user_agent=_user_agent(request),
    )
    response.set_cookie(
        admin_auth.SESSION_COOKIE_NAME,
        session_token,
        max_age=admin_auth.SESSION_TTL_HOURS * 3600,
        httponly=True,
        secure=os.getenv("APP_ENV") == "production",
        samesite="lax",
        path="/",
    )
    return {"admin": store.public_admin(admin), "csrf_token": csrf_token}


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    store: AdminStore = Depends(get_admin_store),
    current: dict[str, Any] = Depends(require_admin(csrf=True)),
):
    token = request.cookies.get(admin_auth.SESSION_COOKIE_NAME)
    if token:
        store.revoke_session(admin_auth.hash_token(token))
    response.delete_cookie(admin_auth.SESSION_COOKIE_NAME, path="/")
    return {"status": "ok"}


@router.get("/me")
def me(current: dict[str, Any] = Depends(require_admin())):
    return {"admin": current["admin"], "csrf_required": True}


@router.get("/dashboard")
def dashboard(
    store: AdminStore = Depends(get_admin_store),
    current: dict[str, Any] = Depends(require_admin("dashboard:view")),
):
    total_users = 0
    active_subs = 0
    recent_users: list[dict[str, Any]] = []
    engine = _prod_engine()
    if engine:
        try:
            with engine.connect() as conn:
                total_users = conn.execute(sql_text("SELECT COUNT(*) FROM usertable")).scalar() or 0
                active_subs = conn.execute(
                    sql_text("SELECT COUNT(*) FROM subscriptions WHERE status='active'")
                ).scalar() or 0
                rows = conn.execute(sql_text("""
                    SELECT u.user_id, u.name, u.email, u.created_at,
                           s.status AS sub_status
                    FROM usertable u
                    LEFT JOIN subscriptions s ON s.user_id = u.user_id AND s.status = 'active'
                    ORDER BY u.created_at DESC LIMIT 8
                """)).mappings().all()
                recent_users = [
                    {
                        "user_id": str(r["user_id"]),
                        "name": r["name"] or "",
                        "email": r["email"] or "",
                        "created_at": r["created_at"].isoformat() if r["created_at"] else "",
                        "subscription_status": r["sub_status"] or "free",
                    }
                    for r in rows
                ]
        except Exception:
            pass
    return {
        "metrics": {
            "users": total_users,
            "active_subscriptions": active_subs,
            "prompt_activity": 0,
            "uploads": _count_uploads(),
            "evaluations": _count_evaluations(),
            "admin_users": store.list_admin_users()["total"],
            "audit_logs": store.list_audit_logs(page_size=1)["total"],
            "storage": velocity_store.storage_healthcheck(),
        },
        "recent_users": recent_users,
        "recent_audit_logs": store.list_audit_logs(page_size=8)["items"],
        "prompt_metadata": prompt_metadata(),
    }


@router.get("/audit-logs")
def audit_logs(
    search: str = "",
    page: int = 1,
    page_size: int = 50,
    store: AdminStore = Depends(get_admin_store),
    current: dict[str, Any] = Depends(require_admin("audit:view")),
):
    return store.list_audit_logs(search=search, page=page, page_size=page_size)


@router.get("/prompt-traces")
def prompt_traces(
    flow: str = "",
    status: str = "",
    user_id: str = "",
    prompt_mode: str = "",
    search: str = "",
    page: int = 1,
    page_size: int = 25,
    include_payload: bool = False,
    trace_store: PromptTraceStore = Depends(get_prompt_trace_store),
    current: dict[str, Any] = Depends(require_prompt_trace_reader()),
):
    return trace_store.list_traces(
        flow=flow,
        status=status,
        user_id=user_id,
        prompt_mode=prompt_mode,
        search=search,
        page=page,
        page_size=page_size,
        include_payload=include_payload,
    )


@router.get("/prompt-traces/{trace_id}")
def prompt_trace_detail(
    trace_id: str,
    trace_store: PromptTraceStore = Depends(get_prompt_trace_store),
    current: dict[str, Any] = Depends(require_prompt_trace_reader()),
):
    trace = trace_store.get(trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="Prompt trace not found")
    return {"trace": trace}


@router.get("/prompt-traces/{trace_id}/diff")
def prompt_trace_diff(
    trace_id: str,
    trace_store: PromptTraceStore = Depends(get_prompt_trace_store),
    current: dict[str, Any] = Depends(require_prompt_trace_reader()),
):
    diff = trace_store.diff(trace_id)
    if diff is None:
        raise HTTPException(status_code=404, detail="Prompt trace not found")
    return diff


@router.get("/prompt-metrics")
def prompt_metrics(
    days: int | None = None,
    trace_store: PromptTraceStore = Depends(get_prompt_trace_store),
    current: dict[str, Any] = Depends(require_prompt_trace_reader()),
):
    return {"metrics": trace_store.metrics(days=days)}


@router.get("/users")
def list_users(
    search: str = "",
    page: int = 1,
    page_size: int = 25,
    current: dict[str, Any] = Depends(require_admin("users:view")),
):
    engine = _prod_engine()
    if engine:
        try:
            needle = search.strip().lower()
            where = "WHERE (LOWER(u.name) LIKE :q OR LOWER(u.email) LIKE :q OR CAST(u.user_id AS TEXT) = :exact)" if needle else ""
            params: dict[str, Any] = {"limit": page_size, "offset": (page - 1) * page_size}
            if needle:
                params["q"] = f"%{needle}%"
                params["exact"] = needle
            with engine.connect() as conn:
                total = conn.execute(sql_text(f"SELECT COUNT(*) FROM usertable u {where}"), params).scalar() or 0
                rows = conn.execute(sql_text(f"""
                    SELECT u.user_id, u.name, u.email, u.created_at, u.updated_at,
                           u.email_verified, s.status AS sub_status
                    FROM usertable u
                    LEFT JOIN subscriptions s ON s.user_id = u.user_id AND s.status = 'active'
                    {where}
                    ORDER BY u.created_at DESC
                    LIMIT :limit OFFSET :offset
                """), params).mappings().all()
            items = [
                {
                    "user_id": str(r["user_id"]),
                    "name": r["name"] or "",
                    "email": r["email"] or "",
                    "email_verified": bool(r["email_verified"]),
                    "subscription_status": r["sub_status"] or "free",
                    "created_at": r["created_at"].isoformat() if r["created_at"] else "",
                    "updated_at": r["updated_at"].isoformat() if r["updated_at"] else "",
                }
                for r in rows
            ]
            return {"items": items, "total": total, "page": page, "page_size": page_size, "pages": max(1, -(-total // page_size))}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))
    return {"items": [], "total": 0, "page": page, "page_size": page_size, "pages": 0}


@router.get("/users/{user_id}")
def get_user(user_id: str, current: dict[str, Any] = Depends(require_admin("users:view"))):
    engine = _prod_engine()
    if engine:
        try:
            with engine.connect() as conn:
                row = conn.execute(sql_text("""
                    SELECT u.user_id, u.name, u.email, u.created_at, u.updated_at,
                           u.email_verified, u.google_id, u.onboarding_completed,
                           u.occupation, u.llm_platform,
                           s.status AS sub_status, s.current_period_end
                    FROM usertable u
                    LEFT JOIN subscriptions s ON s.user_id = u.user_id AND s.status = 'active'
                    WHERE u.user_id = :uid
                """), {"uid": int(user_id) if user_id.isdigit() else -1}).mappings().first()
                if row:
                    return {
                        "user_id": str(row["user_id"]),
                        "name": row["name"] or "",
                        "email": row["email"] or "",
                        "email_verified": bool(row["email_verified"]),
                        "google_id": row["google_id"] or "",
                        "onboarding_completed": bool(row["onboarding_completed"]),
                        "occupation": row["occupation"] or "",
                        "llm_platform": row["llm_platform"] or "",
                        "subscription_status": row["sub_status"] or "free",
                        "subscription_end": row["current_period_end"].isoformat() if row["current_period_end"] else None,
                        "created_at": row["created_at"].isoformat() if row["created_at"] else "",
                        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else "",
                    }
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
    raise HTTPException(status_code=404, detail="User not found")


@router.patch("/users/{user_id}")
def update_user(
    user_id: str,
    body: UserContextPatch,
    request: Request,
    store: AdminStore = Depends(get_admin_store),
    current: dict[str, Any] = Depends(require_admin("users:edit", csrf=True)),
):
    before = velocity_store.get_user_context(user_id)
    if body.personalization_notes is not None:
        velocity_store.update_personalization_notes(user_id, body.personalization_notes)
    if body.preferences is not None:
        velocity_store.update_preferences(user_id, body.preferences)
    after = velocity_store.get_user_context(user_id)
    _audit(
        store=store,
        request=request,
        actor=current["admin"],
        action="users.update",
        entity_type="user_context",
        entity_id=user_id,
        before=_context_audit_slice(before),
        after=_context_audit_slice(after),
    )
    return after


@router.post("/users/{user_id}/reset-memory")
def reset_user_memory(
    user_id: str,
    request: Request,
    store: AdminStore = Depends(get_admin_store),
    current: dict[str, Any] = Depends(require_admin("users:reset", csrf=True)),
):
    before = velocity_store.get_user_context(user_id)
    after = velocity_store.reset_user_context(user_id)
    _audit(
        store=store,
        request=request,
        actor=current["admin"],
        action="users.reset_memory",
        entity_type="user_context",
        entity_id=user_id,
        before=_context_audit_slice(before),
        after=_context_audit_slice(after),
    )
    return after


@router.get("/admin-users")
def list_admin_users(
    include_deleted: bool = False,
    store: AdminStore = Depends(get_admin_store),
    current: dict[str, Any] = Depends(require_admin("admin_users:view")),
):
    return store.list_admin_users(include_deleted=include_deleted)


@router.post("/admin-users")
def create_admin_user(
    body: AdminUserCreate,
    request: Request,
    store: AdminStore = Depends(get_admin_store),
    current: dict[str, Any] = Depends(require_admin("admin_users:manage", csrf=True)),
):
    if not admin_auth.can_manage_target_role(current["admin"]["role"], body.role):
        raise HTTPException(status_code=403, detail="Cannot assign that admin role")
    created = store.create_admin_user(
        email=body.email,
        display_name=body.display_name,
        password=body.password,
        role=body.role,
        actor_id=current["admin"]["id"],
    )
    _audit(
        store=store,
        request=request,
        actor=current["admin"],
        action="admin_users.create",
        entity_type="admin_user",
        entity_id=created["id"],
        before=None,
        after=created,
    )
    return created


@router.patch("/admin-users/{admin_user_id}")
def update_admin_user(
    admin_user_id: str,
    body: AdminUserPatch,
    request: Request,
    store: AdminStore = Depends(get_admin_store),
    current: dict[str, Any] = Depends(require_admin("admin_users:manage", csrf=True)),
):
    before = store.get_admin_by_id(admin_user_id)
    if before is None:
        raise HTTPException(status_code=404, detail="Admin user not found")
    target_role = body.role or before["role"]
    if not admin_auth.can_manage_target_role(current["admin"]["role"], target_role):
        raise HTTPException(status_code=403, detail="Cannot assign that admin role")
    updates = body.model_dump(exclude_none=True)
    after = store.update_admin_user(admin_user_id, updates, actor_id=current["admin"]["id"])
    _audit(
        store=store,
        request=request,
        actor=current["admin"],
        action="admin_users.update",
        entity_type="admin_user",
        entity_id=admin_user_id,
        before=store.public_admin(before),
        after=after,
    )
    return after


@router.delete("/admin-users/{admin_user_id}")
def delete_admin_user(
    admin_user_id: str,
    request: Request,
    store: AdminStore = Depends(get_admin_store),
    current: dict[str, Any] = Depends(require_admin("admin_users:manage", csrf=True)),
):
    if admin_user_id == current["admin"]["id"]:
        raise HTTPException(status_code=400, detail="You cannot delete your own admin account")
    before = store.get_admin_by_id(admin_user_id)
    if before is None:
        raise HTTPException(status_code=404, detail="Admin user not found")
    if not admin_auth.can_manage_target_role(current["admin"]["role"], before["role"]):
        raise HTTPException(status_code=403, detail="Cannot delete that admin role")
    after = store.delete_admin_user(admin_user_id, actor_id=current["admin"]["id"])
    _audit(
        store=store,
        request=request,
        actor=current["admin"],
        action="admin_users.delete",
        entity_type="admin_user",
        entity_id=admin_user_id,
        before=store.public_admin(before),
        after=after,
    )
    return after


@router.get("/config")
def get_config(
    store: AdminStore = Depends(get_admin_store),
    current: dict[str, Any] = Depends(require_admin("config:view")),
):
    return {"config": store.get_runtime_config()}


@router.patch("/config")
def patch_config(
    body: RuntimeConfigPatch,
    request: Request,
    store: AdminStore = Depends(get_admin_store),
    current: dict[str, Any] = Depends(require_admin("config:manage", csrf=True)),
):
    before = store.get_runtime_config()
    after = store.set_runtime_config(body.values, actor_id=current["admin"]["id"])
    _audit(
        store=store,
        request=request,
        actor=current["admin"],
        action="config.update",
        entity_type="runtime_config",
        entity_id="global",
        before=before,
        after=after,
    )
    return {"config": after}


@router.get("/connectors")
def get_connectors(current: dict[str, Any] = Depends(require_admin("config:view"))):
    return {"connectors": connector_catalog_summary(limit=100)}


@router.patch("/connectors")
def patch_connectors(
    body: RuntimeConfigPatch,
    request: Request,
    store: AdminStore = Depends(get_admin_store),
    current: dict[str, Any] = Depends(require_admin("config:manage", csrf=True)),
):
    before = store.get_runtime_config().get("connectors", {})
    after = store.set_runtime_config({"connectors": body.values}, actor_id=current["admin"]["id"])
    _audit(
        store=store,
        request=request,
        actor=current["admin"],
        action="connectors.update",
        entity_type="runtime_config",
        entity_id="connectors",
        before=before,
        after=after.get("connectors", {}),
    )
    return {"config": after.get("connectors", {})}


@router.get("/sources")
def get_sources(current: dict[str, Any] = Depends(require_admin("config:view"))):
    return {"sources": load_source_catalog()}


@router.patch("/sources")
def patch_sources(
    body: RuntimeConfigPatch,
    request: Request,
    store: AdminStore = Depends(get_admin_store),
    current: dict[str, Any] = Depends(require_admin("config:manage", csrf=True)),
):
    before = store.get_runtime_config().get("sources", {})
    after = store.set_runtime_config({"sources": body.values}, actor_id=current["admin"]["id"])
    _audit(
        store=store,
        request=request,
        actor=current["admin"],
        action="sources.update",
        entity_type="runtime_config",
        entity_id="sources",
        before=before,
        after=after.get("sources", {}),
    )
    return {"config": after.get("sources", {})}


@router.get("/prompts/runtime")
def runtime_prompts(current: dict[str, Any] = Depends(require_admin("config:view"))):
    prompt_dir = Path(__file__).parent.parent / "core" / "prompts"
    files = [
        {"name": path.name, "size": path.stat().st_size, "updated_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()}
        for path in sorted(prompt_dir.glob("*.md"))
    ]
    return {"metadata": prompt_metadata(), "versions": prompt_versions(), "files": files}


@router.get("/operations/health")
def operations_health(current: dict[str, Any] = Depends(require_admin("operations:view"))):
    return {
        "storage": velocity_store.storage_healthcheck(),
        "app_env": os.getenv("APP_ENV", "development"),
        "remote_test_runner_enabled": os.getenv("ENABLE_REMOTE_TEST_RUNNER") == "true",
        "prompt_metadata": prompt_metadata(),
    }


@router.post("/operations/run-tests")
async def operations_run_tests(
    body: TestRunRequest,
    current: dict[str, Any] = Depends(require_admin("operations:run", csrf=True)),
):
    from api.diagnostics import TestRunRequest as DiagnosticsTestRunRequest
    from api.diagnostics import run_tests

    return await run_tests(DiagnosticsTestRunRequest(suite=body.suite))


@router.get("/{entity_type}")
def list_managed_entities(
    entity_type: str,
    search: str = "",
    status: str = "",
    page: int = 1,
    page_size: int = 25,
    include_deleted: bool = False,
    store: AdminStore = Depends(get_admin_store),
    current: dict[str, Any] = Depends(require_admin("content:view")),
):
    _validate_entity_type_or_404(entity_type)
    return store.list_managed_entities(
        entity_type,
        search=search,
        status=status,
        page=page,
        page_size=page_size,
        include_deleted=include_deleted,
    )


@router.post("/{entity_type}")
def create_managed_entity(
    entity_type: str,
    body: ManagedEntityWrite,
    request: Request,
    store: AdminStore = Depends(get_admin_store),
    current: dict[str, Any] = Depends(require_admin("content:manage", csrf=True)),
):
    _validate_entity_type_or_404(entity_type)
    _require_entity_manage_permission(entity_type, current["admin"]["role"])
    created = store.create_managed_entity(
        entity_type=entity_type,
        slug=body.slug,
        title=body.title,
        status=body.status,
        payload=body.payload,
        actor_id=current["admin"]["id"],
    )
    _audit(
        store=store,
        request=request,
        actor=current["admin"],
        action=f"{entity_type}.create",
        entity_type=entity_type,
        entity_id=created["id"],
        before=None,
        after=created,
    )
    return created


@router.get("/{entity_type}/{entity_id}")
def get_managed_entity(
    entity_type: str,
    entity_id: str,
    store: AdminStore = Depends(get_admin_store),
    current: dict[str, Any] = Depends(require_admin("content:view")),
):
    _validate_entity_type_or_404(entity_type)
    row = store.get_managed_entity(entity_type, entity_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Managed entity not found")
    return row


@router.patch("/{entity_type}/{entity_id}")
def update_managed_entity(
    entity_type: str,
    entity_id: str,
    body: ManagedEntityPatch,
    request: Request,
    store: AdminStore = Depends(get_admin_store),
    current: dict[str, Any] = Depends(require_admin("content:manage", csrf=True)),
):
    _validate_entity_type_or_404(entity_type)
    _require_entity_manage_permission(entity_type, current["admin"]["role"])
    before = store.get_managed_entity(entity_type, entity_id)
    if before is None:
        raise HTTPException(status_code=404, detail="Managed entity not found")
    after = store.update_managed_entity(
        entity_type,
        entity_id,
        body.model_dump(exclude_none=True),
        actor_id=current["admin"]["id"],
    )
    _audit(
        store=store,
        request=request,
        actor=current["admin"],
        action=f"{entity_type}.update",
        entity_type=entity_type,
        entity_id=entity_id,
        before=before,
        after=after,
    )
    return after


@router.delete("/{entity_type}/{entity_id}")
def delete_managed_entity(
    entity_type: str,
    entity_id: str,
    request: Request,
    store: AdminStore = Depends(get_admin_store),
    current: dict[str, Any] = Depends(require_admin("content:manage", csrf=True)),
):
    _validate_entity_type_or_404(entity_type)
    _require_entity_manage_permission(entity_type, current["admin"]["role"])
    before = store.get_managed_entity(entity_type, entity_id)
    if before is None:
        raise HTTPException(status_code=404, detail="Managed entity not found")
    after = store.delete_managed_entity(entity_type, entity_id, actor_id=current["admin"]["id"])
    _audit(
        store=store,
        request=request,
        actor=current["admin"],
        action=f"{entity_type}.delete",
        entity_type=entity_type,
        entity_id=entity_id,
        before=before,
        after=after,
    )
    return after


def _validate_entity_type_or_404(entity_type: str) -> None:
    if entity_type not in MANAGED_ENTITY_TYPES:
        raise HTTPException(status_code=404, detail="Unknown admin entity route")


def _require_entity_manage_permission(entity_type: str, role: str) -> None:
    if entity_type == "pricing-plans" and not admin_auth.role_has_permission(role, "pricing:manage"):
        raise HTTPException(status_code=403, detail="Pricing management requires Admin or Super Admin")


def _list_user_summaries(search: str = "") -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        backend = getattr(velocity_store, "_BACKEND", "local")
        if backend == "postgresql" and getattr(velocity_store, "_DB_STORAGE", None) is not None:
            from storage.db import UserContext

            db_storage = getattr(velocity_store, "_DB_STORAGE")
            with db_storage._session() as session:
                contexts = [row.context for row in session.scalars(__import__("sqlalchemy").select(UserContext)).all()]
        else:
            storage_path = Path(velocity_store.storage_path())
            contexts = []
            for path in sorted(storage_path.glob("user_*.json")):
                try:
                    import json

                    contexts.append(json.loads(path.read_text(encoding="utf-8")))
                except (OSError, ValueError):
                    continue
        for context in contexts:
            if not isinstance(context, dict):
                continue
            rows.append(_context_summary(context))
    except Exception:
        rows = []
    needle = search.strip().lower()
    if needle:
        rows = [
            row
            for row in rows
            if needle in row["user_id"].lower()
            or any(needle in str(domain).lower() for domain in row.get("domains", []))
        ]
    rows.sort(key=lambda row: row.get("updated_at") or "", reverse=True)
    return rows


def _context_summary(context: dict[str, Any]) -> dict[str, Any]:
    history = context.get("recent_context", []) if isinstance(context.get("recent_context"), list) else []
    return {
        "user_id": str(context.get("user_id", "")),
        "domains": context.get("domains", [])[:5] if isinstance(context.get("domains"), list) else [],
        "enhancement_count": int(context.get("enhancement_count", 0) or 0),
        "recent_context_count": len(history),
        "total_tokens_used": int(context.get("total_tokens_used", 0) or 0),
        "total_tokens_saved": int(context.get("total_tokens_saved", 0) or 0),
        "created_at": context.get("created_at", ""),
        "updated_at": context.get("updated_at", ""),
        "last_summary": history[0].get("summary", "") if history and isinstance(history[0], dict) else "",
    }


def _context_audit_slice(context: dict[str, Any]) -> dict[str, Any]:
    return {
        "user_id": context.get("user_id"),
        "enhancement_count": context.get("enhancement_count", 0),
        "preferences": context.get("preferences", {}),
        "personalization_notes": context.get("personalization_notes", ""),
        "updated_at": context.get("updated_at", ""),
    }


def _count_uploads() -> int:
    base = (Path(__file__).parent.parent / "storage" / "uploads").resolve()
    if not base.exists():
        return 0
    return sum(1 for _ in base.glob("*/*/metadata.json"))


def _count_evaluations() -> int:
    try:
        storage_path = Path(velocity_store.storage_path())
    except Exception:
        return 0
    total = 0
    for path in storage_path.glob("evals_*.json"):
        try:
            import json

            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                total += len(payload)
        except (OSError, ValueError):
            continue
    return total


def _paginate(rows: list[dict[str, Any]], *, page: int, page_size: int) -> dict[str, Any]:
    clean_page = max(1, int(page or 1))
    clean_page_size = min(100, max(1, int(page_size or 25)))
    start = (clean_page - 1) * clean_page_size
    return {
        "items": rows[start : start + clean_page_size],
        "total": len(rows),
        "page": clean_page,
        "page_size": clean_page_size,
    }
