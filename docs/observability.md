# Observability

> The logging, metrics, and tracing setup for Firstline / Atlas — **honest about what is implemented
> vs planned.** Logging, request correlation, **Prometheus metrics**, and **OpenTelemetry tracing
> (GenAI semconv)** are now implemented in the production edition; dashboards, SLOs, and alerting are
> the remaining work.

## Table of contents

- [Status at a glance](#status-at-a-glance)
- [Logging (implemented)](#logging-implemented)
- [Request correlation (implemented)](#request-correlation-implemented)
- [Metrics (implemented)](#metrics-implemented)
- [Tracing (implemented)](#tracing-implemented)
- [The live edition](#the-live-edition)
- [What to instrument next](#what-to-instrument-next)

## Status at a glance

| Signal | Production edition | Live (Cloudflare) edition |
|---|---|---|
| Structured logs | ✅ implemented (JSON to stdout, **PII-redacted**) | ✅ Workers observability enabled |
| Request correlation | ✅ `X-Request-ID` middleware | n/a (one Worker per request) |
| Metrics (Prometheus) | ✅ implemented — `/metrics` endpoint + RED + run/token counters | — |
| Tracing (OpenTelemetry) | ✅ implemented — GenAI semconv spans, **no-op without an OTLP collector** | — |
| Run-level telemetry | ✅ persisted to `run_steps` (tokens, latency_ms, payload) | partial (D1 `runs.tokens`) |

Legend: ✅ implemented · 📋 planned/scaffolded.

## Logging (implemented)

The API and worker emit **structured JSON logs to stdout**, the right shape for a container
platform to collect ([`logging.py`](../apps/api/src/atlas_api/logging.py)):

```json
{"level":"INFO","logger":"atlas_api…","msg":"…"}
```

`configure_logging()` installs a single stdout handler with a JSON formatter at `INFO` and is
called from the app factory ([`main.py`](../apps/api/src/atlas_api/main.py)). It also attaches a
**`RedactionFilter`** ([`security/redaction.py`](../apps/api/src/atlas_api/security/redaction.py)) to
the handler, so every log record is scrubbed of PII (SSNs, cards, emails, phones) before it is
emitted — a breach description in a message or stack trace never reaches a log sink (OWASP LLM02). On
EKS, pod stdout is collected by the platform's log pipeline (e.g. Fluent Bit → CloudWatch); this
chart does not bundle a log shipper.

Errors are returned as RFC-9457-style problem responses **without stack-trace leakage**
([`errors.py`](../apps/api/src/atlas_api/errors.py)) — a security property as much as an
observability one.

## Request correlation (implemented)

[`middleware.py`](../apps/api/src/atlas_api/middleware.py) attaches a request id to every request:
it reads an inbound `X-Request-ID` or generates a UUID, stores it on `request.state.request_id`, and
echoes it back on the response header. This is the correlation key that ties together the log lines
for one request.

## Metrics (implemented)

The FastAPI app **serves Prometheus metrics at `/metrics`**
([`observability/metrics.py`](../apps/api/src/atlas_api/observability/metrics.py), wired in
[`main.py`](../apps/api/src/atlas_api/main.py) via `app.add_route("/metrics", …)`). The endpoint
returns the Prometheus exposition format from `prometheus_client.generate_latest()` and is
unauthenticated (intended for in-cluster scraping; keep it off the public ingress). The chart's
scrape annotations in [`values.yaml`](../infra/k8s/atlas/values.yaml) (`metrics.enabled`,
`metrics.path: /metrics`, `metrics.port`) now point at a live endpoint.

Exposed series:

| Metric | Type | Labels | Signal |
|---|---|---|---|
| `atlas_http_requests_total` | counter | `method`, `path`, `status` | RED — rate + errors |
| `atlas_http_request_duration_seconds` | histogram | `method`, `path` | RED — duration |
| `atlas_runs_total` | counter | `outcome` (`done`/`cancelled`/`truncated`/…) | run lifecycle |
| `atlas_run_tokens_total` | counter | `kind` (`input`/`output`) | **denial-of-wallet spend signal** |

The `observe_request` middleware records request rate/errors/latency for every request, keyed on the
**matched route template** (low cardinality, not the raw path). `record_run()` is incremented by the
worker at each terminal outcome ([`worker.py`](../apps/api/src/atlas_api/worker.py)); the token
counter is the cost signal that the denial-of-wallet guardrails (see
[security](security.md#denial-of-wallet-guardrails)) can be alerted on. The API CPU HPA still relies
on **metrics-server**, and worker autoscaling on **KEDA / Redis queue depth** — both independent of
Prometheus. Per-step telemetry also persists to `run_steps` (tokens, latency_ms, payload).

## Tracing (implemented)

Distributed tracing uses **OpenTelemetry** with the
[GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
([`observability/telemetry.py`](../apps/api/src/atlas_api/observability/telemetry.py)).
`setup_telemetry()` is called from the app lifespan
([`main.py`](../apps/api/src/atlas_api/main.py)); `span_for_node()` opens a span per agent-graph node
(`agent.<node>`) carrying `gen_ai.system`, `gen_ai.operation.name`, `gen_ai.request.model`, and the
`gen_ai.usage.{input,output}_tokens` counters.

**Important — no-op without a collector.** Real exporting activates **only when
`OTEL_EXPORTER_OTLP_ENDPOINT` is configured** (and the OTel SDK is installed). With no endpoint, the
OpenTelemetry API falls back to a **no-op tracer**: spans are created but not recorded or exported,
so instrumented paths are zero-overhead and never break offline or in tests. To turn it on, point the
endpoint at a collector (e.g. AWS Distro for OpenTelemetry):

```yaml
# app.extraEnv:
#   OTEL_EXPORTER_OTLP_ENDPOINT: http://adot-collector.observability:4317
#   OTEL_SERVICE_NAME: atlas-api
```

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

The signal plumbing (logs, RED metrics, GenAI traces, PII redaction) is in place; the remaining work
is turning signals into operations (all 📋 planned):

1. **Deploy a collector + dashboards.** Stand up an OTLP collector (ADOT) and a Prometheus/Grafana
   (or CloudWatch) stack, then build dashboards for the RED signals and the
   `atlas_run_tokens_total` spend curve. OTel export is a no-op until the collector exists.
2. **SLOs + alerting.** Define latency/error SLOs on the RED metrics and **cost alerting** on the
   token counter — directly relevant to the denial-of-wallet risk (see
   [threat model](threat-model.md#2-denial-of-wallet--unbounded-consumption-owasp-llm10) and
   [cost notes](cost-notes.md)). Add security alerting on auth-failure spikes, kill-switch
   activation / quota breaches, and egress NetworkPolicy denials.
3. **Extend tracing coverage** beyond the per-node spans to the full API → worker → graph path
   (context propagation across the arq boundary) and attach `run_steps.payload` selectively.
4. **Live-edition metrics.** Surface Worker request/error/cost counters (Workers Analytics Engine)
   to match the production RED signals.
