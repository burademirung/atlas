"""Agentic research engine — a LangGraph multi-agent graph driven by Claude.

Graph shape:  plan ─▶ [search ×N in parallel] ─▶ verify ─▶ write

- plan:    Claude decomposes the question into focused sub-questions.
- search:  each sub-question fans out (LangGraph Send) to a searcher that calls
           a pluggable SearchProvider; results merge + dedupe into shared state.
- verify:  grounds the answer — every retained source becomes a tracked claim.
- write:   Claude composes a cited Markdown report from the verified sources.

The model and search provider are injected, so the whole graph runs
deterministically in tests with a fake chat model and a stub provider.
"""

from atlas_api.agents.graph import build_graph
from atlas_api.agents.providers import (
    SearchProvider,
    SearchResult,
    StubSearchProvider,
    TavilySearchProvider,
)
from atlas_api.agents.runner import run_research
from atlas_api.agents.state import Claim, ResearchState, Source

__all__ = [
    "build_graph",
    "run_research",
    "ResearchState",
    "Source",
    "Claim",
    "SearchProvider",
    "SearchResult",
    "StubSearchProvider",
    "TavilySearchProvider",
]
