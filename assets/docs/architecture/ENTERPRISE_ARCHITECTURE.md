# DocFlow Enterprise Architecture — Design Document

**Version:** 2.0  
**Date:** 2026-02-11  
**Status:** Proposed  
**Author:** Architecture Review  

---

## 1. Executive Summary

This document defines the architecture evolution of DocFlow from a synchronous MVP into a **production enterprise platform** capable of processing **1M+ documents/day**. The design preserves the existing hexagonal architecture (ports & adapters), keeps the domain layer pure, and adds four new port interfaces with pluggable adapters for queuing, caching, blob storage, and observability.

### Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Async job processing | ARQ (Redis-backed) + custom WorkerPool | Proven Python async worker; Redis Streams for local dev |
| Configuration | pydantic-settings, `DOCFLOW_` prefix | Already established pattern |
| Multi-tenancy | Tenant ID header + per-tenant rate limits, row-level isolation | Enterprise-ready without DB-per-tenant complexity |
| Local testing | In-memory adapters for every port | Zero cloud dependencies for E2E tests |
| API versioning | `/api/v1/` prefix (existing) | Non-breaking evolution |

---

## 2. System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        INBOUND ADAPTERS                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────────────────┐  │
│  │ REST API │  │   CLI    │  │ gRPC     │  │ Webhook Receiver   │  │
│  │ (FastAPI)│  │ (Typer)  │  │ (future) │  │ (future)           │  │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────────┬───────────┘  │
│       │              │              │                 │              │
├───────┴──────────────┴──────────────┴─────────────────┴──────────────┤
│                      APPLICATION LAYER                               │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────────┐        │
│  │DocumentService│  │  JobService  │  │ ProcessingPipeline  │        │
│  │  (existing)  │  │    (new)     │  │    (existing)       │        │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬──────────┘        │
│         │                 │                      │                   │
├─────────┴─────────────────┴──────────────────────┴───────────────────┤
│                         DOMAIN LAYER (pure)                          │
│  ┌────────┐  ┌────────┐  ┌──────────────────────────────────┐       │
│  │ Models │  │ Events │  │ Ports (ABC interfaces)            │       │
│  │        │  │        │  │ ExtractorPort   OCRPort           │       │
│  │        │  │        │  │ PostProcessorPort                 │       │
│  │        │  │        │  │ OutputFormatterPort  StoragePort  │       │
│  │        │  │        │  │ ──── NEW ────────────────────     │       │
│  │        │  │        │  │ QueuePort       CachePort         │       │
│  │        │  │        │  │ BlobStoragePort MetricsPort       │       │
│  │        │  │        │  │ EventBusPort                      │       │
│  └────────┘  └────────┘  └──────────────────────────────────┘       │
│                                                                      │
├──────────────────────────────────────────────────────────────────────┤
│                      OUTBOUND ADAPTERS                               │
│  ┌─────────┐ ┌─────────┐ ┌──────────┐ ┌──────────┐ ┌─────────────┐ │
│  │Extractor│ │  Queue  │ │  Cache   │ │BlobStore │ │  Metrics    │ │
│  │Tika     │ │Redis    │ │Redis     │ │S3        │ │Prometheus   │ │
│  │PyMuPDF  │ │PubSub   │ │Memcached │ │GCS       │ │Datadog      │ │
│  │         │ │AzureSB  │ │InMemory  │ │AzureBlob │ │CloudWatch   │ │
│  │         │ │InMemory │ │          │ │Local FS  │ │InMemory     │ │
│  └─────────┘ └─────────┘ └──────────┘ └──────────┘ └─────────────┘ │
│  ┌─────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────────────┐ │
│  │   OCR   │ │Formatter │ │Processor │ │   Storage (existing)     │ │
│  │Tesseract│ │Markdown  │ │Cleanup   │ │   LocalStorage           │ │
│  │         │ │JSON      │ │          │ │                          │ │
│  └─────────┘ └──────────┘ └──────────┘ └──────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 3. New Domain Models

Added to `domain/models.py`. The existing `Document`, `DocumentStatus`, etc. remain unchanged.

```python
# ── domain/models.py (additions) ─────────────────────────────

class JobStatus(StrEnum):
    """Lifecycle of an async processing job."""
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"

class JobPriority(StrEnum):
    """Job processing priority."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"

@dataclass
class Job:
    """Async processing job wrapping a Document extraction request."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str = "default"
    status: JobStatus = JobStatus.QUEUED
    priority: JobPriority = JobPriority.NORMAL

    # Input
    filename: str = ""
    mime_type: str = ""
    blob_key: str = ""              # key in BlobStoragePort where input file lives
    output_format: OutputFormat = OutputFormat.MARKDOWN
    extraction_engine: ExtractionEngine = ExtractionEngine.AUTO
    ocr_engine: OCREngine = OCREngine.TESSERACT
    language: str = "eng"

    # Output
    document_id: str | None = None  # resulting Document.id after processing
    result_blob_key: str | None = None  # BlobStoragePort key for output
    error: str | None = None

    # Lifecycle
    attempts: int = 0
    max_retries: int = 3
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Webhook
    callback_url: str | None = None

    # Batch
    batch_id: str | None = None

@dataclass
class JobFilter:
    """Query filter for listing jobs."""
    tenant_id: str | None = None
    status: JobStatus | None = None
    batch_id: str | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None

@dataclass
class Page:
    """Pagination wrapper."""
    items: list[Any] = field(default_factory=list)
    total: int = 0
    offset: int = 0
    limit: int = 50
    has_more: bool = False
```

---

## 4. New Domain Events

Added to `domain/events.py`:

```python
# ── domain/events.py (additions) ─────────────────────────────

@dataclass(frozen=True)
class JobQueued(DomainEvent):
    """Emitted when a job is submitted to the queue."""
    job_id: str = ""
    tenant_id: str = ""
    priority: str = "normal"

@dataclass(frozen=True)
class JobStarted(DomainEvent):
    """Emitted when a worker picks up a job."""
    job_id: str = ""
    worker_id: str = ""

@dataclass(frozen=True)
class JobCompleted(DomainEvent):
    """Emitted when a job finishes successfully."""
    job_id: str = ""
    document_id: str = ""
    processing_time_ms: int = 0

@dataclass(frozen=True)
class JobFailed(DomainEvent):
    """Emitted when a job fails after all retries."""
    job_id: str = ""
    error: str = ""
    attempt: int = 0

@dataclass(frozen=True)
class JobCancelled(DomainEvent):
    """Emitted when a job is cancelled by the user."""
    job_id: str = ""

@dataclass(frozen=True)
class BatchCompleted(DomainEvent):
    """Emitted when all jobs in a batch are finished."""
    batch_id: str = ""
    total_jobs: int = 0
    succeeded: int = 0
    failed: int = 0
```

---

## 5. New Port Interfaces

All new ports go into `domain/ports.py` alongside the existing five ports. Each port is a pure ABC with no dependencies on any adapter library.

