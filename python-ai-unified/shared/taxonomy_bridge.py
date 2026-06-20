"""
Two-taxonomy bridge for ThinkVelocity prompt intelligence.

WHY TWO TAXONOMIES:
- Context engine (6 intents, 20 domains): coarse session-level classification used to
  build MASTER/FLOW essence and store in pgvector/Supermemory. Optimised for stability
  across sessions — "what is this user working on over time?"
- Enhance system (21 intents, 16 domains): fine-grained prompt-level classification used
  by the enhance LLM to select prompt framework and apply domain rules. Optimised for
  precision — "which framework fits this specific prompt?"

This module maps context-engine signals → enhance-system hints. The enhance LLM still
classifies independently; these hints are advisory, not overriding.
"""

_CONTEXT_TO_ENHANCE_DOMAIN = {
    "software_data_engineering": "software_engineering",
    "business_marketing": "marketing_growth",
    "operations_hr_support": "business_operations",
    "finance_legal": "finance",  # REVIEW: could split — legal → legal, finance → finance
    "education_research": "education",
    "creative_arts_media": "creative_arts",
    "healthcare_medical": "health_science",
    "gov_nonprofit": "business_operations",  # REVIEW: no direct match; closest is business_operations
    "manufacturing_agri": "business_operations",  # REVIEW: no direct match in enhance taxonomy
    "travel_hospitality": "general",
    "environment_sustainability": "general",
    "productivity_planning": "business_operations",
    "lifestyle_relationships": "general",
    "food_nutrition": "general",
    "sports_recreation": "general",
    "logic_mathematics": "data_science",  # REVIEW: math ≠ data science but it's the closest
    "news_current_events": "general",
    "philosophy_religion": "education",  # REVIEW: education is the closest but imperfect
    "social_casual": "general",
    "system_ai_meta": "software_engineering",
}

_CONTEXT_TO_ENHANCE_INTENT = {
    "inquiry": "research",
    "construction": "code_generation",  # REVIEW: construction also covers writing/planning; code_generation is narrower
    "debugging": "debugging",
    "decision": "business_strategy",  # REVIEW: decision also covers non-business choices; business_strategy is narrower
    "operation": "task_automation",
    "chat": "general_qa",
}


def map_context_domain(context_domain: str) -> str:
    """Map a context-engine macro-domain to the closest enhance-system domain."""
    return _CONTEXT_TO_ENHANCE_DOMAIN.get(context_domain, "general")


def map_context_intent(context_intent: str) -> str:
    """Map a context-engine macro-intent to the closest enhance-system intent."""
    return _CONTEXT_TO_ENHANCE_INTENT.get(context_intent, "general_qa")


def map_context_to_enhance(context_intent: str, context_domain: str) -> dict:
    """Return both mapped values as a dict — convenience for callers needing both."""
    return {
        "enhance_intent_hint": map_context_intent(context_intent),
        "enhance_domain_hint": map_context_domain(context_domain),
    }
