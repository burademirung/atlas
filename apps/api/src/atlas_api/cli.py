"""Entry points used by container one-shot services."""

import subprocess
import sys


def migrate() -> None:
    sys.exit(subprocess.call(["alembic", "upgrade", "head"]))  # noqa: S603, S607
