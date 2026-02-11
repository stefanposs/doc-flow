"""E2E tests — concurrency and scale.

Verifies the pipeline handles concurrent document submissions without
data corruption, lost results, or excessive latency.

All tests use in-memory adapters — no cloud services required.
Timeout is set conservatively for CI; locally these finish in <5 s.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from httpx import AsyncClient

pytestmark = [pytest.mark.e2e, pytest.mark.timeout(60)]

_CONCURRENT_DOCS = 50


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_unique_content(index: int) -> bytes:
    """Generate a distinct text payload so we can verify no cross-contamination."""
    return f"Document #{index:04d} — unique payload for corruption check.".encode()


async def _extract_one(
    client: AsyncClient, index: int
) -> tuple[int, dict]:
    """Submit a single sync extraction and return (index, response_json)."""
    content = _make_unique_content(index)
    response = await client.post(
        "/api/v1/extract",
        files={"file": (f"doc_{index:04d}.txt", content, "text/plain")},
        params={"output_format": "plaintext"},
    )
    return index, {"status_code": response.status_code, "body": response.json()}


# ── Concurrent sync extractions ──────────────────────────────────────────────


class TestConcurrentSyncExtractions:
    """Submit many documents concurrently via the sync /extract endpoint."""

    async def test_all_documents_complete_successfully(
        self, client: AsyncClient
    ) -> None:
        """50 concurrent extractions all return 200 / completed."""
        tasks = [_extract_one(client, i) for i in range(_CONCURRENT_DOCS)]
        results = await asyncio.gather(*tasks)

        successes = [
            (idx, r) for idx, r in results if r["status_code"] == 200
        ]
        failures = [
            (idx, r)
            for idx, r in results
            if r["status_code"] != 200
        ]

        assert len(failures) == 0, (
            f"{len(failures)} of {_CONCURRENT_DOCS} requests failed: "
            f"{[(idx, r['status_code']) for idx, r in failures[:5]]}"
        )
        assert len(successes) == _CONCURRENT_DOCS

        # All should be completed
        for idx, r in successes:
            assert r["body"]["status"] == "completed", (
                f"Doc {idx} status={r['body']['status']}"
            )

    async def test_no_data_corruption(self, client: AsyncClient) -> None:
        """Each response contains content derived from *its own* input.

        The InMemoryExtractor echoes the decoded input text, so we can check
        that each result contains the unique marker for its index.
        """
        tasks = [_extract_one(client, i) for i in range(_CONCURRENT_DOCS)]
        results = await asyncio.gather(*tasks)

        for idx, r in results:
            assert r["status_code"] == 200
            content: str = r["body"]["content"]
            expected_marker = f"Document #{idx:04d}"
            assert expected_marker in content, (
                f"Corruption: doc {idx} result does not contain its marker.\n"
                f"  Expected substring: {expected_marker!r}\n"
                f"  Got: {content[:120]!r}"
            )

    async def test_all_document_ids_are_unique(self, client: AsyncClient) -> None:
        """No two responses share the same document ID."""
        tasks = [_extract_one(client, i) for i in range(_CONCURRENT_DOCS)]
        results = await asyncio.gather(*tasks)

        ids = [r["body"]["id"] for _, r in results if r["status_code"] == 200]
        assert len(ids) == len(set(ids)), "Duplicate document IDs detected"


# ── Throughput / latency baseline ────────────────────────────────────────────


class TestLatencyBaseline:
    """Sanity-check that in-memory pipeline latency stays sub-second per doc."""

    async def test_single_extraction_under_500ms(
        self, client: AsyncClient, sample_txt_bytes: bytes
    ) -> None:
        """A single sync extraction should finish well under 500 ms."""
        response = await client.post(
            "/api/v1/extract",
            files={"file": ("quick.txt", sample_txt_bytes, "text/plain")},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["processing_time_ms"] is not None
        assert body["processing_time_ms"] < 500, (
            f"Pipeline too slow: {body['processing_time_ms']} ms"
        )

    async def test_batch_50_under_30_seconds(self, client: AsyncClient) -> None:
        """50 concurrent extractions complete within the overall budget."""
        import time

        start = time.monotonic()

        tasks = [_extract_one(client, i) for i in range(_CONCURRENT_DOCS)]
        results = await asyncio.gather(*tasks)

        elapsed = time.monotonic() - start

        success_count = sum(1 for _, r in results if r["status_code"] == 200)
        assert success_count == _CONCURRENT_DOCS
        assert elapsed < 30.0, f"Batch took {elapsed:.1f}s — exceeds 30s budget"
