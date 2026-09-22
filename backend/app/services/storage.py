"""Photo/logo storage behind an interface, so S3 (or similar) can replace the local disk later.

Security: the real file type is detected from magic bytes (the client's extension and Content-Type are
ignored), size is capped, and the stored name is a random UUID, so a user never controls a path."""

import asyncio
import uuid
from pathlib import Path
from typing import Protocol

from fastapi import UploadFile

from app.core.config import settings
from app.core.errors import AppError

_SIGNATURES: dict[str, tuple[str, str]] = {
    # detected type -> (extension, mime)
    "jpeg": (".jpg", "image/jpeg"),
    "png": (".png", "image/png"),
    "webp": (".webp", "image/webp"),
}


def sniff_image_type(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


class StorageBackend(Protocol):
    async def save_image(self, upload: UploadFile, folder: str = "photos") -> str:
        """Validates and stores an image; returns the public URL."""
        ...

    async def delete(self, url: str | None) -> None: ...


class LocalStorage:
    def __init__(self, root: str, url_prefix: str, max_bytes: int):
        self.root = Path(root).resolve()
        self.url_prefix = url_prefix.rstrip("/")
        self.max_bytes = max_bytes

    async def save_image(self, upload: UploadFile, folder: str = "photos") -> str:
        data = await upload.read(self.max_bytes + 1)
        if len(data) > self.max_bytes:
            raise AppError(
                413,
                "file_too_large",
                f"The image is larger than {self.max_bytes // (1024 * 1024)} MB.",
                fields={"file": "File too large"},
            )
        kind = sniff_image_type(data)
        if kind is None:
            raise AppError(
                422,
                "invalid_file_type",
                "Only JPEG, PNG or WebP images are accepted.",
                fields={"file": "Unsupported image type"},
            )
        name = f"{uuid.uuid4().hex}{_SIGNATURES[kind][0]}"
        target_dir = self.root / folder
        target = target_dir / name

        def _write() -> None:
            target_dir.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)

        await asyncio.to_thread(_write)
        return f"{self.url_prefix}/{folder}/{name}"

    async def delete(self, url: str | None) -> None:
        if not url or not url.startswith(self.url_prefix + "/"):
            return
        relative = url[len(self.url_prefix) + 1 :]
        path = (self.root / relative).resolve()
        if self.root not in path.parents:  # never delete outside the upload root
            return
        await asyncio.to_thread(lambda: path.unlink(missing_ok=True))


def get_storage() -> StorageBackend:
    """FastAPI dependency; tests or a future S3 deployment override it."""
    return LocalStorage(settings.upload_dir, settings.upload_url_prefix, settings.max_upload_bytes)
