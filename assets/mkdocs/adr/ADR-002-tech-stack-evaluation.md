# ADR-002: Tech Stack Evaluation für DocFlow

## Status

**Proposed** – 2026-02-11

## Context

DocFlow benötigt konkrete Technologie-Entscheidungen für jeden Adapter-Layer der hexagonalen Architektur. Diese ADR bewertet die Optionen entlang der Kriterien **Austauschbarkeit**, **Enterprise-Tauglichkeit** und **einfache Einrichtung**.

---

## 1. Document Extraction (Adapter-Layer)

### Bewertungsmatrix

| Technologie | Formate | Self-Hosted | Genauigkeit | Setup | Enterprise |
|-------------|---------|-------------|-------------|-------|------------|
| Apache Tika (HTTP) | PDF, Office, HTML, 1000+ | ✅ | ⭐⭐⭐ | Einfach (Docker) | ✅ |
| PyMuPDF (fitz) | PDF only | ✅ | ⭐⭐⭐⭐ | Sehr einfach (pip) | ✅ |
| python-docx/openpyxl/pptx | Office only | ✅ | ⭐⭐⭐⭐ | Einfach (pip) | ✅ |
| AWS Textract | PDF, Bilder | ❌ Cloud | ⭐⭐⭐⭐⭐ | Mittel (IAM) | ✅ |
| Google Document AI | PDF, Bilder | ❌ Cloud | ⭐⭐⭐⭐⭐ | Mittel (GCP) | ✅ |
| Unstructured.io | PDF, Office, HTML | ✅ | ⭐⭐⭐⭐ | Komplex | ⚠️ Lizenz |

### Empfehlung: Gestaffelter Ansatz (3 Adapter)

| Phase | Adapter | Begründung |
|-------|---------|------------|
| **Phase 1 (MVP)** | **Apache Tika (HTTP)** + **PyMuPDF** | Tika als Allrounder (1000+ Formate via Docker-Container). PyMuPDF für performantes PDF-Parsing ohne Netzwerk-Overhead. |
| **Phase 2 (Enterprise)** | + **AWS Textract** / **Google Document AI** | Cloud-Adapter für Kunden mit hohen Genauigkeitsanforderungen. |
| Nicht empfohlen | Unstructured.io | Zu viel eigene Abstraktion, kollidiert mit eurer hexagonalen Architektur. Übernimmt Routing-Logik, die in eurem `ExtractorRouter` gehört. |

**Begründung Tika als Primary:**
- Docker-Image (`apache/tika:3.0.0`) → passt zu eurem `docker-compose.yml`
- HTTP-API → saubere Entkopplung, Health-Checkbar, im Crash kein Python-Prozess betroffen
- 1000+ MIME-Types → ein Adapter deckt 90% der Formate ab
- Mature (Apache Foundation), Enterprise-proven

**Begründung PyMuPDF als Secondary:**
- 10-50x schneller als Tika für reine PDF-Extraktion
- Kein externer Service nötig → ideal für den synchronen Pfad (`/api/v1/documents/sync`)
- Native Tabellen-Erkennung und Layout-Analyse

### Port Interface (aus ARCHITECTURE.md bestätigt)

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class BlockType(StrEnum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    TABLE = "table"
    LIST = "list"
    IMAGE_REF = "image_ref"


@dataclass(frozen=True)
class ContentBlock:
    block_type: BlockType
    content: str
    level: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExtractionResult:
    document_id: str
    raw_text: str
    structured_blocks: list[ContentBlock]
    metadata: dict[str, Any]
    extractor_used: str
    confidence: float  # 0.0 – 1.0


class ExtractorPort(ABC):
    """Outbound Port für Dokumenten-Extraktion.

    Jeder Adapter implementiert genau dieses Interface.
    Die Domain kennt keine konkreten Extraktoren.
    """

    @abstractmethod
    async def extract(self, file_data: bytes, mime_type: str) -> ExtractionResult:
        """Extrahiert Rohtext und Struktur aus einem Dokument."""
        ...

    @abstractmethod
    def supports(self, mime_type: str) -> bool:
        """Prüft ob dieser Extraktor den MIME-Type verarbeiten kann."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Eindeutiger Adapter-Name für Registry und Logging."""
        ...
```

### Adapter-Skeleton: Tika

```python
import httpx

from docflow.domain.ports.extractor import ExtractorPort, ExtractionResult


class TikaExtractorAdapter(ExtractorPort):
    """Adapter: Apache Tika via HTTP API."""

    _SUPPORTED_TYPES = frozenset({
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "text/html",
        "text/plain",
    })

    def __init__(self, base_url: str = "http://tika:9998", timeout: float = 120.0) -> None:
        self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout)

    async def extract(self, file_data: bytes, mime_type: str) -> ExtractionResult:
        response = await self._client.put(
            "/tika",
            content=file_data,
            headers={"Content-Type": mime_type, "Accept": "text/plain"},
        )
        response.raise_for_status()
        raw_text = response.text
        # ... parse structured_blocks from Tika metadata endpoint ...
        return ExtractionResult(
            document_id="",  # Set by caller
            raw_text=raw_text,
            structured_blocks=[],
            metadata={"source": "tika"},
            extractor_used=self.name,
            confidence=0.85,
        )

    def supports(self, mime_type: str) -> bool:
        return mime_type in self._SUPPORTED_TYPES

    @property
    def name(self) -> str:
        return "tika"
