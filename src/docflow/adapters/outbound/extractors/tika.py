"""Apache Tika extractor adapter.

Connects to a Tika server via HTTP to extract text from documents.
Supports 1000+ document formats.
"""

from __future__ import annotations

import httpx
import structlog

from docflow.domain.models import ExtractionResult
from docflow.domain.ports import ExtractorPort

logger = structlog.get_logger()


class TikaExtractor(ExtractorPort):
    """Extract text from documents using Apache Tika via HTTP."""

    def __init__(self, tika_url: str = "http://localhost:9998", timeout: int = 120) -> None:
        self._tika_url = tika_url.rstrip("/")
        self._timeout = timeout

    async def extract(self, file_content: bytes, mime_type: str) -> ExtractionResult:
        """Extract text by sending file to Tika server."""
        log = logger.bind(engine="tika", mime_type=mime_type, size=len(file_content))

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            # Extract text via /tika endpoint
            response = await client.put(
                f"{self._tika_url}/tika",
                content=file_content,
                headers={
                    "Content-Type": mime_type,
                    "Accept": "text/plain",
                },
            )
            response.raise_for_status()
            text = response.text.strip()

            # Extract metadata via /meta endpoint
            meta_response = await client.put(
                f"{self._tika_url}/meta",
                content=file_content,
                headers={
                    "Content-Type": mime_type,
                    "Accept": "application/json",
                },
            )
            metadata: dict[str, str] = {}
            if meta_response.status_code == 200:
                metadata = meta_response.json()

        log.info("tika.extracted", text_length=len(text))

        return ExtractionResult(
            text=text,
            metadata=metadata,
            engine_used="tika",
        )

    def supported_mime_types(self) -> set[str]:
        """Tika supports virtually all document types."""
        return {
            "application/pdf",
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.ms-excel",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.ms-powerpoint",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "text/plain",
            "text/html",
            "text/csv",
            "application/rtf",
            "application/epub+zip",
            "image/png",
            "image/jpeg",
            "image/tiff",
        }

    @property
    def name(self) -> str:
        return "tika"
