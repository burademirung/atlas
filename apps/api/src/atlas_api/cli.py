"""Entry points used by container one-shot services."""

import subprocess  # nosec B404 - fixed, literal command below; no untrusted input
import sys


def migrate() -> None:
    # Static argument list, no shell, no user input -> not injectable.
    sys.exit(subprocess.call(["alembic", "upgrade", "head"]))  # noqa: S603, S607  # nosec B603,B607
