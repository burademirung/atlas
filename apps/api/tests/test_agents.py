from langchain_core.language_models.fake_chat_models import FakeListChatModel

from atlas_api.agents import StubSearchProvider, run_research
from atlas_api.config import Settings

PLAN = (
    "What are the newest battery chemistries?\n"
    "Which have the highest energy density?\n"
    "What are the safety tradeoffs?"
)
VERIFY = "Relevant sources: 1, 2, 3, 4, 5, 6"
REPORT = (
    "## Findings\nSolid-state cells lead on density [1]. Safety remains a tradeoff [2].\n\n"
    "## Sources\n[1] ... [2] ..."
)


def _settings() -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://u:p@localhost/db",
        redis_url="redis://localhost:6379/0",
        jwt_secret="s" * 32,
        max_subquestions=4,
        max_sources_per_q=2,
    )


async def test_research_graph_runs_end_to_end() -> None:
    # plan → verify → write (3 model calls per run).
    fake = FakeListChatModel(responses=[PLAN, VERIFY, REPORT])
    state = await run_research(
        "What are the newest EV battery chemistries?",
        model=fake,
        provider=StubSearchProvider(),
        settings=_settings(),
    )

    assert state["subquestions"] == [
        "What are the newest battery chemistries?",
        "Which have the highest energy density?",
        "What are the safety tradeoffs?",
    ]
    # 3 sub-questions × 2 results each, deduped by URL → 6 unique sources.
    assert len(state["sources"]) == 6
    # verifier turns every retained source into a tracked, citable claim.
    assert len(state["claims"]) == len(state["sources"])
    assert all(c["source_urls"] for c in state["claims"])
    assert state["report"] == REPORT


async def test_planner_falls_back_to_question_when_empty() -> None:
    fake = FakeListChatModel(responses=["", VERIFY, REPORT])
    state = await run_research(
        "Why is the sky blue?",
        model=fake,
        provider=StubSearchProvider(),
        settings=_settings(),
    )
    assert state["subquestions"] == ["Why is the sky blue?"]
    assert len(state["sources"]) == 2