### 5.1 QueuePort

```python
class QueuePort(ABC):
    """Port for async message/job queue.

    Implementations: RedisStreamQueue, PubSubQueue, AzureServiceBusQueue,
                     RabbitMQQueue, InMemoryQueue
    """

    @abstractmethod
    async def enqueue(
        self, queue_name: str, payload: dict[str, Any], priority: int = 0
    ) -> str:
        """Add a message to the queue. Returns message ID."""

    @abstractmethod
    async def dequeue(
        self, queue_name: str, timeout: float = 30.0
    ) -> tuple[str, dict[str, Any]] | None:
        """Blocking dequeue. Returns (message_id, payload) or None on timeout."""

    @abstractmethod
    async def acknowledge(self, queue_name: str, message_id: str) -> None:
        """Acknowledge successful processing of a message."""

    @abstractmethod
    async def reject(
        self, queue_name: str, message_id: str, requeue: bool = True
    ) -> None:
        """Reject/nack a message, optionally re-queuing it."""

    @abstractmethod
    async def queue_length(self, queue_name: str) -> int:
        """Return approximate number of pending messages."""

    @abstractmethod
    async def purge(self, queue_name: str) -> int:
        """Remove all messages from a queue. Returns count removed."""

    @abstractmethod
    async def connect(self) -> None:
        """Initialize connection to the queue backend."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Gracefully close the connection."""
```

### 5.2 CachePort

```python
class CachePort(ABC):
    """Port for caching (extraction results, job state, dedup).

    Implementations: RedisCacheAdapter, MemcachedAdapter, InMemoryCacheAdapter
    """

    @abstractmethod
    async def get(self, key: str) -> bytes | None:
        """Get a cached value. Returns None on miss."""

    @abstractmethod
    async def set(
        self, key: str, value: bytes, ttl_seconds: int | None = None
    ) -> None:
        """Set a cached value with optional TTL."""

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Delete a key. Returns True if existed."""

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if a key exists."""

    @abstractmethod
    async def increment(self, key: str, amount: int = 1) -> int:
        """Atomic increment. Used for rate limiting counters."""

    @abstractmethod
    async def expire(self, key: str, ttl_seconds: int) -> None:
        """Set/update TTL on an existing key."""

    @abstractmethod
    async def get_json(self, key: str) -> dict[str, Any] | None:
        """Convenience: get + JSON deserialize."""

    @abstractmethod
    async def set_json(
        self, key: str, value: dict[str, Any], ttl_seconds: int | None = None
    ) -> None:
        """Convenience: JSON serialize + set."""
```

### 5.3 BlobStoragePort

```python
class BlobStoragePort(ABC):
    """Port for cloud object/blob storage.

    Unlike StoragePort (which is for local file I/O), BlobStoragePort handles
    large-scale cloud storage with presigned URLs, multipart uploads, and metadata.

    Implementations: S3BlobAdapter, GCSBlobAdapter, AzureBlobAdapter,
                     LocalFSBlobAdapter (testing)
    """

    @abstractmethod
    async def upload(
        self,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> str:
        """Upload a blob. Returns the storage URI/key."""

    @abstractmethod
    async def download(self, key: str) -> bytes:
        """Download a blob by key.

        Raises:
            FileNotFoundError: If the key does not exist.
        """

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete a blob."""

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if a blob exists."""

    @abstractmethod
    async def get_presigned_url(
        self, key: str, expires_in: int = 3600
    ) -> str:
        """Generate a presigned/SAS download URL.

        Args:
            key: Blob key.
            expires_in: URL validity in seconds.
        """

    @abstractmethod
    async def get_upload_url(
        self, key: str, content_type: str, expires_in: int = 3600
    ) -> str:
        """Generate a presigned/SAS upload URL for client-side uploads."""

    @abstractmethod
    async def list_blobs(
        self, prefix: str, max_keys: int = 1000
    ) -> list[str]:
        """List blob keys under a prefix."""

    @abstractmethod
    async def get_metadata(self, key: str) -> dict[str, str]:
        """Get blob metadata without downloading the content."""
```

### 5.4 MetricsPort

```python
class MetricsPort(ABC):
    """Port for application metrics/observability.

    Implementations: PrometheusMetricsAdapter, DatadogMetricsAdapter,
                     CloudWatchMetricsAdapter, InMemoryMetricsAdapter
    """

    @abstractmethod
    def counter(self, name: str, value: float = 1.0, tags: dict[str, str] | None = None) -> None:
        """Increment a counter metric."""

    @abstractmethod
    def gauge(self, name: str, value: float, tags: dict[str, str] | None = None) -> None:
        """Set a gauge metric."""

    @abstractmethod
    def histogram(self, name: str, value: float, tags: dict[str, str] | None = None) -> None:
        """Record a histogram observation (e.g., latency)."""

    @abstractmethod
    def timer(self, name: str, tags: dict[str, str] | None = None) -> Any:
        """Return a context manager that records elapsed time as a histogram.

        Usage:
            with metrics.timer("pipeline.duration"):
                await pipeline.run(...)
        """
```

### 5.5 EventBusPort

```python
class EventBusPort(ABC):
    """Port for internal domain event publishing (decoupled from queue).

    Used for: webhook dispatch, audit logging, metrics emission.
    Implementations: InProcessEventBus, RedisEventBus
    """

    @abstractmethod
    async def publish(self, event: "DomainEvent") -> None:
        """Publish a domain event."""

    @abstractmethod
    async def subscribe(
        self, event_type: type, handler: Any  # Callable[[DomainEvent], Awaitable[None]]
    ) -> None:
        """Subscribe a handler to a specific event type."""
```

### 5.6 JobRepositoryPort

```python
class JobRepositoryPort(ABC):
    """Port for persisting and querying Job state.

    Implementations: RedisJobRepository, PostgresJobRepository,
                     InMemoryJobRepository
    """

    @abstractmethod
    async def save(self, job: "Job") -> None:
        """Persist or update a job."""

    @abstractmethod
    async def get(self, job_id: str) -> "Job | None":
        """Retrieve a job by ID."""

    @abstractmethod
    async def list_jobs(
        self, filter: "JobFilter", offset: int = 0, limit: int = 50
    ) -> "Page":
        """List jobs matching the filter with pagination."""

    @abstractmethod
    async def delete(self, job_id: str) -> bool:
        """Delete a job. Returns True if it existed."""

    @abstractmethod
    async def count(self, filter: "JobFilter") -> int:
        """Count jobs matching the filter."""
```

---

## 6. Adapter Implementations

### 6.1 Adapter Matrix

