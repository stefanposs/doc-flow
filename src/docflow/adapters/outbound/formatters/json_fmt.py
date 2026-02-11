"""JSON output formatter."""

from __future__ import annotations

import json
from typing import Any

from docflow.domain.models import OutputFormat, ProcessingResult
from docflow.domain.ports import OutputFormatterPort


class JSONFormatter(OutputFormatterPort):
    """Format extracted text as structured JSON."""

    async def format(self, text: str, metadata: dict[str, Any] | None = None) -> ProcessingResult:
        """Format text as JSON with content and metadata."""
        output = {
            "content": text,
            "metadata": metadata or {},
        }

        return ProcessingResult(
            content=json.dumps(output, indent=2, ensure_ascii=False),
            format=OutputFormat.JSON,
            processors_applied=["json_formatter"],
        )

    @property
    def output_format(self) -> OutputFormat:
        return OutputFormat.JSON