```

### Packages

```toml
# pyproject.toml – Extraction dependencies
[project.optional-dependencies]
tika = ["httpx>=0.27,<1.0"]
pymupdf = ["PyMuPDF>=1.24,<2.0"]
office = [
    "python-docx>=1.1,<2.0",
    "openpyxl>=3.1,<4.0",
    "python-pptx>=1.0,<2.0",
]
textract = ["boto3>=1.35,<2.0"]
```

### Fallstricke

| Problem | Lösung |
|---------|--------|
| Tika-Server crasht bei korrupten PDFs | Timeout + Circuit Breaker. Health-Check via `/tika` GET. |
| `tika-python` Library startet eigenen JVM-Prozess | **Nicht verwenden.** Direkt HTTP via `httpx` ansprechen. |
| PyMuPDF hat C-Extension → Build-Probleme in Alpine | `python:3.12-slim` (Debian-basiert) statt Alpine verwenden. |
| Große Dateien (>50 MB) via Tika blockieren | Streaming via `PUT /tika` mit chunked transfer. Timeout konfigurierbar. |

---

## 2. OCR

### Bewertungsmatrix

| Technologie | Sprachen | Self-Hosted | Genauigkeit | Latenz | Kosten |
|-------------|----------|-------------|-------------|--------|--------|
| Tesseract 5 | 100+ | ✅ | ⭐⭐⭐ | Mittel | Kostenlos |
| EasyOCR | 80+ | ✅ | ⭐⭐⭐½ | Langsam (GPU) | Kostenlos |
| PaddleOCR | 80+ | ✅ | ⭐⭐⭐⭐ | Schnell (GPU) | Kostenlos |
| Google Vision API | 100+ | ❌ Cloud | ⭐⭐⭐⭐⭐ | Schnell | $1.50/1000 S. |
| Azure Computer Vision | 100+ | ❌ Cloud | ⭐⭐⭐⭐⭐ | Schnell | $1.00/1000 S. |

### Empfehlung: Tesseract (Phase 1) + Cloud-Adapter (Phase 2)

**Phase 1: Tesseract 5 via `pytesseract`**
- Zero-Cost, Self-Hosted, Docker-freundlich (`apt install tesseract-ocr`)
- Gut genug für maschinell erstellte Scans (>90% Accuracy)
- Sprach-Packs per `apt install tesseract-ocr-deu tesseract-ocr-eng`

**Phase 2: Google Vision API als Premium-Adapter**
- Für handschriftliche Dokumente, schlechte Scan-Qualität
- Deutlich höhere Accuracy bei schwierigen Vorlagen
- Pay-per-Use → Enterprise-Kunden tragen die Kosten

**Nicht empfohlen für Phase 1:**
- **EasyOCR**: Schwere PyTorch-Dependency (>2 GB), langsam ohne GPU
- **PaddleOCR**: Gute Accuracy, aber PaddlePaddle-Framework ist exotisch, schlechte Docs in Englisch, große Installation

### Port Interface

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True)
class OCRRegion:
    """Ein erkannter Textbereich mit Bounding Box."""
    text: str
    confidence: float
    bbox: tuple[int, int, int, int]  # x, y, width, height


@dataclass(frozen=True)
class OCRResult:
    full_text: str
    regions: list[OCRRegion]
    language_detected: str
    average_confidence: float
    engine_used: str
    metadata: dict[str, object] = field(default_factory=dict)


class OCRPort(ABC):
    """Outbound Port für Optical Character Recognition.

    Empfängt Bilddaten (PNG/JPEG/TIFF), liefert strukturierten Text.
    """

    @abstractmethod
    async def recognize(
        self,
        image_data: bytes,
        language: str = "deu",
        *,
        dpi: int = 300,
    ) -> OCRResult:
        """Führt OCR auf den übergebenen Bilddaten durch."""
        ...

    @abstractmethod
    def supported_languages(self) -> frozenset[str]:
        """Menge der unterstützten Sprachcodes (ISO 639-3)."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Adapter-Name für Registry und Konfiguration."""
        ...
```

