"""No-op metrics adapter — does nothing, zero overhead."""

from __future__ import annotations

from docflow.domain.ports import MetricsPort


class NoOpMetrics(MetricsPort):
    """Metrics adapter that silently discards all metrics.

    Use for local development or when no metrics backend is configured.
    For production, use PrometheusMetrics.
    """

    def counter(self, name: str, value: float = 1, tags: dict[str, str] | None = None) -> None:
        pass

    def histogram(self, name: str, value: float, tags: dict[str, str] | None = None) -> None:
        pass

    def gauge(self, name: str, value: float, tags: dict[str, str] | None = None) -> None:
        pass
