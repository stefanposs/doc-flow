"""Document service — application-level orchestration."""

from __future__ import annotations

import hashlib
import mimetypes
from typing import TYPE_CHECKING, Any

try:
    import magic

    _HAS_MAGIC = True
except (ImportError, OSError):
    _HAS_MAGIC = False

import structlog

from docflow.domain.models import (
    Document,
    DocumentMetadata,
    ExtractionEngine,
    OCREngine,
    OutputFormat,
)

if TYPE_CHECKING:
    from docflow.application.config import Settings
    from docflow.application.pipeline import ProcessingPipeline

logger = structlog.get_logger()


class DocumentService:
    """Application service for document processing.

    Coordinates between the API layer, pipeline, and storage.
    """

    def __init__(self, pipeline: ProcessingPipeline, settings: Settings) -> None:
        self._pipeline = pipeline
        self._settings = settings

    async def process_document(
        self,
        filename: str,
        file_content: bytes,
        output_format: OutputFormat | None = None,
        extraction_engine: ExtractionEngine | None = None,
        ocr_engine: OCREngine | None = None,
        language: str | None = None,
    ) -> Document:
        """Process a single document through the full pipeline.

        Args:
            filename: Original filename.
            file_content: Raw file bytes.
            output_format: Desired output format (default from settings).
            extraction_engine: Preferred extraction engine (default: AUTO).
            ocr_engine: Preferred OCR engine (default from settings).
            language: Document language hint.

        Returns:
            Processed Document entity with results.
        """
        # Detect MIME type
        if _HAS_MAGIC:
            mime_type = magic.from_buffer(file_content, mime=True)
        else:
            guessed, _ = mimetypes.guess_type(filename)
            mime_type = guessed or "application/octet-stream"

        # Build metadata
        metadata = DocumentMetadata(
            filename=filename,
            mime_type=mime_type,
            size_bytes=len(file_content),
            language=language or self._settings.default_language,
            checksum=hashlib.sha256(file_content).hexdigest(),
        )

        # Create document entity
        document = Document(
            metadata=metadata,
            output_format=output_format or self._settings.default_output_format,
            extraction_engine=extraction_engine or self._settings.default_extractor,
            ocr_engine=ocr_engine or self._settings.ocr_engine,
        )

        log = logger.bind(
            document_id=document.id,
            filename=filename,
            mime_type=mime_type,
            size_bytes=len(file_content),
        )
        log.info("document.received")

        # Validate file size
        max_bytes = self._settings.max_file_size_mb * 1024 * 1024
        if len(file_content) > max_bytes:
            document.mark_failed(f"File exceeds maximum size of {self._settings.max_file_size_mb}MB")
            log.warning("document.rejected", reason="file_too_large")
            return document

        # Run pipeline
        document = await self._pipeline.run(document, file_content, mime_type)

        return document

    def get_supported_formats(self) -> dict[str, Any]:
        """Return information about supported document formats."""
        return {
            "extraction_engines": [e.value for e in ExtractionEngine],
            "ocr_engines": [e.value for e in OCREngine],
            "output_formats": [f.value for f in OutputFormat],
            "max_file_size_mb": self._settings.max_file_size_mb,
        }
