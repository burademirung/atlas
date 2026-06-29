"""Pluggable web-search providers for the research agent.

The graph depends only on the ``SearchProvider`` protocol, so adapters can be
swapped (Tavily in production, a deterministic stub in tests/offline).
"""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import httpx


@dataclass(slots=True)
class SearchResult:
    url: str
    title: str
    content: str


@runtime_checkable
class SearchProvider(Protocol):
    async def search(self, query: str, max_results: int) -> list[SearchResult]: ...


class StubSearchProvider:
    """Deterministic provider for tests and offline/local runs.

    Returns synthetic-but-shaped results derived from the query, so the graph
    can be exercised end-to-end without any network or API key.
    """

    async def search(self, query: str, max_results: int) -> list[SearchResult]:
        slug = query.lower().strip().replace(" ", "-")[:48] or "topic"
        return [
            SearchResult(
                url=f"https://example.org/{slug}/{i}",
                title=f"{query.strip().capitalize()} — reference {i + 1}",
                content=(
                    f"A grounded passage about '{query.strip()}'. Source {i + 1} of "
                    f"{max_results}. Used by the verifier to back claims with citations."
                ),
            )
            for i in range(max_results)
        ]


class TavilySearchProvider:
    """Real provider backed by the Tavily search+extract API."""

    _URL = "https://api.tavily.com/search"

    def __init__(self, api_key: str, *, timeout: float = 20.0) -> None:
        self._api_key = api_key
        self._timeout = timeout

    async def search(self, query: str, max_results: int) -> list[SearchResult]:
        payload = {
            "api_key": self._api_key,
            "query": query,
            "max_results": max_results,
            "include_raw_content": True,
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(self._URL, json=payload)
            resp.raise_for_status()
            data = resp.json()
        results: list[SearchResult] = []
        for item in data.get("results", [])[:max_results]:
            results.append(
                SearchResult(
                    url=item.get("url", ""),
                    title=item.get("title", item.get("url", "")),
                    content=(item.get("raw_content") or item.get("content") or "")[:1500],
                )
            )
        return results
