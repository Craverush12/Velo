import json
import logging
from core.connectors_catalog import connector_catalog_summary

logger = logging.getLogger(__name__)

def generate_proactive_suggestions(user_context: dict) -> list[dict]:
    """
    Scans the user's Knowledge Graph (or context) and the connector catalog
    to suggest skills or connectors that the user might find useful.
    """
    suggestions = []
    if not user_context:
        return suggestions
        
    domains = user_context.get("domains", [])
    prefs = user_context.get("preferences", {})
    history = user_context.get("recent_context", [])
    
    # Simple heuristic-based matching
    # Example: if they do UI/Frontend, suggest v0.dev
    frontend_keywords = {"react", "ui", "frontend", "css", "tailwind", "component"}
    data_keywords = {"data", "analysis", "pandas", "sql", "research"}
    
    # Flatten history intents and domains
    flat_text = " ".join([h.get("summary", "") + " " + h.get("intent", "") for h in history]).lower()
    for d in domains:
        flat_text += f" {d.lower()}"
        
    flat_text += f" {prefs.get('industry', '').lower()}"

    # Catalog
    catalog = connector_catalog_summary()
    
    if any(k in flat_text for k in frontend_keywords):
        suggestions.append({
            "id": "v0-dev-connector",
            "name": "v0 by Vercel",
            "type": "connector",
            "reason": "Active Memory noticed you design UI components frequently. v0 can generate React components directly."
        })
        
    if any(k in flat_text for k in data_keywords):
        suggestions.append({
            "id": "chatgpt-advanced-data",
            "name": "ChatGPT Advanced Data Analysis",
            "type": "connector",
            "reason": "Active Memory noticed you analyze data. This connector lets you run Python over CSVs directly."
        })
        
    # Deduplicate
    seen = set()
    unique_suggestions = []
    for s in suggestions:
        if s["id"] not in seen:
            seen.add(s["id"])
            unique_suggestions.append(s)
            
    return unique_suggestions
