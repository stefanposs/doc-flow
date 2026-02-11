"""Redis cache adapter."""

from __future__ import annotations

from typing import Any

import structlog

from docflow.domain.ports import CachePort

logger = structlog.get_logger()


class RedisCache(CachePort):
    """Cache backed by Redis.

    Requires: pip install redis
    Config: DOCFLOW_REDIS_URL
    """

    def __init__(self, redis_url: str = "redis://localhost:6379/0") -> None:
        self._redis_url = redis_url
        self._redis: Any = None

    async def connect(self) -> None:
        import redis.asyncio as aioredis

        self._redis = aioredis.from_url(self._redis_url, decode_responses=True)  # type: ignore[no-untyped-call]
        logger.info("redis_cache.connected", url=self._redis_url)

    async def disconnect(self) -> None:
        if self._redis:
            await self._redis.aclose()
            self._redis = None

    def _ensure_connected(self) -> Any:
        if self._redis is None:
            msg = "RedisCache not connected — call connect() first"
            raise RuntimeError(msg)
        return self._redis

    async def get(self, key: str) -> str | None:
        r = self._ensure_connected()
        result: str | None = await r.get(key)
        return result

    async def set(self, key: str, value: str, ttl: int | None = None) -> None:
        r = self._ensure_connected()
        if ttl:
            await r.setex(key, ttl, value)
        else:
            await r.set(key, value)

    async def delete(self, key: str) -> None:
        r = self._ensure_connected()
        await r.delete(key)

    async def exists(self, key: str) -> bool:
        r = self._ensure_connected()
        result: int = await r.exists(key)
        return result > 0

    async def increment(self, key: str) -> int:
        r = self._ensure_connected()
        result: int = await r.incr(key)
        return result
