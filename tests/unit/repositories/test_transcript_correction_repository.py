"""
Tests for TranscriptCorrectionRepository (Feature 033 — T008).

Covers all public methods:
- update()  — overridden to raise NotImplementedError (FR-018 immutability)
- delete()  — overridden to raise NotImplementedError (FR-018 immutability)
- get()     — lookup by UUID primary key
- exists()  — presence check by UUID primary key
- get_by_segment() — corrections for a (segment_id, video_id, language_code) triple,
                     ordered by version_number DESC
- get_by_video()   — paginated corrections for a (video_id, language_code) pair
- count_by_video() — total correction count for a (video_id, language_code) pair
- get_latest_version() — highest version_number for a segment, or 0 when none exist

Mock strategy: every test creates a ``MagicMock(spec=AsyncSession)`` whose
``execute`` attribute is an ``AsyncMock``.  This avoids real database I/O and
follows the pattern used in ``test_canonical_tag_repository.py`` and
``test_tag_operation_log_repository.py``.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from uuid_utils import uuid7

from chronovista.db.models import TranscriptCorrection as TranscriptCorrectionDB
from chronovista.models.enums import CorrectionType
from chronovista.models.transcript_correction import TranscriptCorrectionCreate
from chronovista.repositories.transcript_correction_repository import (
    TranscriptCorrectionRepository,
)
from tests.factories.transcript_correction_factory import (
    TranscriptCorrectionFactory,
    create_transcript_correction,
)

# Ensures every async test in this module is recognised by pytest-asyncio
# regardless of how coverage is invoked (see CLAUDE.md §pytest-asyncio section).
pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_uuid() -> uuid.UUID:
    """Return a UUIDv7 expressed as a stdlib ``uuid.UUID`` instance."""
    return uuid.UUID(bytes=uuid7().bytes)


def _make_correction_db(
    *,
    id: uuid.UUID | None = None,
    video_id: str = "dQw4w9WgXcQ",
    language_code: str = "en",
    segment_id: int | None = 1,
    correction_type: str = CorrectionType.SPELLING.value,
    original_text: str = "teh quick brown fox",
    corrected_text: str = "the quick brown fox",
    correction_note: str | None = None,
    corrected_by_user_id: str | None = "cli",
    corrected_at: datetime | None = None,
    version_number: int = 1,
) -> TranscriptCorrectionDB:
    """Build an in-memory TranscriptCorrectionDB instance without a DB session.

    Parameters
    ----------
    id : uuid.UUID, optional
        Primary key; generated via UUIDv7 when omitted.
    video_id : str
        YouTube video ID (max 20 chars).
    language_code : str
        BCP-47 language code.
    segment_id : int or None
        Optional FK to transcript_segments.id.
    correction_type : str
        One of the CorrectionType enum values.
    original_text : str
        Text before the correction.
    corrected_text : str
        Text after the correction.
    correction_note : str or None
        Optional human-readable note.
    corrected_by_user_id : str or None
        Identifier of the user who made the correction.
    corrected_at : datetime or None
        Timestamp; defaults to now(UTC).
    version_number : int
        Must be >= 1.

    Returns
    -------
    TranscriptCorrectionDB
        In-memory ORM instance.
    """
    return TranscriptCorrectionDB(
        id=id or _make_uuid(),
        video_id=video_id,
        language_code=language_code,
        segment_id=segment_id,
        correction_type=correction_type,
        original_text=original_text,
        corrected_text=corrected_text,
        correction_note=correction_note,
        corrected_by_user_id=corrected_by_user_id,
        corrected_at=corrected_at or datetime.now(tz=timezone.utc),
        version_number=version_number,
    )


def _make_mock_session() -> MagicMock:
    """Create a MagicMock AsyncSession with an AsyncMock execute attribute.

    Returns
    -------
    MagicMock
        Mock session compatible with AsyncSession interface.
    """
    session = MagicMock(spec=AsyncSession)
    session.execute = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# TestTranscriptCorrectionRepositoryImmutability
# ---------------------------------------------------------------------------


class TestTranscriptCorrectionRepositoryImmutability:
    """Verify that update() and delete() raise NotImplementedError (FR-018).

    The transcript corrections table is an append-only audit log. No
    mutation or deletion is permitted after a row has been inserted.
    """

    @pytest.fixture
    def repository(self) -> TranscriptCorrectionRepository:
        """Provide a fresh repository instance for each test."""
        return TranscriptCorrectionRepository()

    @pytest.fixture
    def mock_session(self) -> MagicMock:
        """Provide a mock async session for each test."""
        return _make_mock_session()

    async def test_update_raises_not_implemented(
        self,
        repository: TranscriptCorrectionRepository,
        mock_session: MagicMock,
    ) -> None:
        """Calling update() must raise NotImplementedError with an 'immutable' message.

        FR-018 mandates that transcript corrections are append-only. The
        repository must actively prevent any caller from mutating an existing
        row via the standard repository interface.
        """
        db_obj = _make_correction_db()
        update_data: dict[str, Any] = {"corrected_text": "something different"}

        with pytest.raises(NotImplementedError, match="immutable"):
            await repository.update(
                mock_session,
                db_obj=db_obj,
                obj_in=update_data,
            )

        # Session must never be touched — no database round-trip should occur.
        mock_session.execute.assert_not_called()

    async def test_delete_raises_not_implemented(
        self,
        repository: TranscriptCorrectionRepository,
        mock_session: MagicMock,
    ) -> None:
        """Calling delete() must raise NotImplementedError with an 'immutable' message.

        FR-018 mandates that transcript corrections are append-only. Rows must
        never be removed once inserted.
        """
        correction_id = _make_uuid()

        with pytest.raises(NotImplementedError, match="immutable"):
            await repository.delete(mock_session, id=correction_id)

        mock_session.execute.assert_not_called()


# ---------------------------------------------------------------------------
# TestTranscriptCorrectionRepositoryGet
# ---------------------------------------------------------------------------


class TestTranscriptCorrectionRepositoryGet:
    """Tests for get() and exists() — primary-key lookup methods."""

    @pytest.fixture
    def repository(self) -> TranscriptCorrectionRepository:
        """Provide a fresh repository instance for each test."""
        return TranscriptCorrectionRepository()

    @pytest.fixture
    def mock_session(self) -> MagicMock:
        """Provide a mock async session for each test."""
        return _make_mock_session()

    async def test_get_returns_correction_by_id(
        self,
        repository: TranscriptCorrectionRepository,
        mock_session: MagicMock,
    ) -> None:
        """get() returns the matching TranscriptCorrectionDB when the row exists."""
        correction = _make_correction_db(video_id="abc123ABC12", version_number=1)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = correction
        mock_session.execute.return_value = mock_result

        result = await repository.get(mock_session, correction.id)

        assert result is correction
        mock_session.execute.assert_called_once()

    async def test_get_returns_none_for_missing(
        self,
        repository: TranscriptCorrectionRepository,
        mock_session: MagicMock,
    ) -> None:
        """get() returns None when no row matches the given UUID."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.get(mock_session, _make_uuid())

        assert result is None
        mock_session.execute.assert_called_once()

    async def test_exists_returns_true_for_existing(
        self,
        repository: TranscriptCorrectionRepository,
        mock_session: MagicMock,
    ) -> None:
        """exists() returns True when the row is present in the database."""
        correction_id = _make_uuid()

        mock_result = MagicMock()
        # first() returns a non-None row tuple when the row exists
        mock_result.first.return_value = (correction_id,)
        mock_session.execute.return_value = mock_result

        result = await repository.exists(mock_session, correction_id)

        assert result is True
        mock_session.execute.assert_called_once()

    async def test_exists_returns_false_for_missing(
        self,
        repository: TranscriptCorrectionRepository,
        mock_session: MagicMock,
    ) -> None:
        """exists() returns False when no row matches the given UUID."""
        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.exists(mock_session, _make_uuid())

        assert result is False
        mock_session.execute.assert_called_once()


