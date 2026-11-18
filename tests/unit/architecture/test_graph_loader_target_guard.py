"""Fitness guard: the Neo4j graph loaders resolve their write target through ONE place.

Constitution v1.3.0 (≥3 call sites → one home + a same-PR, mutation-verified fitness test):
four loaders write to Neo4j — load_neo4j, load_semantic, load_categories, load_reviewed — so
the "refuse a remote target without --allow-remote" guard lives in scripts/graph/neo4j_target.py
and every loader MUST go through it. The guard exists because the loaders issue DETACH DELETE; a
remote write must be deliberate. These tests fail (mutation-verified) if:
  - a loader stops calling neo4j_target.resolve(), or
  - a loader reverts to reading NEO4J_URI directly (bypassing the guard), or
  - the guard stops refusing a remote target when --allow-remote is absent.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

_GRAPH_DIR = Path(__file__).resolve().parents[3] / "scripts" / "graph"
_LOADERS = (
    "load_neo4j.py",
    "load_semantic.py",
    "load_categories.py",
    "load_reviewed.py",
)


@pytest.mark.parametrize("loader", _LOADERS)
def test_loader_resolves_target_through_shared_guard(loader: str) -> None:
    src = (_GRAPH_DIR / loader).read_text()
    # Must resolve through the shared guard AND forward the CLI flag verbatim. Hardcoding
    # allow_remote=True would silently defeat the remote-write guard, so guard against it too.
    assert "neo4j_target.resolve(allow_remote=args.allow_remote)" in src, (
        f"{loader} must call neo4j_target.resolve(allow_remote=args.allow_remote) — the single "
        "home for the remote-write guard, with the --allow-remote flag forwarded (not hardcoded)."
    )
    assert (
        "resolve(allow_remote=True)" not in src
    ), f"{loader} hardcodes allow_remote=True, which defeats the remote-write guard."


# NEO4J_URI read by any direct-env syntax: environ.get / getenv / environ[...]. Any of these
# bypasses neo4j_target.resolve()'s remote-write guard.
_NEO4J_URI_BYPASS = re.compile(
    r"""os\.environ\.get\(\s*['"]NEO4J_URI['"]"""
    r"""|os\.getenv\(\s*['"]NEO4J_URI['"]"""
    r"""|os\.environ\[\s*['"]NEO4J_URI['"]\s*\]"""
)


@pytest.mark.parametrize("loader", _LOADERS)
def test_loader_does_not_read_neo4j_uri_directly(loader: str) -> None:
    src = (_GRAPH_DIR / loader).read_text()
    assert not _NEO4J_URI_BYPASS.search(src), (
        f"{loader} reads NEO4J_URI directly (environ.get / getenv / environ[...]), bypassing "
        "neo4j_target.resolve()'s remote-write guard. Resolve the target through neo4j_target."
    )


def _neo4j_target():
    if str(_GRAPH_DIR) not in sys.path:
        sys.path.insert(0, str(_GRAPH_DIR))
    import neo4j_target  # noqa: E402 — a scripts/graph module, not a package import

    return neo4j_target


def test_guard_refuses_remote_without_allow_remote(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    nt = _neo4j_target()
    monkeypatch.setenv("NEO4J_URI", "neo4j+s://example.databases.neo4j.io")
    monkeypatch.setenv("NEO4J_PWD", "secret")
    with pytest.raises(SystemExit):
        nt.resolve(allow_remote=False)


def test_guard_allows_remote_with_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    nt = _neo4j_target()
    monkeypatch.setenv("NEO4J_URI", "neo4j+s://example.databases.neo4j.io")
    monkeypatch.setenv("NEO4J_PWD", "secret")
    uri, _user, pw, _db = nt.resolve(allow_remote=True)
    assert uri.startswith("neo4j+s://") and pw == "secret"


def test_guard_defaults_to_local_when_uri_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    nt = _neo4j_target()
    monkeypatch.delenv("NEO4J_URI", raising=False)
    monkeypatch.delenv("NEO4J_PWD", raising=False)
    monkeypatch.delenv("NEO4J_PASSWORD", raising=False)
    uri, _user, pw, _db = nt.resolve(allow_remote=False)
    assert uri == "bolt://localhost:7688" and pw == "dev_password"
