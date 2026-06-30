"""PII redaction for breach-response inputs and logs.

Firstline ingests free-text descriptions of data breaches, which frequently
contain the very identifiers that were leaked (SSNs, card numbers, emails,
phone numbers). We mask those before they are persisted or logged.

Standards / rationale:
  * OWASP ASVS v4 V8.3 (Sensitive Private Data) — minimize storage of personal
    data and prevent it leaking into logs.
  * OWASP LLM Top-10 LLM02 (Sensitive Information Disclosure) — strip PII from
    text that may be echoed back by, or stored alongside, an LLM workflow.
  * NIST SP 800-122 — protect PII confidentiality through de-identification.

Trade-off (documented deliberately): recovery *advice* almost never needs the
literal identifier. Knowing that "an SSN was exposed" is enough to recommend a
credit freeze; the nine digits themselves add no value to the guidance while
adding breach-blast-radius and compliance scope. We therefore redact eagerly
and accept that the raw value is irrecoverable from our store. Redaction is a
defense-in-depth control, not a guarantee — novel formats may slip through, so
it complements (does not replace) access control and encryption at rest.
"""

from __future__ import annotations

import logging
import re

SSN_TOKEN = "[redacted-ssn]"  # noqa: S105 - redaction placeholder, not a secret
CC_TOKEN = "[redacted-cc]"  # noqa: S105 - redaction placeholder, not a secret
EMAIL_TOKEN = "[redacted-email]"  # noqa: S105 - redaction placeholder, not a secret
PHONE_TOKEN = "[redacted-phone]"  # noqa: S105 - redaction placeholder, not a secret

# Email — handled first so digits inside an address are not re-matched as SSN/CC.
# ReDoS-safe: '.' is the fixed separator between label runs and is NOT in the
# repeated class, so there is no ambiguous backtracking (CodeQL py/polynomial-redos).
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)+")
# US SSN in its canonical dashed/spaced 3-2-4 grouping.
_SSN_RE = re.compile(r"\b\d{3}[-\s]\d{2}[-\s]\d{4}\b")
# Credit-card-like: 13-19 digits, optionally separated by spaces or dashes.
# Anchored on a leading/trailing digit so a separator can't be eaten off the end.
_CC_RE = re.compile(r"\b\d(?:[ -]?\d){12,18}\b")
# US phone numbers (10 significant digits, optional +1 / parens / separators).
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}(?!\d)")


def _luhn_ok(digits: str) -> bool:
    """Return True if ``digits`` passes the Luhn checksum used by payment cards."""
    total = 0
    for idx, ch in enumerate(reversed(digits)):
        d = ord(ch) - 48
        if idx % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _redact_cc(match: re.Match[str]) -> str:
    raw = match.group(0)
    digits = re.sub(r"\D", "", raw)
    # Only mask when it both has a card-length digit count and passes Luhn; this
    # keeps the matcher from eating unrelated long digit runs (Luhn-check is the
    # "optional" precision filter called for in the spec).
    if 13 <= len(digits) <= 19 and _luhn_ok(digits):
        return CC_TOKEN
    return raw


def redact_pii(text: str) -> str:
    """Mask US SSNs, payment-card numbers, emails and phone numbers in ``text``.

    Substitution order is deliberate: emails first (their digits must not be
    re-read as SSN/CC), then the dashed SSN grouping, then Luhn-validated card
    runs, then phone numbers. Returns the input unchanged when it holds no PII.
    """
    if not text:
        return text
    text = _EMAIL_RE.sub(EMAIL_TOKEN, text)
    text = _SSN_RE.sub(SSN_TOKEN, text)
    text = _CC_RE.sub(_redact_cc, text)
    text = _PHONE_RE.sub(PHONE_TOKEN, text)
    return text


class RedactionFilter(logging.Filter):
    """Logging filter that scrubs PII from every log record before it is emitted.

    Installed on the root handler so no breach description, stack-trace, or
    interpolated argument can carry raw identifiers into log sinks
    (OWASP ASVS V7/V8, OWASP LLM02).
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except (TypeError, ValueError):
            message = str(record.msg)
        redacted = redact_pii(message)
        if redacted != message:
            record.msg = redacted
            record.args = None
        return True
