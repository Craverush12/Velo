import math
import re
from collections import Counter
from typing import Iterable


_TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)?")
_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "better",
    "for",
    "from",
    "how",
    "i",
    "in",
    "into",
    "is",
    "it",
    "need",
    "of",
    "on",
    "or",
    "prompt",
    "the",
    "this",
    "to",
    "with",
    "write",
}


def _normalize_token(token: str) -> str:
    token = token.lower().replace("_", "-")
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 5 and token.endswith("ing"):
        return token[:-3]
    if len(token) > 4 and token.endswith("s"):
        return token[:-1]
    return token


def tokenize(text: str) -> list[str]:
    """Tokenize text for deterministic local semantic retrieval."""
    tokens: list[str] = []
    for match in _TOKEN_RE.finditer(text or ""):
        token = _normalize_token(match.group(0))
        tokens.append(token)
        if "-" in token:
            tokens.extend(_normalize_token(part) for part in token.split("-"))
    return [token for token in tokens if token and token not in _STOPWORDS]


def embed_text(text: str) -> dict[str, float]:
    """Return a normalized sparse term-frequency vector."""
    counts = Counter(tokenize(text))
    norm = math.sqrt(sum(count * count for count in counts.values()))
    if not norm:
        return {}
    return {token: count / norm for token, count in counts.items()}


def cosine_similarity(left: dict[str, float], right: dict[str, float]) -> float:
    if not left or not right:
        return 0.0
    if len(left) > len(right):
        left, right = right, left
    return sum(weight * right.get(token, 0.0) for token, weight in left.items())


def _context_text(item: dict) -> str:
    parts: Iterable[str | None] = (
        item.get("summary"),
        item.get("intent"),
        item.get("domain"),
        item.get("framework"),
        item.get("prompt_mode"),
        item.get("original_prompt"),
    )
    return " ".join(str(part) for part in parts if part)


def retrieve_relevant_context(
    query: str,
    contexts: list[dict],
    top_k: int = 5,
    min_score: float = 0.0,
) -> list[dict]:
    """Rank prior context entries by deterministic cosine similarity.

    This is the local file-backed retrieval path. The function accepts and
    returns plain dicts so a pgvector-backed store can later preserve the same
    call boundary.
    """
    if top_k <= 0 or not contexts:
        return []

    query_vector = embed_text(query)
    if not query_vector:
        return contexts[:top_k]

    ranked: list[tuple[float, int, dict]] = []
    for index, item in enumerate(contexts):
        score = cosine_similarity(query_vector, embed_text(_context_text(item)))
        if score > min_score:
            ranked.append((score, index, item))

    ranked.sort(key=lambda row: (-row[0], row[1]))
    selected = [item for _, _, item in ranked[:top_k]]
    if len(selected) >= top_k:
        return selected

    selected_ids = {id(item) for item in selected}
    for item in contexts:
        if id(item) not in selected_ids:
            selected.append(item)
            if len(selected) >= top_k:
                break
    return selected
