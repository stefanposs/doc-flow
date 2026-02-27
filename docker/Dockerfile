# ============================================================
# DocFlow – Multi-Stage Dockerfile
# ============================================================
# Stage 1: Builder – install dependencies
# Stage 2: Runtime – minimal production image
# ============================================================

# --------------- Stage 1: Builder ---------------
FROM python:3.14-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency resolution
RUN pip install --no-cache-dir uv

# Copy dependency manifests first (cache-friendly layer ordering)
COPY pyproject.toml uv.lock ./

# Install production dependencies only
RUN uv sync --no-dev --frozen

# --------------- Stage 2: Runtime ---------------
FROM python:3.14-slim AS runtime

LABEL maintainer="DocFlow Team"
LABEL org.opencontainers.image.source="https://github.com/stefanposs/doc-flow"
LABEL org.opencontainers.image.description="DocFlow – Document Text Extraction Pipeline"

WORKDIR /app

# Install runtime system dependencies (Tesseract for OCR)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-deu \
        tesseract-ocr-eng \
        libmagic1 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Security: non-root user
RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid appuser --create-home appuser

# Create data directories
RUN mkdir -p /data/documents /data/tmp && \
    chown -R appuser:appuser /data

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy application source
COPY src/ ./src/
COPY config/ ./config/

# Set ownership
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Environment
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DOCFLOW_ENV="production" \
    DOCFLOW_LOG_LEVEL="INFO" \
    DOCFLOW_LOG_FORMAT="json"

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

EXPOSE 8000

# Run with uvicorn – production settings
CMD ["uvicorn", "docflow.adapters.inbound.api.app:create_app", \
     "--factory", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "4", \
     "--access-log", \
     "--proxy-headers", \
     "--forwarded-allow-ips", "*"]