### Adapter-Skeleton: Tesseract

```python
import asyncio
from functools import partial
from pathlib import Path

from PIL import Image
import pytesseract

from docflow.domain.ports.ocr import OCRPort, OCRResult, OCRRegion


class TesseractOCRAdapter(OCRPort):
    """Adapter: Tesseract 5 via pytesseract."""

    def __init__(
        self,
        executable: str = "/usr/bin/tesseract",
        languages: list[str] | None = None,
    ) -> None:
        pytesseract.pytesseract.tesseract_cmd = executable
        self._languages = frozenset(languages or ["deu", "eng"])

    async def recognize(
        self,
        image_data: bytes,
        language: str = "deu",
        *,
        dpi: int = 300,
    ) -> OCRResult:
        # Blocking Tesseract-Call in Thread-Pool auslagern
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            partial(self._run_tesseract, image_data, language, dpi),
        )
        return result

    def _run_tesseract(self, image_data: bytes, language: str, dpi: int) -> OCRResult:
        import io
        image = Image.open(io.BytesIO(image_data))
        # TSV-Output für Bounding Boxes + Confidence
        data = pytesseract.image_to_data(
            image, lang=language, output_type=pytesseract.Output.DICT,
            config=f"--dpi {dpi}",
        )
        full_text = pytesseract.image_to_string(image, lang=language)
        regions = self._parse_regions(data)
        avg_conf = sum(r.confidence for r in regions) / max(len(regions), 1)
        return OCRResult(
            full_text=full_text.strip(),
            regions=regions,
            language_detected=language,
            average_confidence=avg_conf,
            engine_used=self.name,
        )

    def _parse_regions(self, data: dict) -> list[OCRRegion]:
        regions: list[OCRRegion] = []
        for i, text in enumerate(data["text"]):
            conf = float(data["conf"][i])
            if conf > 0 and text.strip():
                regions.append(OCRRegion(
                    text=text.strip(),
                    confidence=conf / 100.0,
                    bbox=(data["left"][i], data["top"][i],
                          data["width"][i], data["height"][i]),
                ))
        return regions

    def supported_languages(self) -> frozenset[str]:
        return self._languages

    @property
    def name(self) -> str:
        return "tesseract"
```

### Packages

```toml
[project.optional-dependencies]
tesseract = [
    "pytesseract>=0.3.13,<1.0",
    "Pillow>=11.0,<12.0",
]
google-vision = ["google-cloud-vision>=3.8,<4.0"]
azure-ocr = ["azure-ai-vision-imageanalysis>=1.0,<2.0"]
```

### Fallstricke

| Problem | Lösung |
|---------|--------|
| Tesseract ist blocking (kein async) | `loop.run_in_executor()` — **niemals** direkt in async aufrufen! |
| Tesseract braucht Sprachpakete im Container | `Dockerfile`: `RUN apt-get install -y tesseract-ocr-deu tesseract-ocr-eng` |
| Schlechte OCR-Qualität bei niedrigem DPI | Image-Preprocessing: Upscale auf 300 DPI, Binarisierung, Deskew vor OCR |
| Memory-Spikes bei großen Bildern | `Pillow` max-pixel-Limit setzen: `Image.MAX_IMAGE_PIXELS = 200_000_000` |
| `pytesseract` gibt leise leeren String bei fehlender Sprache | `supported_languages()` in Router prüfen, bevor OCR gestartet wird |

---

## 3. LLM Post-Processing

### Bewertungsmatrix

| Technologie | Self-Hosted | Qualität | Latenz | Kosten | Datenschutz |
|-------------|-------------|----------|--------|--------|-------------|
| OpenAI GPT-4o | ❌ Cloud | ⭐⭐⭐⭐⭐ | 2-10s | $2.50/1M in | ⚠️ Daten an OpenAI |
| Anthropic Claude 3.5 | ❌ Cloud | ⭐⭐⭐⭐⭐ | 2-8s | $3.00/1M in | ⚠️ Daten an Anthropic |
| Ollama (llama3, mistral) | ✅ | ⭐⭐⭐ | 5-30s | Hardware | ✅ On-Premise |
| LangChain | N/A (Layer) | N/A | N/A | N/A | N/A |

### Empfehlung: Direkte SDK-Integration (kein LangChain)

**Phase 1 (MVP): Kein LLM – regelbasiertes Processing**
- `CleanupProcessor` und `StructureProcessor` reichen für 80% der Fälle
- Kein API-Cost, kein Latenz-Overhead, deterministisch

