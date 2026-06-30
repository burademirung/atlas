"""Prometheus metrics: HTTP RED signals, run lifecycle counters, token cost.

Exposes a ``/metrics`` ASGI app (``prometheus_client.make_asgi_app``) and small
recorders the API/worker call. RED = Rate, Errors, Duration. The token counter
is the denial-of-wallet spend signal (OWASP LLM10) so cost can be alerted on.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.requests import Request
from starlette.responses import Response

_REQUESTS = Counter(
    "atlas_http_requests_total",
    "Total HTTP requests (RED: rate + errors).",
    ["method", "path", "status"],
)
_LATENCY = Histogram(
    "atlas_http_request_duration_seconds",
    "HTTP request latency in seconds (RED: duration).",
    ["method", "path"],
)
_RUNS = Counter(
    "atlas_runs_total",
    "Research runs by terminal outcome.",
    ["outcome"],
)
_TOKENS = Counter(
    "atlas_run_tokens_total",
    "LLM tokens consumed by research runs (denial-of-wallet spend signal).",
    ["kind"],
)


def record_run(outcome: str) -> None:
    """Increment the run counter for a terminal outcome (done/cancelled/...)."""
    _RUNS.labels(outcome=outcome).inc()


def record_tokens(input_tokens: int = 0, output_tokens: int = 0) -> None:
    """Add to the token-cost counters (split input/output per GenAI semconv)."""
    if input_tokens:
        _TOKENS.labels(kind="input").inc(input_tokens)
    if output_tokens:
        _TOKENS.labels(kind="output").inc(output_tokens)


def _route_template(request: Request) -> str:
    """Use the matched route template (low cardinality) not the raw path."""
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    if isinstance(path, str):
        return path
    return request.url.path


async def observe_request(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Middleware recording RED metrics for every request."""
    start = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        path = _route_template(request)
        _LATENCY.labels(method=request.method, path=path).observe(time.perf_counter() - start)
        _REQUESTS.labels(method=request.method, path=path, status=str(status)).inc()


async def metrics_endpoint(_request: Request) -> Response:
    """Serve the Prometheus exposition format at /metrics (no trailing-slash redirect)."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
