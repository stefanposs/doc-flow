"""Unit tests for the cleanup processor."""

from __future__ import annotations

import pytest

from docflow.adapters.outbound.processors.cleanup import CleanupProcessor


class TestCleanupProcessor:
    """Tests for CleanupProcessor."""

    @pytest.fixture
    def processor(self) -> CleanupProcessor:
        return CleanupProcessor()

    @pytest.mark.asyncio
    async def test_normalize_line_endings(self, processor: CleanupProcessor) -> None:
        """Should normalize \\r\\n to \\n."""
        text = "Hello\r\nWorld\rFoo"
        result = await processor.process(text)
        assert "\r" not in result
        assert result == "Hello\nWorld\nFoo"

    @pytest.mark.asyncio
    async def test_collapse_newlines(self, processor: CleanupProcessor) -> None:
        """Should collapse 3+ newlines to 2."""
        text = "Hello\n\n\n\n\nWorld"
        result = await processor.process(text)
        assert result == "Hello\n\nWorld"

    @pytest.mark.asyncio
    async def test_remove_null_bytes(self, processor: CleanupProcessor) -> None:
        """Should remove NULL and control characters."""
        text = "Hello\x00World\x01Foo"
        result = await processor.process(text)
        assert "\x00" not in result
        assert "\x01" not in result
        assert result == "HelloWorldFoo"

    @pytest.mark.asyncio
    async def test_fix_hyphenation(self, processor: CleanupProcessor) -> None:
        """Should rejoin hyphenated words at line breaks."""
        text = "docu-\nment"
        result = await processor.process(text)
        assert "document" in result

    @pytest.mark.asyncio
    async def test_strip_trailing_whitespace(self, processor: CleanupProcessor) -> None:
        """Should strip trailing whitespace from lines."""
        text = "Hello   \nWorld  "
        result = await processor.process(text)
        assert result == "Hello\nWorld"

    @pytest.mark.asyncio
    async def test_name(self, processor: CleanupProcessor) -> None:
        """Should return correct name."""
        assert processor.name == "cleanup"
