"""Upload validation (§42): extension allow-list, size limits, magic bytes."""
from __future__ import annotations

from fastapi import HTTPException, UploadFile, status

from ..config import get_settings

_MAGIC = {
    ".pdf": [b"%PDF"],
    ".docx": [b"PK\x03\x04"],  # zip container
    ".txt": [],
    ".md": [],
}


async def validate_upload(file: UploadFile) -> bytes:
    settings = get_settings()
    filename = file.filename or "upload"
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in settings.allowed_extensions:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            f"File type {ext or '(none)'} is not allowed",
        )
    data = await file.read()
    max_bytes = settings.max_upload_mb * 1024 * 1024
    if len(data) > max_bytes:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"File exceeds the {settings.max_upload_mb} MB limit",
        )
    if not data:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Empty file")
    magics = _MAGIC.get(ext, [])
    if magics and not any(data.startswith(m) for m in magics):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "File content does not match its extension",
        )
    return data
