from __future__ import annotations

import copy
import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import DateTime, String, Text, create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.types import JSON

from core import admin_auth
from storage.db import normalize_database_url


class AdminBase(DeclarativeBase):
    pass


JsonColumn = JSON().with_variant(JSONB, "postgresql")


class AdminUser(AdminBase):
    __tablename__ = "admin_users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AdminSession(AdminBase):
    __tablename__ = "admin_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    admin_user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    session_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    csrf_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ip_address: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    user_agent: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AdminAuditLog(AdminBase):
    __tablename__ = "admin_audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    actor_admin_user_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    actor_email: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    action: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    before: Mapped[dict[str, Any] | None] = mapped_column(JsonColumn)
    after: Mapped[dict[str, Any] | None] = mapped_column(JsonColumn)
    ip_address: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    user_agent: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AdminManagedEntity(AdminBase):
    __tablename__ = "admin_managed_entities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JsonColumn, nullable=False)
    created_by: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    updated_by: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AdminRuntimeConfig(AdminBase):
    __tablename__ = "admin_runtime_config"

    key: Mapped[str] = mapped_column(String(160), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JsonColumn, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_by: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,158}[a-z0-9]$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_MANAGED_ENTITY_TYPES = {
    "announcements",
    "faqs",
    "feature-flags",
    "pricing-plans",
    "usage-limits",
    "prompt-templates",
}
_STATUSES = {"draft", "published", "hidden", "active", "inactive", "archived"}


