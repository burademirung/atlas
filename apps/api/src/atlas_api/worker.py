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
from atlas_api.runs import streaming
from atlas_api.runs.repository import RunRepository


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
        await repo.set_status(run_id, RunStatus.planning)
        await session.commit()

    await streaming.emit(redis, run_id, "status", {"phase": "planning"})

    graph = build_graph(model=model, provider=provider, settings=settings)
    seen: set[str] = set()
    sources: list[dict[str, str]] = []
    claims: list[dict[str, object]] = []
    report = ""
    cancelled = False

    async for update in graph.astream({"question": question}, stream_mode="updates"):
        if await streaming.is_cancelled(redis, run_id):
            cancelled = True
            break
        for node, payload in update.items():
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

    final = RunStatus.cancelled if cancelled else RunStatus.done
    async with maker() as session:
        repo = RunRepository(session)
        await repo.save_results(
            run_id, status=final, report=report, sources=sources, claims=claims
        )
        await session.commit()

    await streaming.emit(
        redis, run_id, "cancelled" if cancelled else "done", {"id": run_id, "sources": len(sources)}
    )
    return {"status": final.value, "sources": len(sources)}


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
