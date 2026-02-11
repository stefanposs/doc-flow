# Installation

## Prerequisites

- **Python 3.12+**
- **Docker & Docker Compose** (for Tika and full stack)
- **just** (task runner) — optional but recommended
- **uv** (fast Python package manager)

---

## Quick Install (Docker)

The fastest way to get started:

```bash
git clone https://github.com/stefanposs/doc-flow.git
cd doc-flow
docker compose -f docker/docker-compose.yml up -d
```

This starts:

- **DocFlow API** on `http://localhost:8000`
- **Apache Tika** on `http://localhost:9998`
- **Redis** on `http://localhost:6379`

---

## Development Setup

### 1. Install `uv`

```bash
# macOS
brew install uv

# Linux / WSL
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. Install `just`

```bash
# macOS
brew install just

# Linux
curl --proto '=https' --tlsv1.2 -sSf https://just.systems/install.sh | bash -s -- --to /usr/local/bin
```

### 3. Clone & Install

```bash
git clone https://github.com/stefanposs/doc-flow.git
cd doc-flow

# Install all dependencies (including dev + optional extras)
just setup

# Or manually:
uv sync --all-extras
```

### 4. Start Tika (required for extraction)

```bash
docker run -d --name tika -p 9998:9998 apache/tika:2.9.2.1
```

### 5. Run Tests

```bash
just test
```

### 6. Start Development Server

```bash
# With Docker (recommended)
just dev

# Or locally
uv run uvicorn docflow.adapters.inbound.api.app:create_app --factory --reload
```

---

## Available Commands

```bash
just               # lists all recipes
just setup         # install all dependencies
just dev           # start Docker dev stack
just test          # run all tests
just lint          # run ruff linter
just format        # auto-format code
just qa            # full QA: lint + typecheck + test
just docs          # serve docs locally (http://localhost:8001)
```

---

## Next Steps

- [Quick Start](quick-start.md) — first extraction
- [Configuration](configuration.md) — environment variables reference