# ---------------------------------------------------------------------------
# TestTranscriptCorrectionRepositoryQueries
# ---------------------------------------------------------------------------


class TestTranscriptCorrectionRepositoryQueries:
    """Tests for the domain-specific query methods.

    Covers:
    - get_by_segment()       — corrections for a segment, ordered version DESC
    - get_by_video()         — paginated corrections for a video transcript
    - count_by_video()       — total correction count for a video transcript
    - get_latest_version()   — highest version_number, or 0 if no corrections
    """

    @pytest.fixture
    def repository(self) -> TranscriptCorrectionRepository:
        """Provide a fresh repository instance for each test."""
        return TranscriptCorrectionRepository()

    @pytest.fixture
    def mock_session(self) -> MagicMock:
        """Provide a mock async session for each test."""
        return _make_mock_session()

    # ------------------------------------------------------------------
    # get_by_segment
    # ------------------------------------------------------------------

    async def test_get_by_segment_orders_by_version_desc(
        self,
        repository: TranscriptCorrectionRepository,
        mock_session: MagicMock,
    ) -> None:
        """get_by_segment() returns corrections ordered by version_number DESC.

        The repository must order results so that the most recent correction
        (highest version_number) appears first. This is the canonical order
        consumers expect when replaying the correction chain for a segment.
        """
        # Build three corrections for the same segment in descending version order
        # as the DB would return them after ORDER BY version_number DESC.
        correction_v3 = _make_correction_db(
            video_id="dQw4w9WgXcQ",
            language_code="en",
            segment_id=42,
            version_number=3,
            original_text="original v2 text",
            corrected_text="corrected v3 text",
        )
        correction_v2 = _make_correction_db(
            video_id="dQw4w9WgXcQ",
            language_code="en",
            segment_id=42,
            version_number=2,
            original_text="original v1 text",
            corrected_text="corrected v2 text",
        )
        correction_v1 = _make_correction_db(
            video_id="dQw4w9WgXcQ",
            language_code="en",
            segment_id=42,
            version_number=1,
            original_text="teh quick brown fox",
            corrected_text="the quick brown fox",
        )

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [correction_v3, correction_v2, correction_v1]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repository.get_by_segment(
            mock_session,
            video_id="dQw4w9WgXcQ",
            language_code="en",
            segment_id=42,
        )

        assert len(results) == 3
        # Verify descending order by version_number
        assert results[0].version_number == 3
        assert results[1].version_number == 2
        assert results[2].version_number == 1
        mock_session.execute.assert_called_once()

    async def test_get_by_segment_empty_list_for_no_corrections(
        self,
        repository: TranscriptCorrectionRepository,
        mock_session: MagicMock,
    ) -> None:
        """get_by_segment() returns an empty list when no corrections exist for the segment."""
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repository.get_by_segment(
            mock_session,
            video_id="dQw4w9WgXcQ",
            language_code="en",
            segment_id=999,
        )

        assert results == []
        mock_session.execute.assert_called_once()

    # ------------------------------------------------------------------
    # get_by_video
    # ------------------------------------------------------------------

    async def test_get_by_video_returns_paginated_results_with_count(
        self,
        repository: TranscriptCorrectionRepository,
        mock_session: MagicMock,
    ) -> None:
        """get_by_video() returns (items, total) tuple with pagination applied.

        The total reflects the full row count for the (video_id, language_code)
        pair, not just the current page. Items contain only the requested page.
        """
        correction_a = _make_correction_db(
            video_id="dQw4w9WgXcQ",
            language_code="en",
            segment_id=1,
            version_number=1,
            original_text="teh",
            corrected_text="the",
        )
        correction_b = _make_correction_db(
            video_id="dQw4w9WgXcQ",
            language_code="en",
            segment_id=2,
            version_number=1,
            original_text="wold",
            corrected_text="world",
        )

        # First execute: count query
        count_result = MagicMock()
        count_result.scalar_one.return_value = 5  # Total across all pages

        # Second execute: items query (page returns 2 of 5)
        items_scalars = MagicMock()
        items_scalars.all.return_value = [correction_a, correction_b]
        items_result = MagicMock()
        items_result.scalars.return_value = items_scalars

        mock_session.execute.side_effect = [count_result, items_result]

        items, total = await repository.get_by_video(
            mock_session,
            video_id="dQw4w9WgXcQ",
            language_code="en",
            skip=0,
            limit=2,
        )

        assert total == 5
        assert len(items) == 2
        assert items[0] is correction_a
        assert items[1] is correction_b
        assert mock_session.execute.call_count == 2

    async def test_get_by_video_requires_language_code(
        self,
        repository: TranscriptCorrectionRepository,
        mock_session: MagicMock,
    ) -> None:
        """get_by_video() filters by both video_id AND language_code.

        Corrections for the same video in a different language must not appear
        in results. The query must include a language_code equality predicate.
        """
        correction_en = _make_correction_db(
            video_id="dQw4w9WgXcQ",
            language_code="en",
            segment_id=1,
            version_number=1,
            original_text="teh fox",
            corrected_text="the fox",
        )

        # Count query for "en" returns 1 (the "es" corrections are excluded)
        count_result = MagicMock()
        count_result.scalar_one.return_value = 1

        items_scalars = MagicMock()
        items_scalars.all.return_value = [correction_en]
        items_result = MagicMock()
        items_result.scalars.return_value = items_scalars

        mock_session.execute.side_effect = [count_result, items_result]

        items, total = await repository.get_by_video(
            mock_session,
            video_id="dQw4w9WgXcQ",
            language_code="en",
        )

        assert total == 1
        assert len(items) == 1
        assert items[0].language_code == "en"

        # Inspect SQL to confirm language_code is in the WHERE clause
        count_stmt = mock_session.execute.call_args_list[0].args[0]
        sql_string = str(count_stmt.compile(compile_kwargs={"literal_binds": False}))
        assert "language_code" in sql_string, (
            "Expected language_code filter in get_by_video SQL; "
            f"got: {sql_string}"
        )

    # ------------------------------------------------------------------
    # count_by_video
    # ------------------------------------------------------------------

    async def test_count_by_video_returns_total(
        self,
        repository: TranscriptCorrectionRepository,
        mock_session: MagicMock,
    ) -> None:
        """count_by_video() returns the total number of corrections for a video transcript."""
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 7
        mock_session.execute.return_value = mock_result

        count = await repository.count_by_video(
            mock_session,
            video_id="dQw4w9WgXcQ",
            language_code="en",
        )

        assert count == 7
        mock_session.execute.assert_called_once()

    async def test_count_by_video_returns_zero_when_no_corrections(
        self,
        repository: TranscriptCorrectionRepository,
        mock_session: MagicMock,
    ) -> None:
        """count_by_video() returns 0 when the video transcript has no corrections."""
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 0
        mock_session.execute.return_value = mock_result

        count = await repository.count_by_video(
            mock_session,
            video_id="nonExistVid1",
            language_code="en",
        )

        assert count == 0
        mock_session.execute.assert_called_once()

    # ------------------------------------------------------------------
    # get_latest_version
    # ------------------------------------------------------------------

    async def test_get_latest_version_returns_max(
        self,
        repository: TranscriptCorrectionRepository,
        mock_session: MagicMock,
    ) -> None:
        """get_latest_version() returns the highest version_number for the segment.

        This value is used by the apply-correction service to determine the
        version_number to assign to the next correction in the chain.
        """
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [1, 2, 3, 4]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        version = await repository.get_latest_version(
            mock_session,
            video_id="dQw4w9WgXcQ",
            language_code="en",
            segment_id=42,
        )

        assert version == 4
        mock_session.execute.assert_called_once()

    async def test_get_latest_version_returns_zero_for_no_corrections(
        self,
        repository: TranscriptCorrectionRepository,
        mock_session: MagicMock,
    ) -> None:
        """get_latest_version() returns 0 when the segment has no corrections yet.

        The caller uses this as a sentinel value: 0 means no prior corrections
        exist, so the next correction should be assigned version_number = 1.
        """
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        version = await repository.get_latest_version(
            mock_session,
            video_id="dQw4w9WgXcQ",
            language_code="en",
            segment_id=999,
        )

        assert version == 0
        mock_session.execute.assert_called_once()


