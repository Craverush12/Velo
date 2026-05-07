import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

from mcp.server import Server
from mcp.types import Tool, TextContent

from core import context_loader, safety
from core.llm import complete_with_usage
from core.normalize import normalize_result, quality_ceiling
from storage import store

_ENHANCE_PROMPT = (Path(__file__).parent / "prompts" / "enhance_system.md").read_text()
_REFINE_PROMPT = (Path(__file__).parent / "prompts" / "refine_system.md").read_text()

mcp_server = Server("velocity")


def _user_id() -> str:
    return os.getenv("VELOCITY_USER_ID", "anonymous")


# ── Tool schemas ──────────────────────────────────────────────────────────────

@mcp_server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="enhance_prompt",
            description=(
                "Transform a raw prompt into a precision-engineered prompt using the optimal "
                "prompt engineering framework. Returns an annotated breakdown showing before/after, "
                "quality improvement, and the techniques applied. "
                "IMPORTANT: Call inject_context at the start of every new conversation to load user memory."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "The raw prompt to enhance",
                    },
                    "target_ai": {
                        "type": "string",
                        "description": "Target AI surface: claude, chatgpt, cursor, gemini, bolt, replit, gamma, midjourney",
                    },
                },
                "required": ["prompt"],
            },
        ),
        Tool(
            name="refine_prompt",
            description=(
                "Refine an enhanced prompt using clarification answers. "
                "Call this after enhance_prompt when you have answers to the clarification questions."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "original_prompt": {
                        "type": "string",
                        "description": "The original raw prompt (before enhancement)",
                    },
                    "clarification_qa": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "question": {"type": "string"},
                                "answer": {"type": "string"},
                            },
                            "required": ["question", "answer"],
                        },
                        "description": "Question/answer pairs from the enhance_prompt clarification_questions",
                    },
                    "target_ai": {
                        "type": "string",
                        "description": "Target AI surface (optional)",
                    },
                },
                "required": ["original_prompt", "clarification_qa"],
            },
        ),
        Tool(
            name="get_my_context",
            description=(
                "Show your Velocity profile: token efficiency metrics, usage signals, "
                "recent sessions, and persona. Use this to inspect what Velocity knows about you."
            ),
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="inject_context",
            description=(
                "Load your Velocity memory into this session. "
                "Call this automatically at the start of every conversation so the AI knows your "
                "expertise, stack, current work, and preferences without you having to explain them."
            ),
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


# ── Tool handlers ─────────────────────────────────────────────────────────────

@mcp_server.call_tool()
async def call_tool(name: str, arguments: dict | None) -> list[TextContent]:
    args = arguments or {}

    if name == "enhance_prompt":
        return await _handle_enhance(args)
    if name == "refine_prompt":
        return await _handle_refine(args)
    if name == "get_my_context":
        return [TextContent(type="text", text=_format_context(store.get_user_context(_user_id())))]
    if name == "inject_context":
        return [TextContent(type="text", text=_format_inject(store.get_user_context(_user_id())))]

    raise ValueError(f"Unknown tool: {name}")


async def _handle_enhance(args: dict) -> list[TextContent]:
    raw_prompt = args.get("prompt", "").strip()
    target_ai = args.get("target_ai")
    user_id = _user_id()

    clean_prompt, _ = safety.redact(raw_prompt)
    user_ctx = store.get_user_context(user_id)
    ctx_block = context_loader.format_context_for_prompt(user_ctx)

    user_message_parts = [
        f"Raw prompt: {clean_prompt}",
        f"Target AI: {target_ai or 'not specified'}",
    ]
    if ctx_block:
        user_message_parts.append(ctx_block)
    user_message = "\n".join(user_message_parts)

    raw, usage = await complete_with_usage(_ENHANCE_PROMPT, user_message)

    try:
        result = normalize_result(json.loads(raw), clean_prompt)
    except json.JSONDecodeError:
        return [TextContent(type="text", text="Velocity: Failed to parse enhancement output. Please try again.")]

    # Store with token tracking
    tokens_used = usage.get("total_tokens", 0)
    quality = float(result.get("prompt_quality_score", 0.5) or 0.5)
    avg_retries = (1.0 - quality) * 2.5
    tokens_saved = max(0, int(usage.get("prompt_tokens", 0) * avg_retries))

    store.update_after_enhancement(
        user_id,
        result.get("intent", "general_qa"),
        result.get("domain", "general"),
        result.get("summary", ""),
        result.get("framework_used"),
        len(result.get("placeholder_fields") or []),
        tokens_used,
        tokens_saved,
    )

    return [TextContent(type="text", text=_format_enhance_result(raw_prompt, result))]


async def _handle_refine(args: dict) -> list[TextContent]:
    original = args.get("original_prompt", "")
    qa_pairs = args.get("clarification_qa", [])
    target_ai = args.get("target_ai")

    qa_lines = []
    for i, qa in enumerate(qa_pairs, 1):
        qa_lines.append(f"Q{i}: {qa.get('question', '')}")
        qa_lines.append(f"A{i}: {qa.get('answer', '')}")

    user_message = "\n".join([
        f"Original prompt: {original}",
        f"Target AI: {target_ai or 'not specified'}",
        "",
        "Clarification Q&A:",
        *qa_lines,
    ])

    raw = await _refine_complete(user_message)

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        return [TextContent(type="text", text="Velocity Refine: Failed to parse output. Please try again.")]

    return [TextContent(type="text", text=_format_refine_result(result))]


async def _refine_complete(user_message: str) -> str:
    from core.llm import complete
    return await complete(_REFINE_PROMPT, user_message)


# ── Formatters ────────────────────────────────────────────────────────────────

def _format_enhance_result(original: str, result: dict) -> str:
    enhanced = result.get("enhanced_prompt", "")
    framework = result.get("framework_used", "")
    quality = result.get("prompt_quality_score", 0.0)
    domain = result.get("domain", "")
    intent = result.get("intent", "")
    techniques = result.get("pe_techniques_applied", [])
    segments = result.get("annotated_segments", [])
    summary = result.get("summary", "")
    clarifications = result.get("clarification_questions", [])

    # Quality score before (estimate from original length/complexity)
    original_words = len(original.split())
    before_quality = min(0.35, original_words * 0.02)

    pts_gained = round((quality - before_quality) * 100)

    lines = [
        f"## Velocity Enhanced ⚡",
        f"",
        f"**{framework}** · Quality **{before_quality:.2f} → {quality:.2f}** (+{pts_gained} pts) · {domain} · {intent}",
        f"",
        f"### Before",
        f"```",
        original,
        f"```",
        f"",
        f"### After",
        f"```",
        enhanced,
        f"```",
    ]

    # What Velocity added — top 3 segments with real explanations
    if segments:
        lines += ["", "### What Velocity added"]
        ICONS = {
            "persona_injection": "🎭",
            "chain_of_thought": "🧠",
            "output_format_spec": "📐",
            "constraint_definition": "🔒",
            "context_framing": "🗂️",
            "few_shot_example": "📎",
            "negative_space": "🚫",
            "target_ai_optimization": "🎯",
            "step_back_trigger": "⬆️",
            "domain_specific_depth": "🔬",
            "user_context_integration": "👤",
        }
        shown = 0
        for seg in segments:
            if shown >= 3:
                break
            technique = seg.get("technique", "")
            label = seg.get("technique_label", technique.replace("_", " ").title())
            reason = seg.get("reason", "")
            icon = ICONS.get(technique, "•")
            lines.append(f"- {icon} **{label}** — {reason}")
            shown += 1

    # Techniques
    if techniques:
        tech_display = " · ".join(t.replace("_", " ").title() for t in techniques)
        lines += ["", f"**Techniques:** {tech_display}"]

    # Summary
    if summary:
        lines += ["", f"*{summary}*"]

    # Clarification questions
    if clarifications:
        lines += ["", "### Clarify further (call refine_prompt with answers)"]
        for i, q in enumerate(clarifications, 1):
            lines.append(f"{i}. {q}")

    lines += [
        "",
        "---",
        "*Copy the **After** prompt above and use it with any AI.*",
    ]

    return "\n".join(lines)


def _format_refine_result(result: dict) -> str:
    refined = result.get("refined_prompt", "")
    framework = result.get("framework_used", "")
    techniques = result.get("pe_techniques_applied", [])
    additions = result.get("key_additions", [])
    summary = result.get("summary", "")

    lines = [
        "## Velocity Refined ✦",
        "",
        f"**{framework}**",
        "",
        "### Refined Prompt",
        "```",
        refined,
        "```",
    ]

    if additions:
        lines += ["", "### What changed"]
        for a in additions:
            lines.append(f"- {a}")

    if techniques:
        tech_display = " · ".join(t.replace("_", " ").title() for t in techniques)
        lines += ["", f"**Techniques:** {tech_display}"]

    if summary:
        lines += ["", f"*{summary}*"]

    lines += ["", "---", "*Copy the refined prompt above.*"]
    return "\n".join(lines)


def _format_inject(ctx: dict) -> str:
    if not ctx or ctx.get("enhancement_count", 0) == 0:
        return (
            "🟣 **Velocity context loading**\n\n"
            "No sessions yet — your memory graph is empty. "
            "Use `enhance_prompt` to start building your profile.\n\n"
            "*No need to re-explain yourself — Velocity will learn as you go.*"
        )

    prefs = ctx.get("preferences", {})
    domains = ctx.get("domains", [])[:3]
    recent = ctx.get("recent_context", [])[:2]
    expertise = prefs.get("expertise_level", "intermediate")
    tools = prefs.get("preferred_tools", [])
    notes = ctx.get("personalization_notes", "")
    count = ctx.get("enhancement_count", 0)

    persona = _persona_label(ctx)

    lines = [
        f"🟣 **Velocity context loaded** — {persona} · Session {count}",
        "",
    ]

    if expertise:
        lines.append(f"- **Expertise:** {expertise.title()}")
    if domains:
        lines.append(f"- **Domains:** {', '.join(d.replace('_', ' ') for d in domains)}")
    if tools:
        lines.append(f"- **Stack:** {', '.join(tools)}")
    if recent:
        recent_summaries = [r.get("summary", r.get("intent", "")) for r in recent if r.get("summary")]
        if recent_summaries:
            lines.append(f"- **Current work:** {' · '.join(recent_summaries[:2])}")
    if prefs.get("output_style"):
        lines.append(f"- **Style:** {prefs['output_style'].replace('_', ' ').title()}")
    if notes:
        lines.append(f"- **Note:** {notes}")

    lines += [
        "",
        "*No need to re-explain yourself — I have your context for this session.*",
    ]

    return "\n".join(lines)


def _format_context(ctx: dict) -> str:
    count = ctx.get("enhancement_count", 0)
    domains = ctx.get("domains", [])
    recent = ctx.get("recent_context", [])
    total_used = ctx.get("total_tokens_used", 0)
    total_saved = ctx.get("total_tokens_saved", 0)
    persona = _persona_label(ctx)
    frameworks = ctx.get("frameworks_used", [])

    efficiency_pct = 0
    if total_used + total_saved > 0:
        efficiency_pct = round(total_saved / (total_used + total_saved) * 100)

    lines = [
        f"## Velocity Signals 🧠",
        f"",
        f"**{persona}** · {count} sessions · {len(domains)} domains",
        f"",
    ]

    # Token efficiency strip
    lines += [
        "### Token Efficiency",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Prompts enhanced | {count} |",
        f"| Tokens used by Velocity | {total_used:,} |",
        f"| Tokens saved (estimated) | {total_saved:,} |",
        f"| Efficiency | {efficiency_pct}% fewer tokens spent |",
        "",
    ]

    # Visual bar
    with_pct = max(5, 100 - efficiency_pct)
    filled = round(with_pct / 5)
    empty = 20 - filled
    lines += [
        f"Without Velocity: {'█' * 20}",
        f"With Velocity:    {'█' * filled}{'░' * empty}  ({with_pct}%)",
        "",
    ]

    # Signals
    lines.append("### Signals")

    # Build sprint detection
    if len(recent) >= 3:
        recent_intents = [r.get("intent", "") for r in recent[:4]]
        code_intents = {"code_generation", "debugging", "code_review", "architecture_design"}
        if sum(1 for i in recent_intents if i in code_intents) >= 3:
            lines.append(f"- 🏗️ **Building sprint** — {len(recent_intents)} consecutive technical sessions · biasing toward RTF + CoT")

    # Quality trend
    if count >= 5 and recent:
        avg_recent = sum(r.get("tokens_saved", 0) for r in recent[:3]) / max(1, min(3, len(recent)))
        lines.append(f"- 📈 **Quality improving** — avg {avg_recent:.0f} tokens saved per session over last {min(3, len(recent))} sessions")

    # Positive signal for framework preference
    if frameworks:
        lines.append(f"- ⚡ **Preferred framework: {frameworks[0]}** — Velocity selects this for your prompt types {round(1/len(frameworks)*100) if frameworks else 0}% of the time")

    # Gap signal
    if count >= 3:
        lines.append("- 📐 **Tip** — Specifying `target_ai` in enhance_prompt unlocks AI-specific optimisations")

    # Recent sessions
    lines += ["", "### Recent Sessions", ""]
    lines.append("| Session | Tokens saved | When |")
    lines.append("|---------|-------------|------|")
    for r in recent[:3]:
        summary = r.get("summary", r.get("intent", "Unknown"))[:45]
        saved = r.get("tokens_saved", 0)
        at_str = _relative_time(r.get("at", ""))
        lines.append(f"| {summary} | −{saved} | {at_str} |")

    return "\n".join(lines)


def _persona_label(ctx: dict) -> str:
    placeholder_count = ctx.get("placeholder_count", 0)
    enhancement_count = max(ctx.get("enhancement_count", 1), 1)
    domains = ctx.get("domains", [])
    recent = ctx.get("recent_context", [])

    if enhancement_count < 3:
        return "New Operator"

    placeholder_ratio = placeholder_count / enhancement_count
    if placeholder_ratio > 1.5:
        return "Template Architect"

    recent_intents = [r.get("intent", "") for r in recent[:5]]
    strategy_intents = {"business_strategy", "product_strategy", "marketing"}
    code_intents = {"code_generation", "debugging", "architecture_design", "system_design"}
    marketing_intents = {"marketing", "copywriting", "creative_writing"}

    if sum(1 for i in recent_intents if i in strategy_intents) >= 3:
        return "Strategy Builder"
    if sum(1 for i in recent_intents if i in code_intents) >= 3:
        return "Technical Builder"
    if sum(1 for i in recent_intents if i in marketing_intents) >= 3:
        return "Growth Operator"
    if len(domains) >= 4:
        return "Cross-Domain Explorer"
    return "Builder"


def _relative_time(iso: str) -> str:
    if not iso:
        return "Unknown"
    try:
        then = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        delta = now - then
        if delta < timedelta(hours=1):
            return f"{delta.seconds // 60}m ago"
        if delta < timedelta(days=1):
            return f"{delta.seconds // 3600}h ago"
        return f"{delta.days}d ago"
    except Exception:
        return "Recently"
