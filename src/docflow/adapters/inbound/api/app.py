"""FastAPI application factory.

Creates the app with all routes, middleware, and dependency injection.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from docflow import __version__
from docflow.adapters.inbound.api.dependencies import setup_dependencies
from docflow.adapters.inbound.api.routes import router
from docflow.application.config import Settings, get_settings

logger = structlog.get_logger()


def configure_logging(settings: Settings) -> None:
    """Configure structlog based on settings."""
    processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if settings.log_format == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            structlog.stdlib._NAME_TO_LEVEL.get(settings.log_level.lower(), 20),  # noqa: SLF001
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan — startup & shutdown."""
    settings = get_settings()
    configure_logging(settings)

    logger.info(
        "docflow.startup",
        version=__version__,
        env=settings.env,
        log_level=settings.log_level,
    )

    # Wire up dependency injection
    setup_dependencies(app, settings)

    yield

    logger.info("docflow.shutdown")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="DocFlow",
        description="End-to-End Document Text Extraction Pipeline",
        version=__version__,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routes
    app.include_router(router, prefix="/api/v1")

    return app
