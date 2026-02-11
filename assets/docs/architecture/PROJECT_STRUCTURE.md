# DocFlow – Projektstruktur

> Python src-Layout mit Hexagonaler Architektur

```
doc-flow/
├── docs/
│   └── architecture/
│       ├── ARCHITECTURE.md              # Gesamtarchitektur
│       └── adr/
│           └── ADR-001-hexagonal-architecture.md
│
├── src/
│   └── docflow/
│       ├── __init__.py
│       │
│       ├── domain/                      # ══ DOMAIN CORE ══
│       │   ├── __init__.py
│       │   ├── models.py                # Entities, Value Objects, Enums
│       │   ├── events.py                # Domain Events
│       │   ├── exceptions.py            # Domain Exceptions
│       │   │
│       │   └── ports/                   # ══ PORT INTERFACES ══
│       │       ├── __init__.py
│       │       ├── extractor.py         # ExtractorPort (ABC)
│       │       ├── ocr.py               # OCRPort (ABC)
│       │       ├── post_processor.py    # PostProcessorPort (ABC)
│       │       ├── output_formatter.py  # OutputFormatterPort (ABC)
│       │       ├── storage.py           # StoragePort (ABC)
│       │       └── event_bus.py         # EventBusPort (ABC)
│       │
│       ├── application/                 # ══ APPLICATION SERVICES ══
│       │   ├── __init__.py
│       │   ├── document_service.py      # Orchestrierung: Upload → Extract → Process → Format
│       │   ├── extraction_service.py    # Extractor-Routing & OCR-Fallback
│       │   ├── processing_service.py    # Pipeline-Ausführung
│       │   └── dto.py                   # Data Transfer Objects (Request/Response)
│       │
│       ├── adapters/                    # ══ ADAPTERS ══
│       │   ├── __init__.py
│       │   │
│       │   ├── inbound/                 # Driving Adapters (Primary)
│       │   │   ├── __init__.py
│       │   │   ├── api/                 # FastAPI
│       │   │   │   ├── __init__.py
│       │   │   │   ├── app.py           # FastAPI App Factory
│       │   │   │   ├── routes/
│       │   │   │   │   ├── __init__.py
│       │   │   │   │   ├── documents.py # /api/v1/documents
│       │   │   │   │   └── health.py    # /api/v1/health
│       │   │   │   ├── middleware.py     # CORS, Request-ID, Error Handling
│       │   │   │   └── dependencies.py  # FastAPI Dependency Injection
│       │   │   │
│       │   │   └── cli/                 # CLI Interface (future)
│       │   │       ├── __init__.py
│       │   │       └── main.py
│       │   │
│       │   └── outbound/               # Driven Adapters (Secondary)
│       │       ├── __init__.py
│       │       │
│       │       ├── extractors/          # ExtractorPort Implementierungen
│       │       │   ├── __init__.py
│       │       │   ├── tika_extractor.py
│       │       │   ├── pymupdf_extractor.py
│       │       │   └── textract_extractor.py
│       │       │
│       │       ├── ocr/                 # OCRPort Implementierungen
│       │       │   ├── __init__.py
│       │       │   ├── tesseract_ocr.py
│       │       │   ├── google_vision_ocr.py
│       │       │   └── azure_ocr.py
│       │       │
│       │       ├── processors/          # PostProcessorPort Implementierungen
│       │       │   ├── __init__.py
│       │       │   ├── cleanup_processor.py
│       │       │   ├── structure_processor.py
│       │       │   └── llm_processor.py
│       │       │
│       │       ├── formatters/          # OutputFormatterPort Implementierungen
│       │       │   ├── __init__.py
│       │       │   ├── markdown_formatter.py
│       │       │   ├── json_formatter.py
│       │       │   └── plaintext_formatter.py
│       │       │
│       │       └── storage/             # StoragePort Implementierungen
│       │           ├── __init__.py
│       │           ├── local_storage.py
│       │           └── s3_storage.py
│       │
│       └── infrastructure/             # ══ INFRASTRUCTURE ══
│           ├── __init__.py
│           ├── config.py               # Pydantic Settings, YAML Loader
│           ├── registry.py             # AdapterRegistry – DI Container
│           ├── logging.py              # Structured Logging Setup
│           └── event_bus.py            # InMemoryEventBus Implementation
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py                     # Shared Fixtures
│   │
│   ├── unit/
│   │   ├── __init__.py
│   │   ├── domain/
│   │   │   ├── test_models.py
│   │   │   └── test_events.py
│   │   ├── application/
│   │   │   ├── test_document_service.py
│   │   │   ├── test_extraction_service.py
│   │   │   └── test_processing_service.py
│   │   └── adapters/
│   │       └── outbound/
│   │           ├── test_cleanup_processor.py
│   │           └── test_markdown_formatter.py
│   │
│   ├── integration/
│   │   ├── __init__.py
│   │   ├── test_tika_extractor.py
│   │   ├── test_tesseract_ocr.py
│   │   └── test_api_endpoints.py
│   │
│   └── fakes/                          # In-Memory Fakes für Tests
│       ├── __init__.py
│       ├── fake_extractor.py
│       ├── fake_ocr.py
│       ├── fake_storage.py
│       └── fake_processor.py
│
├── config/
│   ├── docflow.yaml                    # Default-Konfiguration
│   └── docflow.production.yaml         # Production Overrides
│
├── docker/
│   ├── Dockerfile                      # Multi-Stage Build
│   └── docker-compose.yml              # Full Stack
│
├── pyproject.toml                      # Project Metadata, Dependencies
├── README.md
├── LICENSE
└── .env.example                        # Environment Variables Template
```

## Abhängigkeitsregel (Dependency Rule)

```
Adapters (inbound + outbound)
    │
    ▼ depends on
Application Services
    │
    ▼ depends on
Domain (Models + Ports)
    │
    ▼ depends on
NOTHING (zero external dependencies)
```

**Die Domain hat KEINE imports aus `adapters/`, `infrastructure/` oder externen Libraries.**  
Die einzigen Imports in der Domain sind: `abc`, `dataclasses`, `enum`, `datetime`, `typing` – alles Python stdlib.

## Namenskonventionen

| Element | Konvention | Beispiel |
|---------|-----------|---------|
| Port Interface | `{Name}Port` | `ExtractorPort`, `OCRPort` |
| Adapter | `{Technology}{Port}Adapter` | `TikaExtractorAdapter` |
| Domain Event | `{Entity}{Verb}` | `DocumentReceived`, `ExtractionCompleted` |
| Application Service | `{Context}Service` | `DocumentService`, `ExtractionService` |
| DTO | `{Action}{Request\|Response}` | `ProcessDocumentRequest` |
| Config | `{Component}Config` | `TikaConfig`, `OCRConfig` |
