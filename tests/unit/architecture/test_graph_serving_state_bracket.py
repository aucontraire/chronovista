"""Fitness guard: every destructive graph loader participates in the serving-state bracket.

Feature 113 committed contract (``src/chronovista/graph/serving_state.py``): the graph is only
served when a build is ``complete`` and every DECLARED layer is present. The re-entrant bracket
across the four loaders is what guarantees an orchestrated rebuild never flips the graph servable
BETWEEN layer steps, and that a crashed load leaves it unservable rather than half-built. A future
loader (or a fifth destructive path) that wipes/writes without the bracket would open an invisible
servable window over a partial graph — the exact "transient state indistinguishable from a real
result" failure this feature exists to prevent.

Sibling of ``test_graph_loader_target_guard.py`` (same four loaders, same DETACH-DELETE rationale;
Constitution: ≥3 call sites → one home + a same-PR, mutation-verified fitness test).

Mutation-verify (do before merge): delete one loader's ``serving_state.enter(session)`` call, or
the ``WHERE NOT n:Meta`` clause, or a contract phrase from the module docstring → the matching
test below MUST go red; restore it → green.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from chronovista.graph import serving_state

_REPO = Path(__file__).resolve().parents[3]
_GRAPH_DIR = _REPO / "scripts" / "graph"
_SERVING_STATE = _REPO / "src" / "chronovista" / "graph" / "serving_state.py"
_LOADERS = (
    "load_neo4j.py",
    "load_semantic.py",
    "load_categories.py",
    "load_reviewed.py",
)


@pytest.mark.parametrize("loader", _LOADERS)
def test_loader_imports_serving_state(loader: str) -> None:
    src = (_GRAPH_DIR / loader).read_text()
    assert "from chronovista.graph import serving_state" in src, (
        f"{loader} must import the serving-state bracket (Feature 113) — a destructive loader "
        "that writes without bracketing opens an invisible servable window over a partial graph."
    )


@pytest.mark.parametrize("loader", _LOADERS)
def test_loader_enters_and_leaves_bracket(loader: str) -> None:
    src = (_GRAPH_DIR / loader).read_text()
    assert "serving_state.enter(" in src, (
        f"{loader} must call serving_state.enter(session) at the start of its session so the "
        "graph reads 'loading' while it mutates."
    )
    assert "serving_state.leave(" in src, (
        f"{loader} must call serving_state.leave(session) only on success, so a crash mid-load "
        "leaves the graph unservable (the fail-safe)."
    )
    # Fail-safe placement: leave() MUST be on the success path, not inside the try/finally that
    # closes the driver. A leave() in finally would run even on a crash → flip a partial load to
    # 'complete'. Assert the last leave() precedes the (single) `finally:`.
    if "finally:" in src:
        assert src.rfind("serving_state.leave(") < src.index("finally:"), (
            f"{loader}: serving_state.leave() must NOT be inside finally: — that would mark a "
            "crashed/partial load 'complete', defeating the fail-safe."
        )


def test_wipe_protects_meta() -> None:
    """The one unqualified node delete must spare ``:Meta`` or it destroys its own marker."""
    src = (_GRAPH_DIR / "load_neo4j.py").read_text()
    assert "WHERE NOT n:Meta DETACH DELETE n" in src, (
        "load_neo4j's wipe must scope out :Meta (WHERE NOT n:Meta); otherwise the wipe deletes "
        "the serving-state node it is supposed to keep, and the fail-safe degrades to "
        "'absence means not ready' — which fails open."
    )
    assert "MATCH (n) DETACH DELETE n" not in src.replace(
        "WHERE NOT n:Meta DETACH DELETE n", ""
    ), "load_neo4j must not contain an UNqualified MATCH (n) DETACH DELETE n."
    # enter() must precede the actual wipe Cypher (not the --wipe argparse help text, which also
    # contains 'DETACH DELETE') so :Meta exists and reads 'loading' while the graph is torn down.
    assert src.index("serving_state.enter(") < src.index(
        "WHERE NOT n:Meta DETACH DELETE"
    ), "load_neo4j must enter the bracket BEFORE the wipe."


def test_is_servable_predicate() -> None:
    """Executable test of the central servability rule (not just a source grep)."""
    declared = ["observed", "semantic", "categories"]
    present = set(declared)
    # complete + every declared layer present -> servable
    assert serving_state.is_servable("complete", declared, present) is True
    # a declared layer missing (lost/wiped) -> NOT servable
    assert (
        serving_state.is_servable("complete", declared, {"observed", "semantic"})
        is False
    )
    # not complete (mid-rebuild) -> NOT servable, whatever is present
    assert serving_state.is_servable("loading", declared, present) is False
    # never loaded / no declaration -> NOT servable (safe default)
    assert serving_state.is_servable("complete", None, set()) is False
    assert serving_state.is_servable(None, declared, present) is False
    # a layer absent BY DECLARATION is fine (reviewed not declared, extra present ignored)
    assert (
        serving_state.is_servable("complete", declared, present | {"reviewed"}) is True
    )


def test_meta_node_is_label_isolated_from_entities() -> None:
    """Cross-feature contract (Feature 113): the serving-state node carries ONLY the ``:Meta``
    label, never ``:Entity``. The connection queries anchor on ``:Entity`` (and typed bridges), so
    a label-isolated ``:Meta`` is invisible to them — adding it cannot change what the existing
    CLI ``graph connect`` returns, and the wipe's ``WHERE NOT n:Meta`` can distinguish it.
    """
    doc = _SERVING_STATE.read_text()
    # (Cypher is built with f-strings, so the source literal is `(m:Meta {{id:` — match the label.)
    assert "(m:Meta" in doc, "serving-state must MERGE/MATCH a :Meta node."
    assert ":Meta:Entity" not in doc and ":Entity:Meta" not in doc, (
        ":Meta must not ALSO be an :Entity — that would make the serving-state node visible to "
        "entity scans and the co-occurrence/category reads, breaking the cross-feature contract."
    )
    # The presence probe for the observed layer anchors on :Entity, and the serving-state node is
    # a distinct :Meta label — so no connection query (all :Entity-anchored) can return it. (The
    # return clause is existence-only, `RETURN 1`; what the contract needs is the :Entity anchor.)
    assert "MATCH (e:Entity)" in doc


def test_serving_state_contract_committed() -> None:
    """Committed-contract guard: the governing decisions live in committed code, not only specs."""
    doc = _SERVING_STATE.read_text()
    assert "DECLARED, not inferred" in doc, (
        "serving_state.py must commit the declared-not-inferred contract (the skip is declared in "
        ":Meta, never inferred from whether an input file exists)."
    )
    assert "PRESENCE, not completeness" in doc, (
        "serving_state.py must commit the presence-not-completeness contract (the check catches a "
        "fully-wiped declared layer, not a half-populated one)."
    )
