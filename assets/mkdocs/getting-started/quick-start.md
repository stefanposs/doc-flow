# Quick Start

Extract text from your first document in under 5 minutes.

---

## 1. Start the Stack

```bash
just dev
# Or: docker compose -f docker/docker-compose.yml up -d
```

Wait for all services to be healthy:

```bash
just status
```

## 2. Open the API Docs

Visit [http://localhost:8000/api/docs](http://localhost:8000/api/docs) for the interactive Swagger UI.

## 3. Extract Text from a PDF

=== "curl"

    ```bash
    curl -X POST http://localhost:8000/api/v1/extract \
      -F "file=@my-document.pdf" \
      -F "output_format=markdown"
    ```

=== "Python"

    ```python
    import httpx

    with open("my-document.pdf", "rb") as f:
        response = httpx.post(
            "http://localhost:8000/api/v1/extract",
            files={"file": ("document.pdf", f, "application/pdf")},
            params={"output_format": "markdown"},
        )

    result = response.json()
    print(result["content"])
    ```

=== "CLI"

    ```bash
    # Direct CLI usage (requires local install)
    docflow extract my-document.pdf -f markdown -o output.md
    ```

## 4. Get Raw Text (No JSON Wrapper)

```bash
curl -X POST http://localhost:8000/api/v1/extract/raw \
  -F "file=@my-document.pdf" > extracted.md
```

## 5. Explore Available Formats

```bash
curl http://localhost:8000/api/v1/formats | jq
```

Response:

```json
{
  "extraction_engines": ["tika", "pymupdf", "auto"],
  "ocr_engines": ["tesseract", "google_vision", "none"],
  "output_formats": ["markdown", "json", "plaintext"],
  "max_file_size_mb": 100
}
```

---

## Next Steps

- [Configuration](configuration.md) — customize extraction behavior
- [Architecture](../architecture/overview.md) — understand the pipeline
- [API Reference](../api/rest.md) — full endpoint documentation
