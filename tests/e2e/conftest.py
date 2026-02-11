"""E2E test fixtures — app, client, and synthetic test documents.

Sets up a fully wired FastAPI application with **all in-memory adapters** so
the entire E2E suite runs locally without any cloud services (no S3, no Redis,
no Tika server, no Tesseract binary).
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING, Any

import pytest
from httpx import ASGITransport, AsyncClient

from docflow.adapters.inbound.api.app import create_app
from docflow.adapters.outbound.blob import InMemoryBlobStorage
from docflow.adapters.outbound.cache import InMemoryCache
from docflow.adapters.outbound.formatters.json_fmt import JSONFormatter
from docflow.adapters.outbound.formatters.markdown import MarkdownFormatter
from docflow.adapters.outbound.formatters.plaintext import PlainTextFormatter
from docflow.adapters.outbound.metrics import NoOpMetrics
from docflow.adapters.outbound.processors.cleanup import CleanupProcessor
from docflow.adapters.outbound.queue import InMemoryQueue
from docflow.adapters.outbound.repository import InMemoryJobRepository
from docflow.application.config import Settings
from docflow.application.job_service import JobService
from docflow.application.pipeline import ExtractorRouter, ProcessingPipeline
from docflow.application.service import DocumentService
from docflow.application.worker import WorkerPool
from docflow.domain.models import ExtractionResult, OutputFormat
from docflow.domain.ports import (
    ExtractorPort,
    OCRPort,
    OutputFormatterPort,
    StoragePort,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

# ── In-Memory Fakes (E2E-specific) ──────────────────────────────────────────
#
# These are slightly richer than the unit-test fakes: the extractor returns
# text derived from the *actual* input bytes so we can assert round-trip
# correctness (upload → extract → retrieve).


class InMemoryExtractor(ExtractorPort):
    """Extractor that echoes decoded file content — simulates a real engine."""

    async def extract(self, file_content: bytes, mime_type: str) -> ExtractionResult:
        # Attempt UTF-8 decode; fall back to hex summary for binary
        try:
            text = file_content.decode("utf-8")
        except UnicodeDecodeError:
            text = f"[binary content: {len(file_content)} bytes, mime={mime_type}]"

        return ExtractionResult(
            text=text,
            metadata={"mime_type": mime_type, "size": len(file_content)},
            engine_used="in_memory",
        )

    def supported_mime_types(self) -> set[str]:
        return {
            "application/pdf",
            "text/plain",
            "text/html",
            "image/png",
            "image/jpeg",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }

    @property
    def name(self) -> str:
        return "in_memory"


class InMemoryOCR(OCRPort):
    """OCR stub — returns a fixed string for any image."""

    async def recognize(self, image_content: bytes, language: str = "eng") -> str:
        return f"[OCR text from {len(image_content)} bytes, lang={language}]"

    @property
    def name(self) -> str:
        return "in_memory_ocr"


class InMemoryStorage(StoragePort):
    """Fully functional in-memory blob store."""

    def __init__(self) -> None:
        self._blobs: dict[str, bytes] = {}

    async def store(self, key: str, content: bytes, content_type: str = "application/octet-stream") -> str:
        self._blobs[key] = content
        return f"mem://{key}"

    async def retrieve(self, key: str) -> bytes:
        if key not in self._blobs:
            msg = f"Blob not found: {key}"
            raise FileNotFoundError(msg)
        return self._blobs[key]

    async def delete(self, key: str) -> None:
        self._blobs.pop(key, None)

    async def exists(self, key: str) -> bool:
        return key in self._blobs


# ── Synthetic Test Documents ─────────────────────────────────────────────────


def _make_minimal_pdf(text: str = "Hello from the test PDF.") -> bytes:
    """Create a minimal valid PDF in memory (no reportlab needed).

    Produces a single-page PDF with the given text embedded as a
    raw content stream.  The result is ~350 bytes — small but structurally
    valid enough to be parsed by most extraction engines.
    """
    # We build the raw PDF structure manually so there is **zero** dependency
    # beyond the stdlib.
    content_stream = f"BT /F1 12 Tf 100 700 Td ({text}) Tj ET"
    stream_bytes = content_stream.encode("latin-1")

    objects: list[str] = []

    # Obj 1 — Catalog
    objects.append("1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj")
    # Obj 2 — Pages
    objects.append("2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj")
    # Obj 3 — Page
    objects.append(
        "3 0 obj\n<< /Type /Page /Parent 2 0 R "
        "/MediaBox [0 0 612 792] "
        "/Contents 4 0 R "
        "/Resources << /Font << /F1 5 0 R >> >> >>\nendobj"
    )
    # Obj 4 — Content stream
    objects.append(
        f"4 0 obj\n<< /Length {len(stream_bytes)} >>\n"
        f"stream\n{content_stream}\nendstream\nendobj"
    )
    # Obj 5 — Font
    objects.append(
        "5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj"
    )

    buf = io.BytesIO()
    buf.write(b"%PDF-1.4\n")
    offsets: list[int] = []
    for obj in objects:
        offsets.append(buf.tell())
        buf.write(obj.encode("latin-1") + b"\n")

    xref_offset = buf.tell()
    buf.write(b"xref\n")
    buf.write(f"0 {len(objects) + 1}\n".encode())
    buf.write(b"0000000000 65535 f \n")
    for off in offsets:
        buf.write(f"{off:010d} 00000 n \n".encode())
    buf.write(b"trailer\n")
    buf.write(f"<< /Size {len(objects) + 1} /Root 1 0 R >>\n".encode())
    buf.write(b"startxref\n")
    buf.write(f"{xref_offset}\n".encode())
    buf.write(b"%%EOF\n")

    return buf.getvalue()


@pytest.fixture(scope="session")
def sample_pdf_bytes() -> bytes:
    """A small, structurally-valid PDF created entirely in memory."""
    return _make_minimal_pdf()


@pytest.fixture(scope="session")
def sample_txt_bytes() -> bytes:
    """Plain-text fixture."""
    return b"The quick brown fox jumps over the lazy dog."


@pytest.fixture(scope="session")
def sample_html_bytes() -> bytes:
    """Simple HTML fixture."""
    return b"<html><body><h1>Title</h1><p>Paragraph content.</p></body></html>"


# ── Application Wiring ──────────────────────────────────────────────────────


def _build_e2e_settings(**overrides: Any) -> Settings:
    """Return a Settings instance tuned for fast, fully-local E2E runs."""
    defaults: dict[str, Any] = {
        "env": "test",
        "log_level": "WARNING",
        "log_format": "text",
        "ocr_enabled": False,
        "storage_backend": "local",
        "default_output_format": OutputFormat.MARKDOWN,
        "default_extractor": "auto",
        "max_file_size_mb": 10,
        "redis_enabled": False,
        "tika_url": "http://fake-tika:9998",
    }
    defaults.update(overrides)
    return Settings(**defaults)


def _wire_app(app: Any, settings: Settings) -> None:
    """Manually inject all in-memory adapters into the FastAPI app state."""
    extractor = InMemoryExtractor()
    extractors: dict[str, ExtractorPort] = {"tika": extractor, "in_memory": extractor}

    router = ExtractorRouter(extractors)

    formatters: dict[OutputFormat, OutputFormatterPort] = {
        OutputFormat.MARKDOWN: MarkdownFormatter(),
        OutputFormat.JSON: JSONFormatter(),
        OutputFormat.PLAINTEXT: PlainTextFormatter(),
    }

    pipeline = ProcessingPipeline(
        extractor_router=router,
        ocr=InMemoryOCR(),
        post_processors=[CleanupProcessor()],
        formatters=formatters,
    )

    service = DocumentService(pipeline=pipeline, settings=settings)

    # Enterprise infrastructure — all in-memory
    queue = InMemoryQueue()
    cache = InMemoryCache()
    blob = InMemoryBlobStorage()
    metrics = NoOpMetrics()
    repo = InMemoryJobRepository()

    job_service = JobService(
        queue=queue,
        blob=blob,
        repo=repo,
        metrics=metrics,
        settings=settings,
    )

    worker_pool = WorkerPool(
        queue=queue,
        blob=blob,
        repo=repo,
        pipeline=pipeline,
        metrics=metrics,
        settings=settings,
        concurrency=4,
    )

    app.state.settings = settings
    app.state.document_service = service
    app.state.job_service = job_service
    app.state.worker_pool = worker_pool
    app.state.extractors = extractors
    app.state.pipeline = pipeline
    app.state.queue = queue
    app.state.cache = cache
    app.state.blob = blob
    app.state.metrics = metrics
    app.state.repo = repo
    app.state.storage = InMemoryStorage()


@pytest.fixture
async def app():
    """Create a fully-wired FastAPI app with in-memory adapters."""
    application = create_app()
    settings = _build_e2e_settings()
    _wire_app(application, settings)
    return application


@pytest.fixture
async def client(app: Any) -> AsyncIterator[AsyncClient]:
    """httpx AsyncClient bound to the E2E app (no real network)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
