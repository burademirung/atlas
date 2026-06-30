# Atlas — Threat Model

A focused threat model for an **agentic web-research product**. Atlas reads attacker-controllable
web content and feeds it to an LLM, then renders LLM output in a browser and spends money on every
run — so its risk profile is dominated by the OWASP **LLM Top 10 (2025)** plus classic web/cloud
risks (OWASP **Top 10 2021/2025**) and JWT hygiene (**RFC 8725**).

This document is **honest about status**: ✅ = enforced in code today, 🟡 = partial, 📋 =
documented-as-planned in the design spec but not yet built. Where a control differs between the two
editions, both are noted.

## Assets & trust boundaries

- **Assets:** user questions (may contain PII), generated reports, source data, JWT secret + cloud
  credentials, the Anthropic/Tavily spend (money), per-user run history.
- **Untrusted inputs:** the research question, and — critically — **all fetched web content** (page
  text, titles, snippets). Web pages are attacker-controllable.
- **Trust boundaries:** browser → edge Worker → API → worker → (Claude, search, DB, Redis, S3). The
  agent worker is the highest-risk node: it consumes untrusted content *and* talks to the LLM.

---

## 1. Indirect prompt injection (OWASP **LLM01**)

**Attack:** an attacker plants instructions in a web page ("ignore previous instructions", "you are
now…", hidden text) that Atlas fetches as a "source." The model obeys the page instead of the user
— exfiltrating the prompt, fabricating citations, or changing output format.

**Mitigations**

- ✅ **Spotlighting / untrusted-data framing.** The live Cloudflare Worker's system prompt
  ([`apps/cloudflare/src/index.ts`](../apps/cloudflare/src/index.ts)) explicitly instructs the model
  to treat **all** `web_search` results as untrusted **data**, never instructions; to ignore any
  injected directive; and to **note in the report** that a source attempted injection. The system
  prompt is the sole authority for the task.
- ✅ **No uncited assertions / no source self-certification** (live edition prompt): the model must
  cite claims with `[n]` and must not invent or alter citations based on page text.
- 🟡 **Production agent** — the graph's content-ingesting `search` node has no tools and cannot
  mutate run state beyond returning sources; the writer consumes only structured source records.
  The explicit untrusted-data delimiters on fetched content in the production prompts are 📋.
- 📋 **Dual-LLM / quarantine** and the **"Rule of Two"** (no single node simultaneously reads
  untrusted input, holds sensitive creds, and changes external state) are specified, not yet
  enforced as code.

**Residual risk:** prompt injection is not fully solvable by prompting; a determined page may still
bias output. Defense-in-depth (quarantine + structured outputs + entailment verification) is the
planned hardening.

---

## 2. Denial-of-wallet / unbounded consumption (OWASP **LLM10**)

**Attack:** an attacker submits expensive or high-volume questions to run up Anthropic + Tavily
cost, or loops the agent indefinitely.

**Mitigations**

- ✅ **Per-request caps (live edition):** question length ≤ 500 chars, `web_search` `max_uses: 5`,
  `max_tokens: 6000` — bounding tokens and searches per run.
- ✅ **Bounded fan-out (production):** `max_subquestions` (default 4) × `max_sources_per_q`
  (default 3) hard-caps searches per run ([`config.py`](../apps/api/src/atlas_api/config.py)); the
  graph is acyclic (plan → search → verify → write) so it cannot loop.
- ✅ **Idempotency:** `POST /runs` enqueues with `_job_id=run:<id>`, and the worker's `allow_abort_jobs`
  + a Redis cancel flag let runs be stopped mid-flight ([`worker.py`](../apps/api/src/atlas_api/worker.py)).
- ✅ **Daily caps (live edition):** the `rate_limits` table + `PER_IP_DAILY` (20) / `GLOBAL_DAILY`
  (500) counters are **enforced** in the research handler — both are bumped atomically per UTC day
  and the request is refused past the ceiling
  ([`apps/cloudflare/src/index.ts`](../apps/cloudflare/src/index.ts),
  [`migrations/0002_rate_limit.sql`](../apps/cloudflare/migrations/0002_rate_limit.sql)).
- ✅ **Per-user/per-IP daily quotas + kill-switch + token ceiling (production):** now enforced in
  [`security/guardrails.py`](../apps/api/src/atlas_api/security/guardrails.py) on the
  `POST /v1/runs` path. A global kill-switch (`service_paused` → `503`); per-user
  (`daily_run_quota` = 50) and per-IP (`daily_run_quota_ip` = 200) Redis counters expiring at UTC
  midnight (`429` on breach); an `Idempotency-Key` dedupe so retries are charged once; and a per-run
  token ceiling (`max_run_tokens` = 50 000) that yields a **`truncated`** partial report rather than
  a silent spin ([`worker.py`](../apps/api/src/atlas_api/worker.py)). The Redis counter is
  incremented-then-checked (`INCR` + `EXPIRE`), failing on the limit.
- ✅ **Spoof-resistant client IP (fixed a HIGH finding):** the per-IP quota key is derived by
  `client_ip(request, trusted_proxy_count)`, which reads the **right-most trusted** `X-Forwarded-For`
  hop (the ALB appends; left-most entries are attacker-controlled), not the forgeable left-most
  value — closing a "quota bypass via X-Forwarded-For spoofing" hole. `trusted_proxy_count`
  (default 1) is configurable; `0` uses the socket peer.
- 📋 Per-provider **cost meters with alerting**, prompt caching, and **Turnstile** on registration
  (`TURNSTILE_*` env hooks exist in the Worker) remain specified, not yet wired.

**Residual risk:** quotas are calendar-day windows keyed on user + IP; a determined attacker with
many IPs and accounts could still spread load under the ceilings. Per-provider spend alerting is the
planned backstop. The Redis `INCR`/`EXPIRE` pair is not a single atomic Lua script, so a crash
between the two leaves a counter without a TTL until the next write — a minor over-counting edge, not
a bypass.

---

## 3. Insecure output handling / XSS from model output (OWASP **LLM05**)

**Attack:** the model emits Markdown that embeds attacker-controlled HTML/JS (echoed from a
poisoned page), which executes in the victim's browser when the report renders.

**Mitigations**

- 🟡 **Markdown rendering** is done client-side ([`apps/web/src/markdown.ts`](../apps/web/src/markdown.ts),
  [`apps/cloudflare/public/app.js`](../apps/cloudflare/public/app.js)). Reports are model-authored
  Markdown rendered as text/structured content rather than raw HTML injection.
- ✅ **Strict CSP at the edge (live edition):** a full `Content-Security-Policy` (plus HSTS,
  `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy`, `X-Frame-Options: DENY`) is set
  on **every** response — `/api/*` and SSE via `withSecurityHeaders()` in
  [`src/index.ts`](../apps/cloudflare/src/index.ts), and static assets via
  [`public/_headers`](../apps/cloudflare/public/_headers). `script-src` has **no** `'unsafe-inline'`
  (`'unsafe-inline'` is scoped to `style-src` only, for the diagram's inline custom-property styles);
  `object-src 'none'`, `frame-ancestors 'none'`, `base-uri 'self'`. This caps the blast radius of any
  injected markup. See [security §Edge response headers & CSP](security.md#edge-response-headers--csp).
- 📋 **Raw-HTML disabled + DOMPurify sanitize** and sanitizing source URLs/titles remain specified
  renderer controls — the CSP is the edge backstop, but DOMPurify in the renderer is not yet wired.
  Tokens should live in an httpOnly cookie or memory, **never `localStorage`**.

**Residual risk:** any path that interpolates source text/titles/URLs into the DOM without
sanitization is an XSS sink. Treat the renderer and a strict CSP as the load-bearing controls and
test them.

---

## 4. SSRF → cloud metadata (OWASP **A01:2025**)

**Attack:** the research worker fetches attacker-supplied/attacker-influenced URLs. An attacker
steers a fetch at `169.254.169.254` (IMDS) or an internal service to steal cloud credentials or
reach private infrastructure (SSRF → IMDS credential theft).

**Mitigations**

- ✅ **Default-deny egress NetworkPolicy** with explicit allows
  ([`networkpolicy.yaml`](../infra/k8s/atlas/templates/networkpolicy.yaml),
  [`values.yaml`](../infra/k8s/atlas/values.yaml) `networkPolicy`): worker egress is HTTPS-only,
  with **IMDS + RFC1918 + link-local explicitly carved out** (`169.254.169.254/32`,
  `169.254.0.0/16`, `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16` blocked). DNS and the EKS Pod
  Identity endpoint are the only other allowed egress.
- ✅ **Edge isolation (live edition):** the Cloudflare Worker does not perform arbitrary
  server-side URL fetches on behalf of content — `web_search` is a managed Anthropic server tool,
  so there is no SSRF-able fetch primitive exposed.
- 📋 **IMDSv2 enforced, hop-limit 1** (Terraform), and application-level URL validation
  (scheme/host **allowlist**, **resolve-then-pin IP** to defeat DNS rebinding, reject redirects into
  private ranges) are specified. An egress proxy is the recommended belt-and-suspenders.

**Residual risk:** the production agent currently relies on Tavily (which fetches on its own
infrastructure) rather than fetching arbitrary URLs itself, which limits the SSRF surface today;
adding a direct `web_fetch` path would require the URL-validation controls above before shipping.

---

## 5. AuthN/AuthZ & tenant isolation (OWASP **A07:2025** / **RFC 8725**)

**Attack:** forge/replay a JWT, confuse the verifier with `alg:none` or HS/RS confusion, or access
another tenant's runs/sources/exports.

**Mitigations**

- ✅ **JWT alg allowlist** — `jwt.decode(..., algorithms=[settings.jwt_algorithm])` rejects
  `alg:none` and algorithm-confusion; `aud` + `iss` validated; `exp`/`iss`/`aud`/`sub`/`jti`
  **required** ([`auth/tokens.py`](../apps/api/src/atlas_api/auth/tokens.py)).
- ✅ **Short access TTL** (600s) + **refresh rotation with reuse detection**: a reused refresh
  `jti` revokes the entire **token family** via Redis; **access revocation** via a Redis `jti`
  deny-list checked per request; logout revokes.
- ✅ **Argon2id** password hashing with tuned cost (`m=19456, t=2, p=1`)
  ([`auth/passwords.py`](../apps/api/src/atlas_api/auth/passwords.py), `config.py`).
- ✅ **Per-user isolation enforced on `{id}` endpoints**: every run read goes through
  `get_for_user(run_id, user_id)`; non-owners get 404, including the **SSE subscribe** path
  ([`runs/router.py`](../apps/api/src/atlas_api/runs/router.py)).
- 📋 **Postgres Row-Level Security** (policy on an `app.user_id` GUC) as a defense-in-depth
  backstop; **edge Worker full signature validation** (not a presence check); login throttling /
  breached-password check; **cross-tenant authz test in CI** asserting 403/404 on every `{id}`
  endpoint — all specified, partially built.

**Residual risk:** isolation rests on the repository-layer filter until RLS lands; a missing filter
on a future endpoint would be a cross-tenant leak. The CI cross-tenant test is the planned guardrail
against regressions.

---

## 6. Secrets management & supply chain (OWASP **A03/A04:2025**)

**Mitigations**

- ✅ **No secrets in git/images:** `pydantic-settings` reads env only; CI runs a **gitleaks** scan
  and a **Trivy** secret scan ([`.github/workflows/ci.yml`](../.github/workflows/ci.yml)). Dev
  secrets in `docker-compose.yml` are clearly non-production.
- ✅ **No long-lived cloud keys:** AWS access is **GitHub OIDC → assume role** in CD and Terraform;
  Cloudflare uses a **scoped, rotatable** API token (OIDC not yet supported by wrangler).
- ✅ **Signed, attested images:** CD signs with **cosign** (keyless) and attaches an **SBOM** (syft)
  + SLSA provenance; images pushed to **ECR by digest** (tag immutability)
  ([`.github/workflows/cd.yml`](../.github/workflows/cd.yml)).
- ✅ **Vuln gates:** Trivy fs + IaC config scans gate on CRITICAL/HIGH; **CodeQL** (Py + TS)
  ([`.github/workflows/codeql.yml`](../.github/workflows/codeql.yml)); Dependabot for pip/npm/actions;
  every action **SHA-pinned**.
- ✅ **Runtime secrets:** **External Secrets Operator** pulls from **AWS Secrets Manager** into a
  k8s Secret (never baked into images/values); RDS/ElastiCache secrets generated by Terraform.
- 📋 **cosign admission verification** (reject unsigned images at admission) and automated Secrets
  Manager rotation are specified.

---

## 7. Data privacy & PII in questions + logs (OWASP **A08/A09:2025**)

**Attack/risk:** questions and fetched content may contain PII; leaking it via logs/traces, or
retaining it indefinitely, is a privacy harm.

**Mitigations**

- ✅ **Encryption everywhere (production):** RDS (KMS), ElastiCache (at-rest + in-transit), S3
  (SSE-KMS + public-access block + TLS-only policy) — explicit in Terraform
  ([`infra/terraform/README.md`](../infra/terraform/README.md)). Report exports are **pre-signed**,
  short-lived S3 objects, never public.
- ✅ **Structured logging with request correlation** (`request_id`)
  ([`middleware.py`](../apps/api/src/atlas_api/middleware.py), [`logging.py`](../apps/api/src/atlas_api/logging.py)).
- ✅ **Fail-closed errors:** a global handler returns RFC-9457-style problem responses without
  stack-trace leakage ([`errors.py`](../apps/api/src/atlas_api/errors.py)).
- ✅ **PII redaction on write + in logs (both editions):** breach descriptions are masked **before**
  the `question` is persisted — `redactPII()` in the live Worker
  ([`src/index.ts`](../apps/cloudflare/src/index.ts)) and `redact_pii()` in
  `RunRepository.create()` ([`security/redaction.py`](../apps/api/src/atlas_api/security/redaction.py),
  [`runs/repository.py`](../apps/api/src/atlas_api/runs/repository.py)). A `RedactionFilter` on the
  root log handler ([`logging.py`](../apps/api/src/atlas_api/logging.py)) scrubs every log record so
  raw identifiers never reach a log sink. Emails, SSNs, **Luhn-validated** cards, and phones are
  masked; the model still gets the original in-memory; the `report` is intentionally not redacted
  (official hotline numbers).
- ✅ **30-day retention + self-service erasure (live edition):** a Cloudflare cron (`"17 3 * * *"`)
  purges runs/sources > 30 days and stale `rate_limits`, and `DELETE /api/runs/:id` lets a user
  erase a run on demand (`204`) — GDPR Art. 5(1)(e) / Art. 17, CCPA right to delete.
- 📋 **Production retention/erasure not yet automated:** prod relies on `ON DELETE CASCADE` from
  `users`; a scheduled purge job and a `DELETE /v1/runs/:id` endpoint are planned. **Security
  alerting** on auth spikes / budget breach / egress deny also remains specified. Full privacy
  posture and GDPR/CCPA/HIPAA stance: [`compliance.md`](compliance.md).

---

## Status summary

| Risk | OWASP | Status |
|---|---|---|
| Indirect prompt injection | LLM01 | ✅ live-edition prompt defense; 🟡/📋 prod quarantine + Rule-of-Two |
| Denial-of-wallet | LLM10 | ✅ per-run caps + daily quotas + kill-switch + token ceiling + spoof-resistant IP; 📋 cost alerting |
| Insecure output / XSS | LLM05 | ✅ strict edge CSP + security headers; 🟡 Markdown rendering; 📋 DOMPurify in renderer |
| SSRF → IMDS | A01 | ✅ default-deny egress + IMDS/RFC1918 block; 📋 IMDSv2 hop-limit + URL pinning |
| AuthN/Z & tenant isolation | A07 / RFC 8725 | ✅ JWT allowlist + rotation + per-user filter; 📋 RLS + CI cross-tenant test |
| Secrets & supply chain | A03/A04 | ✅ OIDC, cosign/SBOM, gitleaks, ESO, Semgrep + Bandit SAST; 📋 admission verify + rotation |
| Data privacy / PII | A08/A09 | ✅ PII redaction (write+logs) + encryption + 30-day retention/erasure (live); 📋 prod purge job + `DELETE /v1/runs` + alerting |

See the design spec §11 for the full hardening checklist:
[`docs/superpowers/specs/2026-06-29-deep-research-studio-design.md`](superpowers/specs/2026-06-29-deep-research-studio-design.md).
