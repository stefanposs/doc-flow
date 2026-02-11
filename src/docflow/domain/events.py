"""Domain events for DocFlow."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True)
class DomainEvent:
    """Base class for domain events."""

    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class DocumentReceived(DomainEvent):
    """Emitted when a new document is uploaded."""

    document_id: str = ""
    filename: str = ""
    mime_type: str = ""
    size_bytes: int = 0


@dataclass(frozen=True)
class ExtractionStarted(DomainEvent):
    """Emitted when extraction begins."""

    document_id: str = ""
    engine: str = ""


@dataclass(frozen=True)
class ExtractionCompleted(DomainEvent):
    """Emitted when extraction finishes successfully."""

    document_id: str = ""
    engine: str = ""
    text_length: int = 0


@dataclass(frozen=True)
class ProcessingCompleted(DomainEvent):
    """Emitted when post-processing finishes."""

    document_id: str = ""
    output_format: str = ""
    processors_applied: tuple[str, ...] = ()


@dataclass(frozen=True)
class DocumentFailed(DomainEvent):
    """Emitted when processing fails at any stage."""

    document_id: str = ""
    stage: str = ""
    error: str = ""
