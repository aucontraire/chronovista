"""Shared Neo4j connection-target resolver + write-side guard for the graph loaders.

Every loader (``load_neo4j`` / ``load_semantic`` / ``load_categories`` /
``load_reviewed``) and ``reload_all.sh`` resolve their Neo4j target HERE, so the
"refuse a remote write without ``--allow-remote``" guard lives in one place instead of
four. This mirrors the Postgres read-side guard in ``db_target.py`` — the asymmetry the
Phase-1 review flagged was that the read path was guarded (``db_target`` refuses a dev
DB) while the destructive write path was not guarded at all.

Rationale that outlives any roadmap: the loaders issue ``MATCH (n) DETACH DELETE n``
(and per-layer deletes), so a loader must not reach a *remote* database without an
explicit, deliberate ``--allow-remote``. This is true the day it is written and stays
true no matter what the demo/API/UI roadmap does with the graph later.

Defaults target the local ``--profile graph`` dev container (``bolt://localhost:7688``,
host-mapped off 7687 to coexist with another local project's Neo4j), so a bare
``reload_all.sh`` targets localhost rather than whatever the lab ``.env`` happens to
point ``NEO4J_URI`` at.
"""
from __future__ import annotations

import argparse
import os
from urllib.parse import urlparse

# The local `--profile graph` dev container (see docker-compose.dev.yml:neo4j-dev).
DEFAULT_URI = "bolt://localhost:7688"
DEFAULT_LOCAL_PASSWORD = "dev_password"  # the dev container's committed, non-secret password

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", ""}
# Encrypted schemes are always remote (Aura uses neo4j+s://).
_SECURE_SCHEMES = {"neo4j+s", "neo4j+ssc", "bolt+s", "bolt+ssc"}
# Every scheme the neo4j driver accepts. Anything else — including a schemeless string like
# "myremote.com:7687", which urlparse parses as scheme="myremote.com" with NO hostname — is
# treated as remote (fail safe), so the guard never waves through a target it couldn't classify.
_PLAIN_SCHEMES = {"neo4j", "bolt"}
_KNOWN_SCHEMES = _SECURE_SCHEMES | _PLAIN_SCHEMES


def _allowed_hosts() -> set[str]:
    """Local hosts, plus ONE explicitly-declared internal deployment host (Feature 113).

    When Neo4j ships inside the stack the loader reaches it at ``bolt://neo4j:7687`` — a
    non-local host. Rather than disarm the guard with a blanket ``--allow-remote`` in the
    deployment entrypoint (which would also wave through Aura), the deployment DECLARES its one
    internal host via ``CHRONO_GRAPH_INTERNAL_HOST=neo4j``. That host is then treated as local;
    every other non-local target — including any ``neo4j+s://`` Aura URI (always remote via its
    secure scheme) — still requires a deliberate ``--allow-remote``. Scoped allowance, not an
    override.

    Caveat: the declared host is trusted over PLAIN bolt (no TLS). Declare only a host you
    control on the deployment's internal network (the compose ``neo4j`` service), never a name
    that could resolve to an external Neo4j — a misdeclared internal host would be silently
    writable (DETACH DELETE) without ``--allow-remote``.
    """
    hosts = set(_LOCAL_HOSTS)
    declared = os.environ.get("CHRONO_GRAPH_INTERNAL_HOST", "").strip().lower()
    if declared:
        hosts.add(declared)
    return hosts


def is_remote(uri: str) -> bool:
    """True if *uri* points at anything other than the local machine (or the one declared
    internal deployment host — see :func:`_allowed_hosts`).

    Fail safe: a URI whose scheme is not one the neo4j driver recognizes (a schemeless string
    included, since urlparse can extract no host from it) is treated as remote — the guard must
    treat what it cannot classify as the dangerous case, not the safe one. A secure scheme
    (Aura's ``neo4j+s://``) is always remote regardless of host.
    """
    parsed = urlparse(uri)
    if parsed.scheme not in _KNOWN_SCHEMES:
        return True
    if parsed.scheme in _SECURE_SCHEMES:
        return True
    host = (parsed.hostname or "").lower()
    return host not in _allowed_hosts()


def add_argument(parser: argparse.ArgumentParser) -> None:
    """Register the shared ``--allow-remote`` option on a loader's arg parser."""
    parser.add_argument(
        "--allow-remote",
        action="store_true",
        help=(
            "permit a non-local Neo4j target (default: refuse — the loaders issue "
            "DETACH DELETE, so a remote write must be deliberate)"
        ),
    )


def resolve(allow_remote: bool = False) -> tuple[str, str, str, str]:
    """Return ``(uri, user, password, db_name)``, refusing a remote target unless asked.

    - ``NEO4J_URI`` unset  -> the local dev container (``DEFAULT_URI``).
    - target is remote and ``allow_remote`` is False -> ``SystemExit`` (the guard).
    - password: ``NEO4J_PASSWORD`` or ``NEO4J_PWD``; for a *local* target it defaults to
      the dev container's password so a bare local reload needs no secrets.
    """
    uri = os.environ.get("NEO4J_URI") or DEFAULT_URI
    user = os.environ.get("NEO4J_USERNAME") or os.environ.get("NEO4J_USER") or "neo4j"
    pw = os.environ.get("NEO4J_PASSWORD") or os.environ.get("NEO4J_PWD")
    # NEO4J_DATABASE preferred; DB_NAME kept as a back-compat fallback (it is a dangerously
    # generic name that an unrelated tool may already have set in the shell).
    db_name = os.environ.get("NEO4J_DATABASE") or os.environ.get("DB_NAME") or "neo4j"

    remote = is_remote(uri)
    if remote and not allow_remote:
        raise SystemExit(
            f"refusing to write to a remote Neo4j target ({uri}).\n"
            "The graph loaders issue DETACH DELETE; a remote write must be deliberate.\n"
            "For the local --profile graph container, set NEO4J_URI=bolt://localhost:7688\n"
            "(or unset NEO4J_URI to use that default). To target the remote instance on\n"
            "purpose, pass --allow-remote."
        )
    if not pw:
        pw = None if remote else DEFAULT_LOCAL_PASSWORD
    if not pw:
        raise SystemExit("Set NEO4J_PWD (or NEO4J_PASSWORD) for the remote target.")

    print(f"neo4j target: {uri}  (db={db_name}, user={user})")
    return uri, user, pw, db_name
