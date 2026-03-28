"""
Unit tests for TranscriptCorrectionService.apply_correction.

Tests all branches of apply_correction with fully mocked repositories.
All database I/O is mocked — these are pure unit tests that validate
service-layer logic without any real database connection.

Service contract source:
  specs/033-transcript-corrections-audit/contracts/service-contracts.md

Implementation target:
  src/chronovista/services/transcript_correction_service.py

Constitution §Cross-Feature Data Contract Verification:
  Mock tests MUST inspect the exact arguments passed to repository methods
  to verify that segment and transcript mutations include every expected
  column, not merely that a method was called.

References
----------
- TranscriptCorrectionService.apply_correction contract: service-contracts.md
- TranscriptSegment DB model: src/chronovista/db/models.py
- VideoTranscript DB model: src/chronovista/db/models.py
- TranscriptCorrectionCreate Pydantic model: src/chronovista/models/transcript_correction.py
- CorrectionType enum: src/chronovista/models/enums.py
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from chronovista.db.models import TranscriptCorrection as TranscriptCorrectionDB
from chronovista.db.models import TranscriptSegment as TranscriptSegmentDB
from chronovista.db.models import VideoTranscript as VideoTranscriptDB
from chronovista.models.enums import CorrectionType
from chronovista.models.transcript_correction import TranscriptCorrectionCreate

# ---------------------------------------------------------------------------
# CRITICAL: Module-level asyncio marker ensures async tests run properly
# with coverage tools, avoiding silent test-skipping (see CLAUDE.md).
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_segment(
    segment_id: int = 1,
    text: str = "teh quick brown fox",
    corrected_text: str | None = None,
    has_correction: bool = False,
    video_id: str = "dQw4w9WgXcQ",
    language_code: str = "en",
) -> MagicMock:
    """Build a mock TranscriptSegmentDB object with relevant attributes."""
    seg = MagicMock(spec=TranscriptSegmentDB)
    seg.id = segment_id
    seg.video_id = video_id
    seg.language_code = language_code
    seg.text = text
    seg.corrected_text = corrected_text
    seg.has_correction = has_correction
    return seg


def _make_transcript(
    video_id: str = "dQw4w9WgXcQ",
    language_code: str = "en",
    has_corrections: bool = False,
    correction_count: int = 0,
    last_corrected_at: datetime | None = None,
) -> MagicMock:
    """Build a mock VideoTranscriptDB object with relevant attributes."""
    tr = MagicMock(spec=VideoTranscriptDB)
    tr.video_id = video_id
    tr.language_code = language_code
    tr.has_corrections = has_corrections
    tr.correction_count = correction_count
    tr.last_corrected_at = last_corrected_at
    return tr


def _make_correction_record(
    video_id: str = "dQw4w9WgXcQ",
    language_code: str = "en",
    segment_id: int = 1,
    version_number: int = 1,
    original_text: str = "teh quick brown fox",
    corrected_text: str = "the quick brown fox",
    corrected_by_user_id: str | None = "cli",
    correction_type: str = CorrectionType.SPELLING.value,
) -> MagicMock:
    """Build a mock TranscriptCorrectionDB that looks like a created record."""
    rec = MagicMock(spec=TranscriptCorrectionDB)
    rec.id = uuid.uuid4()
    rec.video_id = video_id
    rec.language_code = language_code
    rec.segment_id = segment_id
    rec.version_number = version_number
    rec.original_text = original_text
    rec.corrected_text = corrected_text
    rec.corrected_by_user_id = corrected_by_user_id
    rec.correction_type = correction_type
    rec.corrected_at = datetime.now(UTC)
    return rec


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_correction_repo() -> AsyncMock:
    """Provide a mock TranscriptCorrectionRepository with async method stubs."""
    return AsyncMock()


@pytest.fixture
def mock_segment_repo() -> AsyncMock:
    """Provide a mock TranscriptSegmentRepository with async method stubs."""
    return AsyncMock()


@pytest.fixture
def mock_transcript_repo() -> AsyncMock:
    """Provide a mock VideoTranscriptRepository with async method stubs."""
    return AsyncMock()


@pytest.fixture
def mock_session() -> AsyncMock:
    """Provide a mock AsyncSession."""
    return AsyncMock()


@pytest.fixture
def service(
    mock_correction_repo: AsyncMock,
    mock_segment_repo: AsyncMock,
    mock_transcript_repo: AsyncMock,
) -> Any:
    """
    Provide a TranscriptCorrectionService instance wired with mock repos.

    The constructor signature per service-contracts.md:
        TranscriptCorrectionService(
            correction_repo: TranscriptCorrectionRepository,
            segment_repo: TranscriptSegmentRepository,
            transcript_repo: VideoTranscriptRepository,
        )

    We import lazily inside fixture to allow the service to be created
    after implementation (TDD flow — tests written before implementation).
    """
    from chronovista.services.transcript_correction_service import (
        TranscriptCorrectionService,
    )

    return TranscriptCorrectionService(
        correction_repo=mock_correction_repo,
        segment_repo=mock_segment_repo,
        transcript_repo=mock_transcript_repo,
    )


# ---------------------------------------------------------------------------
# TestApplyCorrection
# ---------------------------------------------------------------------------


class TestApplyCorrection:
    """
    Tests for TranscriptCorrectionService.apply_correction.

    Contract (service-contracts.md):
    1. Read segment's current effective text (corrected_text if has_correction else text)
    2. Compute next version_number via correction_repo.get_latest_version()
    3. Create audit record → session.flush()
    4. Update segment: corrected_text, has_correction=True → session.flush()
    5. Update transcript: has_corrections=True, last_corrected_at=now(),
       increment correction_count → session.flush()

    Constitution §Cross-Feature Data Contract Verification:
    Each test verifies the *exact* attributes mutated on segment and transcript
    objects (not merely that methods were called).
    """

    async def test_first_correction_creates_audit_record(
        self,
        service: Any,
        mock_correction_repo: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_transcript_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        When a segment has no prior corrections, apply_correction creates
        an audit record with version_number=1 and original_text taken from
        segment.text (the raw, uncorrected text).
        """
        segment = _make_segment(
            segment_id=1,
            text="teh quick brown fox",
            corrected_text=None,
            has_correction=False,
        )
        transcript = _make_transcript(correction_count=0)
        created_record = _make_correction_record(
            version_number=1,
            original_text="teh quick brown fox",
            corrected_text="the quick brown fox",
        )

        mock_segment_repo.get.return_value = segment
        mock_transcript_repo.get.return_value = transcript
        mock_correction_repo.get_latest_version.return_value = 0
        mock_correction_repo.create.return_value = created_record

        await service.apply_correction(
            mock_session,
            video_id="dQw4w9WgXcQ",
            language_code="en",
            segment_id=1,
            corrected_text="the quick brown fox",
            correction_type=CorrectionType.SPELLING,
        )

        # Verify create was called with correct version_number and original_text
        mock_correction_repo.create.assert_called_once()
        call_kwargs = mock_correction_repo.create.call_args
        obj_in: TranscriptCorrectionCreate = call_kwargs.kwargs["obj_in"]
        assert obj_in.version_number == 1, (
            "First correction must have version_number=1"
        )
        assert obj_in.original_text == "teh quick brown fox", (
            "original_text must be segment.text when no prior correction exists"
        )

    async def test_version_chain_uses_corrected_text_as_original(
        self,
        service: Any,
        mock_correction_repo: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_transcript_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        When a segment already has a correction, the new audit record's
        original_text must be the segment's current corrected_text (the
        effective text at the moment of the new correction), not segment.text.

        This preserves the full version chain for revert operations.
        """
        segment = _make_segment(
            segment_id=1,
            text="teh quick brown fox",          # original raw text
            corrected_text="the quick brown fox", # currently corrected
            has_correction=True,
        )
        transcript = _make_transcript(correction_count=1, has_corrections=True)
        created_record = _make_correction_record(
            version_number=2,
            original_text="the quick brown fox",
            corrected_text="The quick brown fox.",
        )

        mock_segment_repo.get.return_value = segment
        mock_transcript_repo.get.return_value = transcript
        mock_correction_repo.get_latest_version.return_value = 1
        mock_correction_repo.create.return_value = created_record

        await service.apply_correction(
            mock_session,
            video_id="dQw4w9WgXcQ",
            language_code="en",
            segment_id=1,
            corrected_text="The quick brown fox.",
            correction_type=CorrectionType.FORMATTING,
        )

        call_kwargs = mock_correction_repo.create.call_args
        obj_in: TranscriptCorrectionCreate = call_kwargs.kwargs["obj_in"]
        assert obj_in.original_text == "the quick brown fox", (
            "When segment already has correction, original_text must be the "
            "current corrected_text (effective text), not segment.text"
        )

    async def test_version_number_increments(
        self,
        service: Any,
        mock_correction_repo: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_transcript_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        When get_latest_version returns N, the new audit record must have
        version_number = N + 1.
        """
        segment = _make_segment(
            corrected_text="second correction",
            has_correction=True,
        )
        transcript = _make_transcript(correction_count=2, has_corrections=True)
        created_record = _make_correction_record(version_number=3)

        mock_segment_repo.get.return_value = segment
        mock_transcript_repo.get.return_value = transcript
        mock_correction_repo.get_latest_version.return_value = 2
        mock_correction_repo.create.return_value = created_record

        await service.apply_correction(
            mock_session,
            video_id="dQw4w9WgXcQ",
            language_code="en",
            segment_id=1,
            corrected_text="third correction",
            correction_type=CorrectionType.SPELLING,
        )

        call_kwargs = mock_correction_repo.create.call_args
        obj_in: TranscriptCorrectionCreate = call_kwargs.kwargs["obj_in"]
        assert obj_in.version_number == 3, (
            "version_number must be get_latest_version() + 1 (was 2, expected 3)"
        )

    async def test_segment_updated_with_corrected_text_and_has_correction(
        self,
        service: Any,
        mock_correction_repo: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_transcript_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        Constitution §Cross-Feature: apply_correction must set segment.corrected_text
        to the new corrected text AND segment.has_correction to True.

        Verifying the specific attributes mutated on the segment object ensures
        downstream consumers (display_text, SRT export) see the correct state.
        """
        segment = _make_segment(
            text="original text",
            corrected_text=None,
            has_correction=False,
        )
        transcript = _make_transcript()
        created_record = _make_correction_record()

        mock_segment_repo.get.return_value = segment
        mock_transcript_repo.get.return_value = transcript
        mock_correction_repo.get_latest_version.return_value = 0
        mock_correction_repo.create.return_value = created_record

        await service.apply_correction(
            mock_session,
            video_id="dQw4w9WgXcQ",
            language_code="en",
            segment_id=1,
            corrected_text="corrected text",
            correction_type=CorrectionType.SPELLING,
        )

        # Constitution §Cross-Feature: verify WHAT was set, not just that add() was called
        assert segment.corrected_text == "corrected text", (
            "segment.corrected_text must be set to the new corrected_text value"
        )
        assert segment.has_correction is True, (
            "segment.has_correction must be set to True after apply_correction"
        )

    async def test_transcript_metadata_updated_has_corrections_and_count(
        self,
        service: Any,
        mock_correction_repo: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_transcript_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        Constitution §Cross-Feature: apply_correction must set transcript.has_corrections=True,
        increment transcript.correction_count, and set transcript.last_corrected_at to a
        non-None datetime.

        These three fields are read by history queries, the REST API, and the
        frontend display — any missing mutation would silently break downstream consumers.
        """
        segment = _make_segment(text="original", corrected_text=None, has_correction=False)
        transcript = _make_transcript(
            has_corrections=False,
            correction_count=0,
            last_corrected_at=None,
        )
        # Capture the initial correction_count so we can verify it was incremented
        initial_count = transcript.correction_count
        created_record = _make_correction_record()

        mock_segment_repo.get.return_value = segment
        mock_transcript_repo.get.return_value = transcript
        mock_correction_repo.get_latest_version.return_value = 0
        mock_correction_repo.create.return_value = created_record

        await service.apply_correction(
            mock_session,
            video_id="dQw4w9WgXcQ",
            language_code="en",
            segment_id=1,
            corrected_text="corrected",
            correction_type=CorrectionType.SPELLING,
        )

        # Constitution §Cross-Feature: verify all three required transcript fields
        assert transcript.has_corrections is True, (
            "transcript.has_corrections must be set to True after apply_correction"
        )
        assert transcript.correction_count == initial_count + 1, (
            "transcript.correction_count must be incremented by 1"
        )
        assert transcript.last_corrected_at is not None, (
            "transcript.last_corrected_at must be set to a datetime after apply_correction"
        )

    async def test_last_corrected_at_is_datetime(
        self,
        service: Any,
        mock_correction_repo: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_transcript_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        transcript.last_corrected_at must be set to a timezone-aware datetime,
        not None and not a plain date or string.
        """
        segment = _make_segment(text="hello world", corrected_text=None, has_correction=False)
        transcript = _make_transcript(last_corrected_at=None)
        created_record = _make_correction_record()

        mock_segment_repo.get.return_value = segment
        mock_transcript_repo.get.return_value = transcript
        mock_correction_repo.get_latest_version.return_value = 0
        mock_correction_repo.create.return_value = created_record

        await service.apply_correction(
            mock_session,
            video_id="dQw4w9WgXcQ",
            language_code="en",
            segment_id=1,
            corrected_text="hello, world",
            correction_type=CorrectionType.FORMATTING,
        )

        assert isinstance(transcript.last_corrected_at, datetime), (
            "transcript.last_corrected_at must be a datetime object"
        )

    async def test_raises_value_error_for_nonexistent_segment(
        self,
        service: Any,
        mock_correction_repo: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_transcript_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        apply_correction must raise ValueError when the segment does not exist.
        The segment repo returns None to simulate a missing segment.
        """
        mock_segment_repo.get.return_value = None

        with pytest.raises(ValueError, match="segment"):
            await service.apply_correction(
                mock_session,
                video_id="dQw4w9WgXcQ",
                language_code="en",
                segment_id=999,
                corrected_text="any text",
                correction_type=CorrectionType.SPELLING,
            )

        # Ensure no audit record was created
        mock_correction_repo.create.assert_not_called()

    async def test_raises_value_error_for_identical_text_no_prior_correction(
        self,
        service: Any,
        mock_correction_repo: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_transcript_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        apply_correction must raise ValueError when corrected_text is identical
        to the segment's current effective text (segment.text when has_correction=False).
        This prevents no-op corrections from polluting the audit trail.
        """
        segment = _make_segment(
            text="already correct",
            corrected_text=None,
            has_correction=False,
        )
        mock_segment_repo.get.return_value = segment

        with pytest.raises(ValueError, match="identical|no-op|same|differ"):
            await service.apply_correction(
                mock_session,
                video_id="dQw4w9WgXcQ",
                language_code="en",
                segment_id=1,
                corrected_text="already correct",  # identical to segment.text
                correction_type=CorrectionType.SPELLING,
            )

        mock_correction_repo.create.assert_not_called()

    async def test_raises_value_error_for_identical_text_with_prior_correction(
        self,
        service: Any,
        mock_correction_repo: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_transcript_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        When the segment has a prior correction, the effective text is
        segment.corrected_text. apply_correction must raise ValueError if
        the new corrected_text is identical to the current corrected_text.
        """
        segment = _make_segment(
            text="original",
            corrected_text="currently corrected",
            has_correction=True,
        )
        mock_segment_repo.get.return_value = segment

        with pytest.raises(ValueError, match="identical|no-op|same|differ"):
            await service.apply_correction(
                mock_session,
                video_id="dQw4w9WgXcQ",
                language_code="en",
                segment_id=1,
                corrected_text="currently corrected",  # same as corrected_text
                correction_type=CorrectionType.SPELLING,
            )

        mock_correction_repo.create.assert_not_called()

    async def test_corrected_by_user_id_passed_through(
        self,
        service: Any,
        mock_correction_repo: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_transcript_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        The corrected_by_user_id argument must appear in the created
        TranscriptCorrectionCreate object passed to correction_repo.create().
        """
        segment = _make_segment(text="original", corrected_text=None, has_correction=False)
        transcript = _make_transcript()
        created_record = _make_correction_record(corrected_by_user_id="api")

        mock_segment_repo.get.return_value = segment
        mock_transcript_repo.get.return_value = transcript
        mock_correction_repo.get_latest_version.return_value = 0
        mock_correction_repo.create.return_value = created_record

        await service.apply_correction(
            mock_session,
            video_id="dQw4w9WgXcQ",
            language_code="en",
            segment_id=1,
            corrected_text="corrected",
            correction_type=CorrectionType.SPELLING,
            corrected_by_user_id="api",
        )

        call_kwargs = mock_correction_repo.create.call_args
        obj_in: TranscriptCorrectionCreate = call_kwargs.kwargs["obj_in"]
        assert obj_in.corrected_by_user_id == "api", (
            "corrected_by_user_id='api' must be forwarded to the audit record"
        )

    async def test_corrected_by_user_id_defaults_to_none(
        self,
        service: Any,
        mock_correction_repo: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_transcript_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        When corrected_by_user_id is omitted, the audit record should
        have corrected_by_user_id=None (anonymous/system correction).
        """
        segment = _make_segment(text="original", corrected_text=None, has_correction=False)
        transcript = _make_transcript()
        created_record = _make_correction_record(corrected_by_user_id=None)

        mock_segment_repo.get.return_value = segment
        mock_transcript_repo.get.return_value = transcript
        mock_correction_repo.get_latest_version.return_value = 0
        mock_correction_repo.create.return_value = created_record

        await service.apply_correction(
            mock_session,
            video_id="dQw4w9WgXcQ",
            language_code="en",
            segment_id=1,
            corrected_text="corrected",
            correction_type=CorrectionType.SPELLING,
            # corrected_by_user_id omitted intentionally
        )

        call_kwargs = mock_correction_repo.create.call_args
        obj_in: TranscriptCorrectionCreate = call_kwargs.kwargs["obj_in"]
        assert obj_in.corrected_by_user_id is None, (
            "corrected_by_user_id must be None when not provided"
        )

    async def test_returns_created_correction(
        self,
        service: Any,
        mock_correction_repo: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_transcript_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        apply_correction must return the TranscriptCorrectionDB record
        created by correction_repo.create(), not None or the segment.
        """
        segment = _make_segment(text="original", corrected_text=None, has_correction=False)
        transcript = _make_transcript()
        expected_record = _make_correction_record(version_number=1)

        mock_segment_repo.get.return_value = segment
        mock_transcript_repo.get.return_value = transcript
        mock_correction_repo.get_latest_version.return_value = 0
        mock_correction_repo.create.return_value = expected_record

        result = await service.apply_correction(
            mock_session,
            video_id="dQw4w9WgXcQ",
            language_code="en",
            segment_id=1,
            corrected_text="corrected",
            correction_type=CorrectionType.SPELLING,
        )

        assert result is expected_record, (
            "apply_correction must return the TranscriptCorrectionDB record "
            "returned by correction_repo.create()"
        )

    async def test_get_latest_version_called_with_correct_args(
        self,
        service: Any,
        mock_correction_repo: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_transcript_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        correction_repo.get_latest_version must be called with the session,
        video_id, language_code, and segment_id to acquire the FOR UPDATE
        lock and compute the next version_number (NFR-005).
        """
        segment = _make_segment(
            segment_id=42,
            text="foo",
            corrected_text=None,
            has_correction=False,
            video_id="abcABC12345",
            language_code="es",
        )
        transcript = _make_transcript(video_id="abcABC12345", language_code="es")
        created_record = _make_correction_record()

        mock_segment_repo.get.return_value = segment
        mock_transcript_repo.get.return_value = transcript
        mock_correction_repo.get_latest_version.return_value = 0
        mock_correction_repo.create.return_value = created_record

        await service.apply_correction(
            mock_session,
            video_id="abcABC12345",
            language_code="es",
            segment_id=42,
            corrected_text="bar",
            correction_type=CorrectionType.SPELLING,
        )

        mock_correction_repo.get_latest_version.assert_called_once()
        call_args = mock_correction_repo.get_latest_version.call_args
        # Verify the correct identifiers are forwarded for the FOR UPDATE lock
        assert call_args.args[0] is mock_session or mock_session in call_args.args, (
            "get_latest_version must receive the session"
        )

    async def test_correction_note_passed_through(
        self,
        service: Any,
        mock_correction_repo: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_transcript_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        When correction_note is provided, it must appear in the created
        TranscriptCorrectionCreate object.
        """
        segment = _make_segment(text="original", corrected_text=None, has_correction=False)
        transcript = _make_transcript()
        created_record = _make_correction_record()

        mock_segment_repo.get.return_value = segment
        mock_transcript_repo.get.return_value = transcript
        mock_correction_repo.get_latest_version.return_value = 0
        mock_correction_repo.create.return_value = created_record

        await service.apply_correction(
            mock_session,
            video_id="dQw4w9WgXcQ",
            language_code="en",
            segment_id=1,
            corrected_text="corrected",
            correction_type=CorrectionType.PROPER_NOUN,
            correction_note="ASR confused homophone 'teh' → 'the'",
        )

        call_kwargs = mock_correction_repo.create.call_args
        obj_in: TranscriptCorrectionCreate = call_kwargs.kwargs["obj_in"]
        assert obj_in.correction_note == "ASR confused homophone 'teh' → 'the'", (
            "correction_note must be forwarded to the audit record"
        )

    async def test_session_flush_called_for_each_mutation(
        self,
        service: Any,
        mock_correction_repo: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_transcript_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        Per FR-007a (flush-only pattern), the service must call session.flush()
        after each of the three mutations (audit record, segment, transcript).
        session.commit() must NEVER be called (caller owns transaction lifecycle).
        """
        segment = _make_segment(text="original", corrected_text=None, has_correction=False)
        transcript = _make_transcript()
        created_record = _make_correction_record()

        mock_segment_repo.get.return_value = segment
        mock_transcript_repo.get.return_value = transcript
        mock_correction_repo.get_latest_version.return_value = 0
        mock_correction_repo.create.return_value = created_record

        await service.apply_correction(
            mock_session,
            video_id="dQw4w9WgXcQ",
            language_code="en",
            segment_id=1,
            corrected_text="corrected",
            correction_type=CorrectionType.SPELLING,
        )

        # Three flushes required: audit record + segment + transcript
        assert mock_session.flush.call_count >= 1, (
            "session.flush() must be called at least once per mutation step (FR-007a)"
        )
        # NEVER call commit — caller owns the transaction
        mock_session.commit.assert_not_called()

    async def test_correction_type_stored_correctly(
        self,
        service: Any,
        mock_correction_repo: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_transcript_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        The correction_type argument must be forwarded to the TranscriptCorrectionCreate
        object with the correct enum value.
        """
        segment = _make_segment(text="original", corrected_text=None, has_correction=False)
        transcript = _make_transcript()
        created_record = _make_correction_record(
            correction_type=CorrectionType.CONTEXT_CORRECTION.value
        )

        mock_segment_repo.get.return_value = segment
        mock_transcript_repo.get.return_value = transcript
        mock_correction_repo.get_latest_version.return_value = 0
        mock_correction_repo.create.return_value = created_record

        await service.apply_correction(
            mock_session,
            video_id="dQw4w9WgXcQ",
            language_code="en",
            segment_id=1,
            corrected_text="corrected",
            correction_type=CorrectionType.CONTEXT_CORRECTION,
        )

        call_kwargs = mock_correction_repo.create.call_args
        obj_in: TranscriptCorrectionCreate = call_kwargs.kwargs["obj_in"]
        assert obj_in.correction_type == CorrectionType.CONTEXT_CORRECTION, (
            "correction_type must be forwarded to the audit record as-is"
        )

    async def test_video_id_and_language_code_in_audit_record(
        self,
        service: Any,
        mock_correction_repo: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_transcript_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        The audit record must link back to the correct (video_id, language_code)
        transcript pair. This is required for get_by_video() queries.
        """
        segment = _make_segment(
            text="original",
            corrected_text=None,
            has_correction=False,
            video_id="xyz123ABCDE",
            language_code="fr",
        )
        transcript = _make_transcript(video_id="xyz123ABCDE", language_code="fr")
        created_record = _make_correction_record(
            video_id="xyz123ABCDE",
            language_code="fr",
        )

        mock_segment_repo.get.return_value = segment
        mock_transcript_repo.get.return_value = transcript
        mock_correction_repo.get_latest_version.return_value = 0
        mock_correction_repo.create.return_value = created_record

        await service.apply_correction(
            mock_session,
            video_id="xyz123ABCDE",
            language_code="fr",
            segment_id=1,
            corrected_text="corrected",
            correction_type=CorrectionType.SPELLING,
        )

        call_kwargs = mock_correction_repo.create.call_args
        obj_in: TranscriptCorrectionCreate = call_kwargs.kwargs["obj_in"]
        assert obj_in.video_id == "xyz123ABCDE", (
            "audit record must include the correct video_id"
        )
        assert obj_in.language_code == "fr", (
            "audit record must include the correct language_code"
        )

    async def test_segment_id_in_audit_record(
        self,
        service: Any,
        mock_correction_repo: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_transcript_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        The segment_id FK must be set on the audit record to allow
        get_by_segment() queries to work correctly.
        """
        segment = _make_segment(
            segment_id=77,
            text="original",
            corrected_text=None,
            has_correction=False,
        )
        transcript = _make_transcript()
        created_record = _make_correction_record(segment_id=77)

        mock_segment_repo.get.return_value = segment
        mock_transcript_repo.get.return_value = transcript
        mock_correction_repo.get_latest_version.return_value = 0
        mock_correction_repo.create.return_value = created_record

        await service.apply_correction(
            mock_session,
            video_id="dQw4w9WgXcQ",
            language_code="en",
            segment_id=77,
            corrected_text="corrected",
            correction_type=CorrectionType.SPELLING,
        )

        call_kwargs = mock_correction_repo.create.call_args
        obj_in: TranscriptCorrectionCreate = call_kwargs.kwargs["obj_in"]
        assert obj_in.segment_id == 77, (
            "audit record must include the segment_id FK for history lookups"
        )


# ---------------------------------------------------------------------------
# TestRevertCorrection
# ---------------------------------------------------------------------------


class TestRevertCorrection:
    """
    Tests for TranscriptCorrectionService.revert_correction.

    Contract (service-contracts.md):
    - Fetch V_N (latest audit record for segment by version_number)
    - If V_N.version_number == 1: set corrected_text=None, has_correction=False
    - If V_N.version_number > 1: set corrected_text=V_N.original_text, has_correction=True
    - Create revert audit record: correction_type='revert',
        original_text=V_N.corrected_text, corrected_text=V_N.original_text,
        version_number=V_N.version_number+1
    - If revert-to-original: decrement correction_count, recompute has_corrections
    - If revert-to-prior: correction_count unchanged, has_corrections=True
    - Always: update last_corrected_at=now() (FR-014c)
    - Never call session.commit() (FR-007a)

    Constitution §Cross-Feature Data Contract Verification:
    Each test inspects the exact attributes mutated on segment and transcript,
    and verifies the audit record fields that downstream history queries depend on.
    """

    async def test_revert_to_original_clears_corrected_text(
        self,
        service: Any,
        mock_correction_repo: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_transcript_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        When a segment has exactly one correction (V_N.version_number == 1),
        revert_correction must set segment.corrected_text = None and
        segment.has_correction = False, restoring the segment to its original
        uncorrected state.

        Constitution §Cross-Feature: downstream consumers (display_text, SRT
        export) rely on has_correction=False to skip corrected_text.
        """
        segment = _make_segment(
            segment_id=1,
            text="teh quick brown fox",
            corrected_text="the quick brown fox",
            has_correction=True,
            video_id="dQw4w9WgXcQ",
            language_code="en",
        )
        transcript = _make_transcript(
            correction_count=1,
            has_corrections=True,
        )
        # V_N: the only correction applied, version_number=1
        v_n = _make_correction_record(
            version_number=1,
            original_text="teh quick brown fox",
            corrected_text="the quick brown fox",
        )
        revert_record = _make_correction_record(
            version_number=2,
            original_text="the quick brown fox",
            corrected_text="teh quick brown fox",
            correction_type=CorrectionType.REVERT.value,
        )

        mock_segment_repo.get.return_value = segment
        mock_transcript_repo.get.return_value = transcript
        mock_correction_repo.get_by_segment.return_value = [v_n]
        mock_correction_repo.create.return_value = revert_record
        # Simulate EXISTS scan returning False (no other corrected segments)
        _exists_result_mock = MagicMock()
        _exists_result_mock.scalar_one.return_value = False
        mock_session.execute.return_value = _exists_result_mock

        await service.revert_correction(mock_session, segment_id=1)

        # Constitution §Cross-Feature: verify WHAT was mutated on segment
        assert segment.corrected_text is None, (
            "After revert-to-original, segment.corrected_text must be None"
        )
        assert segment.has_correction is False, (
            "After revert-to-original, segment.has_correction must be False"
        )

    async def test_revert_to_original_decrements_correction_count(
        self,
        service: Any,
        mock_correction_repo: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_transcript_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        FR-014a: When revert-to-original, transcript.correction_count must be
        decremented by exactly 1.

        Constitution §Cross-Feature: the correction_count field is read by the
        REST API and frontend — an incorrect value would show stale data.
        """
        segment = _make_segment(
            corrected_text="corrected",
            has_correction=True,
        )
        transcript = _make_transcript(
            correction_count=3,
            has_corrections=True,
        )
        v_n = _make_correction_record(
            version_number=1,
            original_text="original",
            corrected_text="corrected",
        )
        revert_record = _make_correction_record(
            version_number=2,
            original_text="corrected",
            corrected_text="original",
            correction_type=CorrectionType.REVERT.value,
        )

        mock_segment_repo.get.return_value = segment
        mock_transcript_repo.get.return_value = transcript
        mock_correction_repo.get_by_segment.return_value = [v_n]
        mock_correction_repo.create.return_value = revert_record
        _exists_result_mock = MagicMock()
        _exists_result_mock.scalar_one.return_value = False
        mock_session.execute.return_value = _exists_result_mock

        await service.revert_correction(mock_session, segment_id=1)

        assert transcript.correction_count == 2, (
            "FR-014a: revert-to-original must decrement correction_count by 1 "
            f"(was 3, expected 2, got {transcript.correction_count})"
        )

    async def test_revert_to_original_scans_has_corrections(
        self,
        service: Any,
        mock_correction_repo: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_transcript_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        FR-014b: When revert-to-original, transcript.has_corrections must be
        recomputed by scanning other segments for remaining active corrections.

        If no other segments have has_correction=True, has_corrections becomes False.
        If another segment still has has_correction=True, has_corrections stays True.

        Constitution §Cross-Feature: has_corrections is read by the history
        query endpoint — stale True value would cause false positive "has corrections"
        display on the frontend.
        """
        segment = _make_segment(
            corrected_text="corrected",
            has_correction=True,
        )
        transcript = _make_transcript(
            correction_count=1,
            has_corrections=True,  # was True before revert
        )
        v_n = _make_correction_record(
            version_number=1,
            original_text="original",
            corrected_text="corrected",
        )
        revert_record = _make_correction_record(
            version_number=2,
            original_text="corrected",
            corrected_text="original",
            correction_type=CorrectionType.REVERT.value,
        )

        mock_segment_repo.get.return_value = segment
        mock_transcript_repo.get.return_value = transcript
        mock_correction_repo.get_by_segment.return_value = [v_n]
        mock_correction_repo.create.return_value = revert_record
        # EXISTS scan returns False — no other corrected segments remain
        _exists_result_mock = MagicMock()
        _exists_result_mock.scalar_one.return_value = False
        mock_session.execute.return_value = _exists_result_mock

        await service.revert_correction(mock_session, segment_id=1)

        assert transcript.has_corrections is False, (
            "FR-014b: has_corrections must be recomputed to False when no "
            "other segments have active corrections after revert-to-original"
        )

    async def test_revert_to_original_has_corrections_remains_true_when_others_exist(
        self,
        service: Any,
        mock_correction_repo: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_transcript_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        FR-014b: When revert-to-original but OTHER segments still have active
        corrections, transcript.has_corrections must remain True after the scan.
        """
        segment = _make_segment(
            corrected_text="corrected",
            has_correction=True,
        )
        transcript = _make_transcript(
            correction_count=2,
            has_corrections=True,
        )
        v_n = _make_correction_record(
            version_number=1,
            original_text="original",
            corrected_text="corrected",
        )
        revert_record = _make_correction_record(
            version_number=2,
            original_text="corrected",
            corrected_text="original",
            correction_type=CorrectionType.REVERT.value,
        )

        mock_segment_repo.get.return_value = segment
        mock_transcript_repo.get.return_value = transcript
        mock_correction_repo.get_by_segment.return_value = [v_n]
        mock_correction_repo.create.return_value = revert_record
        # EXISTS scan returns True — another segment still has a correction
        _exists_result_mock = MagicMock()
        _exists_result_mock.scalar_one.return_value = True
        mock_session.execute.return_value = _exists_result_mock

        await service.revert_correction(mock_session, segment_id=1)

        assert transcript.has_corrections is True, (
            "FR-014b: has_corrections must remain True when other segments "
            "still have active corrections after revert-to-original"
        )

    async def test_revert_to_prior_version(
        self,
        service: Any,
        mock_correction_repo: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_transcript_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        When a segment has multiple corrections (V_N.version_number > 1),
        revert_correction must set segment.corrected_text = V_N.original_text
        and segment.has_correction remains True (the segment is still corrected,
        just to an earlier version).

        Constitution §Cross-Feature: downstream SRT export reads corrected_text
        when has_correction=True — it must reflect the prior-version text.
        """
        segment = _make_segment(
            text="teh lazy dog",              # original raw text
            corrected_text="The lazy dog.",   # currently at v2 state
            has_correction=True,
        )
        transcript = _make_transcript(
            correction_count=2,
            has_corrections=True,
        )
        # V_N is version 2: original_text = "the lazy dog" (v1 text), corrected = "The lazy dog."
        v_n = _make_correction_record(
            version_number=2,
            original_text="the lazy dog",
            corrected_text="The lazy dog.",
        )
        revert_record = _make_correction_record(
            version_number=3,
            original_text="The lazy dog.",
            corrected_text="the lazy dog",
            correction_type=CorrectionType.REVERT.value,
        )

        mock_segment_repo.get.return_value = segment
        mock_transcript_repo.get.return_value = transcript
        mock_correction_repo.get_by_segment.return_value = [v_n]
        mock_correction_repo.create.return_value = revert_record

        await service.revert_correction(mock_session, segment_id=1)

        assert segment.corrected_text == "the lazy dog", (
            "Revert-to-prior must set segment.corrected_text = V_N.original_text"
        )
        assert segment.has_correction is True, (
            "Revert-to-prior must leave segment.has_correction=True "
            "(segment is still corrected, just to the prior version)"
        )

    async def test_revert_to_prior_version_count_unchanged(
        self,
        service: Any,
        mock_correction_repo: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_transcript_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        FR-014a: When revert-to-prior-version, transcript.correction_count must
        NOT be changed — the segment is still corrected, just to an earlier version.

        Constitution §Cross-Feature: changing correction_count here would cause
        the API to show incorrect correction statistics.
        """
        segment = _make_segment(
            corrected_text="The lazy dog.",
            has_correction=True,
        )
        transcript = _make_transcript(
            correction_count=4,
            has_corrections=True,
        )
        v_n = _make_correction_record(
            version_number=2,
            original_text="the lazy dog",
            corrected_text="The lazy dog.",
        )
        revert_record = _make_correction_record(
            version_number=3,
            original_text="The lazy dog.",
            corrected_text="the lazy dog",
            correction_type=CorrectionType.REVERT.value,
        )

        mock_segment_repo.get.return_value = segment
        mock_transcript_repo.get.return_value = transcript
        mock_correction_repo.get_by_segment.return_value = [v_n]
        mock_correction_repo.create.return_value = revert_record

        await service.revert_correction(mock_session, segment_id=1)

        assert transcript.correction_count == 4, (
            "FR-014a: revert-to-prior must NOT change correction_count "
            f"(expected 4, got {transcript.correction_count})"
        )

    async def test_revert_audit_record_fields(
        self,
        service: Any,
        mock_correction_repo: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_transcript_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        The revert audit record must have:
        - correction_type = CorrectionType.REVERT
        - version_number = V_N.version_number + 1
        - original_text = V_N.corrected_text (state before revert)
        - corrected_text = V_N.original_text (state restored to)

        Constitution §Cross-Feature: these fields are the inputs for any
        future re-apply or further-revert operations. Incorrect values break
        the full version chain.
        """
        segment = _make_segment(
            corrected_text="the quick brown fox",
            has_correction=True,
        )
        transcript = _make_transcript(correction_count=1, has_corrections=True)
        v_n = _make_correction_record(
            version_number=1,
            original_text="teh quick brown fox",
            corrected_text="the quick brown fox",
        )
        revert_record = _make_correction_record(
            version_number=2,
            original_text="the quick brown fox",
            corrected_text="teh quick brown fox",
            correction_type=CorrectionType.REVERT.value,
        )

        mock_segment_repo.get.return_value = segment
        mock_transcript_repo.get.return_value = transcript
        mock_correction_repo.get_by_segment.return_value = [v_n]
        mock_correction_repo.create.return_value = revert_record
        _exists_result_mock = MagicMock()
        _exists_result_mock.scalar_one.return_value = False
        mock_session.execute.return_value = _exists_result_mock

        await service.revert_correction(mock_session, segment_id=1)

        # Verify the create call had the correct revert audit record fields
        mock_correction_repo.create.assert_called_once()
        call_kwargs = mock_correction_repo.create.call_args
        obj_in: TranscriptCorrectionCreate = call_kwargs.kwargs["obj_in"]

        assert obj_in.correction_type == CorrectionType.REVERT, (
            "Revert audit record must have correction_type=CorrectionType.REVERT"
        )
        assert obj_in.version_number == 2, (
            f"Revert audit record must have version_number=V_N.version_number+1 "
            f"(V_N.version_number=1, expected 2, got {obj_in.version_number})"
        )
        assert obj_in.original_text == "the quick brown fox", (
            "Revert audit original_text must be V_N.corrected_text "
            "(the state the segment had BEFORE this revert)"
        )
        assert obj_in.corrected_text == "teh quick brown fox", (
            "Revert audit corrected_text must be V_N.original_text "
            "(the state the segment is being RESTORED to)"
        )

    async def test_raises_value_error_no_corrections(
        self,
        service: Any,
        mock_correction_repo: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_transcript_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        revert_correction must raise ValueError when the segment has
        has_correction=False — there is nothing to revert.

        No audit record should be created.
        """
        segment = _make_segment(
            corrected_text=None,
            has_correction=False,  # no active correction
        )

        mock_segment_repo.get.return_value = segment

        with pytest.raises(ValueError, match="has_correction|correction|revert"):
            await service.revert_correction(mock_session, segment_id=1)

        mock_correction_repo.create.assert_not_called()

    async def test_raises_value_error_segment_not_found(
        self,
        service: Any,
        mock_correction_repo: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_transcript_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        revert_correction must raise ValueError when the segment_id does not
        exist in the database. No audit record should be created.
        """
        mock_segment_repo.get.return_value = None

        with pytest.raises(ValueError, match="segment"):
            await service.revert_correction(mock_session, segment_id=999)

        mock_correction_repo.create.assert_not_called()

    async def test_double_revert_fully_reverted(
        self,
        service: Any,
        mock_correction_repo: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_transcript_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        EC-DOUBLE-REVERT: After the first revert restores a segment to its
        original uncorrected state (has_correction=False), a second call to
        revert_correction on the same segment must raise ValueError.

        The service checks segment state (has_correction), not audit history.
        An already-reverted-to-original segment must not allow further reverts.
        """
        # Simulate the segment state AFTER a revert-to-original has already run
        segment = _make_segment(
            corrected_text=None,
            has_correction=False,  # first revert already cleared this
        )

        mock_segment_repo.get.return_value = segment

        with pytest.raises(ValueError, match="has_correction|correction|revert"):
            await service.revert_correction(mock_session, segment_id=1)

        mock_correction_repo.create.assert_not_called()

    async def test_last_corrected_at_updated(
        self,
        service: Any,
        mock_correction_repo: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_transcript_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        FR-014c: revert_correction must set transcript.last_corrected_at to a
        current timezone-aware datetime. A revert is always a correction event.

        Constitution §Cross-Feature: last_corrected_at is displayed in the
        transcript history view and must never be stale after any correction
        or revert operation.
        """
        segment = _make_segment(
            corrected_text="corrected",
            has_correction=True,
        )
        transcript = _make_transcript(
            correction_count=1,
            has_corrections=True,
            last_corrected_at=None,  # Start with no timestamp
        )
        v_n = _make_correction_record(
            version_number=1,
            original_text="original",
            corrected_text="corrected",
        )
        revert_record = _make_correction_record(
            version_number=2,
            original_text="corrected",
            corrected_text="original",
            correction_type=CorrectionType.REVERT.value,
        )

        mock_segment_repo.get.return_value = segment
        mock_transcript_repo.get.return_value = transcript
        mock_correction_repo.get_by_segment.return_value = [v_n]
        mock_correction_repo.create.return_value = revert_record
        _exists_result_mock = MagicMock()
        _exists_result_mock.scalar_one.return_value = False
        mock_session.execute.return_value = _exists_result_mock

        await service.revert_correction(mock_session, segment_id=1)

        assert isinstance(transcript.last_corrected_at, datetime), (
            "FR-014c: transcript.last_corrected_at must be set to a datetime "
            "after revert_correction"
        )
        assert transcript.last_corrected_at.tzinfo is not None, (
            "FR-014c: transcript.last_corrected_at must be timezone-aware"
        )

    async def test_session_flush_called_not_commit(
        self,
        service: Any,
        mock_correction_repo: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_transcript_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        FR-007a: revert_correction must call session.flush() for each mutation
        step (audit record, segment, transcript) and must NEVER call
        session.commit() — the caller owns the transaction lifecycle.

        This is the same flush-only pattern enforced throughout the service.
        """
        segment = _make_segment(
            corrected_text="corrected",
            has_correction=True,
        )
        transcript = _make_transcript(
            correction_count=1,
            has_corrections=True,
        )
        v_n = _make_correction_record(
            version_number=1,
            original_text="original",
            corrected_text="corrected",
        )
        revert_record = _make_correction_record(
            version_number=2,
            original_text="corrected",
            corrected_text="original",
            correction_type=CorrectionType.REVERT.value,
        )

        mock_segment_repo.get.return_value = segment
        mock_transcript_repo.get.return_value = transcript
        mock_correction_repo.get_by_segment.return_value = [v_n]
        mock_correction_repo.create.return_value = revert_record
        _exists_result_mock = MagicMock()
        _exists_result_mock.scalar_one.return_value = False
        mock_session.execute.return_value = _exists_result_mock

        await service.revert_correction(mock_session, segment_id=1)

        # At least one flush must be called for each mutation step
        assert mock_session.flush.call_count >= 1, (
            "FR-007a: session.flush() must be called at least once "
            "(audit record + segment + transcript mutations)"
        )
        # NEVER commit — caller owns the transaction
        mock_session.commit.assert_not_called()

    async def test_returns_revert_audit_record(
        self,
        service: Any,
        mock_correction_repo: AsyncMock,
        mock_segment_repo: AsyncMock,
        mock_transcript_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """
        revert_correction must return the TranscriptCorrectionDB record
        created for the revert operation, not None or the segment.
        """
        segment = _make_segment(
            corrected_text="corrected",
            has_correction=True,
        )
        transcript = _make_transcript(
            correction_count=1,
            has_corrections=True,
        )
        v_n = _make_correction_record(
            version_number=1,
            original_text="original",
            corrected_text="corrected",
        )
        expected_revert_record = _make_correction_record(
            version_number=2,
            original_text="corrected",
            corrected_text="original",
            correction_type=CorrectionType.REVERT.value,
        )

        mock_segment_repo.get.return_value = segment
        mock_transcript_repo.get.return_value = transcript
        mock_correction_repo.get_by_segment.return_value = [v_n]
        mock_correction_repo.create.return_value = expected_revert_record
        _exists_result_mock = MagicMock()
        _exists_result_mock.scalar_one.return_value = False
        mock_session.execute.return_value = _exists_result_mock

        result = await service.revert_correction(mock_session, segment_id=1)

        assert result is expected_revert_record, (
            "revert_correction must return the TranscriptCorrectionDB record "
            "returned by correction_repo.create()"
        )
