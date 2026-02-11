"""E2E tests — synchronous extraction flow.

Covers the ``POST /api/v1/extract`` and ``POST /api/v1/extract/raw`` endpoints
with realistic file uploads, multiple output formats, and error cases.

All tests run against in-memory adapters — no cloud services required.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from httpx import AsyncClient

pytestmark = [pytest.mark.e2e]


# ── Happy-path: PDF → Markdown ──────────────────────────────────────────────


class TestExtractPDFToMarkdown:
    """Upload a valid PDF via /extract → receive markdown content."""

    async def test_returns_200_with_completed_status(
        self, client: AsyncClient, sample_pdf_bytes: bytes
    ) -> None:
        response = await client.post(
            "/api/v1/extract",
            files={"file": ("report.pdf", sample_pdf_bytes, "application/pdf")},
            params={"output_format": "markdown"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "completed"
        assert body["filename"] == "report.pdf"
        assert body["content"] is not None
        assert len(body["content"]) > 0
        assert body["output_format"] == "markdown"

    async def test_processing_time_is_reported(
        self, client: AsyncClient, sample_pdf_bytes: bytes
    ) -> None:
        response = await client.post(
            "/api/v1/extract",
            files={"file": ("report.pdf", sample_pdf_bytes, "application/pdf")},
        )

        body = response.json()
        assert body["processing_time_ms"] is not None
        assert body["processing_time_ms"] >= 0

    async def test_document_id_is_uuid(
        self, client: AsyncClient, sample_pdf_bytes: bytes
    ) -> None:
        import uuid

        response = await client.post(
            "/api/v1/extract",
            files={"file": ("report.pdf", sample_pdf_bytes, "application/pdf")},
        )

        body = response.json()
        # Should be a valid UUID
        uuid.UUID(body["id"])


# ── /extract/raw → plain text response ──────────────────────────────────────


class TestExtractRaw:
    """Upload via /extract/raw → receive raw text (no JSON envelope)."""

    async def test_returns_plain_text_content(
        self, client: AsyncClient, sample_txt_bytes: bytes
    ) -> None:
        response = await client.post(
            "/api/v1/extract/raw",
            files={"file": ("notes.txt", sample_txt_bytes, "text/plain")},
            params={"output_format": "plaintext"},
        )

        assert response.status_code == 200
        assert "text/" in response.headers["content-type"]
        # The in-memory extractor echoes the input; cleanup processor trims it
        assert len(response.text) > 0

    async def test_raw_markdown_has_correct_media_type(
        self, client: AsyncClient, sample_txt_bytes: bytes
    ) -> None:
        response = await client.post(
            "/api/v1/extract/raw",
            files={"file": ("notes.txt", sample_txt_bytes, "text/plain")},
            params={"output_format": "markdown"},
        )

        assert response.status_code == 200
        assert "text/markdown" in response.headers["content-type"]


# ── Unsupported / invalid inputs ─────────────────────────────────────────────


class TestErrorHandling:
    """Error scenarios produce proper HTTP error responses."""

    async def test_empty_file_returns_400(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/v1/extract",
            files={"file": ("empty.pdf", b"", "application/pdf")},
        )

        assert response.status_code == 400
        body = response.json()
        assert "detail" in body

    async def test_missing_file_returns_422(self, client: AsyncClient) -> None:
        """Omitting the file field entirely is a validation error."""
        response = await client.post("/api/v1/extract")
        assert response.status_code == 422

    async def test_no_filename_returns_400(self, client: AsyncClient) -> None:
        """A file with empty filename should be rejected."""
        response = await client.post(
            "/api/v1/extract",
            files={"file": ("", b"some content", "application/octet-stream")},
        )

        # FastAPI should reject or our route guard catches empty filename
        assert response.status_code in {400, 422}


# ── Multiple output formats ──────────────────────────────────────────────────


class TestMultipleOutputFormats:
    """The same document extracted in different output formats."""

    @pytest.mark.parametrize(
        "output_format",
        ["markdown", "plaintext", "json"],
    )
    async def test_format_is_respected(
        self, client: AsyncClient, sample_txt_bytes: bytes, output_format: str
    ) -> None:
        response = await client.post(
            "/api/v1/extract",
            files={"file": ("doc.txt", sample_txt_bytes, "text/plain")},
            params={"output_format": output_format},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["output_format"] == output_format
        assert body["content"] is not None

    async def test_json_format_contains_valid_json_content(
        self, client: AsyncClient, sample_txt_bytes: bytes
    ) -> None:
        response = await client.post(
            "/api/v1/extract",
            files={"file": ("doc.txt", sample_txt_bytes, "text/plain")},
            params={"output_format": "json"},
        )

        body = response.json()
        # The content field should itself be valid JSON (from JSONFormatter)
        inner = json.loads(body["content"])
        assert "content" in inner

    async def test_plaintext_format_has_no_markdown_artifacts(
        self, client: AsyncClient, sample_txt_bytes: bytes
    ) -> None:
        response = await client.post(
            "/api/v1/extract",
            files={"file": ("doc.txt", sample_txt_bytes, "text/plain")},
            params={"output_format": "plaintext"},
        )

        body = response.json()
        content = body["content"]
        # PlainTextFormatter passes text through unchanged
        assert "---" not in content  # no YAML front matter


# ── HTML input ───────────────────────────────────────────────────────────────


class TestHTMLExtraction:
    """HTML documents go through the same pipeline."""

    async def test_html_extraction_succeeds(
        self, client: AsyncClient, sample_html_bytes: bytes
    ) -> None:
        response = await client.post(
            "/api/v1/extract",
            files={"file": ("page.html", sample_html_bytes, "text/html")},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "completed"
        assert body["content"] is not None


# ── Idempotency / isolation ──────────────────────────────────────────────────


class TestIsolation:
    """Each request is independent — no state leaks between calls."""

    async def test_two_sequential_extractions_are_independent(
        self, client: AsyncClient, sample_txt_bytes: bytes, sample_pdf_bytes: bytes
    ) -> None:
        r1 = await client.post(
            "/api/v1/extract",
            files={"file": ("a.txt", sample_txt_bytes, "text/plain")},
        )
        r2 = await client.post(
            "/api/v1/extract",
            files={"file": ("b.pdf", sample_pdf_bytes, "application/pdf")},
        )

        assert r1.status_code == 200
        assert r2.status_code == 200

        b1, b2 = r1.json(), r2.json()
        assert b1["id"] != b2["id"]
        assert b1["filename"] == "a.txt"
        assert b2["filename"] == "b.pdf"
