# Configuration

DocFlow is configured entirely through **environment variables** prefixed with `DOCFLOW_`. Copy `.env.example` to `.env` and customise as needed.

---

## Application Settings

| Variable | Default | Description |
|---|---|---|
| `DOCFLOW_ENV` | `development` | Environment: `development`, `staging`, `production` |
| `DOCFLOW_LOG_LEVEL` | `INFO` | Log level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `DOCFLOW_LOG_FORMAT` | `text` | Log format: `text` (dev), `json` (prod) |
| `DOCFLOW_PORT` | `8000` | API server port |
| `DOCFLOW_WORKERS` | `4` | Uvicorn worker count |
| `DOCFLOW_MAX_FILE_SIZE_MB` | `100` | Maximum upload file size |

## Extraction Settings

| Variable | Default | Description |
|---|---|---|
| `DOCFLOW_DEFAULT_EXTRACTOR` | `auto` | Default extractor: `auto`, `tika`, `pymupdf` |
| `DOCFLOW_TIKA_URL` | `http://localhost:9998` | Tika server URL |
| `DOCFLOW_TIKA_TIMEOUT` | `120` | Tika request timeout (seconds) |

## OCR Settings

| Variable | Default | Description |
|---|---|---|
| `DOCFLOW_OCR_ENABLED` | `true` | Enable/disable OCR |
| `DOCFLOW_OCR_ENGINE` | `tesseract` | OCR engine: `tesseract`, `google_vision`, `none` |
| `DOCFLOW_OCR_LANGUAGE` | `deu` | OCR language code |
| `DOCFLOW_OCR_DPI` | `300` | OCR resolution |

## Storage Settings

| Variable | Default | Description |
|---|---|---|
| `DOCFLOW_STORAGE_BACKEND` | `local` | Storage backend: `local`, `s3` |
| `DOCFLOW_STORAGE_PATH` | `/data/documents` | Local storage path |
| `DOCFLOW_S3_ENDPOINT` | — | S3/MinIO endpoint URL |
| `DOCFLOW_S3_BUCKET` | `docflow-documents` | S3 bucket name |
| `DOCFLOW_S3_ACCESS_KEY` | — | S3 access key |
| `DOCFLOW_S3_SECRET_KEY` | — | S3 secret key |

## Processing Settings

| Variable | Default | Description |
|---|---|---|
| `DOCFLOW_DEFAULT_OUTPUT_FORMAT` | `markdown` | Output format: `markdown`, `json`, `plaintext` |
| `DOCFLOW_DEFAULT_LANGUAGE` | `deu` | Default document language |
| `DOCFLOW_PROCESSORS` | `cleanup` | Comma-separated processor list |

## LLM Settings (Optional)

| Variable | Default | Description |
|---|---|---|
| `DOCFLOW_LLM_ENABLED` | `false` | Enable LLM post-processing |
| `DOCFLOW_LLM_PROVIDER` | `openai` | LLM provider: `openai`, `ollama` |
| `DOCFLOW_LLM_MODEL` | `gpt-4` | LLM model name |

---

## Next Steps

- [Quick Start](quick-start.md) — first extraction
- [Architecture](../architecture/overview.md) — how it works
