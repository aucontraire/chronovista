"""Pure-assembly tests for ``EntityMentionRepository.co_occurrence_evidence`` (Feature 114, T009).

Only the DB-free pieces are isolated here: ``_EvPair.sort_key``, ``_group_videos`` and
``_non_transcript_basis``. The three SQL queries (gate / locate / render) are deliberately NOT
mocked row-by-row; that path is crossed against a real database in
``tests/integration/api/test_connection_evidence_api.py``.
"""

from __future__ import annotations

import uuid

import pytest

from chronovista.repositories.entity_mention_repository import (
    EntityMentionRepository,
    _EvMention,
    _EvPair,
)

A = uuid.UUID("00000000-0000-0000-0000-00000000000a")
B = uuid.UUID("00000000-0000-0000-0000-00000000000b")
OTHER = uuid.UUID("00000000-0000-0000-0000-00000000000c")


def _mention(
    entity_id: uuid.UUID,
    seq: int,
    *,
    video_id: str = "vid_1",
    language: str = "en",
    text: str = "surface",
) -> _EvMention:
    return _EvMention(
        entity_id=entity_id,
        video_id=video_id,
        language_code=language,
        segment_id=seq + 1000,
        end_segment_id=None,
        mention_text=text,
        match_start=0,
        match_end=len(text),
        detection_method="rule_match",
        sequence_number=seq,
        start_time=float(seq),
    )


def _pair(
    seq_a: int,
    seq_b: int,
    *,
    video_id: str = "vid_1",
    language: str = "en",
    text_a: str = "alpha",
    text_b: str = "beta",
) -> _EvPair:
    return _EvPair(
        video_id,
        language,
        _mention(A, seq_a, video_id=video_id, language=language, text=text_a),
        _mention(B, seq_b, video_id=video_id, language=language, text=text_b),
    )


class TestEvPair:
    def test_separation_is_absolute_regardless_of_order(self) -> None:
        assert _pair(10, 4).separation == 6
        assert _pair(4, 10).separation == 6

    def test_sort_key_orders_by_separation_first(self) -> None:
        close = _pair(5, 6, video_id="zzz")
        far = _pair(1, 50, video_id="aaa")
        assert close.sort_key < far.sort_key

    def test_sort_key_tie_break_is_total_and_deterministic(self) -> None:
        # Same separation: video, language, then sequence numbers decide.
        pairs = [
            _pair(3, 5, video_id="vid_b"),
            _pair(1, 3, video_id="vid_a", language="en"),
            _pair(1, 3, video_id="vid_a", language="de"),
            _pair(0, 2, video_id="vid_a", language="en"),
        ]
        ordered = sorted(pairs, key=lambda p: p.sort_key)
        assert ordered == sorted([*pairs[2:], *pairs[:2]], key=lambda p: p.sort_key)
        assert [
            (p.video_id, p.language_code, p.ma.sequence_number) for p in ordered
        ] == [
            ("vid_a", "de", 1),
            ("vid_a", "en", 0),
            ("vid_a", "en", 1),
            ("vid_b", "en", 3),
        ]
        assert len({p.sort_key for p in pairs}) == len(pairs)


class TestGroupVideos:
    """FR-009 video grain + FR-016 no-collapse, tested on the pure ``_group_videos`` helper."""

    def test_representative_is_the_videos_min_separation_variant(self) -> None:
        near = _pair(1, 2, video_id="v1", language="en")
        far = _pair(1, 40, video_id="v1", language="de")
        grouped = EntityMentionRepository._group_videos([far, near])
        assert len(grouped) == 1
        rep, others = grouped[0]
        assert rep is near  # closest wins, regardless of language
        assert others == [far]

    def test_other_variants_are_ordered_closest_first(self) -> None:
        near = _pair(1, 2, video_id="v1", language="en")  # sep 1
        mid = _pair(1, 5, video_id="v1", language="it")  # sep 4
        far = _pair(1, 10, video_id="v1", language="de")  # sep 9
        rep, others = EntityMentionRepository._group_videos([far, near, mid])[0]
        assert rep is near
        assert others == [mid, far]

    def test_single_language_video_has_no_other_variants(self) -> None:
        only = _pair(3, 5, video_id="v1", language="en")
        rep, others = EntityMentionRepository._group_videos([only])[0]
        assert rep is only
        assert others == []

    def test_videos_are_ordered_closest_first_by_representative(self) -> None:
        v1_far = _pair(1, 30, video_id="v1", language="en")
        v2_near = _pair(1, 2, video_id="v2", language="en")
        grouped = EntityMentionRepository._group_videos([v1_far, v2_near])
        assert [rep.video_id for rep, _ in grouped] == ["v2", "v1"]

    def test_distinct_videos_sharing_a_surface_form_are_both_kept(self) -> None:
        # The anti-collapse invariant (the bug this redesign fixes): identical surface forms in
        # DIFFERENT videos must never merge — each video is its own audit row.
        v1 = _pair(1, 3, video_id="v1", text_a="alpha", text_b="beta")
        v2 = _pair(1, 4, video_id="v2", text_a="Alpha", text_b="BETA")
        grouped = EntityMentionRepository._group_videos([v1, v2])
        assert len(grouped) == 2
        assert {rep.video_id for rep, _ in grouped} == {"v1", "v2"}


class TestNonTranscriptBasis:
    def test_none_when_no_shared_non_transcript_video(self) -> None:
        triples = [(A, "v1", "title"), (B, "v2", "title")]
        assert EntityMentionRepository._non_transcript_basis(triples, A, B) is None

    def test_names_shared_source(self) -> None:
        triples = [(A, "v1", "description"), (B, "v1", "description")]
        assert (
            EntityMentionRepository._non_transcript_basis(triples, A, B)
            == "description"
        )

    def test_never_reports_transcript(self) -> None:
        triples = [(A, "v1", "transcript"), (B, "v1", "transcript")]
        assert EntityMentionRepository._non_transcript_basis(triples, A, B) is None

    def test_sources_must_match_on_the_same_video_and_source(self) -> None:
        # A via title on v1, B via tag on v1: different sources -> no shared basis.
        triples = [(A, "v1", "title"), (B, "v1", "tag")]
        assert EntityMentionRepository._non_transcript_basis(triples, A, B) is None

    def test_priority_order_title_before_tag(self) -> None:
        triples = [
            (A, "v1", "tag"),
            (B, "v1", "tag"),
            (A, "v2", "title"),
            (B, "v2", "title"),
        ]
        assert EntityMentionRepository._non_transcript_basis(triples, A, B) == "title"

    def test_ignores_unrelated_entities(self) -> None:
        triples = [(OTHER, "v1", "title"), (A, "v1", "title")]
        assert EntityMentionRepository._non_transcript_basis(triples, A, B) is None


@pytest.mark.parametrize("seq_a,seq_b", [(0, 0), (7, 7)])
def test_zero_separation_is_valid(seq_a: int, seq_b: int) -> None:
    assert _pair(seq_a, seq_b).separation == 0
