"""Regression test -- the ArbitrationContext seam is inert (Feature 111, T006/T007).

``_apply_longest_match_wins`` gained a keyword-only ``context: ArbitrationContext |
None`` parameter as an accepted-but-inert seam for a future scoring pass. The whole
point of the seam is that it changes NOTHING today: whether called with no context,
``context=None``, or a default ``ArbitrationContext()``, the returned ordering and
selection MUST be byte-for-byte identical to the span-only longest-match-wins rule
(longer span wins; ties broken by earlier start).

These tests lock that invariant so a later edit that wires scoring into the context
cannot silently alter the fallback (no-signal) path.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

from chronovista.services.entity_mention_scan_service import (
    ArbitrationContext,
    EntityMentionScanService,
    _EntityPattern,
)


def _pattern(entity_id: uuid.UUID) -> _EntityPattern:
    """Minimal ``_EntityPattern``; arbitration never reads its contents."""
    return _EntityPattern(
        entity_id=entity_id,
        canonical_name="x",
        entity_type="person",
        pg_pattern="x",
        alias_names=["x"],
    )


def _matches() -> list[tuple[uuid.UUID, int, int, str, _EntityPattern]]:
    """Overlapping matches exercising longest-wins AND the start tie-break.

    - A [0,10) span 10 -- longest, survives.
    - B [2,8)  span 6  -- overlaps A, shorter, skipped.
    - C [10,15) span 5 -- abuts A (no overlap), survives.
    - D [20,25) span 5 -- survives.
    - E [22,27) span 5 -- overlaps D, equal span but later start, skipped.
    """
    ids = [uuid.UUID(int=i) for i in range(1, 6)]
    return [
        (ids[0], 0, 10, "a", _pattern(ids[0])),
        (ids[1], 2, 8, "b", _pattern(ids[1])),
        (ids[2], 10, 15, "c", _pattern(ids[2])),
        (ids[3], 20, 25, "d", _pattern(ids[3])),
        (ids[4], 22, 27, "e", _pattern(ids[4])),
    ]


def test_context_variants_return_identical_results() -> None:
    row = SimpleNamespace(id=1)

    no_ctx = EntityMentionScanService._apply_longest_match_wins(_matches(), row, False)
    explicit_none = EntityMentionScanService._apply_longest_match_wins(
        _matches(), row, False, context=None
    )
    empty_ctx = EntityMentionScanService._apply_longest_match_wins(
        _matches(), row, False, context=ArbitrationContext()
    )

    assert no_ctx == explicit_none
    assert no_ctx == empty_ctx


def test_fallback_selection_is_longest_wins_with_start_tiebreak() -> None:
    row = SimpleNamespace(id=1)
    matches = _matches()
    surviving, skip_count = EntityMentionScanService._apply_longest_match_wins(
        matches, row, False, context=ArbitrationContext()
    )

    # A (longest), C (abuts A), D (earlier start than overlapping equal-span E).
    assert [m[0] for m in surviving] == [matches[0][0], matches[2][0], matches[3][0]]
    # B overlaps a longer match; E overlaps an equal-span, earlier-start match.
    assert skip_count == 2


def test_populated_context_still_inert() -> None:
    row = SimpleNamespace(id=1)
    populated = ArbitrationContext(known_entity_ids=frozenset({uuid.UUID(int=99)}))
    with_signal = EntityMentionScanService._apply_longest_match_wins(
        _matches(), row, False, context=populated
    )
    baseline = EntityMentionScanService._apply_longest_match_wins(
        _matches(), row, False
    )
    assert with_signal == baseline
