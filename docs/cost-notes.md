# Atlas — Cost Notes

A rough cost model for both editions and the levers that move the bill. Numbers are
**order-of-magnitude planning estimates**, not quotes — verify against current
[Anthropic](https://www.anthropic.com/pricing), [Tavily](https://tavily.com/), AWS, and Cloudflare
pricing before budgeting. The point is to show *where* cost concentrates and how to keep development
cheap.

The two editions sit at opposite ends of the cost curve:

- **Live (Cloudflare) edition** — near-zero fixed cost; you pay per request (mostly LLM tokens).
- **Production edition** — meaningful fixed monthly cost (cluster + managed data services) plus
  per-run LLM/search cost.

---

## 1. Live (Cloudflare) edition

Per-request, serverless. There are no servers to keep warm.

| Component | Cost shape | Notes |
|---|---|---|
| Cloudflare Workers | Per-request + CPU-time; generous free tier, then Workers Paid (~$5/mo base) | One Worker serves SPA + API; SSE streaming is cheap wall-clock, low CPU |
| Cloudflare D1 | Per-row-read/write + storage; large free tier | Tiny schema (`runs`, `sources`, `rate_limits`); negligible at demo scale |
| Cloudflare Assets | Static asset serving | Effectively free at this scale |
| **Anthropic (Claude Opus 4.8)** | **Per token — the dominant cost** | One streamed call per run, `max_tokens: 6000`, `web_search max_uses: 5` |
| Anthropic `web_search` | Per search server-tool use | Bundled into the Claude call; bounded by `max_uses: 5` |

**Dominant lever:** Claude tokens per run. A run is one Opus call bounded to 6000 output tokens plus
input (system prompt + question + up to 5 web_search round-trips). Opus is the premium tier; the
single biggest cost reduction is **routing cheaper runs to a smaller model** (e.g. Sonnet/Haiku) or
trimming `max_tokens` / `max_uses`.

**Built-in cost guardrails (live edition):** question length ≤ 500 chars, `max_uses: 5`,
`max_tokens: 6000`, and the scaffolded `PER_IP_DAILY` (20) / `GLOBAL_DAILY` (500) caps in the
`rate_limits` table — these bound worst-case spend per IP and globally.

---

## 2. Production edition (AWS EKS)

Fixed infrastructure cost dominates here; LLM/search is per-run on top. Defaults from
[`infra/terraform/`](../infra/terraform/) — **dev** uses small instances + single NAT; **prod** uses
HA + larger instances.

| Component | dev default | prod default | Cost driver |
|---|---|---|---|
| **EKS control plane** | 1 cluster | 1 cluster | Flat per-cluster hourly (~$73/mo) |
| **EKS nodes** | 1–3 × `t3.large` | 2–6 × `m6i.large` | Biggest compute line; scales with worker fan-out |
| **NAT gateway** | **1 (shared)** | **1 per AZ (×3)** | Hourly **+ per-GB processed** — egress trap |
| **RDS PostgreSQL** | `db.t4g.micro`, single-AZ | `db.r6g.large`, **Multi-AZ** | Multi-AZ ~2×; storage + IOPS + backups |
| **ElastiCache Redis** | 1 × `cache.t4g.micro` | 2 × `cache.r6g.large`, Multi-AZ failover | Node-hours × node count |
| **ALB** | 1 | 1 | Hourly + LCU (SSE keeps connections open → LCU) |
| **S3** | report exports | report exports | Tiny — storage + requests |
| **ECR** | image storage | image storage | GB-month of images |
| **Data egress / VPC endpoints** | minimal | per-AZ NAT + cross-AZ | Egress + NAT processing; **VPC endpoints** cut NAT traffic to AWS APIs |
| **Anthropic + Tavily** | per run | per run | Per-run token + search cost (as live edition, ×N graph nodes) |

### Where prod cost concentrates

1. **NAT gateways** — per-AZ NAT plus per-GB data processing is a classic surprise. Workers egress
   to Claude/Tavily over 443 through NAT.
2. **EKS nodes** — the worker tier does the expensive LLM work; node count tracks concurrent runs.
3. **RDS Multi-AZ + ElastiCache HA** — roughly double the single-AZ cost for availability.
4. **Per-run LLM cost** — the production graph makes *more* model calls than the live edition (plan
   + N searches + verify + write), so per-run token cost is higher than the single-call Worker.

---

## 3. Keeping dev cheap

The repo's dev profile is already tuned for this — and the architecture adds scale-to-zero:

- **Single NAT gateway in dev** (`single_nat_gateway = true`) instead of one per AZ — the single
  largest dev saving ([`envs/dev/main.tf`](../infra/terraform/envs/dev/main.tf)).
- **Small instances:** `db.t4g.micro` RDS, `cache.t4g.micro` Redis, `t3.large` nodes; single-AZ,
  `deletion_protection = false`, `skip_final_snapshot = true`.
- **KEDA scale-to-zero workers** (`minReplicaCount: 0` in [`values.yaml`](../infra/k8s/atlas/values.yaml)):
  when the queue is empty, the worker tier scales to **zero pods**, so idle clusters don't pay for
  agent compute. This is the key reason queue-depth autoscaling (KEDA, not plain HPA) was chosen.
- **VPC endpoints** for S3/ECR/Secrets Manager/STS keep AWS-API traffic off the NAT path (less
  per-GB NAT processing).
- **Spot / Karpenter** for bursty worker capacity is specified for prod (cheaper burst compute).
- **Free local stack:** `docker compose up` runs the entire production edition with **zero cloud
  cost**, and without provider keys the agent uses a **deterministic stub search provider** — so you
  can develop and demo the full request → stream → report loop **without spending a cent on Claude
  or Tavily**.
- **No live eval cost per PR:** the per-PR eval uses the stub; the paid live eval runs **weekly**
  ([`.github/workflows/eval.yml`](../.github/workflows/eval.yml)), not on every push.

### Per-run LLM cost levers (both editions)

- **Model tier** — Opus vs Sonnet vs Haiku per node (planner/searcher/writer); spec assigns cheaper
  models to cheaper roles.
- **`max_subquestions` × `max_sources_per_q`** — bounds fan-out (default 4 × 3) and therefore search
  + token volume.
- **`max_tokens` / per-run token budget** — caps output; `perRunTokenBudget` yields a `truncated`
  report rather than unbounded spend.
- **Prompt caching** (`cache_control` on shared source context reused across verify/write) —
  specified ~90% cheaper on the reused prefix.
- **`web_search` / Tavily `max_results`** — fewer searches, lower search-API cost.

> Bottom line: in dev, idle cost is dominated by the always-on EKS control plane + small RDS/Redis
> (workers scale to zero); per-run cost is dominated by **Claude tokens**. Trim the model tier and
> fan-out caps first.
