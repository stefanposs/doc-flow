# DocFlow – System Architecture

> End-to-End Document Extraction Platform  
> Version: 0.1.0 | Status: Draft | Date: 2026-02-11

---

## 1. Overview

DocFlow ist eine Enterprise-Plattform zur automatisierten Extraktion von Text aus beliebigen Dokumenten (PDF, Office, Bilder, Scans) und deren Transformation in strukturierten Output (Markdown, JSON, Plain Text).

### Architekturstil: Hexagonale Architektur (Ports & Adapters)

Die Architektur folgt dem Hexagonalen Modell, um **technologische Austauschbarkeit** als erstklassiges Designprinzip zu etablieren. Jede externe Technologie (Tika, Tesseract, LLMs) ist hinter einem Port abstrahiert und über Adapter angebunden.

### Design-Prinzipien

| Prinzip | Umsetzung |
|---------|-----------|
| **Dependency Inversion** | Domain kennt keine Infrastruktur – nur Ports (Interfaces) |
| **Single Responsibility** | Jeder Adapter hat genau eine Verantwortung |
| **Open/Closed** | Neue Extraktoren/OCR-Engines per Plugin, ohne Kernänderung |
| **Configuration over Code** | Adapter-Auswahl via Konfiguration (YAML/ENV) |
| **Fail-Fast & Observable** | Structured Logging, Health Checks, Metriken ab Tag 1 |

---

## 2. Bounded Contexts & Kerndomänen

```
┌─────────────────────────────────────────────────────────┐
│                      DocFlow System                      │
├──────────────┬──────────────┬──────────────┬────────────┤
│  Ingestion   │  Extraction  │  Processing  │  Delivery  │
│   Context    │   Context    │   Context    │  Context   │
└──────────────┴──────────────┴──────────────┴────────────┘
```

### 2.1 Ingestion Context
**Verantwortung:** Dokumentenempfang, Validierung, Speicherung  
**Aggregate:** `Document`  
**Events:** `DocumentReceived`, `DocumentValidated`, `DocumentRejected`

- Empfang via API-Upload oder Batch-Import
- MIME-Type-Erkennung und Validierung
- Speicherung im temporären oder persistenten Storage
- Metadaten-Extraktion (Dateiname, Größe, Typ, Checksumme)

### 2.2 Extraction Context
**Verantwortung:** Rohtext-Extraktion aus Dokumenten  
**Aggregate:** `ExtractionJob`  
**Events:** `ExtractionStarted`, `ExtractionCompleted`, `ExtractionFailed`

- Routing zum passenden Extraktor basierend auf MIME-Type
- Text-Extraktion via Tika, Textract oder Custom-Adapter
- OCR-Fallback für bildbasierte Dokumente / Scans
- Extraktion von Metadaten und Struktur (Überschriften, Tabellen)

### 2.3 Processing Context
**Verantwortung:** Nachbearbeitung und Strukturierung  
**Aggregate:** `ProcessingPipeline`  
**Events:** `ProcessingStarted`, `ProcessingCompleted`, `ProcessingFailed`

- Cleanup (Whitespace-Normalisierung, Encoding-Fixes)
- Strukturerkennung (Überschriften, Listen, Tabellen)
- Optional: LLM-basierte Nachbearbeitung (Zusammenfassung, Korrektur)
- Pipeline-Pattern: Beliebige Reihenfolge von Prozessoren

### 2.4 Delivery Context
**Verantwortung:** Formatierung und Auslieferung des Ergebnisses  
**Aggregate:** `DeliveryResult`  
**Events:** `ResultFormatted`, `ResultDelivered`

- Output-Formatierung (Markdown, JSON, Plain Text)
- Webhook-Delivery oder synchrone Rückgabe
- Result-Caching und -Persistierung

---

## 3. Hexagonale Architektur – Schichtenmodell

