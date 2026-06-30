from typing import Any

from fastapi import APIRouter, Depends, Header, Request, Response, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from atlas_api.config import Settings
from atlas_api.db.models import User
from atlas_api.deps import get_current_user, get_redis, get_session
from atlas_api.errors import ProblemException
from atlas_api.runs import streaming
from atlas_api.runs.repository import RunRepository
from atlas_api.runs.schemas import RunCreateIn, RunDetailOut, RunOut, SourceOut
from atlas_api.security import guardrails

router = APIRouter(prefix="/runs", tags=["runs"])


def get_arq(request: Request) -> Any:
    return request.app.state.arq


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings  # type: ignore[no-any-return]


@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=RunOut)
async def create_run(
    body: RunCreateIn,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    arq: Any = Depends(get_arq),
    redis: Redis = Depends(get_redis),
    settings: Settings = Depends(get_settings_dep),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> RunOut:
    """Submit a research run under layered denial-of-wallet controls (OWASP LLM10).

    Order: kill-switch (503) → idempotent replay → daily quota (429) → create.
    """
    guardrails.check_service_paused(settings.service_paused)

    # Idempotency-Key: a retried/double-clicked submission returns the original
    # run instead of starting (and billing) a second one.
    if idempotency_key:
        prior_id = await guardrails.idempotent_run_id(redis, user.id, idempotency_key)
        if prior_id is not None:
            existing = await RunRepository(session).get_for_user(prior_id, user.id)
            if existing is not None:
                return RunOut.model_validate(existing)

    await guardrails.enforce_daily_quota(
        redis,
        user_id=user.id,
        ip=guardrails.client_ip(request, settings.trusted_proxy_count),
        user_limit=settings.daily_run_quota,
        ip_limit=settings.daily_run_quota_ip,
    )

    run = await RunRepository(session).create(user.id, body.question, body.data_types)
    await session.commit()
    await arq.enqueue_job("run_research_job", run.id, _job_id=f"run:{run.id}")
    if idempotency_key:
        await guardrails.remember_idempotent_run(
            redis, user.id, idempotency_key, run.id, settings.idempotency_ttl_seconds
        )
    return RunOut.model_validate(run)


@router.get("", response_model=list[RunOut])
async def list_runs(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[RunOut]:
    runs = await RunRepository(session).list_for_user(user.id)
    return [RunOut.model_validate(r) for r in runs]


@router.get("/{run_id}", response_model=RunDetailOut)
async def get_run(
    run_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> RunDetailOut:
    repo = RunRepository(session)
    run = await repo.get_for_user(run_id, user.id)
    if run is None:
        raise ProblemException(404, "Run not found")
    report = await repo.report_for_run(run_id)
    sources = await repo.sources_for_run(run_id)
    return RunDetailOut(
        id=run.id,
        question=run.question,
        status=run.status,
        created_at=run.created_at,
        report=report.markdown if report else None,
        sources=[SourceOut.model_validate(s) for s in sources],
    )


@router.post("/{run_id}/cancel", status_code=status.HTTP_202_ACCEPTED)
async def cancel_run(
    run_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> Response:
    run = await RunRepository(session).get_for_user(run_id, user.id)
    if run is None:
        raise ProblemException(404, "Run not found")
    await streaming.request_cancel(redis, run_id)
    return Response(status_code=status.HTTP_202_ACCEPTED)


@router.get("/{run_id}/events")
async def run_events(
    run_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> StreamingResponse:
    run = await RunRepository(session).get_for_user(run_id, user.id)
    if run is None:
        raise ProblemException(404, "Run not found")
    last_id = request.headers.get("Last-Event-ID", "0")
    generator = streaming.sse_events(redis, run_id, last_id)
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
