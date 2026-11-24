"""Properties of the passage rule (Feature 118): ``chain_passages`` and ``group_across_languages``.

The rule is pinned by properties that together determine it uniquely, rather than by a
second copy of the algorithm: every co-mention lands in exactly one passage; inside a
passage (in time order) each co-mention starts within the window of the passage's running
end; and consecutive passages of one (video, language) are more than the window apart.
Grouping is pinned the same way with strict overlap. Hypothesis drives arbitrary interval
sets through both; a few hand cases name the boundaries.
"""

from __future__ import annotations

import uuid

from hypothesis import given, settings
from hypothesis import strategies as st

from chronovista.db.models import UserLanguagePreference as UserLanguagePreferenceDB
from chronovista.repositories.entity_pair_proximity_repository import CoMentionRow
from chronovista.services.proximity_service import (
    _language_ranks,
    _nearest,
    _order_variants,
    _Passage,
    _shared_scopes,
    chain_passages,
    group_across_languages,
)
from tests.factories.pair_passages_factory import (
    LanguagePassageFactory,
    PassageMomentFactory,
)


def _row(
    start: float,
    length: float = 2.0,
    *,
    video_id: str = "video-001",
    language_code: str = "en",
    seq: int = 0,
    gap: float = 1.0,
) -> CoMentionRow:
    return CoMentionRow(
        video_id=video_id,
        channel_id=None,
        language_code=language_code,
        segment_lo_id=seq,
        segment_hi_id=seq + 1,
        gap_seconds=gap,
        start_time=start,
        end_time=start + length,
    )


_rows = st.lists(
    st.tuples(
        st.floats(0, 600, allow_nan=False),
        st.floats(0, 20, allow_nan=False),
        st.sampled_from(["en", "es"]),
        st.sampled_from(["video-001", "video-002"]),
    ),
    max_size=40,
).map(
    lambda items: [
        _row(s, length, language_code=lang, video_id=vid, seq=2 * i)
        for i, (s, length, lang, vid) in enumerate(items)
    ]
)
_windows = st.sampled_from([15.0, 30.0, 60.0, 120.0])


class TestChaining:
    @settings(deadline=None)
    @given(rows=_rows, window=_windows)
    def test_the_rule_holds_for_any_interval_set(
        self, rows: list[CoMentionRow], window: float
    ) -> None:
        passages = chain_passages(rows, window)
        # Partition: every co-mention is in exactly one passage.
        assert sorted(r for p in passages for r in p.comentions) == sorted(rows)
        by_scope: dict[tuple[str, str], list[_Passage]] = {}
        for passage in passages:
            members = sorted(
                passage.comentions, key=lambda r: (r.start_time, r.end_time)
            )
            assert {(r.video_id, r.language_code) for r in members} == {
                (passage.video_id, passage.language_code)
            }
            # Chaining: in time order, each co-mention starts within the window of the
            # passage's running end.
            end = members[0].end_time
            for r in members[1:]:
                assert r.start_time <= end + window
                end = max(end, r.end_time)
            assert passage.start_time == members[0].start_time
            assert passage.end_time == end
            by_scope.setdefault((passage.video_id, passage.language_code), []).append(
                passage
            )
        # Separation: consecutive passages of one scope are more than the window apart,
        # so they never overlap.
        for scope_passages in by_scope.values():
            ordered = sorted(scope_passages, key=lambda p: p.start_time)
            for earlier, later in zip(ordered, ordered[1:], strict=False):
                assert later.start_time > earlier.end_time + window

    def test_a_start_exactly_the_window_after_the_end_joins(self) -> None:
        (passage,) = chain_passages([_row(0.0), _row(32.0, seq=2)], 30.0)
        assert len(passage.comentions) == 2

    def test_a_start_just_past_it_opens_a_new_passage(self) -> None:
        assert len(chain_passages([_row(0.0), _row(32.001, seq=2)], 30.0)) == 2

    def test_a_long_co_mention_keeps_the_passage_open(self) -> None:
        # The running end is the LATEST end so far, not the previous co-mention's end.
        rows = [_row(0.0, 100.0), _row(10.0, seq=2), _row(125.0, seq=4)]
        (passage,) = chain_passages(rows, 30.0)
        assert passage.end_time == 127.0

    def test_languages_and_videos_never_chain_together(self) -> None:
        rows = [
            _row(0.0),
            _row(1.0, language_code="es", seq=2),
            _row(2.0, video_id="video-002", seq=4),
        ]
        assert len(chain_passages(rows, 30.0)) == 3


def _passage(start: float, end: float, language_code: str = "en") -> _Passage:
    return _Passage("video-001", language_code, start, end, [_row(start, end - start)])


_passages = st.lists(
    st.tuples(
        st.floats(0, 600, allow_nan=False),
        st.floats(0, 60, allow_nan=False),
        st.sampled_from(["en", "es", "fr"]),
    ),
    max_size=30,
).map(lambda items: [_passage(s, s + length, lang) for s, length, lang in items])


