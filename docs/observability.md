# Observability

> The logging, metrics, and tracing plan for Firstline / Atlas — **honest about what is implemented
> vs planned.** Logging is implemented; metrics and tracing are scaffolded for the production edition.

## Table of contents

- [Status at a glance](#status-at-a-glance)
- [Logging (implemented)](#logging-implemented)
- [Request correlation (implemented)](#request-correlation-implemented)
- [Metrics (planned)](#metrics-planned)
- [Tracing (planned)](#tracing-planned)
- [The live edition](#the-live-edition)
- [What to instrument next](#what-to-instrument-next)

## Status at a glance

| Signal | Production edition | Live (Cloudflare) edition |
|---|---|---|
| Structured logs | ✅ implemented (JSON to stdout) | ✅ Workers observability enabled |
| Request correlation | ✅ `X-Request-ID` middleware | n/a (one Worker per request) |
| Metrics (Prometheus) | 📋 planned — chart scaffolding only, no `/metrics` in app code | — |
| Tracing (OpenTelemetry) | 📋 planned — env hook only, no instrumentation in code | — |
| Run-level telemetry | ✅ persisted to `run_steps` (tokens, latency_ms, payload) | partial (D1 `runs.tokens`) |

Legend: ✅ implemented · 📋 planned/scaffolded.

## Logging (implemented)

The API and worker emit **structured JSON logs to stdout**, the right shape for a container
platform to collect ([`logging.py`](../apps/api/src/atlas_api/logging.py)):

```json
{"level":"INFO","logger":"atlas_api…","msg":"…"}
```

`configure_logging()` installs a single stdout handler with a JSON formatter at `INFO` and is
called from the app factory ([`main.py`](../apps/api/src/atlas_api/main.py)). On EKS, pod stdout is
collected by the platform's log pipeline (e.g. Fluent Bit → CloudWatch); this chart does not bundle
a log shipper.

Errors are returned as RFC-9457-style problem responses **without stack-trace leakage**
([`errors.py`](../apps/api/src/atlas_api/errors.py)) — a security property as much as an
observability one.

## Request correlation (implemented)

[`middleware.py`](../apps/api/src/atlas_api/middleware.py) attaches a request id to every request:
it reads an inbound `X-Request-ID` or generates a UUID, stores it on `request.state.request_id`, and
echoes it back on the response header. This is the correlation key that ties together the log lines
for one request (and is the seam where per-request log enrichment / PII redaction would attach).

## Metrics (planned)

The Helm chart is **scaffolded** for Prometheus RED metrics but the application does **not yet
expose a `/metrics` endpoint**. In [`values.yaml`](../infra/k8s/atlas/values.yaml):

```yaml
metrics:
  enabled: true
  path: /metrics
  port: 8080
```

This drives annotation-based Prometheus scrape discovery, but until the FastAPI app actually serves
`/metrics` (e.g. via `prometheus-client` / an ASGI instrumentator), scraping returns nothing. The
API CPU HPA relies on **metrics-server** (a cluster prerequisite), which is independent of
Prometheus. Worker autoscaling is driven by KEDA reading **Redis queue depth**, not app metrics.

Useful run-level telemetry **is** already captured in the database: `run_steps` rows record per-step
`agent`, `phase`, `status`, `tokens`, `latency_ms`, and a `payload`
([`db/models.py`](../apps/api/src/atlas_api/db/models.py)) — a foundation a `/metrics` exporter or a
dashboard could aggregate.

## Tracing (planned)

Distributed tracing with **OpenTelemetry** is planned for the production edition. The only wiring
present today is a commented env hook in the chart:

```yaml
# app.extraEnv:
#   OTEL_EXPORTER_OTLP_ENDPOINT: http://adot-collector.observability:4317
```

No OTel SDK or instrumentation is in the application code yet. When added, agent/LLM spans should
follow the [OpenTelemetry GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
(model, token counts, tool calls, latency per node) so the plan → search → verify → write graph is
observable end to end, exported to an OTLP collector (e.g. AWS Distro for OpenTelemetry).

## The live edition

The Cloudflare Worker enables platform observability in
[`wrangler.jsonc`](../apps/cloudflare/wrangler.jsonc):

```jsonc
"observability": { "enabled": true }
```

This surfaces Worker logs/metrics in the Cloudflare dashboard (`wrangler tail` for live logs). The
Worker also persists each run (and its source count / model) to D1, which is the durable record of
live-edition activity.

## What to instrument next

In rough priority order (all 📋 planned):

1. Expose `/metrics` (RED metrics: request rate, errors, duration) so the chart's Prometheus
   scrape becomes live.
2. Per-provider **cost/token meters** with alerting — directly relevant to the denial-of-wallet
   risk (see [threat model](threat-model.md#2-denial-of-wallet--unbounded-consumption-owasp-llm10)
   and [cost notes](cost-notes.md)).
3. OpenTelemetry tracing across the API → worker → graph path using the GenAI semconv.
4. **PII redaction** in logs/traces for questions, `run_steps.payload`, and fetched content before
   any of the above ships (see [security](security.md) / threat model A08/A09).
5. Security **alerting** on auth-failure spikes, budget breach, and egress NetworkPolicy denials.
</content>
