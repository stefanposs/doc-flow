"""PyMuPDF extractor adapter.

High-performance PDF text extraction using PyMuPDF (fitz).
10-50x faster than Tika for PDFs, no network overhead.
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from docflow.domain.models import ExtractionResult
from docflow.domain.ports import ExtractorPort

logger = structlog.get_logger()


class PyMuPDFExtractor(ExtractorPort):
    """Extract text from PDFs using PyMuPDF."""

    async def extract(self, file_content: bytes, mime_type: str) -> ExtractionResult:
        """Extract text from PDF using PyMuPDF in a thread pool."""
        log = logger.bind(engine="pymupdf", mime_type=mime_type, size=len(file_content))

        # PyMuPDF is synchronous — run in thread pool
        result = await asyncio.to_thread(self._extract_sync, file_content)
        log.info("pymupdf.extracted", text_length=len(result.text), pages=len(result.pages))

        return result

    def _extract_sync(self, file_content: bytes) -> ExtractionResult:
        """Synchronous extraction using PyMuPDF."""
        import fitz

        doc = fitz.open(stream=file_content, filetype="pdf")
        pages: list[str] = []
        metadata: dict[str, Any] = {}

        try:
            # Extract metadata
            meta = doc.metadata or {}
            metadata = {
                "title": meta.get("title", ""),
                "author": meta.get("author", ""),
                "subject": meta.get("subject", ""),
                "page_count": doc.page_count,
            }

            # Extract text page by page
            for page in doc:
                text = page.get_text("text")
                pages.append(text)
        finally:
            doc.close()

        full_text = "\n\n".join(pages)

        return ExtractionResult(
            text=full_text,
            metadata=metadata,
            pages=pages,
            engine_used="pymupdf",
        )

    def supported_mime_types(self) -> set[str]:
        """PyMuPDF supports PDF only."""
        return {"application/pdf"}

    @property
    def name(self) -> str:
        return "pymupdf"