**Phase 3 (Intelligence): OpenAI + Ollama als zwei Adapter**
- OpenAI für höchste Qualität (Cloud-Kunden)
- Ollama für On-Premise / DSGVO-konforme Deployments

**LangChain wird NICHT empfohlen:**
- Zu viel Abstraktion, die mit eurem Port-System kollidiert
- Eure `PostProcessorPort` ABC IST die Abstraktion — LangChain wäre eine redundante Zwischenschicht
- Häufige Breaking Changes, komplexe Dependency-Chain
- Direkte `httpx`/`openai`-Calls in Adaptern sind einfacher, testbarer, debugbarer

### Port Interface

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ProcessingContext:
    """Kontext für den Processor: Sprache, gewünschte Struktur, etc."""
    language: str = "deu"
    source_mime_type: str = "application/pdf"
    extraction_confidence: float = 1.0
    options: dict[str, Any] = field(default_factory=dict)


class PostProcessorPort(ABC):
    """Outbound Port für Text-Nachbearbeitung.

    Wird in einer Pipeline sequenziell aufgerufen.
    Jeder Processor transformiert den Text und gibt ihn weiter.
    """

    @abstractmethod
    async def process(self, text: str, context: ProcessingContext) -> str:
        """Verarbeitet den Text. Gibt den transformierten Text zurück."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Eindeutiger Name für Pipeline-Konfiguration."""
        ...


class LLMPort(ABC):
    """Spezialisierter Port für LLM-basierte Verarbeitung.

    Erweitert PostProcessorPort um LLM-spezifische Capabilities.
    Wird vom LLMPostProcessor-Adapter intern genutzt.
    """

    @abstractmethod
    async def complete(
        self,
        prompt: str,
        *,
        system_message: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.1,
    ) -> str:
        """Sendet Prompt an LLM und gibt die Antwort zurück."""
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        """Health-Check: Ist das LLM erreichbar?"""
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Name des verwendeten Modells."""
        ...
```

### Adapter-Skeleton: OpenAI

```python
from openai import AsyncOpenAI

from docflow.domain.ports.post_processor import LLMPort


class OpenAILLMAdapter(LLMPort):
    """Adapter: OpenAI API (GPT-4o, GPT-4o-mini)."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o",
        base_url: str | None = None,
    ) -> None:
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._model = model

    async def complete(
        self,
        prompt: str,
        *,
        system_message: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.1,
    ) -> str:
        messages: list[dict[str, str]] = []
        if system_message:
            messages.append({"role": "system", "content": system_message})
        messages.append({"role": "user", "content": prompt})

        response = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return response.choices[0].message.content or ""

    async def is_available(self) -> bool:
        try:
            await self._client.models.retrieve(self._model)
            return True
        except Exception:
            return False

    @property
    def model_name(self) -> str:
        return self._model
```

### Adapter-Skeleton: Ollama

```python
import httpx

from docflow.domain.ports.post_processor import LLMPort


