"""Google Cloud Storage blob adapter."""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from docflow.domain.ports import BlobStoragePort

logger = structlog.get_logger()


class GCSBlobStorage(BlobStoragePort):
    """Blob storage backed by Google Cloud Storage.

    Requires: pip install google-cloud-storage
    Config: DOCFLOW_GCS_BUCKET, DOCFLOW_GCS_PROJECT
    Uses Application Default Credentials (ADC).
    """

    def __init__(self, bucket: str, project: str | None = None) -> None:
        self._bucket_name = bucket
        self._project = project
        self._client: Any = None
        self._bucket: Any = None

    def _get_bucket(self) -> Any:
        if self._bucket is None:
            from google.cloud import storage

            self._client = storage.Client(project=self._project)
            self._bucket = self._client.bucket(self._bucket_name)
        return self._bucket

    async def upload(self, key: str, content: bytes, content_type: str = "application/octet-stream") -> str:
        bucket = self._get_bucket()
        blob = bucket.blob(key)
        await asyncio.to_thread(blob.upload_from_string, content, content_type=content_type)
        logger.info("gcs.uploaded", bucket=self._bucket_name, key=key, size=len(content))
        return f"gs://{self._bucket_name}/{key}"

    async def download(self, key: str) -> bytes:
        bucket = self._get_bucket()
        blob = bucket.blob(key)
        content: bytes = await asyncio.to_thread(blob.download_as_bytes)
        return content

    async def delete(self, key: str) -> None:
        bucket = self._get_bucket()
        blob = bucket.blob(key)
        await asyncio.to_thread(blob.delete)
        logger.info("gcs.deleted", bucket=self._bucket_name, key=key)

    async def exists(self, key: str) -> bool:
        bucket = self._get_bucket()
        blob = bucket.blob(key)
        result: bool = await asyncio.to_thread(blob.exists)
        return result

    async def list_blobs(self, prefix: str = "") -> list[str]:
        bucket = self._get_bucket()
        blobs = await asyncio.to_thread(lambda: list(bucket.list_blobs(prefix=prefix)))
        return [b.name for b in blobs]

    async def get_metadata(self, key: str) -> dict[str, str]:
        bucket = self._get_bucket()
        blob = bucket.blob(key)
        await asyncio.to_thread(blob.reload)
        return {
            "content_type": blob.content_type or "",
            "size": str(blob.size or 0),
            "last_modified": str(blob.updated or ""),
        }

    async def connect(self) -> None:
        self._get_bucket()
        logger.info("gcs.connected", bucket=self._bucket_name)

    async def disconnect(self) -> None:
        self._client = None
        self._bucket = None
