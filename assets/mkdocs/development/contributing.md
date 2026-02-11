# Contributing

## Development Workflow

### Prerequisites

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) — fast Python package manager
- [just](https://github.com/casey/just) — task runner
- Docker & Docker Compose

### Setup

```bash
git clone https://github.com/stefanposs/doc-flow.git
cd doc-flow
just setup
```

### Available Commands

```bash
# Setup
just setup              # Install all dependencies

# Code quality
just lint               # Run ruff linter
just format             # Auto-format code
just fix                # Format + lint-fix
just typecheck          # Run mypy

# Testing
just test               # Run all tests
just test-unit          # Unit tests with coverage
just test-integration   # Integration tests (needs Docker)

# Docker
just dev                # Start dev stack (hot-reload)
just down               # Stop all containers
just rebuild            # Rebuild and restart

# Documentation
just docs               # Serve docs locally (http://localhost:8001)
just docs-build         # Build static docs

# Quality
just qa                 # Full QA: lint + typecheck + test
just check              # Quick check before commit
```

---

## Pull Request Process

### 1. Create feature branch

```bash
git checkout -b feature/my-awesome-feature
```

### 2. Make changes

- Write tests for new functionality
- Ensure `just qa` passes
- Update documentation if needed

### 3. Push and open PR

```bash
git push origin feature/my-awesome-feature
```

### 4. Code review

- At least one approval required
- CI must pass
- No merge conflicts

---

## Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat(extraction): add PyMuPDF extractor for PDFs
fix(ocr): handle empty image bytes gracefully
docs(api): update extraction endpoint documentation
test(pipeline): add tests for OCR fallback logic
chore(deps): update FastAPI to 0.115
```

---

## Adding a New Adapter

1. Create the adapter in `src/docflow/adapters/outbound/<category>/`
2. Implement the corresponding port interface (ABC)
3. Register in `src/docflow/adapters/inbound/api/dependencies.py`
4. Add optional dependency to `pyproject.toml`
5. Write tests in `tests/unit/` and `tests/integration/`
6. Document in `assets/mkdocs/architecture/ports-and-adapters.md`
