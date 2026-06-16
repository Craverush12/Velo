from fastapi import APIRouter
import httpx
import time

router = APIRouter(prefix="/benchmarks", tags=["Benchmarks"])

_models_cache = None
_cache_timestamp = 0
CACHE_TTL = 3600  # 1 hour cache

KNOWN_BENCHMARKS = {
    "openai/gpt-4o": {"mmlu": 88.7, "humaneval": 90.2, "elo": 1287},
    "openai/gpt-4o-2024-08-06": {"mmlu": 88.7, "humaneval": 90.2, "elo": 1287},
    "openai/gpt-4o-mini": {"mmlu": 82.0, "humaneval": 87.0, "elo": 1240},
    "anthropic/claude-3.5-sonnet": {"mmlu": 88.3, "humaneval": 92.0, "elo": 1279},
    "anthropic/claude-3.5-sonnet:beta": {"mmlu": 88.3, "humaneval": 92.0, "elo": 1279},
    "anthropic/claude-3-opus": {"mmlu": 86.8, "humaneval": 84.9, "elo": 1248},
    "meta-llama/llama-3.1-405b-instruct": {"mmlu": 88.6, "humaneval": 89.0, "elo": 1260},
    "meta-llama/llama-3.1-70b-instruct": {"mmlu": 82.0, "humaneval": 81.7, "elo": 1210},
    "meta-llama/llama-3.3-70b-instruct": {"mmlu": 84.5, "humaneval": 85.0, "elo": 1225},
    "google/gemini-pro-1.5": {"mmlu": 81.9, "humaneval": 84.1, "elo": 1250},
    "google/gemini-flash-1.5": {"mmlu": 78.9, "humaneval": 74.0, "elo": 1220},
    "mistralai/mixtral-8x22b-instruct": {"mmlu": 77.3, "humaneval": 75.0, "elo": 1150},
    "cohere/command-r-plus": {"mmlu": 82.5, "humaneval": 76.5, "elo": 1160},
}

@router.get("/")
async def get_live_benchmarks():
    global _models_cache, _cache_timestamp
    
    current_time = time.time()
    if _models_cache and (current_time - _cache_timestamp < CACHE_TTL):
        return {"data": _models_cache, "cached": True}
        
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get("https://openrouter.ai/api/v1/models")
            response.raise_for_status()
            data = response.json()
            
            models = data.get("data", [])
            for m in models:
                mid = m.get("id", "")
                bench = KNOWN_BENCHMARKS.get(mid, {})
                m["mmlu"] = bench.get("mmlu")
                m["humaneval"] = bench.get("humaneval")
                m["elo"] = bench.get("elo")
                
            _models_cache = models
            _cache_timestamp = current_time
            return {"data": _models_cache, "cached": False}
        except Exception as e:
            if _models_cache:
                return {"data": _models_cache, "cached": True, "error": str(e)}
            return {"error": str(e), "data": []}