| Port | Adapter Class | Library | Location | Notes |
|------|--------------|---------|----------|-------|
| **QueuePort** | `RedisStreamQueue` | `redis[hiredis]>=5.0` | `adapters/outbound/queue/redis_stream.py` | Production default |
| | `PubSubQueue` | `google-cloud-pubsub>=2.23` | `adapters/outbound/queue/pubsub.py` | GCP |
| | `AzureServiceBusQueue` | `azure-servicebus>=7.12` | `adapters/outbound/queue/azure_sb.py` | Azure |
| | `RabbitMQQueue` | `aio-pika>=9.4` | `adapters/outbound/queue/rabbitmq.py` | AMQP |
| | `InMemoryQueue` | stdlib `asyncio.Queue` | `adapters/outbound/queue/memory.py` | Testing |
| **CachePort** | `RedisCacheAdapter` | `redis[hiredis]>=5.0` | `adapters/outbound/cache/redis_cache.py` | Production default |
| | `MemcachedAdapter` | `aiomcache>=0.8` | `adapters/outbound/cache/memcached.py` | Alternative |
| | `InMemoryCacheAdapter` | stdlib `dict` + TTL | `adapters/outbound/cache/memory.py` | Testing |
| **BlobStoragePort** | `S3BlobAdapter` | `aiobotocore>=2.13` | `adapters/outbound/blob/s3.py` | AWS / MinIO |
| | `GCSBlobAdapter` | `gcloud-aio-storage>=9.3` | `adapters/outbound/blob/gcs.py` | GCP |
| | `AzureBlobAdapter` | `azure-storage-blob[aio]>=12.23` | `adapters/outbound/blob/azure_blob.py` | Azure |
| | `LocalFSBlobAdapter` | stdlib `pathlib` / `aiofiles` | `adapters/outbound/blob/local_fs.py` | Testing / dev |
| **MetricsPort** | `PrometheusMetricsAdapter` | `prometheus-client>=0.21` | `adapters/outbound/metrics/prometheus.py` | Self-hosted |
| | `DatadogMetricsAdapter` | `datadog>=0.50` | `adapters/outbound/metrics/datadog.py` | SaaS |
| | `CloudWatchMetricsAdapter` | `aiobotocore>=2.13` | `adapters/outbound/metrics/cloudwatch.py` | AWS |
| | `InMemoryMetricsAdapter` | stdlib `dict` | `adapters/outbound/metrics/memory.py` | Testing |
| **EventBusPort** | `InProcessEventBus` | stdlib `dict[type, list]` | `adapters/outbound/events/in_process.py` | Default |
| | `RedisEventBus` | `redis>=5.0` | `adapters/outbound/events/redis_bus.py` | Distributed |
| **JobRepositoryPort** | `RedisJobRepository` | `redis>=5.0` | `adapters/outbound/jobs/redis_repo.py` | Production default |
| | `InMemoryJobRepository` | stdlib `dict` | `adapters/outbound/jobs/memory_repo.py` | Testing |

### 6.2 In-Memory Adapter Examples (Testing Fallbacks)

#### InMemoryQueue

```python
# adapters/outbound/queue/memory.py

import asyncio
import uuid
from typing import Any
from docflow.domain.ports import QueuePort


class InMemoryQueue(QueuePort):
    """In-memory queue for testing. Uses asyncio.Queue per queue name."""

    def __init__(self) -> None:
        self._queues: dict[str, asyncio.Queue[tuple[str, dict[str, Any]]]] = {}
        self._unacked: dict[str, dict[str, dict[str, Any]]] = {}

    async def connect(self) -> None:
        pass  # No-op

    async def disconnect(self) -> None:
        self._queues.clear()
        self._unacked.clear()

    def _get_queue(self, name: str) -> asyncio.Queue[tuple[str, dict[str, Any]]]:
        if name not in self._queues:
            self._queues[name] = asyncio.Queue()
            self._unacked[name] = {}
        return self._queues[name]

    async def enqueue(self, queue_name: str, payload: dict[str, Any], priority: int = 0) -> str:
        msg_id = str(uuid.uuid4())
        await self._get_queue(queue_name).put((msg_id, payload))
        return msg_id

    async def dequeue(self, queue_name: str, timeout: float = 30.0) -> tuple[str, dict[str, Any]] | None:
        try:
            msg_id, payload = await asyncio.wait_for(
                self._get_queue(queue_name).get(), timeout=timeout
            )
            self._unacked.setdefault(queue_name, {})[msg_id] = payload
            return msg_id, payload
        except asyncio.TimeoutError:
            return None

    async def acknowledge(self, queue_name: str, message_id: str) -> None:
        self._unacked.get(queue_name, {}).pop(message_id, None)

    async def reject(self, queue_name: str, message_id: str, requeue: bool = True) -> None:
        payload = self._unacked.get(queue_name, {}).pop(message_id, None)
        if requeue and payload is not None:
            await self._get_queue(queue_name).put((message_id, payload))

    async def queue_length(self, queue_name: str) -> int:
        return self._get_queue(queue_name).qsize()

    async def purge(self, queue_name: str) -> int:
        q = self._get_queue(queue_name)
        count = q.qsize()
        while not q.empty():
            try:
                q.get_nowait()
            except asyncio.QueueEmpty:
                break
        return count
```

#### InMemoryCacheAdapter

```python
# adapters/outbound/cache/memory.py

import json
import time
from typing import Any
from docflow.domain.ports import CachePort


class InMemoryCacheAdapter(CachePort):
    """In-memory cache with TTL. For testing only."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[bytes, float | None]] = {}
        # (value, expiry_timestamp | None)

    def _is_expired(self, key: str) -> bool:
        if key not in self._store:
            return True
        _, expiry = self._store[key]
        if expiry is not None and time.monotonic() > expiry:
            del self._store[key]
            return True
        return False

    async def get(self, key: str) -> bytes | None:
        if self._is_expired(key):
            return None
        return self._store[key][0]

    async def set(self, key: str, value: bytes, ttl_seconds: int | None = None) -> None:
        expiry = time.monotonic() + ttl_seconds if ttl_seconds else None
        self._store[key] = (value, expiry)

    async def delete(self, key: str) -> bool:
        return self._store.pop(key, None) is not None

    async def exists(self, key: str) -> bool:
        return not self._is_expired(key)

    async def increment(self, key: str, amount: int = 1) -> int:
        current = await self.get(key)
        val = int(current) if current else 0
        val += amount
        _, expiry = self._store.get(key, (b"0", None))
        ttl = int(expiry - time.monotonic()) if expiry else None
        await self.set(key, str(val).encode(), ttl)
        return val

    async def expire(self, key: str, ttl_seconds: int) -> None:
        if key in self._store:
            value, _ = self._store[key]
            self._store[key] = (value, time.monotonic() + ttl_seconds)

    async def get_json(self, key: str) -> dict[str, Any] | None:
        raw = await self.get(key)
        return json.loads(raw) if raw else None

    async def set_json(self, key: str, value: dict[str, Any], ttl_seconds: int | None = None) -> None:
        await self.set(key, json.dumps(value).encode(), ttl_seconds)
```

---

## 7. Job Management System — Application Layer

### 7.1 JobService

