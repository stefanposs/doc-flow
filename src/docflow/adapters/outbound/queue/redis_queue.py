"""Redis queue adapter — uses Redis Streams for reliable messaging."""

from __future__ import annotations

import json
import uuid
from typing import Any

import structlog

from docflow.domain.ports import QueuePort

logger = structlog.get_logger()


class RedisQueue(QueuePort):
    """Queue backed by Redis Streams.

    Requires: pip install redis
    Config: DOCFLOW_REDIS_URL
    """

    def __init__(self, redis_url: str = "redis://localhost:6379/0", consumer_group: str = "docflow") -> None:
        self._redis_url = redis_url
        self._consumer_group = consumer_group
        self._consumer_name = f"worker-{uuid.uuid4().hex[:8]}"
        self._redis: Any = None

    async def connect(self) -> None:
        import redis.asyncio as aioredis

        self._redis = aioredis.from_url(self._redis_url, decode_responses=True)  # type: ignore[no-untyped-call]
        logger.info("redis_queue.connected", url=self._redis_url)

    async def disconnect(self) -> None:
        if self._redis:
            await self._redis.aclose()
            self._redis = None

    def _ensure_connected(self) -> Any:
        if self._redis is None:
            msg = "RedisQueue not connected — call connect() first"
            raise RuntimeError(msg)
        return self._redis

    async def enqueue(self, queue_name: str, payload: dict[str, Any]) -> str:
        r = self._ensure_connected()
        msg_id: str = await r.xadd(queue_name, {"data": json.dumps(payload)})
        return msg_id

    async def dequeue(self, queue_name: str, timeout: float = 0) -> tuple[str, dict[str, Any]] | None:
        r = self._ensure_connected()

        # Ensure consumer group exists
        try:
            await r.xgroup_create(queue_name, self._consumer_group, id="0", mkstream=True)
        except Exception:
            pass  # Group already exists

        block_ms = int(timeout * 1000) if timeout > 0 else 100
        results = await r.xreadgroup(
            self._consumer_group,
            self._consumer_name,
            {queue_name: ">"},
            count=1,
            block=block_ms,
        )
        if not results:
            return None

        for _stream, messages in results:
            for msg_id, fields in messages:
                payload = json.loads(fields["data"])
                return msg_id, payload

        return None

    async def acknowledge(self, queue_name: str, message_id: str) -> None:
        r = self._ensure_connected()
        await r.xack(queue_name, self._consumer_group, message_id)

    async def reject(self, queue_name: str, message_id: str) -> None:
        r = self._ensure_connected()
        # Claim back to pending so another consumer can pick it up
        await r.xack(queue_name, self._consumer_group, message_id)
        # Re-enqueue (simplified DLQ strategy)
        # In production, you'd use XCLAIM or a dead-letter queue

    async def queue_length(self, queue_name: str) -> int:
        r = self._ensure_connected()
        length: int = await r.xlen(queue_name)
        return length
