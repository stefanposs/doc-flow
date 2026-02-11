"""S3-compatible blob storage adapter (AWS S3, MinIO, etc.)."""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from docflow.domain.ports import BlobStoragePort

logger = structlog.get_logger()


class S3BlobStorage(BlobStoragePort):
    """Blob storage backed by AWS S3 or any S3-compatible service (MinIO, R2, etc.).

    Requires: pip install boto3 (or uv add boto3)
    Config: DOCFLOW_S3_BUCKET, DOCFLOW_S3_ENDPOINT, DOCFLOW_S3_REGION
    """

    def __init__(
        self,
        bucket: str,
        endpoint_url: str | None = None,
        region: str = "eu-central-1",
        access_key: str | None = None,
        secret_key: str | None = None,
    ) -> None:
        self._bucket = bucket
        self._endpoint_url = endpoint_url or None
        self._region = region
        self._access_key = access_key or None
        self._secret_key = secret_key or None
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            import boto3

            kwargs: dict[str, Any] = {"region_name": self._region}
            if self._endpoint_url:
                kwargs["endpoint_url"] = self._endpoint_url
            if self._access_key and self._secret_key:
                kwargs["aws_access_key_id"] = self._access_key
                kwargs["aws_secret_access_key"] = self._secret_key
            self._client = boto3.client("s3", **kwargs)
        return self._client

    async def upload(self, key: str, content: bytes, content_type: str = "application/octet-stream") -> str:
        client = self._get_client()
        await asyncio.to_thread(
            client.put_object,
            Bucket=self._bucket,
            Key=key,
            Body=content,
            ContentType=content_type,
        )
        logger.info("s3.uploaded", bucket=self._bucket, key=key, size=len(content))
        return f"s3://{self._bucket}/{key}"

    async def download(self, key: str) -> bytes:
        client = self._get_client()
        response = await asyncio.to_thread(
            client.get_object,
            Bucket=self._bucket,
            Key=key,
        )
        content: bytes = response["Body"].read()
        return content

    async def delete(self, key: str) -> None:
        client = self._get_client()
        await asyncio.to_thread(
            client.delete_object,
            Bucket=self._bucket,
            Key=key,
        )
        logger.info("s3.deleted", bucket=self._bucket, key=key)

    async def exists(self, key: str) -> bool:
        client = self._get_client()
        try:
            await asyncio.to_thread(
                client.head_object,
                Bucket=self._bucket,
                Key=key,
            )
            return True
        except client.exceptions.ClientError:
            return False

    async def list_blobs(self, prefix: str = "") -> list[str]:
        client = self._get_client()
        response = await asyncio.to_thread(
            client.list_objects_v2,
            Bucket=self._bucket,
            Prefix=prefix,
        )
        return [obj["Key"] for obj in response.get("Contents", [])]

    async def get_metadata(self, key: str) -> dict[str, str]:
        client = self._get_client()
        response = await asyncio.to_thread(
            client.head_object,
            Bucket=self._bucket,
            Key=key,
        )
        return {
            "content_type": response.get("ContentType", ""),
            "size": str(response.get("ContentLength", 0)),
            "last_modified": str(response.get("LastModified", "")),
        }

    async def connect(self) -> None:
        self._get_client()
        logger.info("s3.connected", bucket=self._bucket)

    async def disconnect(self) -> None:
        self._client = None
