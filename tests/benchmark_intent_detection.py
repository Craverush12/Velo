"""
Benchmark intent detection and domain classification against the ideal test cases.

Usage (from python-ai-unified/):
    python -m pytest ../tests/benchmark_intent_detection.py -v --tb=short

Or run standalone:
    cd python-ai-unified && python ../tests/benchmark_intent_detection.py
"""

import asyncio
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Make python-ai-unified importable
_SERVICE_DIR = Path(__file__).parent.parent / "python-ai-unified"
if str(_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICE_DIR))

_TEST_FILE = Path(__file__).parent / "ideal_cases" / "ideal_test_cases.json"
_SCORES_DIR = Path(__file__).parent / "benchmarks"
_SCORES_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# Load test cases
# ---------------------------------------------------------------------------

def load_test_cases() -> List[Dict[str, Any]]:
    with open(_TEST_FILE, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Adapter: call _extract_context from context.py
# ---------------------------------------------------------------------------

async def run_extraction(case: Dict[str, Any]) -> Dict[str, Any]:
    """Call the real _extract_context() with this test case's conversation."""
    from routers.context import _extract_context, ChatMessage

    messages = [
        ChatMessage(role=m["role"], content=m["content"], timestamp="0")
        for m in case["conversation"]
    ]
    previous_essence = case.get("existing_essence")

    result = await _extract_context(messages, previous_essence=previous_essence)
    return result


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

def score_intent(result: Dict, case: Dict) -> Tuple[bool, str]:
    got = result.get("intent", "")
    expected = case.get("expected_intent", "")
    return got == expected, f"got={got!r} expected={expected!r}"


def score_domain(result: Dict, case: Dict) -> Tuple[bool, str]:
    got = result.get("primary_domain", result.get("domains", [""])[0])
    expected = case.get("expected_domain", "")
    return got == expected, f"got={got!r} expected={expected!r}"


def score_secondary_intent_specificity(result: Dict, case: Dict) -> Tuple[bool, str]:
    si = result.get("secondary_intent") or ""
    if not si:
        return False, "secondary_intent is empty"
    words = [w for w in si.split("_") if w]
    specific = len(words) >= 2
    return specific, f"secondary_intent={si!r} (words={len(words)})"


def check_suggested_ai(case: Dict) -> Optional[Tuple[bool, str]]:
    """Test _resolve_suggested_ai if the case has expected_suggested_ai."""
    expected = case.get("expected_suggested_ai")
    if not expected:
        return None

    try:
        from routers.ai.enhance import _resolve_suggested_ai
        persona = json.dumps(case.get("user_profile") or {})
        domain = case.get("domain", "")
        got = _resolve_suggested_ai(persona, domain)
        return got == expected, f"got={got!r} expected={expected!r}"
    except ImportError:
        return None, "could not import _resolve_suggested_ai"


# ---------------------------------------------------------------------------
# Main benchmark runner
# ---------------------------------------------------------------------------

async def run_benchmark(cases: List[Dict[str, Any]]) -> Dict[str, Any]:
    results = []

    for case in cases:
        case_id = case["id"]
        try:
            extraction = await run_extraction(case)
        except Exception as exc:
            results.append({
                "id": case_id,
                "error": str(exc),
                "intent_ok": False,
                "domain_ok": False,
                "secondary_specific": False,
                "suggested_ai_ok": None,
            })
            continue

        intent_ok, intent_msg = score_intent(extraction, case)
        domain_ok, domain_msg = score_domain(extraction, case)
        secondary_ok, secondary_msg = score_secondary_intent_specificity(extraction, case)
        ai_result = check_suggested_ai(case)
        ai_ok = ai_result[0] if ai_result else None

        results.append({
            "id": case_id,
            "icp": case.get("icp"),
            "intent_ok": intent_ok,
            "intent_detail": intent_msg,
            "domain_ok": domain_ok,
            "domain_detail": domain_msg,
            "secondary_specific": secondary_ok,
            "secondary_detail": secondary_msg,
            "suggested_ai_ok": ai_ok,
            "extracted_intent": extraction.get("intent"),
            "extracted_domain": extraction.get("primary_domain", extraction.get("domains", [""])[0]),
            "extracted_secondary": extraction.get("secondary_intent"),
            "essence_snippet": (extraction.get("essence") or "")[:120],
            "test_assertion": case.get("test_assertion"),
        })

    return aggregate(results)


def aggregate(results: List[Dict]) -> Dict[str, Any]:
    total = len(results)
    errors = [r for r in results if "error" in r]
    valid = [r for r in results if "error" not in r]

    intent_pass = sum(1 for r in valid if r["intent_ok"])
    domain_pass = sum(1 for r in valid if r["domain_ok"])
    secondary_pass = sum(1 for r in valid if r["secondary_specific"])
    ai_valid = [r for r in valid if r["suggested_ai_ok"] is not None]
    ai_pass = sum(1 for r in ai_valid if r["suggested_ai_ok"])

    # Per-class intent breakdown
    by_intent: Dict[str, Dict[str, int]] = defaultdict(lambda: {"total": 0, "correct": 0})
    for r in valid:
        expected_intent = r.get("intent_detail", "").split("expected=")[-1].strip().strip("'")
        by_intent[expected_intent]["total"] += 1
        if r["intent_ok"]:
            by_intent[expected_intent]["correct"] += 1

    # Per-class domain breakdown
    by_domain: Dict[str, Dict[str, int]] = defaultdict(lambda: {"total": 0, "correct": 0})
    for r in valid:
        expected_domain = r.get("domain_detail", "").split("expected=")[-1].strip().strip("'")
        by_domain[expected_domain]["total"] += 1
        if r["domain_ok"]:
            by_domain[expected_domain]["correct"] += 1

    # Failures
    intent_failures = [r for r in valid if not r["intent_ok"]]
    domain_failures = [r for r in valid if not r["domain_ok"]]

    return {
        "summary": {
            "total_cases": total,
            "errors": len(errors),
            "valid": len(valid),
            "intent_accuracy": round(intent_pass / len(valid), 3) if valid else 0,
            "domain_accuracy": round(domain_pass / len(valid), 3) if valid else 0,
            "secondary_specificity_rate": round(secondary_pass / len(valid), 3) if valid else 0,
            "suggested_ai_accuracy": round(ai_pass / len(ai_valid), 3) if ai_valid else None,
        },
        "thresholds": {
            "intent_target": 0.85,
            "domain_target": 0.75,
            "secondary_specificity_target": 0.70,
        },
        "threshold_pass": {
            "intent": (intent_pass / len(valid) >= 0.85) if valid else False,
            "domain": (domain_pass / len(valid) >= 0.75) if valid else False,
            "secondary": (secondary_pass / len(valid) >= 0.70) if valid else False,
        },
        "by_intent": dict(by_intent),
        "by_domain": dict(by_domain),
        "intent_failures": [
            {"id": r["id"], "detail": r["intent_detail"], "essence": r["essence_snippet"]}
            for r in intent_failures
        ],
        "domain_failures": [
            {"id": r["id"], "detail": r["domain_detail"], "essence": r["essence_snippet"]}
            for r in domain_failures
        ],
        "raw": results,
    }


def print_report(report: Dict[str, Any]) -> None:
    s = report["summary"]
    tp = report["threshold_pass"]

    print("\n" + "=" * 60)
    print("INTENT DETECTION BENCHMARK RESULTS")
    print("=" * 60)
    print(f"  Cases: {s['total_cases']}  Errors: {s['errors']}  Valid: {s['valid']}")
    print()
    print(f"  Intent accuracy:      {s['intent_accuracy']:.1%}  {'✓ PASS' if tp['intent'] else '✗ FAIL'}  (target ≥85%)")
    print(f"  Domain accuracy:      {s['domain_accuracy']:.1%}  {'✓ PASS' if tp['domain'] else '✗ FAIL'}  (target ≥75%)")
    print(f"  Secondary specificity:{s['secondary_specificity_rate']:.1%}  {'✓ PASS' if tp['secondary'] else '✗ FAIL'}  (target ≥70%)")
    if s["suggested_ai_accuracy"] is not None:
        print(f"  Suggested AI:         {s['suggested_ai_accuracy']:.1%}")
    print()

    print("Per-intent breakdown:")
    for intent, counts in sorted(report["by_intent"].items()):
        acc = counts["correct"] / counts["total"] if counts["total"] else 0
        flag = "✓" if acc >= 0.85 else "✗"
        print(f"  {flag} {intent:<20} {counts['correct']}/{counts['total']} ({acc:.0%})")
    print()

    if report["intent_failures"]:
        print("Intent failures:")
        for f in report["intent_failures"]:
            print(f"  [{f['id']}] {f['detail']}")
            if f["essence"]:
                print(f"    essence: {f['essence'][:80]}...")
    print()

    if report["domain_failures"]:
        print("Domain failures:")
        for f in report["domain_failures"][:10]:
            print(f"  [{f['id']}] {f['detail']}")
    print("=" * 60)


async def main() -> int:
    cases = load_test_cases()
    print(f"Loaded {len(cases)} test cases from {_TEST_FILE}")

    report = await run_benchmark(cases)
    print_report(report)

    # Save scores
    scores_file = _SCORES_DIR / "intent_latest_scores.json"
    with open(scores_file, "w", encoding="utf-8") as f:
        # Exclude raw per-case detail for the scores file — keep summary + failures
        save = {k: v for k, v in report.items() if k != "raw"}
        json.dump(save, f, indent=2)
    print(f"Scores saved to {scores_file}")

    # Exit code: 0 if all thresholds pass, 1 if any fail
    all_pass = all(report["threshold_pass"].values())
    return 0 if all_pass else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
