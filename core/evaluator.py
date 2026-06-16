import json
import datetime
from core.llm import complete
from storage import store

EVALUATOR_PROMPT = """You are an expert LLM judge evaluating prompt execution for an enterprise monitoring system.
You will be provided with the System Prompt, User Input, and the resulting LLM Output.
Assess the quality of the LLM Output based on:
1. adherence: Did it faithfully follow the instructions and constraints in the system prompt? (Score 1-5)
2. coherence: Is the output logically sound, clear, and well-structured? (Score 1-5)
3. quality: What is the overall quality and usefulness of the response? (Score 1-5)

You MUST return ONLY a JSON object with these exact keys: "adherence" (int), "coherence" (int), "quality" (int), "feedback" (string - brief explanation of the scores).
"""

async def evaluate_execution(data: dict):
    """Run an LLM-as-a-judge evaluation on a prompt execution and save the result."""
    user_message = (
        f"System Prompt:\n{data.get('system_prompt', '')}\n\n"
        f"User Input:\n{data.get('user_input', '')}\n\n"
        f"LLM Output:\n{data.get('llm_output', '')}"
    )
    
    try:
        response_text = await complete(EVALUATOR_PROMPT, user_message, temperature=0.0)
        scores = json.loads(response_text)
    except Exception as e:
        scores = {"error": str(e), "adherence": 0, "coherence": 0, "quality": 0, "feedback": "Failed to evaluate"}
        
    eval_record = {
        "user_id": data.get("user_id", "default"),
        "prompt_id": data.get("prompt_id", "unknown"),
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "latency_ms": data.get("latency_ms", 0),
        "token_usage": data.get("token_usage", {}),
        "scores": scores
    }
    
    store.save_evaluation(eval_record)