```
                    ┌─────────────────────────┐
                    │     Driving Adapters     │
                    │  (Primary / Inbound)     │
                    ├─────────────────────────┤
                    │  REST API (FastAPI)      │
                    │  CLI Interface           │
                    │  Batch/File Watcher      │
                    │  gRPC (future)           │
                    └──────────┬──────────────┘
                               │
                    ┌──────────▼──────────────┐
                    │     INBOUND PORTS        │
                    │  (Application Services)  │
                    ├─────────────────────────┤
                    │  DocumentService         │
                    │  ExtractionService       │
                    │  ProcessingService       │
                    │  DeliveryService         │
                    └──────────┬──────────────┘
                               │
                    ┌──────────▼──────────────┐
                    │      DOMAIN CORE         │
                    ├─────────────────────────┤
                    │  Entities                │
                    │  Value Objects           │
                    │  Domain Events           │
                    │  Domain Services         │
                    │  Port Interfaces         │
                    └──────────┬──────────────┘
                               │
                    ┌──────────▼──────────────┐
                    │     OUTBOUND PORTS       │
                    │  (Driven Interfaces)     │
                    ├─────────────────────────┤
                    │  ExtractorPort           │
                    │  OCRPort                 │
                    │  PostProcessorPort       │
                    │  OutputFormatterPort     │
                    │  StoragePort             │
                    │  EventBusPort            │
                    └──────────┬──────────────┘
                               │
                    ┌──────────▼──────────────┐
                    │    Driven Adapters       │
                    │  (Secondary / Outbound)  │
                    ├─────────────────────────┤
                    │  TikaExtractor           │
                    │  TextractExtractor       │
                    │  TesseractOCR            │
                    │  GoogleVisionOCR         │
                    │  OpenAIPostProcessor     │
                    │  MarkdownFormatter       │
                    │  LocalFileStorage        │
                    │  S3Storage               │
                    └─────────────────────────┘
```

---

## 4. Abstraktionsschichten – Port Interfaces

### 4.1 Extractor Port

```python
from abc import ABC, abstractmethod
from docflow.domain.models import Document, ExtractionResult

class ExtractorPort(ABC):
    """Port für Dokumenten-Extraktion (Tika, Textract, Custom)."""

    @abstractmethod
    async def extract(self, document: Document) -> ExtractionResult:
        """Extrahiert Rohtext und Metadaten aus einem Dokument."""
        ...

    @abstractmethod
    def supports(self, mime_type: str) -> bool:
        """Prüft ob dieser Extraktor den MIME-Type unterstützt."""
        ...
```

**Adapter-Implementierungen:**
| Adapter | Technologie | Use Case |
|---------|------------|----------|
| `TikaExtractorAdapter` | Apache Tika | Standard-Parsing (PDF, Office, HTML) |
| `TextractExtractorAdapter` | AWS Textract | Cloud-basiert, hohe Genauigkeit |
| `PyMuPDFExtractorAdapter` | PyMuPDF | Schnelles PDF-only Parsing |
| `CustomExtractorAdapter` | Plugin | Unternehmensspezifisch |

### 4.2 OCR Port

```python
class OCRPort(ABC):
    """Port für Optical Character Recognition."""

    @abstractmethod
    async def recognize(self, image_data: bytes, language: str = "deu") -> OCRResult:
        """Führt OCR auf Bilddaten durch."""
        ...

    @abstractmethod
    def supported_languages(self) -> list[str]:
        """Liste der unterstützten Sprachen."""
        ...
```

**Adapter-Implementierungen:**
| Adapter | Technologie | Use Case |
|---------|------------|----------|
| `TesseractOCRAdapter` | Tesseract | Open-Source, Self-Hosted |
| `GoogleVisionOCRAdapter` | Google Cloud Vision | Cloud, hohe Genauigkeit |
| `AzureOCRAdapter` | Azure Cognitive Services | Enterprise Azure Stack |

### 4.3 Post-Processor Port

```python
class PostProcessorPort(ABC):
    """Port für Nachbearbeitung extrahierter Texte."""

    @abstractmethod
    async def process(self, text: str, context: ProcessingContext) -> str:
        """Verarbeitet/verbessert den extrahierten Text."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Eindeutiger Name des Processors für die Pipeline-Konfiguration."""
        ...
```

**Adapter-Implementierungen:**
| Adapter | Technologie | Use Case |
|---------|------------|----------|
| `WhitespaceCleanupProcessor` | Regex/Python | Basis-Cleanup |
| `StructureDetectionProcessor` | Heuristiken | Erkennung von Überschriften, Listen |
| `LLMPostProcessor` | OpenAI / Ollama | Intelligente Strukturierung |
| `SpellCheckProcessor` | LanguageTool | Rechtschreibkorrektur |