class AdminStore:
    def __init__(
        self,
        *,
        state_path: Path | None = None,
        database_url: str | None = None,
        engine=None,
    ):
        self._lock = threading.RLock()
        self.state_path = state_path
        self.engine = engine
        self.SessionLocal = None
        if database_url:
            self.engine = create_engine(normalize_database_url(database_url), pool_pre_ping=True, future=True)
        if self.engine is not None:
            AdminBase.metadata.create_all(self.engine)
            self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False, future=True)
        elif self.state_path is None:
            self.state_path = (Path(__file__).parent / "admin" / "admin_state.json").resolve()

    @classmethod
    def local(cls, root: Path) -> "AdminStore":
        return cls(state_path=(root / "admin_state.json").resolve())

    @classmethod
    def from_database_url(cls, database_url: str) -> "AdminStore":
        return cls(database_url=database_url)

    @classmethod
    def from_engine(cls, engine) -> "AdminStore":
        return cls(engine=engine)

    def ensure_bootstrap_admin(self, email: str | None, password: str | None) -> bool:
        if self.count_active_admin_users() > 0:
            return False
        clean_email = _validate_email(email or "")
        clean_password = str(password or "")
        admin = {
            "id": _new_id(),
            "email": clean_email,
            "display_name": clean_email.split("@", 1)[0],
            "password_hash": admin_auth.hash_password(clean_password),
            "role": "super_admin",
            "status": "active",
            "last_login_at": None,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "deleted_at": None,
        }
        if self.SessionLocal:
            with self._session() as session:
                session.add(_admin_user_from_dict(admin))
                session.commit()
        else:
            state = self._read_state()
            state["admin_users"].append(admin)
            self._write_state(state)
        return True

    def count_active_admin_users(self) -> int:
        if self.SessionLocal:
            with self._session() as session:
                rows = session.scalars(select(AdminUser)).all()
                return sum(1 for row in rows if row.deleted_at is None and row.status == "active")
        state = self._read_state()
        return sum(1 for row in state["admin_users"] if not row.get("deleted_at") and row.get("status") == "active")

    def get_admin_by_email(self, email: str, *, include_deleted: bool = False) -> dict[str, Any] | None:
        clean = _validate_email(email)
        if self.SessionLocal:
            with self._session() as session:
                row = session.scalar(select(AdminUser).where(AdminUser.email == clean))
                if row is None or (row.deleted_at and not include_deleted):
                    return None
                return _admin_user_to_dict(row)
        state = self._read_state()
        for row in state["admin_users"]:
            if row["email"] == clean and (include_deleted or not row.get("deleted_at")):
                return copy.deepcopy(row)
        return None

    def get_admin_by_id(self, admin_user_id: str, *, include_deleted: bool = False) -> dict[str, Any] | None:
        if self.SessionLocal:
            with self._session() as session:
                row = session.get(AdminUser, admin_user_id)
                if row is None or (row.deleted_at and not include_deleted):
                    return None
                return _admin_user_to_dict(row)
        state = self._read_state()
        for row in state["admin_users"]:
            if row["id"] == admin_user_id and (include_deleted or not row.get("deleted_at")):
                return copy.deepcopy(row)
        return None

    def list_admin_users(self, *, include_deleted: bool = False) -> dict[str, Any]:
        if self.SessionLocal:
            with self._session() as session:
                rows = [_admin_user_to_dict(row) for row in session.scalars(select(AdminUser)).all()]
        else:
            rows = self._read_state()["admin_users"]
        items = [self.public_admin(row) for row in rows if include_deleted or not row.get("deleted_at")]
        items.sort(key=lambda row: row["created_at"], reverse=True)
        return {"items": items, "total": len(items)}

    def create_admin_user(
        self,
        *,
        email: str,
        display_name: str,
        password: str,
        role: str,
        actor_id: str,
    ) -> dict[str, Any]:
        clean_email = _validate_email(email)
        if self.get_admin_by_email(clean_email, include_deleted=True):
            raise ValueError("admin email already exists")
        now = _now_iso()
        row = {
            "id": _new_id(),
            "email": clean_email,
            "display_name": _clean_required(display_name, "display_name", 255),
            "password_hash": admin_auth.hash_password(password),
            "role": admin_auth.normalize_role(role),
            "status": "active",
            "last_login_at": None,
            "created_at": now,
            "updated_at": now,
            "deleted_at": None,
        }
        if self.SessionLocal:
            with self._session() as session:
                session.add(_admin_user_from_dict(row))
                session.commit()
        else:
            state = self._read_state()
            state["admin_users"].append(row)
            self._write_state(state)
        return self.public_admin(row)

    def update_admin_user(self, admin_user_id: str, updates: dict[str, Any], *, actor_id: str) -> dict[str, Any]:
        allowed = {"display_name", "role", "status", "password"}
        clean = {key: value for key, value in updates.items() if key in allowed}
        if "role" in clean:
            clean["role"] = admin_auth.normalize_role(clean["role"])
        if "status" in clean and clean["status"] not in {"active", "disabled"}:
            raise ValueError("admin status must be active or disabled")
        if "display_name" in clean:
            clean["display_name"] = _clean_required(clean["display_name"], "display_name", 255)
        if "password" in clean:
            clean["password_hash"] = admin_auth.hash_password(str(clean.pop("password") or ""))
        clean["updated_at"] = _now_iso()
        row = self._update_admin_row(admin_user_id, clean)
        return self.public_admin(row)

    def delete_admin_user(self, admin_user_id: str, *, actor_id: str) -> dict[str, Any]:
        row = self._update_admin_row(
            admin_user_id,
            {"deleted_at": _now_iso(), "status": "disabled", "updated_at": _now_iso()},
            include_deleted=False,
        )
        return self.public_admin(row)

    def mark_login(self, admin_user_id: str) -> None:
        self._update_admin_row(admin_user_id, {"last_login_at": _now_iso(), "updated_at": _now_iso()})

    def public_admin(self, admin: dict[str, Any]) -> dict[str, Any]:
        public = copy.deepcopy(admin)
        public.pop("password_hash", None)
        return public

    def create_session(
        self,
        *,
        admin_user_id: str,
        session_hash: str,
        csrf_hash: str,
        expires_at: datetime,
        ip_address: str,
        user_agent: str,
    ) -> dict[str, Any]:
        row = {
            "id": _new_id(),
            "admin_user_id": admin_user_id,
            "session_hash": session_hash,
            "csrf_hash": csrf_hash,
            "expires_at": _dt_iso(expires_at),
            "revoked_at": None,
            "ip_address": ip_address[:64],
            "user_agent": user_agent[:1000],
            "created_at": _now_iso(),
        }
        if self.SessionLocal:
            with self._session() as session:
                session.add(_admin_session_from_dict(row))
                session.commit()
        else:
            state = self._read_state()
            state["admin_sessions"].append(row)
            self._write_state(state)
        self.mark_login(admin_user_id)
        return copy.deepcopy(row)

    def get_session_by_hash(self, session_hash: str) -> dict[str, Any] | None:
        if self.SessionLocal:
            with self._session() as session:
                row = session.scalar(select(AdminSession).where(AdminSession.session_hash == session_hash))
                return _admin_session_to_dict(row) if row else None
        state = self._read_state()
        for row in state["admin_sessions"]:
            if row["session_hash"] == session_hash:
                return copy.deepcopy(row)
        return None

    def revoke_session(self, session_hash: str) -> None:
        if self.SessionLocal:
            with self._session() as session:
                row = session.scalar(select(AdminSession).where(AdminSession.session_hash == session_hash))
                if row:
                    row.revoked_at = _now_dt()
                    session.commit()
            return
        state = self._read_state()
        for row in state["admin_sessions"]:
            if row["session_hash"] == session_hash:
                row["revoked_at"] = _now_iso()
        self._write_state(state)

    def list_managed_entities(
        self,
        entity_type: str,
        *,
        search: str = "",
        status: str = "",
        page: int = 1,
        page_size: int = 25,
        include_deleted: bool = False,
    ) -> dict[str, Any]:
        entity_type = _validate_entity_type(entity_type)
        if self.SessionLocal:
            with self._session() as session:
                rows = [
                    _managed_entity_to_dict(row)
                    for row in session.scalars(
                        select(AdminManagedEntity).where(AdminManagedEntity.entity_type == entity_type)
                    ).all()
                ]
        else:
            rows = [row for row in self._read_state()["managed_entities"] if row["entity_type"] == entity_type]
        rows = _filter_rows(rows, search=search, status=status, include_deleted=include_deleted)
        rows.sort(key=lambda row: row["updated_at"], reverse=True)
        return _paginate(rows, page=page, page_size=page_size)

    def get_managed_entity(self, entity_type: str, entity_id: str, *, include_deleted: bool = False) -> dict[str, Any] | None:
        entity_type = _validate_entity_type(entity_type)
        rows = self.list_managed_entities(entity_type, include_deleted=True, page_size=10000)["items"]
        for row in rows:
            if row["id"] == entity_id and (include_deleted or not row.get("deleted_at")):
                return row
        return None

    def create_managed_entity(
        self,
        *,
        entity_type: str,
        slug: str,
        title: str,
        status: str,
        payload: dict[str, Any],
        actor_id: str,
    ) -> dict[str, Any]:
        entity_type = _validate_entity_type(entity_type)
        now = _now_iso()
        row = {
            "id": _new_id(),
            "entity_type": entity_type,
            "slug": _validate_slug(slug),
            "title": _clean_required(title, "title", 255),
            "status": _validate_status(status),
            "payload": _validate_payload(payload),
            "created_by": actor_id,
            "updated_by": actor_id,
            "created_at": now,
            "updated_at": now,
            "deleted_at": None,
        }
        if self.SessionLocal:
            with self._session() as session:
                session.add(_managed_entity_from_dict(row))
                session.commit()
        else:
            state = self._read_state()
            state["managed_entities"].append(row)
            self._write_state(state)
        return copy.deepcopy(row)

    def update_managed_entity(
        self,
        entity_type: str,
        entity_id: str,
        updates: dict[str, Any],
        *,
        actor_id: str,
    ) -> dict[str, Any]:
        _validate_entity_type(entity_type)
        allowed = {"slug", "title", "status", "payload"}
        clean = {key: value for key, value in updates.items() if key in allowed}
        if "slug" in clean:
            clean["slug"] = _validate_slug(clean["slug"])
        if "title" in clean:
            clean["title"] = _clean_required(clean["title"], "title", 255)
        if "status" in clean:
            clean["status"] = _validate_status(clean["status"])
        if "payload" in clean:
            clean["payload"] = _validate_payload(clean["payload"])
        clean["updated_by"] = actor_id
        clean["updated_at"] = _now_iso()
        return self._update_managed_row(entity_type, entity_id, clean)

    def delete_managed_entity(self, entity_type: str, entity_id: str, *, actor_id: str) -> dict[str, Any]:
        _validate_entity_type(entity_type)
        return self._update_managed_row(
            entity_type,
            entity_id,
            {"deleted_at": _now_iso(), "updated_by": actor_id, "updated_at": _now_iso()},
        )

    def get_runtime_config(self) -> dict[str, Any]:
        if self.SessionLocal:
            with self._session() as session:
                rows = session.scalars(select(AdminRuntimeConfig)).all()
                return {row.key: _runtime_config_to_dict(row) for row in rows}
        return copy.deepcopy(self._read_state()["runtime_config"])

    def set_runtime_config(self, values: dict[str, Any], *, actor_id: str) -> dict[str, Any]:
        if not isinstance(values, dict):
            raise ValueError("config values must be an object")
        now = _now_iso()
        if self.SessionLocal:
            with self._session() as session:
                for key, value in values.items():
                    row = session.get(AdminRuntimeConfig, _clean_key(key))
                    if row is None:
                        session.add(
                            AdminRuntimeConfig(
                                key=_clean_key(key),
                                value={"value": value},
                                description="",
                                updated_by=actor_id,
                                updated_at=_now_dt(),
                            )
                        )
                    else:
                        row.value = {"value": value}
                        row.updated_by = actor_id
                        row.updated_at = _now_dt()
                session.commit()
            return self.get_runtime_config()
        state = self._read_state()
        for key, value in values.items():
            state["runtime_config"][_clean_key(key)] = {
                "key": _clean_key(key),
                "value": value,
                "description": "",
                "updated_by": actor_id,
                "updated_at": now,
            }
        self._write_state(state)
        return copy.deepcopy(state["runtime_config"])

    def record_audit(
        self,
        *,
        actor: dict[str, Any],
        action: str,
        entity_type: str,
        entity_id: str,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
        ip_address: str,
        user_agent: str,
    ) -> dict[str, Any]:
        row = {
            "id": _new_id(),
            "actor_admin_user_id": actor.get("id", ""),
            "actor_email": actor.get("email", ""),
            "action": _clean_required(action, "action", 120),
            "entity_type": _clean_required(entity_type, "entity_type", 80),
            "entity_id": str(entity_id or "")[:120],
            "before": copy.deepcopy(before),
            "after": copy.deepcopy(after),
            "ip_address": ip_address[:64],
            "user_agent": user_agent[:1000],
            "created_at": _now_iso(),
        }
        if self.SessionLocal:
            with self._session() as session:
                session.add(_audit_from_dict(row))
                session.commit()
        else:
            state = self._read_state()
            state["audit_logs"].append(row)
            state["audit_logs"] = state["audit_logs"][-5000:]
            self._write_state(state)
        return copy.deepcopy(row)

    def list_audit_logs(self, *, search: str = "", page: int = 1, page_size: int = 50) -> dict[str, Any]:
        if self.SessionLocal:
            with self._session() as session:
                rows = [_audit_to_dict(row) for row in session.scalars(select(AdminAuditLog)).all()]
        else:
            rows = self._read_state()["audit_logs"]
        needle = search.strip().lower()
        if needle:
            rows = [
                row
                for row in rows
                if needle in row.get("action", "").lower()
                or needle in row.get("entity_type", "").lower()
                or needle in row.get("actor_email", "").lower()
            ]
        rows.sort(key=lambda row: row["created_at"], reverse=True)
        return _paginate(rows, page=page, page_size=page_size)

    def close(self) -> None:
        if self.engine is not None:
            self.engine.dispose()

    def _session(self) -> Session:
        return self.SessionLocal()

    def _read_state(self) -> dict[str, Any]:
        assert self.state_path is not None
        with self._lock:
            if not self.state_path.exists():
                return _empty_state()
            with open(self.state_path, encoding="utf-8") as handle:
                payload = json.load(handle)
            state = _empty_state()
            for key, value in payload.items():
                if key in state:
                    state[key] = value
            return state

    def _write_state(self, state: dict[str, Any]) -> None:
        assert self.state_path is not None
        with self._lock:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.state_path.with_suffix(".json.tmp")
            with open(tmp, "w", encoding="utf-8") as handle:
                json.dump(state, handle, indent=2)
                handle.write("\n")
            os.replace(tmp, self.state_path)

    def _update_admin_row(
        self,
        admin_user_id: str,
        updates: dict[str, Any],
        *,
        include_deleted: bool = True,
    ) -> dict[str, Any]:
        if self.SessionLocal:
            with self._session() as session:
                row = session.get(AdminUser, admin_user_id)
                if row is None or (row.deleted_at and not include_deleted):
                    raise KeyError("admin user not found")
                for key, value in updates.items():
                    setattr(row, key, _parse_dt(value) if key.endswith("_at") else value)
                session.commit()
                return _admin_user_to_dict(row)
        state = self._read_state()
        for row in state["admin_users"]:
            if row["id"] == admin_user_id and (include_deleted or not row.get("deleted_at")):
                row.update(copy.deepcopy(updates))
                self._write_state(state)
                return copy.deepcopy(row)
        raise KeyError("admin user not found")

    def _update_managed_row(self, entity_type: str, entity_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        if self.SessionLocal:
            with self._session() as session:
                row = session.get(AdminManagedEntity, entity_id)
                if row is None or row.entity_type != entity_type or row.deleted_at is not None:
                    raise KeyError("managed entity not found")
                for key, value in updates.items():
                    setattr(row, key, _parse_dt(value) if key.endswith("_at") else value)
                session.commit()
                return _managed_entity_to_dict(row)
        state = self._read_state()
        for row in state["managed_entities"]:
            if row["id"] == entity_id and row["entity_type"] == entity_type and not row.get("deleted_at"):
                row.update(copy.deepcopy(updates))
                self._write_state(state)
                return copy.deepcopy(row)
        raise KeyError("managed entity not found")


_DEFAULT_STORE: AdminStore | None = None


def get_default_store() -> AdminStore:
    global _DEFAULT_STORE
    if _DEFAULT_STORE is not None:
        return _DEFAULT_STORE
    admin_db_url = os.getenv("ADMIN_DATABASE_URL", "").strip()
    if admin_db_url:
        _DEFAULT_STORE = AdminStore.from_database_url(admin_db_url)
    else:
        backend = os.getenv("STORAGE_BACKEND", "").strip().lower()
        database_url = os.getenv("DATABASE_URL", "").strip()
        if backend in {"postgres", "postgresql", "db", "database"} and database_url:
            _DEFAULT_STORE = AdminStore.from_database_url(database_url)
        else:
            root = Path(os.getenv("ADMIN_STORAGE_PATH", "storage/admin"))
            if not root.is_absolute():
                root = Path(__file__).parent.parent / root
            _DEFAULT_STORE = AdminStore.local(root.resolve())
    return _DEFAULT_STORE


def _empty_state() -> dict[str, Any]:
    return {
        "admin_users": [],
        "admin_sessions": [],
        "audit_logs": [],
        "managed_entities": [],
        "runtime_config": {},
    }


def _now_dt() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _dt_iso(_now_dt())


def _dt_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _parse_dt(value: Any) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return None


def _new_id() -> str:
    return str(uuid.uuid4())


def _validate_email(value: str) -> str:
    clean = str(value or "").strip().lower()
    if not _EMAIL_RE.fullmatch(clean):
        raise ValueError("admin email must be a valid email address")
    return clean


def _clean_required(value: Any, field: str, max_length: int) -> str:
    clean = str(value or "").strip()
    if not clean:
        raise ValueError(f"{field} is required")
    return clean[:max_length]


def _clean_key(value: Any) -> str:
    clean = str(value or "").strip().lower()
    if not clean or len(clean) > 160:
        raise ValueError("config key is invalid")
    return clean


def _validate_slug(value: str) -> str:
    clean = str(value or "").strip().lower()
    if not _SLUG_RE.fullmatch(clean):
        raise ValueError("slug must be 3-160 lowercase letters, numbers, hyphens, or underscores")
    return clean


def _validate_entity_type(value: str) -> str:
    clean = str(value or "").strip()
    if clean not in _MANAGED_ENTITY_TYPES:
        raise ValueError("unsupported managed entity type")
    return clean


def _validate_status(value: str) -> str:
    clean = str(value or "").strip().lower()
    if clean not in _STATUSES:
        raise ValueError("unsupported status")
    return clean


def _validate_payload(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("payload must be an object")
    json.dumps(value)
    return copy.deepcopy(value)


def _filter_rows(
    rows: list[dict[str, Any]],
    *,
    search: str,
    status: str,
    include_deleted: bool,
) -> list[dict[str, Any]]:
    needle = search.strip().lower()
    clean_status = status.strip().lower()
    filtered: list[dict[str, Any]] = []
    for row in rows:
        if row.get("deleted_at") and not include_deleted:
            continue
        if clean_status and row.get("status") != clean_status:
            continue
        if needle and needle not in row.get("slug", "").lower() and needle not in row.get("title", "").lower():
            continue
        filtered.append(copy.deepcopy(row))
    return filtered


def _paginate(rows: list[dict[str, Any]], *, page: int, page_size: int) -> dict[str, Any]:
    clean_page = max(1, int(page or 1))
    clean_page_size = min(100, max(1, int(page_size or 25)))
    start = (clean_page - 1) * clean_page_size
    end = start + clean_page_size
    return {
        "items": copy.deepcopy(rows[start:end]),
        "total": len(rows),
        "page": clean_page,
        "page_size": clean_page_size,
    }


def _admin_user_from_dict(row: dict[str, Any]) -> AdminUser:
    return AdminUser(
        id=row["id"],
        email=row["email"],
        display_name=row["display_name"],
        password_hash=row["password_hash"],
        role=row["role"],
        status=row["status"],
        last_login_at=_parse_dt(row.get("last_login_at")),
        created_at=_parse_dt(row["created_at"]),
        updated_at=_parse_dt(row["updated_at"]),
        deleted_at=_parse_dt(row.get("deleted_at")),
    )


def _admin_user_to_dict(row: AdminUser) -> dict[str, Any]:
    return {
        "id": row.id,
        "email": row.email,
        "display_name": row.display_name,
        "password_hash": row.password_hash,
        "role": row.role,
        "status": row.status,
        "last_login_at": _dt_iso(row.last_login_at) if row.last_login_at else None,
        "created_at": _dt_iso(row.created_at),
        "updated_at": _dt_iso(row.updated_at),
        "deleted_at": _dt_iso(row.deleted_at) if row.deleted_at else None,
    }


def _admin_session_from_dict(row: dict[str, Any]) -> AdminSession:
    return AdminSession(
        id=row["id"],
        admin_user_id=row["admin_user_id"],
        session_hash=row["session_hash"],
        csrf_hash=row["csrf_hash"],
        expires_at=_parse_dt(row["expires_at"]),
        revoked_at=_parse_dt(row.get("revoked_at")),
        ip_address=row.get("ip_address", ""),
        user_agent=row.get("user_agent", ""),
        created_at=_parse_dt(row["created_at"]),
    )


def _admin_session_to_dict(row: AdminSession) -> dict[str, Any]:
    return {
        "id": row.id,
        "admin_user_id": row.admin_user_id,
        "session_hash": row.session_hash,
        "csrf_hash": row.csrf_hash,
        "expires_at": _dt_iso(row.expires_at),
        "revoked_at": _dt_iso(row.revoked_at) if row.revoked_at else None,
        "ip_address": row.ip_address,
        "user_agent": row.user_agent,
        "created_at": _dt_iso(row.created_at),
    }


def _managed_entity_from_dict(row: dict[str, Any]) -> AdminManagedEntity:
    return AdminManagedEntity(
        id=row["id"],
        entity_type=row["entity_type"],
        slug=row["slug"],
        title=row["title"],
        status=row["status"],
        payload=row["payload"],
        created_by=row.get("created_by", ""),
        updated_by=row.get("updated_by", ""),
        created_at=_parse_dt(row["created_at"]),
        updated_at=_parse_dt(row["updated_at"]),
        deleted_at=_parse_dt(row.get("deleted_at")),
    )


def _managed_entity_to_dict(row: AdminManagedEntity) -> dict[str, Any]:
    return {
        "id": row.id,
        "entity_type": row.entity_type,
        "slug": row.slug,
        "title": row.title,
        "status": row.status,
        "payload": copy.deepcopy(row.payload),
        "created_by": row.created_by,
        "updated_by": row.updated_by,
        "created_at": _dt_iso(row.created_at),
        "updated_at": _dt_iso(row.updated_at),
        "deleted_at": _dt_iso(row.deleted_at) if row.deleted_at else None,
    }


def _audit_from_dict(row: dict[str, Any]) -> AdminAuditLog:
    return AdminAuditLog(
        id=row["id"],
        actor_admin_user_id=row.get("actor_admin_user_id", ""),
        actor_email=row.get("actor_email", ""),
        action=row["action"],
        entity_type=row["entity_type"],
        entity_id=row.get("entity_id", ""),
        before=row.get("before"),
        after=row.get("after"),
        ip_address=row.get("ip_address", ""),
        user_agent=row.get("user_agent", ""),
        created_at=_parse_dt(row["created_at"]),
    )


def _audit_to_dict(row: AdminAuditLog) -> dict[str, Any]:
    return {
        "id": row.id,
        "actor_admin_user_id": row.actor_admin_user_id,
        "actor_email": row.actor_email,
        "action": row.action,
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
        "before": copy.deepcopy(row.before),
        "after": copy.deepcopy(row.after),
        "ip_address": row.ip_address,
        "user_agent": row.user_agent,
        "created_at": _dt_iso(row.created_at),
    }


def _runtime_config_to_dict(row: AdminRuntimeConfig) -> dict[str, Any]:
    value = row.value.get("value") if isinstance(row.value, dict) and "value" in row.value else row.value
    return {
        "key": row.key,
        "value": copy.deepcopy(value),
        "description": row.description,
        "updated_by": row.updated_by,
        "updated_at": _dt_iso(row.updated_at),
    }
