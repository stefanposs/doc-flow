# DocFlow – Test-Strategie

> Umfassende Teststrategie für die DocFlow Document Extraction Pipeline  
> Version: 0.1.0 | Status: Draft | Date: 2026-02-11

---

## 1. Test-Pyramide

```
            ╱╲
           ╱ E2E ╲              ~5%   │ Full Pipeline: Upload → Extract → Process → Format
          ╱────────╲                   │ Docker Compose, echte Services
         ╱ Contract  ╲          ~10%   │ API-Contracts, Port-Interface-Compliance
        ╱──────────────╲               │ Adapter ↔ Port Schema-Tests
       ╱  Integration    ╲      ~25%   │ Tika, Tesseract, S3 via Testcontainers
      ╱────────────────────╲           │ FastAPI TestClient, DB-Zugriffe
     ╱      Unit Tests       ╲  ~60%   │ Domain Models, Application Services,
    ╱──────────────────────────╲       │ Processors, Formatters – alles mit Fakes
```

### Schichten-Definition

| Schicht | Scope | Geschwindigkeit | Infrastruktur | Marker |
|---------|-------|-----------------|--------------|--------|
| **Unit** | Domain Models, Value Objects, Application Services, Pure Adapters (Formatters, Cleanup) | < 50ms/Test | Keine | `@pytest.mark.unit` |
| **Integration** | Tika-Adapter, Tesseract-Adapter, Storage-Adapter, API-Endpoints | < 10s/Test | Testcontainers / TestClient | `@pytest.mark.integration` |
| **Contract** | Port-Interface-Compliance, API-Schema-Validation | < 1s/Test | Keine | `@pytest.mark.contract` |
| **E2E** | Gesamte Pipeline: Upload → Extraction → Processing → Delivery | < 60s/Test | Docker Compose | `@pytest.mark.e2e` |

### Verhältnis & Coverage Targets

| Schicht | Anzahl Tests (Ziel) | Coverage Target | CI Stage |
|---------|---------------------|-----------------|----------|
| Unit | ~200+ | 90% Domain, 85% Application | Jeder Push |
| Integration | ~50 | 70% Adapter-Code | Jeder Push (Testcontainers) |
| Contract | ~20 | Alle Port-Interfaces | Jeder Push |
| E2E | ~10 | Critical Paths only | Pre-Merge / Nightly |

---

## 2. Test-Tooling

### 2.1 Abhängigkeiten (`pyproject.toml`)

```toml
[project.optional-dependencies]
test = [
    # === Core ===
    "pytest>=8.0",
    "pytest-asyncio>=0.24",         # async/await Support
    "pytest-cov>=6.0",              # Coverage Reports
    
    # === Fixtures & Factories ===
    "polyfactory>=2.0",             # Model Factories (ersetzt factory_boy für Dataclasses)
    
    # === HTTP Testing ===
    "httpx>=0.27",                  # AsyncClient für FastAPI Tests
    
    # === Infrastructure ===
    "testcontainers[postgres]>=4.0", # Testcontainers für Python
    
    # === Quality ===
    "pytest-xdist>=3.5",            # Parallele Test-Ausführung
    "pytest-timeout>=2.3",          # Test-Timeouts
    "pytest-randomly>=3.15",        # Zufällige Test-Reihenfolge (Flaky-Detection)
    "pytest-sugar>=1.0",            # Hübschere Output-Formatierung
    
    # === Snapshot Testing ===
    "syrupy>=4.0",                  # Snapshot/Golden-File Testing
    
    # === Mocking (minimal, Fakes bevorzugt) ===
    "respx>=0.21",                  # HTTP Mock für httpx (externe API-Calls)
]
```

### 2.2 pytest Konfiguration (`pyproject.toml`)

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
markers = [
    "unit: Unit Tests – keine Infrastruktur",
    "integration: Integration Tests – benötigt Testcontainers/Services",
    "contract: Contract Tests – Port-Interface-Compliance",
    "e2e: End-to-End Tests – benötigt Docker Compose",
    "slow: Tests > 10s Laufzeit",
]
addopts = [
    "--strict-markers",
    "--tb=short",
    "-ra",                          # Summary aller nicht-passed Tests
    "--timeout=30",                 # Default Timeout pro Test
]
filterwarnings = [
    "error",                        # Warnings → Errors
    "ignore::DeprecationWarning:testcontainers.*",
]

[tool.coverage.run]
source = ["src/docflow"]
branch = true
omit = [
    "src/docflow/infrastructure/*",
    "src/docflow/adapters/inbound/cli/*",
]

