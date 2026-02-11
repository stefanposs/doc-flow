"""Dependency injection — wires adapters to ports based on configuration."""

from __future__ import annotations

from fastapi import FastAPI

from docflow.adapters.outbound.extractors.tika import TikaExtractor
from docflow.adapters.outbound.formatters.json_fmt import JSONFormatter
from docflow.adapters.outbound.formatters.markdown import MarkdownFormatter
from docflow.adapters.outbound.formatters.plaintext import PlainTextFormatter
from docflow.adapters.outbound.processors.cleanup import CleanupProcessor
from docflow.application.config import Settings
from docflow.application.pipeline import ExtractorRouter, ProcessingPipeline
from docflow.application.service import DocumentService
from docflow.domain.models import OutputFormat
from docflow.domain.ports import ExtractorPort, OCRPort, OutputFormatterPort, PostProcessorPort


def _build_extractors(settings: Settings) -> dict[str, ExtractorPort]:
    """Build extractor adapters from config."""
    extractors: dict[str, ExtractorPort] = {}

    # Tika is always available (HTTP, no extra deps)
    extractors["tika"] = TikaExtractor(
        tika_url=settings.tika_url,
        timeout=settings.tika_timeout,
    )

    # PyMuPDF is optional
    try:
        from docflow.adapters.outbound.extractors.pymupdf import PyMuPDFExtractor

        extractors["pymupdf"] = PyMuPDFExtractor()
    except ImportError:
        pass

    return extractors


def _build_ocr(settings: Settings) -> OCRPort | None:
    """Build OCR adapter from config."""
    if not settings.ocr_enabled:
        return None

    if settings.ocr_engine.value == "tesseract":
        try:
            from docflow.adapters.outbound.ocr.tesseract import TesseractOCR

            return TesseractOCR(dpi=settings.ocr_dpi)
        except ImportError:
            return None

    return None


def _build_processors(settings: Settings) -> list[PostProcessorPort]:
    """Build post-processor chain from config."""
    processors: list[PostProcessorPort] = []

    for name in settings.processors:
        if name == "cleanup":
            processors.append(CleanupProcessor())
        # Future: LLM processor, regex processor, etc.

    return processors


def _build_formatters() -> dict[OutputFormat, OutputFormatterPort]:
    """Build output formatters."""
    return {
        OutputFormat.MARKDOWN: MarkdownFormatter(),
        OutputFormat.JSON: JSONFormatter(),
        OutputFormat.PLAINTEXT: PlainTextFormatter(),
    }


def setup_dependencies(app: FastAPI, settings: Settings) -> None:
    """Wire up all dependencies and store on app state."""
    extractors = _build_extractors(settings)
    ocr = _build_ocr(settings)
    processors = _build_processors(settings)
    formatters = _build_formatters()

    router = ExtractorRouter(extractors)

    pipeline = ProcessingPipeline(
        extractor_router=router,
        ocr=ocr,
        post_processors=processors,
        formatters=formatters,
    )

    service = DocumentService(pipeline=pipeline, settings=settings)

    # Store on app state for dependency injection
    app.state.settings = settings
    app.state.document_service = service
    app.state.extractors = extractors
    app.state.pipeline = pipeline
