"""Breach-response domain: the curated playbook knowledge store, the breach-law
rules table, and a Have I Been Pwned client. These power the agent's grounding
and the Firstline MCP server's tools."""

from atlas_api.breach.hibp import HIBPClient, pwned_password_count
from atlas_api.breach.laws import JURISDICTIONS, notification_law
from atlas_api.breach.playbooks import (
    DATA_TYPES,
    load_playbook,
    playbook_context,
)

__all__ = [
    "DATA_TYPES",
    "load_playbook",
    "playbook_context",
    "JURISDICTIONS",
    "notification_law",
    "HIBPClient",
    "pwned_password_count",
]
