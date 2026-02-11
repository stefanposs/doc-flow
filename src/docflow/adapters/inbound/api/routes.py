"""API routes — FastAPI endpoints for document extraction."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, UploadFile
from fastapi.responses import PlainTextResponse

from docflow import __version__
from docflow.adapters.inbound.api.schemas import (
    DocumentResponse,
    ErrorResponse,
    FormatsResponse,
    HealthResponse,
)
from docflow.application.service import DocumentService
from docflow.domain.models import DocumentStatus, ExtractionEngine, OCREngine, OutputFormat

router = APIRouter()


def _get_service(request: Request) -> DocumentService:
    """Get DocumentService from app state."""
    return request.app.state.document_service  # type: ignore[no-any-return]


# ─── Health ──────────────────────────────────────────────────


@router.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check(request: Request) -> HealthResponse:
    """Health check endpoint."""
    settings = request.app.state.settings
    extractors = list(request.app.state.extractors.keys())

    return HealthResponse(
        status="healthy",
        version=__version__,
        env=settings.env,
        extractors=extractors,
        ocr_available=settings.ocr_enabled,
    )


# ─── Extraction ──────────────────────────────────────────────


@router.post(
    "/extract",
    response_model=DocumentResponse,
    responses={400: {"model": ErrorResponse}, 413: {"model": ErrorResponse}},
    tags=["Extraction"],
    summary="Extract text from a document",
)
async def extract_document(
    request: Request,
    file: UploadFile,
    output_format: OutputFormat = OutputFormat.MARKDOWN,
    extraction_engine: ExtractionEngine = ExtractionEngine.AUTO,
    ocr_engine: OCREngine = OCREngine.TESSERACT,
    language: str | None = None,
) -> DocumentResponse:
    """Upload a document and extract text.

    Supports PDF, Office documents (DOCX, XLSX, PPTX), images, and more.
    Returns extracted text in the specified output format.
    """
    service = _get_service(request)

    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    # Read file content
    file_content = await file.read()

    if not file_content:
        raise HTTPException(status_code=400, detail="Empty file")

    # Process document
    document = await service.process_document(
        filename=file.filename,
        file_content=file_content,
        output_format=output_format,
        extraction_engine=extraction_engine,
        ocr_engine=ocr_engine,
        language=language,
    )

    if document.status == DocumentStatus.FAILED:
        raise HTTPException(status_code=422, detail=document.error or "Processing failed")

    return DocumentResponse(
        id=document.id,
        status=document.status,
        filename=document.metadata.filename if document.metadata else file.filename,
        mime_type=document.metadata.mime_type if document.metadata else "unknown",
        size_bytes=document.metadata.size_bytes if document.metadata else len(file_content),
        output_format=document.output_format,
        content=document.processed_content,
        processing_time_ms=document.processing_time_ms,
        created_at=document.created_at,
        extraction_engine=document.extraction_engine.value,
    )


@router.post(
    "/extract/raw",
    response_class=PlainTextResponse,
    tags=["Extraction"],
    summary="Extract text and return raw content",
)
async def extract_raw(
    request: Request,
    file: UploadFile,
    output_format: OutputFormat = OutputFormat.MARKDOWN,
    extraction_engine: ExtractionEngine = ExtractionEngine.AUTO,
    language: str | None = None,
) -> PlainTextResponse:
    """Upload a document and get raw extracted text (no JSON wrapper)."""
    service = _get_service(request)

    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    file_content = await file.read()
    if not file_content:
        raise HTTPException(status_code=400, detail="Empty file")

    document = await service.process_document(
        filename=file.filename,
        file_content=file_content,
        output_format=output_format,
        extraction_engine=extraction_engine,
        language=language,
    )

    if document.status == DocumentStatus.FAILED:
        raise HTTPException(status_code=422, detail=document.error or "Processing failed")

    return PlainTextResponse(
        content=document.processed_content or "",
        media_type="text/markdown" if output_format == OutputFormat.MARKDOWN else "text/plain",
    )


# ─── Info ────────────────────────────────────────────────────


@router.get("/formats", response_model=FormatsResponse, tags=["System"])
async def get_formats(request: Request) -> FormatsResponse:
    """Get supported document formats and extraction engines."""
    service = _get_service(request)
    info = service.get_supported_formats()

    return FormatsResponse(**info)