class TestGrouping:
    @settings(deadline=None)
    @given(passages=_passages)
    def test_the_rule_holds_for_any_passage_set(self, passages: list[_Passage]) -> None:
        groups = group_across_languages(passages)
        assert sorted(p for g in groups for p in g) == sorted(passages)
        previous_end: float | None = None
        for group in groups:
            members = sorted(group, key=lambda p: (p.start_time, p.end_time))
            # Transitive strict overlap inside a group.
            end = members[0].end_time
            for p in members[1:]:
                assert p.start_time < end or p.start_time == members[0].start_time
                end = max(end, p.end_time)
            # Groups are in time order and do not overlap (touching is not overlap).
            if previous_end is not None:
                assert members[0].start_time >= previous_end
            previous_end = end

    def test_overlapping_languages_group(self) -> None:
        (group,) = group_across_languages([_passage(10, 40), _passage(20, 50, "es")])
        assert {p.language_code for p in group} == {"en", "es"}

    def test_touching_ranges_do_not_group(self) -> None:
        groups = group_across_languages([_passage(10, 40), _passage(40, 60, "es")])
        assert len(groups) == 2

    def test_unequal_boundaries_group_transitively(self) -> None:
        # One language splits where the other does not: all three are one group, with the
        # split language listed twice.
        (group,) = group_across_languages(
            [_passage(0, 20), _passage(30, 50), _passage(10, 40, "es")]
        )
        assert sorted(p.language_code for p in group) == ["en", "en", "es"]

    def test_zero_length_passages_at_one_moment_group(self) -> None:
        (group,) = group_across_languages([_passage(10, 10), _passage(10, 10, "es")])
        assert len(group) == 2


def _pref(
    language_code: str, preference_type: str, priority: int
) -> UserLanguagePreferenceDB:
    return UserLanguagePreferenceDB(
        user_id="test-user",
        language_code=language_code,
        preference_type=preference_type,
        priority=priority,
    )


def _variant(language_code: str, gap: float):  # type: ignore[no-untyped-def]
    return LanguagePassageFactory(
        language_code=language_code, closest=PassageMomentFactory(gap_seconds=gap)
    )


class TestVariantOrder:
    def test_priority_orders_within_a_tier_and_base_languages_match(self) -> None:
        ranks = _language_ranks(
            [
                _pref("fr", "fluent", 2),
                _pref("es-MX", "fluent", 1),
                _pref("de", "learning", 1),
            ]
        )
        order = _order_variants(
            [
                _variant("de", 1.0),
                _variant("fr", 2.0),
                _variant("es", 9.0),
                _variant("en", 0.5),
            ],
            ranks,
        )
        assert [v.language_code for v in order] == ["es", "fr", "de", "en"]

    def test_curious_and_exclude_never_promote(self) -> None:
        ranks = _language_ranks([_pref("en", "curious", 1), _pref("fr", "exclude", 2)])
        order = _order_variants(
            [_variant("en", 5.0), _variant("fr", 3.0), _variant("de", 4.0)], ranks
        )
        assert [v.language_code for v in order] == ["fr", "de", "en"]

    def test_the_best_rank_wins_when_one_base_has_several_preferences(self) -> None:
        ranks = _language_ranks(
            [_pref("es", "learning", 1), _pref("es-ES", "fluent", 4)]
        )
        assert ranks["es"].tier == 0

    def test_ties_break_by_gap_then_language(self) -> None:
        order = _order_variants(
            [_variant("fr", 2.0), _variant("de", 2.0), _variant("en", 3.0)], {}
        )
        assert [v.language_code for v in order] == ["de", "fr", "en"]

    @settings(deadline=None)
    @given(
        st.permutations(
            [("en", 1.0), ("es", 2.0), ("fr", 2.0), ("de", 0.5), ("it", 7.0)]
        )
    )
    def test_the_order_does_not_depend_on_input_order(
        self, items: list[tuple[str, float]]
    ) -> None:
        ranks = _language_ranks([_pref("it", "learning", 1)])
        order = _order_variants([_variant(lang, gap) for lang, gap in items], ranks)
        assert [v.language_code for v in order] == ["it", "de", "en", "es", "fr"]


class TestNearest:
    @settings(deadline=None)
    @given(
        st.lists(st.floats(0, 5000, allow_nan=False), min_size=1, max_size=30),
        st.lists(st.floats(0, 5000, allow_nan=False), min_size=1, max_size=30),
    )
    def test_matches_the_brute_force_minimum(
        self, xs: list[float], ys: list[float]
    ) -> None:
        gap, at = _nearest(xs, ys)
        assert gap == min(abs(x - y) for x in xs for y in ys)
        assert any(abs(x - y) == gap and min(x, y) == at for x in xs for y in ys)

    def test_single_and_equal_values(self) -> None:
        assert _nearest([5.0], [5.0]) == (0.0, 5.0)
        assert _nearest([100.0], [40.0]) == (60.0, 40.0)


class TestSharedScopes:
    def test_only_scopes_with_both_entities(self) -> None:
        a, b = uuid.uuid4(), uuid.uuid4()
        rows = [
            (a, "video-001", "en", 1.0),
            (b, "video-001", "en", 2.0),
            (a, "video-001", "es", 1.0),
            (b, "video-002", "en", 3.0),
        ]
        assert _shared_scopes(rows, a, b) == {("video-001", "en")}