```python
# application/job_service.py

class JobService:
    """Application service for async job orchestration.

    Coordinates between API → BlobStorage → Queue → Workers → Callbacks.
    """

    def __init__(
        self,
        queue: QueuePort,
        blob_storage: BlobStoragePort,
        job_repo: JobRepositoryPort,
        cache: CachePort,
        event_bus: EventBusPort,
        metrics: MetricsPort,
        settings: Settings,
    ) -> None:
        self._queue = queue
        self._blob = blob_storage
        self._jobs = job_repo
        self._cache = cache
        self._events = event_bus
        self._metrics = metrics
        self._settings = settings

    async def submit_job(
        self,
        tenant_id: str,
        filename: str,
        file_content: bytes,
        output_format: OutputFormat = OutputFormat.MARKDOWN,
        extraction_engine: ExtractionEngine = ExtractionEngine.AUTO,
        ocr_engine: OCREngine = OCREngine.TESSERACT,
        language: str = "eng",
        priority: JobPriority = JobPriority.NORMAL,
        callback_url: str | None = None,
        batch_id: str | None = None,
    ) -> Job:
        """Submit a document for async processing.

        1. Upload file to BlobStorage
        2. Create Job entity
        3. Persist Job in JobRepository
        4. Enqueue message
        5. Publish JobQueued event
        6. Return Job (with id for polling)
        """
        ...

    async def get_job(self, job_id: str, tenant_id: str) -> Job | None:
        """Get job status. Check cache first, then repo."""
        ...

    async def list_jobs(
        self, tenant_id: str, filter: JobFilter, offset: int = 0, limit: int = 50
    ) -> Page:
        """List jobs with filtering and pagination."""
        ...

    async def cancel_job(self, job_id: str, tenant_id: str) -> Job | None:
        """Cancel a queued/running job."""
        ...

    async def retry_job(self, job_id: str, tenant_id: str) -> Job | None:
        """Re-queue a failed job."""
        ...

    async def submit_batch(
        self, tenant_id: str, files: list[tuple[str, bytes]], **kwargs: Any
    ) -> list[Job]:
        """Submit multiple files as a batch. Returns list of Jobs sharing a batch_id."""
        ...
```

---

## 8. Worker Architecture

### 8.1 Concurrency Model for 1M docs/day

**Target:** 1,000,000 docs / 86,400s ≈ **12 docs/second sustained**.

Assuming average processing time of 2–5 seconds per document:

| Component | Instances | Concurrency | Throughput |
|-----------|-----------|-------------|------------|
| API servers | 3–5 pods | 4 uvicorn workers each | Handles upload + enqueue |
| Worker pods | 10–20 pods | 8 concurrent tasks each | 80–160 parallel jobs |
| Queue (Redis Streams) | 1 cluster | Consumer groups | Distributes to workers |

This gives **80–160 docs in parallel**, yielding 16–80 docs/sec at 2–5s per doc. Comfortably exceeds 12 docs/sec target with headroom for spikes.

### 8.2 Worker Process Design

```python
# application/worker.py

class WorkerPool:
    """Runs N concurrent workers consuming from QueuePort.

    Each worker:
    1. Dequeues a message (blocking with timeout)
    2. Downloads file from BlobStoragePort
    3. Runs ProcessingPipeline
    4. Uploads result to BlobStoragePort
    5. Updates Job state in JobRepositoryPort
    6. Publishes domain event
    7. Fires webhook callback (if configured)
    8. Acknowledges message
    """

    def __init__(
        self,
        queue: QueuePort,
        blob_storage: BlobStoragePort,
        job_repo: JobRepositoryPort,
        pipeline: ProcessingPipeline,
        document_service: DocumentService,
        event_bus: EventBusPort,
        metrics: MetricsPort,
        cache: CachePort,
        settings: Settings,
        concurrency: int = 8,
    ) -> None:
        self._queue = queue
        self._blob = blob_storage
        self._jobs = job_repo
        self._pipeline = pipeline
        self._doc_service = document_service
        self._events = event_bus
        self._metrics = metrics
        self._cache = cache
        self._settings = settings
        self._concurrency = concurrency
        self._semaphore = asyncio.Semaphore(concurrency)
        self._running = False
        self._worker_id = str(uuid.uuid4())[:8]

    async def start(self) -> None:
        """Start the worker pool. Creates N consumer tasks."""
        self._running = True
        tasks = [
            asyncio.create_task(self._consumer_loop(i))
            for i in range(self._concurrency)
        ]
        await asyncio.gather(*tasks)

    async def stop(self) -> None:
        """Graceful shutdown: finish in-flight, stop consuming."""
        self._running = False

    async def _consumer_loop(self, worker_idx: int) -> None:
        """Single consumer loop."""
        queue_name = self._settings.job_queue_name
        while self._running:
            msg = await self._queue.dequeue(queue_name, timeout=5.0)
            if msg is None:
                continue  # timeout, check self._running again

            msg_id, payload = msg
            try:
                await self._process_job(payload)
                await self._queue.acknowledge(queue_name, msg_id)
            except Exception as exc:
                await self._queue.reject(queue_name, msg_id, requeue=True)
                self._metrics.counter(
                    "worker.job.error",
                    tags={"worker": str(worker_idx), "error": type(exc).__name__},
                )

    async def _process_job(self, payload: dict[str, Any]) -> None:
        """Process a single job from the queue payload."""
        job_id = payload["job_id"]
        job = await self._jobs.get(job_id)
        if job is None or job.status == JobStatus.CANCELLED:
            return

        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(timezone.utc)
        job.attempts += 1
        await self._jobs.save(job)

        await self._events.publish(JobStarted(job_id=job_id, worker_id=self._worker_id))
        self._metrics.counter("worker.job.started", tags={"tenant": job.tenant_id})

        start = time.monotonic()
        try:
            # 1. Download input from blob storage
            file_content = await self._blob.download(job.blob_key)

            # 2. Run the existing pipeline (reuses DocumentService)
            document = await self._doc_service.process_document(
                filename=job.filename,
                file_content=file_content,
                output_format=job.output_format,
                extraction_engine=job.extraction_engine,
                ocr_engine=job.ocr_engine,
                language=job.language,
            )

            if document.status == DocumentStatus.FAILED:
                raise RuntimeError(document.error or "Pipeline failed")

            # 3. Upload result to blob storage
            result_key = f"results/{job.tenant_id}/{job.id}/output.{job.output_format.value}"
            await self._blob.upload(
                result_key,
                (document.processed_content or "").encode(),
                content_type="text/plain",
            )

            # 4. Update job state
            elapsed_ms = int((time.monotonic() - start) * 1000)
            job.status = JobStatus.COMPLETED
            job.document_id = document.id
            job.result_blob_key = result_key
            job.completed_at = datetime.now(timezone.utc)
            await self._jobs.save(job)

            # 5. Invalidate cache, publish event
            await self._cache.delete(f"job:{job_id}")
            await self._events.publish(
                JobCompleted(job_id=job_id, document_id=document.id, processing_time_ms=elapsed_ms)
            )
            self._metrics.histogram(
                "worker.job.duration_ms", elapsed_ms, tags={"tenant": job.tenant_id}
            )

            # 6. Fire webhook if configured
            if job.callback_url:
                await self._fire_webhook(job)

        except Exception as exc:
            job.status = JobStatus.FAILED if job.attempts >= job.max_retries else JobStatus.RETRYING
            job.error = str(exc)
            await self._jobs.save(job)
            await self._events.publish(
                JobFailed(job_id=job_id, error=str(exc), attempt=job.attempts)
            )
            self._metrics.counter("worker.job.failed", tags={"tenant": job.tenant_id})
            if job.attempts < job.max_retries:
                # Re-enqueue with exponential backoff (handled by queue delay or retry scheduler)
                await self._queue.enqueue(
                    self._settings.job_queue_name,
                    {"job_id": job_id},
                    priority=0,
                )
```

