"""Observability: Prometheus RED metrics + optional OpenTelemetry tracing.

Metrics follow Prometheus conventions; spans follow the OpenTelemetry GenAI
semantic conventions (``gen_ai.*``). OTel exporting is opt-in via
``OTEL_EXPORTER_OTLP_ENDPOINT`` and otherwise a no-op.
"""

from atlas_api.observability.metrics import (
    metrics_endpoint,
    observe_request,
    record_run,
    record_tokens,
)
from atlas_api.observability.telemetry import setup_telemetry, span_for_node

__all__ = [
    "metrics_endpoint",
    "observe_request",
    "record_run",
    "record_tokens",
    "setup_telemetry",
    "span_for_node",
]
