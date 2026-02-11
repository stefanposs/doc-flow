"""In-memory cache adapter — dict-based, no Redis needed."""

from __future__ import annotations

import time

from docflow.domain.ports import CachePort


class InMemoryCache(CachePort):
    """Cache backed by a Python dict with TTL support.

    For production, use RedisCache.
    """

    def __init__(self) -> None:
        self._store: dict[str, tuple[str, float | None]] = {}  # key → (value, expires_at)

    def _is_expired(self, key: str) -> bool:
        if key not in self._store:
            return True
        _, expires_at = self._store[key]
        if expires_at is not None and time.monotonic() > expires_at:
            del self._store[key]
            return True
        return False

    async def get(self, key: str) -> str | None:
        if self._is_expired(key):
            return None
        return self._store[key][0]

    async def set(self, key: str, value: str, ttl: int | None = None) -> None:
        expires_at = time.monotonic() + ttl if ttl else None
        self._store[key] = (value, expires_at)

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)

    async def exists(self, key: str) -> bool:
        return not self._is_expired(key)

    async def increment(self, key: str) -> int:
        current = await self.get(key)
        new_val = int(current) + 1 if current else 1
        # Keep existing TTL
        existing_expires = self._store.get(key, (None, None))[1]
        self._store[key] = (str(new_val), existing_expires)
        return new_val

    async def connect(self) -> None:
        pass

    async def disconnect(self) -> None:
        self._store.clear()
