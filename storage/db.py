import copy
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, String, create_engine, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.types import JSON


class Base(DeclarativeBase):
    pass


class UserContext(Base):
    __tablename__ = "user_contexts"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    context: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_database_url(database_url: str) -> str:
    url = database_url.strip()
    if not url:
        raise ValueError("DATABASE_URL is required for PostgreSQL storage")
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url.removeprefix("postgres://")
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url.removeprefix("postgresql://")
    return url


class DatabaseStorage:
    def __init__(self, database_url: str):
        self.database_url = normalize_database_url(database_url)
        self.engine = create_engine(self.database_url, pool_pre_ping=True, future=True)
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False, future=True)
        self.initialize_schema()

    def initialize_schema(self) -> None:
        Base.metadata.create_all(self.engine)

    def healthcheck(self) -> dict:
        try:
            with self.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except Exception as exc:
            return {
                "ok": False,
                "backend": "postgresql",
                "database_url": self._safe_database_url(),
                "error": str(exc),
            }
        return {
            "ok": True,
            "backend": "postgresql",
            "database_url": self._safe_database_url(),
        }

    def get_user_context(self, user_id: str, default_context: dict) -> dict:
        with self._session() as session:
            row = session.get(UserContext, user_id)
            if row is None:
                context = copy.deepcopy(default_context)
                context["user_id"] = user_id
                now = datetime.now(timezone.utc).isoformat()
                context["created_at"] = now
                context["updated_at"] = now
                return context
            return copy.deepcopy(row.context)

    def save_user_context(self, user_id: str, context: dict) -> None:
        payload = copy.deepcopy(context)
        now = _now()
        created_at = _parse_timestamp(payload.get("created_at")) or now
        updated_at = _parse_timestamp(payload.get("updated_at")) or now

        with self._session() as session:
            row = session.get(UserContext, user_id)
            if row is None:
                session.add(
                    UserContext(
                        user_id=user_id,
                        context=payload,
                        created_at=created_at,
                        updated_at=updated_at,
                    )
                )
            else:
                row.context = payload
                row.updated_at = updated_at
            session.commit()

    def migrate_json_contexts(self, contexts: list[dict]) -> int:
        migrated = 0
        for context in contexts:
            user_id = context.get("user_id")
            if not isinstance(user_id, str) or not user_id:
                continue
            self.save_user_context(user_id, context)
            migrated += 1
        return migrated

    def close(self) -> None:
        self.engine.dispose()

    def _safe_database_url(self) -> str:
        if "@" not in self.database_url:
            return self.database_url
        scheme, rest = self.database_url.split("://", 1)
        _, host = rest.rsplit("@", 1)
        return f"{scheme}://***@{host}"

    def _session(self) -> Session:
        return self.SessionLocal()


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def load_all_json_contexts(storage_path) -> list[dict]:
    contexts: list[dict] = []
    for path in sorted(storage_path.glob("user_*.json")):
        import json

        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
        if isinstance(payload, dict):
            contexts.append(payload)
    return contexts
