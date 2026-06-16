from fastapi import APIRouter
from pydantic import BaseModel
from core.migration import stochastic_hill_climb, MigrationRequest

router = APIRouter(prefix="/migrate", tags=["Migration"])

@router.post("/")
async def migrate_prompt(req: MigrationRequest):
    """
    Execute the Prompt Migration algorithm.
    This performs AST Structural Translation and Gradient-based Hill Climbing.
    """
    optimized_prompt = await stochastic_hill_climb(req)
    return {
        "status": "success",
        "original_model": req.source_model,
        "target_model": req.target_model,
        "optimized_prompt": optimized_prompt
    }
