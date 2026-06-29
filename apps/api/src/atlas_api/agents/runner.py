"""Convenience runner that builds and invokes the research graph."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from atlas_api.agents.graph import build_graph
from atlas_api.agents.providers import (
    SearchProvider,
    StubSearchProvider,
    TavilySearchProvider,
)
from atlas_api.agents.state import ResearchState
from atlas_api.config import Settings, get_settings

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel


def default_provider(settings: Settings) -> SearchProvider:
    if settings.tavily_api_key:
        return TavilySearchProvider(settings.tavily_api_key)
    return StubSearchProvider()


async def run_research(
    question: str,
    *,
    model: BaseChatModel | None = None,
    provider: SearchProvider | None = None,
    settings: Settings | None = None,
) -> ResearchState:
    settings = settings or get_settings()
    if model is None:
        from atlas_api.agents.models import build_chat_model

        model = build_chat_model(settings)
    provider = provider or default_provider(settings)
    graph = build_graph(model=model, provider=provider, settings=settings)
    result = await graph.ainvoke({"question": question})
    return cast(ResearchState, result)
