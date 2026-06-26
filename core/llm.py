import json
import logging
import os
from typing import AsyncGenerator

import litellm
from litellm.exceptions import RateLimitError as LiteLLMRateLimitError, ServiceUnavailableError as LiteLLMServiceUnavailableError
from dotenv import load_dotenv
from groq import AsyncGroq, APIError, RateLimitError
from fastapi import HTTPException

load_dotenv()

_AGENTIC_MODEL = os.getenv("LLM_AGENTIC_MODEL", "groq/compound-mini")

logger = logging.getLogger(__name__)


def _primary_model(override: str | None = None) -> str:
    m = override or os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
    if m.startswith("groq/"):
        return m
    return m if "/" in m else f"groq/{m}"


def _fallback_model() -> str:
    return os.getenv("LLM_FALLBACK_MODEL", "openai/gpt-4o-mini")


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
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    async def _stream(chosen_model: str) -> AsyncGenerator[str, None]:
        stream = await litellm.acompletion(
            model=chosen_model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
            stream=True,
        )
        async for chunk in stream:
            content = chunk.choices[0].delta.content if chunk.choices else None
            if content:
                yield content

    primary = _primary_model(model)
    try:
        async for token in _stream(primary):
            yield token
    except (LiteLLMRateLimitError, LiteLLMServiceUnavailableError):
        fallback = _fallback_model()
        logger.warning("llm: groq unavailable, falling back to %s", fallback)
        try:
            async for token in _stream(fallback):
                yield token
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"All LLM providers failed: {e}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM API error: {e}")


async def complete(
    system_prompt: str,
    user_message: str,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    model: str | None = None,
) -> str:
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    primary = _primary_model(model)
    try:
        response = await litellm.acompletion(
            model=primary,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content
    except (LiteLLMRateLimitError, LiteLLMServiceUnavailableError):
        fallback = _fallback_model()
        logger.warning("llm: groq unavailable, falling back to %s", fallback)
        try:
            response = await litellm.acompletion(
                model=fallback,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
            )
            return response.choices[0].message.content
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"All LLM providers failed: {e}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM API error: {e}")


async def complete_multi_turn(
    system_prompt: str,
    messages: list[dict],
    temperature: float = 0.7,
    max_tokens: int = 1024,
) -> str:
    """Multi-turn completion. messages is a list of {role, content} dicts."""
    full_messages = [
        {"role": "system", "content": system_prompt},
        *messages,
    ]
    primary = _primary_model()
    try:
        response = await litellm.acompletion(
            model=primary,
            messages=full_messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content
    except (LiteLLMRateLimitError, LiteLLMServiceUnavailableError):
        fallback = _fallback_model()
        logger.warning("llm: groq unavailable, falling back to %s", fallback)
        try:
            response = await litellm.acompletion(
                model=fallback,
                messages=full_messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
            )
            return response.choices[0].message.content
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"All LLM providers failed: {e}")
    except Exception as e:
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
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    primary = _primary_model(model)
    try:
        response = await litellm.acompletion(
            model=primary,
            messages=messages,
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
    except (LiteLLMRateLimitError, LiteLLMServiceUnavailableError):
        fallback = _fallback_model()
        logger.warning("llm: groq unavailable, falling back to %s", fallback)
        try:
            response = await litellm.acompletion(
                model=fallback,
                messages=messages,
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
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"All LLM providers failed: {e}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM API error: {e}")
