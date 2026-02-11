# DocFlow — Development Commands
# Install just: https://github.com/casey/just

# Default recipe — show available commands
default:
    @just --list

# ============================================================================
# Setup & Installation
# ============================================================================

# Install all dependencies
setup:
    uv sync --all-extras
    @echo "✅ All dependencies installed!"

# Install production dependencies only
setup-prod:
    uv sync --no-dev --frozen
    @echo "✅ Production dependencies installed!"

# ============================================================================
# Testing
# ============================================================================

# Run all tests
test: test-unit test-e2e
    @echo "✅ All tests passed!"

# Run unit tests with coverage
test-unit:
    uv run pytest tests/unit/ -v --cov=src/docflow --cov-report=term-missing

# Run integration tests (requires Docker services)
test-integration:
    uv run pytest tests/integration/ -v

# Run E2E tests (in-memory adapters, no external services)
test-e2e:
    uv run pytest tests/e2e/ -v -m e2e

# Run tests like CI does
test-ci:
    uv run pytest tests/unit/ tests/e2e/ -v --cov=src/docflow --cov-report=xml --junitxml=junit.xml

# ============================================================================
# Code Quality
# ============================================================================

# Run linter
lint:
    uv run ruff check src/ tests/

# Format code
format:
    uv run ruff format src/ tests/

# Auto-fix lint issues
lint-fix:
    uv run ruff check --fix src/ tests/

# Format + lint-fix
fix: format lint-fix
    @echo "✅ Code formatted and linted!"

# Type check
typecheck:
    uv run mypy src/

# Full QA pipeline (lint + typecheck + test)
qa: lint typecheck test
    @echo "✅ All QA checks passed!"

# Quick check before commit
check: lint typecheck
    @echo "✅ Ready to commit!"

# ============================================================================
# Docker
# ============================================================================

compose := "docker compose -f docker/docker-compose.yml"
compose_dev := compose + " -f docker/docker-compose.dev.yml"
compose_prod := compose + " -f docker/docker-compose.prod.yml"

# Start development stack (hot-reload)
dev:
    {{ compose_dev }} up -d
    @echo "✅ Dev stack running — http://localhost:8000/api/docs"

# Start full stack
up:
    {{ compose }} up -d
    @echo "✅ Stack running — http://localhost:8000/api/docs"

# Stop all containers
down:
    {{ compose }} down

# Stop and remove data
down-clean:
    {{ compose }} down -v
    @echo "⚠️  Volumes removed"

# Build Docker image
build:
    {{ compose }} build docflow-api

# Force rebuild (no cache)
rebuild:
    {{ compose }} build --no-cache docflow-api

# View logs (follow)
logs service="docflow-api":
    {{ compose }} logs -f {{ service }}

# Check service health
status:
    {{ compose }} ps

# Start with MinIO (S3 storage)
with-minio:
    {{ compose }} --profile storage up -d

# ============================================================================
# Production
# ============================================================================

# Start production stack
prod:
    {{ compose_prod }} up -d

# Start production with 3 API replicas
prod-scale:
    {{ compose_prod }} up -d --scale docflow-api=3

# ============================================================================
# Documentation
# ============================================================================

# Serve docs locally (http://localhost:8001)
docs:
    uv run mkdocs serve -a localhost:8001

# Build documentation
docs-build:
    uv run mkdocs build

# ============================================================================
# Utility
# ============================================================================

# Clean build artifacts
clean:
    rm -rf dist/ build/ .pytest_cache .ruff_cache htmlcov .mypy_cache
    find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
    @echo "✅ Cleaned build artifacts"

# Show project info
info:
    @echo "Project: DocFlow"
    @echo "Version: 0.1.0"
    @echo "Source:  src/docflow/"
    @echo "Tests:   tests/"
    @echo ""
    @docker compose -f docker/docker-compose.yml ps 2>/dev/null || echo "(Docker not running)"

# Count lines of code
loc:
    @echo "Python (source):"
    @find src -name '*.py' | xargs wc -l 2>/dev/null | tail -1
    @echo "Python (tests):"
    @find tests -name '*.py' | xargs wc -l 2>/dev/null | tail -1
    @echo "Documentation:"
    @find assets -name '*.md' | xargs wc -l 2>/dev/null | tail -1

# ============================================================================
# CI Simulation
# ============================================================================

# Simulate full CI pipeline locally
ci: clean lint typecheck test
    @echo "✅ CI simulation complete!"

# Quick CI (lint + test, skip typecheck)
ci-quick: lint test
    @echo "✅ Quick CI done!"

# ============================================================================
# Release
# ============================================================================

# Create a patch release
release-patch:
    ./scripts/release.sh patch

# Create a minor release
release-minor:
    ./scripts/release.sh minor

# Create a major release
release-major:
    ./scripts/release.sh major
