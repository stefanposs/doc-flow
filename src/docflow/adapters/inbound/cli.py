"""CLI adapter — command-line interface for DocFlow."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path


def main() -> None:
    """DocFlow CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="docflow",
        description="DocFlow — Document Text Extraction Pipeline",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # ── extract command ──────────────────────────────────────
    extract_parser = subparsers.add_parser("extract", help="Extract text from a document")
    extract_parser.add_argument("file", type=Path, help="Path to the document file")
    extract_parser.add_argument("-o", "--output", type=Path, help="Output file (default: stdout)")
    extract_parser.add_argument(
        "-f", "--format", choices=["markdown", "json", "plaintext"], default="markdown", help="Output format"
    )
    extract_parser.add_argument("-l", "--language", default="deu", help="OCR language")

    # ── version command ──────────────────────────────────────
    subparsers.add_parser("version", help="Show version")

    # ── serve command ────────────────────────────────────────
    serve_parser = subparsers.add_parser("serve", help="Start the API server")
    serve_parser.add_argument("-p", "--port", type=int, default=8000, help="Port")
    serve_parser.add_argument("--host", default="0.0.0.0", help="Host")  # noqa: S104
    serve_parser.add_argument("--reload", action="store_true", help="Enable auto-reload")

    args = parser.parse_args()

    if args.command == "version":
        from docflow import __version__

        print(f"DocFlow {__version__}")  # noqa: T201

    elif args.command == "extract":
        asyncio.run(_extract(args))

    elif args.command == "serve":
        _serve(args)

    else:
        parser.print_help()
        sys.exit(1)


async def _extract(args: argparse.Namespace) -> None:
    """Run extraction from CLI."""
    from docflow.application.config import get_settings
    from docflow.domain.models import OutputFormat

    file_path = args.file
    if not file_path.exists():
        print(f"Error: File not found: {file_path}", file=sys.stderr)  # noqa: T201
        sys.exit(1)

    # Lazy import to avoid loading everything on --help
    from docflow.adapters.inbound.api.dependencies import (
        _build_extractors,
        _build_formatters,
        _build_ocr,
        _build_processors,
    )
    from docflow.application.pipeline import ExtractorRouter, ProcessingPipeline
    from docflow.application.service import DocumentService

    settings = get_settings()
    extractors = _build_extractors(settings)
    ocr = _build_ocr(settings)
    processors = _build_processors(settings)
    formatters = _build_formatters()

    pipeline = ProcessingPipeline(
        extractor_router=ExtractorRouter(extractors),
        ocr=ocr,
        post_processors=processors,
        formatters=formatters,
    )
    service = DocumentService(pipeline=pipeline, settings=settings)

    format_map = {"markdown": OutputFormat.MARKDOWN, "json": OutputFormat.JSON, "plaintext": OutputFormat.PLAINTEXT}
    output_format = format_map[args.format]

    file_content = file_path.read_bytes()
    document = await service.process_document(
        filename=file_path.name,
        file_content=file_content,
        output_format=output_format,
        language=args.language,
    )

    if document.processed_content:
        if args.output:
            args.output.write_text(document.processed_content, encoding="utf-8")
            print(f"Output written to {args.output}", file=sys.stderr)  # noqa: T201
        else:
            print(document.processed_content)  # noqa: T201
    else:
        print(f"Error: {document.error}", file=sys.stderr)  # noqa: T201
        sys.exit(1)


def _serve(args: argparse.Namespace) -> None:
    """Start the API server."""
    import uvicorn

    uvicorn.run(
        "docflow.adapters.inbound.api.app:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