class OllamaLLMAdapter(LLMPort):
    """Adapter: Ollama (lokale LLMs – llama3, mistral, etc.)."""

    def __init__(
        self,
        base_url: str = "http://ollama:11434",
        model: str = "llama3.1:8b",
    ) -> None:
        self._client = httpx.AsyncClient(base_url=base_url, timeout=120.0)
        self._model = model

    async def complete(
        self,
        prompt: str,
        *,
        system_message: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.1,
    ) -> str:
        payload: dict = {
            "model": self._model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        if system_message:
            payload["system"] = system_message

        response = await self._client.post("/api/generate", json=payload)
        response.raise_for_status()
        return response.json()["response"]

    async def is_available(self) -> bool:
        try:
            resp = await self._client.get("/api/tags")
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    @property
    def model_name(self) -> str:
        return self._model
```

### LLM-Processor, der den LLMPort nutzt

```python
from docflow.domain.ports.post_processor import PostProcessorPort, ProcessingContext, LLMPort


class LLMPostProcessor(PostProcessorPort):
    """Nutzt ein LLM zur intelligenten Text-Strukturierung.

    Kapselt den LLMPort — der LLMPostProcessor ist selbst
    ein PostProcessorPort und fügt sich in die Pipeline ein.
    """

    SYSTEM_PROMPT = (
        "Du bist ein Dokumenten-Strukturierungs-Experte. "
        "Transformiere den folgenden extrahierten Rohtext in sauberes, "
        "strukturiertes Markdown. Behalte alle Informationen bei."
    )

    def __init__(self, llm: LLMPort) -> None:
        self._llm = llm

    async def process(self, text: str, context: ProcessingContext) -> str:
        if not await self._llm.is_available():
            # Graceful Degradation: Text unverändert durchreichen
            return text

        prompt = f"Sprache: {context.language}\n\nRohtext:\n{text}"
        return await self._llm.complete(
            prompt,
            system_message=self.SYSTEM_PROMPT,
            temperature=0.1,
        )

    @property
    def name(self) -> str:
        return "llm"
```

### Packages

```toml
[project.optional-dependencies]
openai = ["openai>=1.55,<2.0"]
ollama = ["httpx>=0.27,<1.0"]  # Direct HTTP, kein extra SDK nötig
anthropic = ["anthropic>=0.40,<1.0"]
```

### Fallstricke

| Problem | Lösung |
|---------|--------|
| LLM-Halluzinationen verändern Dokumentinhalt | `temperature=0.1`, Prompt-Engineering: "Keine Informationen hinzufügen oder entfernen" |
| Token-Limits bei großen Dokumenten | Chunking-Strategie: Dokument in Blöcke aufteilen, einzeln verarbeiten |
| API-Kosten explodieren | Token-Tracking pro Request, Budget-Limits in Config, LLM als opt-in |
| Latenz (2-30s pro Call) | LLM-Processing nur als *optionaler* Pipeline-Schritt, nie im Sync-Pfad |
| DSGVO: Daten an Cloud-LLM | Ollama-Adapter für On-Premise, Kunden-Konfiguration welcher LLM-Provider |
| LangChain Overhead | **Nicht verwenden** — euer `PostProcessorPort` + `LLMPort` ist die sauberere Abstraktion |

---

## 4. Framework & Tools

### 4.1 Web Framework: FastAPI vs. Litestar

| Kriterium | FastAPI | Litestar |
|-----------|---------|----------|
| Maturity | ⭐⭐⭐⭐⭐ (seit 2018) | ⭐⭐⭐ (seit 2022) |
| Community | Riesig, 75k+ GitHub Stars | Klein, 5k+ Stars |
| Ecosystem | Umfangreich (Auth, CORS, etc.) | Wachsend |
| Performance | Sehr gut (Starlette) | Leicht besser (eigener Router) |
| DI System | Einfach (Depends) | Mächtiger (native DI) |
| Hiring | Einfach | Schwierig |
| OpenAPI | Automatisch | Automatisch |

**Empfehlung: FastAPI**
- Größeres Ecosystem, einfacheres Hiring, mehr Battle-Tested
- Litestar hat ein besseres DI-System, aber ihr habt bereits eure eigene `AdapterRegistry`
- Der Performance-Unterschied ist bei I/O-bound Workloads (Extraktion) irrelevant

### 4.2 Validation: Pydantic v2

**Empfehlung: Pydantic v2 — keine Alternative.**

Pydantic v2 ist der Standard für:
- API Request/Response Schemas (FastAPI-Integration)
- Configuration (`pydantic-settings` für `docflow.yaml` + ENV)
- DTOs zwischen Application- und Adapter-Layer

```python
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class TikaConfig(BaseSettings):
    """Konfiguration für den Tika-Adapter. Liest aus ENV + YAML."""
    url: str = Field(default="http://tika:9998", alias="TIKA_URL")
    timeout_seconds: float = Field(default=120.0, gt=0)

    model_config = {"env_prefix": "DOCFLOW_TIKA_"}


class ProcessDocumentRequest(BaseModel):
    """API Request Schema."""
    output_format: str = Field(default="markdown", pattern=r"^(markdown|json|plaintext)$")
    ocr_enabled: bool = True
    language: str = Field(default="deu", min_length=2, max_length=3)
    processors: list[str] = Field(default=["cleanup", "structure"])
```

### 4.3 Background Jobs: Celery vs. ARQ vs. asyncio TaskGroups

| Kriterium | Celery | ARQ | asyncio TaskGroups |
|-----------|--------|-----|-------------------|
| Maturity | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ (stdlib) |
| Broker | Redis, RabbitMQ | Redis only | Keiner (in-process) |
| Horizontal Scale | ✅ Multi-Worker | ✅ Multi-Worker | ❌ Single-Process |
| Retry/DLQ | ✅ Built-in | ✅ Built-in | ❌ Manuell |
| Monitoring | Flower Dashboard | Minimal | ❌ |
| Async-native | ❌ (sync by default) | ✅ | ✅ |
| Komplexität | Hoch | Niedrig | Sehr niedrig |

**Empfehlung: Gestaffelter Ansatz**

| Phase | Lösung | Begründung |
|-------|--------|------------|
| **Phase 1** | **asyncio TaskGroups + in-memory Queue** | Kein Redis nötig, einfaches Setup, reicht für 100 Docs/min |
| **Phase 4** | **ARQ** (oder Celery wenn RabbitMQ schon da) | Wenn horizontal skaliert werden muss |

**Gegen Celery in Phase 1:**
- Celery ist sync-first — kollidiert mit eurer async-Pipeline
- Braucht Redis/RabbitMQ → zusätzlicher Container
- Overengineered für das MVP

```python
# Phase 1: Simple async background processing
import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field


@dataclass
class JobQueue:
    """Einfache in-process Job Queue für Phase 1."""
    _tasks: dict[str, asyncio.Task] = field(default_factory=dict)

    async def enqueue(
        self,
        job_id: str,
        coro: Awaitable,
    ) -> None:
        task = asyncio.create_task(coro)
        self._tasks[job_id] = task

    def get_status(self, job_id: str) -> str:
        if job_id not in self._tasks:
            return "not_found"
        task = self._tasks[job_id]
        if task.done():
            return "failed" if task.exception() else "completed"
        return "processing"
```

### 4.4 Database: SQLAlchemy vs. SQLModel

| Kriterium | SQLAlchemy 2.0 | SQLModel |
|-----------|---------------|----------|
| Maturity | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |
| Async Support | ✅ (asyncio extension) | ✅ (via SQLAlchemy) |
| Pydantic Integration | Manuell | ✅ Native |
| Migrations | Alembic | Alembic |
| Complex Queries | ✅ Vollständig | ⚠️ Limitiert |
| Documentation | Excellent | Dünn |

**Empfehlung: SQLAlchemy 2.0 + Alembic**
- SQLModel ist ein dünner Wrapper um SQLAlchemy — bei Problemen fallt ihr durch auf SQLAlchemy
- SQLAlchemy 2.0 hat native Type-Hints → die Pydantic-Convenience von SQLModel braucht ihr nicht
- Eure Entities sind Domain-Objekte (Dataclasses), keine ORM-Modelle — das Mapping gehört in den Persistence-Adapter

```python
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class DocumentRecord(Base):
    """Persistence Model — NICHT das Domain-Entity!"""
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(primary_key=True)
    filename: Mapped[str]
    mime_type: Mapped[str]
    size_bytes: Mapped[int]
    status: Mapped[str]
    storage_reference: Mapped[str | None]
    created_at: Mapped[datetime]
```

### 4.5 File Storage: MinIO / S3

**Empfehlung: S3-kompatibles Interface (MinIO für Dev, AWS S3 für Prod)**

```python
from docflow.domain.ports.storage import StoragePort


class S3StorageAdapter(StoragePort):
    """Adapter: S3-kompatibler Object Storage (AWS S3, MinIO, etc.)."""

    def __init__(
        self,
        bucket: str,
        endpoint_url: str | None = None,  # MinIO: "http://minio:9000"
        region: str = "eu-central-1",
    ) -> None:
        import aiobotocore.session
        self._session = aiobotocore.session.get_session()
        self._bucket = bucket
        self._endpoint_url = endpoint_url
        self._region = region

    async def store(self, document_id: str, data: bytes, metadata: dict) -> str:
        key = f"documents/{document_id}"
        async with self._session.create_client(
            "s3",
            endpoint_url=self._endpoint_url,
            region_name=self._region,
        ) as client:
            await client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=data,
                Metadata={k: str(v) for k, v in metadata.items()},
            )
        return f"s3://{self._bucket}/{key}"

    async def retrieve(self, reference: str) -> bytes:
        _, _, bucket, key = reference.replace("s3://", "").split("/", 1)
        # ... retrieve implementation ...

    async def delete(self, reference: str) -> None:
        # ... delete implementation ...
