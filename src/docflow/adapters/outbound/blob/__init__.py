"""In-memory blob storage adapter — dict-based, zero dependencies."""

from __future__ import annotations

from docflow.domain.ports import BlobStoragePort


class InMemoryBlobStorage(BlobStoragePort):
    """Blob storage backed by a Python dict.

    Perfect for local development and testing.
    For production, use S3BlobStorage, GCSBlobStorage, or AzureBlobStorage.
    """

    def __init__(self) -> None:
        self._blobs: dict[str, tuple[bytes, str]] = {}  # key → (content, content_type)

    async def upload(self, key: str, content: bytes, content_type: str = "application/octet-stream") -> str:
        self._blobs[key] = (content, content_type)
        return f"memory://{key}"

    async def download(self, key: str) -> bytes:
        if key not in self._blobs:
            msg = f"Blob not found: {key}"
            raise FileNotFoundError(msg)
        return self._blobs[key][0]

    async def delete(self, key: str) -> None:
        self._blobs.pop(key, None)

    async def exists(self, key: str) -> bool:
        return key in self._blobs

    async def list_blobs(self, prefix: str = "") -> list[str]:
        return [k for k in self._blobs if k.startswith(prefix)]

    async def get_metadata(self, key: str) -> dict[str, str]:
        if key not in self._blobs:
            msg = f"Blob not found: {key}"
            raise FileNotFoundError(msg)
        content, content_type = self._blobs[key]
        return {
            "content_type": content_type,
            "size": str(len(content)),
        }

    async def connect(self) -> None:
        pass

    async def disconnect(self) -> None:
        self._blobs.clear()
