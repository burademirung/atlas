"""Firstline MCP server — exposes breach-response tools over the Model Context
Protocol so an agent (or Claude Code / any MCP client) can call them.

Run:  ``python -m atlas_api.mcp_server``  (stdio transport).

Tools:
- list_data_types()                      → the playbook data-type keys
- recovery_steps(data_type)              → the curated playbook for a leaked data type
- breach_notification_law(jurisdiction)  → notification obligation summary (org)
- pwned_password_count(password)         → times a password appears in breaches (free, k-anonymity)
- check_email_breaches(email)            → breaches an email appears in (needs HIBP_API_KEY)
"""

from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

from atlas_api.breach import (
    DATA_TYPES,
    HIBPClient,
    load_playbook,
    notification_law,
    pwned_password_count,
)

mcp = FastMCP("firstline")

_DISCLAIMER = "General guidance, not legal or financial advice."


@mcp.tool()
def list_data_types() -> list[str]:
    """List the leaked-data-type keys that have a recovery playbook."""
    return sorted(set(DATA_TYPES.values()))


@mcp.tool()
def recovery_steps(data_type: str) -> str:
    """Return the curated, source-cited recovery playbook for a leaked data type
    (e.g. 'passwords', 'ssn', 'email', 'financial', 'medical', 'company')."""
    try:
        return load_playbook(data_type)
    except KeyError:
        valid = ", ".join(sorted(set(DATA_TYPES.values())))
        return f"Unknown data type '{data_type}'. Try one of: {valid}."


@mcp.tool()
def breach_notification_law(jurisdiction: str) -> str:
    """Summarize an organization's breach-notification obligation for a regime
    (e.g. 'us_state', 'gdpr', 'hipaa', 'ccpa', 'glba', 'pci'). {disclaimer}"""
    try:
        r = notification_law(jurisdiction)
    except KeyError:
        return (
            f"Unknown jurisdiction '{jurisdiction}'. "
            "Try: us_state, gdpr, hipaa, ccpa, glba, pci."
        )
    return (
        f"**{r.name}**\nWho to notify: {r.notify}\nDeadline: {r.deadline}\n"
        f"Source: {r.source}\n\n{_DISCLAIMER} Confirm with counsel."
    )


@mcp.tool()
async def pwned_password(password: str) -> str:
    """Check how many times a password appears in known breaches (0 = not found).
    Uses k-anonymity — only a hash prefix leaves your machine."""
    count = await pwned_password_count(password)
    if count == 0:
        return "Not found in known breaches. Still use a unique password + MFA."
    return f"Found {count:,} times in breaches — do not use this password anywhere."


@mcp.tool()
async def check_email_breaches(email: str) -> str:
    """List the known breaches an email address appears in (needs HIBP_API_KEY)."""
    key = os.environ.get("HIBP_API_KEY")
    if not key:
        return "Email breach lookup needs HIBP_API_KEY. Self-check at https://haveibeenpwned.com/"
    breaches = await HIBPClient(key).breached_account(email)
    if not breaches:
        return "No known breaches for that address."
    names = ", ".join(str(b.get("Name", "?")) for b in breaches[:25])
    return f"Appears in {len(breaches)} breach(es): {names}"


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
