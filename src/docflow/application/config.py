"""Application configuration via pydantic-settings."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from docflow.domain.models import ExtractionEngine, OCREngine, OutputFormat


class Settings(BaseSettings):
    """DocFlow application settings.

    All settings can be overridden via environment variables prefixed with DOCFLOW_.
    """

    model_config = SettingsConfigDict(
        env_prefix="DOCFLOW_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ─── Application ─────────────────────────────────────────
    env: str = "development"
    log_level: str = "INFO"
    log_format: str = "text"  # text | json
    port: int = 8000
    workers: int = 4
    max_file_size_mb: int = 100

    # ─── Extraction ──────────────────────────────────────────
    default_extractor: ExtractionEngine = ExtractionEngine.AUTO
    tika_url: str = "http://localhost:9998"
    tika_timeout: int = 120

    # ─── OCR ─────────────────────────────────────────────────
    ocr_enabled: bool = True
    ocr_engine: OCREngine = OCREngine.TESSERACT
    ocr_language: str = "deu"
    ocr_dpi: int = 300

    # ─── Storage ─────────────────────────────────────────────
    storage_backend: str = "local"  # local | s3
    storage_path: str = "/data/documents"

    # S3 / MinIO
    s3_endpoint: str = ""
    s3_bucket: str = "docflow-documents"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_region: str = "eu-central-1"

    # ─── Processing ──────────────────────────────────────────
    default_output_format: OutputFormat = OutputFormat.MARKDOWN
    default_language: str = "deu"
    processors: list[str] = Field(default_factory=lambda: ["cleanup"])

    # ─── LLM (optional) ─────────────────────────────────────
    llm_enabled: bool = False
    llm_provider: str = "openai"  # openai | ollama
    llm_model: str = "gpt-4"

    # ─── Redis (optional) ────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"
    redis_enabled: bool = False

    # ─── Security ────────────────────────────────────────────
    api_key: str = ""
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])


def get_settings() -> Settings:
    """Create and return application settings (cached by FastAPI dependency)."""
    return Settings()
