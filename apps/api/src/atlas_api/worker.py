"""arq worker: runs the LangGraph research graph, streams progress, persists results.

Run with:  ``arq atlas_api.worker.WorkerSettings``  (this is the command the Helm
chart's worker Deployment uses).
"""

from __future__ import annotations

from typing import Any

from arq.connections import RedisSettings

from atlas_api.agents.graph import build_graph
from atlas_api.agents.runner import default_provider
from atlas_api.config import get_settings
from atlas_api.db.engine import create_engine, session_factory
from atlas_api.db.models import RunStatus
from atlas_api.observability import metrics
from atlas_api.runs import streaming
from atlas_api.runs.repository import RunRepository
from atlas_api.security.guardrails import over_token_cap


def _data_types(config: dict[str, object] | None) -> list[str]:
    """Pull the persisted ``data_types`` list off a run's JSONB config, safely."""
    if not config:
        return []
    raw = config.get("data_types")
    if isinstance(raw, list):
        return [str(item) for item in raw]
    return []


async def run_research_job(ctx: dict[str, Any], run_id: int) -> dict[str, Any]:
    """Execute one research run: plan → search → verify → write, streaming events."""
    redis = ctx["redis"]
    maker = ctx["sessionmaker"]
    settings = ctx["settings"]
    model = ctx.get("model") or _build_model(settings)
    provider = ctx.get("provider") or default_provider(settings)

    async with maker() as session:
        repo = RunRepository(session)
        run = await repo.get(run_id)
        if run is None:
            return {"status": "missing"}
        question = run.question
        data_types = _data_types(run.config)
        await repo.set_status(run_id, RunStatus.planning)
        await session.commit()

    await streaming.emit(redis, run_id, "status", {"phase": "planning"})

    graph = build_graph(model=model, provider=provider, settings=settings)
    seen: set[str] = set()
    sources: list[dict[str, str]] = []
    claims: list[dict[str, object]] = []
    report = ""
    tokens = 0
    cancelled = False
    truncated = False

    async for update in graph.astream(
        {"question": question, "data_types": data_types}, stream_mode="updates"
    ):
        if await streaming.is_cancelled(redis, run_id):
            cancelled = True
            break
        for node, payload in update.items():
            tokens += int(payload.get("tokens", 0) or 0)
            if node == "plan":
                await streaming.emit(redis, run_id, "status", {"phase": "searching"})
                await streaming.emit(
                    redis, run_id, "plan", {"subquestions": payload.get("subquestions", [])}
                )
            elif node == "search":
                for s in payload.get("sources", []):
                    if s["url"] in seen:
                        continue
                    seen.add(s["url"])
                    sources.append(dict(s))
                    await streaming.emit(
                        redis, run_id, "source", {"url": s["url"], "title": s["title"]}
                    )
            elif node == "verify":
                claims = [dict(c) for c in payload.get("claims", [])]
                await streaming.emit(redis, run_id, "status", {"phase": "verifying"})
            elif node == "write":
                report = payload.get("report", "")
                await streaming.emit(redis, run_id, "status", {"phase": "writing"})
                await streaming.emit(redis, run_id, "report", {"markdown": report})
        # Per-run denial-of-wallet ceiling: stop spending once the cumulative
        # token budget is exhausted (OWASP LLM10 / Unbounded Consumption).
        if over_token_cap(tokens, settings.max_run_tokens):
            truncated = True
            break

    if cancelled:
        final = RunStatus.cancelled
    elif truncated:
        final = RunStatus.truncated
    else:
        final = RunStatus.done
    async with maker() as session:
        repo = RunRepository(session)
        await repo.save_results(
            run_id, status=final, report=report, sources=sources, claims=claims, tokens=tokens
        )
        await session.commit()

    event = "done"
    if cancelled:
        event = "cancelled"
    elif truncated:
        event = "truncated"
    await streaming.emit(
        redis, run_id, event, {"id": run_id, "sources": len(sources), "tokens": tokens}
    )
    metrics.record_run(final.value)
    return {"status": final.value, "sources": len(sources), "tokens": tokens}


def _build_model(settings: Any) -> Any:
    from atlas_api.agents.models import build_chat_model

    return build_chat_model(settings)


async def on_startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    ctx["settings"] = settings
    ctx["engine"] = engine
    ctx["sessionmaker"] = session_factory(engine)
    ctx["provider"] = default_provider(settings)
    if settings.anthropic_api_key:
        ctx["model"] = _build_model(settings)


async def on_shutdown(ctx: dict[str, Any]) -> None:
    engine = ctx.get("engine")
    if engine is not None:
        await engine.dispose()


def _redis_settings() -> RedisSettings:
    try:
        return RedisSettings.from_dsn(get_settings().redis_url)
    except Exception:
        # No environment (e.g. during tests/import) — arq falls back to defaults.
        return RedisSettings()


class WorkerSettings:
    functions = [run_research_job]
    on_startup = on_startup
    on_shutdown = on_shutdown
    redis_settings = _redis_settings()
    allow_abort_jobs = True
    max_jobs = 10
