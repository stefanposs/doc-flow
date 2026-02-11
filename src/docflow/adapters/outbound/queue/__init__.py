"""In-memory queue adapter — zero dependencies, perfect for local dev & testing."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from docflow.domain.ports import QueuePort


class InMemoryQueue(QueuePort):
    """Queue backed by asyncio.Queue — no Redis, no PubSub needed.

    Suitable for single-process local development and testing.
    For production with multiple workers, use RedisQueue.
    """

    def __init__(self) -> None:
        self._queues: dict[str, asyncio.Queue[tuple[str, dict[str, Any]]]] = {}
        self._pending: dict[str, dict[str, dict[str, Any]]] = {}

    def _get_queue(self, name: str) -> asyncio.Queue[tuple[str, dict[str, Any]]]:
        if name not in self._queues:
            self._queues[name] = asyncio.Queue()
            self._pending[name] = {}
        return self._queues[name]

    async def enqueue(self, queue_name: str, payload: dict[str, Any]) -> str:
        msg_id = str(uuid.uuid4())
        q = self._get_queue(queue_name)
        await q.put((msg_id, payload))
        return msg_id

    async def dequeue(self, queue_name: str, timeout: float = 0) -> tuple[str, dict[str, Any]] | None:
        q = self._get_queue(queue_name)
        try:
            if timeout > 0:
                msg_id, payload = await asyncio.wait_for(q.get(), timeout=timeout)
            else:
                msg_id, payload = q.get_nowait()
        except (TimeoutError, asyncio.QueueEmpty):
            return None
        self._pending.setdefault(queue_name, {})[msg_id] = payload
        return msg_id, payload

    async def acknowledge(self, queue_name: str, message_id: str) -> None:
        self._pending.get(queue_name, {}).pop(message_id, None)

    async def reject(self, queue_name: str, message_id: str) -> None:
        payload = self._pending.get(queue_name, {}).pop(message_id, None)
        if payload is not None:
            await self.enqueue(queue_name, payload)

    async def queue_length(self, queue_name: str) -> int:
        q = self._get_queue(queue_name)
        return q.qsize()

    async def connect(self) -> None:
        pass  # nothing to connect

    async def disconnect(self) -> None:
        self._queues.clear()
        self._pending.clear()