### 4.4 Output Formatter Port

```python
class OutputFormatterPort(ABC):
    """Port für Output-Formatierung."""

    @abstractmethod
    async def format(self, content: ProcessedContent) -> FormattedOutput:
        """Formatiert den verarbeiteten Inhalt in das Zielformat."""
        ...

    @property
    @abstractmethod
    def output_format(self) -> str:
        """Zielformat (z.B. 'markdown', 'json', 'plaintext')."""
        ...
```

**Adapter-Implementierungen:**
| Adapter | Format | Use Case |
|---------|--------|----------|
| `MarkdownFormatter` | Markdown | Standard-Output |
| `JSONFormatter` | JSON | API-Integration |
| `PlainTextFormatter` | Text | Einfache Weiterverarbeitung |
| `HTMLFormatter` | HTML | Web-Darstellung |

### 4.5 Storage Port

```python
class StoragePort(ABC):
    """Port für Dokumenten-Speicherung."""

    @abstractmethod
    async def store(self, document_id: str, data: bytes, metadata: dict) -> str:
        """Speichert Daten und gibt eine Storage-Referenz zurück."""
        ...

    @abstractmethod
    async def retrieve(self, reference: str) -> bytes:
        """Lädt Daten anhand der Storage-Referenz."""
        ...

    @abstractmethod
    async def delete(self, reference: str) -> None:
        """Löscht Daten."""
        ...
```

---

## 5. Domain Model

### 5.1 Entities & Value Objects

```python
# === Value Objects ===

@dataclass(frozen=True)
class DocumentId:
    value: str  # UUID

@dataclass(frozen=True)
class MimeType:
    value: str  # z.B. "application/pdf"

    def is_image(self) -> bool:
        return self.value.startswith("image/")

    def is_pdf(self) -> bool:
        return self.value == "application/pdf"

@dataclass(frozen=True)
class FileMetadata:
    filename: str
    size_bytes: int
    mime_type: MimeType
    checksum: str  # SHA-256

# === Entities ===

@dataclass
class Document:
    id: DocumentId
    metadata: FileMetadata
    storage_reference: str | None = None
    status: DocumentStatus = DocumentStatus.RECEIVED
    created_at: datetime = field(default_factory=datetime.utcnow)

@dataclass
class ExtractionResult:
    document_id: DocumentId
    raw_text: str
    structured_blocks: list[ContentBlock]
    metadata: dict[str, Any]
    extractor_used: str
    confidence: float  # 0.0 - 1.0

@dataclass
class ContentBlock:
    block_type: BlockType  # HEADING, PARAGRAPH, TABLE, LIST, IMAGE_REF
    content: str
    level: int | None = None  # für Headings
    metadata: dict[str, Any] = field(default_factory=dict)
```

### 5.2 Domain Events

```python
class DocumentReceived(DomainEvent):
    document_id: DocumentId
    mime_type: MimeType

class ExtractionCompleted(DomainEvent):
    document_id: DocumentId
    extractor_used: str
    text_length: int
    confidence: float

class ProcessingCompleted(DomainEvent):
    document_id: DocumentId
    processors_applied: list[str]

class ExtractionFailed(DomainEvent):
    document_id: DocumentId
    error: str
    extractor_used: str
```

---

## 6. API Contracts (FastAPI)

### 6.1 Endpoints

#### `POST /api/v1/documents` – Dokument hochladen

```
Request:
  Content-Type: multipart/form-data
  Body:
    file: UploadFile (required)
    output_format: str = "markdown"  (optional: "markdown" | "json" | "plaintext")
    ocr_enabled: bool = true
    language: str = "deu"
    processors: list[str] = ["cleanup", "structure"]  (optional)

Response: 202 Accepted
{
  "job_id": "uuid",
  "document_id": "uuid",
  "status": "processing",
  "created_at": "2026-02-11T10:00:00Z",
  "estimated_duration_seconds": 30
}
```

#### `GET /api/v1/documents/{document_id}` – Status abfragen

