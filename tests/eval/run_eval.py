"""ThinkVelocity eval runner.

Runs all golden cases against the live enhance pipeline and scores each with
the LLM judge. Exits 0 if mean >= 3.5 and pass rate >= 80%, else exits 1.

Usage:
    python tests/eval/run_eval.py                  # run all 25 cases
    python tests/eval/run_eval.py --ids G-001 G-007  # specific cases
    python tests/eval/run_eval.py --mode fast_build  # filter by mode
    python tests/eval/run_eval.py --no-judge         # skip LLM scoring, signal-check only

Environment:
    GROQ_API_KEY   required
    TV_BASE_URL    defaults to http://localhost:8000
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

HERE = Path(__file__).parent
GOLDEN_PATH = HERE / "golden.json"

TV_BASE_URL = os.getenv("TV_BASE_URL", "http://localhost:8000")
ENHANCE_URL = f"{TV_BASE_URL}/enhance"

PASS_MEAN_THRESHOLD = 3.5
PASS_RATE_THRESHOLD = 0.80


def _load_cases(ids: list[str] | None, mode: str | None) -> list[dict]:
    cases = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    if ids:
        cases = [c for c in cases if c["id"] in ids]
    if mode:
        cases = [c for c in cases if c.get("mode") == mode]
    return cases


async def _run_case(client: httpx.AsyncClient, case: dict) -> tuple[dict, str]:
    """Call the enhance endpoint and return (case, enhanced_prompt)."""
    payload = {
        "prompt": case["prompt"],
        "user_id": "eval_runner",
        "prompt_mode": case.get("mode", "normal"),
        "incognito": True,
    }
    t0 = time.perf_counter()
    resp = await client.post(ENHANCE_URL, json=payload, timeout=60.0)
    resp.raise_for_status()

    enhanced = ""
    for line in resp.text.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        raw = line[5:].strip()
        if not raw:
            continue
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "done":
            enhanced = event.get("result", {}).get("enhanced_prompt", "")
            break

    latency_ms = round((time.perf_counter() - t0) * 1000)
    return case, enhanced, latency_ms


def _signal_check(case: dict, enhanced: str) -> dict:
    ep = enhanced.lower()
    present = [s for s in case.get("must_contain", []) if s.lower() in ep]
    missing = [s for s in case.get("must_contain", []) if s.lower() not in ep]
    forbidden = [s for s in case.get("must_not_contain", []) if s.lower() in ep]
    length_ok = len(enhanced) >= case.get("min_length", 0)
    passed = not missing and not forbidden and length_ok
    return {
        "signals_present": present,
        "signals_missing": missing,
        "forbidden_present": forbidden,
        "length_ok": length_ok,
        "signal_pass": passed,
    }


def _print_row(case_id: str, mode: str, sub: str, score: float | None, passed: bool, notes: str, latency_ms: int):
    status = "✓ PASS" if passed else "✗ FAIL"
    score_str = f"{score:.2f}" if score is not None else "  n/a"
    print(f"  {status}  {case_id:<8}  {mode:<12}  {sub:<20}  score={score_str}  {latency_ms}ms  {notes}")


async def main():
    parser = argparse.ArgumentParser(description="ThinkVelocity eval runner")
    parser.add_argument("--ids", nargs="*", help="Run specific case IDs")
    parser.add_argument("--mode", help="Filter by mode (media, fast_build, research, normal)")
    parser.add_argument("--no-judge", action="store_true", help="Skip LLM judge scoring")
    args = parser.parse_args()

    cases = _load_cases(args.ids, args.mode)
    if not cases:
        print("No cases matched. Check --ids or --mode filter.")
        sys.exit(1)

    print(f"\nThinkVelocity Eval — {len(cases)} cases — {TV_BASE_URL}\n")
    print(f"  {'':6}  {'ID':<8}  {'mode':<12}  {'sub_type':<20}  {'score':>9}  {'latency':>8}  notes")
    print(f"  {'─'*80}")

    results = []
    judge_scores = []
    total_latency = 0

    async with httpx.AsyncClient() as client:
        for case in cases:
            try:
                case_data, enhanced, latency_ms = await _run_case(client, case)
            except Exception as e:
                print(f"  ✗ FAIL  {case['id']:<8}  {'':12}  {'':20}  score=  n/a  ERROR: {e}")
                results.append({"case_id": case["id"], "pass": False, "error": str(e)})
                continue

            total_latency += latency_ms
            sig = _signal_check(case, enhanced)
            sub = case.get("build_sub") or case.get("research_sub") or case.get("media_sub") or ""

            if args.no_judge:
                passed = sig["signal_pass"]
                notes = f"missing={sig['signals_missing']}" if sig["signals_missing"] else ""
                if sig["forbidden_present"]:
                    notes += f" forbidden={sig['forbidden_present']}"
                _print_row(case["id"], case.get("mode", ""), sub, None, passed, notes, latency_ms)
                results.append({"case_id": case["id"], "pass": passed, "signal_check": sig})
            else:
                try:
                    from tests.eval.judge import score_enhancement
                    judgment = await score_enhancement(case, enhanced)
                    mean = judgment.get("mean", 0.0)
                    passed = judgment.get("pass", False) and sig["signal_pass"]
                    notes = judgment.get("notes", "")[:60]
                    judge_scores.append(mean)
                    _print_row(case["id"], case.get("mode", ""), sub, mean, passed, notes, latency_ms)
                    results.append({**judgment, "signal_check": sig, "latency_ms": latency_ms})
                except Exception as e:
                    passed = sig["signal_pass"]
                    _print_row(case["id"], case.get("mode", ""), sub, None, passed, f"JUDGE_ERR: {e}", latency_ms)
                    results.append({"case_id": case["id"], "pass": passed, "signal_check": sig})

    print(f"\n  {'─'*80}")
    total = len(results)
    passed_count = sum(1 for r in results if r.get("pass"))
    pass_rate = passed_count / total if total else 0
    mean_score = sum(judge_scores) / len(judge_scores) if judge_scores else None
    avg_latency = total_latency // len(cases) if cases else 0

    print(f"\n  Results: {passed_count}/{total} passed ({pass_rate*100:.0f}%)")
    if mean_score is not None:
        print(f"  Mean judge score: {mean_score:.2f} (threshold: {PASS_MEAN_THRESHOLD})")
    print(f"  Avg latency: {avg_latency}ms\n")

    ok = pass_rate >= PASS_RATE_THRESHOLD
    if mean_score is not None:
        ok = ok and (mean_score >= PASS_MEAN_THRESHOLD)

    if ok:
        print("  ✓ EVAL PASSED\n")
        sys.exit(0)
    else:
        reasons = []
        if pass_rate < PASS_RATE_THRESHOLD:
            reasons.append(f"pass rate {pass_rate*100:.0f}% < {PASS_RATE_THRESHOLD*100:.0f}%")
        if mean_score is not None and mean_score < PASS_MEAN_THRESHOLD:
            reasons.append(f"mean score {mean_score:.2f} < {PASS_MEAN_THRESHOLD}")
        print(f"  ✗ EVAL FAILED — {'; '.join(reasons)}\n")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
