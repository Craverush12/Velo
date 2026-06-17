from __future__ import annotations

import copy
import difflib
import hashlib
import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_DEFAULT_LIMIT = 1000
_LOCK = threading.Lock()
_DEFAULT_STORE: PromptTraceStore | None = None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def text_hash(value: str) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def text_preview(value: str, limit: int = 500) -> str:
    clean = str(value or "")
    return clean if len(clean) <= limit else clean[:limit] + "...[truncated]"


def unified_diff(before: str, after: str, before_label: str = "before", after_label: str = "after") -> str:
    return "\n".join(
        difflib.unified_diff(
            str(before or "").splitlines(),
            str(after or "").splitlines(),
            fromfile=before_label,
            tofile=after_label,
            lineterm="",
        )
    )


class PromptTraceStore:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "prompt_traces.jsonl"

    @classmethod
    def local(cls, root: Path) -> "PromptTraceStore":
        return cls(root)

    def record(self, trace: dict[str, Any]) -> dict[str, Any]:
        row = self._normalize_trace(trace)
        with _LOCK:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
                f.write("\n")
        return copy.deepcopy(row)

    def list_traces(
        self,
        *,
        flow: str = "",
        status: str = "",
        user_id: str = "",
        prompt_mode: str = "",
        search: str = "",
        page: int = 1,
        page_size: int = 25,
        include_payload: bool = False,
    ) -> dict[str, Any]:
        rows = self._read_all()
        rows = self._filter(
            rows,
            flow=flow,
            status=status,
            user_id=user_id,
            prompt_mode=prompt_mode,
            search=search,
        )
        rows.sort(key=lambda row: row.get("created_at", ""), reverse=True)
        total = len(rows)
        clean_page = max(1, int(page or 1))
        clean_page_size = min(100, max(1, int(page_size or 25)))
        start = (clean_page - 1) * clean_page_size
        items = rows[start : start + clean_page_size]
        if not include_payload:
            items = [self._summary(row) for row in items]
        return {
            "items": items,
            "total": total,
            "page": clean_page,
            "page_size": clean_page_size,
            "pages": max(1, -(-total // clean_page_size)) if total else 0,
        }

    def get(self, trace_id: str) -> dict[str, Any] | None:
        clean = str(trace_id or "").strip()
        if not clean:
            return None
        for row in reversed(self._read_all()):
            if row.get("trace_id") == clean:
                return copy.deepcopy(row)
        return None

    def diff(self, trace_id: str) -> dict[str, Any] | None:
        row = self.get(trace_id)
        if row is None:
            return None
        before_after = row.get("before_after") or {}
        before = str(before_after.get("before") or "")
        after = str(before_after.get("after") or "")
        return {
            "trace_id": row["trace_id"],
            "before": before,
            "after": after,
            "unified_diff": unified_diff(before, after),
            "similarity": _similarity(before, after),
        }

    def metrics(self, *, days: int | None = None) -> dict[str, Any]:
        rows = self._read_all()
        if days is not None:
            cutoff = datetime.now(timezone.utc).timestamp() - (max(1, days) * 86400)
            rows = [row for row in rows if _timestamp(row.get("created_at")) >= cutoff]
        totals = {
            "traces": len(rows),
            "completed": sum(1 for row in rows if row.get("status") == "completed"),
            "failed": sum(1 for row in rows if row.get("status") == "failed"),
            "tokens": sum(_int_at(row, "usage", "total_tokens") for row in rows),
        }
        quality_scores = [
            _float_at(row, "output", "quality_score")
            for row in rows
            if _float_at(row, "output", "quality_score") is not None
        ]
        latencies = [
            _float_at(row, "timings", "total_ms")
            for row in rows
            if _float_at(row, "timings", "total_ms") is not None
        ]
        return {
            "generated_at": utc_now(),
            "totals": totals,
            "quality": {
                "average_score": round(sum(quality_scores) / len(quality_scores), 4) if quality_scores else 0.0,
                "samples": len(quality_scores),
            },
            "latency": {
                "average_ms": round(sum(latencies) / len(latencies), 2) if latencies else 0.0,
                "samples": len(latencies),
            },
            "by_flow": _group_counts(rows, "flow"),
            "by_status": _group_counts(rows, "status"),
            "by_prompt_mode": _group_counts(rows, "prompt_mode"),
            "by_model": _group_counts(rows, "model"),
        }

    def _read_all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        with self.path.open(encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict):
                    rows.append(value)
        if len(rows) > _DEFAULT_LIMIT:
            rows = rows[-_DEFAULT_LIMIT:]
        return rows

    def _filter(self, rows: list[dict[str, Any]], **filters: str) -> list[dict[str, Any]]:
        result = rows
        for key in ("flow", "status", "user_id", "prompt_mode"):
            value = str(filters.get(key) or "").strip()
            if value:
                result = [row for row in result if str(row.get(key) or "") == value]
        search = str(filters.get("search") or "").strip().lower()
        if search:
            result = [
                row
                for row in result
                if search in json.dumps(self._summary(row), ensure_ascii=False).lower()
                or search in json.dumps(row.get("input") or {}, ensure_ascii=False).lower()
                or search in json.dumps(row.get("output") or {}, ensure_ascii=False).lower()
            ]
        return result

    def _normalize_trace(self, trace: dict[str, Any]) -> dict[str, Any]:
        now = utc_now()
        row = copy.deepcopy(trace)
        row.setdefault("trace_id", str(uuid.uuid4()))
        row.setdefault("created_at", now)
        row.setdefault("updated_at", now)
        row.setdefault("status", "completed")
        row.setdefault("flow", "unknown")
        row.setdefault("user_id", "anonymous")
        row.setdefault("prompt_mode", "")
        row.setdefault("target_ai", None)
        row.setdefault("model", "")
        row.setdefault("prompt_version", "")
        row.setdefault("prompt_files", [])
        row.setdefault("input", {})
        row.setdefault("messages", {})
        row.setdefault("output", {})
        row.setdefault("usage", {})
        row.setdefault("timings", {})
        row.setdefault("validation", {})
        row.setdefault("before_after", {})
        before_after = row["before_after"]
        before = str(before_after.get("before") or "")
        after = str(before_after.get("after") or "")
        before_after.setdefault("changed", before.strip() != after.strip())
        before_after.setdefault("similarity", _similarity(before, after))
        before_after.setdefault("before_hash", text_hash(before))
        before_after.setdefault("after_hash", text_hash(after))
        return row

    def _summary(self, row: dict[str, Any]) -> dict[str, Any]:
        output = row.get("output") or {}
        input_payload = row.get("input") or {}
        before_after = row.get("before_after") or {}
        return {
            "trace_id": row.get("trace_id", ""),
            "created_at": row.get("created_at", ""),
            "flow": row.get("flow", ""),
            "status": row.get("status", ""),
            "user_id": row.get("user_id", ""),
            "session_id": row.get("session_id", ""),
            "prompt_mode": row.get("prompt_mode", ""),
            "target_ai": row.get("target_ai"),
            "model": row.get("model", ""),
            "prompt_version": row.get("prompt_version", ""),
            "prompt_files": row.get("prompt_files", []),
            "raw_prompt_preview": text_preview(str(input_payload.get("redacted_prompt") or input_payload.get("raw_prompt") or ""), 220),
            "output_preview": text_preview(str(output.get("final_text") or ""), 220),
            "quality_score": output.get("quality_score"),
            "tokens": _int_at(row, "usage", "total_tokens"),
            "latency_ms": _float_at(row, "timings", "total_ms"),
            "changed": before_after.get("changed", False),
            "similarity": before_after.get("similarity", 0.0),
        }


def get_default_store() -> PromptTraceStore:
    global _DEFAULT_STORE
    env_path = os.getenv("PROMPT_TRACE_STORAGE_PATH", "").strip()
    root = Path(env_path) if env_path else Path(__file__).parent / "traces"
    if not root.is_absolute():
        root = Path(__file__).parent.parent / root
    resolved = root.resolve()
    if _DEFAULT_STORE is None or _DEFAULT_STORE.root != resolved:
        _DEFAULT_STORE = PromptTraceStore.local(resolved)
    return _DEFAULT_STORE


def _group_counts(rows: list[dict[str, Any]], field: str) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = {}
    for row in rows:
        key = str(row.get(field) or "unknown")
        counts.setdefault(key, {"count": 0, "tokens": 0})
        counts[key]["count"] += 1
        counts[key]["tokens"] += _int_at(row, "usage", "total_tokens")
    return counts


def _int_at(row: dict[str, Any], parent: str, key: str) -> int:
    try:
        return int((row.get(parent) or {}).get(key) or 0)
    except (TypeError, ValueError):
        return 0


def _float_at(row: dict[str, Any], parent: str, key: str) -> float | None:
    try:
        value = (row.get(parent) or {}).get(key)
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _similarity(before: str, after: str) -> float:
    if not before and not after:
        return 1.0
    return round(difflib.SequenceMatcher(None, before, after).ratio(), 4)


def _timestamp(value: Any) -> float:
    if not value:
        return 0.0
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    except ValueError:
        return 0.0