# ---------------------------------------------------------------------------
# TestTranscriptCorrectionRepositoryInitialization
# ---------------------------------------------------------------------------


@pytest.mark.filterwarnings("ignore::pytest.PytestWarning")
class TestTranscriptCorrectionRepositoryInitialization:
    """Tests for repository initialization.

    Note: These tests are synchronous even though the module-level
    pytestmark applies asyncio mode to the entire module. The
    filterwarnings decorator suppresses unrelated asyncio warnings.
    """

    def test_repository_can_be_instantiated(self) -> None:
        """TranscriptCorrectionRepository can be constructed without arguments."""
        repo = TranscriptCorrectionRepository()
        assert repo is not None

    def test_repository_model_attribute_is_correct(self) -> None:
        """repository.model points to TranscriptCorrectionDB ORM class."""
        repo = TranscriptCorrectionRepository()
        assert repo.model is TranscriptCorrectionDB


# ---------------------------------------------------------------------------
# TestTranscriptCorrectionRepositoryFactoryIntegration
# ---------------------------------------------------------------------------


class TestTranscriptCorrectionRepositoryFactoryIntegration:
    """Smoke-tests that the factory produces valid ORM instances compatible
    with the repository interface.  These tests do not touch a real database.
    """

    @pytest.fixture
    def repository(self) -> TranscriptCorrectionRepository:
        """Provide a fresh repository instance for each test."""
        return TranscriptCorrectionRepository()

    @pytest.fixture
    def mock_session(self) -> MagicMock:
        """Provide a mock async session for each test."""
        return _make_mock_session()

    async def test_factory_built_correction_is_accepted_by_get(
        self,
        repository: TranscriptCorrectionRepository,
        mock_session: MagicMock,
    ) -> None:
        """A correction built by TranscriptCorrectionFactory can be returned from get()."""
        correction = TranscriptCorrectionFactory.build()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = correction
        mock_session.execute.return_value = mock_result

        result = await repository.get(mock_session, correction.id)

        assert result is correction

    async def test_create_transcript_correction_convenience_function(
        self,
        repository: TranscriptCorrectionRepository,
        mock_session: MagicMock,
    ) -> None:
        """create_transcript_correction() helper returns a valid ORM instance."""
        correction = create_transcript_correction(
            video_id="9bZkp7q19f0",
            language_code="es",
            version_number=2,
        )

        assert isinstance(correction, TranscriptCorrectionDB)
        assert correction.video_id == "9bZkp7q19f0"
        assert correction.language_code == "es"
        assert correction.version_number == 2

    async def test_factory_override_correction_type(
        self,
        repository: TranscriptCorrectionRepository,
        mock_session: MagicMock,
    ) -> None:
        """Factory produces corrections with overridden correction_type values."""
        for ct in CorrectionType:
            correction = TranscriptCorrectionFactory.build(
                correction_type=ct.value,
                original_text="before",
                corrected_text="after",
            )
            assert correction.correction_type == ct.value
