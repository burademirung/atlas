"""Agent graph nodes: plan, search, verify, write."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from langchain_core.messages import HumanMessage, SystemMessage

from atlas_api.agents.providers import SearchProvider
from atlas_api.agents.state import Claim, ResearchState, SearchTask, Source
from atlas_api.config import Settings

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

_PLAN_SYSTEM = (
    "You are a research planner. Break the question into focused, factual sub-questions "
    "that together fully cover it. Output one sub-question per line, no numbering or prose."
)
_WRITE_SYSTEM = (
    "You are a meticulous research writer. Using ONLY the numbered sources provided, write a "
    "clear Markdown report that answers the question. Cite claims inline with [n] matching the "
    "source numbers. Do not invent sources. End with a '## Sources' list."
)


def _as_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [p.get("text", "") if isinstance(p, dict) else str(p) for p in content]
        return "".join(parts)
    return str(content)


async def plan_node(
    state: ResearchState, *, model: BaseChatModel, settings: Settings
) -> dict[str, list[str]]:
    question = state["question"]
    msg = await model.ainvoke(
        [SystemMessage(content=_PLAN_SYSTEM), HumanMessage(content=question)]
    )
    lines = [
        re.sub(r"^\s*(?:\d+[.)]|[-*•])\s*", "", ln).strip()
        for ln in _as_text(msg.content).splitlines()
    ]
    subqs = [ln for ln in lines if len(ln) > 8][: settings.max_subquestions]
    return {"subquestions": subqs or [question]}


async def search_node(
    task: SearchTask, *, provider: SearchProvider, settings: Settings
) -> dict[str, list[Source]]:
    results = await provider.search(task["subquestion"], settings.max_sources_per_q)
    sources: list[Source] = [
        Source(url=r.url, title=r.title, content=r.content) for r in results if r.url
    ]
    return {"sources": sources}


def verify_node(state: ResearchState) -> dict[str, list[Claim]]:
    """Grounding step: each retained source becomes a tracked, citable claim.

    (The production variant runs an LLM entailment check that the cited source
    text actually supports each claim; this code-only pass keeps the graph
    deterministic and is the seam where that check plugs in.)
    """
    claims = [
        Claim(text=s["title"], source_urls=[s["url"]]) for s in state.get("sources", [])
    ]
    return {"claims": claims}


async def write_node(state: ResearchState, *, model: BaseChatModel) -> dict[str, str]:
    sources = state.get("sources", [])
    block = "\n\n".join(
        f"[{i + 1}] {s['title']} — {s['url']}\n{s['content'][:600]}"
        for i, s in enumerate(sources)
    )
    user = (
        f"Question: {state['question']}\n\nSOURCES:\n{block}\n\nWrite the cited report now."
    )
    msg = await model.ainvoke([SystemMessage(content=_WRITE_SYSTEM), HumanMessage(content=user)])
    return {"report": _as_text(msg.content)}
