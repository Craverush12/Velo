def format_context_for_prompt(context: dict) -> str:
    """Return a formatted context block, or empty string for new/empty users."""
    if not context or context.get("enhancement_count", 0) == 0:
        return ""

    prefs = context.get("preferences", {})
    domains = context.get("domains", [])
    recent = context.get("recent_context", [])[:3]
    tools = prefs.get("preferred_tools", [])
    notes = context.get("personalization_notes", "")

    lines = ["--- USER CONTEXT ---"]
    if domains:
        lines.append(f"Expertise domains: {', '.join(domains)}")
    if prefs.get("expertise_level"):
        lines.append(f"Expertise level: {prefs['expertise_level']}")
    if tools:
        lines.append(f"Preferred tools: {', '.join(tools)}")
    if prefs.get("industry"):
        lines.append(f"Industry: {prefs['industry']}")
    if recent:
        lines.append("Recent work:")
        for item in recent:
            lines.append(f"  • {item.get('summary', item.get('intent', ''))}")
    if notes:
        lines.append(f"Personalization notes: {notes}")
    lines.append(f"Total sessions: {context.get('enhancement_count', 0)}")
    lines.append("--- END CONTEXT ---")
    return "\n".join(lines)
