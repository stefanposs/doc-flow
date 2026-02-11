"""API schemas for job management."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from docflow.domain.models import ExtractionEngine, JobStatus, OutputFormat


class JobSubmitResponse(BaseModel):
    """Response after submitting a job."""

    job_id: str
    status: JobStatus
    filename: str
    message: str = "Job submitted successfully"


class JobStatusResponse(BaseModel):
    """Full job status response."""

    id: str
    status: JobStatus
    filename: str
    mime_type: str
    size_bytes: int
    output_format: OutputFormat
    extraction_engine: ExtractionEngine
    result_content: str | None = None
    error: str | None = None
    attempts: int = 0
    max_attempts: int = 3
    processing_time_ms: int | None = None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}


class BatchSubmitRequest(BaseModel):
    """Request body for batch file submission (metadata only — files via multipart)."""

    output_format: OutputFormat = OutputFormat.MARKDOWN
    extraction_engine: ExtractionEngine = ExtractionEngine.AUTO


class BatchSubmitResponse(BaseModel):
    """Response for batch submission."""

    jobs: list[JobSubmitResponse]
    total: int
    message: str = "Batch submitted successfully"


class JobListResponse(BaseModel):
    """Paginated list of jobs."""

    items: list[JobStatusResponse]
    total: int
    page: int
    page_size: int
    has_next: bool


class JobStatsResponse(BaseModel):
    """Job processing statistics."""

    queue_depth: int
    total_jobs: int
    completed: int
    failed: int
    processing: int
    queued: int
