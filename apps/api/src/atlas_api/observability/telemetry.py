"""Optional OpenTelemetry wiring + GenAI-semconv spans for the agent graph.

Tracing is enabled only when ``OTEL_EXPORTER_OTLP_ENDPOINT`` is configured; with
no endpoint the OpenTelemetry API falls back to a no-op tracer, so instrumented
code paths are zero-overhead and never break offline or in tests.

Span attributes follow the OpenTelemetry GenAI semantic conventions
(https://opentelemetry.io/docs/specs/semconv/gen-ai/): ``gen_ai.system``,
``gen_ai.operation.name``, ``gen_ai.request.model`` and the
``gen_ai.usage.{input,output}_tokens`` counters.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from atlas_api.config import Settings

try:  # pragma: no cover - exercised indirectly; guards a missing optional dep
    from opentelemetry import trace
    from opentelemetry.trace import Tracer

    _OTEL_AVAILABLE = True
except ImportError:  # pragma: no cover
    _OTEL_AVAILABLE = False

_configured = False


def setup_telemetry(settings: Settings) -> bool:
    """Configure the global tracer provider + OTLP exporter once.

    Returns ``True`` if real exporting was activated, ``False`` for the no-op
    path (no endpoint configured or the SDK unavailable). Safe to call repeatedly.
    """
    global _configured
    if _configured or not _OTEL_AVAILABLE:
        return False
    if not settings.otel_exporter_otlp_endpoint:
        return False
    try:  # pragma: no cover - requires a running collector to fully exercise
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource.create({"service.name": settings.otel_service_name})
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint))
        )
        trace.set_tracer_provider(provider)
        _configured = True
        return True
    except Exception:  # pragma: no cover - never let telemetry break startup
        return False


def _tracer() -> Tracer | None:
    if not _OTEL_AVAILABLE:
        return None
    return trace.get_tracer("atlas_api.agents")


def set_token_usage(span: Any, input_tokens: int, output_tokens: int) -> None:
    """Attach GenAI usage counters to a span (no-op for a non-recording span)."""
    if span is None or not _OTEL_AVAILABLE:
        return
    if input_tokens:
        span.set_attribute("gen_ai.usage.input_tokens", input_tokens)
    if output_tokens:
        span.set_attribute("gen_ai.usage.output_tokens", output_tokens)


@contextmanager
def span_for_node(node: str, *, model: str | None = None) -> Iterator[Any]:
    """Open a GenAI span for an agent-graph node.

    Yields the active span (or ``None`` when OTel is unavailable) so the caller
    can attach token usage once the model call returns.
    """
    tracer = _tracer()
    if tracer is None:
        yield None
        return
    with tracer.start_as_current_span(f"agent.{node}") as span:
        span.set_attribute("gen_ai.operation.name", node)
        span.set_attribute("gen_ai.system", "anthropic")
        if model:
            span.set_attribute("gen_ai.request.model", model)
        yield span
