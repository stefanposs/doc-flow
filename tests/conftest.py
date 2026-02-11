"""Shared test fixtures and fakes."""

from __future__ import annotations

from typing import Any

import pytest

from docflow.domain.models import ExtractionResult, OutputFormat, ProcessingResult
from docflow.domain.ports import ExtractorPort, OCRPort, OutputFormatterPort, PostProcessorPort, StoragePort


# ─── Fakes (In-Memory Implementations of Ports) ─────────────


class FakeExtractor(ExtractorPort):
    """In-memory extractor for unit tests."""

    def __init__(self, text: str = "Fake extracted text.", metadata: dict[str, Any] | None = None) -> None:
        self._text = text
        self._metadata = metadata or {}

    async def extract(self, file_content: bytes, mime_type: str) -> ExtractionResult:
        return ExtractionResult(
            text=self._text,
            metadata=self._metadata,
            engine_used="fake",
        )

    def supported_mime_types(self) -> set[str]:
        return {"application/pdf", "text/plain", "image/png"}

    @property
    def name(self) -> str:
        return "fake"


class FakeOCR(OCRPort):
    """In-memory OCR for unit tests."""

    def __init__(self, text: str = "Fake OCR text.") -> None:
        self._text = text

    async def recognize(self, image_content: bytes, language: str = "eng") -> str:
        return self._text

    @property
    def name(self) -> str:
        return "fake_ocr"


class FakePostProcessor(PostProcessorPort):
    """In-memory post-processor for unit tests."""

    def __init__(self, suffix: str = " [processed]") -> None:
        self._suffix = suffix

    async def process(self, text: str, context: dict[str, Any] | None = None) -> str:
        return text + self._suffix

    @property
    def name(self) -> str:
        return "fake_processor"


class FakeFormatter(OutputFormatterPort):
    """In-memory formatter for unit tests."""

    async def format(self, text: str, metadata: dict[str, Any] | None = None) -> ProcessingResult:
        return ProcessingResult(
            content=f"# Formatted\n\n{text}",
            format=OutputFormat.MARKDOWN,
            processors_applied=["fake_formatter"],
        )

    @property
    def output_format(self) -> OutputFormat:
        return OutputFormat.MARKDOWN


class FakeStorage(StoragePort):
    """In-memory storage for unit tests."""

    def __init__(self) -> None:
        self._files: dict[str, bytes] = {}

    async def store(self, key: str, content: bytes, content_type: str = "application/octet-stream") -> str:
        self._files[key] = content
        return f"/fake/{key}"

    async def retrieve(self, key: str) -> bytes:
        if key not in self._files:
            msg = f"File not found: {key}"
            raise FileNotFoundError(msg)
        return self._files[key]

    async def delete(self, key: str) -> None:
        self._files.pop(key, None)

    async def exists(self, key: str) -> bool:
        return key in self._files
