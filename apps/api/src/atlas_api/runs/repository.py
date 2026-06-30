"""Persistence for research runs, sources, claims, and reports."""

from __future__ import annotations

import hashlib

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from atlas_api.db.models import Claim, ClaimSource, Report, ResearchRun, RunStatus, Source
from atlas_api.security.redaction import redact_pii


def _url_hash(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:64]


class RunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, user_id: int, question: str, data_types: list[str] | None = None
    ) -> ResearchRun:
        # PII is stripped *before* the breach description is persisted: the
        # stored question drives advice, which never needs the literal
        # identifier (OWASP ASVS V8.3, OWASP LLM02, NIST SP 800-122).
        config: dict[str, object] = {"data_types": list(data_types or [])}
        run = ResearchRun(
            user_id=user_id,
            question=redact_pii(question),
            status=RunStatus.queued,
            config=config,
        )
        self._session.add(run)
        await self._session.flush()
        return run

    async def get(self, run_id: int) -> ResearchRun | None:
        return await self._session.get(ResearchRun, run_id)

    async def get_for_user(self, run_id: int, user_id: int) -> ResearchRun | None:
        run = await self._session.get(ResearchRun, run_id)
        if run is None or run.user_id != user_id:
            return None
        return run

    async def list_for_user(self, user_id: int, limit: int = 25) -> list[ResearchRun]:
        result = await self._session.execute(
            select(ResearchRun)
            .where(ResearchRun.user_id == user_id)
            .order_by(ResearchRun.created_at.desc(), ResearchRun.id.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def sources_for_run(self, run_id: int) -> list[Source]:
        result = await self._session.execute(select(Source).where(Source.run_id == run_id))
        return list(result.scalars().all())

    async def report_for_run(self, run_id: int) -> Report | None:
        result = await self._session.execute(select(Report).where(Report.run_id == run_id))
        return result.scalars().first()

    async def set_status(self, run_id: int, status: RunStatus) -> None:
        run = await self._session.get(ResearchRun, run_id)
        if run is not None:
            run.status = status

    async def save_results(
        self,
        run_id: int,
        *,
        status: RunStatus,
        report: str,
        sources: list[dict[str, str]],
        claims: list[dict[str, object]],
        tokens: int = 0,
    ) -> None:
        run = await self._session.get(ResearchRun, run_id)
        if run is None:
            return
        run.status = status
        run.tokens_used = tokens

        url_to_id: dict[str, int] = {}
        for s in sources:
            url = s["url"]
            if url in url_to_id:
                continue
            src = Source(
                run_id=run_id,
                url=url,
                url_hash=_url_hash(url),
                title=s.get("title"),
                snippet=(s.get("content") or "")[:500],
            )
            self._session.add(src)
            await self._session.flush()
            url_to_id[url] = src.id

        self._session.add(
            Report(run_id=run_id, markdown=report, truncated=status == RunStatus.truncated)
        )

        for c in claims:
            claim = Claim(run_id=run_id, text=str(c.get("text", "")))
            self._session.add(claim)
            await self._session.flush()
            urls = c.get("source_urls") or []
            if not isinstance(urls, list):
                continue
            for url in urls:
                sid = url_to_id.get(str(url))
                if sid is not None:
                    self._session.add(ClaimSource(claim_id=claim.id, source_id=sid))
