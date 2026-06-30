# ADR 0002 — LangGraph for the multi-agent research graph

**Status:** Accepted · 2026-06-29

## Context

The production agent must decompose a question, run **parallel** web searches, ground claims in
sources, and write a cited report — with **durable execution** (crash-resume), **cooperative
cancellation**, bounded fan-out, and per-node error isolation so one failed search doesn't kill the
run. We needed an orchestration model that makes the agent graph explicit and testable, rather than
an opaque prompt loop.

## Decision

Use **LangGraph** (`StateGraph`) driven by **Claude** via `langchain-anthropic`. The compiled graph
([`apps/api/src/atlas_api/agents/graph.py`](../../apps/api/src/atlas_api/agents/graph.py)) is:

```
plan ─► [search ×N via Send] ─► verify ─► write
```

- **Parallel fan-out** via LangGraph's **`Send` API** (dynamic map-reduce): one `search` branch per
  sub-question, bounded by `max_subquestions`.
- **Pluggable search** behind a `SearchProvider` protocol (Tavily in production, a deterministic
  stub for tests/offline) — so the graph is testable without network or API keys.
- **Per-node resilience:** each searcher returns its own results; a failure degrades that branch
  rather than aborting the superstep.
- The graph is compiled and driven by the **arq worker**, which streams `status`/`plan`/`source`/
  `report` events to Redis Streams as nodes complete.

## Consequences

- **+** The agent is an explicit, inspectable graph — easy to test deterministically (stub provider
  + `tests/test_agents.py`) and to instrument per node.
- **+** `Send` gives true parallel search with a hard fan-out bound (cost control).
- **+** Clean seam for the planned upgrades: LLM **entailment verification**, a **critic re-loop**,
  structured outputs, and a **Postgres checkpointer** for crash-resume all plug into existing nodes.
- **−** Today's `verify` node is a deterministic claim-tracking pass, not yet the LLM entailment
  check the spec describes — groundedness is structural, not semantic, until that lands.
- **−** The **critic / bounded re-loop**, durable Postgres checkpointer, and per-token streaming
  (present in the live edition) are specified but not yet in the production graph.
- **−** Adds a heavier dependency surface (`langgraph`, `langchain-core`, `langchain-anthropic`)
  than hand-rolled orchestration.
