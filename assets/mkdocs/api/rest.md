# REST API Reference

Base URL: `http://localhost:8000/api/v1`

Interactive docs: [http://localhost:8000/api/docs](http://localhost:8000/api/docs)

---

## Endpoints

### Health Check

```http
GET /api/v1/health
```

**Response:**

```json
{
  "status": "healthy",
  "version": "0.1.0",
  "env": "development",
  "extractors": ["tika", "pymupdf"],
  "ocr_available": true
}
```

---

### Extract Text

```http
POST /api/v1/extract
Content-Type: multipart/form-data
```

**Parameters:**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `file` | File | *required* | Document to extract |
| `output_format` | string | `markdown` | `markdown`, `json`, `plaintext` |
| `extraction_engine` | string | `auto` | `auto`, `tika`, `pymupdf` |
| `ocr_engine` | string | `tesseract` | `tesseract`, `none` |
| `language` | string | — | OCR language hint |

**Response:**

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "filename": "document.pdf",
  "mime_type": "application/pdf",
  "size_bytes": 102400,
  "output_format": "markdown",
  "content": "# Document Title\n\nExtracted text...",
  "processing_time_ms": 1234,
  "created_at": "2026-02-11T10:00:00Z",
  "extraction_engine": "pymupdf"
}
```

---

### Extract Raw

```http
POST /api/v1/extract/raw
Content-Type: multipart/form-data
```

Same parameters as `/extract`, but returns raw text without JSON wrapper.

**Response:** `text/markdown` or `text/plain` body.

---

### Get Formats

```http
GET /api/v1/formats
```

**Response:**

```json
{
  "extraction_engines": ["tika", "pymupdf", "auto"],
  "ocr_engines": ["tesseract", "google_vision", "none"],
  "output_formats": ["markdown", "json", "plaintext"],
  "max_file_size_mb": 100
}
```

---

## Error Responses

All errors follow this format:

```json
{
  "detail": "File exceeds maximum size of 100MB"
}
```

| Status | Meaning |
|--------|---------|
| `400` | Bad request (missing file, empty file) |
| `413` | File too large |
| `422` | Processing failed |
| `500` | Internal server error |
