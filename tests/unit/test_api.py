"""Unit tests for the FastAPI routes."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from docflow.adapters.inbound.api.app import create_app


@pytest.fixture
def client() -> TestClient:
    """Create a test client with fake dependencies."""
    app = create_app()

    # Override dependencies with fakes
    from docflow.adapters.outbound.processors.cleanup import CleanupProcessor
    from docflow.application.config import Settings
    from docflow.application.pipeline import ExtractorRouter, ProcessingPipeline
    from docflow.application.service import DocumentService
    from docflow.domain.models import OutputFormat
    from tests.conftest import FakeExtractor, FakeFormatter

    settings = Settings(tika_url="http://fake:9998", ocr_enabled=False)
    extractors = {"tika": FakeExtractor()}
    router = ExtractorRouter(extractors)
    pipeline = ProcessingPipeline(
        extractor_router=router,
        post_processors=[CleanupProcessor()],
        formatters={OutputFormat.MARKDOWN: FakeFormatter()},
    )
    service = DocumentService(pipeline=pipeline, settings=settings)

    app.state.settings = settings
    app.state.document_service = service
    app.state.extractors = extractors
    app.state.pipeline = pipeline

    return TestClient(app)


class TestHealthEndpoint:
    """Tests for GET /api/v1/health."""

    def test_health_returns_ok(self, client: TestClient) -> None:
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data
        assert "extractors" in data


class TestFormatsEndpoint:
    """Tests for GET /api/v1/formats."""

    def test_formats_returns_engines(self, client: TestClient) -> None:
        response = client.get("/api/v1/formats")
        assert response.status_code == 200
        data = response.json()
        assert "extraction_engines" in data
        assert "ocr_engines" in data
        assert "output_formats" in data


class TestExtractEndpoint:
    """Tests for POST /api/v1/extract."""

    def test_extract_returns_content(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/extract",
            files={"file": ("test.txt", b"Hello World", "text/plain")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["content"] is not None
        assert data["filename"] == "test.txt"

    def test_extract_empty_file_returns_400(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/extract",
            files={"file": ("empty.txt", b"", "text/plain")},
        )
        assert response.status_code == 400

    def test_extract_raw_returns_plain_text(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/extract/raw",
            files={"file": ("test.txt", b"Hello World", "text/plain")},
        )
        assert response.status_code == 200
        assert "text/" in response.headers["content-type"]
