"""File upload business logic."""

from pathlib import Path
import uuid

from fastapi import HTTPException, UploadFile

from app.core.config import settings
from app.schemas.file import UploadedFileOut


def _uploads_dir() -> Path:
    path = Path(settings.UPLOAD_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _is_allowed_mime(content_type: str | None, filename: str | None) -> bool:
    ext = Path(filename or "").suffix.lower()
    if ext and ext in settings.ALLOWED_UPLOAD_EXTENSIONS:
        return True
    if not content_type:
        return False
    if content_type in settings.ALLOWED_UPLOAD_MIME_TYPES:
        return True
    return content_type.startswith("text/")


def _safe_extension(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext and len(ext) <= 10:
        return ext
    return ""


async def upload_files(files: list[UploadFile]) -> list[UploadedFileOut]:
    if not files:
        raise HTTPException(status_code=400, detail={"error": "invalid_request", "message": "No files uploaded"})

    uploads = _uploads_dir()
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    saved: list[UploadedFileOut] = []

    for file in files:
        if not _is_allowed_mime(file.content_type, file.filename):
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "invalid_file_type",
                    "message": f"Unsupported file type: {file.content_type or 'unknown'}",
                },
            )

        payload = await file.read()
        size = len(payload)
        if size == 0:
            raise HTTPException(
                status_code=400,
                detail={"error": "invalid_file", "message": f"Empty file: {file.filename}"},
            )
        if size > max_bytes:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "file_too_large",
                    "message": f"File exceeds {settings.MAX_UPLOAD_MB}MB limit: {file.filename}",
                },
            )

        ext = _safe_extension(file.filename or "")
        stored_name = f"upload_{uuid.uuid4().hex}{ext}"
        path = uploads / stored_name
        path.write_bytes(payload)

        saved.append(
            UploadedFileOut(
                filename=file.filename or stored_name,
                content_type=file.content_type or "application/octet-stream",
                size=size,
                url=f"{settings.BACKEND_PUBLIC_URL.rstrip('/')}/uploads/{stored_name}",
            )
        )

    return saved
