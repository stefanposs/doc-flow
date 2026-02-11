"""Unit tests for domain models."""

from __future__ import annotations

from docflow.domain.models import Document, DocumentMetadata, DocumentStatus, OutputFormat


class TestDocument:
    """Tests for the Document entity."""

    def test_create_document_defaults(self) -> None:
        """Document should have sensible defaults."""
        doc = Document()
        assert doc.status == DocumentStatus.PENDING
        assert doc.output_format == OutputFormat.MARKDOWN
        assert doc.id is not None
        assert doc.error is None

    def test_mark_extracting(self) -> None:
        """Transition to extracting state."""
        doc = Document()
        doc.mark_extracting()
        assert doc.status == DocumentStatus.EXTRACTING

    def test_mark_processing(self) -> None:
        """Transition to processing state."""
        doc = Document()
        doc.mark_processing()
        assert doc.status == DocumentStatus.PROCESSING

    def test_mark_completed(self) -> None:
        """Transition to completed state with content."""
        doc = Document()
        doc.mark_completed("Hello world", processing_time_ms=42)
        assert doc.status == DocumentStatus.COMPLETED
        assert doc.processed_content == "Hello world"
        assert doc.processing_time_ms == 42

    def test_mark_failed(self) -> None:
        """Transition to failed state with error."""
        doc = Document()
        doc.mark_failed("Something went wrong")
        assert doc.status == DocumentStatus.FAILED
        assert doc.error == "Something went wrong"


class TestDocumentMetadata:
    """Tests for DocumentMetadata."""

    def test_create_metadata(self) -> None:
        """Metadata should store file information."""
        meta = DocumentMetadata(
            filename="test.pdf",
            mime_type="application/pdf",
            size_bytes=1024,
            language="deu",
        )
        assert meta.filename == "test.pdf"
        assert meta.mime_type == "application/pdf"
        assert meta.size_bytes == 1024
        assert meta.language == "deu"
        assert meta.page_count is None
