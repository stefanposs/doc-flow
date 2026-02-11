# DocFlow — End-to-End Document Text Extraction Pipeline

Extract text from **any document** — PDF, Office, images, scans — and get clean **Markdown**, JSON, or plain text output.

Built with a **hexagonal architecture** where every technology (Tika, Tesseract, LLMs) is swappable via configuration.

---

## Architecture

```
Document (PDF/DOCX/Image)
    → [Extractor Router]
        → PyMuPDF (PDF) / Tika (1000+ formats) / Tesseract (OCR)
    → [Post-Processing]
        → Cleanup / Structure / (optional LLM)
    → [Output Formatter]
        → Markdown / JSON / Plain Text
```

### Tech Stack

| Component | Technology |
|-----------|-----------|
| **Backend** | FastAPI + Pydantic v2 |
| **Extraction** | Apache Tika (HTTP) + PyMuPDF |
| **OCR** | Tesseract 5 |
| **Architecture** | Hexagonal (Ports & Adapters) |
| **Packaging** | uv + ruff + mypy |
| **Infrastructure** | Docker Compose |
| **CI/CD** | GitHub Actions |

---

## Quick Start

### Docker (recommended)

```bash
git clone https://github.com/stefanposs/doc-flow.git
cd doc-flow
docker compose -f docker/docker-compose.yml up -d
```

### Extract a document

```bash
curl -X POST http://localhost:8000/api/v1/extract \
  -F "file=@document.pdf" \
  -F "output_format=markdown"
```

### Development Setup

```bash
# Install dependencies
just setup

# Start dev stack
just dev

# Run tests
just test

# Full QA
just qa
```

---

## Project Structure

```
src/docflow/
├── domain/                 # Models, Events, Ports (zero deps)
│   ├── models.py           # Document, Metadata, Enums
│   ├── events.py           # Domain events
│   └── ports.py            # 5 ABC interfaces
├── application/            # Pipeline orchestration
│   ├── config.py           # pydantic-settings
│   ├── pipeline.py         # ExtractorRouter + ProcessingPipeline
│   └── service.py          # DocumentService
├── adapters/
│   ├── inbound/
│   │   ├── api/            # FastAPI (app, routes, schemas, DI)
│   │   └── cli.py          # CLI entry point
│   └── outbound/
│       ├── extractors/     # Tika, PyMuPDF
│       ├── ocr/            # Tesseract
│       ├── processors/     # Cleanup
│       ├── formatters/     # Markdown, JSON, PlainText
│       └── storage/        # Local filesystem
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/health` | Health check |
| `POST` | `/api/v1/extract` | Extract text (JSON response) |
| `POST` | `/api/v1/extract/raw` | Extract text (raw content) |
| `GET` | `/api/v1/formats` | List supported formats |

Interactive API docs: [http://localhost:8000/api/docs](http://localhost:8000/api/docs)

---

## Pluggable Adapters

Every technology is behind a Port interface (Python ABC). Switch via config:

```bash
# Use PyMuPDF for PDFs (default for PDF)
DOCFLOW_DEFAULT_EXTRACTOR=pymupdf

# Use Tika for everything
DOCFLOW_DEFAULT_EXTRACTOR=tika

# Disable OCR
DOCFLOW_OCR_ENABLED=false

# Change OCR language
DOCFLOW_OCR_LANGUAGE=eng
```

Adding a new adapter = implement the ABC + register in `dependencies.py`. No core changes needed.

---

## Available Commands

```bash
just               # Show all commands
just setup         # Install dependencies
just dev           # Start Docker dev stack
just test          # Run all tests
just lint          # Run ruff linter
just format        # Auto-format code
just typecheck     # Run mypy
just qa            # Full QA pipeline
just docs          # Serve docs locally
just ci            # Simulate CI locally
```

---

## Documentation

Full documentation: [https://stefanposs.github.io/doc-flow](https://stefanposs.github.io/doc-flow)

---

## License

MIT — see [LICENSE](LICENSE) for details.