```

### Packages

```toml
[project.dependencies]
fastapi = ">=0.115,<1.0"
uvicorn = {version = ">=0.32,<1.0", extras = ["standard"]}
pydantic = ">=2.10,<3.0"
pydantic-settings = ">=2.6,<3.0"
httpx = ">=0.27,<1.0"
structlog = ">=24.4,<26.0"

[project.optional-dependencies]
database = [
    "sqlalchemy[asyncio]>=2.0,<3.0",
    "alembic>=1.14,<2.0",
    "asyncpg>=0.30,<1.0",       # PostgreSQL async driver
    "aiosqlite>=0.20,<1.0",     # SQLite für Dev/Tests
]
s3 = ["aiobotocore>=2.15,<3.0"]
```

---

## 5. Python Packaging

### Empfehlung: src-Layout + pyproject.toml + uv

| Tool | Empfehlung | Begründung |
|------|-----------|------------|
| **Layout** | `src/docflow/` | Bereits so in PROJECT_STRUCTURE.md. Verhindert accidental imports. |
| **Package Manager** | **uv** | 10-100x schneller als pip/poetry, native lockfile, stabiles CLI |
| **Linting** | **ruff** | Ersetzt flake8 + isort + Black + pyupgrade. Ein Tool, <100ms |
| **Type Checking** | **mypy** (strict) | Standard für Enterprise Python |
| **Testing** | **pytest** + **pytest-asyncio** | Standard, kein Grund für Alternativen |

### uv vs. poetry vs. pip

| Kriterium | uv | poetry | pip + pip-tools |
|-----------|-----|--------|----------------|
| Speed | ⭐⭐⭐⭐⭐ (Rust) | ⭐⭐ | ⭐⭐⭐ |
| Lockfile | ✅ `uv.lock` | ✅ `poetry.lock` | ✅ `requirements.txt` |
| PEP 621 Compliance | ✅ `pyproject.toml` | ⚠️ Eigenes Format | ✅ |
| Workspace Support | ✅ | ❌ | ❌ |
| Venv Management | ✅ Built-in | ✅ Built-in | ❌ Manuell |
| Adoption Trend | 📈 Stark steigend | 📉 Stagnierend | Stabil |

**Empfehlung: uv**
- Folgt PEP 621 (`pyproject.toml`) — kein Vendor-Lock-in
- Extrem schnell (relevantier bei CI/CD mit vielen Dependencies)
- Drop-in Ersatz: `uv pip install`, `uv run`, `uv lock`
- Aktive Entwicklung (Astral, gleiche Firma wie `ruff`)

### pyproject.toml (Vollständig)

```toml
[project]
name = "docflow"
version = "0.1.0"
description = "Enterprise Document Text Extraction Pipeline"
readme = "README.md"
license = { text = "MIT" }
requires-python = ">=3.12"
authors = [{ name = "DocFlow Team" }]

