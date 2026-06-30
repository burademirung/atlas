import hashlib

import pytest

import atlas_api.mcp_server  # noqa: F401 — ensures the MCP server builds/imports
from atlas_api.breach import hibp
from atlas_api.breach.laws import notification_law
from atlas_api.breach.playbooks import load_playbook, playbook_context


def test_load_playbook_known_and_unknown() -> None:
    pb = load_playbook("ssn")
    assert "credit" in pb.lower()
    assert "## Sources" in pb
    # aliases resolve to the same playbook
    assert load_playbook("social_security") == pb
    with pytest.raises(KeyError):
        load_playbook("not_a_type")


def test_playbook_context_dedupes_and_skips_unknown() -> None:
    ctx = playbook_context(["passwords", "credentials", "ssn", "bogus"])
    # passwords + credentials map to one playbook; ssn is the other → 2 sections
    assert ctx.count("## Sources") == 2


def test_notification_law_lookup_and_alias() -> None:
    assert notification_law("gdpr").deadline.startswith("72 hours")
    assert notification_law("eu") == notification_law("gdpr")  # alias
    assert "60 days" in notification_law("hipaa").deadline
    with pytest.raises(KeyError):
        notification_law("narnia")


async def test_pwned_password_count(monkeypatch: pytest.MonkeyPatch) -> None:
    pwd = "hunter2hunter2"
    digest = hashlib.sha1(pwd.encode(), usedforsecurity=False).hexdigest().upper()
    suffix = digest[5:]
    body = f"00000000000000000000000000000000000:1\r\n{suffix}:1234\r\nABC:7"

    class _Resp:
        text = body

        def raise_for_status(self) -> None:
            return None

    class _Client:
        def __init__(self, *a: object, **k: object) -> None:
            pass

        async def __aenter__(self) -> "_Client":
            return self

        async def __aexit__(self, *a: object) -> bool:
            return False

        async def get(self, *a: object, **k: object) -> _Resp:
            return _Resp()

    monkeypatch.setattr(hibp.httpx, "AsyncClient", _Client)
    assert await hibp.pwned_password_count(pwd) == 1234
