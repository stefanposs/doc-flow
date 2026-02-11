"""Dependency injection — wires adapters to ports based on configuration."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from docflow.adapters.outbound.blob import InMemoryBlobStorage
from docflow.adapters.outbound.cache import InMemoryCache
from docflow.adapters.outbound.extractors.tika import TikaExtractor
from docflow.adapters.outbound.formatters.json_fmt import JSONFormatter
from docflow.adapters.outbound.formatters.markdown import MarkdownFormatter
from docflow.adapters.outbound.formatters.plaintext import PlainTextFormatter
from docflow.adapters.outbound.metrics import NoOpMetrics
from docflow.adapters.outbound.processors.cleanup import CleanupProcessor
from docflow.adapters.outbound.queue import InMemoryQueue
from docflow.adapters.outbound.repository import InMemoryJobRepository
from docflow.application.job_service import JobService
from docflow.application.pipeline import ExtractorRouter, ProcessingPipeline
from docflow.application.service import DocumentService
from docflow.application.worker import WorkerPool
from docflow.domain.models import BlobBackend, CacheBackend, OutputFormat, QueueBackend

if TYPE_CHECKING:
    from fastapi import FastAPI

    from docflow.application.config import Settings
    from docflow.domain.ports import (
        BlobStoragePort,
        CachePort,
        ExtractorPort,
        JobRepositoryPort,
        MetricsPort,
        OCRPort,
        OutputFormatterPort,
        PostProcessorPort,
        QueuePort,
    )

logger = structlog.get_logger()


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


def _build_queue(settings: Settings) -> QueuePort:
    """Build queue adapter from config."""
    if settings.queue_backend == QueueBackend.REDIS:
        from docflow.adapters.outbound.queue.redis_queue import RedisQueue

        return RedisQueue(redis_url=settings.redis_url)

    return InMemoryQueue()


def _build_cache(settings: Settings) -> CachePort:
    """Build cache adapter from config."""
    if settings.cache_backend == CacheBackend.REDIS:
        from docflow.adapters.outbound.cache.redis_cache import RedisCache

        return RedisCache(redis_url=settings.redis_url)

    return InMemoryCache()


def _build_blob(settings: Settings) -> BlobStoragePort:
    """Build blob storage adapter from config."""
    if settings.blob_backend == BlobBackend.S3:
        from docflow.adapters.outbound.blob.s3 import S3BlobStorage

        return S3BlobStorage(
            bucket=settings.s3_bucket,
            endpoint_url=settings.s3_endpoint or None,
            region=settings.s3_region,
            access_key=settings.s3_access_key or None,
            secret_key=settings.s3_secret_key or None,
        )

    if settings.blob_backend == BlobBackend.GCS:
        from docflow.adapters.outbound.blob.gcs import GCSBlobStorage

        return GCSBlobStorage(
            bucket=settings.gcs_bucket,
            project=settings.gcs_project or None,
        )

    if settings.blob_backend == BlobBackend.AZURE:
        from docflow.adapters.outbound.blob.azure import AzureBlobStorage

        return AzureBlobStorage(
            connection_string=settings.azure_connection_string,
            container=settings.azure_container,
        )

    # Default: in-memory (perfect for local dev)
    return InMemoryBlobStorage()


def _build_metrics() -> MetricsPort:
    """Build metrics adapter. Always NoOp for now; swap for Prometheus in prod."""
    return NoOpMetrics()


def _build_job_repository() -> JobRepositoryPort:
    """Build job repository. In-memory for local dev; swap for Redis/DB in prod."""
    return InMemoryJobRepository()


def setup_dependencies(app: FastAPI, settings: Settings) -> None:
    """Wire up all dependencies and store on app state."""
    # ── Extraction pipeline (existing) ──
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

    # ── Enterprise infrastructure (new) ──
    queue = _build_queue(settings)
    cache = _build_cache(settings)
    blob = _build_blob(settings)
    metrics = _build_metrics()
    repo = _build_job_repository()

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
        concurrency=settings.worker_concurrency,
    )

    # Store on app state for dependency injection
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

    logger.info(
        "dependencies.wired",
        queue=settings.queue_backend,
        cache=settings.cache_backend,
        blob=settings.blob_backend,
        async_mode=settings.async_mode,
    )
