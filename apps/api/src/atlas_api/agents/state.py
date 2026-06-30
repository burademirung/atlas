"""Graph state + reducers for the research agent."""

from typing import Annotated, TypedDict


class Source(TypedDict):
    url: str
    title: str
    content: str


class Claim(TypedDict):
    text: str
    source_urls: list[str]


def merge_sources(existing: list[Source], new: list[Source]) -> list[Source]:
    """Reducer: append new sources, de-duplicating by URL.

    Parallel searcher branches all return ``sources``; LangGraph runs this to
    fold them into one list without duplicates.
    """
    seen = {s["url"] for s in existing}
    merged = list(existing)
    for s in new:
        if s["url"] in seen:
            continue
        seen.add(s["url"])
        merged.append(s)
    return merged


class ResearchState(TypedDict, total=False):
    question: str
    data_types: list[str]
    subquestions: list[str]
    sources: Annotated[list[Source], merge_sources]
    claims: list[Claim]
    report: str


class SearchTask(TypedDict):
    """Payload carried on each parallel Send to the searcher node."""

    question: str
    subquestion: str
