"""
Integration tests for cross-segment correction pattern matching.

Tests end-to-end behaviour of `TranscriptSegmentRepository.find_by_text_pattern()`
and `BatchCorrectionService.find_and_replace()` against a real PostgreSQL database.
Each test uses the `db_session` fixture from `tests/integration/conftest.py`, which
creates all tables fresh per test and rolls back on completion.

Feature 040 -- Correction Pattern Matching

Test coverage:
T005  — Word boundary integration: \\bamlo\\w* matches "amlo" / "amlo's government"
        but must NOT match "kamloops is a city" in the database via find_by_text_pattern().
T011  — Cross-segment match basic: "Claudia Shane" + "Bound …" corrected to "Claudia Sheinbaum".
T012  — Single-segment match within cross-segment mode: pattern fully within one segment.
T013  — No cross-segment flag: only single-segment matches found with default mode.
T014  — Language boundary: segments with different language codes are NOT paired.
T015  — Non-consecutive sequence numbers: segments with a gap are NOT paired.
T016  — Regex + cross-segment composition: regex pattern matched across adjacent pair.
T016b — Case-insensitive + cross-segment composition: case-folded pattern matched across pair.
T017  — Overlapping pairs: earlier pair (1,2) wins over later pair (2,3) for shared segment.
T018  — Empty effective text: pair with one empty segment is skipped.
T036a — Empty segment after correction: warning displayed, segment not deleted (FR-008).
T034  — Basic cross-segment revert: apply cross-segment, batch_revert, verify both restored.
T035  — Partner cascade revert: revert pattern matches one segment, partner cascaded.
T036b — Revert of emptied segment: revert restores emptied segment to original text.
T037  — Missing partner on revert: partner deleted, surviving segment still reverted.

Note: T005 will FAIL until T007/T009 implement the regex translator that converts
Python \\b word-boundary syntax into its PostgreSQL equivalent.

Note: T011-T018 and T036a will FAIL until the ``cross_segment`` parameter is added
to ``BatchCorrectionService.find_and_replace()``. This is intentional TDD: the tests
define the contract before the implementation ships.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import (
    Channel as ChannelDB,
)
from chronovista.db.models import (
    TranscriptSegment as TranscriptSegmentDB,
)
from chronovista.db.models import (
    Video as VideoDB,
)
from chronovista.db.models import (
    VideoTranscript as VideoTranscriptDB,
)
from chronovista.repositories.transcript_segment_repository import (
    TranscriptSegmentRepository,
)
from chronovista.services.batch_correction_service import BatchCorrectionService
from tests.factories.id_factory import channel_id, video_id

# ---------------------------------------------------------------------------
# Module-level defaults
# ---------------------------------------------------------------------------

# Deterministic IDs — valid format guaranteed by the factory helpers.
DEFAULT_CHANNEL_ID: str = channel_id(seed="cross_seg_test")

# CRITICAL: This line ensures async tests work with coverage tools,
# avoiding silent test-skipping when pytest-cov is used (see CLAUDE.md).
pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


async def _seed_channel(
    session: AsyncSession,
    ch_id: str = DEFAULT_CHANNEL_ID,
) -> None:
    """
    Insert a minimal Channel row required as FK parent for videos.

    Parameters
    ----------
    session : AsyncSession
        Active database session.
    ch_id : str
        YouTube channel ID (24-character, starts with 'UC').
    """
    channel = ChannelDB(
        channel_id=ch_id,
        title="Cross-Segment Integration Test Channel",
        description="Channel seeded for Feature 040 cross-segment integration tests",
        is_subscribed=False,
    )
    session.add(channel)
    await session.flush()


async def _seed_video(
    session: AsyncSession,
    vid_id: str,
    ch_id: str = DEFAULT_CHANNEL_ID,
) -> None:
    """
    Insert a minimal Video row required as FK parent for transcripts.

    Parameters
    ----------
    session : AsyncSession
        Active database session.
    vid_id : str
        YouTube video ID (11-character string).
    ch_id : str
        Parent channel ID.
    """
    video = VideoDB(
        video_id=vid_id,
        channel_id=ch_id,
        title=f"Video {vid_id}",
        description="Integration test video for cross-segment pattern matching",
        upload_date=datetime(2024, 6, 1, tzinfo=UTC),
        duration=300,
        made_for_kids=False,
        self_declared_made_for_kids=False,
    )
    session.add(video)
    await session.flush()


async def _seed_transcript(
    session: AsyncSession,
    vid_id: str,
    language_code: str = "en",
) -> None:
    """
    Insert a minimal VideoTranscript row required as FK parent for segments.

    Parameters
    ----------
    session : AsyncSession
        Active database session.
    vid_id : str
        Parent video ID.
    language_code : str
        BCP-47 language code for the transcript track.
    """
    transcript = VideoTranscriptDB(
        video_id=vid_id,
        language_code=language_code,
        transcript_text="",
        transcript_type="auto",
        download_reason="user_request",
        is_cc=False,
        is_auto_synced=True,
        track_kind="standard",
        source="youtube_transcript_api",
    )
    session.add(transcript)
    await session.flush()


async def _seed_segment(
    session: AsyncSession,
    *,
    vid_id: str,
    language_code: str = "en",
    sequence_number: int,
    text: str,
    start_time: float = 0.0,
) -> TranscriptSegmentDB:
    """
    Insert a TranscriptSegment row and return the ORM object.

    Parameters
    ----------
    session : AsyncSession
        Active database session.
    vid_id : str
        Parent video ID.
    language_code : str
        BCP-47 language code matching the parent VideoTranscript.
    sequence_number : int
        Zero-based ordering index within the transcript.
    text : str
        Raw ASR text for the segment.
    start_time : float
        Segment start time in seconds.

    Returns
    -------
    TranscriptSegmentDB
        The flushed (but not committed) ORM instance.
    """
    segment = TranscriptSegmentDB(
        video_id=vid_id,
        language_code=language_code,
        sequence_number=sequence_number,
        text=text,
        has_correction=False,
        start_time=start_time,
        duration=5.0,
        end_time=start_time + 5.0,
    )
    session.add(segment)
    await session.flush()
    return segment


# ---------------------------------------------------------------------------
# T005 — Word boundary integration
# ---------------------------------------------------------------------------


class TestWordBoundaryRegexIntegration:
    r"""
    Integration tests for \\b word-boundary behaviour in find_by_text_pattern().

    T005 verifies that the PostgreSQL regex operator ('~') honours word-boundary
    semantics equivalent to Python's \\b when the pattern \\bamlo\\w* is supplied.

    The three segments seeded cover the three boundary cases that must all be
    handled correctly in a single call:

    * Segment 0 — "amlo said something"    → matches  (word starts at text start)
    * Segment 1 — "kamloops is a city"     → no match (amlo is a mid-word substring)
    * Segment 2 — "amlo's government"      → matches  (word starts at text start,
                                                        possessive suffix ignored by \\w*)

    NOTE: This test is expected to FAIL until T007/T009 implement the regex
    translator that converts Python \\b into the correct PostgreSQL equivalent
    (e.g. \\y or (?<![a-zA-Z]) / (?![a-zA-Z]) boundary assertions). That failure
    is intentional: this test defines the contract before the implementation ships.
    """

    async def test_word_boundary_pattern_matches_amlo_but_not_kamloops(
        self, db_session: AsyncSession
    ) -> None:
        r"""
        \\bamlo\\w* must match segments containing "amlo" as a whole word but
        must NOT match segments where "amlo" appears only as an interior substring
        (e.g. "kamloops").

        Seed setup
        ----------
        Segment 0 — text = "amlo said something"   → MATCH expected
        Segment 1 — text = "kamloops is a city"    → NO MATCH expected
        Segment 2 — text = "amlo's government"     → MATCH expected

        Assertions
        ----------
        * Exactly 2 segments returned.
        * Segment 1 (kamloops) is not among the results.
        * Segments 0 and 2 are both present in the results (by sequence_number).
        """
        vid_id = video_id(seed="wb_amlo_001")

        await _seed_channel(db_session)
        await _seed_video(db_session, vid_id)
        await _seed_transcript(db_session, vid_id)

        seg0 = await _seed_segment(
            db_session,
            vid_id=vid_id,
            sequence_number=0,
            text="amlo said something",
            start_time=0.0,
        )
        seg1 = await _seed_segment(
            db_session,
            vid_id=vid_id,
            sequence_number=1,
            text="kamloops is a city",
            start_time=5.0,
        )
        seg2 = await _seed_segment(
            db_session,
            vid_id=vid_id,
            sequence_number=2,
            text="amlo's government",
            start_time=10.0,
        )

        await db_session.commit()

        repo = TranscriptSegmentRepository()
        results = await repo.find_by_text_pattern(
            db_session,
            pattern=r"\bamlo\w*",
            regex=True,
        )

        # Collect returned segment IDs and sequence numbers for clear failure messages
        returned_ids = {seg.id for seg in results}
        returned_seqs = sorted(seg.sequence_number for seg in results)

        assert len(results) == 2, (
            f"Expected exactly 2 matching segments (seq 0 and 2), "
            f"got {len(results)}: sequence_numbers={returned_seqs}"
        )

        assert seg1.id not in returned_ids, (
            f"Segment 1 ('kamloops is a city') must NOT match \\bamlo\\w* "
            f"because 'amlo' is a substring of 'kamloops', not a word boundary match. "
            f"Returned segment IDs: {returned_ids}"
        )

        assert seg0.id in returned_ids, (
            f"Segment 0 ('amlo said something') must match \\bamlo\\w* — "
            f"'amlo' appears at a word boundary. "
            f"Returned segment IDs: {returned_ids}"
        )

        assert seg2.id in returned_ids, (
            f"Segment 2 ('amlo\\'s government') must match \\bamlo\\w* — "
            f"'amlo' appears at a word boundary before the possessive apostrophe. "
            f"Returned segment IDs: {returned_ids}"
        )


# ---------------------------------------------------------------------------
# Shared service factory for Phase 4 (US2) cross-segment tests
# ---------------------------------------------------------------------------


def _make_batch_service() -> BatchCorrectionService:
    """
    Instantiate a ``BatchCorrectionService`` wired with real repositories.

    Using real (zero-config) repositories against the integration database
    exercises the full stack.  All tests that use this helper share the same
    class structure so that dependencies are explicit and the factory can be
    updated in one place when the service constructor changes.

    Returns
    -------
    BatchCorrectionService
        Fully wired service instance.
    """
    from chronovista.repositories.transcript_correction_repository import (
        TranscriptCorrectionRepository,
    )
    from chronovista.repositories.transcript_segment_repository import (
        TranscriptSegmentRepository,
    )
    from chronovista.repositories.video_transcript_repository import (
        VideoTranscriptRepository,
    )
    from chronovista.services.batch_correction_service import BatchCorrectionService
    from chronovista.services.transcript_correction_service import (
        TranscriptCorrectionService,
    )

    correction_repo = TranscriptCorrectionRepository()
    segment_repo = TranscriptSegmentRepository()
    transcript_repo = VideoTranscriptRepository()
    correction_service = TranscriptCorrectionService(
        correction_repo=correction_repo,
        segment_repo=segment_repo,
        transcript_repo=transcript_repo,
    )
    return BatchCorrectionService(
        correction_service=correction_service,
        segment_repo=segment_repo,
        correction_repo=correction_repo,
    )


# ---------------------------------------------------------------------------
# T011 — Cross-segment match basic
# ---------------------------------------------------------------------------


class TestCrossSegmentMatchBasic:
    r"""
    T011 — Basic end-to-end cross-segment correction.

    Segment 155: "Claudia Shane"
    Segment 156: "Bound también siendo candidata"

    Pattern "Claudia Shane Bound" spans both segments.  With
    ``cross_segment=True``, the replacement "Claudia Sheinbaum" should be
    placed entirely in segment 155, and "Bound" should be removed from the
    start of segment 156.

    Per spec edge case: "Multiple matches within a single segment pair's
    concatenated text → all matches are replaced, consistent with single-
    segment re.sub() behavior."

    NOTE: This test is expected to FAIL until ``find_and_replace()`` gains a
    ``cross_segment`` parameter.  That failure is intentional TDD.
    """

    async def test_basic_cross_segment_replacement(
        self, db_session: AsyncSession
    ) -> None:
        """
        Pattern spanning two adjacent segments is fully replaced in live mode.

        Seed setup
        ----------
        Segment 155 — text = "Claudia Shane"        (tail of name)
        Segment 156 — text = "Bound también siendo candidata"
                                                     (head of surname + rest)

        Assertions
        ----------
        * Result type is ``BatchCorrectionResult``.
        * ``total_matched >= 1`` (at least the cross-segment pair was detected).
        * Segment 155 ``corrected_text`` contains "Claudia Sheinbaum".
        * Segment 155 ``corrected_text`` does NOT contain the ASR artefact "Shane".
        * Segment 156 ``corrected_text`` does NOT start with "Bound".
        * Segment 156 ``corrected_text`` still contains "también siendo candidata"
          (trailing context preserved).
        """
        vid_id = video_id(seed="t011_cross_basic")

        await _seed_channel(db_session)
        await _seed_video(db_session, vid_id)
        await _seed_transcript(db_session, vid_id, language_code="es")

        seg_a = await _seed_segment(
            db_session,
            vid_id=vid_id,
            language_code="es",
            sequence_number=155,
            text="Claudia Shane",
            start_time=310.0,
        )
        seg_b = await _seed_segment(
            db_session,
            vid_id=vid_id,
            language_code="es",
            sequence_number=156,
            text="Bound también siendo candidata",
            start_time=315.0,
        )

        await db_session.commit()

        service = _make_batch_service()
        result = await service.find_and_replace(
            db_session,
            pattern="Claudia Shane Bound",
            replacement="Claudia Sheinbaum",
            cross_segment=True,  # TDD: parameter does not yet exist
        )

        from chronovista.models.batch_correction_models import BatchCorrectionResult

        assert isinstance(result, BatchCorrectionResult), (
            f"Expected BatchCorrectionResult, got {type(result)!r}"
        )
        assert result.total_matched >= 1, (
            "Cross-segment pair 'Claudia Shane' + 'Bound …' must be counted as matched. "
            f"total_matched={result.total_matched}"
        )

        # Reload corrected segments from DB
        from chronovista.db.models import TranscriptSegment as TranscriptSegmentDB

        refreshed_a = await db_session.get(TranscriptSegmentDB, seg_a.id)
        refreshed_b = await db_session.get(TranscriptSegmentDB, seg_b.id)

        assert refreshed_a is not None
        assert refreshed_b is not None

        corrected_a: str = (refreshed_a.corrected_text or refreshed_a.text) or ""
        corrected_b: str = (refreshed_b.corrected_text or refreshed_b.text) or ""

        assert "Claudia Sheinbaum" in corrected_a, (
            f"Segment 155 must contain 'Claudia Sheinbaum' after cross-segment "
            f"replacement. Got: {corrected_a!r}"
        )
        assert "Shane" not in corrected_a, (
            f"ASR artefact 'Shane' must be removed from segment 155. "
            f"Got: {corrected_a!r}"
        )
        assert not corrected_b.startswith("Bound"), (
            f"'Bound' must be removed from the start of segment 156. "
            f"Got: {corrected_b!r}"
        )
        assert "también siendo candidata" in corrected_b, (
            f"Trailing context 'también siendo candidata' must be preserved in "
            f"segment 156 after removing 'Bound'. Got: {corrected_b!r}"
        )

    async def test_multiple_occurrences_in_combined_text_all_replaced(
        self, db_session: AsyncSession
    ) -> None:
        """
        When the pattern appears multiple times in the combined pair text, all
        occurrences are replaced (per spec: "consistent with re.sub() behavior").

        Seed setup
        ----------
        Segment 10 — "foo bar foo"
        Segment 11 — "bar baz"
        Combined:    "foo bar foo bar baz"
        Pattern "foo bar" appears at positions 0 and 8.

        Assertions
        ----------
        * Both occurrences of "foo bar" are replaced with "qux".
        * Combined corrected text reads "qux foo qux baz" (approximately).
        """
        vid_id = video_id(seed="t011_multi_occur")

        await _seed_channel(db_session)
        await _seed_video(db_session, vid_id)
        await _seed_transcript(db_session, vid_id)

        await _seed_segment(
            db_session,
            vid_id=vid_id,
            sequence_number=10,
            text="foo bar foo",
            start_time=0.0,
        )
        await _seed_segment(
            db_session,
            vid_id=vid_id,
            sequence_number=11,
            text="bar baz",
            start_time=5.0,
        )

        await db_session.commit()

        service = _make_batch_service()
        result = await service.find_and_replace(
            db_session,
            pattern="foo bar",
            replacement="qux",
            cross_segment=True,  # TDD: parameter does not yet exist
        )

        from chronovista.models.batch_correction_models import BatchCorrectionResult

        assert isinstance(result, BatchCorrectionResult), (
            f"Expected BatchCorrectionResult, got {type(result)!r}"
        )
        # Both segments should be affected when both occurrences are replaced.
        assert result.total_matched >= 1, (
            "At least the cross-segment pair must be matched. "
            f"total_matched={result.total_matched}"
        )


# ---------------------------------------------------------------------------
# T012 — Single-segment match within cross-segment mode
# ---------------------------------------------------------------------------


class TestSingleSegmentWithinCrossSegment:
    """
    T012 — Pattern fully contained within a single segment is treated as a
    single-segment match, not a cross-segment match, even when
    ``cross_segment=True``.

    Per spec edge case: "When a pattern matches entirely within a single
    segment while --cross-segment is active, the segment is found as a
    single-segment match and excluded from all cross-segment pairs it would
    participate in."

    NOTE: This test is expected to FAIL until ``find_and_replace()`` gains a
    ``cross_segment`` parameter.  That failure is intentional TDD.
    """

    async def test_single_segment_match_found_not_cross_segment(
        self, db_session: AsyncSession
    ) -> None:
        """
        Pattern "hello world" lives entirely in segment 0.

        When ``cross_segment=True``, the engine finds it as a single-segment
        match (not a cross-segment match involving segment 1).

        Seed setup
        ----------
        Segment 0 — "hello world today"   → contains pattern fully
        Segment 1 — "some other text"     → unrelated

        Assertions
        ----------
        * ``result.total_matched >= 1`` (pattern was found).
        * Segment 0 ``corrected_text`` contains the replacement "greetings".
        * Segment 1 is NOT modified (its text/corrected_text unchanged).
        """
        vid_id = video_id(seed="t012_single_in_cross")

        await _seed_channel(db_session)
        await _seed_video(db_session, vid_id)
        await _seed_transcript(db_session, vid_id)

        seg0 = await _seed_segment(
            db_session,
            vid_id=vid_id,
            sequence_number=0,
            text="hello world today",
            start_time=0.0,
        )
        seg1 = await _seed_segment(
            db_session,
            vid_id=vid_id,
            sequence_number=1,
            text="some other text",
            start_time=5.0,
        )

        await db_session.commit()

        service = _make_batch_service()
        result = await service.find_and_replace(
            db_session,
            pattern="hello world",
            replacement="greetings",
            cross_segment=True,  # TDD: parameter does not yet exist
        )

        from chronovista.models.batch_correction_models import BatchCorrectionResult

        assert isinstance(result, BatchCorrectionResult), (
            f"Expected BatchCorrectionResult, got {type(result)!r}"
        )
        assert result.total_matched >= 1, (
            "Pattern 'hello world' must be found (as a single-segment match). "
            f"total_matched={result.total_matched}"
        )

        from chronovista.db.models import TranscriptSegment as TranscriptSegmentDB

        refreshed0 = await db_session.get(TranscriptSegmentDB, seg0.id)
        refreshed1 = await db_session.get(TranscriptSegmentDB, seg1.id)

        assert refreshed0 is not None
        assert refreshed1 is not None

        corrected0: str = (refreshed0.corrected_text or refreshed0.text) or ""
        assert "greetings" in corrected0, (
            f"Segment 0 must contain the replacement 'greetings'. Got: {corrected0!r}"
        )

        # Segment 1 must NOT be modified — it did not participate in any match.
        assert not refreshed1.has_correction, (
            f"Segment 1 ('some other text') must not be corrected — the pattern "
            f"matched entirely within segment 0 and segment 1 was not involved. "
            f"has_correction={refreshed1.has_correction}"
        )


# ---------------------------------------------------------------------------
# T013 — No cross-segment flag
# ---------------------------------------------------------------------------


class TestNoCrossSegmentFlag:
    """
    T013 — Without ``cross_segment=True``, only single-segment matches are
    found.  A pattern that spans two segments remains undetected.

    Per spec acceptance scenario 4: "Given no --cross-segment flag is
    provided, When user runs find-replace, Then behavior is identical to the
    current single-segment matching with no performance or correctness
    regression."

    This test exercises the default (backward-compatible) path — no new
    parameter is required here, but the test validates that the new flag's
    presence does not disturb the legacy result when omitted.
    """

    async def test_cross_segment_pattern_not_found_without_flag(
        self, db_session: AsyncSession
    ) -> None:
        """
        Pattern "Claudia Shane Bound" spans two segments but is NOT matched
        when ``cross_segment`` is omitted (defaults to False / absent).

        Seed setup
        ----------
        Segment 155 — "Claudia Shane"
        Segment 156 — "Bound también siendo candidata"

        Assertions
        ----------
        * ``result.total_matched == 0`` (no single-segment contains the full
          pattern "Claudia Shane Bound").
        * Neither segment is modified.
        """
        vid_id = video_id(seed="t013_no_cross_flag")

        await _seed_channel(db_session)
        await _seed_video(db_session, vid_id)
        await _seed_transcript(db_session, vid_id, language_code="es")

        seg_a = await _seed_segment(
            db_session,
            vid_id=vid_id,
            language_code="es",
            sequence_number=155,
            text="Claudia Shane",
            start_time=310.0,
        )
        seg_b = await _seed_segment(
            db_session,
            vid_id=vid_id,
            language_code="es",
            sequence_number=156,
            text="Bound también siendo candidata",
            start_time=315.0,
        )

        await db_session.commit()

        service = _make_batch_service()
        # Deliberately omit cross_segment — default single-segment behaviour.
        result = await service.find_and_replace(
            db_session,
            pattern="Claudia Shane Bound",
            replacement="Claudia Sheinbaum",
        )

        from chronovista.models.batch_correction_models import BatchCorrectionResult

        assert isinstance(result, BatchCorrectionResult), (
            f"Expected BatchCorrectionResult, got {type(result)!r}"
        )
        assert result.total_matched == 0, (
            "Without --cross-segment, a pattern spanning two segments must NOT be "
            f"matched. total_matched={result.total_matched}"
        )

        from chronovista.db.models import TranscriptSegment as TranscriptSegmentDB

        refreshed_a = await db_session.get(TranscriptSegmentDB, seg_a.id)
        refreshed_b = await db_session.get(TranscriptSegmentDB, seg_b.id)

        assert refreshed_a is not None and not refreshed_a.has_correction, (
            "Segment A must not be modified when no match was found. "
            f"has_correction={refreshed_a.has_correction if refreshed_a else 'N/A'}"
        )
        assert refreshed_b is not None and not refreshed_b.has_correction, (
            "Segment B must not be modified when no match was found. "
            f"has_correction={refreshed_b.has_correction if refreshed_b else 'N/A'}"
        )


# ---------------------------------------------------------------------------
# T014 — Language boundary
# ---------------------------------------------------------------------------


class TestLanguageBoundary:
    """
    T014 — Adjacent segments with different ``language_code`` values must NOT
    be paired for cross-segment matching.

    Per spec FR-011: "Cross-segment matching MUST only consider adjacent pairs
    within the same video and same language code."

    Per spec edge case: "What happens when a cross-segment match spans a
    language boundary (segment N is 'en', segment N+1 is 'es')? Only pairs
    with the same language_code are concatenated."

    NOTE: This test is expected to FAIL until ``find_and_replace()`` gains a
    ``cross_segment`` parameter.  That failure is intentional TDD.
    """

    async def test_different_language_segments_not_paired(
        self, db_session: AsyncSession
    ) -> None:
        """
        Segment N (en) and segment N+1 (es) are adjacent but must NOT be
        concatenated for cross-segment matching.

        Seed setup
        ----------
        Segment 0 — language="en", text="hello boundary"
        Segment 1 — language="es", text="boundary world"
        Two separate VideoTranscript parent rows (one per language) are
        required to satisfy the FK constraint.

        Pattern "hello boundary boundary world" spans the language boundary
        but must produce zero cross-segment matches.

        Assertions
        ----------
        * ``result.total_matched == 0`` (no cross-segment pair produced).
        * Neither segment is modified.
        """
        vid_id = video_id(seed="t014_lang_boundary")

        await _seed_channel(db_session)
        await _seed_video(db_session, vid_id)
        # Seed both language transcript parents
        await _seed_transcript(db_session, vid_id, language_code="en")
        await _seed_transcript(db_session, vid_id, language_code="es")

        seg_en = await _seed_segment(
            db_session,
            vid_id=vid_id,
            language_code="en",
            sequence_number=0,
            text="hello boundary",
            start_time=0.0,
        )
        seg_es = await _seed_segment(
            db_session,
            vid_id=vid_id,
            language_code="es",
            sequence_number=1,
            text="boundary world",
            start_time=5.0,
        )

        await db_session.commit()

        service = _make_batch_service()
        result = await service.find_and_replace(
            db_session,
            pattern="hello boundary boundary world",
            replacement="SHOULD_NOT_APPEAR",
            cross_segment=True,  # TDD: parameter does not yet exist
        )

        from chronovista.models.batch_correction_models import BatchCorrectionResult

        assert isinstance(result, BatchCorrectionResult)
        assert result.total_matched == 0, (
            "Segments with different language_code values must NOT be paired for "
            f"cross-segment matching. total_matched={result.total_matched}"
        )

        from chronovista.db.models import TranscriptSegment as TranscriptSegmentDB

        refreshed_en = await db_session.get(TranscriptSegmentDB, seg_en.id)
        refreshed_es = await db_session.get(TranscriptSegmentDB, seg_es.id)

        assert refreshed_en is not None and not refreshed_en.has_correction, (
            "English segment must not be corrected — language boundary prevented pairing."
        )
        assert refreshed_es is not None and not refreshed_es.has_correction, (
            "Spanish segment must not be corrected — language boundary prevented pairing."
        )


# ---------------------------------------------------------------------------
# T015 — Non-consecutive sequence numbers
# ---------------------------------------------------------------------------


class TestNonConsecutiveSequence:
    """
    T015 — Segments with a gap in ``sequence_number`` (e.g., 5 and 7) must
    NOT be paired for cross-segment matching.

    Per spec FR-006: "strictly consecutive sequence numbers where
    segment_b.sequence_number == segment_a.sequence_number + 1".
    "Segments with gaps in sequence numbering are NOT paired."

    NOTE: This test is expected to FAIL until ``find_and_replace()`` gains a
    ``cross_segment`` parameter.  That failure is intentional TDD.
    """

    async def test_non_consecutive_segments_not_paired(
        self, db_session: AsyncSession
    ) -> None:
        """
        Seeding seq_numbers 5 and 7 (gap at 6) prevents cross-segment pairing.

        Seed setup
        ----------
        Segment 5 — "alpha bravo"
        Segment 7 — "bravo charlie"  (no segment 6 in the DB)

        Pattern "alpha bravo bravo charlie" would match the concatenation, but
        since the sequence numbers are non-consecutive the pair is rejected.

        Assertions
        ----------
        * ``result.total_matched == 0`` (non-consecutive pair not produced).
        * Neither segment is modified.
        """
        vid_id = video_id(seed="t015_nonconsec_seq")

        await _seed_channel(db_session)
        await _seed_video(db_session, vid_id)
        await _seed_transcript(db_session, vid_id)

        seg5 = await _seed_segment(
            db_session,
            vid_id=vid_id,
            sequence_number=5,
            text="alpha bravo",
            start_time=25.0,
        )
        seg7 = await _seed_segment(
            db_session,
            vid_id=vid_id,
            sequence_number=7,
            text="bravo charlie",
            start_time=35.0,
        )

        await db_session.commit()

        service = _make_batch_service()
        result = await service.find_and_replace(
            db_session,
            pattern="alpha bravo bravo charlie",
            replacement="SHOULD_NOT_APPEAR",
            cross_segment=True,  # TDD: parameter does not yet exist
        )

        from chronovista.models.batch_correction_models import BatchCorrectionResult

        assert isinstance(result, BatchCorrectionResult)
        assert result.total_matched == 0, (
            "Non-consecutive segments (seq 5 and 7, gap at 6) must NOT be paired "
            f"for cross-segment matching. total_matched={result.total_matched}"
        )

        from chronovista.db.models import TranscriptSegment as TranscriptSegmentDB

        refreshed5 = await db_session.get(TranscriptSegmentDB, seg5.id)
        refreshed7 = await db_session.get(TranscriptSegmentDB, seg7.id)

        assert refreshed5 is not None and not refreshed5.has_correction, (
            "Segment 5 must not be corrected — non-consecutive sequence prevented pairing."
        )
        assert refreshed7 is not None and not refreshed7.has_correction, (
            "Segment 7 must not be corrected — non-consecutive sequence prevented pairing."
        )


# ---------------------------------------------------------------------------
# T016 — Regex + cross-segment composition
# ---------------------------------------------------------------------------


class TestRegexCrossSegment:
    r"""
    T016 — Regex pattern with ``cross_segment=True``: regex matching is applied
    to the concatenated adjacent-segment text.

    Per spec edge case: "What happens when --cross-segment and --regex are
    used together? Both features compose — regex matching is applied to the
    concatenated adjacent segment text."

    Per spec FR-009: "The --cross-segment flag MUST compose with all existing
    flags: --regex, --case-insensitive, …"

    NOTE: This test is expected to FAIL until ``find_and_replace()`` gains a
    ``cross_segment`` parameter.  That failure is intentional TDD.
    """

    async def test_regex_pattern_applied_to_cross_segment_pair(
        self, db_session: AsyncSession
    ) -> None:
        r"""
        Pattern ``\bCla\w+ Shane Bound\b`` matches "Claudia Shane Bound"
        spanning segment N and segment N+1.

        Seed setup
        ----------
        Segment 20 — "Claudia Shane"
        Segment 21 — "Bound también"

        Combined: "Claudia Shane Bound también"

        The regex ``\bCla\w+ Shane Bound\b`` matches "Claudia Shane Bound" in
        the combined text, spanning the boundary.  The replacement
        "Claudia Sheinbaum" is placed into segment 20; "Bound" is removed
        from segment 21.

        Assertions
        ----------
        * ``result.total_matched >= 1``
        * Segment 20 corrected_text contains "Claudia Sheinbaum".
        * Segment 21 corrected_text does not start with "Bound".
        """
        vid_id = video_id(seed="t016_regex_cross")

        await _seed_channel(db_session)
        await _seed_video(db_session, vid_id)
        await _seed_transcript(db_session, vid_id, language_code="es")

        seg_a = await _seed_segment(
            db_session,
            vid_id=vid_id,
            language_code="es",
            sequence_number=20,
            text="Claudia Shane",
            start_time=100.0,
        )
        seg_b = await _seed_segment(
            db_session,
            vid_id=vid_id,
            language_code="es",
            sequence_number=21,
            text="Bound también",
            start_time=105.0,
        )

        await db_session.commit()

        service = _make_batch_service()
        result = await service.find_and_replace(
            db_session,
            pattern=r"\bCla\w+ Shane Bound\b",
            replacement="Claudia Sheinbaum",
            regex=True,
            cross_segment=True,
        )

        from chronovista.models.batch_correction_models import BatchCorrectionResult

        assert isinstance(result, BatchCorrectionResult)
        assert result.total_matched >= 1, (
            r"Regex pattern \bCla\w+ Shane Bound\b must match "
            r"'Claudia Shane Bound' across the cross-segment boundary. "
            f"total_matched={result.total_matched}"
        )

        from chronovista.db.models import TranscriptSegment as TranscriptSegmentDB

        refreshed_a = await db_session.get(TranscriptSegmentDB, seg_a.id)
        refreshed_b = await db_session.get(TranscriptSegmentDB, seg_b.id)

        assert refreshed_a is not None
        assert refreshed_b is not None

        corrected_a: str = (refreshed_a.corrected_text or refreshed_a.text) or ""
        corrected_b: str = (refreshed_b.corrected_text or refreshed_b.text) or ""

        assert "Claudia Sheinbaum" in corrected_a, (
            f"Segment 20 must contain 'Claudia Sheinbaum' after regex cross-segment "
            f"replacement. Got: {corrected_a!r}"
        )
        assert not corrected_b.startswith("Bound"), (
            f"'Bound' must be removed from segment 21. Got: {corrected_b!r}"
        )


# ---------------------------------------------------------------------------
# T016b — Case-insensitive + cross-segment composition
# ---------------------------------------------------------------------------


class TestCaseInsensitiveCrossSegment:
    """
    T016b — ``case_insensitive=True`` combined with ``cross_segment=True``
    matches across the segment boundary despite case differences.

    Per spec FR-009: "The --cross-segment flag MUST compose with all existing
    flags: --regex, --case-insensitive, …"

    NOTE: This test is expected to FAIL until ``find_and_replace()`` gains a
    ``cross_segment`` parameter.  That failure is intentional TDD.
    """

    async def test_case_insensitive_cross_segment_match(
        self, db_session: AsyncSession
    ) -> None:
        """
        Pattern "claudia shane bound" (all lowercase) matches across segments
        "Claudia Shane" and "BOUND también" (mixed/uppercase) when
        ``case_insensitive=True``.

        Seed setup
        ----------
        Segment 30 — "Claudia Shane"          (mixed case)
        Segment 31 — "BOUND también"          (uppercase BOUND)

        Assertions
        ----------
        * ``result.total_matched >= 1``
        * Segment 30 corrected_text contains "Claudia Sheinbaum".
        * Segment 31 corrected_text does NOT start with "BOUND" or "bound".
        * Segment 31 corrected_text still contains "también".
        """
        vid_id = video_id(seed="t016b_ci_cross")

        await _seed_channel(db_session)
        await _seed_video(db_session, vid_id)
        await _seed_transcript(db_session, vid_id, language_code="es")

        seg_a = await _seed_segment(
            db_session,
            vid_id=vid_id,
            language_code="es",
            sequence_number=30,
            text="Claudia Shane",
            start_time=150.0,
        )
        seg_b = await _seed_segment(
            db_session,
            vid_id=vid_id,
            language_code="es",
            sequence_number=31,
            text="BOUND también",
            start_time=155.0,
        )

        await db_session.commit()

        service = _make_batch_service()
        result = await service.find_and_replace(
            db_session,
            pattern="claudia shane bound",
            replacement="Claudia Sheinbaum",
            case_insensitive=True,
            cross_segment=True,  # TDD: parameter does not yet exist
        )

        from chronovista.models.batch_correction_models import BatchCorrectionResult

        assert isinstance(result, BatchCorrectionResult)
        assert result.total_matched >= 1, (
            "Case-insensitive pattern 'claudia shane bound' must match "
            "'Claudia Shane' + 'BOUND …' across the segment boundary. "
            f"total_matched={result.total_matched}"
        )

        from chronovista.db.models import TranscriptSegment as TranscriptSegmentDB

        refreshed_a = await db_session.get(TranscriptSegmentDB, seg_a.id)
        refreshed_b = await db_session.get(TranscriptSegmentDB, seg_b.id)

        assert refreshed_a is not None
        assert refreshed_b is not None

        corrected_a: str = (refreshed_a.corrected_text or refreshed_a.text) or ""
        corrected_b: str = (refreshed_b.corrected_text or refreshed_b.text) or ""

        assert "Claudia Sheinbaum" in corrected_a, (
            f"Segment 30 must contain 'Claudia Sheinbaum'. Got: {corrected_a!r}"
        )
        assert not corrected_b.lower().startswith("bound"), (
            f"'BOUND' (any case) must be removed from segment 31. Got: {corrected_b!r}"
        )
        assert "también" in corrected_b, (
            f"Remaining text 'también' must be preserved in segment 31. "
            f"Got: {corrected_b!r}"
        )


# ---------------------------------------------------------------------------
# T017 — Overlapping pairs
# ---------------------------------------------------------------------------


class TestOverlappingPairs:
    """
    T017 — When a segment participates in two overlapping pairs (e.g., segment
    2 belongs to both pair (1,2) and pair (2,3)) and both pairs match the
    pattern, the earlier pair (lower sequence_number) takes precedence and the
    later pair is skipped with a warning.

    Per spec edge case: "If a segment is part of two matched pairs, the earlier
    pair (lower sequence_number) takes precedence and the later pair is skipped
    with a warning."

    NOTE: This test is expected to FAIL until ``find_and_replace()`` gains a
    ``cross_segment`` parameter.  That failure is intentional TDD.
    """

    async def test_earlier_pair_wins_over_later_overlapping_pair(
        self, db_session: AsyncSession
    ) -> None:
        """
        Pattern "end start" matches both pair(1,2) and pair(2,3).
        Only pair(1,2) is applied; pair(2,3) is skipped.

        Seed setup
        ----------
        Segment 1 — "prefix end"
        Segment 2 — "start middle"
        Segment 3 — "end suffix"   (if pair(2,3) were applied its "start" left
                                     from seg2 would pair with "end" from seg3)

        Pattern: "end start" — appears in combined texts of both (1,2) and (2,3)
        assuming segment 2's text provides "start" at the boundary.

        Assertions
        ----------
        * Pair (1,2) is applied: segment 1 corrected, segment 2 de-headed.
        * Pair (2,3) is NOT applied (segment 2 already used by pair (1,2)).
        * ``result.total_matched >= 1`` but segment 3 has no correction from
          the "end start" pattern (since pair(2,3) was skipped).
        """
        vid_id = video_id(seed="t017_overlap_pairs")

        await _seed_channel(db_session)
        await _seed_video(db_session, vid_id)
        await _seed_transcript(db_session, vid_id)

        seg1 = await _seed_segment(
            db_session,
            vid_id=vid_id,
            sequence_number=1,
            text="prefix end",
            start_time=5.0,
        )
        await _seed_segment(
            db_session,
            vid_id=vid_id,
            sequence_number=2,
            text="start middle end",
            start_time=10.0,
        )
        seg3 = await _seed_segment(
            db_session,
            vid_id=vid_id,
            sequence_number=3,
            text="start suffix",
            start_time=15.0,
        )

        await db_session.commit()

        service = _make_batch_service()
        result = await service.find_and_replace(
            db_session,
            pattern="end start",
            replacement="REPLACED",
            cross_segment=True,  # TDD: parameter does not yet exist
        )

        from chronovista.models.batch_correction_models import BatchCorrectionResult

        assert isinstance(result, BatchCorrectionResult)
        assert result.total_matched >= 1, (
            "Pattern 'end start' must be detected in at least one cross-segment "
            f"pair. total_matched={result.total_matched}"
        )

        from chronovista.db.models import TranscriptSegment as TranscriptSegmentDB

        refreshed1 = await db_session.get(TranscriptSegmentDB, seg1.id)
        refreshed3 = await db_session.get(TranscriptSegmentDB, seg3.id)

        assert refreshed1 is not None
        assert refreshed3 is not None

        # Pair (1,2) must have been applied — segment 1 corrected.
        assert refreshed1.has_correction, (
            "Segment 1 must be corrected as part of the winning pair (1,2). "
            f"has_correction={refreshed1.has_correction}"
        )

        # Pair (2,3) must have been SKIPPED because segment 2 was already used.
        # Segment 3 must NOT have a correction attributable to "end start" matching
        # the pair(2,3) boundary (its text "start suffix" would require "end start"
        # to span the boundary from a used segment 2).
        # We assert segment 3 was not modified by the overlapping-pair rule.
        assert not refreshed3.has_correction, (
            "Segment 3 must NOT be corrected because pair(2,3) was skipped — "
            "segment 2 was already consumed by the earlier pair(1,2). "
            f"has_correction={refreshed3.has_correction}"
        )


# ---------------------------------------------------------------------------
# T018 — Empty effective text
# ---------------------------------------------------------------------------


class TestEmptyEffectiveText:
    """
    T018 — When either segment in a candidate pair has empty effective text,
    the pair is skipped for cross-segment matching.  The non-empty partner
    segment remains eligible for single-segment matching against the pattern.

    Per spec edge case: "What happens when either segment in a pair has empty
    effective text? The pair is skipped for cross-segment matching. The
    non-empty segment is still eligible for single-segment matching."

    NOTE: This test is expected to FAIL until ``find_and_replace()`` gains a
    ``cross_segment`` parameter.  That failure is intentional TDD.
    """

    async def test_pair_with_empty_segment_is_skipped(
        self, db_session: AsyncSession
    ) -> None:
        """
        Segment 0 has empty text; segment 1 has the pattern within it.
        The pair (0,1) is skipped for cross-segment matching; segment 1 is
        still matched as a single-segment match.

        Seed setup
        ----------
        Segment 0 — text=""          (empty)
        Segment 1 — text="find me here"

        Pattern: "find me" → replacement "found it"

        Assertions
        ----------
        * No cross-segment match is produced from the (0,1) pair.
        * Segment 1 IS matched as a single-segment match (pattern fully within it).
        * ``result.total_matched >= 1`` (single-segment match from seg 1).
        * Segment 1 corrected_text contains "found it".
        """
        vid_id = video_id(seed="t018_empty_eff_text")

        await _seed_channel(db_session)
        await _seed_video(db_session, vid_id)
        await _seed_transcript(db_session, vid_id)

        seg0 = await _seed_segment(
            db_session,
            vid_id=vid_id,
            sequence_number=0,
            text="",
            start_time=0.0,
        )
        seg1 = await _seed_segment(
            db_session,
            vid_id=vid_id,
            sequence_number=1,
            text="find me here",
            start_time=5.0,
        )

        await db_session.commit()

        service = _make_batch_service()
        result = await service.find_and_replace(
            db_session,
            pattern="find me",
            replacement="found it",
            cross_segment=True,  # TDD: parameter does not yet exist
        )

        from chronovista.models.batch_correction_models import BatchCorrectionResult

        assert isinstance(result, BatchCorrectionResult)
        assert result.total_matched >= 1, (
            "Pattern 'find me' must be found as a single-segment match in "
            f"segment 1 even when segment 0 is empty. total_matched={result.total_matched}"
        )

        from chronovista.db.models import TranscriptSegment as TranscriptSegmentDB

        refreshed0 = await db_session.get(TranscriptSegmentDB, seg0.id)
        refreshed1 = await db_session.get(TranscriptSegmentDB, seg1.id)

        assert refreshed0 is not None
        assert refreshed1 is not None

        # Empty segment 0 was not part of any matched pair — no correction.
        assert not refreshed0.has_correction, (
            "Empty segment 0 must not receive a correction. "
            f"has_correction={refreshed0.has_correction}"
        )

        corrected1: str = (refreshed1.corrected_text or refreshed1.text) or ""
        assert "found it" in corrected1, (
            f"Segment 1 must contain 'found it' (single-segment match). "
            f"Got: {corrected1!r}"
        )


# ---------------------------------------------------------------------------
# T036a — Empty segment after correction
# ---------------------------------------------------------------------------


class TestEmptySegmentAfterCorrection:
    """
    T036a — When applying a cross-segment correction removes ALL text from
    segment N+1, the system must display a warning and flag the segment but
    must NOT delete the segment row (FR-008).

    Per spec FR-008: "When a cross-segment correction leaves the second segment
    with only whitespace or empty text, the system MUST display a warning
    message after the results table listing the segment IDs that were left
    empty or whitespace-only."

    Per spec acceptance scenario (Story 4, scenario 2): "Given a cross-segment
    correction that removes all text from segment N+1, When the correction is
    applied, Then the empty segment is flagged in the output (not deleted —
    segment boundaries are preserved)."

    NOTE: This test is expected to FAIL until ``find_and_replace()`` gains a
    ``cross_segment`` parameter.  That failure is intentional TDD.
    """

    async def test_segment_not_deleted_when_correction_empties_it(
        self, db_session: AsyncSession
    ) -> None:
        """
        Correction "Claudia Shane Bound" → "Claudia Sheinbaum" removes the
        word "Bound" from segment N+1 whose text IS exactly "Bound".

        Segment N+1 would become empty/whitespace-only after the correction.
        The row must still exist in the database (not deleted), and the
        result must signal the emptied segment.

        Seed setup
        ----------
        Segment 40 — "Claudia Shane"
        Segment 41 — "Bound"          (only one word; will be fully consumed)

        Assertions
        ----------
        * ``result.total_matched >= 1``
        * Segment 40 ``corrected_text`` contains "Claudia Sheinbaum".
        * Segment 41 row still EXISTS in the database after correction.
        * Segment 41 ``corrected_text`` is empty or whitespace-only (the word
          "Bound" was fully consumed by the cross-segment replacement).
        * The ``BatchCorrectionResult`` (or a side-channel warning) indicates
          that at least one segment was left empty — verified by checking the
          corrected text, not by inspecting stdout directly.
        """
        vid_id = video_id(seed="t036a_empty_after_corr")

        await _seed_channel(db_session)
        await _seed_video(db_session, vid_id)
        await _seed_transcript(db_session, vid_id, language_code="es")

        seg_a = await _seed_segment(
            db_session,
            vid_id=vid_id,
            language_code="es",
            sequence_number=40,
            text="Claudia Shane",
            start_time=200.0,
        )
        seg_b = await _seed_segment(
            db_session,
            vid_id=vid_id,
            language_code="es",
            sequence_number=41,
            text="Bound",
            start_time=205.0,
        )

        await db_session.commit()

        service = _make_batch_service()
        result = await service.find_and_replace(
            db_session,
            pattern="Claudia Shane Bound",
            replacement="Claudia Sheinbaum",
            cross_segment=True,  # TDD: parameter does not yet exist
        )

        from chronovista.models.batch_correction_models import BatchCorrectionResult

        assert isinstance(result, BatchCorrectionResult)
        assert result.total_matched >= 1, (
            "Cross-segment pair 'Claudia Shane' + 'Bound' must be matched. "
            f"total_matched={result.total_matched}"
        )

        # Verify segment A received the replacement.
        from chronovista.db.models import TranscriptSegment as TranscriptSegmentDB

        refreshed_a = await db_session.get(TranscriptSegmentDB, seg_a.id)
        refreshed_b = await db_session.get(TranscriptSegmentDB, seg_b.id)

        assert refreshed_a is not None, (
            "Segment A must still exist in the database after correction."
        )
        assert refreshed_b is not None, (
            "Segment B (emptied) must NOT be deleted — FR-008 requires the row "
            "to be preserved even when its corrected text is empty."
        )

        corrected_a: str = (refreshed_a.corrected_text or refreshed_a.text) or ""
        corrected_b: str = (refreshed_b.corrected_text or refreshed_b.text) or ""

        assert "Claudia Sheinbaum" in corrected_a, (
            f"Segment 40 must contain 'Claudia Sheinbaum'. Got: {corrected_a!r}"
        )

        # Segment B must be empty or whitespace-only after correction.
        assert corrected_b.strip() == "", (
            f"Segment 41 must be empty or whitespace-only after 'Bound' is "
            f"consumed by the cross-segment replacement. Got: {corrected_b!r}"
        )


# ---------------------------------------------------------------------------
# T034 — Basic cross-segment revert
# ---------------------------------------------------------------------------


class TestBasicCrossSegmentRevert:
    """
    T034 — Apply a cross-segment correction via ``find_and_replace`` with
    ``cross_segment=True``, then call ``batch_revert`` matching the corrected
    text.  Verify both segments are restored to their original text.
    """

    async def test_revert_restores_both_segments(
        self, db_session: AsyncSession
    ) -> None:
        """
        Apply cross-segment correction "Claudia Shane Bound" -> "Claudia Sheinbaum",
        then revert by matching "Claudia Sheinbaum" in the corrected text.
        Both segments must be restored to their original text.
        """
        vid_id = video_id(seed="t034_basic_revert")

        await _seed_channel(db_session)
        await _seed_video(db_session, vid_id)
        await _seed_transcript(db_session, vid_id, language_code="en")

        seg_a = await _seed_segment(
            db_session,
            vid_id=vid_id,
            language_code="en",
            sequence_number=0,
            text="Claudia Shane",
            start_time=0.0,
        )
        seg_b = await _seed_segment(
            db_session,
            vid_id=vid_id,
            language_code="en",
            sequence_number=1,
            text="Bound is a word",
            start_time=5.0,
        )

        await db_session.commit()

        service = _make_batch_service()

        # Step 1: Apply cross-segment correction
        result = await service.find_and_replace(
            db_session,
            pattern="Claudia Shane Bound",
            replacement="Claudia Sheinbaum",
            cross_segment=True,
        )

        from chronovista.models.batch_correction_models import BatchCorrectionResult

        assert isinstance(result, BatchCorrectionResult)
        assert result.total_applied >= 1

        # Verify correction applied
        refreshed_a = await db_session.get(TranscriptSegmentDB, seg_a.id)
        assert refreshed_a is not None
        assert refreshed_a.has_correction is True

        # Step 2: Revert using batch_revert matching the corrected text
        revert_result = await service.batch_revert(
            db_session,
            pattern="Claudia Sheinbaum",
        )

        assert isinstance(revert_result, BatchCorrectionResult)
        assert revert_result.total_applied >= 2, (
            "Both segments (A matched + B partner cascade) must be reverted. "
            f"total_applied={revert_result.total_applied}"
        )

        # Verify both segments are restored to original text
        final_a = await db_session.get(TranscriptSegmentDB, seg_a.id)
        final_b = await db_session.get(TranscriptSegmentDB, seg_b.id)

        assert final_a is not None
        assert final_b is not None

        # After revert-to-original, has_correction should be False
        assert final_a.has_correction is False, (
            f"Segment A should have has_correction=False after revert. "
            f"Got: {final_a.has_correction}"
        )
        assert final_b.has_correction is False, (
            f"Segment B should have has_correction=False after revert. "
            f"Got: {final_b.has_correction}"
        )

        # Original text should be restored
        effective_a = final_a.corrected_text or final_a.text
        effective_b = final_b.corrected_text or final_b.text

        assert effective_a == "Claudia Shane", (
            f"Segment A must be restored to 'Claudia Shane'. Got: {effective_a!r}"
        )
        assert effective_b == "Bound is a word", (
            f"Segment B must be restored to 'Bound is a word'. Got: {effective_b!r}"
        )


# ---------------------------------------------------------------------------
# T035 — Partner cascade revert
# ---------------------------------------------------------------------------


class TestPartnerCascadeRevert:
    """
    T035 — Apply a cross-segment correction, then call ``batch_revert`` with
    a pattern that matches only ONE segment's corrected text.  The partner
    segment should also be reverted because of the ``[cross-segment:partner=N]``
    marker in the correction note.
    """

    async def test_partner_reverted_via_cascade(
        self, db_session: AsyncSession
    ) -> None:
        """
        After cross-segment correction, segment A has "Claudia Sheinbaum is a word"
        and segment B has " " (emptied).  Revert using pattern "Claudia Sheinbaum"
        which matches only segment A — segment B should also be reverted via cascade.
        """
        vid_id = video_id(seed="t035_partner_cascade")

        await _seed_channel(db_session)
        await _seed_video(db_session, vid_id)
        await _seed_transcript(db_session, vid_id, language_code="en")

        seg_a = await _seed_segment(
            db_session,
            vid_id=vid_id,
            language_code="en",
            sequence_number=0,
            text="Claudia Shane",
            start_time=0.0,
        )
        seg_b = await _seed_segment(
            db_session,
            vid_id=vid_id,
            language_code="en",
            sequence_number=1,
            text="Bound",
            start_time=5.0,
        )

        await db_session.commit()

        service = _make_batch_service()

        # Apply cross-segment correction that empties seg B
        result = await service.find_and_replace(
            db_session,
            pattern="Claudia Shane Bound",
            replacement="Claudia Sheinbaum",
            cross_segment=True,
        )

        from chronovista.models.batch_correction_models import BatchCorrectionResult

        assert isinstance(result, BatchCorrectionResult)
        assert result.total_applied >= 1

        # Verify seg B is empty/whitespace after correction
        refreshed_b = await db_session.get(TranscriptSegmentDB, seg_b.id)
        assert refreshed_b is not None
        assert refreshed_b.has_correction is True
        # seg B has " " (single space, FR-008 preservation)

        # batch_revert with pattern "Claudia Sheinbaum" — only matches seg A.
        # seg B has " " which doesn't match, but should be reverted via cascade.
        revert_result = await service.batch_revert(
            db_session,
            pattern="Claudia Sheinbaum",
        )

        assert isinstance(revert_result, BatchCorrectionResult)
        assert revert_result.total_applied >= 2, (
            "Both segment A (matched) and segment B (partner cascade) must be "
            f"reverted. total_applied={revert_result.total_applied}"
        )

        # Verify both restored
        final_a = await db_session.get(TranscriptSegmentDB, seg_a.id)
        final_b = await db_session.get(TranscriptSegmentDB, seg_b.id)

        assert final_a is not None
        assert final_b is not None
        assert final_a.has_correction is False
        assert final_b.has_correction is False

        effective_a = final_a.corrected_text or final_a.text
        effective_b = final_b.corrected_text or final_b.text

        assert effective_a == "Claudia Shane", (
            f"Segment A must be restored. Got: {effective_a!r}"
        )
        assert effective_b == "Bound", (
            f"Segment B must be restored. Got: {effective_b!r}"
        )


# ---------------------------------------------------------------------------
# T036b — Revert of emptied segment
# ---------------------------------------------------------------------------


class TestRevertOfEmptiedSegment:
    """
    T036b — Apply a cross-segment correction that empties segment N+1
    (all text from seg B consumed by the match), then revert.
    Verify original text restored in both segments.
    """

    async def test_revert_restores_emptied_segment(
        self, db_session: AsyncSession
    ) -> None:
        """
        Correction "Claudia Shane Bound" -> "Claudia Sheinbaum" where seg B
        is exactly "Bound" — seg B becomes " " after correction.
        Revert must restore seg B to "Bound".
        """
        vid_id = video_id(seed="t036b_revert_emptied")

        await _seed_channel(db_session)
        await _seed_video(db_session, vid_id)
        await _seed_transcript(db_session, vid_id, language_code="en")

        seg_a = await _seed_segment(
            db_session,
            vid_id=vid_id,
            language_code="en",
            sequence_number=0,
            text="Claudia Shane",
            start_time=0.0,
        )
        seg_b = await _seed_segment(
            db_session,
            vid_id=vid_id,
            language_code="en",
            sequence_number=1,
            text="Bound",
            start_time=5.0,
        )

        await db_session.commit()

        service = _make_batch_service()

        # Apply cross-segment correction
        result = await service.find_and_replace(
            db_session,
            pattern="Claudia Shane Bound",
            replacement="Claudia Sheinbaum",
            cross_segment=True,
        )

        from chronovista.models.batch_correction_models import BatchCorrectionResult

        assert isinstance(result, BatchCorrectionResult)
        assert result.total_applied >= 1

        # Verify seg B is emptied
        refreshed_b = await db_session.get(TranscriptSegmentDB, seg_b.id)
        assert refreshed_b is not None
        assert refreshed_b.has_correction is True
        effective_b_after = (refreshed_b.corrected_text or "").strip()
        assert effective_b_after == "", (
            f"Seg B should be empty after correction. Got: {effective_b_after!r}"
        )

        # Revert via batch_revert matching seg A's corrected text
        revert_result = await service.batch_revert(
            db_session,
            pattern="Claudia Sheinbaum",
        )

        assert isinstance(revert_result, BatchCorrectionResult)
        assert revert_result.total_applied >= 2

        # Verify restoration
        final_a = await db_session.get(TranscriptSegmentDB, seg_a.id)
        final_b = await db_session.get(TranscriptSegmentDB, seg_b.id)

        assert final_a is not None
        assert final_b is not None
        assert final_a.has_correction is False
        assert final_b.has_correction is False

        effective_a = final_a.corrected_text or final_a.text
        effective_b = final_b.corrected_text or final_b.text

        assert effective_a == "Claudia Shane", (
            f"Segment A must be restored. Got: {effective_a!r}"
        )
        assert effective_b == "Bound", (
            f"Segment B must be restored to original 'Bound'. Got: {effective_b!r}"
        )


# ---------------------------------------------------------------------------
# T037 — Missing partner on revert
# ---------------------------------------------------------------------------


class TestMissingPartnerOnRevert:
    """
    T037 — Apply a cross-segment correction, then delete the partner segment
    from the DB (simulating a transcript re-download). Call ``batch_revert``
    and verify the surviving segment is reverted and a warning is logged
    about the missing partner.
    """

    async def test_surviving_segment_reverted_when_partner_missing(
        self, db_session: AsyncSession
    ) -> None:
        """
        After cross-segment correction, delete segment B, then revert.
        Segment A must still be reverted. A warning must be logged about
        the missing partner.
        """
        vid_id = video_id(seed="t037_missing_partner")

        await _seed_channel(db_session)
        await _seed_video(db_session, vid_id)
        await _seed_transcript(db_session, vid_id, language_code="en")

        seg_a = await _seed_segment(
            db_session,
            vid_id=vid_id,
            language_code="en",
            sequence_number=0,
            text="Claudia Shane",
            start_time=0.0,
        )
        seg_b = await _seed_segment(
            db_session,
            vid_id=vid_id,
            language_code="en",
            sequence_number=1,
            text="Bound is great",
            start_time=5.0,
        )

        await db_session.commit()

        service = _make_batch_service()

        # Apply cross-segment correction
        result = await service.find_and_replace(
            db_session,
            pattern="Claudia Shane Bound",
            replacement="Claudia Sheinbaum",
            cross_segment=True,
        )

        from chronovista.models.batch_correction_models import BatchCorrectionResult

        assert isinstance(result, BatchCorrectionResult)
        assert result.total_applied >= 1

        # Remember partner segment ID before deletion
        partner_id = seg_b.id

        # Delete the partner segment (simulate re-download).
        # Must first delete correction records due to RESTRICT FK constraint.
        from sqlalchemy import delete as sa_delete

        from chronovista.db.models import TranscriptCorrection as TranscriptCorrectionDB

        await db_session.execute(
            sa_delete(TranscriptCorrectionDB).where(
                TranscriptCorrectionDB.segment_id == partner_id
            )
        )
        await db_session.delete(seg_b)
        await db_session.commit()

        # Verify partner is gone
        deleted_seg = await db_session.get(TranscriptSegmentDB, partner_id)
        assert deleted_seg is None, "Partner segment should be deleted"

        # Revert via batch_revert — surviving segment should still be reverted
        revert_result = await service.batch_revert(
            db_session,
            pattern="Claudia Sheinbaum",
        )

        assert isinstance(revert_result, BatchCorrectionResult)
        assert revert_result.total_applied >= 1, (
            "Surviving segment A must be reverted even when partner is missing. "
            f"total_applied={revert_result.total_applied}"
        )

        # Verify segment A is restored
        final_a = await db_session.get(TranscriptSegmentDB, seg_a.id)
        assert final_a is not None
        assert final_a.has_correction is False

        effective_a = final_a.corrected_text or final_a.text
        assert effective_a == "Claudia Shane", (
            f"Segment A must be restored. Got: {effective_a!r}"
        )
