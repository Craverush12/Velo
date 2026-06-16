from __future__ import annotations

import copy
import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_POST_STATUSES = {"draft", "ready", "rejected", "published_external"}
_RUN_STATUSES = {"running", "completed", "failed", "skipped"}
_OUTBOUND_JOB_STATUSES = {"queued", "running", "completed", "failed", "skipped"}


class BlogStore:
    def __init__(self, *, state_path: Path | None = None):
        self._lock = threading.RLock()
        self.state_path = state_path or (Path(__file__).parent / "blog" / "blog_state.json").resolve()

    @classmethod
    def local(cls, root: Path) -> "BlogStore":
        return cls(state_path=(root / "blog_state.json").resolve())

    def create_run(self, *, trigger: str, queries: list[str]) -> dict[str, Any]:
        now = _now_iso()
        row = {
            "id": _new_id(),
            "trigger": str(trigger or "manual"),
            "queries": [str(query) for query in queries],
            "status": "running",
            "stats": {},
            "error": "",
            "started_at": now,
            "finished_at": None,
            "created_at": now,
            "updated_at": now,
        }
        state = self._read_state()
        state["runs"].append(row)
        self._write_state(state)
        return copy.deepcopy(row)

    def finish_run(
        self,
        run_id: str,
        *,
        status: str,
        stats: dict[str, Any] | None = None,
        error: str = "",
    ) -> dict[str, Any]:
        clean_status = _validate_status(status, _RUN_STATUSES, "run status")
        state = self._read_state()
        for row in state["runs"]:
            if row["id"] == run_id:
                row["status"] = clean_status
                row["stats"] = copy.deepcopy(stats or {})
                row["error"] = str(error or "")
                row["finished_at"] = _now_iso()
                row["updated_at"] = _now_iso()
                self._write_state(state)
                return copy.deepcopy(row)
        raise KeyError("blog run not found")

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        for row in self._read_state()["runs"]:
            if row["id"] == run_id:
                return copy.deepcopy(row)
        return None

    def list_runs(self, *, page: int = 1, page_size: int = 25) -> dict[str, Any]:
        rows = self._read_state()["runs"]
        rows.sort(key=lambda row: row.get("created_at", ""), reverse=True)
        return _paginate(rows, page=page, page_size=page_size)

    def create_post(self, values: dict[str, Any], *, run_id: str = "") -> dict[str, Any]:
        now = _now_iso()
        row = _normalize_post(values)
        row.update(
            {
                "id": _new_id(),
                "run_id": run_id,
                "created_at": now,
                "updated_at": now,
            }
        )
        state = self._read_state()
        if any(post["slug"] == row["slug"] for post in state["posts"]):
            raise ValueError("blog post slug already exists")
        state["posts"].append(row)
        self._write_state(state)
        return copy.deepcopy(row)

    def list_posts(
        self,
        *,
        status: str = "",
        search: str = "",
        page: int = 1,
        page_size: int = 25,
    ) -> dict[str, Any]:
        rows = self._read_state()["posts"]
        clean_status = status.strip()
        needle = search.strip().lower()
        filtered = []
        for row in rows:
            if clean_status and row.get("status") != clean_status:
                continue
            if needle and needle not in row.get("title", "").lower() and needle not in row.get("slug", "").lower():
                continue
            filtered.append(copy.deepcopy(row))
        filtered.sort(key=lambda row: row.get("updated_at", ""), reverse=True)
        return _paginate(filtered, page=page, page_size=page_size)

    def get_post(self, post_id: str) -> dict[str, Any] | None:
        for row in self._read_state()["posts"]:
            if row["id"] == post_id:
                return copy.deepcopy(row)
        return None

    def update_post(self, post_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        allowed = {
            "slug",
            "title",
            "excerpt",
            "meta_title",
            "meta_description",
            "keywords",
            "content_markdown",
            "content_html",
            "faq",
            "sources",
            "status",
            "quality_score",
            "validation_errors",
            "rejection_reason",
            "model",
            "outbound_publications",
            "seo_score",
            "geo_score",
            "eeat_score",
            "schema_jsonld",
            "seo_audit",
        }
        clean = {key: copy.deepcopy(value) for key, value in updates.items() if key in allowed}
        if "status" in clean:
            clean["status"] = _validate_status(clean["status"], _POST_STATUSES, "post status")
        if "slug" in clean:
            clean["slug"] = _clean_slug(clean["slug"])
        clean["updated_at"] = _now_iso()
        state = self._read_state()
        for row in state["posts"]:
            if row["id"] == post_id:
                next_slug = clean.get("slug", row["slug"])
                if next_slug != row["slug"] and any(post["slug"] == next_slug for post in state["posts"]):
                    raise ValueError("blog post slug already exists")
                row.update(clean)
                self._write_state(state)
                return copy.deepcopy(row)
        raise KeyError("blog post not found")

    def approve_post(self, post_id: str) -> dict[str, Any]:
        return self.update_post(post_id, {"status": "ready", "rejection_reason": ""})

    def reject_post(self, post_id: str, *, reason: str = "") -> dict[str, Any]:
        return self.update_post(post_id, {"status": "rejected", "rejection_reason": str(reason or "")})

    def slug_exists(self, slug: str) -> bool:
        clean = _clean_slug(slug)
        return any(row["slug"] == clean for row in self._read_state()["posts"])

    def existing_slugs(self) -> set[str]:
        return {row["slug"] for row in self._read_state()["posts"]}

    def export_posts(self, *, status: str = "ready") -> dict[str, Any]:
        posts = self.list_posts(status=status, page_size=10000)["items"]
        return {
            "exported_at": _now_iso(),
            "status": status,
            "posts": posts,
        }

    def create_outbound_job(
        self,
        *,
        post_id: str,
        platform: str,
        method: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self.get_post(post_id) is None:
            raise KeyError("blog post not found")
        now = _now_iso()
        row = {
            "id": _new_id(),
            "post_id": str(post_id),
            "platform": _clean_platform(platform),
            "method": str(method or "browser"),
            "status": "queued",
            "payload": copy.deepcopy(payload or {}),
            "result": {},
            "error": "",
            "attempts": 0,
            "created_at": now,
            "updated_at": now,
            "started_at": None,
            "finished_at": None,
        }
        state = self._read_state()
        state["outbound_jobs"].append(row)
        self._write_state(state)
        return copy.deepcopy(row)

    def list_outbound_jobs(
        self,
        *,
        status: str = "",
        platform: str = "",
        method: str = "",
        page: int = 1,
        page_size: int = 25,
    ) -> dict[str, Any]:
        clean_status = status.strip()
        clean_platform = platform.strip().lower()
        clean_method = method.strip()
        rows = []
        for row in self._read_state()["outbound_jobs"]:
            if clean_status and row.get("status") != clean_status:
                continue
            if clean_platform and row.get("platform") != clean_platform:
                continue
            if clean_method and row.get("method") != clean_method:
                continue
            rows.append(copy.deepcopy(row))
        rows.sort(key=lambda row: row.get("updated_at", ""), reverse=True)
        return _paginate(rows, page=page, page_size=page_size)

    def get_outbound_job(self, job_id: str) -> dict[str, Any] | None:
        for row in self._read_state()["outbound_jobs"]:
            if row["id"] == job_id:
                return copy.deepcopy(row)
        return None

    def has_active_outbound_job(self, *, post_id: str, platform: str, method: str = "browser") -> bool:
        clean_platform = _clean_platform(platform)
        for row in self._read_state()["outbound_jobs"]:
            if row.get("post_id") != post_id:
                continue
            if row.get("platform") != clean_platform or row.get("method") != method:
                continue
            if row.get("status") in {"queued", "running", "completed"}:
                return True
        return False

    def claim_next_outbound_job(self, *, platforms: list[str] | None = None, method: str = "browser") -> dict[str, Any] | None:
        allowed_platforms = {_clean_platform(platform) for platform in platforms or []}
        state = self._read_state()
        queued = [
            row
            for row in state["outbound_jobs"]
            if row.get("status") == "queued"
            and row.get("method") == method
            and (not allowed_platforms or row.get("platform") in allowed_platforms)
        ]
        queued.sort(key=lambda row: row.get("created_at", ""))
        if not queued:
            return None
        row = queued[0]
        row["status"] = "running"
        row["attempts"] = int(row.get("attempts") or 0) + 1
        row["started_at"] = row.get("started_at") or _now_iso()
        row["updated_at"] = _now_iso()
        self._write_state(state)
        return copy.deepcopy(row)

    def finish_outbound_job(
        self,
        job_id: str,
        *,
        status: str,
        result: dict[str, Any] | None = None,
        error: str = "",
    ) -> dict[str, Any]:
        clean_status = _validate_status(status, _OUTBOUND_JOB_STATUSES, "outbound job status")
        state = self._read_state()
        for row in state["outbound_jobs"]:
            if row["id"] == job_id:
                row["status"] = clean_status
                row["result"] = copy.deepcopy(result or {})
                row["error"] = str(error or "")
                row["finished_at"] = _now_iso()
                row["updated_at"] = _now_iso()
                self._write_state(state)
                return copy.deepcopy(row)
        raise KeyError("outbound job not found")

    def _read_state(self) -> dict[str, Any]:
        with self._lock:
            if not self.state_path.exists():
                return _empty_state()
            with open(self.state_path, encoding="utf-8") as handle:
                payload = json.load(handle)
            state = _empty_state()
            for key in state:
                if isinstance(payload.get(key), list):
                    state[key] = payload[key]
            return state

    def _write_state(self, state: dict[str, Any]) -> None:
        with self._lock:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.state_path.with_suffix(".json.tmp")
            with open(tmp, "w", encoding="utf-8") as handle:
                json.dump(state, handle, indent=2)
                handle.write("\n")
            os.replace(tmp, self.state_path)


_DEFAULT_STORE: BlogStore | None = None


def get_default_blog_store() -> BlogStore:
    global _DEFAULT_STORE
    if _DEFAULT_STORE is not None:
        return _DEFAULT_STORE
    root = Path(os.getenv("BLOG_STORAGE_PATH", "storage/blog"))
    if not root.is_absolute():
        root = Path(__file__).parent.parent / root
    _DEFAULT_STORE = BlogStore.local(root.resolve())
    return _DEFAULT_STORE


def _normalize_post(values: dict[str, Any]) -> dict[str, Any]:
    now = _now_iso()
    return {
        "slug": _clean_slug(values.get("slug") or values.get("title") or "blog-post"),
        "title": _clean_text(values.get("title"), "title", 255),
        "status": _validate_status(values.get("status", "draft"), _POST_STATUSES, "post status"),
        "excerpt": str(values.get("excerpt") or "")[:500],
        "meta_title": str(values.get("meta_title") or "")[:90],
        "meta_description": str(values.get("meta_description") or "")[:220],
        "keywords": _clean_list(values.get("keywords")),
        "content_markdown": str(values.get("content_markdown") or ""),
        "content_html": str(values.get("content_html") or ""),
        "faq": _clean_list(values.get("faq")),
        "sources": _clean_list(values.get("sources")),
        "quality_score": int(values.get("quality_score") or 0),
        "validation_errors": _clean_list(values.get("validation_errors")),
        "rejection_reason": str(values.get("rejection_reason") or ""),
        "model": str(values.get("model") or ""),
        "outbound_publications": _clean_list(values.get("outbound_publications")),
        "seo_score": int(values.get("seo_score") or 0),
        "geo_score": int(values.get("geo_score") or 0),
        "eeat_score": int(values.get("eeat_score") or 0),
        "schema_jsonld": copy.deepcopy(values.get("schema_jsonld") if isinstance(values.get("schema_jsonld"), dict) else {}),
        "seo_audit": copy.deepcopy(values.get("seo_audit") if isinstance(values.get("seo_audit"), dict) else {}),
        "published_at": values.get("published_at"),
        "source_checked_at": values.get("source_checked_at") or now,
    }


def _empty_state() -> dict[str, Any]:
    return {"posts": [], "runs": [], "outbound_jobs": []}


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


def _new_id() -> str:
    return str(uuid.uuid4())


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_slug(value: Any) -> str:
    clean = str(value or "").strip().lower()
    out = []
    previous_dash = False
    for char in clean:
        if char.isalnum():
            out.append(char)
            previous_dash = False
        elif not previous_dash:
            out.append("-")
            previous_dash = True
    slug = "".join(out).strip("-")
    return (slug or "blog-post")[:160].strip("-") or "blog-post"


def _clean_platform(value: Any) -> str:
    clean = str(value or "").strip().lower()
    out = []
    for char in clean:
        if char.isalnum():
            out.append(char)
        elif char in {"-", "_"}:
            out.append("-")
    return ("".join(out).strip("-") or "unknown")[:64]


def _clean_text(value: Any, field: str, max_length: int) -> str:
    clean = str(value or "").strip()
    if not clean:
        raise ValueError(f"{field} is required")
    return clean[:max_length]


def _clean_list(value: Any) -> list[Any]:
    if not isinstance(value, list):
        return []
    return copy.deepcopy(value)


def _validate_status(value: Any, allowed: set[str], label: str) -> str:
    clean = str(value or "").strip()
    if clean not in allowed:
        raise ValueError(f"unsupported {label}")
    return clean
