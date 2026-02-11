"""Domain models for DocFlow."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


class DocumentStatus(StrEnum):
    """Lifecycle status of a document."""

    PENDING = "pending"
    EXTRACTING = "extracting"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class OutputFormat(StrEnum):
    """Supported output formats."""

    MARKDOWN = "markdown"
    JSON = "json"
    PLAINTEXT = "plaintext"


class ExtractionEngine(StrEnum):
    """Available extraction engines."""

    TIKA = "tika"
    PYMUPDF = "pymupdf"
    AUTO = "auto"


class OCREngine(StrEnum):
    """Available OCR engines."""

    TESSERACT = "tesseract"
    GOOGLE_VISION = "google_vision"
    NONE = "none"


@dataclass
class DocumentMetadata:
    """Metadata extracted from a document."""

    filename: str
    mime_type: str
    size_bytes: int
    page_count: int | None = None
    language: str | None = None
    author: str | None = None
    title: str | None = None
    created_at: str | None = None
    checksum: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExtractionResult:
    """Raw extraction result from an extractor adapter."""

    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    pages: list[str] = field(default_factory=list)
    engine_used: str = ""
    confidence: float | None = None


@dataclass
class ProcessingResult:
    """Result after post-processing pipeline."""

    content: str
    format: OutputFormat = OutputFormat.MARKDOWN
    processors_applied: list[str] = field(default_factory=list)


@dataclass
class Document:
    """Core domain entity representing a document in the pipeline."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: DocumentStatus = DocumentStatus.PENDING
    metadata: DocumentMetadata | None = None
    raw_text: str | None = None
    processed_content: str | None = None
    output_format: OutputFormat = OutputFormat.MARKDOWN
    extraction_engine: ExtractionEngine = ExtractionEngine.AUTO
    ocr_engine: OCREngine = OCREngine.TESSERACT
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    processing_time_ms: int | None = None

    def mark_extracting(self) -> None:
        """Transition to extracting state."""
        self.status = DocumentStatus.EXTRACTING
        self.updated_at = datetime.now(timezone.utc)

    def mark_processing(self) -> None:
        """Transition to processing state."""
        self.status = DocumentStatus.PROCESSING
        self.updated_at = datetime.now(timezone.utc)

    def mark_completed(self, content: str, processing_time_ms: int) -> None:
        """Transition to completed state with result."""
        self.status = DocumentStatus.COMPLETED
        self.processed_content = content
        self.processing_time_ms = processing_time_ms
        self.updated_at = datetime.now(timezone.utc)

    def mark_failed(self, error: str) -> None:
        """Transition to failed state with error."""
        self.status = DocumentStatus.FAILED
        self.error = error
        self.updated_at = datetime.now(timezone.utc)
