"""Unit tests for the fake storage (verifies fake correctness)."""

from __future__ import annotations

import pytest

from tests.conftest import FakeStorage


class TestFakeStorage:
    """Tests for the in-memory storage fake."""

    @pytest.fixture
    def storage(self) -> FakeStorage:
        return FakeStorage()

    @pytest.mark.asyncio
    async def test_store_and_retrieve(self, storage: FakeStorage) -> None:
        """Should store and retrieve files."""
        await storage.store("test.pdf", b"content")
        result = await storage.retrieve("test.pdf")
        assert result == b"content"

    @pytest.mark.asyncio
    async def test_retrieve_nonexistent_raises(self, storage: FakeStorage) -> None:
        """Should raise FileNotFoundError for missing files."""
        with pytest.raises(FileNotFoundError):
            await storage.retrieve("missing.pdf")

    @pytest.mark.asyncio
    async def test_delete(self, storage: FakeStorage) -> None:
        """Should delete stored files."""
        await storage.store("test.pdf", b"content")
        await storage.delete("test.pdf")
        assert not await storage.exists("test.pdf")

    @pytest.mark.asyncio
    async def test_exists(self, storage: FakeStorage) -> None:
        """Should return correct existence status."""
        assert not await storage.exists("test.pdf")
        await storage.store("test.pdf", b"content")
        assert await storage.exists("test.pdf")
