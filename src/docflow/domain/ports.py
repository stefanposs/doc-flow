"""Port interfaces (ABCs) — the contracts between domain and adapters.

These define WHAT the system needs, not HOW it's implemented.
Each adapter implements one or more of these ports.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from docflow.domain.models import ExtractionResult, OutputFormat, ProcessingResult


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
