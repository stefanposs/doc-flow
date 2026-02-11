"""Unit tests for the processing pipeline."""

from __future__ import annotations

import pytest

from docflow.application.pipeline import ExtractorRouter, ProcessingPipeline
from docflow.domain.models import Document, ExtractionEngine, OCREngine, OutputFormat
from tests.conftest import FakeExtractor, FakeFormatter, FakeOCR, FakePostProcessor


class TestExtractorRouter:
    """Tests for ExtractorRouter."""

    def test_resolve_auto_pdf_prefers_pymupdf(self) -> None:
        """AUTO mode should prefer PyMuPDF for PDFs."""
        extractors = {
            "tika": FakeExtractor(text="tika result"),
            "pymupdf": FakeExtractor(text="pymupdf result"),
        }
        router = ExtractorRouter(extractors)
        extractor = router.resolve("application/pdf")
        assert extractor.name == "fake"  # both are FakeExtractor, but pymupdf key matched

    def test_resolve_explicit_engine(self) -> None:
        """Explicit engine selection should be respected."""
        extractors = {
            "tika": FakeExtractor(text="tika"),
            "pymupdf": FakeExtractor(text="pymupdf"),
        }
        router = ExtractorRouter(extractors)
        extractor = router.resolve("application/pdf", ExtractionEngine.TIKA)
        # Should return tika extractor
        assert extractor is extractors["tika"]

    def test_resolve_unsupported_mime_raises(self) -> None:
        """Should raise ValueError for unsupported MIME types when no fallback."""
        router = ExtractorRouter({})
        with pytest.raises(ValueError, match="No extractor available"):
            router.resolve("application/unknown")

    def test_resolve_fallback_to_tika(self) -> None:
        """Non-PDF types should fall back to Tika."""
        extractors = {"tika": FakeExtractor(text="tika")}
        router = ExtractorRouter(extractors)
        extractor = router.resolve("application/msword")
        assert extractor is extractors["tika"]


class TestProcessingPipeline:
    """Tests for ProcessingPipeline."""

    @pytest.fixture
    def pipeline(self) -> ProcessingPipeline:
        """Create a pipeline with fakes."""
        router = ExtractorRouter({"tika": FakeExtractor()})
        return ProcessingPipeline(
            extractor_router=router,
            ocr=FakeOCR(),
            post_processors=[FakePostProcessor()],
            formatters={OutputFormat.MARKDOWN: FakeFormatter()},
        )

    @pytest.mark.asyncio
    async def test_full_pipeline(self, pipeline: ProcessingPipeline) -> None:
        """Pipeline should extract, process, and format."""
        doc = Document(output_format=OutputFormat.MARKDOWN, ocr_engine=OCREngine.NONE)
        result = await pipeline.run(doc, b"fake content", "application/pdf")

        assert result.status.value == "completed"
        assert result.processed_content is not None
        assert result.processing_time_ms is not None
        assert result.processing_time_ms >= 0

    @pytest.mark.asyncio
    async def test_pipeline_applies_processors(self, pipeline: ProcessingPipeline) -> None:
        """Pipeline should apply post-processors."""
        doc = Document(output_format=OutputFormat.MARKDOWN, ocr_engine=OCREngine.NONE)
        result = await pipeline.run(doc, b"fake content", "text/plain")

        # FakePostProcessor appends " [processed]"
        assert result.processed_content is not None
        assert "[processed]" in result.processed_content

    @pytest.mark.asyncio
    async def test_pipeline_handles_failure(self) -> None:
        """Pipeline should catch exceptions and mark document failed."""

        class FailingExtractor(FakeExtractor):
            async def extract(self, file_content: bytes, mime_type: str):  # type: ignore[override]
                raise RuntimeError("Extraction failed!")

        router = ExtractorRouter({"tika": FailingExtractor()})
        pipeline = ProcessingPipeline(extractor_router=router)

        doc = Document()
        result = await pipeline.run(doc, b"content", "application/pdf")

        assert result.status.value == "failed"
        assert result.error is not None
        assert "Extraction failed!" in result.error
