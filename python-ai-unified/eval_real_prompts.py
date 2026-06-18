#!/usr/bin/env python3
# eval_real_prompts.py
# Evaluates real user prompts by comparing old enhanced output vs new enhance API output.
# Time: O(n) per prompt, O(n) total

import argparse
import csv
import os
import re
import sys
import warnings
from datetime import datetime

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    print("ERROR: psycopg (v3) is required. Install with: pip install 'psycopg[binary]'", file=sys.stderr)
    sys.exit(1)

try:
    import httpx
except ImportError:
    print("ERROR: httpx is required. Install with: pip install httpx", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

QUERY = """
SELECT
  up.user_id,
  up.conversation_id,
  up.user_prompt AS raw_prompt,
  ep.enhanced_prompt,
  ep.feedback,
  ep.domain,
  ep.mode,
  ep.created_at
FROM user_prompts up
JOIN save_enhance_prompt ep ON ep.prompt_id = up.prompt_id
WHERE LENGTH(up.user_prompt) BETWEEN 80 AND 3000
  AND ep.enhanced_prompt IS NOT NULL
  AND LENGTH(ep.enhanced_prompt) > 100
ORDER BY ep.created_at DESC
LIMIT %s;
"""

# ---------------------------------------------------------------------------
# Metric helpers
# ---------------------------------------------------------------------------

CONSTRAINT_WORDS = ["must", "no ", "only", "exactly", "never", "require", "constraint"]
PLACEHOLDER_PATTERN = re.compile(r'\[[A-Z_]{3,}\]')


def expansion_ratio(enhanced: str, raw: str) -> float:
    raw_len = len(raw)
    if raw_len == 0:
        return 0.0
    return len(enhanced) / raw_len


def constraint_count(text: str) -> int:
    text_lower = text.lower()
    return sum(text_lower.count(w) for w in CONSTRAINT_WORDS)


def placeholder_count(text: str) -> int:
    return len(PLACEHOLDER_PATTERN.findall(text))


# ---------------------------------------------------------------------------
# API call
# ---------------------------------------------------------------------------

def call_enhance_api(api_url: str, raw_prompt: str, user_id: str, timeout: int = 30) -> str | None:
    """Call the ThinkVelocity enhance API and return the new enhanced prompt string, or None on failure."""
    payload = {
        "prompt": raw_prompt,
        "user_id": str(user_id),
    }
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(api_url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        # Try common response key patterns
        for key in ("enhanced_prompt", "enhanced", "result", "output", "data"):
            if key in data:
                val = data[key]
                if isinstance(val, str) and val.strip():
                    return val
                if isinstance(val, dict):
                    for sub_key in ("enhanced_prompt", "enhanced", "result", "output"):
                        if sub_key in val and isinstance(val[sub_key], str):
                            return val[sub_key]
        str_fields = {k: v for k, v in data.items() if isinstance(v, str) and len(v) > 50}
        if len(str_fields) == 1:
            return list(str_fields.values())[0]
        warnings.warn(f"Unexpected API response shape. Keys: {list(data.keys())}")
        return None
    except httpx.ConnectError as e:
        warnings.warn(f"API connection error: {e}")
        return None
    except httpx.TimeoutException:
        warnings.warn(f"API request timed out after {timeout}s")
        return None
    except httpx.HTTPStatusError as e:
        warnings.warn(f"API HTTP error {e.response.status_code}: {e}")
        return None
    except Exception as e:
        warnings.warn(f"API call failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Console summary
# ---------------------------------------------------------------------------

def print_summary(results: list[dict]) -> None:
    if not results:
        print("No results to summarise.")
        return

    n = len(results)

    def avg(field: str) -> float:
        vals = [r[field] for r in results if r[field] is not None]
        return sum(vals) / len(vals) if vals else 0.0

    def compare(new_field: str, old_field: str) -> tuple[int, int, int]:
        better = worse = same = 0
        for r in results:
            nv = r.get(new_field)
            ov = r.get(old_field)
            if nv is None or ov is None:
                continue
            if nv > ov:
                better += 1
            elif nv < ov:
                worse += 1
            else:
                same += 1
        return better, worse, same

    print("\n" + "=" * 60)
    print(f"EVAL SUMMARY  ({n} rows processed)")
    print("=" * 60)

    print(f"\n{'Metric':<30} {'Old':>10} {'New':>10}")
    print("-" * 52)
    print(f"{'Avg expansion ratio':<30} {avg('expansion_ratio_old'):>10.2f} {avg('expansion_ratio_new'):>10.2f}")
    print(f"{'Avg constraint count':<30} {avg('constraint_count_old'):>10.2f} {avg('constraint_count_new'):>10.2f}")
    print(f"{'Avg placeholder count':<30} {avg('placeholder_count_old'):>10.2f} {avg('placeholder_count_new'):>10.2f}")

    print(f"\n{'Metric':<30} {'Better':>8} {'Worse':>8} {'Same':>8}")
    print("-" * 56)
    for label, new_f, old_f in [
        ("Expansion ratio", "expansion_ratio_new", "expansion_ratio_old"),
        ("Constraint count", "constraint_count_new", "constraint_count_old"),
        ("Placeholder count", "placeholder_count_new", "placeholder_count_old"),
    ]:
        b, w, s = compare(new_f, old_f)
        print(f"  {label:<28} {b:>8} {w:>8} {s:>8}")

    # Negative feedback rows
    neg_rows = [r for r in results if str(r.get("feedback", "")).strip().lower() in ("thumbs_down", "down", "-1", "negative", "bad", "0", "false")]
    if neg_rows:
        print(f"\n{'=' * 60}")
        print(f"  NEGATIVE FEEDBACK ROWS ({len(neg_rows)}):")
        print(f"{'=' * 60}")
        for r in neg_rows:
            print(
                f"  conversation_id={r['conversation_id']} | domain={r.get('domain','?')} | mode={r.get('mode','?')}"
                f" | raw_len={r['raw_length']} | exp_old={r['expansion_ratio_old']:.2f} exp_new={r['expansion_ratio_new']:.2f}"
                f" | created_at={r.get('created_at','?')}"
            )
    else:
        print("\n  No negative-feedback rows found in this sample.")

    print("=" * 60 + "\n")


# ---------------------------------------------------------------------------
# CSV output
# ---------------------------------------------------------------------------

CSV_FIELDS = [
    "user_id",
    "conversation_id",
    "raw_length",
    "old_enhanced_length",
    "new_enhanced_length",
    "expansion_ratio_old",
    "expansion_ratio_new",
    "constraint_count_old",
    "constraint_count_new",
    "placeholder_count_old",
    "placeholder_count_new",
    "feedback",
    "domain",
    "mode",
    "created_at",
]


def write_csv(results: list[dict], output_path: str) -> None:
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)
    print(f"CSV written to: {output_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate ThinkVelocity enhance quality against real production prompts."
    )
    parser.add_argument(
        "--pg-dsn",
        default=None,
        help="PostgreSQL DSN (e.g. postgresql://user:pass@host:5432/db). "
             "Defaults to PG_CONNECTION env var.",
    )
    parser.add_argument(
        "--api-url",
        default="http://localhost:8005/ai/enhance/chat",
        help="ThinkVelocity enhance API endpoint.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Number of rows to fetch from the database (default: 50).",
    )
    parser.add_argument(
        "--output",
        default="eval_results.csv",
        help="Output CSV file path (default: eval_results.csv).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Resolve DSN
    dsn = args.pg_dsn or os.environ.get("PG_CONNECTION") or os.environ.get("DATABASE_URL")
    if not dsn:
        print(
            "ERROR: No database DSN provided. Use --pg-dsn or set PG_CONNECTION env var.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Strip SQLAlchemy driver prefix if present (e.g. postgresql+psycopg://...)
    clean_dsn = dsn.replace("postgresql+psycopg://", "postgresql://", 1)

    # Connect to DB
    try:
        conn = psycopg.connect(clean_dsn, row_factory=dict_row)
    except psycopg.OperationalError as e:
        print(f"ERROR: Could not connect to database: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Database connection failed: {e}", file=sys.stderr)
        sys.exit(1)

    # Fetch rows
    try:
        with conn.cursor() as cur:
            cur.execute(QUERY, (args.limit,))
            rows = cur.fetchall()
    except psycopg.Error as e:
        print(f"ERROR: Query failed: {e}", file=sys.stderr)
        conn.close()
        sys.exit(1)
    finally:
        conn.close()

    if not rows:
        print("WARNING: Query returned 0 rows. Nothing to evaluate.")
        sys.exit(0)

    print(f"Fetched {len(rows)} rows from DB. Calling enhance API for each...")

    results: list[dict] = []
    skipped = 0

    for i, row in enumerate(rows, start=1):
        raw_prompt: str = row["raw_prompt"] or ""
        old_enhanced: str = row["enhanced_prompt"] or ""
        user_id = row["user_id"]
        conversation_id = row["conversation_id"]

        print(f"  [{i}/{len(rows)}] conversation_id={conversation_id} raw_len={len(raw_prompt)}", end="", flush=True)

        new_enhanced = call_enhance_api(args.api_url, raw_prompt, user_id)

        if new_enhanced is None:
            print(" — SKIPPED (API failure)")
            skipped += 1
            continue

        print(f" → new_len={len(new_enhanced)}")

        result = {
            "user_id": str(user_id),
            "conversation_id": str(conversation_id),
            "raw_length": len(raw_prompt),
            "old_enhanced_length": len(old_enhanced),
            "new_enhanced_length": len(new_enhanced),
            "expansion_ratio_old": round(expansion_ratio(old_enhanced, raw_prompt), 4),
            "expansion_ratio_new": round(expansion_ratio(new_enhanced, raw_prompt), 4),
            "constraint_count_old": constraint_count(old_enhanced),
            "constraint_count_new": constraint_count(new_enhanced),
            "placeholder_count_old": placeholder_count(old_enhanced),
            "placeholder_count_new": placeholder_count(new_enhanced),
            "feedback": row.get("feedback"),
            "domain": row.get("domain"),
            "mode": row.get("mode"),
            "created_at": row.get("created_at"),
        }
        results.append(result)

    print(f"\nProcessed {len(results)} rows successfully. Skipped {skipped} due to API failures.")

    if not results:
        print("ERROR: All rows were skipped. No output produced.", file=sys.stderr)
        sys.exit(1)

    write_csv(results, args.output)
    print_summary(results)


if __name__ == "__main__":
    main()
