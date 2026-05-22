import json
import os
from typing import AsyncGenerator

from dotenv import load_dotenv
from groq import AsyncGroq, APIError, RateLimitError
from fastapi import HTTPException

load_dotenv()

_MODEL = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
_AGENTIC_MODEL = os.getenv("LLM_AGENTIC_MODEL", "groq/compound-mini")


def _client() -> AsyncGroq:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="GROQ_API_KEY is not configured")
    return AsyncGroq(api_key=api_key)


async def stream_completion(
    system_prompt: str,
    user_message: str,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    usage_sink: dict | None = None,
    model: str | None = None,
) -> AsyncGenerator[str, None]:
    try:
        stream = await _client().chat.completions.create(
            model=model or _MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
            stream=True,
        )
        async for chunk in stream:
            content = chunk.choices[0].delta.content if chunk.choices else None
            if content:
                yield content
    except RateLimitError as e:
        raise HTTPException(status_code=429, detail=f"Rate limit hit: {e}")
    except APIError as e:
        raise HTTPException(status_code=502, detail=f"LLM API error: {e}")


async def complete(
    system_prompt: str,
    user_message: str,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    model: str | None = None,
) -> str:
    try:
        response = await _client().chat.completions.create(
            model=model or _MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content
    except RateLimitError as e:
        raise HTTPException(status_code=429, detail=f"Rate limit hit: {e}")
    except APIError as e:
        raise HTTPException(status_code=502, detail=f"LLM API error: {e}")


async def complete_multi_turn(
    system_prompt: str,
    messages: list[dict],
    temperature: float = 0.7,
    max_tokens: int = 1024,
) -> str:
    """Multi-turn completion. messages is a list of {role, content} dicts."""
    try:
        response = await _client().chat.completions.create(
            model=_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                *messages,
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content
    except RateLimitError as e:
        raise HTTPException(status_code=429, detail=f"Rate limit hit: {e}")
    except APIError as e:
        raise HTTPException(status_code=502, detail=f"LLM API error: {e}")


AGENTIC_TOOLS = {"enabled_tools": ["web_search", "code_interpreter", "visit_website"]}


async def agentic_stream(
    system_prompt: str,
    user_message: str,
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> AsyncGenerator[dict, None]:
    """Streaming completion using the Groq Compound agentic model with tools.
    Yields typed dicts: {type: tool_use|content|done, ...}
    """
    try:
        stream = await _client().chat.completions.create(
            model=_AGENTIC_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            stop=None,
            extra_body={"compound_custom": {"tools": AGENTIC_TOOLS}},
        )
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            tool_calls = getattr(delta, "tool_calls", None)
            if tool_calls:
                for tc in tool_calls:
                    fn = getattr(tc, "function", None)
                    if fn:
                        name = getattr(fn, "name", None)
                        if name:
                            yield {
                                "type": "tool_use",
                                "tool": name,
                                "input": getattr(fn, "arguments", "") or "",
                            }
            if delta.content:
                yield {"type": "content", "text": delta.content}
        yield {"type": "done"}
    except RateLimitError as e:
        raise HTTPException(status_code=429, detail=f"Rate limit hit: {e}")
    except APIError as e:
        raise HTTPException(status_code=502, detail=f"LLM API error: {e}")


async def complete_with_usage(
    system_prompt: str,
    user_message: str,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    model: str | None = None,
) -> tuple[str, dict]:
    """Non-streaming completion that returns (content, usage_dict).
    usage_dict keys: prompt_tokens, completion_tokens, total_tokens."""
    try:
        response = await _client().chat.completions.create(
            model=model or _MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        usage = {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens,
        }
        return response.choices[0].message.content, usage
    except RateLimitError as e:
        raise HTTPException(status_code=429, detail=f"Rate limit hit: {e}")
    except APIError as e:
        raise HTTPException(status_code=502, detail=f"LLM API error: {e}")
