"""Point the application's ``db_manager`` at the entity-resolution database.

Scripts here that go through repositories need an ``AsyncSession``, which means
``chronovista.config.database.db_manager``, which means
``settings.effective_database_url`` — and that returns the **development** URL
whenever ``DEVELOPMENT_MODE`` is true. It is true in this repo's ``.env``.

That default is wrong for every script in this directory. The entities, their
aliases, and ``external_ids`` live in the production database; dev holds an
unrelated, much smaller snapshot. Worse, the mistake is quiet: dev has the same
tables, so a mis-targeted run does not raise. ``write_external_ids.py`` simply
reports "0 would write", and ``create_entities.py`` would create the entities in
the wrong database and report success.

The sibling scripts that use raw asyncpg (``export_ledger.py``, the ``fetch_*``
family) already hardcode this same URL as their default. This module makes the
session-based scripts agree with them, so *which database* is no longer
something the caller has to remember.

An explicit ``--database-url`` still wins; the guard only fires when the target
resolves to a development database without being asked for.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from chronovista.config.settings import settings  # noqa: E402

# The database the rest of this directory already points at by default. In a container the
# deployment redirects this via CHRONO_GRAPH_PG_URL, which MUST point at the SAME Postgres as
# export_graph.sh's CHRONO_PGHOST/PORT/USER/DB (the two target mechanisms have to agree —
# Feature 113). The default keeps the local prod port for dev use.
DEFAULT_URL = os.environ.get("CHRONO_GRAPH_PG_URL") or (
    "postgresql+asyncpg://chronovista:chronovista@localhost:5435/chronovista"
)

_CREDENTIALS = re.compile(r"//[^/@]*@")


def redact(url: str) -> str:
    """Strip credentials so the target can be printed."""
    return _CREDENTIALS.sub("//***@", url)


def add_argument(parser: argparse.ArgumentParser) -> None:
    """Register the shared ``--database-url`` option."""
    parser.add_argument(
        "--database-url",
        default=DEFAULT_URL,
        help="Target database (default: the production entity store)",
    )
    parser.add_argument(
        "--allow-dev",
        action="store_true",
        help="Permit a development target (refused otherwise)",
    )


def use(database_url: str = DEFAULT_URL, allow_dev: bool = False) -> str:
    """Bind ``db_manager`` to ``database_url`` and report the target.

    Returns the resolved URL. Raises ``SystemExit`` if it resolves to a
    development database without ``allow_dev``, because that is the silent
    failure this module exists to prevent.
    """
    settings.development_mode = False
    settings.database_url = database_url

    resolved = settings.effective_database_url
    if resolved != database_url:  # pragma: no cover - defensive
        raise SystemExit(
            f"database target did not take: asked for {redact(database_url)}, "
            f"settings resolved {redact(resolved)}"
        )

    if not allow_dev and ("chronovista_dev" in resolved or ":5434/" in resolved):
        raise SystemExit(
            f"refusing to run against a development database ({redact(resolved)}).\n"
            "Entity-resolution data lives in the production store. Pass "
            "--allow-dev if this is deliberate."
        )

    print(f"database: {redact(resolved)}")
    return resolved
