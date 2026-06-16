import json
from pydantic import BaseModel
from typing import List, Optional
import asyncio

from core.llm import complete
from core.evaluator import evaluate_execution

class PromptAST(BaseModel):
    role: str
    context: str
    instructions: str
    constraints: List[str]
    few_shot_examples: List[str]
    output_format: str

class MigrationRequest(BaseModel):
    source_prompt: str
    source_model: str
    target_model: str
    test_input: str
    expected_output_hint: str

async def parse_to_ast(prompt: str) -> PromptAST:
    sys_prompt = "You are a prompt engineering AST parser. Break the given prompt down into the exact fields requested in JSON format. Do not change the meaning. If a section is missing, use an empty string or empty list."
    res = await complete(sys_prompt, prompt)
    try:
        data = json.loads(res)
        return PromptAST(
            role=data.get("role", ""),
            context=data.get("context", ""),
            instructions=data.get("instructions", ""),
            constraints=data.get("constraints", []),
            few_shot_examples=data.get("few_shot_examples", []),
            output_format=data.get("output_format", "")
        )
    except:
        # Fallback empty AST if parsing fails
        return PromptAST(role="", context="", instructions=prompt, constraints=[], few_shot_examples=[], output_format="")

def structural_translation(ast: PromptAST, target_model: str) -> PromptAST:
    """
    O(N) Tree Transformation mapping dialect-specific quirks.
    E.g., Sonnet prefers XML tags (<thought>), Gemini prefers markdown or clear structural delimiters.
    """
    target = target_model.lower()
    if "gemini" in target:
        # Gemini often prefers markdown over XML tags
        ast.instructions = ast.instructions.replace("<thinking>", "**Thinking Process:**").replace("</thinking>", "")
        ast.output_format = ast.output_format.replace("<output>", "```").replace("</output>", "```")
    elif "sonnet" in target or "claude" in target:
        # Claude loves XML tags
        if not "<instructions>" in ast.instructions:
            ast.instructions = f"<instructions>\n{ast.instructions}\n</instructions>"
    
    return ast

def reconstruct_prompt(ast: PromptAST) -> str:
    parts = []
    if ast.role: parts.append(f"{ast.role}\n")
    if ast.context: parts.append(f"CONTEXT:\n{ast.context}\n")
    if ast.instructions: parts.append(f"INSTRUCTIONS:\n{ast.instructions}\n")
    if ast.constraints:
        parts.append("CONSTRAINTS:")
        for c in ast.constraints: parts.append(f"- {c}")
        parts.append("")
    if ast.few_shot_examples:
        parts.append("EXAMPLES:")
        for e in ast.few_shot_examples: parts.append(f"{e}\n")
    if ast.output_format: parts.append(f"OUTPUT FORMAT:\n{ast.output_format}\n")
    return "\n".join(parts)

async def mutate_node(ast: PromptAST, failing_node: str, gradient: str) -> PromptAST:
    """
    Stochastic mutation based on textual gradient from the evaluator.
    """
    sys_prompt = f"You are an optimization function mutating a prompt AST node. The node '{failing_node}' failed due to: {gradient}. Fix the node to resolve this error. Return the fixed text in JSON format under the key 'updated_node'."
    current_val = getattr(ast, failing_node, "")
    res = await complete(sys_prompt, str(current_val))
    try:
        updated_text = json.loads(res).get("updated_node", str(current_val))
    except:
        updated_text = str(current_val)
    
    # Create a copy and apply mutation
    new_ast = PromptAST(**ast.model_dump())
    setattr(new_ast, failing_node, updated_text)
    return new_ast

async def stochastic_hill_climb(req: MigrationRequest, max_iterations: int = 3) -> str:
    """
    Gradient-based optimization loop.
    1. Parse -> 2. Translate -> 3. Evaluate -> 4. Mutate (if needed)
    """
    # 1. Parse & Translate (Tree Transformation)
    ast = await parse_to_ast(req.source_prompt)
    ast = structural_translation(ast, req.target_model)
    current_prompt = reconstruct_prompt(ast)
    
    for i in range(max_iterations):
        # Generate test output using target model
        # For prototype, we use the default LLM wrapper, but in a real system we'd use the specific target API.
        test_input_json = req.test_input + " Return your response in JSON format."
        test_output = await complete(current_prompt, test_input_json)
        
        # 3. Evaluate
        eval_payload = {
            "prompt_id": "migration-test",
            "user_id": "migration",
            "system_prompt": current_prompt,
            "user_input": req.test_input,
            "llm_output": test_output,
            "latency_ms": 0,
            "token_usage": {}
        }
        
        # We run the evaluator logic directly to get the score inline
        eval_sys = "You are a harsh evaluator. Score the LLM output out of 5 for adherence, coherence, and quality. Also provide feedback. Expected hint: " + req.expected_output_hint + ". Return JSON format with keys 'quality', 'adherence', 'coherence', 'feedback'."
        eval_user = f"System Prompt: {current_prompt}\nUser Input: {req.test_input}\nOutput: {test_output}"
        eval_res = await complete(eval_sys, eval_user)
        
        try:
            scores = json.loads(eval_res)
            quality = scores.get("quality", 0)
            feedback = scores.get("feedback", "No feedback provided.")
            
            if quality >= 4.0:
                # Local maximum reached, stop climbing
                return current_prompt
                
            # 4. Mutate (Gradient Descent)
            # Find the failing node based on feedback (naively targeting instructions or constraints)
            if "format" in feedback.lower() or "output" in feedback.lower():
                node = "output_format"
            elif "constraint" in feedback.lower():
                node = "constraints"
            else:
                node = "instructions"
                
            ast = await mutate_node(ast, node, feedback)
            current_prompt = reconstruct_prompt(ast)
            
        except Exception as e:
            # If evaluator fails, return best known prompt
            break
            
    return current_prompt
