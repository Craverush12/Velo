from __future__ import annotations

import json
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

router = APIRouter(prefix="/uploads", tags=["uploads"])

MAX_UPLOAD_BYTES = 15 * 1024 * 1024
MAX_TEXT_PREVIEW_CHARS = 12_000

_BASE_DIR = (Path(__file__).parent.parent / "storage" / "uploads").resolve()
_USER_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._ -]+")

_TEXT_MIME_TYPES = {
    "text/plain",
    "text/markdown",
    "text/csv",
    "application/json",
}

_DOCUMENT_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

_IMAGE_MIME_TYPES = {
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/gif",
}

_TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".csv", ".json"}
_DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".xlsx"}
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
_MODEL_EXTENSIONS = {".glb", ".gltf", ".obj", ".fbx", ".stl", ".blend"}

_ALLOWED_EXTENSIONS = _TEXT_EXTENSIONS | _DOCUMENT_EXTENSIONS | _IMAGE_EXTENSIONS


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_user_id(user_id: str) -> str:
    clean = (user_id or "").strip()
    if not _USER_ID_RE.fullmatch(clean):
        raise HTTPException(
            status_code=422,
            detail={
                "status": "rejected",
                "reason": "invalid_user_id",
                "message": "user_id must match ^[A-Za-z0-9_-]{1,64}$",
            },
        )
    return clean


def _sanitize_filename(filename: str | None) -> str:
    raw = (filename or "upload").strip().replace("\\", "/").split("/")[-1]
    safe = _SAFE_FILENAME_RE.sub("_", raw).strip(" .")
    return safe[:160] or "upload"


def _category_for(content_type: str, extension: str) -> str | None:
    mime = content_type.lower().split(";", 1)[0].strip()
    ext = extension.lower()
    if mime in _TEXT_MIME_TYPES or ext in _TEXT_EXTENSIONS:
        return "text"
    if mime in _IMAGE_MIME_TYPES or ext in _IMAGE_EXTENSIONS:
        return "image"
    if mime in _DOCUMENT_MIME_TYPES or ext in _DOCUMENT_EXTENSIONS:
        return "document"
    return None


def _blocked_reason(content_type: str, extension: str) -> str | None:
    mime = content_type.lower().split(";", 1)[0].strip()
    ext = extension.lower()
    if mime.startswith("video/") or ext in _VIDEO_EXTENSIONS:
        return "video_uploads_are_not_supported"
    if mime.startswith("model/") or ext in _MODEL_EXTENSIONS:
        return "3d_uploads_are_not_supported"
    if mime == "application/octet-stream" and ext not in _ALLOWED_EXTENSIONS:
        return "binary_upload_requires_an_allowed_extension"
    return None


def _metadata_path(user_id: str, upload_id: str) -> Path:
    user_dir = (_BASE_DIR / user_id).resolve()
    path = (user_dir / upload_id / "metadata.json").resolve()
    if not path.is_relative_to(_BASE_DIR):
        raise HTTPException(status_code=400, detail="resolved upload path escaped storage root")
    return path


def _find_metadata_path(upload_id: str, user_id: str | None = None) -> Path:
    _validate_upload_id(upload_id)
    if user_id:
        path = _metadata_path(_validate_user_id(user_id), upload_id)
        if path.exists():
            return path
    else:
        for path in _BASE_DIR.glob(f"*/{upload_id}/metadata.json"):
            resolved = path.resolve()
            if resolved.is_relative_to(_BASE_DIR):
                return resolved
    raise HTTPException(
        status_code=404,
        detail={
            "status": "missing",
            "reason": "upload_not_found",
            "upload_id": upload_id,
        },
    )


def _validate_upload_id(upload_id: str) -> None:
    try:
        uuid.UUID(upload_id)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail={
                "status": "rejected",
                "reason": "invalid_upload_id",
                "message": "upload_id must be a UUID",
            },
        ) from None


def _text_preview(data: bytes, category: str, extension: str) -> tuple[str, bool]:
    if category != "text" and extension.lower() not in _TEXT_EXTENSIONS:
        return "", False
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("utf-8", errors="replace")
    text = " ".join(text.replace("\r", "\n").split())
    return text[:MAX_TEXT_PREVIEW_CHARS], bool(text)


def _read_metadata(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise HTTPException(status_code=500, detail="stored upload metadata is invalid")
    return payload


@router.post("")
async def create_upload(
    file: UploadFile = File(...),
    user_id: str = Form(...),
) -> dict[str, Any]:
    clean_user_id = _validate_user_id(user_id)
    filename = _sanitize_filename(file.filename)
    extension = Path(filename).suffix.lower()
    content_type = (file.content_type or "application/octet-stream").split(";", 1)[0].strip().lower()

    blocked_reason = _blocked_reason(content_type, extension)
    if blocked_reason:
        raise HTTPException(
            status_code=415,
            detail={
                "status": "rejected",
                "reason": blocked_reason,
                "filename": filename,
                "content_type": content_type,
                "category": "blocked",
            },
        )

    category = _category_for(content_type, extension)
    if category is None:
        raise HTTPException(
            status_code=415,
            detail={
                "status": "rejected",
                "reason": "unsupported_upload_type",
                "filename": filename,
                "content_type": content_type,
                "allowed_categories": ["text", "image", "document"],
            },
        )

    payload = await file.read(MAX_UPLOAD_BYTES + 1)
    size_bytes = len(payload)
    if size_bytes > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail={
                "status": "rejected",
                "reason": "upload_too_large",
                "max_size_bytes": MAX_UPLOAD_BYTES,
                "filename": filename,
            },
        )

    upload_id = str(uuid.uuid4())
    upload_dir = (_BASE_DIR / clean_user_id / upload_id).resolve()
    if not upload_dir.is_relative_to(_BASE_DIR):
        raise HTTPException(status_code=400, detail="resolved upload path escaped storage root")
    upload_dir.mkdir(parents=True, exist_ok=True)

    original_path = upload_dir / "original"
    original_path.write_bytes(payload)

    preview, has_text_preview = _text_preview(payload, category, extension)
    metadata: dict[str, Any] = {
        "upload_id": upload_id,
        "user_id": clean_user_id,
        "filename": filename,
        "content_type": content_type,
        "media_type": content_type,
        "category": category,
        "kind": category,
        "size_bytes": size_bytes,
        "text_preview": preview,
        "has_text_preview": has_text_preview,
        "status": "ready",
        "created_at": _now_iso(),
        "storage": {
            "original_path": str(original_path),
            "metadata_path": str(upload_dir / "metadata.json"),
        },
        "context": {
            "usable_as_realtime_context": category in {"text", "image", "document"},
            "future_context_summary": (
                preview[:500] if preview else f"{category} upload named {filename}"
            ),
        },
    }

    with open(upload_dir / "metadata.json", "w", encoding="utf-8") as handle:
        json.dump(metadata, handle, indent=2)
        handle.write("\n")

    return metadata


@router.get("/{upload_id}")
def get_upload(upload_id: str, user_id: str | None = None) -> dict[str, Any]:
    return _read_metadata(_find_metadata_path(upload_id, user_id))


@router.delete("/{upload_id}")
def delete_upload(upload_id: str, user_id: str | None = None) -> dict[str, Any]:
    metadata_path = _find_metadata_path(upload_id, user_id)
    upload_dir = metadata_path.parent
    metadata = _read_metadata(metadata_path)
    shutil.rmtree(upload_dir)
    return {
        "upload_id": upload_id,
        "filename": metadata.get("filename", ""),
        "status": "deleted",
    }
