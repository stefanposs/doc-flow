"""Unit tests for output formatters."""

from __future__ import annotations

import json

import pytest

from docflow.adapters.outbound.formatters.json_fmt import JSONFormatter
from docflow.adapters.outbound.formatters.markdown import MarkdownFormatter
from docflow.adapters.outbound.formatters.plaintext import PlainTextFormatter
from docflow.domain.models import OutputFormat


class TestMarkdownFormatter:
    """Tests for MarkdownFormatter."""

    @pytest.mark.asyncio()
    async def test_format_basic_text(self) -> None:
        """Should output text as markdown."""
        formatter = MarkdownFormatter(include_metadata=False)
        result = await formatter.format("Hello world")
        assert result.format == OutputFormat.MARKDOWN
        assert "Hello world" in result.content

    @pytest.mark.asyncio()
    async def test_format_with_metadata(self) -> None:
        """Should include YAML front matter when metadata provided."""
        formatter = MarkdownFormatter(include_metadata=True)
        result = await formatter.format("Content", metadata={"title": "My Doc", "author": "Test"})
        assert "---" in result.content
        assert "title: My Doc" in result.content
        assert "author: Test" in result.content

    @pytest.mark.asyncio()
    async def test_uppercase_lines_become_headers(self) -> None:
        """Should convert ALL CAPS lines to markdown headers."""
        formatter = MarkdownFormatter(include_metadata=False)
        result = await formatter.format("INTRODUCTION\n\nSome content here.")
        assert "## Introduction" in result.content

    def test_output_format_property(self) -> None:
        """Should return MARKDOWN."""
        assert MarkdownFormatter().output_format == OutputFormat.MARKDOWN


class TestJSONFormatter:
    """Tests for JSONFormatter."""

    @pytest.mark.asyncio()
    async def test_format_as_json(self) -> None:
        """Should output valid JSON with content and metadata."""
        formatter = JSONFormatter()
        result = await formatter.format("Hello", metadata={"title": "Test"})
        data = json.loads(result.content)
        assert data["content"] == "Hello"
        assert data["metadata"]["title"] == "Test"

    def test_output_format_property(self) -> None:
        assert JSONFormatter().output_format == OutputFormat.JSON


class TestPlainTextFormatter:
    """Tests for PlainTextFormatter."""

    @pytest.mark.asyncio()
    async def test_format_passthrough(self) -> None:
        """Should return text unchanged."""
        formatter = PlainTextFormatter()
        result = await formatter.format("Hello world")
        assert result.content == "Hello world"
        assert result.format == OutputFormat.PLAINTEXT

    def test_output_format_property(self) -> None:
        assert PlainTextFormatter().output_format == OutputFormat.PLAINTEXT
