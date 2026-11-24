"""Validators of the Feature 118 discussion-passage models.

Each cross-field rule is shown accepting a consistent instance and rejecting the one
inconsistency it guards. Instances come from ``tests/factories/pair_passages_factory``.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from chronovista.models.connection_evidence import (
    OTHER_MOMENTS_LIMIT,
    PASSAGE_RULE_VERSION,
)
from tests.factories.pair_passages_factory import (
    CoMomentFactory,
    GroupedPassageFactory,
    LanguagePassageFactory,
    PairPassagesFactory,
    PassageMomentFactory,
    PassageSegmentFactory,
    VideoPassagesFactory,
)


class TestLanguagePassage:
    def test_consistent_passage_is_accepted(self) -> None:
        passage = LanguagePassageFactory(
            other_moments=[CoMomentFactory(), CoMomentFactory()]
        )
        assert passage.co_mention_count == 3

    def test_count_must_match_moments(self) -> None:
        with pytest.raises(ValidationError, match="other_moments"):
            LanguagePassageFactory(co_mention_count=2)

    def test_a_long_passage_lists_only_the_first_moments(self) -> None:
        moments = [CoMomentFactory() for _ in range(OTHER_MOMENTS_LIMIT)]
        passage = LanguagePassageFactory(other_moments=moments, co_mention_count=500)
        assert passage.co_mention_count == 500
        with pytest.raises(ValidationError, match="other_moments"):
            LanguagePassageFactory(other_moments=moments[:-1], co_mention_count=500)

    def test_closest_gap_must_be_the_rendered_moment(self) -> None:
        with pytest.raises(ValidationError, match="closest_gap_seconds"):
            LanguagePassageFactory(
                closest=PassageMomentFactory(gap_seconds=4.0), closest_gap_seconds=1.0
            )

    def test_range_must_not_be_inverted(self) -> None:
        with pytest.raises(ValidationError, match="starts after it ends"):
            LanguagePassageFactory(start_time=20.0, end_time=10.0)


class TestPassageParts:
    def test_segment_text_must_be_non_empty(self) -> None:
        with pytest.raises(ValidationError):
            PassageSegmentFactory(text="")

    def test_moment_text_is_bounded(self) -> None:
        with pytest.raises(ValidationError):
            PassageMomentFactory(segments=[PassageSegmentFactory() for _ in range(7)])


class TestGroupedPassage:
    def test_gap_is_the_minimum_over_variants(self) -> None:
        near = LanguagePassageFactory(closest=PassageMomentFactory(gap_seconds=1.0))
        far = LanguagePassageFactory(
            language_code="es", closest=PassageMomentFactory(gap_seconds=5.0)
        )
        # The leading variant is the farther one: the group's gap still comes from all.
        group = GroupedPassageFactory(variants=[far, near])
        assert group.closest_gap_seconds == 1.0

    def test_gap_from_the_leading_variant_only_is_rejected(self) -> None:
        near = LanguagePassageFactory(closest=PassageMomentFactory(gap_seconds=1.0))
        far = LanguagePassageFactory(closest=PassageMomentFactory(gap_seconds=5.0))
        with pytest.raises(ValidationError, match="minimum over its variants"):
            GroupedPassageFactory(variants=[far, near], closest_gap_seconds=5.0)

    def test_range_must_be_the_union_of_variants(self) -> None:
        with pytest.raises(ValidationError, match="union"):
            GroupedPassageFactory(start_time=0.0)


class TestVideoPassages:
    def test_gap_counts_folded_passages(self) -> None:
        passages = [
            GroupedPassageFactory(
                variants=[
                    LanguagePassageFactory(
                        start_time=float(t),
                        end_time=float(t) + 4,
                        closest=PassageMomentFactory(gap_seconds=g),
                    )
                ]
            )
            for t, g in [(10, 9.0), (100, 8.0), (200, 7.0), (300, 1.0)]
        ]
        # The closest passage is the fourth: folded in the panel, still the video's gap.
        assert VideoPassagesFactory(passages=passages).closest_gap_seconds == 1.0

    def test_gap_ignoring_a_passage_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="folded or not"):
            VideoPassagesFactory(closest_gap_seconds=99.0)

    def test_passages_must_be_in_time_order(self) -> None:
        late = GroupedPassageFactory(
            variants=[LanguagePassageFactory(start_time=50.0, end_time=55.0)]
        )
        early = GroupedPassageFactory(
            variants=[LanguagePassageFactory(start_time=5.0, end_time=9.0)]
        )
        with pytest.raises(ValidationError, match="time order"):
            VideoPassagesFactory(passages=[late, early])


class TestPairPassages:
    def test_default_is_a_consistent_passages_response(self) -> None:
        response = PairPassagesFactory()
        assert response.state == "passages"
        assert response.passage_rule_version == PASSAGE_RULE_VERSION
        assert response.returned == 1
        assert response.truncated is False

    def test_passages_state_requires_videos(self) -> None:
        with pytest.raises(ValidationError, match="contradicts"):
            PairPassagesFactory(items=[], state="passages")

    def test_empty_state_with_videos_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="contradicts"):
            PairPassagesFactory(state="not_computed")

    def test_passages_cannot_be_fewer_than_videos(self) -> None:
        with pytest.raises(ValidationError, match="passage_count"):
            PairPassagesFactory(passage_count=0)

    def test_page_must_fit_the_total(self) -> None:
        with pytest.raises(ValidationError, match="cannot exceed"):
            PairPassagesFactory(offset=5)

    def test_basis_only_with_no_transcript(self) -> None:
        empty = PairPassagesFactory(
            items=[], state="no_transcript", basis_when_empty="tag"
        )
        assert empty.basis_when_empty == "tag"
        with pytest.raises(ValidationError, match="basis_when_empty"):
            PairPassagesFactory(
                items=[], state="no_passage_in_window", basis_when_empty="tag"
            )

    def test_closest_gap_is_none_exactly_without_videos(self) -> None:
        with pytest.raises(ValidationError, match="closest_gap_seconds"):
            PairPassagesFactory(closest_gap_seconds=None)
        with pytest.raises(ValidationError, match="closest_gap_seconds"):
            PairPassagesFactory(items=[], state="not_computed", closest_gap_seconds=3.0)

    def test_truncated_when_more_videos_remain(self) -> None:
        response = PairPassagesFactory(video_count=3, passage_count=3)
        assert response.truncated is True

    def test_window_outside_the_four_values_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PairPassagesFactory(window_seconds=45)
