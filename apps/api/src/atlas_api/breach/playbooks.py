"""Load the curated breach-response playbooks (the GitHub-based knowledge store).

The Markdown files in ``playbooks/`` are the org-wide context layer: vetted,
source-cited recovery steps per leaked data type. They're injected into the
agent's writer and served by the MCP server's ``recovery_steps`` tool.
"""

from __future__ import annotations

from importlib import resources

# Canonical data-type keys -> playbook filename (without .md).
DATA_TYPES: dict[str, str] = {
    "passwords": "passwords",
    "credentials": "passwords",
    "email": "email",
    "financial": "financial",
    "bank": "financial",
    "card": "financial",
    "ssn": "ssn",
    "social_security": "ssn",
    "medical": "medical",
    "health": "medical",
    "drivers_license": "drivers_license",
    "license": "drivers_license",
    "company": "company",
    "business": "company",
}


def _read(name: str) -> str:
    # Anchor on the breach package, then navigate into the playbooks/ data dir.
    # (Anchoring on "atlas_api.breach.playbooks" would resolve to this module, not the dir.)
    return resources.files("atlas_api.breach").joinpath("playbooks", f"{name}.md").read_text()


def load_playbook(data_type: str) -> str:
    """Return the playbook Markdown for a data-type key (raises KeyError if unknown)."""
    key = data_type.strip().lower().replace(" ", "_").replace("-", "_")
    if key not in DATA_TYPES:
        raise KeyError(data_type)
    return _read(DATA_TYPES[key])


def notification_laws_doc() -> str:
    return _read("notification_laws")


def playbook_context(data_types: list[str]) -> str:
    """Concatenate the playbooks for the given data types, de-duplicated, for
    injection into the agent's context. Unknown types are skipped."""
    seen: set[str] = set()
    parts: list[str] = []
    for dt in data_types:
        try:
            key = DATA_TYPES[dt.strip().lower().replace(" ", "_").replace("-", "_")]
        except KeyError:
            continue
        if key in seen:
            continue
        seen.add(key)
        parts.append(_read(key))
    return "\n\n---\n\n".join(parts)
