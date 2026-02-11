# Ports & Adapters

DocFlow defines **5 outbound ports** (interfaces) that decouple the domain from any specific technology.

---

## Port Overview

| Port | Purpose | Adapters |
|------|---------|----------|
| `ExtractorPort` | Extract raw text from documents | Tika, PyMuPDF |
| `OCRPort` | Optical character recognition | Tesseract |
| `PostProcessorPort` | Text post-processing | Cleanup |
| `OutputFormatterPort` | Format output | Markdown, JSON, PlainText |
| `StoragePort` | File storage | Local filesystem |

---

## ExtractorPort

```python
class ExtractorPort(ABC):
    @abstractmethod
    async def extract(self, file_content: bytes, mime_type: str) -> ExtractionResult: ...

    @abstractmethod
    def supported_mime_types(self) -> set[str]: ...

    @property
    @abstractmethod
    def name(self) -> str: ...
```

**Implementations:**

- **TikaExtractor** — HTTP client to Apache Tika server. Supports 1000+ formats.
- **PyMuPDFExtractor** — Direct PDF parsing. 10-50x faster than Tika for PDFs.

---

## OCRPort

```python
class OCRPort(ABC):
    @abstractmethod
    async def recognize(self, image_content: bytes, language: str = "eng") -> str: ...
```

**Implementations:**

- **TesseractOCR** — Self-hosted, open-source. Runs in thread pool.

**Planned:** Google Vision, Azure Computer Vision

---

## PostProcessorPort

```python
class PostProcessorPort(ABC):
    @abstractmethod
    async def process(self, text: str, context: dict | None = None) -> str: ...
```

**Implementations:**

- **CleanupProcessor** — Normalize whitespace, fix OCR artifacts, rejoin hyphenation.

**Planned:** LLM post-processor (OpenAI, Ollama)

---

## OutputFormatterPort

```python
class OutputFormatterPort(ABC):
    @abstractmethod
    async def format(self, text: str, metadata: dict | None = None) -> ProcessingResult: ...
```

**Implementations:**

- **MarkdownFormatter** — Clean Markdown with YAML front matter
- **JSONFormatter** — Structured JSON with content + metadata
- **PlainTextFormatter** — Pass-through, no formatting

---

## Adding a New Adapter

1. Create a new file in `src/docflow/adapters/outbound/<category>/`
2. Implement the corresponding port (ABC)
3. Register it in `dependencies.py`
4. Add the new package to `pyproject.toml` optional dependencies

No changes to domain or application layer required.
