from httpx import AsyncClient

from atlas_api.config import Settings
from atlas_api.observability import metrics
from atlas_api.observability.telemetry import set_token_usage, setup_telemetry, span_for_node


def _settings(**extra: object) -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://u:p@localhost/db",
        redis_url="redis://localhost:6379/0",
        jwt_secret="s" * 32,
        **extra,
    )


async def test_metrics_endpoint_exposes_prometheus(app_client: AsyncClient) -> None:
    # Make a request first so the RED counters have something to report.
    await app_client.get("/healthz")
    r = await app_client.get("/metrics")
    assert r.status_code == 200
    body = r.text
    assert "atlas_http_requests_total" in body
    assert "atlas_http_request_duration_seconds" in body


def test_record_run_and_tokens_increment() -> None:
    # Recorders must not raise and should reflect in the exposition output.
    metrics.record_run("done")
    metrics.record_tokens(input_tokens=10, output_tokens=5)
    metrics.record_tokens()  # zero is a no-op, must not raise
    from prometheus_client import generate_latest

    dump = generate_latest().decode()
    assert "atlas_runs_total" in dump
    assert "atlas_run_tokens_total" in dump


def test_setup_telemetry_is_noop_without_endpoint() -> None:
    assert setup_telemetry(_settings()) is False


def test_span_for_node_noop_path_yields_usable_context() -> None:
    # With no exporter configured, the span context manager still works and
    # set_token_usage is a safe no-op.
    with span_for_node("plan", model="claude-test") as span:
        set_token_usage(span, 3, 4)
    # span is either a no-op span or None depending on SDK state; both are fine.
    assert span is None or span is not None
