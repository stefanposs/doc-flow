"""Domain models for DocFlow."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class DocumentStatus(StrEnum):
    """Lifecycle status of a document."""

    PENDING = "pending"
    EXTRACTING = "extracting"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class JobStatus(StrEnum):
    """Lifecycle status of an async job."""

    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


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


class QueueBackend(StrEnum):
    """Available queue backends."""

    MEMORY = "memory"
    REDIS = "redis"


class CacheBackend(StrEnum):
    """Available cache backends."""

    MEMORY = "memory"
    REDIS = "redis"


class BlobBackend(StrEnum):
    """Available blob storage backends."""

    LOCAL = "local"
    MEMORY = "memory"
    S3 = "s3"
    GCS = "gcs"
    AZURE = "azure"


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
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    processing_time_ms: int | None = None

    def mark_extracting(self) -> None:
        """Transition to extracting state."""
        self.status = DocumentStatus.EXTRACTING
        self.updated_at = datetime.now(UTC)

    def mark_processing(self) -> None:
        """Transition to processing state."""
        self.status = DocumentStatus.PROCESSING
        self.updated_at = datetime.now(UTC)

    def mark_completed(self, content: str, processing_time_ms: int) -> None:
        """Transition to completed state with result."""
        self.status = DocumentStatus.COMPLETED
        self.processed_content = content
        self.processing_time_ms = processing_time_ms
        self.updated_at = datetime.now(UTC)

    def mark_failed(self, error: str) -> None:
        """Transition to failed state with error."""
        self.status = DocumentStatus.FAILED
        self.error = error
        self.updated_at = datetime.now(UTC)


# ─── Job (async processing) ─────────────────────────────────


@dataclass
class Job:
    """Represents an async document processing job."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: JobStatus = JobStatus.QUEUED
    filename: str = ""
    mime_type: str = ""
    size_bytes: int = 0
    output_format: OutputFormat = OutputFormat.MARKDOWN
    extraction_engine: ExtractionEngine = ExtractionEngine.AUTO
    ocr_engine: OCREngine = OCREngine.TESSERACT
    language: str | None = None
    blob_key: str | None = None  # where input file is stored
    result_key: str | None = None  # where output is stored
    result_content: str | None = None
    error: str | None = None
    attempts: int = 0
    max_attempts: int = 3
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    processing_time_ms: int | None = None
    tenant_id: str | None = None
    callback_url: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def mark_processing(self) -> None:
        """Transition to processing."""
        self.status = JobStatus.PROCESSING
        self.started_at = datetime.now(UTC)
        self.updated_at = datetime.now(UTC)
        self.attempts += 1

    def mark_completed(self, result_key: str, result_content: str, processing_time_ms: int) -> None:
        """Transition to completed with result."""
        self.status = JobStatus.COMPLETED
        self.result_key = result_key
        self.result_content = result_content
        self.processing_time_ms = processing_time_ms
        self.completed_at = datetime.now(UTC)
        self.updated_at = datetime.now(UTC)

    def mark_failed(self, error: str) -> None:
        """Transition to failed."""
        self.status = JobStatus.FAILED
        self.error = error
        self.updated_at = datetime.now(UTC)

    def mark_cancelled(self) -> None:
        """Transition to cancelled."""
        self.status = JobStatus.CANCELLED
        self.updated_at = datetime.now(UTC)

    @property
    def can_retry(self) -> bool:
        """Check if this job can be retried."""
        return self.status == JobStatus.FAILED and self.attempts < self.max_attempts


@dataclass
class JobFilter:
    """Filter criteria for listing jobs."""

    status: JobStatus | None = None
    tenant_id: str | None = None
    filename_contains: str | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None


@dataclass
class PaginatedResult:
    """Paginated list result."""

    items: list[Any] = field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 50
    has_next: bool = False
