"""Text cleanup post-processor.

Cleans up raw extracted text: normalizes whitespace, removes artifacts,
fixes encoding issues. No external dependencies.
"""

from __future__ import annotations

import re
from typing import Any

from docflow.domain.ports import PostProcessorPort


class CleanupProcessor(PostProcessorPort):
    """Clean up raw extracted text without external dependencies."""

    async def process(self, text: str, context: dict[str, Any] | None = None) -> str:
        """Apply cleanup transformations to extracted text."""
        result = text

        # Normalize line endings
        result = result.replace("\r\n", "\n").replace("\r", "\n")

        # Remove NULL bytes and control characters (keep newlines, tabs)
        result = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", result)

        # Collapse 3+ consecutive newlines into 2
        result = re.sub(r"\n{3,}", "\n\n", result)

        # Remove trailing whitespace from lines
        result = re.sub(r"[ \t]+$", "", result, flags=re.MULTILINE)

        # Remove leading/trailing whitespace from document
        result = result.strip()

        # Fix common OCR artifacts
        result = self._fix_ocr_artifacts(result)

        return result

    def _fix_ocr_artifacts(self, text: str) -> str:
        """Fix common OCR misrecognitions."""
        # Fix broken words (hyphenation at line breaks)
        text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)

        # Fix multiple spaces (but keep indentation)
        text = re.sub(r"(?<=\S)  +(?=\S)", " ", text)

        return text

    @property
    def name(self) -> str:
        return "cleanup"