```
Response: 200 OK
{
  "document_id": "uuid",
  "status": "completed" | "processing" | "failed",
  "metadata": {
    "filename": "report.pdf",
    "mime_type": "application/pdf",
    "size_bytes": 1048576,
    "pages": 42
  },
  "result": {
    "output_format": "markdown",
    "content": "# Report Title\n\n...",
    "extraction_confidence": 0.95,
    "extractor_used": "tika",
    "processors_applied": ["cleanup", "structure"],
    "processing_time_ms": 1250
  }
}
```

#### `POST /api/v1/documents/sync` – Synchrone Extraktion (kleine Dokumente)

```
Request:
  Content-Type: multipart/form-data
  Body:
    file: UploadFile (required)
    output_format: str = "markdown"
    timeout_seconds: int = 60

Response: 200 OK
{
  "document_id": "uuid",
  "content": "# Extracted Content\n\n...",
  "metadata": { ... }
}
```

#### `GET /api/v1/health` – Health Check

```
Response: 200 OK
{
  "status": "healthy",
  "version": "0.1.0",
  "adapters": {
    "extractor": {"name": "tika", "healthy": true},
    "ocr": {"name": "tesseract", "healthy": true},
    "storage": {"name": "local", "healthy": true}
  }
}
```

#### `GET /api/v1/config/adapters` – Verfügbare Adapter

```
Response: 200 OK
{
  "extractors": [
    {"name": "tika", "active": true, "mime_types": ["application/pdf", ...]},
    {"name": "pymupdf", "active": false, "mime_types": ["application/pdf"]}
  ],
  "ocr_engines": [
    {"name": "tesseract", "active": true, "languages": ["deu", "eng"]},
    {"name": "google_vision", "active": false, "languages": ["*"]}
  ],
  "processors": [
    {"name": "cleanup", "active": true},
    {"name": "structure", "active": true},
    {"name": "llm", "active": false}
  ],
  "formatters": [
    {"name": "markdown", "active": true},
    {"name": "json", "active": true},
    {"name": "plaintext", "active": true}
  ]
}
```

### 6.2 Error Response Format

```json
{
  "error": {
    "code": "EXTRACTION_FAILED",
    "message": "Could not extract text from document",
    "details": {
      "document_id": "uuid",
      "extractor": "tika",
      "reason": "Unsupported document format"
    },
    "request_id": "uuid"
  }
}
```

### 6.3 Error Codes

| Code | HTTP Status | Beschreibung |
|------|-------------|-------------|
| `DOCUMENT_TOO_LARGE` | 413 | Dokument überschreitet Größenlimit |
| `UNSUPPORTED_FORMAT` | 415 | MIME-Type wird nicht unterstützt |
| `EXTRACTION_FAILED` | 500 | Extraktion fehlgeschlagen |
| `OCR_FAILED` | 500 | OCR-Verarbeitung fehlgeschlagen |
| `PROCESSING_TIMEOUT` | 504 | Verarbeitungs-Timeout |
| `ADAPTER_UNAVAILABLE` | 503 | Benötigter Adapter nicht verfügbar |

---

## 7. Pipeline-Architektur

Der Verarbeitungsfluss ist als Pipeline modelliert:

```
Document Upload
      │
      ▼
┌─────────────┐     ┌──────────────┐     ┌───────────────┐     ┌──────────────┐
│  Ingestion  │────▶│  Extraction  │────▶│  Processing   │────▶│   Delivery   │
│             │     │              │     │   Pipeline    │     │              │
│ • Validate  │     │ • Route by   │     │ • Cleanup     │     │ • Format     │
│ • Store     │     │   MIME-Type  │     │ • Structure   │     │ • Cache      │
│ • Metadata  │     │ • Extract    │     │ • LLM (opt.)  │     │ • Deliver    │
│             │     │ • OCR (opt.) │     │               │     │              │
└─────────────┘     └──────────────┘     └───────────────┘     └──────────────┘
```

### Extractor Routing

```python
class ExtractorRouter:
    """Routet Dokumente zum passenden Extraktor basierend auf MIME-Type."""

    def __init__(self, extractors: list[ExtractorPort]):
        self._extractors = extractors

    def resolve(self, mime_type: MimeType) -> ExtractorPort:
        for extractor in self._extractors:
            if extractor.supports(mime_type.value):
                return extractor
        raise UnsupportedFormatError(mime_type.value)
```

