"""Photo/logo storage behind an interface, so S3 (or similar) can replace the local disk later.

Security: the real file type is detected from magic bytes (the client's extension and Content-Type are
ignored), size is capped, and the stored name is a random UUID, so a user never controls a path."""

import asyncio
import io
import struct
import uuid
import zipfile
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


_DOCUMENTS = {"pdf": ".pdf", "docx": ".docx", "xlsx": ".xlsx", "pptx": ".pptx"}
_OOXML_ROOTS = {"word/": "docx", "xl/": "xlsx", "ppt/": "pptx"}


_MAX_ZIP_ENTRIES = 2000  # real Office files have a few dozen; a huge central directory is a stall attack


def _zip_entry_count(data: bytes) -> int | None:
    """Entry count from the end-of-central-directory record, read without parsing the directory."""
    eocd = data.rfind(b"PK\x05\x06", max(0, len(data) - 65_557))
    if eocd < 0 or eocd + 12 > len(data):
        return None
    return struct.unpack("<H", data[eocd + 10 : eocd + 12])[0]


def sniff_document_type(data: bytes) -> str | None:
    """PDF, Word/Excel/PowerPoint (OOXML zip with its content-types part) or an image."""
    if data.startswith(b"%PDF-"):
        return "pdf"
    if data.startswith(b"PK\x03\x04"):
        count = _zip_entry_count(data)
        if count is None or count > _MAX_ZIP_ENTRIES:
            return None
        try:
            names = zipfile.ZipFile(io.BytesIO(data)).namelist()
        except Exception:  # malformed zips raise BadZipFile, UnicodeDecodeError, ValueError, ...
            return None
        if "[Content_Types].xml" in names:
            for prefix, kind in _OOXML_ROOTS.items():
                if any(n.startswith(prefix) for n in names):
                    return kind
        return None
    return sniff_image_type(data)


class StorageBackend(Protocol):
    async def save_image(self, upload: UploadFile, folder: str = "photos") -> str:
        """Validates and stores an image; returns the public URL."""
        ...

    async def save_document(self, upload: UploadFile, folder: str = "documents") -> str:
        """Validates and stores a PDF, Office document or image; returns the public URL."""
        ...

    async def delete(self, url: str | None) -> None: ...


class LocalStorage:
    def __init__(self, root: str, url_prefix: str, max_bytes: int, max_document_bytes: int | None = None):
        self.root = Path(root).resolve()
        self.url_prefix = url_prefix.rstrip("/")
        self.max_bytes = max_bytes
        self.max_document_bytes = max_document_bytes or max_bytes

    async def _read(self, upload: UploadFile, max_bytes: int) -> bytes:
        data = await upload.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise AppError(
                413,
                "file_too_large",
                f"The file is larger than {max_bytes // (1024 * 1024)} MB.",
                fields={"file": "File too large"},
            )
        return data

    async def _write(self, data: bytes, folder: str, ext: str) -> str:
        name = f"{uuid.uuid4().hex}{ext}"
        target_dir = self.root / folder
        target = target_dir / name

        def _write() -> None:
            target_dir.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)

        await asyncio.to_thread(_write)
        return f"{self.url_prefix}/{folder}/{name}"

    async def save_image(self, upload: UploadFile, folder: str = "photos") -> str:
        data = await self._read(upload, self.max_bytes)
        kind = sniff_image_type(data)
        if kind is None:
            raise AppError(
                422,
                "invalid_file_type",
                "Only JPEG, PNG or WebP images are accepted.",
                fields={"file": "Unsupported image type"},
            )
        return await self._write(data, folder, _SIGNATURES[kind][0])

    async def save_document(self, upload: UploadFile, folder: str = "documents") -> str:
        data = await self._read(upload, self.max_document_bytes)
        kind = await asyncio.to_thread(sniff_document_type, data)
        if kind is None:
            raise AppError(
                422,
                "invalid_file_type",
                "Only PDF, Word, Excel, PowerPoint or JPEG/PNG/WebP images are accepted.",
                fields={"file": "Unsupported file type"},
            )
        return await self._write(data, folder, _DOCUMENTS.get(kind) or _SIGNATURES[kind][0])

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
    return LocalStorage(
        settings.upload_dir, settings.upload_url_prefix, settings.max_upload_bytes, settings.max_document_bytes
    )
