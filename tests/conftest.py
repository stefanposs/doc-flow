"""Shared test fixtures and fakes."""

from __future__ import annotations

from typing import Any

from docflow.domain.models import (
    ExtractionResult,
    Job,
    JobFilter,
    OutputFormat,
    PaginatedResult,
    ProcessingResult,
)
from docflow.domain.ports import (
    BlobStoragePort,
    CachePort,
    ExtractorPort,
    JobRepositoryPort,
    MetricsPort,
    OCRPort,
    OutputFormatterPort,
    PostProcessorPort,
    QueuePort,
    StoragePort,
)

# ─── Fakes (In-Memory Implementations of Ports) ─────────────


class FakeExtractor(ExtractorPort):
    """In-memory extractor for unit tests."""

    def __init__(self, text: str = "Fake extracted text.", metadata: dict[str, Any] | None = None) -> None:
        self._text = text
        self._metadata = metadata or {}

    async def extract(self, file_content: bytes, mime_type: str) -> ExtractionResult:
        return ExtractionResult(
            text=self._text,
            metadata=self._metadata,
            engine_used="fake",
        )

    def supported_mime_types(self) -> set[str]:
        return {"application/pdf", "text/plain", "image/png"}

    @property
    def name(self) -> str:
        return "fake"


class FakeOCR(OCRPort):
    """In-memory OCR for unit tests."""

    def __init__(self, text: str = "Fake OCR text.") -> None:
        self._text = text

    async def recognize(self, image_content: bytes, language: str = "eng") -> str:
        return self._text

    @property
    def name(self) -> str:
        return "fake_ocr"


class FakePostProcessor(PostProcessorPort):
    """In-memory post-processor for unit tests."""

    def __init__(self, suffix: str = " [processed]") -> None:
        self._suffix = suffix

    async def process(self, text: str, context: dict[str, Any] | None = None) -> str:
        return text + self._suffix

    @property
    def name(self) -> str:
        return "fake_processor"


class FakeFormatter(OutputFormatterPort):
    """In-memory formatter for unit tests."""

    async def format(self, text: str, metadata: dict[str, Any] | None = None) -> ProcessingResult:
        return ProcessingResult(
            content=f"# Formatted\n\n{text}",
            format=OutputFormat.MARKDOWN,
            processors_applied=["fake_formatter"],
        )

    @property
    def output_format(self) -> OutputFormat:
        return OutputFormat.MARKDOWN


class FakeStorage(StoragePort):
    """In-memory storage for unit tests."""

    def __init__(self) -> None:
        self._files: dict[str, bytes] = {}

    async def store(self, key: str, content: bytes, content_type: str = "application/octet-stream") -> str:
        self._files[key] = content
        return f"/fake/{key}"

    async def retrieve(self, key: str) -> bytes:
        if key not in self._files:
            msg = f"File not found: {key}"
            raise FileNotFoundError(msg)
        return self._files[key]

    async def delete(self, key: str) -> None:
        self._files.pop(key, None)

    async def exists(self, key: str) -> bool:
        return key in self._files


# ─── Fakes for Enterprise Ports ──────────────────────────────


class FakeQueue(QueuePort):
    """In-memory queue for testing."""

    def __init__(self) -> None:
        self._messages: list[tuple[str, dict[str, Any]]] = []
        self._counter = 0

    async def enqueue(self, queue_name: str, payload: dict[str, Any]) -> str:
        self._counter += 1
        msg_id = f"msg-{self._counter}"
        self._messages.append((msg_id, payload))
        return msg_id

    async def dequeue(self, queue_name: str, timeout: float = 0) -> tuple[str, dict[str, Any]] | None:
        if self._messages:
            return self._messages.pop(0)
        return None

    async def acknowledge(self, queue_name: str, message_id: str) -> None:
        pass

    async def reject(self, queue_name: str, message_id: str) -> None:
        pass

    async def queue_length(self, queue_name: str) -> int:
        return len(self._messages)

    async def connect(self) -> None:
        pass

    async def disconnect(self) -> None:
        self._messages.clear()


class FakeCache(CachePort):
    """In-memory cache for testing."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def set(self, key: str, value: str, ttl: int | None = None) -> None:
        self._store[key] = value

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)

    async def exists(self, key: str) -> bool:
        return key in self._store

    async def increment(self, key: str) -> int:
        current = int(self._store.get(key, "0"))
        self._store[key] = str(current + 1)
        return current + 1

    async def connect(self) -> None:
        pass

    async def disconnect(self) -> None:
        self._store.clear()


class FakeBlobStorage(BlobStoragePort):
    """In-memory blob storage for testing."""

    def __init__(self) -> None:
        self._blobs: dict[str, tuple[bytes, str]] = {}

    async def upload(self, key: str, content: bytes, content_type: str = "application/octet-stream") -> str:
        self._blobs[key] = (content, content_type)
        return f"fake://{key}"

    async def download(self, key: str) -> bytes:
        if key not in self._blobs:
            msg = f"Blob not found: {key}"
            raise FileNotFoundError(msg)
        return self._blobs[key][0]

    async def delete(self, key: str) -> None:
        self._blobs.pop(key, None)

    async def exists(self, key: str) -> bool:
        return key in self._blobs

    async def list_blobs(self, prefix: str = "") -> list[str]:
        return [k for k in self._blobs if k.startswith(prefix)]

    async def get_metadata(self, key: str) -> dict[str, str]:
        if key not in self._blobs:
            msg = f"Blob not found: {key}"
            raise FileNotFoundError(msg)
        content, ct = self._blobs[key]
        return {"content_type": ct, "size": str(len(content))}

    async def connect(self) -> None:
        pass

    async def disconnect(self) -> None:
        self._blobs.clear()


class FakeJobRepository(JobRepositoryPort):
    """In-memory job repository for testing."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}

    async def save(self, job: Job) -> None:
        import copy

        self._jobs[job.id] = copy.deepcopy(job)

    async def get(self, job_id: str) -> Job | None:
        import copy

        job = self._jobs.get(job_id)
        return copy.deepcopy(job) if job else None

    async def list_jobs(
        self,
        filter_: JobFilter | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> PaginatedResult:
        import copy

        jobs = list(self._jobs.values())
        if filter_ and filter_.status:
            jobs = [j for j in jobs if j.status == filter_.status]
        total = len(jobs)
        start = (page - 1) * page_size
        items = jobs[start : start + page_size]
        return PaginatedResult(
            items=[copy.deepcopy(j) for j in items],
            total=total,
            page=page,
            page_size=page_size,
            has_next=(start + page_size) < total,
        )

    async def delete(self, job_id: str) -> bool:
        return self._jobs.pop(job_id, None) is not None

    async def count(self, filter_: JobFilter | None = None) -> int:
        if not filter_:
            return len(self._jobs)
        jobs = list(self._jobs.values())
        if filter_.status:
            jobs = [j for j in jobs if j.status == filter_.status]
        return len(jobs)


class FakeMetrics(MetricsPort):
    """No-op metrics for testing. Records calls for assertions."""

    def __init__(self) -> None:
        self.counters: dict[str, float] = {}
        self.histograms: list[tuple[str, float]] = []

    def counter(self, name: str, value: float = 1, tags: dict[str, str] | None = None) -> None:
        self.counters[name] = self.counters.get(name, 0) + value

    def histogram(self, name: str, value: float, tags: dict[str, str] | None = None) -> None:
        self.histograms.append((name, value))

    def gauge(self, name: str, value: float, tags: dict[str, str] | None = None) -> None:
        pass