dependencies = [
    "fastapi>=0.115,<1.0",
    "uvicorn[standard]>=0.32,<1.0",
    "pydantic>=2.10,<3.0",
    "pydantic-settings>=2.6,<3.0",
    "httpx>=0.27,<1.0",
    "structlog>=24.4,<26.0",
    "python-multipart>=0.0.18",
]

[project.optional-dependencies]
tika = ["httpx>=0.27,<1.0"]
pymupdf = ["PyMuPDF>=1.24,<2.0"]
office = [
    "python-docx>=1.1,<2.0",
    "openpyxl>=3.1,<4.0",
    "python-pptx>=1.0,<2.0",
]
textract = ["boto3>=1.35,<2.0"]
tesseract = [
    "pytesseract>=0.3.13,<1.0",
    "Pillow>=11.0,<12.0",
]
google-vision = ["google-cloud-vision>=3.8,<4.0"]
azure-ocr = ["azure-ai-vision-imageanalysis>=1.0,<2.0"]
openai = ["openai>=1.55,<2.0"]
anthropic = ["anthropic>=0.40,<1.0"]
database = [
    "sqlalchemy[asyncio]>=2.0,<3.0",
    "alembic>=1.14,<2.0",
    "asyncpg>=0.30,<1.0",
    "aiosqlite>=0.20,<1.0",
]
s3 = ["aiobotocore>=2.15,<3.0"]
all = ["docflow[tika,pymupdf,tesseract,database,s3]"]
dev = [
    "pytest>=8.3,<9.0",
    "pytest-asyncio>=0.24,<1.0",
    "pytest-cov>=6.0,<7.0",
    "mypy>=1.13,<2.0",
    "ruff>=0.8,<1.0",
    "pre-commit>=4.0,<5.0",
    "httpx>=0.27,<1.0",  # Für TestClient
]

