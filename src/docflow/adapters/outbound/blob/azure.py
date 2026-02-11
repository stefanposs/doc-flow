"""Azure Blob Storage adapter."""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from docflow.domain.ports import BlobStoragePort

logger = structlog.get_logger()


class AzureBlobStorage(BlobStoragePort):
    """Blob storage backed by Azure Blob Storage.

    Requires: pip install azure-storage-blob
    Config: DOCFLOW_AZURE_CONNECTION_STRING, DOCFLOW_AZURE_CONTAINER
    """

    def __init__(self, connection_string: str, container: str) -> None:
        self._connection_string = connection_string
        self._container_name = container
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            from azure.storage.blob import BlobServiceClient

            service = BlobServiceClient.from_connection_string(self._connection_string)
            self._client = service.get_container_client(self._container_name)
        return self._client

    async def upload(self, key: str, content: bytes, content_type: str = "application/octet-stream") -> str:
        client = self._get_client()
        blob = client.get_blob_client(key)
        await asyncio.to_thread(blob.upload_blob, content, overwrite=True, content_type=content_type)
        logger.info("azure.uploaded", container=self._container_name, key=key, size=len(content))
        return f"az://{self._container_name}/{key}"

    async def download(self, key: str) -> bytes:
        client = self._get_client()
        blob = client.get_blob_client(key)
        stream = await asyncio.to_thread(blob.download_blob)
        content: bytes = await asyncio.to_thread(stream.readall)
        return content

    async def delete(self, key: str) -> None:
        client = self._get_client()
        blob = client.get_blob_client(key)
        await asyncio.to_thread(blob.delete_blob)
        logger.info("azure.deleted", container=self._container_name, key=key)

    async def exists(self, key: str) -> bool:
        client = self._get_client()
        blob = client.get_blob_client(key)
        try:
            await asyncio.to_thread(blob.get_blob_properties)
            return True
        except Exception:
            return False

    async def list_blobs(self, prefix: str = "") -> list[str]:
        client = self._get_client()
        blobs = await asyncio.to_thread(lambda: list(client.list_blobs(name_starts_with=prefix)))
        return [b.name for b in blobs]

    async def get_metadata(self, key: str) -> dict[str, str]:
        client = self._get_client()
        blob = client.get_blob_client(key)
        props = await asyncio.to_thread(blob.get_blob_properties)
        return {
            "content_type": props.content_settings.content_type or "",
            "size": str(props.size or 0),
            "last_modified": str(props.last_modified or ""),
        }

    async def connect(self) -> None:
        self._get_client()
        logger.info("azure.connected", container=self._container_name)

    async def disconnect(self) -> None:
        self._client = None
