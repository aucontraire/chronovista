"""Fitness guard -- one longest-match-wins ranker arbitrates EVERY scan route (SC-003).

Invariant (Feature 111 US4, FR-005/FR-006)
------------------------------------------
A shorter match overlapping a longer one never survives, regardless of whether the
contest is within one segment, across a segment boundary, or in a video's metadata.
That holds only if (a) the ranker itself prefers the longer span, and (b) every route
funnels its candidates through that ONE ranker instead of re-deriving arbitration.

Two arms, guarding two different failure modes:

* **Behavioural** -- ``_apply_longest_match_wins`` keeps the longer of two overlapping
  spans. Sees a mutated sort key (e.g. shortest-first) that every route would inherit.
* **Single-source** -- the three scan routes (per-segment ``_scan_batch``, metadata
  ``_match_text_for_video``, cross-segment ``_scan_cross_segment``) each call the
  ranker, and no OTHER function in ``src/chronovista`` re-implements a
  length-descending greedy claim. Sees a route that quietly stops arbitrating (or grows
  a private copy), which no behavioural test of the ranker can notice because the
  ranker itself is untouched.

Companion to ``tests/integration/services/test_scan_scope_invariant.py`` (end-to-end
shadowing through the real DB); this module is the cheap structural half.

MUTATION-VERIFIED (relocated copy of the service; real tree untouched):
  * sort key ``(-(m[2]-m[1]), m[1])`` -> ``((m[2]-m[1]), m[1])``
    -> the behavioural tests go RED;
  * rename one call site (``_scan_cross_segment``'s ``self._apply_longest_match_wins``
    -> ``self._apply_lmw_bypassed``) -> :func:`test_every_scan_route_calls_the_ranker`
    RED.
"""

from __future__ import annotations

import ast
import uuid
from pathlib import Path
from typing import cast

import pytest

