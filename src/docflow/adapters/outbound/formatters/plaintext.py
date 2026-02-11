"""Plain text output formatter."""

from __future__ import annotations

from typing import Any

from docflow.domain.models import OutputFormat, ProcessingResult
from docflow.domain.ports import OutputFormatterPort


class PlainTextFormatter(OutputFormatterPort):
    """Output extracted text as-is (plain text)."""

    async def format(self, text: str, metadata: dict[str, Any] | None = None) -> ProcessingResult:
        """Return text without any formatting changes."""
        return ProcessingResult(
            content=text,
            format=OutputFormat.PLAINTEXT,
            processors_applied=["plaintext_formatter"],
        )

    @property
    def output_format(self) -> OutputFormat:
        return OutputFormat.PLAINTEXT
