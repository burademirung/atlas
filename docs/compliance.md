# Privacy & Compliance Posture

> Firstline ingests **sensitive personal data** — people describe data breaches in free text, which
> routinely contains the very identifiers that leaked (SSNs, card numbers, emails, phone numbers) and
> sometimes health- or financial-incident context. This document is the honest privacy & compliance
> posture: the data-handling principles we implement in code, where we stand against **GDPR / CCPA /
> HIPAA**, and the operational/legal work that is explicitly **out of code scope**. It complements
> [`security.md`](security.md) (controls) and [`threat-model.md`](threat-model.md) (attack paths +
> status). Nothing here claims certification — this is a portfolio project; read every statement as
> *posture / readiness*, not as an attested compliance artifact.

## Table of contents

- [What data we hold, and why it is sensitive](#what-data-we-hold-and-why-it-is-sensitive)
- [Data-handling principles (implemented)](#data-handling-principles-implemented)
- [GDPR posture](#gdpr-posture)
- [CCPA / CPRA posture](#ccpa--cpra-posture)
- [HIPAA posture (scope honesty)](#hipaa-posture-scope-honesty)
- [Control mapping (ASVS / NIST)](#control-mapping-asvs--nist)
- [Implemented vs. operational/legal work still required](#implemented-vs-operationallegal-work-still-required)

## What data we hold, and why it is sensitive

| Data | Where | Sensitivity |
|---|---|---|
| The breach description (`question`) | D1 `runs.question` (live) / Postgres `research_runs.question` (prod) | High — free text that often embeds SSNs, card numbers, emails, phone numbers, and breach context (incl. health/financial) |
| Leaked-data categories (`data_types`) | Postgres `research_runs.config` JSONB (prod) | Low–moderate — categorical (e.g. `ssn`, `financial`, `medical`), not the identifiers themselves |
| The generated plan (`report`) | `runs.report` / `reports.markdown` | Low — official-guidance steps; may legitimately contain public phone numbers (e.g. the FTC IdentityTheft line) |
| Sources | `sources` | Low — public URLs/titles from an authoritative allow-list |
| Account identity (prod only) | Postgres `users.email`, `password_hash` | High — email is personal data; password is argon2id-hashed, never stored in clear |

The live (Cloudflare) edition is **anonymous** — there is no account, only an unguessable random run
UUID. The production edition is authenticated (email + argon2id), so a run is linkable to a data
subject.

## Data-handling principles (implemented)

These are enforced in code today, not aspirational.

### 1. Data minimization & redaction-on-write (GDPR Art. 5(1)(c); NIST SP 800-122; OWASP ASVS V8.3)

The breach description is **redacted before it is persisted**. Recovery advice never needs the literal
identifier — knowing "an SSN was exposed" is enough to recommend a credit freeze; the nine digits add
breach blast-radius and compliance scope while adding nothing to the guidance.

- **Live edition** — `redactPII()` in
  [`apps/cloudflare/src/index.ts`](../apps/cloudflare/src/index.ts) masks emails, US SSNs,
  Luhn-validated card numbers, and phone numbers, and the masked copy is what is written to D1
  (`storedQuestion`). Claude still receives the **original** text in-memory to produce an accurate
  plan; only the persisted copy is redacted.
- **Production edition** — `redact_pii()` in
  [`security/redaction.py`](../apps/api/src/atlas_api/security/redaction.py) is applied in
  `RunRepository.create()` ([`runs/repository.py`](../apps/api/src/atlas_api/runs/repository.py))
  *before* the row is flushed, and a `RedactionFilter` is installed on the root log handler
  ([`logging.py`](../apps/api/src/atlas_api/logging.py)) so no breach description, stack trace, or
  interpolated log argument can carry raw identifiers into a log sink (OWASP LLM02 — Sensitive
  Information Disclosure).

Redaction is a heuristic, defense-in-depth control: it can over-mask (e.g. a 16-digit order id that
passes Luhn) or miss exotic formats. We accept false positives in stored data to avoid leaks, and
redaction **complements** — does not replace — access control and encryption at rest. The `report`
is deliberately **not** redacted, because the phone-number heuristic would destroy the official
hotline numbers the plan needs.

### 2. Storage limitation — 30-day retention & auto-delete (GDPR Art. 5(1)(e))

- **Live edition** — a Cloudflare **cron trigger** (`"17 3 * * *"` in
  [`wrangler.jsonc`](../apps/cloudflare/wrangler.jsonc)) invokes a `scheduled()` handler that purges
  runs and their sources older than 30 days (plus stale `rate_limits` rows) via `purgeExpired()`. The
  sweep is idempotent.
- **Production edition** — retention is **not yet automated**; the schema cascades cleanly
  (`research_runs` → sources/claims/reports `ON DELETE CASCADE`), so a scheduled purge job is a small
  addition. Treat prod retention automation as planned (see the table below).

### 3. Right to erasure — self-service deletion (GDPR Art. 17 / CCPA right to delete)

- **Live edition** — `DELETE /api/runs/:id` removes the run and its sources and returns `204`. Because
  the run id is an unguessable random UUID, anonymous self-service deletion is acceptable.
- **Production edition** — there is **no** `DELETE /v1/runs/:id` endpoint yet. Erasure today relies on
  the `ON DELETE CASCADE` from `users` down (deleting a user removes their runs and everything under
  them), but a self-service run-deletion endpoint and a documented erasure workflow are **planned**.

### 4. Encryption in transit & at rest (GDPR Art. 32; NIST 800-53 SC-13/SC-28)

- **Live edition** — Cloudflare terminates TLS; D1 is encrypted at rest by the platform.
- **Production edition** — Terraform configures **RDS** `storage_encrypted = true` (KMS),
  **ElastiCache** `at_rest_encryption_enabled` + `transit_encryption_enabled`, and **S3** report
  exports with SSE-KMS (dedicated CMK), a public-access block, a TLS-only bucket policy, and a
  `DenyUnEncryptedObjectUploads` statement ([`infra/terraform/modules/`](../infra/terraform/modules/)).
  Report exports are short-lived **pre-signed** objects, never public.

### 5. Purpose limitation & no secondary use

Data is used only to generate the requested recovery plan and to let the user browse their own run
history. There is no profiling, ad-targeting, or third-party data sale. The only external data egress
is the LLM call (Anthropic) and the constrained `web_search` against an **authoritative-domain
allow-list**.

## GDPR posture

> Posture, not certification. A production launch in the EU would require the legal artifacts called
> out as out-of-scope below.

- **Lawful basis (Art. 6).** For an authenticated user submitting their own breach for help, the
  natural bases are **consent** (Art. 6(1)(a)) and/or **performance of a service the user requested**
  (Art. 6(1)(b)). Because descriptions can contain **special-category data** (e.g. health context of a
  medical-records breach, Art. 9), an explicit-consent gate and an Art. 9 condition would be required
  before EU production use.
- **Data-subject rights.** Erasure (Art. 17) is implemented as self-service delete in the live
  edition; access/portability (Art. 15/20) are partially served by `GET /api/runs/:id` /
  `GET /v1/runs/{id}` returning the stored run. A formal rights-request process is operational work.
- **Storage limitation (Art. 5(1)(e)).** 30-day auto-delete in the live edition; planned for prod.
- **Data minimization (Art. 5(1)(c)).** Redaction-on-write (above).
- **Security of processing (Art. 32).** Encryption in transit/at rest, access control (JWT +
  per-user isolation), redaction, and the controls in [`security.md`](security.md).
- **International transfers (Ch. V).** Out of scope here — depends on deployment region and the
  Anthropic data-processing terms in force.

## CCPA / CPRA posture

- **Categories collected.** Identifiers (email), and "sensitive personal information" where a
  description includes SSN/financial/health data — minimized via redaction-on-write.
- **Right to delete.** Implemented (live edition self-service delete; prod via user-cascade, with a
  self-service endpoint planned).
- **Right to know / access.** Served by the run-detail read endpoints.
- **No sale / no sharing.** Firstline does not sell or "share" (cross-context behavioral advertising)
  personal information; there is no ad tech. A "Do Not Sell/Share" link is therefore not applicable,
  but a published privacy notice still is (operational/legal, below).
- **Sensitive PI use limitation.** The redaction control plus purpose limitation keep sensitive PI use
  to the service the consumer requested.

## HIPAA posture (scope honesty)

Firstline can **receive** health-related breach descriptions (e.g. "my hospital's records system was
breached, my diagnosis and member id leaked"). It is important to be precise about scope:

- **Firstline is not a HIPAA Covered Entity or Business Associate** in its current form. It is a
  consumer-facing recovery-advice tool, not a service operated *on behalf of* a covered entity, and
  there is no Business Associate Agreement (BAA) in place — with Anthropic or anyone else. **No HIPAA
  certification is claimed** (HIPAA has no certification regime in any case).
- Health information a user volunteers in a description is **not** automatically PHI in the regulatory
  sense unless Firstline were operating as/for a covered entity. We treat it as **sensitive personal
  data regardless** and apply the same safeguards.
- **Safeguards aligned to the HIPAA Security Rule (45 CFR §164.312) we already implement:** access
  control (JWT + per-user isolation), audit-relevant structured logging with request correlation,
  encryption in transit and at rest, and integrity/transmission security. Redaction-on-write further
  shrinks the amount of health-adjacent identifier data retained.
- **To be *in scope* for HIPAA** (i.e. to knowingly process PHI for a covered entity), the following
  would be prerequisites and are **out of current scope**: a signed BAA with every processor
  (including the LLM provider), formal risk analysis, workforce training, breach-notification
  procedures under the HIPAA Breach Notification Rule, and stricter retention/audit controls.

The honest stance: **out of HIPAA scope today, with several Security-Rule-aligned safeguards already
in place**; moving in-scope is a legal + operational project, not a code change.

## Control mapping (ASVS / NIST)

| Principle | Control (implemented) | OWASP ASVS | NIST 800-53 / other |
|---|---|---|---|
| Data minimization | Redaction-on-write (`redact_pii` / `redactPII`) | V8.3 Sensitive Private Data | SP 800-122 (PII de-identification) |
| No PII in logs | `RedactionFilter` on root handler | V7/V8 | LLM02 (Sensitive Info Disclosure) |
| Storage limitation | 30-day cron purge (live) | V8.3 | NIST Privacy Framework CT-DM |
| Right to erasure | `DELETE /api/runs/:id` (live); user-cascade (prod) | — | GDPR Art. 17 / CCPA |
| Encryption at rest | RDS/ElastiCache/S3 SSE-KMS | V6 Stored Cryptography | SC-28 |
| Encryption in transit | TLS everywhere; HSTS; TLS-only bucket policy | V9 Communications | SC-8 / SC-13 |
| Access control | JWT (RFC 8725) + per-user isolation | V4 Access Control | AC-3 / AC-4 |
| Confidentiality bound on LLM | Authoritative-domain allow-list; spotlighting | — | OWASP LLM01/LLM02 |

## Implemented vs. operational/legal work still required

| Item | Status |
|---|---|
| Redaction-on-write (persistence + logs) | ✅ implemented (both editions persistence; prod logs) |
| 30-day auto-delete | ✅ live edition (cron); 📋 production (schema ready, job not built) |
| Self-service erasure | ✅ live (`DELETE /api/runs/:id`); 📋 production endpoint |
| Encryption at rest / in transit | ✅ implemented (Terraform + platform TLS) |
| Access control + per-user isolation | ✅ implemented (prod) |
| **Published privacy policy / notice** | 📋 out of code scope — legal artifact required before any real launch |
| **Data Processing Agreement (DPA) / BAA** with Anthropic and other processors | 📋 out of code scope — legal/contractual |
| Explicit consent + Art. 9 condition for special-category data | 📋 out of code scope (product + legal) |
| Formal data-subject-request (DSAR) workflow | 📋 operational |
| Records of processing (Art. 30), DPIA | 📋 operational/legal |
| Postgres Row-Level Security (defense-in-depth tenancy) | 📋 planned (see threat model) |

> **Bottom line:** the *technical* privacy controls a sensitive-PII product needs are largely in code
> (redaction, retention, erasure, encryption, access control). The remaining work to actually operate
> under GDPR/CCPA/HIPAA is **legal and operational** — a real privacy policy, processor agreements
> (DPA/BAA), a consent/lawful-basis model, and DSAR procedures — and is deliberately out of scope for
> this repository.
