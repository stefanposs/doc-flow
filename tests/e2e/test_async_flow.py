"""E2E tests — asynchronous job management flow.

Covers the ``POST /api/v1/jobs`` (submit), ``GET /api/v1/jobs/{id}``
(poll), and related endpoints for async document processing.

All tests use in-memory adapters — no cloud services required.
The WorkerPool is started in each test to process queued jobs.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from httpx import AsyncClient

    from docflow.application.worker import WorkerPool

pytestmark = [pytest.mark.e2e]

# Maximum seconds to wait for a job to reach terminal state
_POLL_TIMEOUT = 10.0
_POLL_INTERVAL = 0.05


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _submit_job(
    client: AsyncClient,
    filename: str,
    content: bytes,
    mime_type: str,
    output_format: str = "markdown",
) -> dict[str, Any]:
    """Submit a document as an async job.  Returns the response JSON."""
    response = await client.post(
        "/api/v1/jobs",
        files={"file": (filename, content, mime_type)},
        params={"output_format": output_format},
    )
    assert response.status_code == 202, f"Expected 202, got {response.status_code}: {response.text}"
    body = response.json()
    assert "job_id" in body
    return body


async def _start_worker(app: Any) -> WorkerPool:
    """Start the worker pool so queued jobs get processed."""
    worker: WorkerPool = app.state.worker_pool
    await worker.start()
    return worker


async def _stop_worker(worker: WorkerPool) -> None:
    """Stop the worker pool."""
    await worker.stop()


async def _poll_until_done(
    client: AsyncClient,
    job_id: str,
    *,
    timeout: float = _POLL_TIMEOUT,
    interval: float = _POLL_INTERVAL,
) -> dict[str, Any]:
    """Poll GET /api/v1/jobs/{id} until the job reaches a terminal state."""
    terminal_states = {"completed", "failed", "cancelled"}
    elapsed = 0.0
    body: dict[str, Any] = {}

    while elapsed < timeout:
        response = await client.get(f"/api/v1/jobs/{job_id}")
        assert response.status_code == 200
        body = response.json()

        if body["status"] in terminal_states:
            return body

        await asyncio.sleep(interval)
        elapsed += interval

    pytest.fail(f"Job {job_id} did not finish within {timeout}s (last status: {body.get('status')})")
    return {}  # unreachable, for type checker


# ── Submit & poll a single job ───────────────────────────────────────────────


class TestSingleJobFlow:
    """Submit one document, poll until done, download result."""

    async def test_submit_returns_202_with_job_id(
        self, client: AsyncClient, sample_pdf_bytes: bytes
    ) -> None:
        body = await _submit_job(client, "report.pdf", sample_pdf_bytes, "application/pdf")
        assert body["status"] == "queued"

    async def test_poll_until_completed(
        self, client: AsyncClient, app: Any, sample_pdf_bytes: bytes
    ) -> None:
        worker = await _start_worker(app)
        try:
            submitted = await _submit_job(client, "report.pdf", sample_pdf_bytes, "application/pdf")
            result = await _poll_until_done(client, submitted["job_id"])
            assert result["status"] == "completed"
            assert result.get("error") is None
        finally:
            await _stop_worker(worker)

    async def test_download_result(
        self, client: AsyncClient, app: Any, sample_pdf_bytes: bytes
    ) -> None:
        worker = await _start_worker(app)
        try:
            submitted = await _submit_job(client, "report.pdf", sample_pdf_bytes, "application/pdf")
            result = await _poll_until_done(client, submitted["job_id"])
            assert result["status"] == "completed"

            # Download the extracted content
            response = await client.get(f"/api/v1/jobs/{submitted['job_id']}/result")
            assert response.status_code == 200
            assert len(response.text) > 0
        finally:
            await _stop_worker(worker)

    async def test_nonexistent_job_returns_404(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/jobs/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404


# ── Batch submission ─────────────────────────────────────────────────────────


class TestBatchJobFlow:
    """Submit multiple documents and verify all complete successfully."""

    async def test_three_documents_all_complete(
        self,
        client: AsyncClient,
        app: Any,
        sample_pdf_bytes: bytes,
        sample_txt_bytes: bytes,
        sample_html_bytes: bytes,
    ) -> None:
        worker = await _start_worker(app)
        try:
            documents = [
                ("report.pdf", sample_pdf_bytes, "application/pdf"),
                ("notes.txt", sample_txt_bytes, "text/plain"),
                ("page.html", sample_html_bytes, "text/html"),
            ]

            # Submit all three
            job_ids: list[str] = []
            for filename, content, mime in documents:
                submitted = await _submit_job(client, filename, content, mime)
                job_ids.append(submitted["job_id"])

            assert len(job_ids) == 3
            assert len(set(job_ids)) == 3, "Each job must have a unique ID"

            # Poll all until terminal
            results = []
            for job_id in job_ids:
                result = await _poll_until_done(client, job_id)
                results.append(result)

            # All should be completed
            for result in results:
                assert result["status"] == "completed", (
                    f"Job {result.get('id')} ended with status {result['status']}: "
                    f"{result.get('error')}"
                )
        finally:
            await _stop_worker(worker)


# ── Cancel a job ─────────────────────────────────────────────────────────────


class TestCancelJob:
    """Submit a job and attempt to cancel it."""

    async def test_cancel_queued_job(
        self, client: AsyncClient, sample_pdf_bytes: bytes
    ) -> None:
        # Submit without starting worker — job stays queued
        submitted = await _submit_job(client, "report.pdf", sample_pdf_bytes, "application/pdf")
        job_id = submitted["job_id"]

        # Cancel via DELETE
        response = await client.delete(f"/api/v1/jobs/{job_id}")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "cancelled"

    async def test_cancel_nonexistent_job_returns_404(self, client: AsyncClient) -> None:
        response = await client.delete("/api/v1/jobs/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404


# ── Retry a failed job ──────────────────────────────────────────────────────


class TestRetryJob:
    """Retry a failed job."""

    async def test_retry_nonexistent_job_returns_404(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/v1/jobs/00000000-0000-0000-0000-000000000000/retry"
        )
        assert response.status_code == 404
