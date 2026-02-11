"""Port interfaces (ABCs) — the contracts between domain and adapters.

These define WHAT the system needs, not HOW it's implemented.
Each adapter implements one or more of these ports.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from docflow.domain.models import (
        ExtractionResult,
        Job,
        JobFilter,
        OutputFormat,
        PaginatedResult,
        ProcessingResult,
    )


class ExtractorPort(ABC):
    """Port for document text extraction.

    Implementations: TikaExtractor, PyMuPDFExtractor, TextractExtractor
    """

    @abstractmethod
    async def extract(self, file_content: bytes, mime_type: str) -> ExtractionResult:
        """Extract raw text from a document.

        Args:
            file_content: Raw file bytes.
            mime_type: MIME type of the document.

        Returns:
            ExtractionResult with extracted text and metadata.
        """

    @abstractmethod
    def supported_mime_types(self) -> set[str]:
        """Return the set of MIME types this extractor supports."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of this extractor."""


class OCRPort(ABC):
    """Port for Optical Character Recognition.

    Implementations: TesseractOCR, GoogleVisionOCR, AzureOCR
    """

    @abstractmethod
    async def recognize(self, image_content: bytes, language: str = "eng") -> str:
        """Perform OCR on an image.

        Args:
            image_content: Raw image bytes (PNG, JPEG, TIFF).
            language: OCR language code (e.g. 'eng', 'deu').

        Returns:
            Recognized text.
        """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of this OCR engine."""


class PostProcessorPort(ABC):
    """Port for text post-processing (cleanup, structuring, enrichment).

    Implementations: CleanupProcessor, LLMProcessor, RegexProcessor
    """

    @abstractmethod
    async def process(self, text: str, context: dict[str, Any] | None = None) -> str:
        """Process/transform extracted text.

        Args:
            text: Raw extracted text.
            context: Optional metadata for context-aware processing.

        Returns:
            Processed text.
        """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of this processor."""


class OutputFormatterPort(ABC):
    """Port for formatting processed text into output format.

    Implementations: MarkdownFormatter, JSONFormatter, PlainTextFormatter
    """

    @abstractmethod
    async def format(self, text: str, metadata: dict[str, Any] | None = None) -> ProcessingResult:
        """Format text into the target output format.

        Args:
            text: Processed text.
            metadata: Optional document metadata to include.

        Returns:
            ProcessingResult with formatted content.
        """

    @property
    @abstractmethod
    def output_format(self) -> OutputFormat:
        """The output format this formatter produces."""


class StoragePort(ABC):
    """Port for file storage (upload/download/delete).

    Implementations: LocalStorage, S3Storage
    """

    @abstractmethod
    async def store(self, key: str, content: bytes, content_type: str = "application/octet-stream") -> str:
        """Store a file and return its storage path/URL.

        Args:
            key: Storage key / filename.
            content: File content bytes.
            content_type: MIME type of the content.

        Returns:
            Storage path or URL.
        """

    @abstractmethod
    async def retrieve(self, key: str) -> bytes:
        """Retrieve a file by key.

        Args:
            key: Storage key.

        Returns:
            File content bytes.

        Raises:
            FileNotFoundError: If the key does not exist.
        """

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete a file by key.

        Args:
            key: Storage key.
        """

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if a file exists.

        Args:
            key: Storage key.

        Returns:
            True if the file exists.
        """


# ─── Queue Port ──────────────────────────────────────────────


