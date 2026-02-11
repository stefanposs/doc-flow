"""API routes for async job management."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Request, UploadFile
from fastapi.responses import PlainTextResponse

from docflow.adapters.inbound.api.job_schemas import (
    BatchSubmitResponse,
    JobListResponse,
    JobStatsResponse,
    JobStatusResponse,
    JobSubmitResponse,
)
from docflow.domain.models import ExtractionEngine, JobStatus, OCREngine, OutputFormat

if TYPE_CHECKING:
    from docflow.application.job_service import JobService

job_router = APIRouter(prefix="/jobs", tags=["Jobs"])


def _get_job_service(request: Request) -> JobService:
    """Get JobService from app state."""
    return request.app.state.job_service  # type: ignore[no-any-return]


def _job_to_response(job: object) -> JobStatusResponse:
    """Convert a Job domain object to API response."""
    from docflow.domain.models import Job

    assert isinstance(job, Job)
    return JobStatusResponse(
        id=job.id,
        status=job.status,
        filename=job.filename,
        mime_type=job.mime_type,
        size_bytes=job.size_bytes,
        output_format=job.output_format,
        extraction_engine=job.extraction_engine,
        result_content=job.result_content,
        error=job.error,
        attempts=job.attempts,
        max_attempts=job.max_attempts,
        processing_time_ms=job.processing_time_ms,
        created_at=job.created_at,
        updated_at=job.updated_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
    )


# ─── Submit ───────────────────────────────────────────────────


@job_router.post("", response_model=JobSubmitResponse, status_code=202, summary="Submit a document for processing")
async def submit_job(
    request: Request,
    file: UploadFile,
    output_format: OutputFormat = OutputFormat.MARKDOWN,
    extraction_engine: ExtractionEngine = ExtractionEngine.AUTO,
    ocr_engine: OCREngine = OCREngine.TESSERACT,
    language: str | None = None,
) -> JobSubmitResponse:
    """Submit a document for async processing.

    Returns immediately with a job_id. Poll GET /jobs/{id} for status.
    """
    svc = _get_job_service(request)

    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    job = await svc.submit(
        filename=file.filename,
        file_content=content,
        output_format=output_format,
        extraction_engine=extraction_engine,
        ocr_engine=ocr_engine,
        language=language,
    )

    if job.status.value == "failed":
        raise HTTPException(status_code=422, detail=job.error or "Submission failed")

    return JobSubmitResponse(
        job_id=job.id,
        status=job.status,
        filename=job.filename,
    )


# ─── Batch Submit ─────────────────────────────────────────────


@job_router.post(
    "/batch",
    response_model=BatchSubmitResponse,
    status_code=202,
    summary="Submit multiple documents",
)
async def submit_batch(
    request: Request,
    files: list[UploadFile],
    output_format: OutputFormat = OutputFormat.MARKDOWN,
    extraction_engine: ExtractionEngine = ExtractionEngine.AUTO,
) -> BatchSubmitResponse:
    """Submit a batch of documents for async processing."""
    svc = _get_job_service(request)

    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    file_pairs: list[tuple[str, bytes]] = []
    for f in files:
        if not f.filename:
            raise HTTPException(status_code=400, detail="All files must have filenames")
        content = await f.read()
        if not content:
            raise HTTPException(status_code=400, detail=f"Empty file: {f.filename}")
        file_pairs.append((f.filename, content))

    jobs = await svc.submit_batch(
        files=file_pairs,
        output_format=output_format,
        extraction_engine=extraction_engine,
    )

    return BatchSubmitResponse(
        jobs=[
            JobSubmitResponse(job_id=j.id, status=j.status, filename=j.filename)
            for j in jobs
        ],
        total=len(jobs),
    )


# ─── Status ───────────────────────────────────────────────────


@job_router.get("/{job_id}", response_model=JobStatusResponse, summary="Get job status")
async def get_job_status(request: Request, job_id: str) -> JobStatusResponse:
    """Get the current status and result of a job."""
    svc = _get_job_service(request)
    job = await svc.get(job_id)

    if not job:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    return _job_to_response(job)


# ─── List ─────────────────────────────────────────────────────


@job_router.get("", response_model=JobListResponse, summary="List jobs")
async def list_jobs(
    request: Request,
    status: JobStatus | None = None,
    page: int = 1,
    page_size: int = 50,
) -> JobListResponse:
    """List jobs with optional status filter and pagination."""
    svc = _get_job_service(request)
    result = await svc.list_jobs(status=status, page=page, page_size=page_size)

    return JobListResponse(
        items=[_job_to_response(j) for j in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
        has_next=result.has_next,
    )


# ─── Cancel ───────────────────────────────────────────────────


@job_router.delete("/{job_id}", response_model=JobStatusResponse, summary="Cancel a job")
async def cancel_job(request: Request, job_id: str) -> JobStatusResponse:
    """Cancel a queued or processing job."""
    svc = _get_job_service(request)
    job = await svc.cancel(job_id)

    if not job:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    return _job_to_response(job)


# ─── Retry ────────────────────────────────────────────────────


@job_router.post("/{job_id}/retry", response_model=JobStatusResponse, summary="Retry a failed job")
async def retry_job(request: Request, job_id: str) -> JobStatusResponse:
    """Retry a failed job (if attempts < max_attempts)."""
    svc = _get_job_service(request)
    job = await svc.retry(job_id)

    if not job:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    if job.status.value == "failed" and not job.can_retry:
        raise HTTPException(status_code=409, detail="Job has exceeded maximum retry attempts")

    return _job_to_response(job)


# ─── Result ───────────────────────────────────────────────────


@job_router.get("/{job_id}/result", response_class=PlainTextResponse, summary="Download job result")
async def get_job_result(request: Request, job_id: str) -> PlainTextResponse:
    """Download the processed result of a completed job."""
    svc = _get_job_service(request)
    job = await svc.get(job_id)

    if not job:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    if job.status.value != "completed":
        raise HTTPException(status_code=409, detail=f"Job is not completed (status: {job.status})")

    if job.result_content:
        return PlainTextResponse(content=job.result_content)

    result = await svc.get_result(job_id)
    if not result:
        raise HTTPException(status_code=404, detail="Result not available")

    return PlainTextResponse(content=result.decode())


# ─── Stats ────────────────────────────────────────────────────


@job_router.get("/stats/overview", response_model=JobStatsResponse, summary="Get job statistics")
async def get_stats(request: Request) -> JobStatsResponse:
    """Get processing statistics and queue depth."""
    svc = _get_job_service(request)
    stats = await svc.get_stats()
    return JobStatsResponse(**stats)
