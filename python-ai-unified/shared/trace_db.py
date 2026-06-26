from __future__ import annotations

import logging
import uuid
from typing import Any


logger = logging.getLogger(__name__)

_pool: Any | None = None


async def init_trace_pool(dsn: str) -> None:
    global _pool
    clean_dsn = str(dsn or "").strip()
    if not clean_dsn:
        return
    import asyncpg

    _pool = await asyncpg.create_pool(dsn=clean_dsn, min_size=2, max_size=5)


def is_trace_pool_initialized() -> bool:
    return _pool is not None


async def write_trace(trace: dict[str, Any]) -> None:
    if _pool is None:
        return
    try:
        row = _to_trace_row(trace)
        await _pool.execute(
            """
            INSERT INTO prompt_traces (
                trace_id, user_id, session_id, platform, domain, intent,
                raw_prompt, enhanced_prompt, context_hint, persona_hint,
                suggested_ai, model, tokens_in, tokens_out, latency_ms,
                quality_score
            )
            VALUES (
                COALESCE($1::uuid, gen_random_uuid()), $2, $3, $4, $5, $6,
                $7, $8, $9, $10, $11, $12, $13, $14, $15, $16
            )
            """,
            row["trace_id"],
            row["user_id"],
            row["session_id"],
            row["platform"],
            row["domain"],
            row["intent"],
            row["raw_prompt"],
            row["enhanced_prompt"],
            row["context_hint"],
            row["persona_hint"],
            row["suggested_ai"],
            row["model"],
            row["tokens_in"],
            row["tokens_out"],
            row["latency_ms"],
            row["quality_score"],
        )
    except Exception as exc:  # noqa: BLE001 - traces must never block enhance
        logger.warning("prompt trace DB write failed: %s", exc)


# Outcomes where the user took a meaningful action with the enhanced prompt.
# These count toward outcome_rate (the engagement signal).
_SIGNAL_OUTCOMES = {"copied", "reenhanced", "thumbs_up", "thumbs_down"}

# Outcomes that are valid to record but indicate no active engagement.
# Stored for visibility in by_outcome but excluded from outcome_rate.
_NEUTRAL_OUTCOMES = {"ignored"}

_VALID_OUTCOMES = _SIGNAL_OUTCOMES | _NEUTRAL_OUTCOMES


async def record_outcome(trace_id: str, outcome: str) -> bool:
    """Attach a downstream outcome to an existing trace. Degrades open.

    Returns True only when exactly one row was updated. Never raises.
    """
    if _pool is None:
        return False
    clean = (outcome or "").strip().lower()
    if clean not in _VALID_OUTCOMES:
        return False
    tid = _valid_uuid_or_none(trace_id)
    if tid is None:
        return False
    try:
        status = await _pool.execute(
            "UPDATE prompt_traces SET outcome = $2, outcome_at = NOW() "
            "WHERE trace_id = $1::uuid",
            tid,
            clean,
        )
        return str(status).strip() == "UPDATE 1"
    except Exception as exc:  # noqa: BLE001 - outcome write must never raise
        logger.warning("record_outcome failed for trace %s: %s", trace_id, exc)
        return False


