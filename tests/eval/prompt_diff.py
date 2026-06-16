"""tests/eval/prompt_diff.py — Visual before/after diff of enhanced/refined prompts.

Purpose: make the effect of a code change (or a personalization layer like
Supermemory/local context) *visible* rather than inferred from logs. Calls the
live /enhance or /refine endpoint twice — once for a "before" condition and
once for an "after" condition — and renders a side-by-side HTML diff plus a
unified-diff text view, written directly to disk (avoids the Blob/iframe
sandbox issue with chat-rendered downloads).

Usage:
    # Compare a fresh/no-history user vs a user with stored context —
    # isolates exactly what personalization (local memory + Supermemory)
    # changes in the output, holding the prompt itself constant.
    python tests/eval/prompt_diff.py --mode enhance \
        --prompt "build a React Native grocery delivery app" \
        --before-user fresh_anon_001 --after-user 999999 \
        --out diff_report.html

    # Compare two arbitrary raw outputs you already have (e.g. captured before
    # a deploy and after a deploy) without making live calls:
    python tests/eval/prompt_diff.py --before-text before.txt --after-text after.txt --out diff_report.html

Environment:
    TV_BASE_URL    defaults to http://localhost:8000
"""

from __future__ import annotations

import argparse
import asyncio
import difflib
import html
import json
import os
import sys
import time
from pathlib import Path

import httpx

TV_BASE_URL = os.getenv("TV_BASE_URL", "http://localhost:8000")


async def _call_enhance(client: httpx.AsyncClient, prompt: str, user_id: str, prompt_mode: str) -> tuple[str, dict]:
    resp = await client.post(
        f"{TV_BASE_URL}/enhance",
        json={"prompt": prompt, "user_id": user_id, "prompt_mode": prompt_mode, "incognito": False},
        timeout=60.0,
    )
    resp.raise_for_status()
    enhanced = ""
    meta: dict = {}
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
            result = event.get("result", {})
            enhanced = result.get("enhanced_prompt", "")
            meta = {
                "intent": result.get("intent"),
                "domain": result.get("domain"),
                "framework_used": result.get("framework_used"),
                "_stage_timings": result.get("_stage_timings"),
            }
            break
    return enhanced, meta


async def _call_refine(
    client: httpx.AsyncClient, original_prompt: str, previous_enhanced: str, user_id: str, prompt_mode: str
) -> tuple[str, dict]:
    resp = await client.post(
        f"{TV_BASE_URL}/ai/refine",
        json={
            "original_prompt": original_prompt,
            "clarification_qa": [],
            "previous_enhanced_prompt": previous_enhanced,
            "user_id": user_id,
            "prompt_mode": prompt_mode,
            "incognito": False,
        },
        timeout=60.0,
    )
    resp.raise_for_status()
    data = resp.json()
    refined = data.get("refined_prompt") or data.get("enhanced_prompt") or ""
    return refined, {"raw_keys": list(data.keys())}


def _word_diff_html(before: str, after: str) -> str:
    """Render an inline word-level diff: removed words struck through in red,
    added words highlighted in green, unchanged words plain."""
    before_words = before.split()
    after_words = after.split()
    sm = difflib.SequenceMatcher(None, before_words, after_words)
    out: list[str] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            out.append(html.escape(" ".join(before_words[i1:i2])))
        elif tag == "delete":
            out.append(f'<span class="del">{html.escape(" ".join(before_words[i1:i2]))}</span>')
        elif tag == "insert":
            out.append(f'<span class="ins">{html.escape(" ".join(after_words[j1:j2]))}</span>')
        elif tag == "replace":
            out.append(f'<span class="del">{html.escape(" ".join(before_words[i1:i2]))}</span>')
            out.append(f'<span class="ins">{html.escape(" ".join(after_words[j1:j2]))}</span>')
    return " ".join(out)


def _unified_diff_text(before: str, after: str, before_label: str, after_label: str) -> str:
    diff = difflib.unified_diff(
        before.splitlines(), after.splitlines(),
        fromfile=before_label, tofile=after_label, lineterm="",
    )
    return "\n".join(diff)