### 8.3 Backpressure Handling

| Strategy | Implementation |
|----------|---------------|
| **Queue depth monitoring** | `MetricsPort.gauge("queue.depth", await queue.queue_length(...))` polled every 10s |
| **Semaphore-bounded concurrency** | `asyncio.Semaphore(N)` per worker pod — won't over-consume |
| **Rate limiting at API** | `CachePort.increment()` for sliding-window per tenant |
| **Auto-scaling trigger** | Expose queue depth via `/metrics` → HPA scales worker pods |
| **Circuit breaker** | If error rate > 50% in 60s window → pause dequeuing for 30s |
| **Priority queues** | Critical/high jobs get separate queue, consumed first |

### 8.4 Deduplication Strategy

Before enqueuing, compute `sha256(file_content)`. Check cache:
```python
dedup_key = f"dedup:{tenant_id}:{checksum}"
if await cache.exists(dedup_key):
    # Return existing job_id from cache
    ...
await cache.set(dedup_key, job_id.encode(), ttl_seconds=86400)
```

---

## 9. API Design — Enterprise Endpoints

All new endpoints under `/api/v1/`. The existing `/extract` and `/extract/raw` endpoints remain unchanged for backward compatibility.

### 9.1 Authentication & Multi-Tenancy

```
Header: X-API-Key: <key>          # Required for all /jobs endpoints
Header: X-Tenant-ID: <tenant_id>  # Required; identifies the tenant
```

Authentication is handled by a FastAPI middleware/dependency:

```python
# adapters/inbound/api/auth.py

async def require_api_key(
    x_api_key: str = Header(...),
    x_tenant_id: str = Header(...),
    cache: CachePort = Depends(get_cache),
    settings: Settings = Depends(get_settings),
) -> TenantContext:
    """Validate API key and extract tenant context.

    Keys stored as: api_key:<sha256(key)> → {"tenant_id": "...", "tier": "..."}
    """
    ...
```

### 9.2 Endpoint Definitions

#### POST /api/v1/jobs — Submit Job

```
POST /api/v1/jobs
Content-Type: multipart/form-data
Headers: X-API-Key, X-Tenant-ID

Form fields:
  file: UploadFile (required)
  output_format: str = "markdown"
  extraction_engine: str = "auto"
  ocr_engine: str = "tesseract"
  language: str = "eng"
  priority: str = "normal"
  callback_url: str | None = None

Response 202:
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "queued",
  "created_at": "2026-02-11T10:00:00Z",
  "estimated_wait_seconds": 12,
  "links": {
    "self": "/api/v1/jobs/550e8400-e29b-41d4-a716-446655440000",
    "cancel": "/api/v1/jobs/550e8400-e29b-41d4-a716-446655440000"
  }
}
```

#### GET /api/v1/jobs/{job_id} — Job Status

```
GET /api/v1/jobs/{job_id}
Headers: X-API-Key, X-Tenant-ID

Response 200 (queued/running):
{
  "job_id": "...",
  "status": "running",
  "priority": "normal",
  "filename": "report.pdf",
  "created_at": "...",
  "started_at": "...",
  "attempts": 1,
  "progress": null
}

Response 200 (completed):
{
  "job_id": "...",
  "status": "completed",
  "filename": "report.pdf",
  "output_format": "markdown",
  "created_at": "...",
  "completed_at": "...",
  "processing_time_ms": 2340,
  "result": {
    "download_url": "https://storage.example.com/results/.../output.md?sig=...",
    "expires_at": "2026-02-11T11:00:00Z",
    "size_bytes": 45230
  }
}

Response 200 (failed):
{
  "job_id": "...",
  "status": "failed",
  "error": "Tika extraction timeout after 120s",
  "attempts": 3,
  "links": {
    "retry": "/api/v1/jobs/.../retry"
  }
}
```

#### POST /api/v1/jobs/batch — Batch Submit

```
POST /api/v1/jobs/batch
Content-Type: multipart/form-data
Headers: X-API-Key, X-Tenant-ID

Form fields:
  files: list[UploadFile] (required, max 100)
  output_format: str = "markdown"
  callback_url: str | None = None

Response 202:
{
  "batch_id": "batch-abc123",
  "jobs": [
    {"job_id": "...", "filename": "file1.pdf", "status": "queued"},
    {"job_id": "...", "filename": "file2.docx", "status": "queued"}
  ],
  "total": 2,
  "links": {
    "batch_status": "/api/v1/jobs?batch_id=batch-abc123"
  }
}
```

#### GET /api/v1/jobs — List Jobs (paginated)

```
GET /api/v1/jobs?status=completed&limit=20&offset=0&batch_id=...&created_after=...
Headers: X-API-Key, X-Tenant-ID

Response 200:
{
  "items": [ ... ],
  "total": 1423,
  "offset": 0,
  "limit": 20,
  "has_more": true,
  "links": {
    "next": "/api/v1/jobs?offset=20&limit=20&status=completed"
  }
}
```

#### DELETE /api/v1/jobs/{job_id} — Cancel Job

```
DELETE /api/v1/jobs/{job_id}
Headers: X-API-Key, X-Tenant-ID

Response 200:
{
  "job_id": "...",
  "status": "cancelled",
  "cancelled_at": "..."
}

Response 409: (already completed)
{
  "detail": "Cannot cancel job in status: completed"
}
```

#### POST /api/v1/jobs/{job_id}/retry — Retry Failed Job

```
POST /api/v1/jobs/{job_id}/retry
Headers: X-API-Key, X-Tenant-ID

Response 202:
{
  "job_id": "...",
  "status": "queued",
  "attempts": 3,
  "max_retries": 5
}

Response 409:
{
  "detail": "Job is not in a failed state"
}
```

#### GET /api/v1/jobs/{job_id}/result — Download Result

```
GET /api/v1/jobs/{job_id}/result
Headers: X-API-Key, X-Tenant-ID

Response 307: Redirect to presigned blob URL
Location: https://storage.example.com/results/.../output.md?sig=...

Response 404: Job not completed or result expired
```

### 9.3 API Response Schemas (Pydantic)

