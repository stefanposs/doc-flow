"""Markdown output formatter.

Formats extracted text into clean Markdown with optional metadata header.
"""

from __future__ import annotations

import re
from typing import Any

from docflow.domain.models import OutputFormat, ProcessingResult
from docflow.domain.ports import OutputFormatterPort


class MarkdownFormatter(OutputFormatterPort):
    """Format extracted text as Markdown."""

    def __init__(self, include_metadata: bool = True) -> None:
        self._include_metadata = include_metadata

    async def format(self, text: str, metadata: dict[str, Any] | None = None) -> ProcessingResult:
        """Format text as Markdown with optional YAML front matter."""
        parts: list[str] = []

        # Add YAML front matter if metadata available
        if self._include_metadata and metadata:
            front_matter = self._build_front_matter(metadata)
            if front_matter:
                parts.append(front_matter)

        # Process text into clean markdown
        content = self._to_markdown(text)
        parts.append(content)

        return ProcessingResult(
            content="\n".join(parts),
            format=OutputFormat.MARKDOWN,
            processors_applied=["markdown_formatter"],
        )

    def _build_front_matter(self, metadata: dict[str, Any]) -> str:
        """Build YAML front matter from metadata."""
        lines: list[str] = ["---"]

        # Pick relevant metadata fields
        field_map = {
            "title": "title",
            "author": "author",
            "subject": "subject",
            "dc:title": "title",
            "dc:creator": "author",
            "Content-Type": "content_type",
            "page_count": "pages",
        }

        added: set[str] = set()
        for key, field_name in field_map.items():
            if key in metadata and metadata[key] and field_name not in added:
                value = metadata[key]
                if isinstance(value, str):
                    value = value.strip()
                if value:
                    lines.append(f"{field_name}: {value}")
                    added.add(field_name)

        lines.append("---")

        return "\n".join(lines) if len(lines) > 2 else ""

    def _to_markdown(self, text: str) -> str:
        """Convert text to cleaner markdown formatting."""
        lines = text.split("\n")
        result: list[str] = []

        for line in lines:
            stripped = line.strip()

            # Detect potential headers (ALL CAPS lines, short lines followed by blank)
            if stripped and stripped.isupper() and len(stripped) < 80 and not stripped.startswith("#"):
                result.append(f"## {stripped.title()}")
            else:
                result.append(line)

        return "\n".join(result)

    @property
    def output_format(self) -> OutputFormat:
        return OutputFormat.MARKDOWN
