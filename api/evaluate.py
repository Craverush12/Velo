from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel
from typing import Optional
from core.evaluator import evaluate_execution
from storage import store

router = APIRouter(prefix="/evaluate", tags=["Evaluation"])

class EvaluationRequest(BaseModel):
    user_id: str = "default"
    prompt_id: str = "unknown"
    system_prompt: str = ""
    user_input: str = ""
    llm_output: str = ""
    latency_ms: int = 0
    token_usage: dict = {}

@router.post("/")
async def trigger_evaluation(req: EvaluationRequest, background_tasks: BackgroundTasks):
    """Trigger an asynchronous evaluation of a prompt execution."""
    background_tasks.add_task(evaluate_execution, req.model_dump())
    return {"status": "evaluation_queued"}

@router.post("/sample")
async def seed_sample_evaluation(background_tasks: BackgroundTasks):
    """Seed a sample evaluation for the dashboard."""
    sample_req = EvaluationRequest(
        user_id="default",
        prompt_id="sample-code-gen",
        system_prompt="You are an expert Python coder.",
        user_input="Write a binary search function.",
        llm_output="def binary_search(arr, target):\n    low, high = 0, len(arr) - 1\n    while low <= high:\n        mid = (low + high) // 2\n        if arr[mid] == target:\n            return mid\n        elif arr[mid] < target:\n            low = mid + 1\n        else:\n            high = mid - 1\n    return -1",
        latency_ms=1250,
        token_usage={"prompt_tokens": 15, "completion_tokens": 50, "total_tokens": 65}
    )
    background_tasks.add_task(evaluate_execution, sample_req.model_dump())
    return {"status": "sample_evaluation_queued"}

@router.get("/")
def get_evaluations(user_id: str = "default"):
    """Retrieve all stored evaluations for the given user."""
    return {"evaluations": store.get_evaluations(user_id)}
