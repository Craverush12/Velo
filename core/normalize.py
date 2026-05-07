def quality_ceiling(raw_prompt: str) -> float:
    words = [w for w in raw_prompt.replace("\n", " ").split(" ") if w.strip()]
    word_count = len(words)
    char_count = len(raw_prompt.strip())
    markers = 0
    marker_terms = [
        "output", "format", "audience", "target", "tone", "constraint",
        "example", "context", "because", "using", "avoid", "include",
        "json", "table", "steps", "role", "goal", "metric",
    ]
    lowered = raw_prompt.lower()
    markers += sum(1 for term in marker_terms if term in lowered)
    markers += 1 if "[" in raw_prompt and "]" in raw_prompt else 0
    markers += 1 if "\n" in raw_prompt else 0

    if char_count <= 2 or word_count <= 1:
        return 0.08
    if word_count <= 3:
        return 0.18
    if word_count <= 7 and markers == 0:
        return 0.28
    if word_count <= 12 and markers <= 1:
        return 0.42
    if word_count <= 25 and markers <= 2:
        return 0.62
    if markers >= 4 and word_count >= 20:
        return 0.88
    return 0.74


def normalize_result(result: dict, raw_prompt: str = "") -> dict:
    """Repair common JSON-mode drift while preserving LLM annotations."""
    prompt = result.get("enhanced_prompt") or ""
    segments = result.get("annotated_segments") or []
    if prompt and segments and "".join(seg.get("text", "") for seg in segments) != prompt:
        cursor = 0
        repaired = []
        for seg in segments:
            text = seg.get("text", "")
            stripped = text.strip()
            found = prompt.find(stripped, cursor) if stripped else -1
            if found >= 0:
                seg = dict(seg)
                seg["text"] = prompt[cursor:found] + stripped
                repaired.append(seg)
                cursor = found + len(stripped)
            else:
                repaired = []
                break
        if repaired and cursor <= len(prompt):
            repaired[-1]["text"] += prompt[cursor:]
            result["annotated_segments"] = repaired

    fields = result.get("placeholder_fields") or []
    if fields:
        techniques = result.setdefault("pe_techniques_applied", [])
        if "placeholder_facilitation" not in techniques:
            techniques.append("placeholder_facilitation")

    try:
        model_score = float(result.get("prompt_quality_score", 0.0) or 0.0)
    except (TypeError, ValueError):
        model_score = 0.0
    result["prompt_quality_score"] = round(
        max(0.0, min(model_score, quality_ceiling(raw_prompt))), 2
    )
    return result
