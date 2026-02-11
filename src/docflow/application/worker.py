"""Worker pool — processes jobs from the queue asynchronously."""

from __future__ import annotations

import asyncio
import contextlib
import time
from typing import TYPE_CHECKING, Any

import structlog

from docflow.application.job_service import JOBS_QUEUE
from docflow.domain.models import (
    Document,
    DocumentMetadata,
    Job,
    JobStatus,
)

if TYPE_CHECKING:
    from docflow.application.config import Settings
    from docflow.application.pipeline import ProcessingPipeline
    from docflow.domain.ports import BlobStoragePort, JobRepositoryPort, MetricsPort, QueuePort

logger = structlog.get_logger()


class WorkerPool:
    """Async worker pool that consumes jobs from the queue.

    Architecture:
    - N concurrent workers (bounded by asyncio.Semaphore)
    - Each worker: dequeue → download file → run pipeline → upload result → update job
    - Graceful shutdown via cancel signal
    """

    def __init__(
        self,
        queue: QueuePort,
        blob: BlobStoragePort,
        repo: JobRepositoryPort,
        pipeline: ProcessingPipeline,
        metrics: MetricsPort,
        settings: Settings,
        concurrency: int = 8,
    ) -> None:
        self._queue = queue
        self._blob = blob
        self._repo = repo
        self._pipeline = pipeline
        self._metrics = metrics
        self._settings = settings
        self._concurrency = concurrency
        self._semaphore = asyncio.Semaphore(concurrency)
        self._running = False
        self._tasks: set[asyncio.Task[None]] = set()
        self._poll_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start the worker pool (non-blocking)."""
        self._running = True
        self._poll_task = asyncio.create_task(self._poll_loop())
        logger.info("worker_pool.started", concurrency=self._concurrency)

    async def stop(self) -> None:
        """Gracefully stop the worker pool."""
        self._running = False
        if self._poll_task:
            self._poll_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._poll_task

        # Wait for in-flight tasks
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        logger.info("worker_pool.stopped")

    async def _poll_loop(self) -> None:
        """Main polling loop — dequeues and dispatches work."""
        while self._running:
            try:
                msg = await self._queue.dequeue(JOBS_QUEUE, timeout=1.0)
                if msg is None:
                    continue

                msg_id, payload = msg
                await self._semaphore.acquire()

                task = asyncio.create_task(self._process_message(msg_id, payload))
                self._tasks.add(task)
                task.add_done_callback(self._task_done)

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("worker_pool.poll_error")
                await asyncio.sleep(1)

    def _task_done(self, task: asyncio.Task[None]) -> None:
        """Callback when a worker task completes."""
        self._tasks.discard(task)
        self._semaphore.release()

    async def _process_message(self, msg_id: str, payload: dict[str, Any]) -> None:
        """Process a single job message."""
        job_id = payload.get("job_id", "")
        log = logger.bind(job_id=job_id, msg_id=msg_id)

        try:
            job = await self._repo.get(job_id)
            if not job:
                log.warning("worker.job_not_found")
                await self._queue.acknowledge(JOBS_QUEUE, msg_id)
                return

            if job.status == JobStatus.CANCELLED:
                log.info("worker.job_cancelled_skip")
                await self._queue.acknowledge(JOBS_QUEUE, msg_id)
                return

            # Mark processing
            job.mark_processing()
            await self._repo.save(job)
            log.info("worker.processing_started")

            start_time = time.monotonic()

            # Download input file
            if not job.blob_key:
                raise ValueError("Job has no blob_key")  # noqa: TRY301
            file_content = await self._blob.download(job.blob_key)

            # Build Document entity for pipeline
            document = Document(
                id=job.id,
                metadata=DocumentMetadata(
                    filename=job.filename,
                    mime_type=job.mime_type,
                    size_bytes=job.size_bytes,
                    language=job.language,
                ),
                output_format=job.output_format,
                extraction_engine=job.extraction_engine,
                ocr_engine=job.ocr_engine,
            )

            # Run pipeline
            document = await self._pipeline.run(document, file_content, job.mime_type)

            elapsed_ms = int((time.monotonic() - start_time) * 1000)

            if document.status.value == "completed" and document.processed_content:
                # Upload result
                result_key = f"results/{job.id}/{job.filename}.result"
                await self._blob.upload(result_key, document.processed_content.encode(), "text/plain")

                job.mark_completed(result_key, document.processed_content, elapsed_ms)
                self._metrics.counter("jobs.completed")
                self._metrics.histogram("jobs.processing_time_ms", elapsed_ms)
                log.info("worker.completed", processing_time_ms=elapsed_ms)
            else:
                job.mark_failed(document.error or "Unknown pipeline error")
                self._metrics.counter("jobs.failed")
                log.error("worker.pipeline_failed", error=document.error)

            await self._repo.save(job)
            await self._queue.acknowledge(JOBS_QUEUE, msg_id)

        except Exception as exc:
            log.exception("worker.error", error=str(exc))

            # Try to mark job as failed
            try:
                job = await self._repo.get(job_id)
                if job and job.status != JobStatus.FAILED:
                    job.mark_failed(str(exc))
                    await self._repo.save(job)
            except Exception:
                pass

            await self._queue.reject(JOBS_QUEUE, msg_id)
            self._metrics.counter("jobs.errors")

    async def process_one(self, job_id: str) -> Job | None:
        """Process a single job synchronously (useful for testing).

        Skips the queue — directly processes the job.
        """
        job = await self._repo.get(job_id)
        if not job:
            return None

        await self._process_message("direct", {"job_id": job_id})

        return await self._repo.get(job_id)
