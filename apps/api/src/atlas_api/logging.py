import logging
import sys

from atlas_api.security.redaction import RedactionFilter


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter('{"level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}')
    )
    # Scrub PII from every record so breach descriptions never land in log sinks
    # (OWASP ASVS V7/V8, OWASP LLM02 — Sensitive Information Disclosure).
    handler.addFilter(RedactionFilter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)
