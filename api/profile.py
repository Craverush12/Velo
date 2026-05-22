from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import json
from datetime import datetime, timezone

from storage.store import get_user_context, save_user_context
from core.llm import complete

router = APIRouter()

class AutoIngestRequest(BaseModel):
    user_id: str
    raw_data: str

@router.post("/profile/auto-ingest")
async def auto_ingest_profile(req: AutoIngestRequest = Body(...)):
    """
    Parses unstructured text, code, or JSON exports from other AIs to extract user persona.
    Populates the Knowledge Graph and preferences.
    """
    context = get_user_context(req.user_id)
    
    # Try to parse as direct JSON first (if the user copy-pasted our extractor output)
    extracted_data = None
    try:
        extracted_data = json.loads(req.raw_data)
    except json.JSONDecodeError:
        pass
        
    if not extracted_data:
        # If not raw JSON, use LLM to extract it based on our prompt
        try:
            with open("core/prompts/memory_extraction.md", "r", encoding="utf-8") as f:
                system_prompt = f.read()
                
            response = await complete(
                system_prompt=system_prompt,
                user_message=f"Extract persona from this data:\n{req.raw_data}",
                temperature=0.1,
                max_tokens=2048
            )
            extracted_data = json.loads(response)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to extract profile: {str(e)}")

    # Update preferences
    prefs = context.setdefault("preferences", {})
    new_prefs = extracted_data.get("preferences", {})
    for k, v in new_prefs.items():
        if v:
            prefs[k] = v
            
    # Add domains and frameworks to flat list
    domains = extracted_data.get("domains", [])
    frameworks = extracted_data.get("frameworks_used", [])
    
    for d in domains:
        if d not in context["domains"]:
            context["domains"].append(d)
            
    for f in frameworks:
        if f not in context.get("frameworks_used", []):
            context.setdefault("frameworks_used", []).append(f)
            
    if extracted_data.get("personalization_notes"):
        context["personalization_notes"] = extracted_data["personalization_notes"]

    # Update Knowledge Graph
    from core.context_graph import KnowledgeGraph
    graph_data = context.get("graph", {"nodes": {}, "edges": []})
    graph = KnowledgeGraph(graph_data)
    
    # We create a meta interaction to represent this import
    import uuid
    import_id = f"import_{uuid.uuid4().hex[:8]}"
    graph.add_node(import_id, "interaction", {
        "intent": "auto_ingest_profile",
        "summary": "Imported persona from external source"
    })
    
    for d in domains:
        domain_id = f"domain:{d.lower()}"
        if domain_id not in graph.data["nodes"]:
            graph.add_node(domain_id, "concept", {"name": d})
        graph.add_edge(import_id, domain_id, "belongs_to_domain")
        graph._update_micro_persona(d, None)
        
    for f in frameworks:
        framework_id = f"framework:{f.lower()}"
        if framework_id not in graph.data["nodes"]:
            graph.add_node(framework_id, "concept", {"name": f})
        graph.add_edge(import_id, framework_id, "uses_framework")
        
        # Link frameworks to the first domain as a guess
        if domains:
            graph._update_micro_persona(domains[0], f)

    context["graph"] = graph.to_dict()
    context["micro_personas"] = {p["id"]: p for p in graph.get_personas()}
    context["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    save_user_context(req.user_id, context)
    
    return {"status": "success", "message": "Profile ingested successfully", "data": extracted_data}
