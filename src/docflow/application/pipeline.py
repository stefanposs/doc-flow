"""Pipeline orchestration — routes documents through extract → process → format."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import structlog

from docflow.domain.models import (
    Document,
    ExtractionEngine,
    ExtractionResult,
    OCREngine,
    OutputFormat,
)

if TYPE_CHECKING:
    from docflow.domain.ports import (
        ExtractorPort,
        OCRPort,
        OutputFormatterPort,
        PostProcessorPort,
    )

logger = structlog.get_logger()

# MIME types that typically need OCR
IMAGE_MIME_TYPES = {
    "image/png",
    "image/jpeg",
    "image/tiff",
    "image/bmp",
    "image/gif",
    "image/webp",
}

# MIME types best handled by PyMuPDF
PDF_MIME_TYPES = {
    "application/pdf",
}


class ExtractorRouter:
    """Routes documents to the appropriate extractor based on MIME type and config."""

    def __init__(self, extractors: dict[str, ExtractorPort]) -> None:
        self._extractors = extractors

    def resolve(self, mime_type: str, preferred: ExtractionEngine = ExtractionEngine.AUTO) -> ExtractorPort:
        """Resolve the best extractor for a given MIME type.

        Args:
            mime_type: Document MIME type.
            preferred: User-preferred engine (AUTO = let router decide).

        Returns:
            The matched ExtractorPort implementation.

        Raises:
            ValueError: If no extractor supports the given MIME type.
        """
        if preferred != ExtractionEngine.AUTO and preferred.value in self._extractors:
            return self._extractors[preferred.value]

        # Prefer PyMuPDF for PDFs (faster, no network)
        if mime_type in PDF_MIME_TYPES and "pymupdf" in self._extractors:
            return self._extractors["pymupdf"]

        # Fallback to Tika (supports everything)
        if "tika" in self._extractors:
            return self._extractors["tika"]

        # Use whatever is available
        for extractor in self._extractors.values():
            if mime_type in extractor.supported_mime_types():
                return extractor

        msg = f"No extractor available for MIME type: {mime_type}"
        raise ValueError(msg)


class ProcessingPipeline:
    """Orchestrates the full extraction → processing → formatting pipeline."""

    def __init__(
        self,
        extractor_router: ExtractorRouter,
        ocr: OCRPort | None = None,
        post_processors: list[PostProcessorPort] | None = None,
        formatters: dict[OutputFormat, OutputFormatterPort] | None = None,
    ) -> None:
        self._router = extractor_router
        self._ocr = ocr
        self._processors = post_processors or []
        self._formatters = formatters or {}

    async def run(
        self,
        document: Document,
        file_content: bytes,
        mime_type: str,
    ) -> Document:
        """Run the full pipeline on a document.

        Args:
            document: The Document domain entity.
            file_content: Raw file bytes.
            mime_type: MIME type of the file.

        Returns:
            Updated Document with extraction results.
        """
        start_time = time.monotonic()
        log = logger.bind(document_id=document.id, mime_type=mime_type)

        try:
            # ── Phase 1: Extraction ──────────────────────────
            document.mark_extracting()
            log.info("extraction.started")

            extraction = await self._extract(file_content, mime_type, document.extraction_engine)
            document.raw_text = extraction.text
            log.info("extraction.completed", engine=extraction.engine_used, text_length=len(extraction.text))

            # ── Phase 2: OCR (if needed) ─────────────────────
            text = extraction.text
            if self._needs_ocr(mime_type, text, document.ocr_engine):
                log.info("ocr.started")
                text = await self._run_ocr(file_content, document)
                log.info("ocr.completed", text_length=len(text))
            elif not text.strip() and mime_type in PDF_MIME_TYPES:
                # Scanned PDF — try OCR
                log.info("ocr.started", reason="empty_extraction")
                text = await self._run_ocr(file_content, document)
                log.info("ocr.completed", text_length=len(text))

            # ── Phase 3: Post-Processing ─────────────────────
            document.mark_processing()
            context: dict[str, Any] = {"mime_type": mime_type, "document_id": document.id}
            processors_applied: list[str] = []

            for processor in self._processors:
                text = await processor.process(text, context)
                processors_applied.append(processor.name)

            log.info("processing.completed", processors=processors_applied)

            # ── Phase 4: Formatting ──────────────────────────
            formatter = self._formatters.get(document.output_format)
            if formatter:
                result = await formatter.format(text, extraction.metadata)
                content = result.content
            else:
                content = text

            # ── Finalize ─────────────────────────────────────
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            document.mark_completed(content, elapsed_ms)
            log.info("pipeline.completed", processing_time_ms=elapsed_ms)

        except Exception as exc:
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            document.mark_failed(str(exc))
            log.exception("pipeline.failed", error=str(exc), processing_time_ms=elapsed_ms)

        return document

    async def _extract(
        self,
        file_content: bytes,
        mime_type: str,
        preferred: ExtractionEngine,
    ) -> ExtractionResult:
        """Route to the appropriate extractor."""
        extractor = self._router.resolve(mime_type, preferred)
        return await extractor.extract(file_content, mime_type)

    def _needs_ocr(self, mime_type: str, text: str, ocr_engine: OCREngine) -> bool:
        """Determine if OCR is needed."""
        if ocr_engine == OCREngine.NONE:
            return False
        if mime_type in IMAGE_MIME_TYPES:
            return True
        # Scanned PDF with no text
        return mime_type in PDF_MIME_TYPES and len(text.strip()) < 50

    async def _run_ocr(self, file_content: bytes, document: Document) -> str:
        """Run OCR on the document."""
        if not self._ocr:
            logger.warning("ocr.not_configured", document_id=document.id)
            return document.raw_text or ""

        language = document.metadata.language if document.metadata and document.metadata.language else "eng"
        return await self._ocr.recognize(file_content, language=language)
