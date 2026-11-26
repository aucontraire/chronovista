"""``MentionSpan``: which of two mentions of one occurrence survives, and what part of
a segment a mention covers (#426). Placeholder values only."""

from __future__ import annotations

import uuid

import pytest

from chronovista.repositories.entity_mention_repository import MentionSpan

_ENTITY = uuid.UUID(int=1)


def _span(
    *,
    mention_id: str = "00000000-0000-7000-8000-000000000001",
    text: str = "Zeta Quux",
    method: str = "rule_match",
    segment_id: int = 1,
    end_segment_id: int | None = None,
    start: int = 0,
    end: int = 9,
    counts: bool = True,
) -> MentionSpan:
    return MentionSpan(
        id=uuid.UUID(mention_id),
        entity_id=_ENTITY,
        video_id="vid00000001",
        language_code="en",
        segment_id=segment_id,
        end_segment_id=end_segment_id,
        match_start=start,
        match_end=end,
        mention_text=text,
        detection_method=method,
        counts=counts,
    )


class TestSurvivorRank:
    """The rule the correction rebase and the repair share. Lowest rank survives."""

    def test_a_counted_name_beats_a_longer_uncounted_gap_span(self) -> None:
        """Keeping one row never loses a counted occurrence. A
        disfluency-gap span is longer than the clean name inside it but does not
        count. Mutation: drop the counts term (the gap span would win on length)."""
        clean = _span(text="Zeta Quux", counts=True)
        gap = _span(
            mention_id="00000000-0000-7000-8000-000000000000",
            text="Zeta Zeta Quux",
            counts=False,
        )
        assert clean.survivor_rank() < gap.survivor_rank()

    def test_the_longer_name_beats_the_shorter_whatever_wrote_it(self) -> None:
        """Mutation: drop the length term, or flip its sign."""
        full_by_scan = _span(text="Zeta Quux", method="rule_match")
        fragment_by_person = _span(text="Quux", method="user_correction")
        assert full_by_scan.survivor_rank() < fragment_by_person.survivor_rank()

    @pytest.mark.parametrize("scan_method", ["rule_match", "asr_match"])
    def test_at_equal_length_a_correction_beats_a_scan_match(
        self, scan_method: str
    ) -> None:
        """A person tagged it. Mutation: flip the scan-owned term."""
        correction = _span(method="user_correction")
        scan = _span(method=scan_method)
        assert correction.survivor_rank() < scan.survivor_rank()

    def test_at_equal_length_and_kind_the_older_row_wins(self) -> None:
        """Ids are UUIDv7, so their text sorts by creation. Mutation: drop the id
        term (ties would resolve by input order)."""
        older = _span(mention_id="00000000-0000-7000-8000-000000000001")
        newer = _span(mention_id="00000000-0000-7000-8000-000000000002")
        assert older.survivor_rank() < newer.survivor_rank()

    def test_sorting_puts_the_survivor_first(self) -> None:
        spans = [
            _span(
                mention_id="00000000-0000-7000-8000-000000000003",
                text="Quux",
                method="user_correction",
            ),
            _span(
                mention_id="00000000-0000-7000-8000-000000000002",
                method="rule_match",
            ),
            _span(
                mention_id="00000000-0000-7000-8000-000000000001",
                method="user_correction",
            ),
        ]
        ordered = sorted(spans, key=lambda s: s.survivor_rank())
        assert [str(s.id)[-1] for s in ordered] == ["1", "2", "3"]


class TestPartIn:
    def test_a_single_segment_mention_covers_its_own_offsets(self) -> None:
        assert _span(start=3, end=8).part_in(1, 50) == (3, 8)

    def test_a_split_mention_covers_the_tail_of_its_start_segment(self) -> None:
        assert _span(segment_id=1, end_segment_id=2, start=7, end=4).part_in(1, 11) == (
            7,
            11,
        )

    def test_a_split_mention_covers_the_head_of_its_end_segment(self) -> None:
        assert _span(segment_id=1, end_segment_id=2, start=7, end=4).part_in(2, 12) == (
            0,
            4,
        )
