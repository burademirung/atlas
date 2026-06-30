# Security Policy

> How to report a vulnerability in Firstline / Atlas, and a short summary of the product's own
> security posture. Deep dives: [`docs/security.md`](docs/security.md) and
> [`docs/threat-model.md`](docs/threat-model.md).

## Reporting a vulnerability

Please report security vulnerabilities **privately** — do not open a public GitHub issue for a
security problem.

- **Email:** <burademirung@gmail.com>
- Include: a description of the issue, the affected edition/component (live Cloudflare Worker vs
  production FastAPI/EKS stack), reproduction steps or a proof-of-concept, and the impact you
  believe it has.
- If you have a fix or mitigation in mind, include it — but please **do not** open a public PR that
  reveals the vulnerability before it is addressed.

### What to expect

This is a portfolio/demonstration project maintained on a best-effort basis. As a guideline:

| Stage | Target |
|---|---|
| Acknowledge your report | within ~3 business days |
| Initial assessment / severity triage | within ~7 business days |
| Fix or mitigation plan | depends on severity and complexity |

We will keep you updated on progress and credit you (if you wish) once the issue is resolved.
Please give us reasonable time to remediate before any public disclosure.

### Scope

In scope: the application code in `apps/`, the infrastructure code in `infra/`, the CI/CD
workflows in `.github/`, and the deployed live edition at
<https://atlas-research.burademirung.workers.dev>.

Out of scope: third-party services this project depends on (Anthropic, Tavily, Cloudflare, AWS,
Have I Been Pwned) — report those to the respective vendors.

## Product security posture (summary)

Firstline is a security incident-response copilot: it ingests **attacker-controllable web
content**, reasons over it with an LLM, renders the result in a browser, and **spends money per
run**. Its design treats that threat model as primary. Highlights:

- **Prompt-injection defense (OWASP LLM01):** all web/search results are treated as untrusted
  **data, never instructions** — spotlighting in the live Worker's system prompt and fenced
  `<untrusted_source>` content in the production `write_node`. The live Worker also constrains
  `web_search` to an **allow-list of authoritative domains**.
- **Denial-of-wallet limits (OWASP LLM10):** per-run caps on question length, search count, and
  output tokens; bounded parallel fan-out; idempotent enqueue + cooperative cancellation. Per-IP
  and global daily caps exist in the live edition.
- **AuthN/Z (OWASP A07 / RFC 8725):** JWT with an algorithm allowlist + required claims, short
  access TTL, refresh-token rotation with reuse detection, argon2id password hashing, and
  per-user tenant isolation on every run endpoint.
- **SSRF containment (OWASP A01):** default-deny egress NetworkPolicy on the production worker
  blocking IMDS/RFC1918/link-local ranges; the live edition exposes no server-side fetch primitive.
- **Secrets & supply chain (OWASP A03/A04):** env-only config, no long-lived cloud keys (GitHub
  OIDC → assume role), gitleaks + Trivy + CodeQL scans, cosign-signed images with SBOMs, ECR by
  digest, External Secrets Operator at runtime.

Some controls are **planned, not yet implemented** (e.g. Postgres Row-Level Security, a strict
CSP + DOMPurify, a spend kill-switch, PII redaction in logs). Both the implemented and planned
controls — with honest status markers — are documented in
[`docs/threat-model.md`](docs/threat-model.md) and [`docs/security.md`](docs/security.md), mapped
to OWASP Top 10, the OWASP LLM Top 10, and NIST SP 800-61 / SP 800-63B.
