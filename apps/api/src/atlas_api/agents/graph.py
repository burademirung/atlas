"""Assemble the LangGraph research graph with parallel (Send) search fan-out."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from atlas_api.agents import nodes
from atlas_api.agents.providers import SearchProvider
from atlas_api.agents.state import ResearchState
from atlas_api.config import Settings

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel
    from langgraph.graph.state import CompiledStateGraph


def _fan_out(state: ResearchState) -> list[Send]:
    """Dynamic map-reduce: one parallel searcher per sub-question."""
    question = state["question"]
    return [
        Send("search", {"question": question, "subquestion": sq})
        for sq in state.get("subquestions", [])
    ]


def build_graph(
    *, model: BaseChatModel, provider: SearchProvider, settings: Settings
) -> CompiledStateGraph[Any, Any, Any]:
    async def plan(state: ResearchState) -> dict[str, Any]:
        return await nodes.plan_node(state, model=model, settings=settings)

    async def search(state: Any) -> dict[str, Any]:
        return await nodes.search_node(state, provider=provider, settings=settings)

    async def write(state: ResearchState) -> dict[str, Any]:
        return await nodes.write_node(state, model=model)

    graph: StateGraph[Any, Any, Any, Any] = StateGraph(ResearchState)
    graph.add_node("plan", plan)
    graph.add_node("search", search)
    graph.add_node("verify", nodes.verify_node)
    graph.add_node("write", write)

    graph.add_edge(START, "plan")
    graph.add_conditional_edges("plan", _fan_out, ["search"])
    graph.add_edge("search", "verify")
    graph.add_edge("verify", "write")
    graph.add_edge("write", END)
    return graph.compile()
