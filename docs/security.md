# Security Architecture

> The defense-in-depth security overview for Firstline / Atlas, mapped to OWASP and NIST. This
> **complements** the [threat model](threat-model.md) (attack paths + status) — it does not
> duplicate it. For vulnerability reporting see [`SECURITY.md`](../SECURITY.md).

## Table of contents

- [Security posture in one paragraph](#security-posture-in-one-paragraph)
- [Trust boundaries](#trust-boundaries)
- [The defense-in-depth layers](#the-defense-in-depth-layers)
- [Standards mapping](#standards-mapping)
- [Implemented vs planned](#implemented-vs-planned)

## Security posture in one paragraph

Firstline ingests **attacker-controllable web content**, reasons over it with an LLM, renders the
result in a browser, and **spends money on every run**. So its security model treats the
agent/LLM boundary as the highest-risk node and layers controls around it: untrusted-content
spotlighting and an authoritative-domain allow-list at the LLM boundary; cost caps and bounded
fan-out against denial-of-wallet; JWT + per-user isolation for access control; default-deny egress
against SSRF; and OIDC + signed images + scanning across the supply chain. The
[threat model](threat-model.md) maps each risk to a control with an honest status marker; this
document is the architectural view of those controls.

## Trust boundaries

```
Browser (untrusted) ─▶ Edge Worker ─▶ API ─▶ Agent Worker ─▶ { Claude, Search, DB, Redis, S3 }
                                                  ▲
                                   highest-risk node: consumes untrusted
                                   web content *and* talks to the LLM
```

- **Untrusted inputs:** the research question (may contain PII) and — critically — **all fetched
  web content** (page text, titles, snippets), which is attacker-controllable.
- **Assets to protect:** user questions/reports, source data, the JWT secret + cloud credentials,
  the Anthropic/Tavily spend (money), and per-user run history.

## The defense-in-depth layers

### 1. The LLM / agent boundary (OWASP LLM01, LLM05)

- **Prompt-injection spotlighting.** All web/search content is framed as **untrusted data, never
  instructions.** The live Worker's system prompt
  ([`apps/cloudflare/src/index.ts`](../apps/cloudflare/src/index.ts)) and the production
  `write_node` ([`agents/nodes.py`](../apps/api/src/atlas_api/agents/nodes.py)) fence fetched
  content (`<untrusted_source>…</untrusted_source>`), tell the model to ignore injected directives,
  and to **note injection attempts** in the output.
- **Authoritative-domain allow-list (live edition).** `web_search` is constrained to a curated
  `ALLOWED_DOMAINS` set (identitytheft.gov, consumer.ftc.gov, cisa.gov, nist.gov, the three credit
  bureaus, irs.gov, ssa.gov, …), so the model can only ground its plan in official guidance.
- **No source self-certification.** The model must cite claims `[n]` and must not invent or alter
  citations based on page text.
- **Grounding/verify pass.** The production `verify_node` asks the model which sources actually
  support concrete steps and keeps claims only for those (falling back to keeping all sources if
  the judge returns nothing parseable). Output is model-authored Markdown rendered as
  text/structured content, not raw HTML injection. See [agent design](agent-design.md).

### 2. Cost / abuse (OWASP LLM10 — denial-of-wallet)

- **Per-run caps:** live edition — question ≤ 500 chars, `web_search max_uses: 5`,
  `max_tokens: 6000`; production — `max_subquestions` (4) × `max_sources_per_q` (3) bound the
  searches per run, and the graph is acyclic (cannot loop).
- **Idempotency + cancellation:** `POST /v1/runs` enqueues with `_job_id=run:<id>`; the worker
  supports `allow_abort_jobs` and checks a Redis cancel flag between graph supersteps.
- **Daily caps (live edition):** per-IP (`20`) + global (`500`) counters in the D1 `rate_limits`
  table, bumped atomically.

### 3. Authentication & authorization (OWASP A07, RFC 8725)

- **JWT with an algorithm allowlist** + required `exp/iss/aud/sub/jti`, rejecting `alg:none` and
  algorithm confusion ([`auth/tokens.py`](../apps/api/src/atlas_api/auth/tokens.py)).
- **Short access TTL (600 s)** + **refresh rotation with reuse detection** — a reused refresh `jti`
  revokes the whole token family via Redis; logout adds the access `jti` to a Redis deny-list.
- **Argon2id** password hashing with tuned cost (`m=19456, t=2, p=1`)
  ([`auth/passwords.py`](../apps/api/src/atlas_api/auth/passwords.py)).
- **Per-user tenant isolation:** every `{id}` run endpoint goes through `get_for_user(run_id,
  user_id)`; non-owners get 404, including the SSE subscribe path
  ([`runs/router.py`](../apps/api/src/atlas_api/runs/router.py)).

### 4. Network / SSRF (OWASP A01)

- **Default-deny egress NetworkPolicy** on the production worker, with IMDS (`169.254.169.254/32`),
  link-local, and RFC1918 ranges explicitly blocked; only HTTPS egress, DNS, and the Pod Identity
  endpoint are allowed ([`networkpolicy.yaml`](../infra/k8s/atlas/templates/networkpolicy.yaml),
  [`values.yaml`](../infra/k8s/atlas/values.yaml)).
- **No SSRF-able fetch primitive (live edition):** `web_search` is a managed Anthropic server tool,
  so the Worker performs no arbitrary server-side fetch on behalf of content. The production agent
  searches via Tavily (which fetches on its own infra) rather than fetching arbitrary URLs itself.

### 5. Secrets & supply chain (OWASP A03/A04)

- **Env-only config** (`pydantic-settings`); no secrets in git/images; CI runs **gitleaks** + a
  Trivy secret scan.
- **No long-lived cloud keys:** AWS access is GitHub **OIDC → assume role**; Cloudflare uses a
  scoped, rotatable token.
- **Signed, attested images:** CD signs with **cosign** (keyless) + attaches an **SBOM** (syft) +
  SLSA provenance; images pushed to **ECR by digest**. Trivy fs/IaC + **CodeQL** gates; Dependabot;
  SHA-pinned actions. Runtime secrets via **External Secrets Operator** → AWS Secrets Manager.

### 6. Data protection & platform hardening (OWASP A05/A08/A09; NIST SP 800-61)

- **Encryption everywhere (production):** RDS (KMS), ElastiCache (at-rest + in-transit), S3
  (SSE-KMS + public-access block + TLS-only). Report exports are short-lived **pre-signed** S3
  objects.
- **Platform hardening:** Restricted Pod Security Standard, NetworkPolicies, PodDisruptionBudgets,
  PgBouncer in front of RDS, immutable image digests.
- **Structured logging with request correlation** (`X-Request-ID`) and **fail-closed errors**
  (RFC-9457 problem responses, no stack-trace leakage). See [observability](observability.md).
- **k-anonymity for password checks:** the Have I Been Pwned integration sends only a SHA-1 prefix
  ([`breach/hibp.py`](../apps/api/src/atlas_api/breach/hibp.py)) — data minimization by design.

## Standards mapping

| Area | Standard | Where addressed |
|---|---|---|
| Web app risks | [OWASP Top 10](https://owasp.org/www-project-top-ten/) | layers 3–6 above; [threat model](threat-model.md) |
| LLM risks | [OWASP LLM Top 10](https://owasp.org/www-project-top-10-for-large-language-model-applications/) | layers 1–2; threat model §1–3 |
| App verification | [OWASP ASVS](https://owasp.org/www-project-application-security-verification-standard/) | authn/z, input handling, secrets |
| Authentication | [NIST SP 800-63B](https://pages.nist.gov/800-63-3/sp800-63b.html) | argon2id, token lifecycle (layer 3) |
| Incident handling | [NIST SP 800-61](https://csrc.nist.gov/pubs/sp/800/61/r3/final) | the product's own breach-response guidance; the [runbook](runbook.md) |
| JWT hygiene | [RFC 8725](https://www.rfc-editor.org/rfc/rfc8725) | `auth/tokens.py` (layer 3) |

## Implemented vs planned

This document describes the **architecture**; the [threat model](threat-model.md#status-summary)
carries the authoritative, per-control status table (✅ / 🟡 / 📋). The major **planned** controls
not yet enforced in code are: Postgres **Row-Level Security**, a strict **CSP + DOMPurify**
sanitization in the renderer, a **spend kill-switch** + per-user daily quota enforced atomically,
**PII redaction** in logs/traces, a data-retention / **erasure** endpoint, **cosign admission
verification** in-cluster, and a **CI cross-tenant authz test**. Treat those as the hardening
backlog, not as shipped guarantees.
</content>
