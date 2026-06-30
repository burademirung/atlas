from langchain_core.language_models.fake_chat_models import FakeListChatModel

from atlas_api.agents import StubSearchProvider
from atlas_api.config import Settings
from atlas_api.evals.harness import run_eval, summarize

# fake responses cycle: plan, verify, report, ... (3 model calls per question)
PLAN = "Sub-question one?\nSub-question two?"
VERIFY = "Relevant: 1, 2, 3, 4"
REPORT = "## Answer\nGrounded finding [1]. Another point [2].\n\n## Sources\n[1] ... [2] ..."


def _settings() -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://u:p@localhost/db",
        redis_url="redis://localhost:6379/0",
        jwt_secret="s" * 32,
        max_subquestions=4,
        max_sources_per_q=2,
    )


async def test_eval_harness_scores_and_enforces_invariants() -> None:
    questions = ["What is X?", "How does Y work?"]
    fake = FakeListChatModel(responses=[PLAN, VERIFY, REPORT])  # cycles across calls
    cases = await run_eval(
        questions, model=fake, provider=StubSearchProvider(), settings=_settings()
    )
    assert len(cases) == 2
    for c in cases:
        assert c.n_sources >= 1
        assert c.uncited_claims == 0  # the no-uncited-claims invariant holds
        assert c.has_citation  # REPORT contains [1]/[2]

    summary = summarize(cases, require_citations=True)
    assert summary.passed
    assert summary.failures == []


async def test_summary_flags_missing_citations() -> None:
    fake = FakeListChatModel(responses=["Sub-q?", VERIFY, "No citations here."])
    cases = await run_eval(
        ["Q?"], model=fake, provider=StubSearchProvider(), settings=_settings()
    )
    summary = summarize(cases, require_citations=True)
    assert not summary.passed
    assert any("citation" in f for f in summary.failures)
