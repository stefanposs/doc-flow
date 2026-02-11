# Testing

## Test Structure

```
tests/
├── conftest.py              # Shared fixtures + Fakes
├── unit/                    # No external deps
│   ├── test_models.py       # Domain models
│   ├── test_pipeline.py     # Pipeline orchestration
│   ├── test_processors.py   # Post-processors
│   ├── test_formatters.py   # Output formatters
│   ├── test_storage.py      # Storage fake
│   └── test_api.py          # FastAPI endpoints
└── integration/             # Requires Docker services
```

---

## Running Tests

```bash
just test                    # All tests
just test-unit               # Unit tests with coverage
just test-integration        # Integration tests
```

---

## Test Philosophy

### Fakes over Mocks

We use **in-memory implementations** of ports (Fakes) instead of `unittest.mock`:

```python
class FakeExtractor(ExtractorPort):
    async def extract(self, file_content, mime_type):
        return ExtractionResult(text="Fake text", engine_used="fake")
```

Benefits:

- Fakes implement the real interface — they break when the port changes
- No brittle mock assertions
- Reusable across tests

### Test Pyramid

| Layer | Proportion | What | How |
|-------|------------|------|-----|
| Unit | ~70% | Domain + Application | Fakes |
| Integration | ~25% | Adapters + API | Tika container |
| E2E | ~5% | Full pipeline | Docker Compose |

---

## Test Markers

```python
@pytest.mark.unit           # Fast, no external deps
@pytest.mark.integration    # Needs Docker services
@pytest.mark.e2e            # Full stack
```

Run specific markers:

```bash
uv run pytest -m unit
uv run pytest -m integration
```

---

## Coverage

Target: **80%** overall, **90%** for domain layer.

```bash
just test-unit   # Includes --cov report
```
