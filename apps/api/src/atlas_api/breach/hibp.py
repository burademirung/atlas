"""Have I Been Pwned integration.

- ``pwned_password_count`` uses the FREE, key-less Pwned Passwords range API
  (k-anonymity: only the first 5 chars of the SHA-1 leave the client).
- ``HIBPClient.breached_account`` uses the authenticated breach API (needs an
  ``hibp-api-key``).
"""

from __future__ import annotations

import hashlib

import httpx

_RANGE_URL = "https://api.pwnedpasswords.com/range/"
_BREACH_URL = "https://haveibeenpwned.com/api/v3/breachedaccount/"
_USER_AGENT = "Firstline-BreachResponse/1.0"


async def pwned_password_count(password: str, *, timeout: float = 10.0) -> int:  # noqa: ASYNC109
    """Return how many times a password appears in known breaches (0 = not found).

    k-anonymity: only the SHA-1 prefix is sent; the suffix is matched locally.
    """
    digest = hashlib.sha1(password.encode(), usedforsecurity=False).hexdigest().upper()
    prefix, suffix = digest[:5], digest[5:]
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(f"{_RANGE_URL}{prefix}", headers={"user-agent": _USER_AGENT})
        resp.raise_for_status()
    for line in resp.text.splitlines():
        tail, _, count = line.partition(":")
        if tail.strip().upper() == suffix:
            return int(count)
    return 0


class HIBPClient:
    """Authenticated breach lookup (requires an API key)."""

    def __init__(self, api_key: str, *, timeout: float = 15.0) -> None:
        self._api_key = api_key
        self._timeout = timeout

    async def breached_account(self, email: str) -> list[dict[str, object]]:
        """Return the list of breaches an email appears in ([] if none/404)."""
        headers = {"hibp-api-key": self._api_key, "user-agent": _USER_AGENT}
        params = {"truncateResponse": "false"}
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(f"{_BREACH_URL}{email}", headers=headers, params=params)
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        data = resp.json()
        return list(data) if isinstance(data, list) else []
