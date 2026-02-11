# Processing Pipeline

The pipeline orchestrates the full document processing flow: **Extract → OCR → Process → Format**.

---

## Pipeline Flow

```mermaid
sequenceDiagram
    participant API as FastAPI
    participant SVC as DocumentService
    participant PIPE as ProcessingPipeline
    participant RT as ExtractorRouter
    participant EXT as Extractor
    participant OCR as OCR Engine
    participant PP as PostProcessor
    participant FMT as Formatter

    API->>SVC: process_document(file, options)
    SVC->>SVC: Detect MIME type
    SVC->>SVC: Create Document entity
    SVC->>PIPE: run(document, content, mime_type)

    PIPE->>RT: resolve(mime_type, preferred_engine)
    RT-->>PIPE: extractor

    PIPE->>EXT: extract(content, mime_type)
    EXT-->>PIPE: ExtractionResult

    alt Needs OCR (image or scanned PDF)
        PIPE->>OCR: recognize(content, language)
        OCR-->>PIPE: text
    end

    loop Each PostProcessor
        PIPE->>PP: process(text, context)
        PP-->>PIPE: processed_text
    end

    PIPE->>FMT: format(text, metadata)
    FMT-->>PIPE: ProcessingResult

    PIPE-->>SVC: Document (completed)
    SVC-->>API: DocumentResponse
```

---

## ExtractorRouter

The router selects the best extractor based on MIME type and user preference:

| MIME Type | Default Extractor | Reason |
|-----------|-------------------|--------|
| `application/pdf` | **PyMuPDF** | 10-50x faster, no network |
| `application/msword` | **Tika** | Office format support |
| `image/*` | **Tika** → OCR | Fallback to OCR |
| Everything else | **Tika** | Universal support |

Users can override with `extraction_engine=tika` or `extraction_engine=pymupdf`.

---

## OCR Decision Logic

```python
def _needs_ocr(mime_type, text, ocr_engine):
    if ocr_engine == "none":
        return False
    if mime_type in IMAGE_TYPES:
        return True
    if mime_type == "application/pdf" and len(text.strip()) < 50:
        return True  # Scanned PDF
    return False
```

---

## Error Handling

The pipeline catches all exceptions and marks the document as `failed`:

```python
try:
    # Extract → Process → Format
    document.mark_completed(content, elapsed_ms)
except Exception as exc:
    document.mark_failed(str(exc))
```

No unhandled exceptions propagate to the API layer.
