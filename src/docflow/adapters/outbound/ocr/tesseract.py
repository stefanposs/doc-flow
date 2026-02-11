"""Tesseract OCR adapter.

Uses pytesseract to perform OCR on images and scanned documents.
Tesseract must be installed as a system dependency.
"""

from __future__ import annotations

import asyncio
import io

import structlog

from docflow.domain.ports import OCRPort

logger = structlog.get_logger()


class TesseractOCR(OCRPort):
    """OCR using Tesseract via pytesseract."""

    def __init__(self, dpi: int = 300) -> None:
        self._dpi = dpi

    async def recognize(self, image_content: bytes, language: str = "eng") -> str:
        """Perform OCR using Tesseract in a thread pool."""
        log = logger.bind(engine="tesseract", language=language, size=len(image_content))

        text = await asyncio.to_thread(self._recognize_sync, image_content, language)
        log.info("tesseract.recognized", text_length=len(text))

        return text

    def _recognize_sync(self, image_content: bytes, language: str) -> str:
        """Synchronous Tesseract OCR."""
        import pytesseract  # type: ignore[import-untyped]
        from PIL import Image

        image = Image.open(io.BytesIO(image_content))

        # Configure Tesseract
        config = f"--dpi {self._dpi} --oem 3 --psm 3"

        text: str = pytesseract.image_to_string(image, lang=language, config=config)
        return text.strip()

    @property
    def name(self) -> str:
        return "tesseract"