class QueuePort(ABC):
    """Port for message queue (Redis Streams, PubSub, Azure Service Bus, etc.).

    Implementations: InMemoryQueue, RedisQueue
    """

    @abstractmethod
    async def enqueue(self, queue_name: str, payload: dict[str, Any]) -> str:
        """Put a message on the queue.

        Returns:
            Message ID.
        """

    @abstractmethod
    async def dequeue(self, queue_name: str, timeout: float = 0) -> tuple[str, dict[str, Any]] | None:
        """Get the next message from the queue.

        Args:
            queue_name: Queue to consume from.
            timeout: Seconds to wait (0 = non-blocking).

        Returns:
            (message_id, payload) or None if empty.
        """

    @abstractmethod
    async def acknowledge(self, queue_name: str, message_id: str) -> None:
        """Acknowledge successful processing of a message."""

    @abstractmethod
    async def reject(self, queue_name: str, message_id: str) -> None:
        """Reject a message (return to queue or dead-letter)."""

    @abstractmethod
    async def queue_length(self, queue_name: str) -> int:
        """Return the approximate number of messages in the queue."""

    @abstractmethod
    async def connect(self) -> None:
        """Initialize connection (called on startup)."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Teardown connection (called on shutdown)."""


# ─── Cache Port ──────────────────────────────────────────────


class CachePort(ABC):
    """Port for caching (Redis, Memcached, local dict, etc.).

    Used for rate limiting, deduplication, and result caching.
    Implementations: InMemoryCache, RedisCache
    """

    @abstractmethod
    async def get(self, key: str) -> str | None:
        """Get a cached value by key."""

    @abstractmethod
    async def set(self, key: str, value: str, ttl: int | None = None) -> None:
        """Set a cached value with optional TTL in seconds."""

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete a cached value."""

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if a key exists in the cache."""

    @abstractmethod
    async def increment(self, key: str) -> int:
        """Atomically increment a counter. Creates the key with value 1 if missing."""

    @abstractmethod
    async def connect(self) -> None:
        """Initialize connection."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Teardown connection."""


# ─── Blob Storage Port ───────────────────────────────────────


class BlobStoragePort(ABC):
    """Port for cloud-native object storage (S3, GCS, Azure Blob, local).

    Extends basic storage with presigned URLs, listing, and metadata.
    Implementations: InMemoryBlobStorage, S3BlobStorage, GCSBlobStorage, AzureBlobStorage
    """

    @abstractmethod
    async def upload(self, key: str, content: bytes, content_type: str = "application/octet-stream") -> str:
        """Upload a blob. Returns the storage URI."""

    @abstractmethod
    async def download(self, key: str) -> bytes:
        """Download a blob by key."""

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete a blob."""

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if a blob exists."""

    @abstractmethod
    async def list_blobs(self, prefix: str = "") -> list[str]:
        """List blob keys with an optional prefix filter."""

    @abstractmethod
    async def get_metadata(self, key: str) -> dict[str, str]:
        """Get metadata for a blob (content_type, size, etc.)."""

    @abstractmethod
    async def connect(self) -> None:
        """Initialize connection."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Teardown connection."""


# ─── Job Repository Port ─────────────────────────────────────


class JobRepositoryPort(ABC):
    """Port for job state persistence.

    Implementations: InMemoryJobRepository, RedisJobRepository
    """

    @abstractmethod
    async def save(self, job: Job) -> None:
        """Save or update a job."""

    @abstractmethod
    async def get(self, job_id: str) -> Job | None:
        """Get a job by ID. Returns None if not found."""

    @abstractmethod
    async def list_jobs(
        self,
        filter_: JobFilter | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> PaginatedResult:
        """List jobs with optional filters and pagination."""

    @abstractmethod
    async def delete(self, job_id: str) -> bool:
        """Delete a job. Returns True if deleted."""

    @abstractmethod
    async def count(self, filter_: JobFilter | None = None) -> int:
        """Count jobs matching the filter."""


# ─── Metrics Port ────────────────────────────────────────────


class MetricsPort(ABC):
    """Port for observability metrics (Prometheus, Datadog, etc.).

    Implementations: NoOpMetrics, PrometheusMetrics
    """

    @abstractmethod
    def counter(self, name: str, value: float = 1, tags: dict[str, str] | None = None) -> None:
        """Increment a counter."""

    @abstractmethod
    def histogram(self, name: str, value: float, tags: dict[str, str] | None = None) -> None:
        """Record a histogram observation."""

    @abstractmethod
    def gauge(self, name: str, value: float, tags: dict[str, str] | None = None) -> None:
        """Set a gauge value."""
