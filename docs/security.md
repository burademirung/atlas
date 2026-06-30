# Security Architecture

> The defense-in-depth security overview for Firstline / Atlas, mapped to OWASP and NIST. This
> **complements** the [threat model](threat-model.md) (attack paths + status) — it does not
> duplicate it. For vulnerability reporting see [`SECURITY.md`](../SECURITY.md).

## Table of contents

- [Security posture in one paragraph](#security-posture-in-one-paragraph)
- [Trust boundaries](#trust-boundaries)
- [The defense-in-depth layers](#the-defense-in-depth-layers)
- [Edge response headers & CSP](#edge-response-headers--csp)
- [PII redaction](#pii-redaction)
- [Denial-of-wallet guardrails](#denial-of-wallet-guardrails)
- [Trusted-proxy IP resolution](#trusted-proxy-ip-resolution)
- [Vulnerability disclosure (security.txt)](#vulnerability-disclosure-securitytxt)
- [Standards mapping](#standards-mapping)
- [Implemented vs planned](#implemented-vs-planned)

> Privacy & regulatory posture (GDPR / CCPA / HIPAA) has its own page:
> [`compliance.md`](compliance.md).

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
- **Production guardrails (now enforced, OWASP LLM10):** a global **kill-switch**
  (`service_paused` → `503`), per-user (`daily_run_quota` = 50) and per-IP (`daily_run_quota_ip` =
  200) **daily quotas** (Redis counters that expire at UTC midnight), an **Idempotency-Key** dedupe
  so a retried/double-clicked submission is charged once, and a per-run **token ceiling**
  (`max_run_tokens` = 50 000) that truncates a run mid-flight rather than spinning. All live in
  [`security/guardrails.py`](../apps/api/src/atlas_api/security/guardrails.py); see
  [Denial-of-wallet guardrails](#denial-of-wallet-guardrails).
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
- **PII redaction on write + in logs:** breach descriptions are masked before they are persisted or
  logged ([PII redaction](#pii-redaction)).
- **Storage limitation + erasure (live edition):** a 30-day retention cron and a self-service
  `DELETE /api/runs/:id` keep stored PII bounded and deletable. Full privacy posture:
  [`compliance.md`](compliance.md).

## Edge response headers & CSP

The live Worker sets a full set of **defense-in-depth response headers on every response** — HTML,
API/JSON, the SSE stream, and the static-asset fall-through (OWASP ASVS V14 Configuration; MDN
security headers). They are applied two ways so there is no gap:

- `/api/*` and the SSE stream — a `withSecurityHeaders()` wrapper at the single `fetch` choke-point
  re-emits every response with the headers layered on
  ([`apps/cloudflare/src/index.ts`](../apps/cloudflare/src/index.ts)).
- Static assets — a [`public/_headers`](../apps/cloudflare/public/_headers) file applies the same set
  to HTML/CSS/JS served by the `ASSETS` binding.

| Header | Value (summary) |
|---|---|
| `Content-Security-Policy` | `default-src 'self'`; `script-src 'self' https://challenges.cloudflare.com`; `style-src 'self' https://fonts.googleapis.com 'unsafe-inline'`; `font-src 'self' https://fonts.gstatic.com`; `img-src 'self' data:`; `connect-src 'self'`; `frame-src https://challenges.cloudflare.com`; `base-uri 'self'`; `form-action 'self'`; `frame-ancestors 'none'`; `object-src 'none'` |
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` |
| `X-Content-Type-Options` | `nosniff` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `Permissions-Policy` | `camera=(), microphone=(), geolocation=()` |
| `X-Frame-Options` | `DENY` |

CSP notes (honest): `'unsafe-inline'` is kept **only** for `style-src`, because `index.html` sets
inline `style="--x:…%"` custom properties on the animated diagram nodes — there is **no inline
script** (`script-src` has no `'unsafe-inline'`). `challenges.cloudflare.com` is allowed in
`script-src` + `frame-src` for the optional Turnstile widget; `connect-src 'self'` because the
browser only talks to this Worker (Turnstile siteverify is server-side). This closes the previously
documented "missing strict CSP / no edge security headers" gap (see
[threat model §3](threat-model.md#3-insecure-output-handling--xss-from-model-output-owasp-llm05)).

## PII redaction

Firstline ingests free-text breach descriptions that routinely contain the leaked identifiers
themselves (SSNs, card numbers, emails, phone numbers). Those are **masked before persistence and
before logging** so they neither sit in durable storage nor leak into log sinks (OWASP ASVS V8.3;
OWASP LLM02 — Sensitive Information Disclosure; NIST SP 800-122).

- **Live edition** — `redactPII()` in [`src/index.ts`](../apps/cloudflare/src/index.ts) masks the
  `question` and writes the masked copy to D1; Claude still receives the **original** text in-memory
  for an accurate plan.
- **Production edition** — `redact_pii()`
  ([`security/redaction.py`](../apps/api/src/atlas_api/security/redaction.py)) runs in
  `RunRepository.create()` *before* the row is flushed, and a `RedactionFilter` on the root log
  handler ([`logging.py`](../apps/api/src/atlas_api/logging.py)) scrubs every log record.

The matcher handles emails, US SSNs, **Luhn-validated** card numbers (so it doesn't clobber long
order ids), and phone numbers. It is heuristic by design — it may over-mask or miss exotic formats —
so it is **defense-in-depth alongside** access control and encryption, not a substitute. The
generated `report` is deliberately **not** redacted: it legitimately contains official hotline
numbers (e.g. the FTC IdentityTheft line) that the phone heuristic would destroy. Full data-handling
posture: [`compliance.md`](compliance.md).

## Denial-of-wallet guardrails

The production `POST /v1/runs` path is wrapped in layered cost controls
([`security/guardrails.py`](../apps/api/src/atlas_api/security/guardrails.py),
[`runs/router.py`](../apps/api/src/atlas_api/runs/router.py)), enforced in this order:

1. **Kill-switch** — `check_service_paused(settings.service_paused)` returns `503` when an operator
   pauses the service, so a runaway client or upstream incident can be contained without a redeploy.
2. **Idempotency-Key** — a prior run id stored under the caller's `Idempotency-Key` is returned
   instead of starting (and billing) a second run; the key dedupes for `idempotency_ttl_seconds`
   (default 24 h).
3. **Daily quotas** — `enforce_daily_quota()` increments per-user (`daily_run_quota` = 50) and per-IP
   (`daily_run_quota_ip` = 200) Redis counters that **expire at the next UTC midnight**; either
   ceiling returns `429`.
4. **Per-run token ceiling** — the worker stops a run and marks it `truncated` once cumulative token
   usage reaches `max_run_tokens` (default 50 000), via `over_token_cap()`
   ([`worker.py`](../apps/api/src/atlas_api/worker.py)).

These close the previously documented "spend kill-switch + per-user quotas not yet enforced" gap.

## Trusted-proxy IP resolution

The per-IP quota key must not be forgeable, or the denial-of-wallet guardrail is trivially bypassed.
`X-Forwarded-For` is `client, proxy1, …, proxyN` where the **left-most** entries are
attacker-controlled (a client can prepend arbitrary values; a trusted proxy only ever *appends*).
Trusting the left-most value would let anyone mint a fresh quota key per request.

`client_ip(request, trusted_proxy_count)`
([`security/guardrails.py`](../apps/api/src/atlas_api/security/guardrails.py)) therefore reads the IP
at `trusted_proxy_count` hops from the **right** — the hops appended by our own infrastructure. With
one trusted proxy (the ALB, the default `trusted_proxy_count` = 1) that is the last element; the
candidate is validated as a real IP or it falls back to the socket peer. Setting
`trusted_proxy_count = 0` ignores the header entirely and uses `request.client.host`. The robust
deployment posture is to also bind Uvicorn's `--forwarded-allow-ips` (or `ProxyHeadersMiddleware`) to
the VPC CIDR so the socket peer is already correct; this parser is the defense-in-depth fallback.
**This fixed a HIGH "quota bypass via X-Forwarded-For spoofing" finding.**

## Vulnerability disclosure (security.txt)

The live edition publishes [`/.well-known/security.txt`](../apps/cloudflare/public/.well-known/security.txt)
(RFC 9116) advertising a `Contact:`, `Expires:`, and `Preferred-Languages:` so researchers have a
standard channel. The repository's full disclosure policy is [`SECURITY.md`](../SECURITY.md).

## Standards mapping

| Area | Standard | Where addressed |
|---|---|---|
| Web app risks | [OWASP Top 10](https://owasp.org/www-project-top-ten/) | layers 3–6 above; [threat model](threat-model.md) |
| LLM risks | [OWASP LLM Top 10](https://owasp.org/www-project-top-10-for-large-language-model-applications/) | layers 1–2; threat model §1–3 |
| App verification | [OWASP ASVS](https://owasp.org/www-project-application-security-verification-standard/) | authn/z, input handling, secrets |
| Authentication | [NIST SP 800-63B](https://pages.nist.gov/800-63-3/sp800-63b.html) | argon2id, token lifecycle (layer 3) |
| Incident handling | [NIST SP 800-61](https://csrc.nist.gov/pubs/sp/800/61/r3/final) | the product's own breach-response guidance; the [runbook](runbook.md) |
| JWT hygiene | [RFC 8725](https://www.rfc-editor.org/rfc/rfc8725) | `auth/tokens.py` (layer 3) |
| Security headers | [MDN](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers) / ASVS V14 | edge CSP/HSTS/… (`src/index.ts`, `public/_headers`) |
| Privacy / PII | [GDPR](https://gdpr-info.eu/) · [CCPA](https://oag.ca.gov/privacy/ccpa) · NIST SP 800-122 | redaction, retention, erasure — [`compliance.md`](compliance.md) |
| Disclosure | [RFC 9116](https://www.rfc-editor.org/rfc/rfc9116) | `/.well-known/security.txt`, `SECURITY.md` |

## Implemented vs planned

This document describes the **architecture**; the [threat model](threat-model.md#status-summary)
carries the authoritative, per-control status table (✅ / 🟡 / 📋). A recent hardening pass **shipped**
several controls that were previously on the backlog: full **edge security headers + strict CSP**,
**PII redaction** on write and in logs, a **spend kill-switch + per-user/per-IP daily quotas + per-run
token ceiling** (with spoof-resistant client-IP resolution), **30-day retention** and **self-service
erasure** in the live edition, a `/.well-known/security.txt`, a coverage gate, and Semgrep + Bandit
SAST. The major **still-planned** controls are: Postgres **Row-Level Security**, **DOMPurify**
output-sanitization in the renderer, a production **retention purge job** + `DELETE /v1/runs/:id`
endpoint, **cosign admission verification** in-cluster, and a **CI cross-tenant authz test**. Treat
those as the remaining hardening backlog, not as shipped guarantees.