from chronovista.services.entity_mention_scan_service import (
    EntityMentionScanService,
    _EntityPattern,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SRC = _REPO_ROOT / "src" / "chronovista"
_SCAN_SERVICE = _SRC / "services" / "entity_mention_scan_service.py"

_RANKER = "_apply_longest_match_wins"

# The only functions allowed to call the ranker: one per scan route.
_EXPECTED_CALLERS = frozenset(
    {"_scan_batch", "_match_text_for_video", "_scan_cross_segment"}
)

Match = tuple[uuid.UUID, int, int, str, _EntityPattern]


class _Row:
    """Minimal stand-in for the segment row the ranker only uses for logging."""

    id = 0


def _pattern() -> _EntityPattern:
    # The ranker never reads the pattern; it is carried through untouched.
    return cast(_EntityPattern, None)


def _match(entity_id: uuid.UUID, start: int, end: int) -> Match:
    return (entity_id, start, end, f"span{start}-{end}", _pattern())


def _rank(matches: list[Match]) -> tuple[list[Match], int]:
    return EntityMentionScanService._apply_longest_match_wins(matches, _Row(), False)


# --------------------------------------------------------------------------- #
# Arm 1: behavioural -- longer wins
# --------------------------------------------------------------------------- #


class TestRankerContract:
    @pytest.mark.parametrize("same_entity", [True, False])
    def test_long_span_beats_short_span_inside_it(self, same_entity: bool) -> None:
        long_id = uuid.uuid4()
        short_id = long_id if same_entity else uuid.uuid4()
        long_m = _match(long_id, 0, 20)
        short_m = _match(short_id, 5, 10)

        # Input order must not matter: feed short first.
        surviving, skips = _rank([short_m, long_m])

        assert surviving == [long_m]
        assert skips == 1

    def test_long_span_beats_partially_overlapping_shorter_span(self) -> None:
        long_m = _match(uuid.uuid4(), 0, 20)
        straddler = _match(uuid.uuid4(), 15, 25)

        surviving, skips = _rank([straddler, long_m])

        assert surviving == [long_m]
        assert skips == 1

    def test_non_overlapping_spans_both_survive(self) -> None:
        first = _match(uuid.uuid4(), 0, 5)
        second = _match(uuid.uuid4(), 10, 30)
        adjacent = _match(uuid.uuid4(), 5, 8)  # touching, not overlapping

        surviving, skips = _rank([second, adjacent, first])

        assert {m[1:3] for m in surviving} == {(0, 5), (5, 8), (10, 30)}
        assert skips == 0

    def test_equal_length_tie_is_stable_by_earlier_start(self) -> None:
        early = _match(uuid.uuid4(), 0, 10)
        late = _match(uuid.uuid4(), 5, 15)

        surviving, skips = _rank([late, early])

        assert surviving == [early]
        assert skips == 1


# --------------------------------------------------------------------------- #
# Arm 2: single-source -- every route uses the ONE ranker
# --------------------------------------------------------------------------- #


def _enclosing_function_names(tree: ast.AST, attr: str) -> set[str]:
    """Names of functions containing a ``<expr>.attr(...)`` call."""
    found: set[str] = set()
    for fn in ast.walk(tree):
        if not isinstance(fn, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        for node in ast.walk(fn):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == attr
            ):
                found.add(fn.name)
                break
    return found


def test_every_scan_route_calls_the_ranker() -> None:
    """Exactly the three scan routes call the ranker -- none bypasses it."""
    tree = ast.parse(_SCAN_SERVICE.read_text(encoding="utf-8"))
    callers = _enclosing_function_names(tree, _RANKER)
    # The ranker is a staticmethod calling nothing of itself, so ``callers`` is the
    # set of routes that arbitrate.
    assert callers == _EXPECTED_CALLERS, (
        f"routes calling `{_RANKER}` are {sorted(callers)}, expected "
        f"{sorted(_EXPECTED_CALLERS)}. A route missing here no longer arbitrates "
        "with longest-match-wins (uniform arbitration, US4); an extra one is a new "
        "route that must be added deliberately."
    )


def _is_length_desc_sort_key(node: ast.Call) -> bool:
    """True for ``sorted(..)``/``.sort(..)`` with a ``key=lambda`` negating a length."""
    func = node.func
    is_sort = (isinstance(func, ast.Name) and func.id == "sorted") or (
        isinstance(func, ast.Attribute) and func.attr == "sort"
    )
    if not is_sort:
        return False
    for kw in node.keywords:
        if kw.arg == "key" and isinstance(kw.value, ast.Lambda):
            # ``-(end - start)``: a negated span length, the greedy-claim sort key.
            if any(
                isinstance(n, ast.UnaryOp)
                and isinstance(n.op, ast.USub)
                and isinstance(n.operand, ast.BinOp)
                and isinstance(n.operand.op, ast.Sub)
                for n in ast.walk(kw.value.body)
            ):
                return True
    return False


def test_no_sibling_reimplements_length_desc_arbitration() -> None:
    """Only the ranker sorts matches by negated span length (greedy-claim copy)."""
    offenders: list[str] = []
    for py in sorted(_SRC.rglob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for fn in ast.walk(tree):
            if not isinstance(fn, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            if fn.name == _RANKER:
                continue
            for node in ast.walk(fn):
                if isinstance(node, ast.Call) and _is_length_desc_sort_key(node):
                    offenders.append(f"{py.relative_to(_SRC)}::{fn.name}")
    assert not offenders, (
        f"{sorted(set(offenders))} sort by negated length outside `{_RANKER}` -- a "
        "private longest-match-wins copy. Route the candidates through the ranker so "
        "within- and cross-segment arbitration stay uniform."
    )


def test_ranker_exists_exactly_once() -> None:
    """The ranker has a single definition in the codebase."""
    defs = 0
    for py in _SRC.rglob("*.py"):
        for node in ast.walk(ast.parse(py.read_text(encoding="utf-8"))):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                defs += node.name == _RANKER
    assert defs == 1, f"expected one `{_RANKER}` definition, found {defs}"
