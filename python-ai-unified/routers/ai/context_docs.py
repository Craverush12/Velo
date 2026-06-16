"""/ai/context/* and /ai/embeddings/generate — document context (pgvector RAG).

Source routes (Server 2 core, present on Server 3):
  - POST   /context/upload          -> /ai/context/upload (multipart file)
  - POST   /context/retrieve        -> /ai/context/retrieve
  - GET    /context/{id}/info       -> /ai/context/{id}/info
  - DELETE /context/{id}            -> /ai/context/{id}
  - POST   /embeddings/generate     -> /ai/embeddings/generate

IMPORTANT: these are DOCUMENT-context routes (RAG over uploaded files), distinct
from the conversation-essence /context/* router owned by another agent.

Per merge plan §5 this router uses PostgreSQL (pgvector) for storage/retrieval
and NVIDIA embeddings (shared.embedding_client). The concrete table/DDL of the
canonical Server 3 pgvector store must be verified — see RECONCILE.md.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db import get_session
from shared.embedding_client import generate_embedding, generate_embeddings_batch

router = APIRouter(tags=["context-docs"])

MAX_DOC_BYTES = 10 * 1024 * 1024  # 10 MB
_CHUNK_CHARS = 1200
_CHUNK_OVERLAP = 150


def _chunk_text(content: str) -> list[str]:
    """Split document text into overlapping character chunks for embedding."""
    content = content.strip()
    if not content:
        return []
    chunks: list[str] = []
    start = 0
    length = len(content)
    while start < length:
        end = min(start + _CHUNK_CHARS, length)
        chunks.append(content[start:end])
        if end >= length:
            break
        start = end - _CHUNK_OVERLAP
    return chunks


def _vector_literal(embedding: list[float]) -> str:
    """Render an embedding as a pgvector literal (e.g. '[0.1,0.2,...]')."""
    return "[" + ",".join(f"{x:.8f}" for x in embedding) + "]"


async def _ensure_table(session: AsyncSession) -> None:
    """Best-effort creation of the document-context store.

    The canonical pgvector schema lives in Server 3; this mirrors a faithful
    minimal shape so the endpoints are runnable. See RECONCILE.md.
    """
    try:
        await session.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await session.execute(
            text(
                "CREATE TABLE IF NOT EXISTS ai_context_documents ("
                " id TEXT PRIMARY KEY,"
                " user_id TEXT,"
                " filename TEXT,"
                " chunk_index INT,"
                " chunk_text TEXT,"
                " embedding vector,"
                " created_at TIMESTAMPTZ DEFAULT now()"
                ")"
            )
        )
        await session.commit()
    except Exception:  # noqa: BLE001 - table may already exist with prod schema
        await session.rollback()


@router.post("/context/upload")
async def context_upload(
    file: UploadFile = File(...),
    user_id: str = Form("anonymous"),
    session: AsyncSession = Depends(get_session),
):
    """Upload a file as enhancement context (RAG). Source: POST /context/upload.

    Chunks the file, embeds each chunk via NVIDIA, and stores vectors in
    pgvector keyed by a generated context_id.
    """
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if len(data) > MAX_DOC_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds 10 MB limit")
    try:
        content = data.decode("utf-8")
    except UnicodeDecodeError:
        content = data.decode("utf-8", errors="ignore")

    chunks = _chunk_text(content)
    if not chunks:
        raise HTTPException(status_code=400, detail="File contains no extractable text")

    try:
        embeddings = await generate_embeddings_batch(chunks)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Embedding generation failed: {exc}") from exc

    context_id = uuid.uuid4().hex
    await _ensure_table(session)
    try:
        for idx, (chunk, emb) in enumerate(zip(chunks, embeddings)):
            await session.execute(
                text(
                    "INSERT INTO ai_context_documents"
                    " (id, user_id, filename, chunk_index, chunk_text, embedding)"
                    " VALUES (:id, :uid, :fn, :ci, :ct, CAST(:emb AS vector))"
                ),
                {
                    "id": f"{context_id}:{idx}",
                    "uid": user_id,
                    "fn": file.filename,
                    "ci": idx,
                    "ct": chunk,
                    "emb": _vector_literal(emb),
                },
            )
        await session.commit()
    except Exception as exc:  # noqa: BLE001
        await session.rollback()
        raise HTTPException(status_code=502, detail=f"Failed to persist context: {exc}") from exc

    return {
        "context_id": context_id,
        "filename": file.filename,
        "chunks": len(chunks),
        "user_id": user_id,
    }


class ContextRetrieveRequest(BaseModel):
    context_id: str | None = None
    query: str
    user_id: str = "anonymous"
    top_k: int = 5

    @field_validator("query")
    @classmethod
    def query_not_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("query must not be empty")
        return value

    @field_validator("top_k")
    @classmethod
    def valid_top_k(cls, value: int) -> int:
        return max(1, min(value, 25))


@router.post("/context/retrieve")
async def context_retrieve(
    request: ContextRetrieveRequest,
    session: AsyncSession = Depends(get_session),
):
    """Retrieve stored context for enhancement. Source: POST /context/retrieve.

    Embeds the query and runs a pgvector cosine-distance nearest-neighbor search,
    optionally scoped to a single uploaded context_id.
    """
    try:
        query_emb = await generate_embedding(request.query)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Embedding generation failed: {exc}") from exc

    params = {"emb": _vector_literal(query_emb), "k": request.top_k, "uid": request.user_id}
    scope = "WHERE user_id = :uid"
    if request.context_id:
        scope += " AND id LIKE :cid"
        params["cid"] = f"{request.context_id}:%"

    sql = (
        "SELECT id, filename, chunk_index, chunk_text,"
        " 1 - (embedding <=> CAST(:emb AS vector)) AS score"
        f" FROM ai_context_documents {scope}"
        " ORDER BY embedding <=> CAST(:emb AS vector) ASC"
        " LIMIT :k"
    )
    try:
        result = await session.execute(text(sql), params)
        rows = result.mappings().all()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Context retrieval failed: {exc}") from exc

    return {
        "query": request.query,
        "matches": [
            {
                "id": row["id"],
                "filename": row["filename"],
                "chunk_index": row["chunk_index"],
                "text": row["chunk_text"],
                "score": float(row["score"]) if row["score"] is not None else None,
            }
            for row in rows
        ],
    }


@router.get("/context/{context_id}/info")
async def context_info(
    context_id: str, session: AsyncSession = Depends(get_session)
):
    """Get metadata for a context document. Source: GET /context/{id}/info."""
    try:
        result = await session.execute(
            text(
                "SELECT filename, COUNT(*) AS chunks, MIN(created_at) AS created_at,"
                " MIN(user_id) AS user_id"
                " FROM ai_context_documents WHERE id LIKE :cid GROUP BY filename"
            ),
            {"cid": f"{context_id}:%"},
        )
        row = result.mappings().first()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Lookup failed: {exc}") from exc
    if not row:
        raise HTTPException(status_code=404, detail="Context document not found")
    return {
        "context_id": context_id,
        "filename": row["filename"],
        "chunks": row["chunks"],
        "user_id": row["user_id"],
        "created_at": str(row["created_at"]) if row["created_at"] else None,
    }


@router.delete("/context/{context_id}")
async def context_delete(
    context_id: str, session: AsyncSession = Depends(get_session)
):
    """Delete a stored context document. Source: DELETE /context/{id}."""
    try:
        result = await session.execute(
            text("DELETE FROM ai_context_documents WHERE id LIKE :cid"),
            {"cid": f"{context_id}:%"},
        )
        await session.commit()
    except Exception as exc:  # noqa: BLE001
        await session.rollback()
        raise HTTPException(status_code=502, detail=f"Delete failed: {exc}") from exc
    deleted = getattr(result, "rowcount", 0) or 0
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Context document not found")
    return {"context_id": context_id, "deleted_chunks": deleted}


class EmbeddingsRequest(BaseModel):
    texts: list[str]

    @field_validator("texts")
    @classmethod
    def texts_not_empty(cls, value: list[str]) -> list[str]:
        cleaned = [t for t in (value or []) if isinstance(t, str) and t.strip()]
        if not cleaned:
            raise ValueError("texts must contain at least one non-empty string")
        if len(cleaned) > 256:
            raise ValueError("texts must not exceed 256 items")
        return cleaned


@router.post("/embeddings/generate")
async def embeddings_generate(request: EmbeddingsRequest):
    """Generate text embeddings (internal utility). Source: POST /embeddings/generate.

    Thin wrapper over the shared NVIDIA embedding client.
    """
    try:
        vectors = await generate_embeddings_batch(request.texts)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Embedding generation failed: {exc}") from exc
    dim = len(vectors[0]) if vectors and vectors[0] else 0
    return {"embeddings": vectors, "count": len(vectors), "dimension": dim}
