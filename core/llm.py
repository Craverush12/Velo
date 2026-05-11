import os
from typing import AsyncGenerator

from dotenv import load_dotenv
from groq import AsyncGroq, APIError, RateLimitError
from fastapi import HTTPException

load_dotenv()

_MODEL = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")


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
) -> AsyncGenerator[str, None]:
    """Yields content chunks. If usage_sink dict is provided, populates it with
    token counts after streaming completes."""
    try:
        create_kwargs = dict(
            model=_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
            stream=True,
        )
        if usage_sink is not None:
            create_kwargs["stream_options"] = {"include_usage": True}

        stream = await _client().chat.completions.create(**create_kwargs)
        async for chunk in stream:
            content = chunk.choices[0].delta.content if chunk.choices else None
            if content:
                yield content
            if usage_sink is not None and getattr(chunk, "usage", None):
                usage_sink.update(
                    {
                        "prompt_tokens": chunk.usage.prompt_tokens,
                        "completion_tokens": chunk.usage.completion_tokens,
                        "total_tokens": chunk.usage.total_tokens,
                    }
                )
    except RateLimitError as e:
        raise HTTPException(status_code=429, detail=f"Rate limit hit: {e}")
    except APIError as e:
        raise HTTPException(status_code=502, detail=f"LLM API error: {e}")


async def complete(
    system_prompt: str,
    user_message: str,
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> str:
    try:
        response = await _client().chat.completions.create(
            model=_MODEL,
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


async def complete_with_usage(
    system_prompt: str,
    user_message: str,
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> tuple[str, dict]:
    """Non-streaming completion that returns (content, usage_dict).
    usage_dict keys: prompt_tokens, completion_tokens, total_tokens."""
    try:
        response = await _client().chat.completions.create(
            model=_MODEL,
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
