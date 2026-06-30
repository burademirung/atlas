"""Targeted tests lifting coverage of small, previously under-tested modules."""

from __future__ import annotations

import hashlib
from typing import Any

import pytest

from atlas_api import cli
from atlas_api.agents.models import build_chat_model
from atlas_api.agents.providers import StubSearchProvider, TavilySearchProvider
from atlas_api.agents.runner import default_provider
from atlas_api.breach import hibp
from atlas_api.config import Settings


def _settings(**extra: Any) -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://u:p@localhost/db",
        redis_url="redis://localhost:6379/0",
        jwt_secret="s" * 32,
        **extra,
    )


def test_cli_migrate_invokes_alembic(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, Any] = {}

    def _call(argv: list[str]) -> int:
        calls["argv"] = argv
        return 0

    monkeypatch.setattr(cli.subprocess, "call", _call)
    with pytest.raises(SystemExit) as ei:
        cli.migrate()
    assert ei.value.code == 0
    assert calls["argv"] == ["alembic", "upgrade", "head"]


def test_build_chat_model_requires_key() -> None:
    with pytest.raises(ValueError, match="anthropic_api_key"):
        build_chat_model(_settings())


def test_build_chat_model_with_key() -> None:
    model = build_chat_model(_settings(anthropic_api_key="sk-test", research_model="claude-x"))
    assert model is not None


def test_default_provider_selects_tavily_or_stub() -> None:
    assert isinstance(default_provider(_settings(tavily_api_key="tvly-x")), TavilySearchProvider)
    assert isinstance(default_provider(_settings()), StubSearchProvider)


class _Resp:
    def __init__(self, *, text: str = "", status: int = 200, payload: Any = None) -> None:
        self.text = text
        self.status_code = status
        self._payload = payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> Any:
        return self._payload


def _fake_client(resp: _Resp) -> type:
    class _Client:
        def __init__(self, *a: object, **k: object) -> None:
            pass

        async def __aenter__(self) -> _Client:
            return self

        async def __aexit__(self, *a: object) -> bool:
            return False

        async def get(self, *a: object, **k: object) -> _Resp:
            return resp

        async def post(self, *a: object, **k: object) -> _Resp:
            return resp

    return _Client


async def test_pwned_password_not_found_returns_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    digest = hashlib.sha1(b"whatever", usedforsecurity=False).hexdigest().upper()
    # Body deliberately omits our suffix -> count 0.
    body = f"{digest[5:][:-1]}A:99\r\nDEADBEEF:5"
    monkeypatch.setattr(hibp.httpx, "AsyncClient", _fake_client(_Resp(text=body)))
    assert await hibp.pwned_password_count("whatever") == 0


async def test_hibp_client_breached_account(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = [{"Name": "Acme"}, {"Name": "Beta"}]
    monkeypatch.setattr(hibp.httpx, "AsyncClient", _fake_client(_Resp(payload=payload)))
    client = hibp.HIBPClient("key")
    assert await client.breached_account("a@b.com") == payload


async def test_hibp_client_404_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hibp.httpx, "AsyncClient", _fake_client(_Resp(status=404)))
    client = hibp.HIBPClient("key")
    assert await client.breached_account("missing@b.com") == []


async def test_tavily_provider_parses_results(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "results": [
            {"url": "https://x.test/a", "title": "A", "raw_content": "body a"},
            {"url": "https://x.test/b", "content": "body b"},
        ]
    }
    monkeypatch.setattr(
        "atlas_api.agents.providers.httpx.AsyncClient", _fake_client(_Resp(payload=payload))
    )
    provider = TavilySearchProvider("tvly-x")
    results = await provider.search("query", 5)
    assert [r.url for r in results] == ["https://x.test/a", "https://x.test/b"]
    assert results[0].content == "body a"
    assert results[1].title == "https://x.test/b"  # falls back to url when title missing


async def test_evals_main_skips_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("JWT_SECRET", "x" * 32)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from atlas_api import config
    from atlas_api.evals import __main__ as evals_main

    config.get_settings.cache_clear()
    assert await evals_main._main() == 0
    config.get_settings.cache_clear()