def _render_html(
    title: str,
    before_label: str,
    after_label: str,
    before_text: str,
    after_text: str,
    before_meta: dict,
    after_meta: dict,
) -> str:
    word_diff = _word_diff_html(before_text, after_text)
    similarity = difflib.SequenceMatcher(None, before_text, after_text).ratio()
    changed = before_text.strip() != after_text.strip()

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>
  body {{ font-family: -apple-system, Segoe UI, Helvetica, Arial, sans-serif; max-width: 1000px; margin: 40px auto; padding: 0 20px; color: #1a1a1a; line-height: 1.55; }}
  h1 {{ font-size: 22px; }}
  .verdict {{ padding: 10px 14px; border-radius: 8px; font-weight: 600; display: inline-block; margin-bottom: 18px; }}
  .verdict.changed {{ background: #fff3cd; color: #7a5b00; }}
  .verdict.same {{ background: #e6f4ea; color: #1e7e34; }}
  .meta {{ display: flex; gap: 24px; font-size: 13px; color: #555; margin-bottom: 20px; }}
  .meta div {{ background: #f6f6f7; padding: 8px 12px; border-radius: 6px; }}
  .panel {{ background: #fafafa; border: 1px solid #e2e2e2; border-radius: 10px; padding: 18px; margin-bottom: 20px; white-space: pre-wrap; font-size: 14px; }}
  .panel h3 {{ margin: 0 0 10px; font-size: 13px; text-transform: uppercase; letter-spacing: 0.04em; color: #888; }}
  .del {{ background: #fde2e1; color: #a31515; text-decoration: line-through; padding: 1px 2px; border-radius: 3px; }}
  .ins {{ background: #d6f5dd; color: #137a3b; padding: 1px 2px; border-radius: 3px; }}
  .similarity {{ font-size: 13px; color: #888; margin-top: 6px; }}
</style></head>
<body>
  <h1>{html.escape(title)}</h1>
  <div class="verdict {'changed' if changed else 'same'}">
    {'⚠ Output differs between before and after' if changed else '✓ Output identical — no change detected'}
  </div>
  <div class="meta">
    <div><b>Before:</b> {html.escape(before_label)}</div>
    <div><b>After:</b> {html.escape(after_label)}</div>
  </div>

  <div class="panel">
    <h3>Word-level diff (red = removed, green = added)</h3>
    {word_diff}
    <div class="similarity">Similarity ratio: {similarity:.1%}</div>
  </div>

  <div class="panel">
    <h3>Before — full text ({before_label})</h3>{html.escape(before_text)}
  </div>
  <div class="panel">
    <h3>After — full text ({after_label})</h3>{html.escape(after_text)}
  </div>

  <div class="panel">
    <h3>Before — metadata</h3>{html.escape(json.dumps(before_meta, indent=2, default=str))}
  </div>
  <div class="panel">
    <h3>After — metadata</h3>{html.escape(json.dumps(after_meta, indent=2, default=str))}
  </div>
</body></html>"""


async def main() -> None:
    parser = argparse.ArgumentParser(description="Visual before/after diff of enhance/refine output")
    parser.add_argument("--mode", choices=["enhance", "refine"], default="enhance")
    parser.add_argument("--prompt", help="Prompt to enhance (required unless --before-text/--after-text given)")
    parser.add_argument("--prompt-mode", default="normal")
    parser.add_argument("--before-user", default="fresh_anon_diff_test")
    parser.add_argument("--after-user", default="999999")
    parser.add_argument("--before-label", default=None)
    parser.add_argument("--after-label", default=None)
    parser.add_argument("--before-text", help="Path to a text file with a pre-captured 'before' output")
    parser.add_argument("--after-text", help="Path to a text file with a pre-captured 'after' output")
    parser.add_argument("--out", default="prompt_diff_report.html")
    args = parser.parse_args()

    if args.before_text and args.after_text:
        before_text = Path(args.before_text).read_text(encoding="utf-8")
        after_text = Path(args.after_text).read_text(encoding="utf-8")
        before_label = args.before_label or args.before_text
        after_label = args.after_label or args.after_text
        before_meta, after_meta = {}, {}
    else:
        if not args.prompt:
            print("ERROR: --prompt is required unless using --before-text/--after-text")
            sys.exit(1)
        before_label = args.before_label or f"user={args.before_user} (no/fresh context)"
        after_label = args.after_label or f"user={args.after_user} (with stored context)"
        async with httpx.AsyncClient() as client:
            if args.mode == "enhance":
                t0 = time.perf_counter()
                before_text, before_meta = await _call_enhance(client, args.prompt, args.before_user, args.prompt_mode)
                before_meta["latency_ms"] = round((time.perf_counter() - t0) * 1000)
                t0 = time.perf_counter()
                after_text, after_meta = await _call_enhance(client, args.prompt, args.after_user, args.prompt_mode)
                after_meta["latency_ms"] = round((time.perf_counter() - t0) * 1000)
            else:
                # Refine needs a previous_enhanced_prompt; generate one first (no personalization)
                first_pass, _ = await _call_enhance(client, args.prompt, "refine_seed_anon", args.prompt_mode)
                before_text, before_meta = await _call_refine(client, args.prompt, first_pass, args.before_user, args.prompt_mode)
                after_text, after_meta = await _call_refine(client, args.prompt, first_pass, args.after_user, args.prompt_mode)

    report = _render_html(
        title=f"ThinkVelocity {args.mode} diff — {args.prompt or 'pre-captured text'}",
        before_label=before_label,
        after_label=after_label,
        before_text=before_text,
        after_text=after_text,
        before_meta=before_meta,
        after_meta=after_meta,
    )
    out_path = Path(args.out)
    out_path.write_text(report, encoding="utf-8")
    print(f"Wrote {out_path.resolve()}")

    unified = _unified_diff_text(before_text, after_text, before_label, after_label)
    print("\n--- unified diff ---")
    print(unified if unified.strip() else "(no textual difference)")


if __name__ == "__main__":
    asyncio.run(main())
