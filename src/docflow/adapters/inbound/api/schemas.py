"""API schemas — Pydantic models for request/response validation."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from docflow.domain.models import DocumentStatus, ExtractionEngine, OCREngine, OutputFormat


class ExtractRequest(BaseModel):
    """Query parameters for extraction (used alongside file upload)."""

    output_format: OutputFormat = OutputFormat.MARKDOWN
    extraction_engine: ExtractionEngine = ExtractionEngine.AUTO
    ocr_engine: OCREngine = OCREngine.TESSERACT
    language: str | None = None


class DocumentResponse(BaseModel):
    """Response schema for a processed document."""

    id: str
    status: DocumentStatus
    filename: str
    mime_type: str
    size_bytes: int
    output_format: OutputFormat
    content: str | None = None
    error: str | None = None
    processing_time_ms: int | None = None
    created_at: datetime
    extraction_engine: str | None = None

    model_config = {"from_attributes": True}


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "healthy"
    version: str
    env: str
    extractors: list[str] = Field(default_factory=list)
    ocr_available: bool = False


class FormatsResponse(BaseModel):
    """Available formats and engines."""

    extraction_engines: list[str]
    ocr_engines: list[str]
    output_formats: list[str]
    max_file_size_mb: int


class ErrorResponse(BaseModel):
    """Standard error response."""

    detail: str
    error_code: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)
