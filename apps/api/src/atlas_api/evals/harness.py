"""Run the research agent over a question set and score quality."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from atlas_api.agents.providers import SearchProvider
from atlas_api.agents.runner import run_research
from atlas_api.config import Settings

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

_CITATION = re.compile(r"\[\d+\]")


@dataclass
class CaseResult:
    question: str
    n_sources: int
    n_claims: int
    uncited_claims: int  # claims with no backing source — must be 0
    unique_domains: int
    has_citation: bool  # report references at least one [n]
    report_len: int


@dataclass
class EvalSummary:
    cases: list[CaseResult]
    passed: bool
    failures: list[str]


async def evaluate_one(
    question: str,
    *,
    model: BaseChatModel,
    provider: SearchProvider,
    settings: Settings,
) -> CaseResult:
    state = await run_research(question, model=model, provider=provider, settings=settings)
    sources = state.get("sources", [])
    claims = state.get("claims", [])
    report = state.get("report", "") or ""
    uncited = sum(1 for c in claims if not c.get("source_urls"))
    domains = {urlparse(s["url"]).netloc for s in sources if s.get("url")}
    return CaseResult(
        question=question,
        n_sources=len(sources),
        n_claims=len(claims),
        uncited_claims=uncited,
        unique_domains=len(domains),
        has_citation=bool(_CITATION.search(report)),
        report_len=len(report),
    )


async def run_eval(
    questions: list[str],
    *,
    model: BaseChatModel,
    provider: SearchProvider,
    settings: Settings,
) -> list[CaseResult]:
    results: list[CaseResult] = []
    for q in questions:
        results.append(await evaluate_one(q, model=model, provider=provider, settings=settings))
    return results


def summarize(cases: list[CaseResult], *, require_citations: bool) -> EvalSummary:
    """Apply quality thresholds and return a pass/fail summary."""
    failures: list[str] = []
    for c in cases:
        if c.uncited_claims > 0:
            failures.append(f"{c.question!r}: {c.uncited_claims} uncited claim(s)")
        if c.n_sources < 1:
            failures.append(f"{c.question!r}: no sources retrieved")
        if require_citations and not c.has_citation:
            failures.append(f"{c.question!r}: report has no [n] citations")
    return EvalSummary(cases=cases, passed=not failures, failures=failures)