[build-system]
requires = ["hatchling>=1.25"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/docflow"]

[tool.ruff]
target-version = "py312"
src = ["src", "tests"]
line-length = 99

[tool.ruff.lint]
select = [
    "E",    # pycodestyle errors
    "W",    # pycodestyle warnings
    "F",    # pyflakes
    "I",    # isort
    "B",    # flake8-bugbear
    "C4",   # flake8-comprehensions
    "UP",   # pyupgrade
    "SIM",  # flake8-simplify
    "TCH",  # flake8-type-checking
    "RUF",  # ruff-specific
    "ASYNC",# flake8-async
]
ignore = ["E501"]  # line length handled by formatter

[tool.ruff.lint.isort]
known-first-party = ["docflow"]

[tool.ruff.format]
quote-style = "double"

[tool.mypy]
python_version = "3.12"
strict = true
plugins = ["pydantic.mypy"]
warn_return_any = true
warn_unused_configs = true

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
markers = [
    "integration: marks tests requiring external services (Tika, Tesseract)",
    "slow: marks tests as slow (>5s)",
]

[tool.coverage.run]
source = ["src/docflow"]
omit = ["*/tests/*"]
```

### Fallstricke Packaging

| Problem | Lösung |
|---------|--------|
| `import docflow` funktioniert nicht im src-Layout | `uv pip install -e .` (editable install) oder `uv run pytest` |
| Optional Dependencies vergessen zu installieren | `uv pip install -e ".[tika,tesseract,database]"` für konkretes Deployment |
| `ruff` und `mypy` widersprechen sich | `ruff` für Formatting/Linting, `mypy` nur für Types. Kein Overlap. |
| CI/CD langsam durch pip | `uv` cacht Dependencies aggressiv → 10x schneller |

---

## 6. Gesamtübersicht: Empfohlener Tech Stack

### Phase 1 (MVP)

| Layer | Technologie | Begründung |
|-------|------------|------------|
| **Framework** | FastAPI + Uvicorn | Standard, hervorragend dokumentiert |
| **Validation** | Pydantic v2 | Zero Alternative |
| **Extraction** | Tika (HTTP) + PyMuPDF | Breite Abdeckung + schnelles PDF |
| **OCR** | Tesseract 5 | Kostenlos, Self-Hosted |
| **Post-Processing** | Regex-basiert (kein LLM) | Deterministisch, schnell |
| **Output** | Markdown Formatter | Kernformat |
| **Storage** | Local Filesystem | Einfach, für Dev/Staging |
| **Jobs** | asyncio (in-process) | Kein Redis nötig |
| **Database** | SQLite (async) | Für Metadata, kein Server nötig |
| **Packaging** | uv + ruff + mypy | Modern, schnell |
| **Container** | Docker + Compose | Tika + App |

### Phase 2 (Enterprise)

| Upgrade | Von → Nach |
|---------|-----------|
| Storage | Local → MinIO / S3 |
| Database | SQLite → PostgreSQL (asyncpg) |
| OCR | + Google Vision API Adapter |
| Extraction | + AWS Textract Adapter |
| Auth | API-Key → OAuth2/OIDC |

### Phase 3 (Intelligence)

| Upgrade | Von → Nach |
|---------|-----------|
| LLM | Kein LLM → OpenAI + Ollama Adapter |
| Processing | Regex → LLM-basierte Strukturierung |
| Delivery | Sync → + Webhooks |

### Phase 4 (Scale)

| Upgrade | Von → Nach |
|---------|-----------|
| Jobs | asyncio → ARQ + Redis |
| Deployment | docker-compose → Kubernetes |
| API | REST → + gRPC |

---

## Docker-Compose (Phase 1)

```yaml
services:
  docflow-api:
    build:
      context: .
      dockerfile: docker/Dockerfile
    ports:
      - "8000:8000"
    environment:
      - DOCFLOW_TIKA_URL=http://tika:9998
      - DOCFLOW_STORAGE_BACKEND=local
      - DOCFLOW_LOG_LEVEL=INFO
    volumes:
      - docflow-data:/data/documents
    depends_on:
      tika:
        condition: service_healthy

  tika:
    image: apache/tika:3.0.0
    ports:
      - "9998:9998"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9998/tika"]
      interval: 10s
      timeout: 5s
      retries: 3

volumes:
  docflow-data:
```

## Dockerfile (Multi-Stage)

```dockerfile
# === Build Stage ===
FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src/ src/
RUN uv sync --frozen --no-dev

# === Runtime Stage ===
FROM python:3.12-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-deu \
    tesseract-ocr-eng \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=builder /app/.venv .venv/
COPY --from=builder /app/src src/
COPY config/ config/

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

EXPOSE 8000
CMD ["uvicorn", "docflow.adapters.inbound.api.app:create_app", "--host", "0.0.0.0", "--port", "8000", "--factory"]
```

## Consequences

### Positive
- **Inkrementell erweiterbar** — Jede Phase baut auf der vorherigen auf, kein Rewrite
- **Adapter-austauschbar** — Jede Technologie-Entscheidung ist durch das Port-Interface revidierbar
- **Enterprise-ready** — Cloud-Adapter (Textract, Vision, OpenAI) als opt-in, nicht als Requirement
- **DSGVO-konform** — Self-Hosted-Defaults (Tika, Tesseract, Ollama), Cloud nur wenn konfiguriert
- **Developer-freundlich** — `uv run pytest` läuft ohne Docker, ohne externe Services

### Risiken
- **Tika-Server ist JVM-basiert** → Memory-Overhead (~512 MB), aber Container-isoliert
- **Tesseract-Qualität** reicht nicht für alle Scans → Cloud-OCR-Adapter für Phase 2 einplanen
- **asyncio-JobQueue (Phase 1)** geht bei Restart verloren → Phase 4 bringt persistente Queue