async def query_traces(
    user_id: str | None = None,
    domain: str | None = None,
    intent: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    if _pool is None:
        return []

    clauses: list[str] = []
    params: list[Any] = []
    if user_id:
        params.append(user_id)
        clauses.append(f"user_id = ${len(params)}")
    if domain:
        params.append(domain)
        clauses.append(f"domain = ${len(params)}")
    if intent:
        params.append(intent)
        clauses.append(f"intent = ${len(params)}")

    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    clean_limit = min(200, max(1, int(limit or 50)))
    clean_offset = max(0, int(offset or 0))
    params.extend([clean_limit, clean_offset])
    limit_ref = f"${len(params) - 1}"
    offset_ref = f"${len(params)}"

    rows = await _pool.fetch(
        f"""
        SELECT trace_id, user_id, session_id, platform, domain, intent,
               raw_prompt, enhanced_prompt, context_hint, persona_hint,
               suggested_ai, model, tokens_in, tokens_out, latency_ms,
               quality_score, created_at
        FROM prompt_traces
        {where}
        ORDER BY created_at DESC
        LIMIT {limit_ref} OFFSET {offset_ref}
        """,
        *params,
    )
    return [_row_to_dict(row) for row in rows]


async def query_metrics() -> dict[str, Any]:
    if _pool is None:
        return {
            "total": 0,
            "avg_latency_ms": 0.0,
            "by_domain": {},
            "by_intent": {},
            "by_suggested_ai": {},
            "by_outcome": {},
            "outcome_rate": 0.0,
        }

    totals = await _pool.fetchrow(
        "SELECT COUNT(*) AS total, COALESCE(AVG(latency_ms), 0) AS avg_latency_ms FROM prompt_traces"
    )
    by_domain, by_intent, by_suggested_ai = await _metric_groups()
    by_outcome = _count_map(await _pool.fetch(
        "SELECT COALESCE(NULLIF(outcome, ''), 'none') AS key, COUNT(*) AS count "
        "FROM prompt_traces GROUP BY COALESCE(NULLIF(outcome, ''), 'none')"
    ))
    total = int((totals or {}).get("total") or 0)
    answered = sum(v for k, v in by_outcome.items() if k in _SIGNAL_OUTCOMES)
    return {
        "total": total,
        "avg_latency_ms": float((totals or {}).get("avg_latency_ms") or 0.0),
        "by_domain": by_domain,
        "by_intent": by_intent,
        "by_suggested_ai": by_suggested_ai,
        "by_outcome": by_outcome,
        "outcome_rate": round(answered / total, 3) if total else 0.0,
    }


async def _metric_groups() -> tuple[dict[str, int], dict[str, int], dict[str, int]]:
    assert _pool is not None
    domain_rows = await _pool.fetch(
        """
        SELECT COALESCE(NULLIF(domain, ''), 'unknown') AS key, COUNT(*) AS count
        FROM prompt_traces
        GROUP BY COALESCE(NULLIF(domain, ''), 'unknown')
        """
    )
    intent_rows = await _pool.fetch(
        """
        SELECT COALESCE(NULLIF(intent, ''), 'unknown') AS key, COUNT(*) AS count
        FROM prompt_traces
        GROUP BY COALESCE(NULLIF(intent, ''), 'unknown')
        """
    )
    ai_rows = await _pool.fetch(
        """
        SELECT COALESCE(NULLIF(suggested_ai, ''), 'unknown') AS key, COUNT(*) AS count
        FROM prompt_traces
        GROUP BY COALESCE(NULLIF(suggested_ai, ''), 'unknown')
        """
    )
    return _count_map(domain_rows), _count_map(intent_rows), _count_map(ai_rows)


def _to_trace_row(trace: dict[str, Any]) -> dict[str, Any]:
    trace = trace or {}
    input_payload = trace.get("input") or {}
    output_payload = trace.get("output") or {}
    before_after = trace.get("before_after") or {}
    usage = trace.get("usage") or trace.get("tokens") or {}
    timings = trace.get("timings") or {}
    metadata = trace.get("metadata") or {}
    metrics = trace.get("metrics") or {}

    trace_id = _valid_uuid_or_none(trace.get("trace_id"))
    return {
        "trace_id": trace_id,
        "user_id": str(trace.get("user_id") or "anonymous"),
        "session_id": trace.get("session_id"),
        "platform": trace.get("platform") or trace.get("prompt_mode") or trace.get("target_ai"),
        "domain": trace.get("domain") or metadata.get("domain"),
        "intent": trace.get("intent") or metadata.get("intent"),
        "raw_prompt": trace.get("raw_prompt")
        or input_payload.get("raw_prompt")
        or input_payload.get("redacted_prompt")
        or before_after.get("before"),
        "enhanced_prompt": trace.get("enhanced_prompt")
        or output_payload.get("final_text")
        or before_after.get("after"),
        "context_hint": trace.get("context_hint"),
        "persona_hint": trace.get("persona_hint"),
        "suggested_ai": trace.get("suggested_ai"),
        "model": trace.get("model"),
        "tokens_in": _int_or_none(
            trace.get("tokens_in")
            or usage.get("input_tokens")
            or usage.get("prompt_tokens")
        ),
        "tokens_out": _int_or_none(
            trace.get("tokens_out")
            or usage.get("output_tokens")
            or usage.get("completion_tokens")
        ),
        "latency_ms": _int_or_none(
            trace.get("latency_ms")
            or timings.get("total_ms")
            or metrics.get("latency_ms")
        ),
        "quality_score": _float_or_none(
            trace.get("quality_score") or output_payload.get("quality_score")
        ),
    }


def _row_to_dict(row: Any) -> dict[str, Any]:
    data = dict(row)
    if data.get("trace_id") is not None:
        data["trace_id"] = str(data["trace_id"])
    if data.get("created_at") is not None:
        data["created_at"] = data["created_at"].isoformat()
    return data


def _count_map(rows: list[Any]) -> dict[str, int]:
    return {str(row["key"]): int(row["count"] or 0) for row in rows}


def _valid_uuid_or_none(value: Any) -> str | None:
    if not value:
        return None
    try:
        return str(uuid.UUID(str(value)))
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
