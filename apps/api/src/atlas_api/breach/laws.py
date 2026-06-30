"""Breach-notification rules table (maintained, not hardcoded into logic).

General information, not legal advice. Deadlines/thresholds change — this is a
summary the agent and MCP server surface, always with the advice to confirm
with counsel.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Regime:
    name: str
    notify: str
    deadline: str
    source: str


JURISDICTIONS: dict[str, Regime] = {
    "us_state": Regime(
        "US state breach laws (all 50 + DC)",
        "Affected residents; often the state AG over a threshold (250–1,000+)",
        "'Without unreasonable delay'; ~20 states set a hard 30–60 days. "
        "The shortest applicable deadline governs.",
        "https://iapp.org/resources/article/state-data-breach-notification-chart",
    ),
    "gdpr": Regime(
        "GDPR (EU/UK)",
        "Supervisory authority; individuals if high risk",
        "72 hours from awareness (authority)",
        "https://gdpr-info.eu/art-33-gdpr/",
    ),
    "hipaa": Regime(
        "HIPAA (US health)",
        "Individuals; HHS; media for 500+ in a state",
        "≤60 days",
        "https://www.hhs.gov/hipaa/for-professionals/breach-notification/index.html",
    ),
    "ccpa": Regime(
        "CCPA/CPRA (California)",
        "Private right of action for unencrypted PI; $100–$750 per consumer",
        "Per CA breach statute (~30 days)",
        "https://oag.ca.gov/privacy/ccpa",
    ),
    "glba": Regime(
        "GLBA / FTC Safeguards (US financial)",
        "FTC for 500+ consumers, unencrypted customer info",
        "≤30 days",
        "https://www.ftc.gov/business-guidance/blog/2024/05/safeguards-rule-notification-requirement-now-effect",
    ),
    "pci": Regime(
        "PCI-DSS (card data)",
        "Card brands / acquirer (contractual, not law)",
        "Per card-brand rules; may require a PCI Forensic Investigator",
        "https://www.pcisecuritystandards.org/",
    ),
}

_ALIASES = {
    "state": "us_state",
    "us": "us_state",
    "eu": "gdpr",
    "uk": "gdpr",
    "health": "hipaa",
    "california": "ccpa",
    "cpra": "ccpa",
    "financial": "glba",
    "card": "pci",
}


def notification_law(jurisdiction: str) -> Regime:
    """Look up a notification regime by key or common alias (raises KeyError)."""
    key = jurisdiction.strip().lower().replace("-", "_").replace(" ", "_")
    key = _ALIASES.get(key, key)
    if key not in JURISDICTIONS:
        raise KeyError(jurisdiction)
    return JURISDICTIONS[key]
