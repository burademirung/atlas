# Testing

> The test strategy across both editions: pytest with testcontainers, Vitest for the Worker,
> deterministic agent tests with a stub provider, the eval harness, and how CI runs them.

## Table of contents

- [Test pyramid at a glance](#test-pyramid-at-a-glance)
- [Backend tests (pytest)](#backend-tests-pytest)
- [Deterministic agent tests](#deterministic-agent-tests)
- [The agent-quality eval harness](#the-agent-quality-eval-harness)
- [Live Worker tests (Vitest)](#live-worker-tests-vitest)
- [Web SPA tests](#web-spa-tests)
- [How CI runs everything](#how-ci-runs-everything)

## Test pyramid at a glance

| Layer | Tool | Where | Cost |
|---|---|---|---|
| Backend unit + integration | `pytest` + testcontainers | [`apps/api/tests/`](../apps/api/tests/) | free, no API calls |
| Deterministic agent graph | `pytest` + stub `SearchProvider` + fake model | `tests/test_agents.py` | free |
| Structural eval (per-PR) | `pytest` | `tests/test_evals.py` | free (stub) |
| Live agent-quality eval | `python -m atlas_api.evals` | [`evals/`](../apps/api/src/atlas_api/evals/) | **paid** (Claude + Tavily), weekly |
| Live Worker | `vitest` | [`apps/cloudflare/test/`](../apps/cloudflare/test/) | free |
| Web SPA | `vitest` | `apps/web/src/*.test.ts` | free |

## Backend tests (pytest)

```bash
cd apps/api
uv sync --all-groups
uv run pytest
```

Config (from [`pyproject.toml`](../apps/api/pyproject.toml)): `asyncio_mode = "auto"` (no per-test
`@pytest.mark.asyncio` needed), `testpaths = ["tests"]`. The dev group includes
`testcontainers[postgres,redis]`, so integration tests spin up **throwaway Postgres and Redis
containers** ([`tests/conftest.py`](../apps/api/tests/conftest.py)) — Docker must be available.

Test files cover the real surfaces:

| File | Covers |
|---|---|
| `test_auth_flow.py`, `test_tokens.py`, `test_passwords.py` | register/login/refresh/logout, JWT rotation + reuse detection, argon2id |
| `test_runs_api.py` | runs CRUD, tenant isolation, SSE wiring |
| `test_db.py`, `test_models.py` | the SQLAlchemy schema against real Postgres |
| `test_agents.py` | the LangGraph graph (deterministic) |
| `test_breach.py` | playbook loading, the law table, the HIBP k-anonymity check |
| `test_evals.py` | the structural eval over the stub provider |
| `test_config.py`, `test_health.py`, `test_smoke.py`, `test_worker.py`, `test_users.py` | config, health, smoke, worker, users |

`ruff` lint relaxations for tests are scoped in `pyproject.toml` (`S101` asserts, `S105/S106`
hardcoded test secrets allowed under `tests/**`).

## Deterministic agent tests

The agent graph is built to be testable without the network or an API key. Two seams make this work
([agent design](agent-design.md)):

- **`SearchProvider` protocol** — tests inject `StubSearchProvider`
  ([`agents/providers.py`](../apps/api/src/atlas_api/agents/providers.py)), which returns
  synthetic-but-shaped results derived from the query, so the graph runs offline and deterministically.
- **Injectable model** — `run_research(...)` and `build_graph(...)` accept a `model`, so a fake
  `BaseChatModel` can be passed to assert graph behavior (plan → search fan-out → verify → write)
  without calling Claude.

This is why the per-PR eval (`test_evals.py`) is free: it exercises the full graph through the stub.

## The agent-quality eval harness

Source: [`evals/harness.py`](../apps/api/src/atlas_api/evals/harness.py), question set
[`evals/questions.py`](../apps/api/src/atlas_api/evals/questions.py) (realistic breach situations).

The harness runs the agent over each question and scores **groundedness / no-uncited-claims /
source diversity**, then applies pass/fail thresholds (`summarize`): a case **fails** if it has any
uncited claims, retrieves zero sources, or (when `require_citations`) produces a report with no
`[n]` citation. Per-case metrics: `n_sources`, `n_claims`, `uncited_claims`, `unique_domains`,
`has_citation`, `report_len`.

Run the live eval locally (needs real keys):

```bash
cd apps/api
ANTHROPIC_API_KEY=... TAVILY_API_KEY=... \
  DATABASE_URL=postgresql+asyncpg://placeholder/db REDIS_URL=redis://localhost:6379/0 \
  JWT_SECRET=local-eval-secret-32-characters-min \
  uv run python -m atlas_api.evals
```

It prints a per-question table and exits non-zero on failure (the printed failure list, e.g.
`'<question>': N uncited claim(s)`, indicates a regression). Without `ANTHROPIC_API_KEY` it skips
and exits `0`.

## Live Worker tests (Vitest)

```bash
cd apps/cloudflare
npm install
npm test                 # vitest (config: vitest.config.ts)
npm run typecheck        # tsc --noEmit
```

Tests live in [`apps/cloudflare/test/`](../apps/cloudflare/test/) (e.g. `render.test.js` for the
SPA render logic). CI gates the Worker on `tsc --noEmit`.

## Web SPA tests

```bash
cd apps/web
npm ci
npm run build            # tsc + vite build — what CI checks
```

Unit tests exist alongside the source (`apps/web/src/api.test.ts` exercises the pure SSE frame
parser `parseSseFrame`; `markdown.test.ts` exercises the renderer). Run them with the project's
Vitest setup (`vite.config.ts`).

## How CI runs everything

[`ci.yml`](../.github/workflows/ci.yml) on every PR + push to `main`:

- **api job:** `uv sync` → `ruff check` + `ruff format --check` → `mypy src` (strict) → `pytest`
  with coverage (testcontainers Postgres/Redis) → upload coverage. The per-PR structural eval runs
  here (no API cost).
- **web job:** `npm ci` → `tsc --noEmit`.
- **security job:** Trivy filesystem + IaC config gates (fail on CRITICAL/HIGH) with SARIF upload,
  plus a gitleaks secret scan.

[`codeql.yml`](../.github/workflows/codeql.yml) runs CodeQL `security-extended` over Python and
JavaScript/TypeScript on PRs, pushes, and weekly.

[`eval.yml`](../.github/workflows/eval.yml) runs the **paid** live agent-quality eval on a weekly
schedule (Mondays 07:00 UTC) + manual `workflow_dispatch`, using the real Anthropic + Tavily keys —
deliberately **not** per-PR, to avoid per-push API spend.
</content>