[tool.coverage.report]
fail_under = 80
show_missing = true
exclude_lines = [
    "pragma: no cover",
    "if TYPE_CHECKING:",
    "if __name__",
    "@abstractmethod",
    "\\.\\.\\.",
]
```

### 2.3 Plugin-Übersicht

| Plugin | Zweck | Warum? |
|--------|-------|--------|
| `pytest-asyncio` | `async def test_*` Support | Alle Ports sind async |
| `pytest-cov` | Coverage-Reports + `fail_under` | Quality Gate |
| `pytest-xdist` | Parallele Ausführung (`-n auto`) | Unit Tests 4x schneller |
| `pytest-timeout` | Timeout pro Test | Verhindert hängende Integration Tests |
| `pytest-randomly` | Zufällige Reihenfolge | Findet Order-Dependencies |
| `polyfactory` | Generiert Test-Daten aus Dataclasses | Kein manuelles Fixture-Bauen |
| `syrupy` | Snapshot-Tests | Golden Files für Formatter Output |
| `respx` | HTTP-Mocking für httpx | LLM-API-Calls mocken |
| `httpx` | FastAPI `AsyncClient` | API Integration Tests |

---

## 3. Test-Verzeichnisstruktur

```
tests/
├── conftest.py                         # Globale Fixtures, Marker-Registration
│
├── unit/                               # ══ UNIT TESTS (~60%) ══
│   ├── conftest.py                     # Unit-spezifische Fixtures
│   ├── domain/
│   │   ├── test_models.py              # Document, ExtractionResult, Value Objects
│   │   ├── test_value_objects.py       # MimeType, DocumentId, FileMetadata
│   │   ├── test_events.py             # Domain Events Serialization
│   │   └── test_exceptions.py         # Custom Exception Behavior
│   ├── application/
│   │   ├── test_document_service.py    # Orchestrierung mit Fakes
│   │   ├── test_extraction_service.py  # Routing + OCR Fallback
│   │   ├── test_processing_service.py  # Pipeline-Ausführung
│   │   └── test_dto.py                # DTO Validation
│   └── adapters/
│       └── outbound/
│           ├── test_cleanup_processor.py    # Pure-Logic Adapter
│           ├── test_structure_processor.py  # Pure-Logic Adapter
│           ├── test_markdown_formatter.py   # Pure-Logic Adapter
│           ├── test_json_formatter.py       # Pure-Logic Adapter
│           └── test_plaintext_formatter.py  # Pure-Logic Adapter
│
├── integration/                        # ══ INTEGRATION TESTS (~25%) ══
│   ├── conftest.py                     # Testcontainers Setup
│   ├── adapters/
│   │   ├── test_tika_extractor.py      # Testcontainer: Tika
│   │   ├── test_tesseract_ocr.py       # Testcontainer: Tesseract
│   │   ├── test_local_storage.py       # Temp Directory
│   │   └── test_llm_processor.py       # HTTP Mock (respx)
│   └── api/
│       ├── test_documents_api.py       # FastAPI TestClient
│       └── test_health_api.py          # FastAPI TestClient
│
├── contract/                           # ══ CONTRACT TESTS (~10%) ══
│   ├── test_extractor_port.py          # Alle Extractor-Adapter gegen Port-Interface
│   ├── test_ocr_port.py               # Alle OCR-Adapter gegen Port-Interface
│   ├── test_storage_port.py            # Alle Storage-Adapter gegen Port-Interface
│   └── test_formatter_port.py          # Alle Formatter-Adapter gegen Port-Interface
│
├── e2e/                                # ══ E2E TESTS (~5%) ══
│   ├── conftest.py                     # Docker Compose Lifecycle
│   ├── test_pdf_pipeline.py            # PDF → Markdown/JSON
│   ├── test_image_pipeline.py          # Bild → OCR → Markdown
│   └── test_office_pipeline.py         # DOCX/XLSX → Markdown
│
├── fakes/                              # ══ IN-MEMORY FAKES ══
│   ├── __init__.py
│   ├── fake_extractor.py
│   ├── fake_ocr.py
│   ├── fake_storage.py
│   ├── fake_processor.py
│   ├── fake_formatter.py
│   └── fake_event_bus.py
│
├── factories/                          # ══ TEST DATA FACTORIES ══
│   ├── __init__.py
│   ├── document_factory.py
│   └── extraction_factory.py
│
└── fixtures/                           # ══ SAMPLE DOCUMENTS & GOLDEN FILES ══
    ├── documents/
    │   ├── sample.pdf                  # Einfaches Text-PDF
    │   ├── scanned.pdf                 # Gescanntes PDF (braucht OCR)
    │   ├── multi_page.pdf              # Mehrseitiges PDF
    │   ├── sample.docx                 # Word-Dokument
    │   ├── sample.xlsx                 # Excel-Dokument
    │   ├── sample.png                  # Screenshot mit Text
    │   ├── sample.jpg                  # Foto eines Dokuments
    │   ├── corrupted.pdf               # Kaputte Datei (Error-Path)
    │   └── empty.pdf                   # Leeres PDF
    └── golden/
        ├── sample_pdf.md               # Erwarteter Markdown-Output
        ├── sample_pdf.json             # Erwarteter JSON-Output
        ├── sample_docx.md
        └── scanned_pdf.md              # Erwarteter OCR-Output
```

---

## 4. Fixtures & Fakes

### 4.1 Globale Fixtures (`tests/conftest.py`)

```python
"""Globale Test-Fixtures für DocFlow."""

from pathlib import Path

import pytest

from tests.fakes.fake_event_bus import FakeEventBus
from tests.fakes.fake_extractor import FakeExtractor
from tests.fakes.fake_formatter import FakeMarkdownFormatter
from tests.fakes.fake_ocr import FakeOCR
from tests.fakes.fake_processor import FakeCleanupProcessor
from tests.fakes.fake_storage import FakeStorage

# ── Pfad-Fixtures ──────────────────────────────────────────

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def sample_pdf(fixtures_dir: Path) -> bytes:
    return (fixtures_dir / "documents" / "sample.pdf").read_bytes()


@pytest.fixture
def sample_docx(fixtures_dir: Path) -> bytes:
    return (fixtures_dir / "documents" / "sample.docx").read_bytes()


@pytest.fixture
def sample_image(fixtures_dir: Path) -> bytes:
    return (fixtures_dir / "documents" / "sample.png").read_bytes()


@pytest.fixture
def scanned_pdf(fixtures_dir: Path) -> bytes:
    return (fixtures_dir / "documents" / "scanned.pdf").read_bytes()


@pytest.fixture
def corrupted_pdf(fixtures_dir: Path) -> bytes:
    return (fixtures_dir / "documents" / "corrupted.pdf").read_bytes()


@pytest.fixture
def golden_dir(fixtures_dir: Path) -> Path:
    return fixtures_dir / "golden"


# ── Fake-Fixtures ──────────────────────────────────────────


@pytest.fixture
def fake_extractor() -> FakeExtractor:
    return FakeExtractor()


@pytest.fixture
def fake_ocr() -> FakeOCR:
    return FakeOCR()


@pytest.fixture
def fake_storage() -> FakeStorage:
    return FakeStorage()


@pytest.fixture
def fake_event_bus() -> FakeEventBus:
    return FakeEventBus()


@pytest.fixture
def fake_processor() -> FakeCleanupProcessor:
    return FakeCleanupProcessor()


@pytest.fixture
def fake_formatter() -> FakeMarkdownFormatter:
    return FakeMarkdownFormatter()
```

### 4.2 Fake Implementations

#### `tests/fakes/fake_extractor.py`

```python
"""In-Memory Fake für ExtractorPort."""

from docflow.domain.models import (
    ContentBlock,
    Document,
    DocumentId,
    ExtractionResult,
)
from docflow.domain.ports.extractor import ExtractorPort


