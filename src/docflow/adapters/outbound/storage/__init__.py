"""Local filesystem storage adapter."""

from __future__ import annotations

import asyncio
from pathlib import Path

import structlog

from docflow.domain.ports import StoragePort

logger = structlog.get_logger()


class LocalStorage(StoragePort):
    """Store files on the local filesystem."""

    def __init__(self, base_path: str = "/data/documents") -> None:
        self._base_path = Path(base_path)
        self._base_path.mkdir(parents=True, exist_ok=True)

    async def store(self, key: str, content: bytes, content_type: str = "application/octet-stream") -> str:
        """Store file to local filesystem."""
        file_path = self._base_path / key
        file_path.parent.mkdir(parents=True, exist_ok=True)

        await asyncio.to_thread(file_path.write_bytes, content)
        logger.info("storage.stored", key=key, size=len(content))

        return str(file_path)

    async def retrieve(self, key: str) -> bytes:
        """Retrieve file from local filesystem."""
        file_path = self._base_path / key

        if not file_path.exists():
            msg = f"File not found: {key}"
            raise FileNotFoundError(msg)

        content: bytes = await asyncio.to_thread(file_path.read_bytes)
        return content

    async def delete(self, key: str) -> None:
        """Delete file from local filesystem."""
        file_path = self._base_path / key

        if file_path.exists():
            await asyncio.to_thread(file_path.unlink)
            logger.info("storage.deleted", key=key)

    async def exists(self, key: str) -> bool:
        """Check if file exists on local filesystem."""
        file_path = self._base_path / key
        return file_path.exists()