```python
# adapters/inbound/api/schemas.py (additions)

class JobSubmitResponse(BaseModel):
    job_id: str
    status: JobStatus
    created_at: datetime
    estimated_wait_seconds: int | None = None
    links: dict[str, str] = Field(default_factory=dict)

class JobStatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    priority: JobPriority
    filename: str
    output_format: OutputFormat
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    processing_time_ms: int | None = None
    attempts: int = 0
    error: str | None = None
    result: JobResultDetail | None = None
    links: dict[str, str] = Field(default_factory=dict)

class JobResultDetail(BaseModel):
    download_url: str
    expires_at: datetime
    size_bytes: int | None = None

class BatchSubmitResponse(BaseModel):
    batch_id: str
    jobs: list[JobSubmitResponse]
    total: int
    links: dict[str, str] = Field(default_factory=dict)

class PaginatedJobsResponse(BaseModel):
    items: list[JobStatusResponse]
    total: int
    offset: int
    limit: int
    has_more: bool
    links: dict[str, str] = Field(default_factory=dict)

class TenantContext(BaseModel):
    tenant_id: str
    tier: str = "standard"   # standard | premium | enterprise
    rate_limit_rpm: int = 600
```

### 9.4 Rate Limiting

Implemented via `CachePort.increment()` using a sliding-window counter:

```python
# adapters/inbound/api/middleware.py

class RateLimitMiddleware:
    """Sliding-window rate limiter per tenant using CachePort."""

    async def __call__(self, request: Request, call_next):
        tenant = request.state.tenant
        window_key = f"ratelimit:{tenant.tenant_id}:{int(time.time()) // 60}"
        count = await self._cache.increment(window_key)
        if count == 1:
            await self._cache.expire(window_key, 120)  # 2-minute window
        if count > tenant.rate_limit_rpm:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded", "retry_after_seconds": 60},
                headers={"Retry-After": "60"},
            )
        response = await call_next(request)
        response.headers["X-RateLimit-Remaining"] = str(max(0, tenant.rate_limit_rpm - count))
        return response
```

| Tier | Rate Limit (req/min) | Max File Size | Max Batch Size | Concurrent Jobs |
|------|---------------------|---------------|----------------|-----------------|
| Standard | 60 | 50 MB | 10 | 5 |
| Premium | 600 | 200 MB | 50 | 25 |
| Enterprise | 6000 | 500 MB | 100 | unlimited |

---

## 10. Configuration

All new settings extend the existing `Settings` class in `application/config.py`. Env var prefix remains `DOCFLOW_`.

```python
# application/config.py (additions)

class Settings(BaseSettings):
    # ... existing fields ...

    # ─── Async Jobs ──────────────────────────────────────────
    async_mode: bool = False                  # False = MVP sync mode; True = queue-backed
    job_queue_name: str = "docflow:jobs"
    job_max_retries: int = 3
    job_result_ttl_hours: int = 72            # Auto-delete results after N hours
    worker_concurrency: int = 8               # Parallel jobs per worker process

    # ─── Queue ───────────────────────────────────────────────
    queue_backend: str = "memory"             # memory | redis | pubsub | azure_sb | rabbitmq
    queue_redis_url: str = "redis://localhost:6379/1"
    queue_pubsub_project: str = ""
    queue_pubsub_topic: str = "docflow-jobs"
    queue_pubsub_subscription: str = "docflow-worker"
    queue_azure_connection_string: str = ""
    queue_azure_queue_name: str = "docflow-jobs"
    queue_rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"

    # ─── Cache ───────────────────────────────────────────────
    cache_backend: str = "memory"             # memory | redis | memcached
    cache_redis_url: str = "redis://localhost:6379/2"
    cache_memcached_hosts: str = "localhost:11211"
    cache_default_ttl: int = 3600             # 1 hour

    # ─── Blob Storage ────────────────────────────────────────
    blob_backend: str = "local"               # local | s3 | gcs | azure
    blob_local_path: str = "/data/blobs"
    blob_s3_endpoint: str = ""                # blank = real AWS; set for MinIO
    blob_s3_bucket: str = "docflow-blobs"
    blob_s3_access_key: str = ""
    blob_s3_secret_key: str = ""
    blob_s3_region: str = "eu-central-1"
    blob_gcs_bucket: str = "docflow-blobs"
    blob_gcs_credentials_json: str = ""       # path to service account JSON
    blob_azure_connection_string: str = ""
    blob_azure_container: str = "docflow-blobs"

    # ─── Metrics ─────────────────────────────────────────────
    metrics_backend: str = "memory"           # memory | prometheus | datadog | cloudwatch
    metrics_prometheus_port: int = 9090       # Separate port for /metrics scrape
    metrics_datadog_api_key: str = ""
    metrics_datadog_app_key: str = ""

    # ─── Multi-Tenancy ───────────────────────────────────────
    multi_tenant: bool = False
    auth_backend: str = "api_key"             # api_key | jwt | oidc

    # ─── Job Repository ──────────────────────────────────────
    job_repo_backend: str = "memory"          # memory | redis
    job_repo_redis_url: str = "redis://localhost:6379/3"
```

### Environment Profile Mapping

| env var combination | Profile | Description |
|---|---|---|
| All backends = `memory`, `async_mode = false` | **Local Dev / Testing** | Zero dependencies, pure Python |
| All backends = `memory`, `async_mode = true` | **Local Async Testing** | Test job flow with in-memory queue |
| Queue/cache/blob = `redis`+`local`, `async_mode = true` | **Docker Compose Dev** | Redis + local FS, no cloud |
| Queue = `redis`, blob = `s3`, cache = `redis` | **AWS Production** | |
| Queue = `pubsub`, blob = `gcs`, cache = `redis` | **GCP Production** | |
| Queue = `azure_sb`, blob = `azure`, cache = `redis` | **Azure Production** | |

---

## 11. Dependency Injection (Updated)

