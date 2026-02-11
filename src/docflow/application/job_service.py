"""Job service — application-level orchestration for async job management."""

from __future__ import annotations

import mimetypes
from typing import TYPE_CHECKING, Any

try:
    import magic

    _HAS_MAGIC = True
except (ImportError, OSError):
    _HAS_MAGIC = False

import structlog

from docflow.domain.models import (
    ExtractionEngine,
    Job,
    JobFilter,
    JobStatus,
    OCREngine,
    OutputFormat,
    PaginatedResult,
)

if TYPE_CHECKING:
    from docflow.application.config import Settings
    from docflow.domain.ports import BlobStoragePort, JobRepositoryPort, MetricsPort, QueuePort

logger = structlog.get_logger()

JOBS_QUEUE = "docflow:jobs"


class JobService:
    """Manages async document processing jobs.

    - Submit: uploads file to blob storage, enqueues job, returns job_id.
    - Status: reads job state from repository.
    - Cancel/Retry: updates job state.
    """

    def __init__(
        self,
        queue: QueuePort,
        blob: BlobStoragePort,
        repo: JobRepositoryPort,
        metrics: MetricsPort,
        settings: Settings,
    ) -> None:
        self._queue = queue
        self._blob = blob
        self._repo = repo
        self._metrics = metrics
        self._settings = settings

    async def submit(
        self,
        filename: str,
        file_content: bytes,
        output_format: OutputFormat | None = None,
        extraction_engine: ExtractionEngine | None = None,
        ocr_engine: OCREngine | None = None,
        language: str | None = None,
        tenant_id: str | None = None,
        callback_url: str | None = None,
    ) -> Job:
        """Submit a new document processing job."""
        # Detect MIME type
        if _HAS_MAGIC:
            mime_type = magic.from_buffer(file_content, mime=True)
        else:
            guessed, _ = mimetypes.guess_type(filename)
            mime_type = guessed or "application/octet-stream"

        # Create job
        job = Job(
            filename=filename,
            mime_type=mime_type,
            size_bytes=len(file_content),
            output_format=output_format or self._settings.default_output_format,
            extraction_engine=extraction_engine or self._settings.default_extractor,
            ocr_engine=ocr_engine or self._settings.ocr_engine,
            language=language or self._settings.default_language,
            tenant_id=tenant_id,
            callback_url=callback_url,
        )

        # Validate file size
        max_bytes = self._settings.max_file_size_mb * 1024 * 1024
        if len(file_content) > max_bytes:
            job.mark_failed(f"File exceeds maximum size of {self._settings.max_file_size_mb}MB")
            await self._repo.save(job)
            return job

        # Upload file to blob storage
        blob_key = f"inputs/{job.id}/{filename}"
        await self._blob.upload(blob_key, file_content, content_type=mime_type)
        job.blob_key = blob_key

        # Persist job
        await self._repo.save(job)

        # Enqueue for processing
        await self._queue.enqueue(JOBS_QUEUE, {"job_id": job.id})

        self._metrics.counter("jobs.submitted", tags={"format": job.output_format})
        logger.info("job.submitted", job_id=job.id, filename=filename, size=len(file_content))

        return job

    async def get(self, job_id: str) -> Job | None:
        """Get job status by ID."""
        return await self._repo.get(job_id)

    async def list_jobs(
        self,
        status: JobStatus | None = None,
        tenant_id: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> PaginatedResult:
        """List jobs with optional filters and pagination."""
        filter_ = JobFilter(status=status, tenant_id=tenant_id) if status or tenant_id else None
        return await self._repo.list_jobs(filter_=filter_, page=page, page_size=page_size)

    async def cancel(self, job_id: str) -> Job | None:
        """Cancel a pending/queued job."""
        job = await self._repo.get(job_id)
        if not job:
            return None
        if job.status not in (JobStatus.QUEUED, JobStatus.PROCESSING):
            return job  # can't cancel completed/failed/cancelled

        job.mark_cancelled()
        await self._repo.save(job)
        self._metrics.counter("jobs.cancelled")
        logger.info("job.cancelled", job_id=job_id)
        return job

    async def retry(self, job_id: str) -> Job | None:
        """Retry a failed job."""
        job = await self._repo.get(job_id)
        if not job:
            return None
        if not job.can_retry:
            return job

        job.status = JobStatus.QUEUED
        job.error = None
        job.updated_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        await self._repo.save(job)

        # Re-enqueue
        await self._queue.enqueue(JOBS_QUEUE, {"job_id": job.id})

        self._metrics.counter("jobs.retried")
        logger.info("job.retried", job_id=job_id, attempt=job.attempts)
        return job

    async def get_result(self, job_id: str) -> bytes | None:
        """Download the result content for a completed job."""
        job = await self._repo.get(job_id)
        if not job or job.status != JobStatus.COMPLETED or not job.result_key:
            return None
        return await self._blob.download(job.result_key)

    async def submit_batch(
        self,
        files: list[tuple[str, bytes]],
        output_format: OutputFormat | None = None,
        extraction_engine: ExtractionEngine | None = None,
        tenant_id: str | None = None,
    ) -> list[Job]:
        """Submit multiple documents as a batch."""
        jobs = []
        for filename, content in files:
            job = await self.submit(
                filename=filename,
                file_content=content,
                output_format=output_format,
                extraction_engine=extraction_engine,
                tenant_id=tenant_id,
            )
            jobs.append(job)
        self._metrics.counter("jobs.batch_submitted", value=len(jobs))
        return jobs

    async def get_stats(self) -> dict[str, Any]:
        """Get job processing statistics."""
        queue_length = await self._queue.queue_length(JOBS_QUEUE)
        total = await self._repo.count()
        completed = await self._repo.count(JobFilter(status=JobStatus.COMPLETED))
        failed = await self._repo.count(JobFilter(status=JobStatus.FAILED))
        processing = await self._repo.count(JobFilter(status=JobStatus.PROCESSING))
        queued = await self._repo.count(JobFilter(status=JobStatus.QUEUED))

        return {
            "queue_depth": queue_length,
            "total_jobs": total,
            "completed": completed,
            "failed": failed,
            "processing": processing,
            "queued": queued,
        }
