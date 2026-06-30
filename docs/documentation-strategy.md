# Documentation Strategy

> Why this documentation set exists, what a project of this class needs, and the standards behind
> each piece. This is the rationale; the [documentation index](README.md) is the map.

## Table of contents

- [What class of project this is](#what-class-of-project-this-is)
- [The documentation model: Diátaxis](#the-documentation-model-diátaxis)
- [Architecture docs: arc42 + C4 + ADRs](#architecture-docs-arc42--c4--adrs)
- [Security documentation](#security-documentation)
- [AI-specific documentation](#ai-specific-documentation)
- [Operational documentation](#operational-documentation)
- [Project-meta documentation](#project-meta-documentation)
- [How this maps to the files in this repo](#how-this-maps-to-the-files-in-this-repo)

## What class of project this is

Firstline / Atlas sits at the intersection of four demanding domains, and each one imposes
documentation requirements:

1. **A production cloud SaaS** — needs runbooks, deployment guides, an architecture overview, and
   decision records so operators and future contributors can run and evolve it.
2. **A security incident-response product** — handles attacker-controllable content and PII, so it
   needs a threat model, a vulnerability-disclosure policy, and a defense-in-depth security overview.
3. **An agentic AI system** — an LLM plans, searches the web, and writes; this needs documentation
   of the agent/graph design, prompt and grounding strategy, and an evaluation approach.
4. **Infrastructure as code** — Terraform + Kubernetes + CI/CD need their own reference and how-to
   docs so the "apply with your own credentials" model is reproducible.

A doc set that covers only one of these (say, a README and API docs) would leave the security,
agent, and operational surfaces undocumented — exactly the surfaces that are hardest to reason
about and most expensive to get wrong.

## The documentation model: Diátaxis

We organize the docs with the [Diátaxis](https://diataxis.fr/) framework, which separates
documentation into four modes by what the reader is trying to do:

| Quadrant | Reader goal | Examples here |
|---|---|---|
| **Tutorials** (learning) | "Get me started" | [Development setup](development.md), the root Quickstart |
| **How-to guides** (tasks) | "Help me do X" | [Deployment](deployment.md), [Runbook](runbook.md), [Testing](testing.md), [Contributing](../CONTRIBUTING.md) |
| **Reference** (information) | "Tell me the facts" | [API reference](api-reference.md), [Data model](data-model.md), [`STACK.md`](../STACK.md), [`AGENTS.md`](../AGENTS.md) |
| **Explanation** (understanding) | "Help me understand why" | [Architecture](architecture.md), [Agent design](agent-design.md), [Security](security.md), [Threat model](threat-model.md), [Cost notes](cost-notes.md) |

Keeping these modes distinct is the point: a how-to guide that drifts into explanation, or a
reference that tries to teach, serves neither reader well. The [documentation index](README.md) is
grouped by these quadrants so a reader can navigate by intent.

## Architecture docs: arc42 + C4 + ADRs

[`architecture.md`](architecture.md) follows the spirit of [arc42](https://arc42.org/) (a
template for architecture documentation) and renders its structural views with the
[C4 model](https://c4model.com/): a **System Context** view, **Container** views for each edition,
a **request/data-flow sequence**, and the **data model**. C4's leveled abstraction (context →
container → component → code) lets a reader zoom in only as far as they need.

Significant, hard-to-reverse decisions are captured as
[Architecture Decision Records](https://adr.github.io/) in [`adr/`](adr/) — each records the
context, the decision, and the consequences (e.g. two editions, LangGraph, Redis Streams vs
pub/sub, KEDA, per-env Terraform state). ADRs keep the "why" from being lost to time and prevent
re-litigating settled choices.

## Security documentation

A security product earns extra documentation obligations:

- A **[threat model](threat-model.md)** enumerating assets, trust boundaries, attack paths, and
  mitigations — here organized around the [OWASP LLM Top 10](https://owasp.org/www-project-top-10-for-large-language-model-applications/)
  (prompt injection, denial-of-wallet, insecure output) plus the classic
  [OWASP Top 10](https://owasp.org/www-project-top-ten/) (SSRF, broken access control, secrets) and
  [JWT BCP RFC 8725](https://www.rfc-editor.org/rfc/rfc8725). It is **honest about status**
  (✅ enforced / 🟡 partial / 📋 planned).
- A **[security architecture overview](security.md)** describing defense-in-depth controls mapped
  to [OWASP ASVS](https://owasp.org/www-project-application-security-verification-standard/),
  [NIST SP 800-61](https://csrc.nist.gov/pubs/sp/800/61/r3/final) (incident handling), and
  [NIST SP 800-63B](https://pages.nist.gov/800-63-3/sp800-63b.html) (authentication).
- A **[`SECURITY.md`](../SECURITY.md)** vulnerability-disclosure policy at the repo root, where
  researchers expect to find it, with a private reporting channel and response expectations.

## AI-specific documentation

Agentic systems need documentation that traditional apps don't:

- **[`AGENTS.md`](../AGENTS.md)** — the [agents.md convention](https://agents.md/): a single,
  skimmable guide that tells an AI coding agent how to build, test, and safely modify the repo
  (commands, conventions, guardrails, definition of done).
- **[Agent design](agent-design.md)** — the LangGraph state graph, parallel fan-out, the grounding
  / verify node, **prompt-injection spotlighting**, the breach playbooks as a trusted context
  layer, the MCP server tools, and the evaluation approach. Prompt and grounding design are
  first-class architecture for this product and deserve their own explanation doc.
- **An evaluation approach** ([testing](testing.md) + [agent design](agent-design.md)) — because
  "does the agent produce grounded, cited, non-hallucinated output?" is a correctness property that
  unit tests alone can't assert. A dedicated eval harness with quality thresholds covers it.

## Operational documentation

Running a cloud service in production requires:

- A **[runbook](runbook.md)** — deploy, secrets, migrations, rollback, and a failure-mode table.
- A **[deployment guide](deployment.md)** — the concrete path for each edition.
- An **[observability plan](observability.md)** — logging, metrics, and tracing (OpenTelemetry +
  Prometheus), clearly separating what is implemented from what is planned, including the
  [OpenTelemetry GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
  for agent telemetry.
- **[Cost notes](cost-notes.md)** — a cost model and the levers that move the bill, which for an
  LLM product is a first-order operational concern (denial-of-wallet, model-tier selection).

## Project-meta documentation

Standard open-source hygiene, each following a recognized standard so contributors get a familiar
shape:

| File | Standard |
|---|---|
| [`CONTRIBUTING.md`](../CONTRIBUTING.md) | Conventional setup/branch/commit/PR guide + [Conventional Commits](https://www.conventionalcommits.org/) |
| [`CHANGELOG.md`](../CHANGELOG.md) | [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/) |
| [`CODE_OF_CONDUCT.md`](../CODE_OF_CONDUCT.md) | [Contributor Covenant 2.1](https://www.contributor-covenant.org/version/2/1/code_of_conduct/) |
| [`SECURITY.md`](../SECURITY.md) | Vulnerability disclosure policy |

## How this maps to the files in this repo

The [documentation index](README.md) lists every doc grouped by Diátaxis quadrant. This strategy
doc is the rationale for that structure: each quadrant is populated, the security and AI surfaces
get dedicated explanation docs, the operational surface gets how-to + reference docs, and the
hard architectural choices are frozen as ADRs. Where the product is honest about being
**code-complete but not fully wired** (e.g. some observability, RLS, the React app vs the live
vanilla SPA), the docs say "planned" rather than overclaiming — itself a documentation principle
for a trustworthy security product.