```python
# adapters/inbound/api/dependencies.py (extended)

def _build_queue(settings: Settings) -> QueuePort:
    match settings.queue_backend:
        case "redis":
            from docflow.adapters.outbound.queue.redis_stream import RedisStreamQueue
            return RedisStreamQueue(url=settings.queue_redis_url)
        case "pubsub":
            from docflow.adapters.outbound.queue.pubsub import PubSubQueue
            return PubSubQueue(
                project=settings.queue_pubsub_project,
                topic=settings.queue_pubsub_topic,
                subscription=settings.queue_pubsub_subscription,
            )
        case "azure_sb":
            from docflow.adapters.outbound.queue.azure_sb import AzureServiceBusQueue
            return AzureServiceBusQueue(
                connection_string=settings.queue_azure_connection_string,
                queue_name=settings.queue_azure_queue_name,
            )
        case "rabbitmq":
            from docflow.adapters.outbound.queue.rabbitmq import RabbitMQQueue
            return RabbitMQQueue(url=settings.queue_rabbitmq_url)
        case _:
            from docflow.adapters.outbound.queue.memory import InMemoryQueue
            return InMemoryQueue()

def _build_cache(settings: Settings) -> CachePort:
    match settings.cache_backend:
        case "redis":
            from docflow.adapters.outbound.cache.redis_cache import RedisCacheAdapter
            return RedisCacheAdapter(url=settings.cache_redis_url)
        case "memcached":
            from docflow.adapters.outbound.cache.memcached import MemcachedAdapter
            return MemcachedAdapter(hosts=settings.cache_memcached_hosts)
        case _:
            from docflow.adapters.outbound.cache.memory import InMemoryCacheAdapter
            return InMemoryCacheAdapter()

def _build_blob_storage(settings: Settings) -> BlobStoragePort:
    match settings.blob_backend:
        case "s3":
            from docflow.adapters.outbound.blob.s3 import S3BlobAdapter
            return S3BlobAdapter(
                endpoint=settings.blob_s3_endpoint,
                bucket=settings.blob_s3_bucket,
                access_key=settings.blob_s3_access_key,
                secret_key=settings.blob_s3_secret_key,
                region=settings.blob_s3_region,
            )
        case "gcs":
            from docflow.adapters.outbound.blob.gcs import GCSBlobAdapter
            return GCSBlobAdapter(
                bucket=settings.blob_gcs_bucket,
                credentials_json=settings.blob_gcs_credentials_json,
            )
        case "azure":
            from docflow.adapters.outbound.blob.azure_blob import AzureBlobAdapter
            return AzureBlobAdapter(
                connection_string=settings.blob_azure_connection_string,
                container=settings.blob_azure_container,
            )
        case _:
            from docflow.adapters.outbound.blob.local_fs import LocalFSBlobAdapter
            return LocalFSBlobAdapter(base_path=settings.blob_local_path)

def _build_metrics(settings: Settings) -> MetricsPort:
    match settings.metrics_backend:
        case "prometheus":
            from docflow.adapters.outbound.metrics.prometheus import PrometheusMetricsAdapter
            return PrometheusMetricsAdapter(port=settings.metrics_prometheus_port)
        case "datadog":
            from docflow.adapters.outbound.metrics.datadog import DatadogMetricsAdapter
            return DatadogMetricsAdapter(
                api_key=settings.metrics_datadog_api_key,
                app_key=settings.metrics_datadog_app_key,
            )
        case "cloudwatch":
            from docflow.adapters.outbound.metrics.cloudwatch import CloudWatchMetricsAdapter
            return CloudWatchMetricsAdapter(region=settings.blob_s3_region)
        case _:
            from docflow.adapters.outbound.metrics.memory import InMemoryMetricsAdapter
            return InMemoryMetricsAdapter()

def _build_job_repo(settings: Settings) -> JobRepositoryPort:
    match settings.job_repo_backend:
        case "redis":
            from docflow.adapters.outbound.jobs.redis_repo import RedisJobRepository
            return RedisJobRepository(url=settings.job_repo_redis_url)
        case _:
            from docflow.adapters.outbound.jobs.memory_repo import InMemoryJobRepository
            return InMemoryJobRepository()

def _build_event_bus() -> EventBusPort:
    from docflow.adapters.outbound.events.in_process import InProcessEventBus
    return InProcessEventBus()
```

---

## 12. Updated Project Structure

```
src/docflow/
├── __init__.py
├── domain/
│   ├── __init__.py
│   ├── models.py              # + Job, JobStatus, JobPriority, JobFilter, Page
│   ├── events.py              # + JobQueued, JobStarted, JobCompleted, ...
│   └── ports.py               # + QueuePort, CachePort, BlobStoragePort,
│                               #   MetricsPort, EventBusPort, JobRepositoryPort
├── application/
│   ├── __init__.py
│   ├── config.py              # + async_mode, queue/cache/blob/metrics settings
│   ├── pipeline.py            # unchanged
│   ├── service.py             # unchanged (sync path still works)
│   ├── job_service.py         # NEW — async job orchestration
│   └── worker.py              # NEW — WorkerPool consumer
├── adapters/
│   ├── __init__.py
│   ├── inbound/
│   │   ├── __init__.py
│   │   ├── cli.py
│   │   └── api/
│   │       ├── __init__.py
│   │       ├── app.py         # + lifespan connects queue/cache; mounts job routes
│   │       ├── routes.py      # existing /extract endpoints (unchanged)
│   │       ├── job_routes.py  # NEW — /jobs CRUD endpoints
│   │       ├── schemas.py     # + Job-related response models
│   │       ├── auth.py        # NEW — API key validation, tenant extraction
│   │       ├── middleware.py   # NEW — rate limiting, request ID, tenant context
│   │       └── dependencies.py # + build functions for new ports
│   └── outbound/
│       ├── __init__.py
│       ├── extractors/        # existing (unchanged)
│       ├── formatters/        # existing (unchanged)
│       ├── ocr/               # existing (unchanged)
│       ├── processors/        # existing (unchanged)
│       ├── storage/           # existing (unchanged)
│       ├── queue/             # NEW
│       │   ├── __init__.py
│       │   ├── memory.py      # InMemoryQueue
│       │   ├── redis_stream.py # RedisStreamQueue
│       │   ├── pubsub.py      # PubSubQueue
│       │   ├── azure_sb.py    # AzureServiceBusQueue
│       │   └── rabbitmq.py    # RabbitMQQueue
│       ├── cache/             # NEW
│       │   ├── __init__.py
│       │   ├── memory.py      # InMemoryCacheAdapter
│       │   ├── redis_cache.py # RedisCacheAdapter
│       │   └── memcached.py   # MemcachedAdapter
│       ├── blob/              # NEW
│       │   ├── __init__.py
│       │   ├── local_fs.py    # LocalFSBlobAdapter
│       │   ├── s3.py          # S3BlobAdapter
│       │   ├── gcs.py         # GCSBlobAdapter
│       │   └── azure_blob.py  # AzureBlobAdapter
│       ├── metrics/           # NEW
│       │   ├── __init__.py
│       │   ├── memory.py      # InMemoryMetricsAdapter
│       │   ├── prometheus.py  # PrometheusMetricsAdapter
│       │   ├── datadog.py     # DatadogMetricsAdapter
│       │   └── cloudwatch.py  # CloudWatchMetricsAdapter
│       ├── events/            # NEW
│       │   ├── __init__.py
│       │   ├── in_process.py  # InProcessEventBus
│       │   └── redis_bus.py   # RedisEventBus
│       └── jobs/              # NEW
│           ├── __init__.py
│           ├── memory_repo.py # InMemoryJobRepository
│           └── redis_repo.py  # RedisJobRepository
```

---

## 13. Docker Compose — Local E2E with Redis