class FakeExtractor(ExtractorPort):
    """Fake Extractor – gibt vorkonfigurierte Ergebnisse zurück.

    Verwendung in Unit-Tests: Application Services testen,
    ohne echte Extraktion (Tika, Textract) auszuführen.
    """

    def __init__(self) -> None:
        self._results: dict[str, ExtractionResult] = {}
        self._supported_types: set[str] = {
            "application/pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }
        self._extract_calls: list[Document] = []
        self._should_fail: bool = False
        self._failure_error: str = "Fake extraction error"

    # ── Test-Steuerung ──

    def set_result(self, document_id: str, result: ExtractionResult) -> None:
        """Konfiguriert das Ergebnis für eine bestimmte Document-ID."""
        self._results[document_id] = result

    def set_supported_types(self, types: set[str]) -> None:
        self._supported_types = types

    def fail_with(self, error: str) -> None:
        """Konfiguriert den Fake, bei extract() eine Exception zu werfen."""
        self._should_fail = True
        self._failure_error = error

    @property
    def extract_calls(self) -> list[Document]:
        """Ermöglicht Assertions über aufgerufene Dokumente."""
        return self._extract_calls

    # ── Port-Interface ──

    async def extract(self, document: Document) -> ExtractionResult:
        self._extract_calls.append(document)

        if self._should_fail:
            raise RuntimeError(self._failure_error)

        if document.id.value in self._results:
            return self._results[document.id.value]

        # Default: Sinnvolles Ergebnis
        return ExtractionResult(
            document_id=document.id,
            raw_text="Fake extracted text from document.",
            structured_blocks=[
                ContentBlock(block_type="PARAGRAPH", content="Fake paragraph.")
            ],
            metadata={"extractor": "fake"},
            extractor_used="fake",
            confidence=0.99,
        )

    def supports(self, mime_type: str) -> bool:
        return mime_type in self._supported_types
```

#### `tests/fakes/fake_ocr.py`

```python
"""In-Memory Fake für OCRPort."""

from docflow.domain.ports.ocr import OCRPort


class FakeOCR(OCRPort):
    """Fake OCR – gibt vorkonfigurierten Text zurück."""

    def __init__(self) -> None:
        self._text: str = "Fake OCR recognized text."
        self._confidence: float = 0.95
        self._recognize_calls: list[tuple[int, str]] = []  # (data_size, language)
        self._should_fail: bool = False

    def set_text(self, text: str, confidence: float = 0.95) -> None:
        self._text = text
        self._confidence = confidence

    def fail_with(self, error: str) -> None:
        self._should_fail = True
        self._error = error

    @property
    def recognize_calls(self) -> list[tuple[int, str]]:
        return self._recognize_calls

    async def recognize(self, image_data: bytes, language: str = "deu") -> "OCRResult":
        self._recognize_calls.append((len(image_data), language))

        if self._should_fail:
            raise RuntimeError(self._error)

        from docflow.domain.models import OCRResult

        return OCRResult(text=self._text, confidence=self._confidence, language=language)

    def supported_languages(self) -> list[str]:
        return ["deu", "eng", "fra"]
```

#### `tests/fakes/fake_storage.py`

```python
"""In-Memory Fake für StoragePort."""

from docflow.domain.ports.storage import StoragePort


class FakeStorage(StoragePort):
    """In-Memory Storage – dict statt Filesystem/S3."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[bytes, dict]] = {}
        self._store_calls: list[str] = []
        self._delete_calls: list[str] = []

    @property
    def stored_documents(self) -> dict[str, tuple[bytes, dict]]:
        """Zugriff auf gespeicherte Daten für Assertions."""
        return self._store

    async def store(self, document_id: str, data: bytes, metadata: dict) -> str:
        reference = f"fake://{document_id}"
        self._store[reference] = (data, metadata)
        self._store_calls.append(reference)
        return reference

    async def retrieve(self, reference: str) -> bytes:
        if reference not in self._store:
            raise FileNotFoundError(f"Not found: {reference}")
        return self._store[reference][0]

    async def delete(self, reference: str) -> None:
        self._delete_calls.append(reference)
        self._store.pop(reference, None)
```

#### `tests/fakes/fake_event_bus.py`

```python
"""In-Memory Fake für EventBusPort."""

from docflow.domain.events import DomainEvent
from docflow.domain.ports.event_bus import EventBusPort


class FakeEventBus(EventBusPort):
    """Sammelt alle publizierten Events für Assertions."""

    def __init__(self) -> None:
        self._events: list[DomainEvent] = []

    @property
    def published_events(self) -> list[DomainEvent]:
        return self._events

    def events_of_type(self, event_type: type[DomainEvent]) -> list[DomainEvent]:
        return [e for e in self._events if isinstance(e, event_type)]

    async def publish(self, event: DomainEvent) -> None:
        self._events.append(event)

    def reset(self) -> None:
        self._events.clear()
```

### 4.3 Test Data Factories (`tests/factories/document_factory.py`)

```python
"""Factories für Domain-Objekte mit polyfactory."""

from datetime import datetime
from uuid import uuid4

from polyfactory.factories import DataclassFactory

from docflow.domain.models import (
    ContentBlock,
    Document,
    DocumentId,
    DocumentStatus,
    ExtractionResult,
    FileMetadata,
    MimeType,
)


class DocumentIdFactory(DataclassFactory):
    __model__ = DocumentId

    @classmethod
    def value(cls) -> str:
        return str(uuid4())


class MimeTypeFactory(DataclassFactory):
    __model__ = MimeType

    @classmethod
    def value(cls) -> str:
        return "application/pdf"


class FileMetadataFactory(DataclassFactory):
    __model__ = FileMetadata

    @classmethod
    def filename(cls) -> str:
        return "test_document.pdf"

    @classmethod
    def size_bytes(cls) -> int:
        return 1024

    @classmethod
    def mime_type(cls) -> MimeType:
        return MimeTypeFactory.build()

    @classmethod
    def checksum(cls) -> str:
        return "sha256:abc123"


class DocumentFactory(DataclassFactory):
    __model__ = Document

    @classmethod
    def id(cls) -> DocumentId:
        return DocumentIdFactory.build()

    @classmethod
    def metadata(cls) -> FileMetadata:
        return FileMetadataFactory.build()

    @classmethod
    def status(cls) -> DocumentStatus:
        return DocumentStatus.RECEIVED


# ── Builder-Pattern für komplexe Szenarien ──


def build_pdf_document(**overrides) -> Document:
    """Erstellt ein PDF-Dokument mit sinnvollen Defaults."""
    defaults = {
        "id": DocumentId(value=str(uuid4())),
        "metadata": FileMetadata(
            filename="report.pdf",
            size_bytes=2048,
            mime_type=MimeType(value="application/pdf"),
            checksum="sha256:test",
        ),
        "status": DocumentStatus.RECEIVED,
    }
    defaults.update(overrides)
    return Document(**defaults)


def build_image_document(**overrides) -> Document:
    """Erstellt ein Bild-Dokument (braucht OCR)."""
    defaults = {
        "id": DocumentId(value=str(uuid4())),
        "metadata": FileMetadata(
            filename="scan.png",
            size_bytes=4096,
            mime_type=MimeType(value="image/png"),
            checksum="sha256:test",
        ),
        "status": DocumentStatus.RECEIVED,
    }
    defaults.update(overrides)
    return Document(**defaults)


def build_extraction_result(document_id: DocumentId | None = None, **overrides) -> ExtractionResult:
    """Erstellt ein ExtractionResult mit sinnvollen Defaults."""
    defaults = {
        "document_id": document_id or DocumentIdFactory.build(),
        "raw_text": "# Sample Heading\n\nThis is extracted text.",
        "structured_blocks": [
            ContentBlock(block_type="HEADING", content="Sample Heading", level=1),
            ContentBlock(block_type="PARAGRAPH", content="This is extracted text."),
        ],
        "metadata": {"pages": 1, "extractor": "test"},
        "extractor_used": "test",
        "confidence": 0.95,
    }
    defaults.update(overrides)
    return ExtractionResult(**defaults)
```

---

## 5. Konkrete Test-Beispiele

### 5.1 Unit Tests – Domain Models

```python
# tests/unit/domain/test_models.py
"""Unit Tests für Domain Models und Value Objects."""

import pytest

from docflow.domain.models import (
    Document,
    DocumentId,
    DocumentStatus,
    FileMetadata,
    MimeType,
)


class TestMimeType:
    """Tests für MimeType Value Object."""

    def test_is_pdf_returns_true_for_pdf(self):
        mime = MimeType(value="application/pdf")
        assert mime.is_pdf() is True

    def test_is_pdf_returns_false_for_docx(self):
        mime = MimeType(value="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        assert mime.is_pdf() is False

    def test_is_image_returns_true_for_png(self):
        mime = MimeType(value="image/png")
        assert mime.is_image() is True

    def test_is_image_returns_true_for_jpeg(self):
        mime = MimeType(value="image/jpeg")
        assert mime.is_image() is True

    def test_is_image_returns_false_for_pdf(self):
        mime = MimeType(value="application/pdf")
        assert mime.is_image() is False

    @pytest.mark.parametrize(
        "mime_str,expected_image",
        [
            ("image/png", True),
            ("image/jpeg", True),
            ("image/tiff", True),
            ("application/pdf", False),
            ("text/plain", False),
        ],
    )
    def test_is_image_parametrized(self, mime_str: str, expected_image: bool):
        assert MimeType(value=mime_str).is_image() is expected_image

    def test_mime_type_is_frozen(self):
        """Value Objects müssen immutable sein."""
        mime = MimeType(value="application/pdf")
        with pytest.raises(AttributeError):
            mime.value = "text/plain"  # type: ignore[misc]


class TestDocument:
    """Tests für Document Entity."""

    def test_new_document_has_received_status(self):
        doc = Document(
            id=DocumentId(value="test-123"),
            metadata=FileMetadata(
                filename="test.pdf",
                size_bytes=1024,
                mime_type=MimeType(value="application/pdf"),
                checksum="sha256:abc",
            ),
        )
        assert doc.status == DocumentStatus.RECEIVED

    def test_document_storage_reference_defaults_to_none(self):
        doc = Document(
            id=DocumentId(value="test-123"),
            metadata=FileMetadata(
                filename="test.pdf",
                size_bytes=1024,
                mime_type=MimeType(value="application/pdf"),
                checksum="sha256:abc",
            ),
        )
        assert doc.storage_reference is None
```

### 5.2 Unit Tests – Application Services

```python
# tests/unit/application/test_extraction_service.py
"""Unit Tests für ExtractionService mit Fakes."""

import pytest

from docflow.application.extraction_service import ExtractionService
from docflow.domain.exceptions import UnsupportedFormatError
from docflow.domain.models import DocumentStatus
from tests.factories.document_factory import (
    build_image_document,
    build_pdf_document,
)
from tests.fakes.fake_event_bus import FakeEventBus
from tests.fakes.fake_extractor import FakeExtractor
from tests.fakes.fake_ocr import FakeOCR


@pytest.fixture
def extraction_service(
    fake_extractor: FakeExtractor,
    fake_ocr: FakeOCR,
    fake_event_bus: FakeEventBus,
) -> ExtractionService:
    """ExtractionService mit allen Fake-Dependencies."""
    return ExtractionService(
        extractors=[fake_extractor],
        ocr=fake_ocr,
        event_bus=fake_event_bus,
    )


class TestExtractionServiceRouting:
    """Tests für Extractor-Routing basierend auf MIME-Type."""

    async def test_routes_pdf_to_extractor(
        self,
        extraction_service: ExtractionService,
        fake_extractor: FakeExtractor,
    ):
        doc = build_pdf_document()

        result = await extraction_service.extract(doc)

        assert result.extractor_used == "fake"
        assert len(fake_extractor.extract_calls) == 1
        assert fake_extractor.extract_calls[0].id == doc.id

    async def test_raises_for_unsupported_mime_type(
        self,
        extraction_service: ExtractionService,
    ):
        doc = build_pdf_document()
        doc.metadata = doc.metadata.__class__(
            filename="test.xyz",
            size_bytes=100,
            mime_type=doc.metadata.mime_type.__class__(value="application/x-unknown"),
            checksum="sha256:abc",
        )

        with pytest.raises(UnsupportedFormatError):
            await extraction_service.extract(doc)


class TestExtractionServiceOCRFallback:
    """Tests für OCR-Fallback bei Bild-Dokumenten."""

    async def test_uses_ocr_for_image_documents(
        self,
        extraction_service: ExtractionService,
        fake_ocr: FakeOCR,
    ):
        doc = build_image_document()
        fake_ocr.set_text("OCR erkannter Text", confidence=0.85)

        result = await extraction_service.extract(doc)

        assert len(fake_ocr.recognize_calls) == 1
        assert result.confidence == 0.85

    async def test_ocr_uses_configured_language(
        self,
        extraction_service: ExtractionService,
        fake_ocr: FakeOCR,
    ):
        doc = build_image_document()

        await extraction_service.extract(doc, language="eng")

        _, language = fake_ocr.recognize_calls[0]
        assert language == "eng"


class TestExtractionServiceEvents:
    """Tests für Domain-Event-Publishing."""

    async def test_publishes_extraction_completed_on_success(
        self,
        extraction_service: ExtractionService,
        fake_event_bus: FakeEventBus,
    ):
        doc = build_pdf_document()

        await extraction_service.extract(doc)

        from docflow.domain.events import ExtractionCompleted

        completed_events = fake_event_bus.events_of_type(ExtractionCompleted)
        assert len(completed_events) == 1
        assert completed_events[0].document_id == doc.id

    async def test_publishes_extraction_failed_on_error(
        self,
        extraction_service: ExtractionService,
        fake_extractor: FakeExtractor,
        fake_event_bus: FakeEventBus,
    ):
        doc = build_pdf_document()
        fake_extractor.fail_with("Tika connection refused")

        with pytest.raises(RuntimeError):
            await extraction_service.extract(doc)

        from docflow.domain.events import ExtractionFailed

        failed_events = fake_event_bus.events_of_type(ExtractionFailed)
        assert len(failed_events) == 1
        assert "connection refused" in failed_events[0].error.lower()
```

### 5.3 Unit Tests – Processing Pipeline

```python
# tests/unit/application/test_processing_service.py
"""Unit Tests für ProcessingService – Pipeline-Ausführung."""

import pytest

from docflow.application.processing_service import ProcessingPipeline
from docflow.domain.models import ProcessingContext


class FakeUpperCaseProcessor:
    """Trivaler Processor für Pipeline-Tests."""

    @property
    def name(self) -> str:
        return "uppercase"

    async def process(self, text: str, context: ProcessingContext) -> str:
        return text.upper()


class FakeStripProcessor:
    """Entfernt führende/abschließende Whitespace."""

    @property
    def name(self) -> str:
        return "strip"

    async def process(self, text: str, context: ProcessingContext) -> str:
        return text.strip()


class TestProcessingPipeline:
    """Tests für die Processing Pipeline."""

    async def test_empty_pipeline_returns_input_unchanged(self):
        pipeline = ProcessingPipeline(processors=[])
        result = await pipeline.execute("hello world", ProcessingContext())
        assert result == "hello world"

    async def test_single_processor_transforms_text(self):
        pipeline = ProcessingPipeline(processors=[FakeUpperCaseProcessor()])
        result = await pipeline.execute("hello", ProcessingContext())
        assert result == "HELLO"

    async def test_multiple_processors_execute_in_order(self):
        pipeline = ProcessingPipeline(
            processors=[FakeStripProcessor(), FakeUpperCaseProcessor()]
        )
        result = await pipeline.execute("  hello  ", ProcessingContext())
        assert result == "HELLO"

    async def test_pipeline_chains_processor_output(self):
        """Die Ausgabe von Processor N ist die Eingabe von Processor N+1."""
        pipeline = ProcessingPipeline(
            processors=[FakeUpperCaseProcessor(), FakeStripProcessor()]
        )
        result = await pipeline.execute("  hello  ", ProcessingContext())
        assert result == "HELLO"  # Upper first → "  HELLO  ", Strip → "HELLO"

    async def test_processor_error_propagates(self):
        class FailingProcessor:
            name = "failing"

            async def process(self, text, context):
                raise ValueError("Processing failed")

        pipeline = ProcessingPipeline(processors=[FailingProcessor()])

        with pytest.raises(ValueError, match="Processing failed"):
            await pipeline.execute("input", ProcessingContext())
```

### 5.4 Unit Tests – Formatters (Snapshot-Tests)

```python
# tests/unit/adapters/outbound/test_markdown_formatter.py
"""Snapshot-Tests für MarkdownFormatter."""

import pytest
from syrupy.assertion import SnapshotAssertion

from docflow.adapters.outbound.formatters.markdown_formatter import MarkdownFormatter
from docflow.domain.models import ContentBlock, ProcessedContent


@pytest.fixture
def formatter() -> MarkdownFormatter:
    return MarkdownFormatter()


class TestMarkdownFormatter:
    """Tests für Markdown-Formatierung mit Snapshot-Vergleich."""

    async def test_formats_heading_and_paragraph(
        self,
        formatter: MarkdownFormatter,
        snapshot: SnapshotAssertion,
    ):
        content = ProcessedContent(
            blocks=[
                ContentBlock(block_type="HEADING", content="Titel", level=1),
                ContentBlock(block_type="PARAGRAPH", content="Ein Absatz mit Text."),
            ]
        )

        result = await formatter.format(content)

        assert result.content == snapshot

    async def test_formats_nested_headings(
        self,
        formatter: MarkdownFormatter,
        snapshot: SnapshotAssertion,
    ):
        content = ProcessedContent(
            blocks=[
                ContentBlock(block_type="HEADING", content="Haupttitel", level=1),
                ContentBlock(block_type="HEADING", content="Untertitel", level=2),
                ContentBlock(block_type="PARAGRAPH", content="Inhalt."),
            ]
        )

        result = await formatter.format(content)

        assert result.content == snapshot

    async def test_formats_list_blocks(
        self,
        formatter: MarkdownFormatter,
        snapshot: SnapshotAssertion,
    ):
        content = ProcessedContent(
            blocks=[
                ContentBlock(block_type="LIST", content="Punkt 1\nPunkt 2\nPunkt 3"),
            ]
        )

        result = await formatter.format(content)

        assert result.content == snapshot

    async def test_empty_content_returns_empty_string(self, formatter: MarkdownFormatter):
        content = ProcessedContent(blocks=[])
        result = await formatter.format(content)
        assert result.content == ""
```

---

## 6. Adapter Testing (Integration)

### 6.1 Tika-Adapter – Testcontainers

```python
# tests/integration/adapters/test_tika_extractor.py
"""Integration Tests für TikaExtractorAdapter mit Testcontainers."""

from pathlib import Path

import pytest
from testcontainers.generic import ServerContainer

from docflow.adapters.outbound.extractors.tika_extractor import TikaExtractorAdapter
from docflow.domain.models import DocumentId, FileMetadata, MimeType
from tests.factories.document_factory import build_pdf_document


class TikaContainer(ServerContainer):
    """Testcontainer für Apache Tika."""

    def __init__(self) -> None:
        super().__init__(port=9998, image="apache/tika:3.0.0")
        self.with_exposed_ports(9998)


@pytest.fixture(scope="module")
def tika_container():
    """Startet Tika-Container einmalig pro Modul."""
    with TikaContainer() as tika:
        tika.start()
        yield tika


@pytest.fixture
def tika_adapter(tika_container: TikaContainer) -> TikaExtractorAdapter:
    host = tika_container.get_container_host_ip()
    port = tika_container.get_exposed_port(9998)
    return TikaExtractorAdapter(url=f"http://{host}:{port}")


@pytest.mark.integration
class TestTikaExtractor:
    """Integration Tests gegen echten Tika-Server."""

    async def test_extracts_text_from_pdf(
        self,
        tika_adapter: TikaExtractorAdapter,
        sample_pdf: bytes,
    ):
        doc = build_pdf_document()

        result = await tika_adapter.extract(doc, file_data=sample_pdf)

        assert len(result.raw_text) > 0
        assert result.extractor_used == "tika"
        assert result.confidence > 0.0

    async def test_extracts_text_from_docx(
        self,
        tika_adapter: TikaExtractorAdapter,
        sample_docx: bytes,
    ):
        doc = build_pdf_document(
            metadata=FileMetadata(
                filename="test.docx",
                size_bytes=len(b""),
                mime_type=MimeType(
                    value="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                ),
                checksum="sha256:test",
            )
        )

        result = await tika_adapter.extract(doc, file_data=sample_docx)

        assert len(result.raw_text) > 0

    async def test_supports_pdf_mime_type(self, tika_adapter: TikaExtractorAdapter):
        assert tika_adapter.supports("application/pdf") is True

    async def test_handles_corrupted_file_gracefully(
        self,
        tika_adapter: TikaExtractorAdapter,
    ):
        doc = build_pdf_document()

        with pytest.raises(Exception):  # ExtractionError
            await tika_adapter.extract(doc, file_data=b"not a real pdf")

    async def test_handles_empty_file(
        self,
        tika_adapter: TikaExtractorAdapter,
    ):
        doc = build_pdf_document()

        result = await tika_adapter.extract(doc, file_data=b"")

        assert result.raw_text == "" or result.confidence < 0.1
```

### 6.2 Tesseract OCR-Adapter – Testcontainers

```python
# tests/integration/adapters/test_tesseract_ocr.py
"""Integration Tests für TesseractOCRAdapter."""

from pathlib import Path

import pytest
from testcontainers.generic import ServerContainer

from docflow.adapters.outbound.ocr.tesseract_ocr import TesseractOCRAdapter


class TesseractContainer(ServerContainer):
    """Testcontainer für Tesseract OCR Service.
    
    Verwendet ein Tesseract-Container-Image das eine HTTP-API bereitstellt,
    oder testet direkt gegen die Tesseract-Binary im Container.
    """

    def __init__(self) -> None:
        super().__init__(port=8884, image="hertzg/tesseract-server:latest")
        self.with_exposed_ports(8884)


@pytest.fixture(scope="module")
def tesseract_container():
    with TesseractContainer() as tesseract:
        tesseract.start()
        yield tesseract


@pytest.fixture
def ocr_adapter(tesseract_container: TesseractContainer) -> TesseractOCRAdapter:
    host = tesseract_container.get_container_host_ip()
    port = tesseract_container.get_exposed_port(8884)
    return TesseractOCRAdapter(url=f"http://{host}:{port}")


@pytest.mark.integration
class TestTesseractOCR:
    """Integration Tests gegen echten Tesseract-Service."""

    async def test_recognizes_text_from_image(
        self,
        ocr_adapter: TesseractOCRAdapter,
        sample_image: bytes,
    ):
        result = await ocr_adapter.recognize(sample_image, language="eng")

        assert len(result.text) > 0
        assert result.confidence > 0.5

    async def test_supports_german_language(
        self,
        ocr_adapter: TesseractOCRAdapter,
    ):
        languages = ocr_adapter.supported_languages()
        assert "deu" in languages

    async def test_handles_empty_image_gracefully(
        self,
        ocr_adapter: TesseractOCRAdapter,
    ):
        with pytest.raises(Exception):
            await ocr_adapter.recognize(b"", language="eng")
```

### 6.3 LLM Post-Processor – HTTP Mocking mit `respx`

```python
# tests/integration/adapters/test_llm_processor.py
"""Tests für LLMPostProcessor – externe API wird gemockt."""

import httpx
import pytest
import respx

from docflow.adapters.outbound.processors.llm_processor import LLMPostProcessor
from docflow.domain.models import ProcessingContext


@pytest.fixture
def llm_processor() -> LLMPostProcessor:
    return LLMPostProcessor(
        api_key="test-key",
        model="gpt-4",
        base_url="https://api.openai.com/v1",
    )


@pytest.mark.integration
class TestLLMPostProcessor:
    """Tests für LLM-basierte Nachbearbeitung.
    
    Die OpenAI-API wird mit respx gemockt – kein echter API-Call.
    Strategie: Die HTTP-Schnittstelle mocken, nicht den Processor selbst.
    """

    @respx.mock
    async def test_sends_text_to_llm_and_returns_response(
        self,
        llm_processor: LLMPostProcessor,
    ):
        respx.post("https://api.openai.com/v1/chat/completions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": "# Verbesserter Text\n\nStrukturiert und korrigiert."
                            }
                        }
                    ]
                },
            )
        )

        result = await llm_processor.process(
            "unstrukturierter text mit fehler",
            ProcessingContext(),
        )

        assert "Verbesserter Text" in result

    @respx.mock
    async def test_handles_api_error_gracefully(
        self,
        llm_processor: LLMPostProcessor,
    ):
        respx.post("https://api.openai.com/v1/chat/completions").mock(
            return_value=httpx.Response(500, json={"error": "Internal Server Error"})
        )

        # Erwartung: Gibt den Original-Text zurück (Graceful Degradation)
        result = await llm_processor.process("original text", ProcessingContext())

        assert result == "original text"

    @respx.mock
    async def test_handles_timeout(
        self,
        llm_processor: LLMPostProcessor,
    ):
        respx.post("https://api.openai.com/v1/chat/completions").mock(
            side_effect=httpx.TimeoutException("Connection timed out")
        )

        # Graceful Degradation: Originaltext zurück
        result = await llm_processor.process("original text", ProcessingContext())

        assert result == "original text"

    @respx.mock
    async def test_sends_correct_headers(
        self,
        llm_processor: LLMPostProcessor,
    ):
        route = respx.post("https://api.openai.com/v1/chat/completions").mock(
            return_value=httpx.Response(
                200,
                json={"choices": [{"message": {"content": "ok"}}]},
            )
        )

        await llm_processor.process("text", ProcessingContext())

        assert route.called
        request = route.calls.last.request
        assert request.headers["Authorization"] == "Bearer test-key"
```

### 6.4 API Testing – FastAPI TestClient

```python
# tests/integration/api/test_documents_api.py
"""Integration Tests für die Documents API."""

import io

import pytest
from httpx import AsyncClient

from docflow.adapters.inbound.api.app import create_app
from tests.fakes.fake_event_bus import FakeEventBus
from tests.fakes.fake_extractor import FakeExtractor
from tests.fakes.fake_formatter import FakeMarkdownFormatter
from tests.fakes.fake_ocr import FakeOCR
from tests.fakes.fake_processor import FakeCleanupProcessor
from tests.fakes.fake_storage import FakeStorage


@pytest.fixture
def app(
    fake_extractor: FakeExtractor,
    fake_ocr: FakeOCR,
    fake_storage: FakeStorage,
    fake_event_bus: FakeEventBus,
):
    """FastAPI App mit Fake-Dependencies."""
    return create_app(
        extractor=fake_extractor,
        ocr=fake_ocr,
        storage=fake_storage,
        event_bus=fake_event_bus,
        processors=[FakeCleanupProcessor()],
        formatters={"markdown": FakeMarkdownFormatter()},
    )


@pytest.fixture
async def client(app) -> AsyncClient:
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


@pytest.mark.integration
class TestDocumentUploadAPI:
    """Tests für POST /api/v1/documents."""

    async def test_upload_returns_202_accepted(self, client: AsyncClient):
        pdf_content = b"%PDF-1.4 fake content"
        response = await client.post(
            "/api/v1/documents",
            files={"file": ("test.pdf", io.BytesIO(pdf_content), "application/pdf")},
            data={"output_format": "markdown"},
        )

        assert response.status_code == 202
        body = response.json()
        assert "job_id" in body
        assert "document_id" in body
        assert body["status"] == "processing"

    async def test_upload_rejects_oversized_file(self, client: AsyncClient):
        large_content = b"x" * (101 * 1024 * 1024)  # 101 MB
        response = await client.post(
            "/api/v1/documents",
            files={"file": ("large.pdf", io.BytesIO(large_content), "application/pdf")},
        )

        assert response.status_code == 413

    async def test_upload_rejects_unsupported_mime_type(self, client: AsyncClient):
        response = await client.post(
            "/api/v1/documents",
            files={"file": ("test.exe", io.BytesIO(b"MZ"), "application/x-msdownload")},
        )

        assert response.status_code == 415

    async def test_upload_without_file_returns_422(self, client: AsyncClient):
        response = await client.post("/api/v1/documents")

        assert response.status_code == 422


@pytest.mark.integration
class TestDocumentSyncAPI:
    """Tests für POST /api/v1/documents/sync."""

    async def test_sync_extraction_returns_200_with_content(self, client: AsyncClient):
        response = await client.post(
            "/api/v1/documents/sync",
            files={"file": ("test.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")},
            data={"output_format": "markdown"},
        )

        assert response.status_code == 200
        body = response.json()
        assert "content" in body
        assert "document_id" in body


@pytest.mark.integration
class TestHealthAPI:
    """Tests für GET /api/v1/health."""

    async def test_health_returns_200(self, client: AsyncClient):
        response = await client.get("/api/v1/health")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "healthy"

    async def test_health_includes_adapter_status(self, client: AsyncClient):
        response = await client.get("/api/v1/health")

        body = response.json()
        assert "adapters" in body
        assert "extractor" in body["adapters"]
        assert "ocr" in body["adapters"]
```

---

## 7. Contract Tests

```python
# tests/contract/test_extractor_port.py
"""Contract Tests – Validiert dass ALLE Extractor-Adapter das Port-Interface korrekt implementieren.

Pattern: Ein Test-Set, parametrisiert über alle Adapter.
Stellt sicher, dass neue Adapter den Vertrag einhalten.
"""

from abc import ABC

import pytest

from docflow.domain.ports.extractor import ExtractorPort
from tests.factories.document_factory import build_pdf_document
from tests.fakes.fake_extractor import FakeExtractor


def all_extractor_implementations() -> list[ExtractorPort]:
    """Sammelt alle verfügbaren ExtractorPort-Implementierungen.

    In Integration Tests werden hier auch TikaExtractorAdapter etc. hinzugefügt,
    sofern die Container verfügbar sind.
    """
    return [
        FakeExtractor(),
        # TikaExtractorAdapter(url="..."),  # nur in Integration
    ]


@pytest.mark.contract
class TestExtractorPortContract:
    """Jeder Extractor MUSS diesen Vertrag erfüllen."""

    @pytest.fixture(params=all_extractor_implementations(), ids=lambda e: type(e).__name__)
    def extractor(self, request) -> ExtractorPort:
        return request.param

    async def test_extract_returns_extraction_result(self, extractor: ExtractorPort):
        doc = build_pdf_document()
        result = await extractor.extract(doc)

        assert result is not None
        assert result.document_id == doc.id
        assert isinstance(result.raw_text, str)
        assert isinstance(result.confidence, float)
        assert 0.0 <= result.confidence <= 1.0

    def test_supports_returns_bool(self, extractor: ExtractorPort):
        result = extractor.supports("application/pdf")
        assert isinstance(result, bool)

    def test_is_subclass_of_port(self, extractor: ExtractorPort):
        assert isinstance(extractor, ExtractorPort)

    async def test_extract_result_has_extractor_name(self, extractor: ExtractorPort):
        doc = build_pdf_document()
        result = await extractor.extract(doc)

        assert isinstance(result.extractor_used, str)
        assert len(result.extractor_used) > 0
```

---

## 8. E2E Tests

```python
# tests/e2e/conftest.py
"""E2E Test Setup – Docker Compose Lifecycle."""

import subprocess
import time

import httpx
import pytest


@pytest.fixture(scope="session")
def docker_compose():
    """Startet die komplette DocFlow-Infrastruktur via Docker Compose."""
    subprocess.run(
        ["docker", "compose", "-f", "docker/docker-compose.yml", "up", "-d", "--wait"],
        check=True,
        timeout=120,
    )

    # Warte auf Health Check
    base_url = "http://localhost:8000"
    for _ in range(30):
        try:
            resp = httpx.get(f"{base_url}/api/v1/health", timeout=5)
            if resp.status_code == 200:
                break
        except httpx.ConnectError:
            time.sleep(2)
    else:
        pytest.fail("DocFlow did not become healthy within 60 seconds")

    yield base_url

    subprocess.run(
        ["docker", "compose", "-f", "docker/docker-compose.yml", "down", "-v"],
        check=True,
    )
```

```python
# tests/e2e/test_pdf_pipeline.py
"""E2E Tests – Gesamte Pipeline für PDF-Dokumente."""

from pathlib import Path

import httpx
import pytest


@pytest.mark.e2e
class TestPDFPipeline:
    """Testet die komplette Pipeline: Upload → Extraction → Processing → Delivery."""

    async def test_pdf_to_markdown_full_pipeline(
        self,
        docker_compose: str,
        sample_pdf: bytes,
        golden_dir: Path,
    ):
        async with httpx.AsyncClient(base_url=docker_compose) as client:
            # 1. Upload
            response = await client.post(
                "/api/v1/documents/sync",
                files={"file": ("test.pdf", sample_pdf, "application/pdf")},
                data={"output_format": "markdown"},
                timeout=60,
            )

            assert response.status_code == 200
            body = response.json()

            # 2. Validiere Struktur
            assert "content" in body
            assert "document_id" in body
            assert len(body["content"]) > 0

            # 3. Optional: Golden-File-Vergleich
            # golden = (golden_dir / "sample_pdf.md").read_text()
            # assert body["content"].strip() == golden.strip()

    async def test_scanned_pdf_uses_ocr(
        self,
        docker_compose: str,
        scanned_pdf: bytes,
    ):
        async with httpx.AsyncClient(base_url=docker_compose) as client:
            response = await client.post(
                "/api/v1/documents/sync",
                files={"file": ("scanned.pdf", scanned_pdf, "application/pdf")},
                data={"output_format": "markdown", "ocr_enabled": "true"},
                timeout=60,
            )

            assert response.status_code == 200
            body = response.json()
            assert len(body["content"]) > 0
            # OCR-Ergebnis hat typischerweise niedrigere Confidence
            assert body.get("metadata", {}).get("extraction_confidence", 1.0) < 1.0
```

---

## 9. Test Data Strategy

### 9.1 Sample Documents

| Datei | Typ | Zweck | Größe |
|-------|-----|-------|-------|
| `sample.pdf` | Einfaches Text-PDF | Happy-Path Extraktion | ~10 KB |
| `multi_page.pdf` | Mehrseitiges PDF | Pagination, Performance | ~100 KB |
| `scanned.pdf` | Scan (Bild-PDF) | OCR-Fallback testen | ~500 KB |
| `sample.docx` | Word-Dokument | Tika Office-Parsing | ~20 KB |
| `sample.xlsx` | Excel-Tabelle | Tabellenextraktion | ~15 KB |
| `sample.png` | Screenshot mit Text | Direkte OCR | ~50 KB |
| `sample.jpg` | Foto eines Dokuments | OCR mit niedrigerer Qualität | ~200 KB |
| `corrupted.pdf` | Kaputte Datei | Error-Path, Graceful Degradation | ~1 KB |
| `empty.pdf` | Leeres PDF | Edge-Case | ~1 KB |
| `unicode.pdf` | PDF mit Sonderzeichen | Encoding-Tests (Umlaute, CJK) | ~10 KB |

### 9.2 Golden Files

Golden Files liegen unter `tests/fixtures/golden/` und werden mit `syrupy` Snapshots verglichen:

```python
# Snapshot Update: pytest --snapshot-update
# Snapshot Review: git diff tests/fixtures/golden/
```

**Strategie:**
- Golden Files nur für **deterministische** Outputs (Formatters)
- **Nicht** für Tika/OCR-Output (variiert je nach Version)
- Bei Tika/OCR: Assert auf **Struktur und Schlüsselinhalte**, nicht auf exakten Text

### 9.3 Fixture-Erzeugung

```bash
# Script zum Erzeugen von Test-Dokumenten
# tests/fixtures/generate_fixtures.py

"""
Generiert Test-Fixtures für verschiedene Dokumenttypen.
Wird einmalig manuell ausgeführt, die Ergebnisse werden
ins Repository eingecheckt.
"""
```

---

## 10. CI/CD Integration

### 10.1 GitHub Actions Pipeline

```yaml
# .github/workflows/test.yml
name: DocFlow Tests

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  # ── Stage 1: Schnelle Tests (< 2 min) ──
  unit-tests:
    name: "Unit & Contract Tests"
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: "pip"

      - name: Install dependencies
        run: pip install -e ".[test]"

      - name: Run Unit Tests
        run: |
          pytest tests/unit tests/contract \
            -m "unit or contract" \
            -n auto \
            --cov=src/docflow \
            --cov-report=xml \
            --cov-report=term-missing \
            --junitxml=reports/unit-tests.xml

      - name: Upload Coverage
        uses: codecov/codecov-action@v4
        with:
          file: coverage.xml
          flags: unit

  # ── Stage 2: Integration Tests (< 10 min) ──
  integration-tests:
    name: "Integration Tests (Testcontainers)"
    runs-on: ubuntu-latest
    needs: unit-tests
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: "pip"

      - name: Install dependencies
        run: pip install -e ".[test]"

      - name: Run Integration Tests
        run: |
          pytest tests/integration \
            -m integration \
            --timeout=60 \
            --cov=src/docflow \
            --cov-report=xml \
            --junitxml=reports/integration-tests.xml

      - name: Upload Coverage
        uses: codecov/codecov-action@v4
        with:
          file: coverage.xml
          flags: integration

  # ── Stage 3: E2E Tests (nur Pre-Merge) ──
  e2e-tests:
    name: "E2E Tests (Docker Compose)"
    runs-on: ubuntu-latest
    needs: integration-tests
    if: github.event_name == 'pull_request'
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: "pip"

      - name: Install dependencies
        run: pip install -e ".[test]"

      - name: Start infrastructure
        run: docker compose -f docker/docker-compose.yml up -d --wait

      - name: Wait for services
        run: |
          timeout 60 bash -c 'until curl -s http://localhost:8000/api/v1/health; do sleep 2; done'

      - name: Run E2E Tests
        run: |
          pytest tests/e2e \
            -m e2e \
            --timeout=120 \
            --junitxml=reports/e2e-tests.xml

      - name: Teardown
        if: always()
        run: docker compose -f docker/docker-compose.yml down -v

  # ── Quality Gates ──
  quality-gate:
    name: "Quality Gate"
    runs-on: ubuntu-latest
    needs: [unit-tests, integration-tests]
    steps:
      - name: Check coverage threshold
        run: |
          echo "Coverage must be >= 80% for merge"
          # Codecov coverage check happens via branch protection rules
```

### 10.2 Quality Gates

| Gate | Threshold | Blocking? | Stage |
|------|-----------|-----------|-------|
| Unit Test Coverage (Domain) | ≥ 90% | ✅ Ja | Push |
| Unit Test Coverage (Application) | ≥ 85% | ✅ Ja | Push |
| Integration Test Coverage | ≥ 70% | ✅ Ja | Push |
| Gesamtcoverage | ≥ 80% | ✅ Ja | Pre-Merge |
| Alle Unit Tests grün | 100% | ✅ Ja | Push |
| Alle Integration Tests grün | 100% | ✅ Ja | Push |
| E2E Critical Paths grün | 100% | ✅ Ja | Pre-Merge |
| Ruff Linting | 0 Errors | ✅ Ja | Push |
| Mypy Type-Check | 0 Errors | ✅ Ja | Push |
| Test-Dauer Unit | < 120s | ⚠️ Warning | Push |
| Test-Dauer Integration | < 300s | ⚠️ Warning | Push |

### 10.3 Performance Testing (Konzept)

```python
# tests/performance/test_throughput.py (optional, nicht in CI)
"""
Performance Tests – werden manuell oder per Nightly-Schedule ausgeführt.
Nicht Teil der Standard-CI-Pipeline.
"""

import pytest
import time


@pytest.mark.slow
@pytest.mark.performance
class TestExtractionPerformance:
    """Performance-Benchmarks für Extraktion."""

    async def test_small_pdf_under_3_seconds(self, docker_compose, sample_pdf):
        """P95-Latenz für kleine PDFs muss < 3s sein."""
        import httpx

        times = []
        async with httpx.AsyncClient(base_url=docker_compose) as client:
            for _ in range(20):
                start = time.monotonic()
                resp = await client.post(
                    "/api/v1/documents/sync",
                    files={"file": ("test.pdf", sample_pdf, "application/pdf")},
                    timeout=30,
                )
                elapsed = time.monotonic() - start
                times.append(elapsed)
                assert resp.status_code == 200

        times.sort()
        p95 = times[int(len(times) * 0.95)]
        assert p95 < 3.0, f"P95 latency {p95:.2f}s exceeds 3s target"

    async def test_throughput_100_docs_per_minute(self, docker_compose, sample_pdf):
        """Durchsatz-Test: Mindestens 100 Dokumente pro Minute."""
        import asyncio
        import httpx

        async def process_one(client: httpx.AsyncClient) -> bool:
            resp = await client.post(
                "/api/v1/documents/sync",
                files={"file": ("test.pdf", sample_pdf, "application/pdf")},
                timeout=30,
            )
            return resp.status_code == 200

        start = time.monotonic()
        async with httpx.AsyncClient(base_url=docker_compose) as client:
            tasks = [process_one(client) for _ in range(100)]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        elapsed = time.monotonic() - start
        successes = sum(1 for r in results if r is True)

        assert successes >= 95, f"Only {successes}/100 succeeded"
        assert elapsed < 60, f"Took {elapsed:.1f}s, target is 60s"
```

---

## 11. Zusammenfassung: Fakes vs. Mocks – Strategie

| Situation | Test-Double | Begründung |
|-----------|------------|------------|
| **Application Service braucht ExtractorPort** | `FakeExtractor` | Verifizierbar, stateful, kein brittle mocking |
| **Application Service braucht StoragePort** | `FakeStorage` (dict) | In-Memory-Simulation eines echten Storage |
| **Application Service braucht EventBusPort** | `FakeEventBus` (list) | Events sammeln & asserten |
| **LLM-Adapter braucht HTTP-Client** | `respx` (HTTP Mock) | Externe API, kein Fake möglich |
| **Tika-Adapter testen** | `Testcontainer` | Echte Technologie, kein sinnvoller Fake |
| **OCR-Adapter testen** | `Testcontainer` | Echte Technologie, kein sinnvoller Fake |
| **Formatter testen** | Direkter Test (kein Double) | Pure Function, keine Dependencies |
| **Cleanup Processor testen** | Direkter Test (kein Double) | Pure Function, keine Dependencies |

**Grundregel:** Fakes > Mocks > Stubs. Mocks (`unittest.mock`) nur als letztes Mittel.

---

## 12. Befehle

```bash
# Alle Unit-Tests
pytest tests/unit -m unit -n auto

# Alle Integration-Tests (benötigt Docker)
pytest tests/integration -m integration

# Alle Contract-Tests
pytest tests/contract -m contract

# E2E-Tests (benötigt Docker Compose)
pytest tests/e2e -m e2e

# Coverage-Report
pytest tests/unit tests/contract --cov=src/docflow --cov-report=html
open htmlcov/index.html

# Snapshot Update (nach gewollten Output-Änderungen)
pytest tests/unit/adapters --snapshot-update

# Nur schnelle Tests (CI Fast-Path)
pytest tests/unit tests/contract -m "unit or contract" -n auto --timeout=10

# Flaky-Detection: Tests 5x in zufälliger Reihenfolge
pytest tests/unit -n auto -p randomly --count=5
```