### Processing Pipeline

```python
class ProcessingPipeline:
    """Ausführbare Pipeline von PostProcessors."""

    def __init__(self, processors: list[PostProcessorPort]):
        self._processors = processors

    async def execute(self, text: str, context: ProcessingContext) -> str:
        result = text
        for processor in self._processors:
            result = await processor.process(result, context)
        return result
```

---

## 8. Konfigurationsmodell

```yaml
# config/docflow.yaml
app:
  name: "DocFlow"
  version: "0.1.0"
  max_file_size_mb: 100
  default_output_format: "markdown"
  default_language: "deu"

extraction:
  active_extractor: "tika"
  extractors:
    tika:
      url: "http://tika:9998"
      timeout_seconds: 120
    pymupdf:
      enabled: false

ocr:
  enabled: true
  active_engine: "tesseract"
  engines:
    tesseract:
      executable: "/usr/bin/tesseract"
      languages: ["deu", "eng"]
      dpi: 300
    google_vision:
      enabled: false
      credentials_path: "/secrets/gcp.json"

processing:
  pipeline:
    - cleanup
    - structure
  processors:
    cleanup:
      normalize_whitespace: true
      fix_encoding: true
    structure:
      detect_headings: true
      detect_tables: true
      detect_lists: true
    llm:
      enabled: false
      provider: "openai"
      model: "gpt-4"
      api_key_env: "OPENAI_API_KEY"

storage:
  backend: "local"
  local:
    base_path: "/data/documents"
  s3:
    enabled: false
    bucket: "docflow-documents"
    region: "eu-central-1"

observability:
  logging:
    level: "INFO"
    format: "json"
  metrics:
    enabled: true
    port: 9090
```

---

## 9. Docker-Architektur

```yaml
# docker-compose.yml (Übersicht)
services:
  docflow-api:        # FastAPI Application
  tika:               # Apache Tika Server
  redis:              # Job Queue / Cache (optional)
  # Optional:
  # ollama:           # Local LLM
  # minio:            # S3-kompatibler Storage
```

### Container-Übersicht

| Service | Image | Port | Zweck |
|---------|-------|------|-------|
| `docflow-api` | Custom (Python 3.12) | 8000 | FastAPI Backend |
| `tika` | `apache/tika:latest` | 9998 | Dokumenten-Parsing |
| `redis` | `redis:7-alpine` | 6379 | Job Queue, Cache |

---

## 10. Nicht-funktionale Anforderungen

| Requirement | Target | Strategie |
|-------------|--------|-----------|
| Latenz (kleine Docs) | < 3s P95 | Synchroner Pfad, Caching |
| Latenz (große Docs) | < 60s P95 | Async Job Queue |
| Durchsatz | 100 Docs/min | Horizontal Scaling, Worker Pool |
| Verfügbarkeit | 99.5% | Health Checks, Graceful Degradation |
| Max. Dateigröße | 100 MB | Konfigurierbar |
| Speicher | < 512 MB pro Worker | Streaming, Chunking |

---

## 11. Security Architecture

| Aspekt | Strategie |
|--------|-----------|
| **Authentication** | API-Key Header (Phase 1), OAuth2/OIDC (Phase 2) |
| **Authorization** | Role-based (admin, user, readonly) |
| **Input Validation** | MIME-Type Whitelist, Dateigröße, Malware-Scan (optional) |
| **Data Protection** | TLS in Transit, Encryption at Rest (Storage-Adapter) |
| **Secrets** | Environment Variables, kein Hardcoding |
| **Audit** | Structured Logging aller Operationen |

---

## 12. Evolutionspfad

| Phase | Fokus | Features |
|-------|-------|----------|
| **Phase 1** | MVP | Upload, Tika-Extraktion, Tesseract-OCR, Markdown-Output |
| **Phase 2** | Enterprise | Auth, Batch-Processing, S3-Storage, Metriken |
| **Phase 3** | Intelligence | LLM-Processing, Multi-Language, Webhooks |
| **Phase 4** | Scale | Worker-Pool, Event-Driven, gRPC, Kubernetes |
