# tests/eval/run_enhancement_eval.py
"""Run the enhancement eval over the golden set.

--mock : score deterministic stub enhancements (infra test, no API key).
real    : call the live enhance pipeline (requires Groq key); each golden
          raw_prompt is enhanced, then scored by structural_scorer.

Saves tests/benchmarks/enhancement_v0_scores.json with summary + mode +
threshold_pass. Exit 0 if mean structural score >= floor, else 1.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import sys

EVAL_DIR = pathlib.Path(__file__).resolve().parent
REPO = EVAL_DIR.parents[1]
SERVICE = REPO / "python-ai-unified"
for p in (str(EVAL_DIR), str(SERVICE)):
    if p not in sys.path:
        sys.path.insert(0, p)

from structural_scorer import score_enhancement  # noqa: E402

GOLDEN = EVAL_DIR / "enhancement_golden_set.json"
OUT = REPO / "tests" / "benchmarks" / "enhancement_v0_scores.json"
FLOOR = 0.80  # ratcheting quality floor — raise, never lower


def _mock_enhance(case: dict) -> dict:
    raw = case["raw_prompt"]
    return {
        "enhanced_prompt": (
            f"You are a senior {case['domain']} expert. Your task: {raw}. "
            "Output must follow named sections. Do not invent facts. Provide [CONTEXT]."
        ),
        "annotated_segments": [{"technique": t} for t in (
            "persona_injection", "task_clarification", "output_format_spec",
            "constraint_definition", "negative_space")],
        "raw_prompt": raw,
    }


async def _real_enhance(case: dict) -> dict:
    from local_app import EnhanceRequest, _generate, map_mode
    from fastapi import BackgroundTasks
    req = EnhanceRequest(prompt=case["raw_prompt"], user_id="eval",
                         prompt_mode=map_mode(case.get("mode")))
    resp = await _generate(req, BackgroundTasks())
    enhanced, segments = "", []
    async for raw_chunk in resp.body_iterator:
        if isinstance(raw_chunk, bytes):
            raw_chunk = raw_chunk.decode("utf-8")
        for line in raw_chunk.split("\n"):
            line = line.strip()
            if line.startswith("data:"):
                try:
                    ev = json.loads(line[5:].strip())
                except json.JSONDecodeError:
                    continue
                if ev.get("type") == "done":
                    r = ev.get("result", {})
                    enhanced = r.get("enhanced_prompt", "")
                    segments = r.get("annotated_segments", [])
    return {"enhanced_prompt": enhanced, "annotated_segments": segments,
            "raw_prompt": case["raw_prompt"]}


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mock", action="store_true")
    args = ap.parse_args()
    mode = "mock" if args.mock else "real"
    if args.mock:
        print("MOCK MODE — deterministic stubs, infrastructure test only")

    cases = json.loads(GOLDEN.read_text(encoding="utf-8"))
    rows, total = [], 0.0
    for c in cases:
        enh = _mock_enhance(c) if args.mock else await _real_enhance(c)
        s = score_enhancement(enh)
        total += s["score"]
        rows.append({"id": c["id"], "domain": c["domain"], "score": s["score"], "checks": s["checks"]})

    mean = round(total / len(cases), 3) if cases else 0.0
    report = {
        "mode": mode,
        "cases": len(cases),
        "mean_structural_score": mean,
        "floor": FLOOR,
        "threshold_pass": mean >= FLOOR,
        "rows": rows,
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"mean={mean}  floor={FLOOR}  pass={report['threshold_pass']}  -> {OUT}")
    return 0 if report["threshold_pass"] else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