```yaml
# docker/docker-compose.dev.yml (updated)
services:
  api:
    build: ..
    environment:
      DOCFLOW_ASYNC_MODE: "true"
      DOCFLOW_QUEUE_BACKEND: "redis"
      DOCFLOW_CACHE_BACKEND: "redis"
      DOCFLOW_BLOB_BACKEND: "local"
      DOCFLOW_METRICS_BACKEND: "prometheus"
      DOCFLOW_JOB_REPO_BACKEND: "redis"
      DOCFLOW_QUEUE_REDIS_URL: "redis://redis:6379/1"
      DOCFLOW_CACHE_REDIS_URL: "redis://redis:6379/2"
      DOCFLOW_JOB_REPO_REDIS_URL: "redis://redis:6379/3"
    ports:
      - "8000:8000"
    depends_on:
      - redis
      - tika

  worker:
    build: ..
    command: ["python", "-m", "docflow.adapters.inbound.cli", "worker"]
    environment:
      DOCFLOW_ASYNC_MODE: "true"
      DOCFLOW_QUEUE_BACKEND: "redis"
      DOCFLOW_CACHE_BACKEND: "redis"
      DOCFLOW_BLOB_BACKEND: "local"
      DOCFLOW_JOB_REPO_BACKEND: "redis"
      DOCFLOW_WORKER_CONCURRENCY: "8"
      DOCFLOW_QUEUE_REDIS_URL: "redis://redis:6379/1"
      DOCFLOW_CACHE_REDIS_URL: "redis://redis:6379/2"
      DOCFLOW_JOB_REPO_REDIS_URL: "redis://redis:6379/3"
    depends_on:
      - redis
      - tika
    deploy:
      replicas: 2

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

  tika:
    image: apache/tika:latest
    ports:
      - "9998:9998"

  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml

volumes:
  redis_data:
```

---

## 14. Key Metrics to Emit

| Metric Name | Type | Tags | Purpose |
|---|---|---|---|
| `docflow.jobs.submitted` | counter | `tenant`, `priority` | Ingest rate |
| `docflow.jobs.completed` | counter | `tenant`, `format` | Success rate |
| `docflow.jobs.failed` | counter | `tenant`, `error_type` | Failure rate |
| `docflow.jobs.duration_ms` | histogram | `tenant`, `engine` | Processing latency |
| `docflow.jobs.queue_depth` | gauge | `queue_name` | Backpressure indicator |
| `docflow.jobs.active_workers` | gauge | — | Worker utilization |
| `docflow.api.request_duration_ms` | histogram | `endpoint`, `method`, `status` | API latency |
| `docflow.api.rate_limit_hits` | counter | `tenant` | Rate limit violations |
| `docflow.blob.upload_bytes` | counter | `tenant` | Storage usage |
| `docflow.cache.hit_rate` | gauge | `cache_name` | Cache effectiveness |

---

## 15. Backward Compatibility

| Aspect | Strategy |
|--------|----------|
| Existing `/api/v1/extract` | **Unchanged.** Continues to work synchronously. |
| Existing `/api/v1/extract/raw` | **Unchanged.** |
| `DOCFLOW_ASYNC_MODE=false` (default) | No queue, no workers needed. MVP behavior preserved. |
| `DOCFLOW_ASYNC_MODE=true` | Enables `/api/v1/jobs` endpoints. `/extract` still works (sync shortcut). |
| Existing adapters | **Untouched.** New adapters go in new directories. |
| Domain models | **Additive only.** New dataclasses, no changes to `Document`. |
| Domain ports | **Additive only.** New ABCs, existing signatures unchanged. |

---

## 16. Implementation Priority (Phases)

### Phase 1 — Foundation (Week 1–2)
- [ ] Add new domain models (`Job`, `JobStatus`, `JobPriority`, `JobFilter`, `Page`)
- [ ] Add new domain events (`JobQueued`, `JobStarted`, etc.)
- [ ] Add new port ABCs to `domain/ports.py`
- [ ] Implement in-memory adapters for all new ports
- [ ] Implement `JobService` and `WorkerPool`
- [ ] Add `/jobs` API routes
- [ ] Unit tests with in-memory adapters (100% local, zero deps)

### Phase 2 — Redis Adapters (Week 3)
- [ ] `RedisStreamQueue` adapter
- [ ] `RedisCacheAdapter` adapter
- [ ] `RedisJobRepository` adapter
- [ ] Docker Compose dev environment with Redis
- [ ] Integration tests against Redis

### Phase 3 — Blob Storage + Auth (Week 4)
- [ ] `S3BlobAdapter` (with MinIO for local dev)
- [ ] `LocalFSBlobAdapter` for testing
- [ ] API key authentication middleware
- [ ] Rate limiting middleware
- [ ] Multi-tenant header extraction

### Phase 4 — Observability (Week 5)
- [ ] `PrometheusMetricsAdapter`
- [ ] Instrument pipeline, workers, API with metrics
- [ ] Grafana dashboards
- [ ] Health/readiness probes for K8s

### Phase 5 — Cloud Adapters (Week 6–8)
- [ ] GCS, Azure Blob, PubSub, Azure Service Bus adapters
- [ ] Terraform/Pulumi modules for cloud deployment
- [ ] Load testing (Locust/k6) to validate 1M docs/day

---

## 17. Architecture Decision Records

See linked ADRs for individual decisions:

- **ADR-003:** Async job processing with custom WorkerPool over ARQ/Celery
- **ADR-004:** Redis Streams as default queue backend
- **ADR-005:** Tenant-header multi-tenancy over JWT claims
- **ADR-006:** In-memory fallbacks for all ports (testing strategy)
- **ADR-007:** BlobStoragePort separate from existing StoragePort

---

## Appendix A: Component Diagram (Mermaid)

```mermaid
graph TB
    subgraph "Inbound Adapters"
        API[FastAPI REST API]
        CLI[CLI - Typer]
    end

    subgraph "Application Layer"
        DS[DocumentService]
        JS[JobService]
        PP[ProcessingPipeline]
        WP[WorkerPool]
    end

    subgraph "Domain Layer"
        M[Models]
        E[Events]
        P[Ports - ABCs]
    end

    subgraph "Outbound Adapters"
        EX[Extractors<br>Tika / PyMuPDF]
        OCR[OCR<br>Tesseract]
        PROC[Processors<br>Cleanup]
        FMT[Formatters<br>MD / JSON / TXT]
        Q[Queue<br>Redis / PubSub / Memory]
        C[Cache<br>Redis / Memory]
        BS[BlobStorage<br>S3 / GCS / Local]
        MET[Metrics<br>Prometheus / Memory]
        EB[EventBus<br>InProcess / Redis]
        JR[JobRepo<br>Redis / Memory]
    end

    API --> DS
    API --> JS
    CLI --> DS
    JS --> Q
    JS --> BS
    JS --> JR
    JS --> C
    JS --> EB
    WP --> Q
    WP --> BS
    WP --> JR
    WP --> DS
    WP --> EB
    WP --> MET
    DS --> PP
    PP --> EX
    PP --> OCR
    PP --> PROC
    PP --> FMT

    DS -.-> P
    JS -.-> P
    WP -.-> P
```
