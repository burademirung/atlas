# ADR 0004 — KEDA for worker queue-depth autoscaling

**Status:** Accepted · 2026-06-29

## Context

Atlas has two workloads with very different scaling signals:

- The **API** is a stateless HTTP/SSE tier — scales well on **CPU** (standard HPA).
- The **agent workers** are queue consumers: each `POST /runs` enqueues an arq job, and runs take
  minutes and fan out. The right scaling signal is **Redis queue depth**, and when the queue is
  empty the worker tier should scale to **zero** to avoid paying for idle agent compute.

The Kubernetes **Horizontal Pod Autoscaler** scales on metrics-server CPU/memory (or custom metrics
plumbing). It **cannot natively read Redis queue depth**, and standard HPA cannot scale a Deployment
to zero. Driving worker scaling off CPU would be wrong: a worker blocked on a slow Claude/Tavily
call shows low CPU while the queue backs up. This was a correctness gap, not just an optimization.

## Decision

Scale the worker Deployment with **KEDA** using its **Redis scaler**, targeting the `arq:queue`
list depth, with **scale-to-zero**
([`infra/k8s/atlas/templates/worker-scaledobject.yaml`](../../infra/k8s/atlas/templates/worker-scaledobject.yaml),
[`values.yaml`](../../infra/k8s/atlas/values.yaml) `keda`). The API keeps a **CPU HPA**.

Key settings: `minReplicaCount: 0` (scale-to-zero), `maxReplicaCount: 20`, `lagThreshold: 5`
(desired jobs per replica), `pollingInterval: 15s`, `cooldownPeriod: 300s`, plus a `fallback` and a
`TriggerAuthentication` hook for ElastiCache AUTH.

## Consequences

- **+** Workers scale on the **correct signal** (backlog), and to **zero** when idle — directly
  cutting dev/idle cost (see cost notes).
- **+** API and worker tiers scale **independently**, matching their different load shapes.
- **−** Adds a **cluster add-on dependency** (KEDA must be installed and healthy; it owns CRDs/HPAs).
  If KEDA is down, the `fallback` (1 replica) prevents a total stall but won't scale.
- **−** Scale-from-zero adds **cold-start latency** to the first run after idle (pod schedule + image
  pull + startup probe); acceptable because runs are minutes-long, not interactive-millisecond.
- **−** Worker count interacts with **RDS connection limits** — max KEDA replicas must be sized
  against PgBouncer/RDS `max_connections` (see runbook failure modes).
