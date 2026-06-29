import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from atlas_api.db.models import ResearchRun, RunStatus, Source, User


async def test_create_user_and_run(db_session: AsyncSession) -> None:
    user = User(email="a@example.com", password_hash="x")
    db_session.add(user)
    await db_session.flush()
    run = ResearchRun(user_id=user.id, question="why is the sky blue?")
    db_session.add(run)
    await db_session.flush()
    assert run.status == RunStatus.queued
    fetched = (await db_session.execute(select(ResearchRun))).scalars().first()
    assert fetched is not None
    assert fetched.question == "why is the sky blue?"


async def test_source_url_hash_unique_per_run(db_session: AsyncSession) -> None:
    user = User(email="b@example.com", password_hash="x")
    db_session.add(user)
    await db_session.flush()
    run = ResearchRun(user_id=user.id, question="q")
    db_session.add(run)
    await db_session.flush()
    db_session.add(Source(run_id=run.id, url="http://a", url_hash="h1", title="t"))
    db_session.add(Source(run_id=run.id, url="http://a2", url_hash="h1", title="t"))
    with pytest.raises(IntegrityError):
        await db_session.flush()
