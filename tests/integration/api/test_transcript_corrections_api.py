"""Integration tests for transcript correction API endpoints (Feature 034).

Covers:
  - T006: POST /api/v1/videos/{video_id}/transcript/segments/{segment_id}/corrections
  - T008: POST /api/v1/videos/{video_id}/transcript/segments/{segment_id}/corrections/revert
  - T010: GET  /api/v1/videos/{video_id}/transcript/segments/{segment_id}/corrections

All tests require an integration database. Each test class seeds its own data
via the ``seed_test_data`` fixture and cleans up after itself to maintain
isolation from other integration test files.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, AsyncGenerator
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import (
    Channel as ChannelDB,
    TranscriptCorrection as TranscriptCorrectionDB,
    TranscriptSegment as TranscriptSegmentDB,
    Video as VideoDB,
    VideoTranscript as VideoTranscriptDB,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

# CRITICAL: Ensures all async tests in this module run with pytest-asyncio
pytestmark = pytest.mark.asyncio

# ---------------------------------------------------------------------------
# Unique stable IDs — chosen to avoid collisions with other test files
# ---------------------------------------------------------------------------
_CHANNEL_ID = "UCtcorr_test_ch001"  # 18 chars — within 24 char limit
_VIDEO_ID = "corr_test_vid01"  # 15 chars — within 20 char limit
_LANGUAGE_CODE = "en"

# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

def _corrections_url(video_id: str, segment_id: int | str) -> str:
    """Return the corrections submit/list URL for a given video and segment."""
    return f"/api/v1/videos/{video_id}/transcript/segments/{segment_id}/corrections"


def _revert_url(video_id: str, segment_id: int | str) -> str:
    """Return the revert URL for a given video and segment."""
    return f"/api/v1/videos/{video_id}/transcript/segments/{segment_id}/corrections/revert"


# ---------------------------------------------------------------------------
# Shared seed fixture
# ---------------------------------------------------------------------------


@pytest.fixture
async def seed_test_data(
    integration_session_factory: "async_sessionmaker[AsyncSession]",
) -> AsyncGenerator[dict[str, Any], None]:
    """Seed database with a channel, video, transcript, and segment for correction tests.

    Yields a dict with ``video_id``, ``segment_id``, ``language_code``, and
    ``original_text`` so individual tests can reference the seeded records.
    Cleans up all created rows after each test in FK-reverse order to avoid
    constraint violations.
    """
    async with integration_session_factory() as session:
        # ---- Channel (FK for videos) ----
        existing_channel = (
            await session.execute(
                select(ChannelDB).where(ChannelDB.channel_id == _CHANNEL_ID)
            )
        ).scalar_one_or_none()
        if not existing_channel:
            channel = ChannelDB(
                channel_id=_CHANNEL_ID,
                title="Transcript Correction Test Channel",
            )
            session.add(channel)

        # ---- Video ----
        existing_video = (
            await session.execute(
                select(VideoDB).where(VideoDB.video_id == _VIDEO_ID)
            )
        ).scalar_one_or_none()
        if not existing_video:
            video = VideoDB(
                video_id=_VIDEO_ID,
                channel_id=_CHANNEL_ID,
                title="Transcript Correction Test Video",
                description="Integration test video for Feature 034",
                upload_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
                duration=300,
            )
            session.add(video)

        # ---- VideoTranscript ----
        existing_transcript = (
            await session.execute(
                select(VideoTranscriptDB).where(
                    VideoTranscriptDB.video_id == _VIDEO_ID,
                    VideoTranscriptDB.language_code == _LANGUAGE_CODE,
                )
            )
        ).scalar_one_or_none()
        if not existing_transcript:
            transcript = VideoTranscriptDB(
                video_id=_VIDEO_ID,
                language_code=_LANGUAGE_CODE,
                transcript_text="teh quick brown fox",
                transcript_type="MANUAL",
                download_reason="USER_REQUEST",
                is_cc=False,
                is_auto_synced=False,
                track_kind="standard",
            )
            session.add(transcript)

        await session.commit()

        # ---- TranscriptSegment (created fresh per test invocation) ----
        segment = TranscriptSegmentDB(
            video_id=_VIDEO_ID,
            language_code=_LANGUAGE_CODE,
            text="teh quick brown fox",
            start_time=0.0,
            duration=2.5,
            end_time=2.5,
            sequence_number=0,
            has_correction=False,
        )
        session.add(segment)
        await session.commit()

        # Retrieve the auto-generated segment PK
        result = await session.execute(
            select(TranscriptSegmentDB).where(
                TranscriptSegmentDB.id == segment.id,
            )
        )
        seeded_segment = result.scalar_one()

        yield {
            "video_id": _VIDEO_ID,
            "segment_id": seeded_segment.id,
            "language_code": _LANGUAGE_CODE,
            "original_text": "teh quick brown fox",
        }

        # ---- Cleanup (FK reverse order) ----
        await session.execute(
            delete(TranscriptCorrectionDB).where(
                TranscriptCorrectionDB.video_id == _VIDEO_ID
            )
        )
        await session.execute(
            delete(TranscriptSegmentDB).where(
                TranscriptSegmentDB.video_id == _VIDEO_ID
            )
        )
        await session.execute(
            delete(VideoTranscriptDB).where(VideoTranscriptDB.video_id == _VIDEO_ID)
        )
        await session.execute(
            delete(VideoDB).where(VideoDB.video_id == _VIDEO_ID)
        )
        await session.execute(
            delete(ChannelDB).where(ChannelDB.channel_id == _CHANNEL_ID)
        )
        await session.commit()


# ---------------------------------------------------------------------------
# T006 — Submit Correction endpoint tests
# ---------------------------------------------------------------------------


class TestSubmitCorrection:
    """Tests for POST /api/v1/videos/{video_id}/transcript/segments/{segment_id}/corrections."""

    async def test_submit_correction_success_201(
        self,
        async_client: AsyncClient,
        seed_test_data: dict[str, Any],
    ) -> None:
        """Submit a valid spelling correction and verify the 201 response structure.

        Verifies that the response contains the correction audit record with all
        required fields and the updated segment state reflecting the correction.
        """
        video_id = seed_test_data["video_id"]
        segment_id = seed_test_data["segment_id"]
        language_code = seed_test_data["language_code"]
        corrected = "the quick brown fox"

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.post(
                _corrections_url(video_id, segment_id),
                params={"language_code": language_code},
                json={
                    "corrected_text": corrected,
                    "correction_type": "spelling",
                },
            )

        assert response.status_code == 201, response.text
        body = response.json()

        # Top-level shape
        assert "data" in body
        data = body["data"]

        # Correction audit record fields
        correction = data["correction"]
        assert correction["video_id"] == video_id
        assert correction["segment_id"] == segment_id
        assert correction["correction_type"] == "spelling"
        assert correction["original_text"] == seed_test_data["original_text"]
        assert correction["corrected_text"] == corrected
        assert correction["version_number"] == 1
        assert "id" in correction
        assert "corrected_at" in correction
        assert correction["correction_note"] is None
        assert correction["corrected_by_user_id"] == "user:local"

        # Segment state
        segment_state = data["segment_state"]
        assert segment_state["has_correction"] is True
        assert segment_state["effective_text"] == corrected

    async def test_submit_correction_with_optional_fields(
        self,
        async_client: AsyncClient,
        seed_test_data: dict[str, Any],
    ) -> None:
        """Submit a correction with optional correction_note and corrected_by_user_id.

        Verifies both optional fields are persisted and returned in the response.
        """
        video_id = seed_test_data["video_id"]
        segment_id = seed_test_data["segment_id"]
        language_code = seed_test_data["language_code"]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.post(
                _corrections_url(video_id, segment_id),
                params={"language_code": language_code},
                json={
                    "corrected_text": "the quick brown fox",
                    "correction_type": "asr_error",
                    "correction_note": "Fixed common ASR mistake",
                    "corrected_by_user_id": "user_test_001",
                },
            )

        assert response.status_code == 201, response.text
        correction = response.json()["data"]["correction"]
        assert correction["correction_note"] == "Fixed common ASR mistake"
        assert correction["corrected_by_user_id"] == "user_test_001"

    async def test_submit_correction_defaults_corrected_by_user_id_to_actor_user_local(
        self,
        async_client: AsyncClient,
        seed_test_data: dict[str, Any],
    ) -> None:
        """Submit a correction without corrected_by_user_id — it must default to 'user:local'.

        When the client omits corrected_by_user_id (or sends null), the endpoint
        must substitute ACTOR_USER_LOCAL ("user:local") so audit records always
        have a non-null actor identifier.
        """
        video_id = seed_test_data["video_id"]
        segment_id = seed_test_data["segment_id"]
        language_code = seed_test_data["language_code"]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.post(
                _corrections_url(video_id, segment_id),
                params={"language_code": language_code},
                json={
                    "corrected_text": "the quick brown fox",
                    "correction_type": "spelling",
                },
            )

        assert response.status_code == 201, response.text
        correction = response.json()["data"]["correction"]
        assert correction["corrected_by_user_id"] == "user:local", (
            f"Expected 'user:local' default, got: {correction['corrected_by_user_id']}"
        )

    async def test_submit_correction_explicit_null_corrected_by_user_id_defaults(
        self,
        async_client: AsyncClient,
        seed_test_data: dict[str, Any],
    ) -> None:
        """Submit a correction with explicit corrected_by_user_id=null — must default to 'user:local'.

        Explicitly sending null for corrected_by_user_id should trigger the same
        default as omitting the field entirely.
        """
        video_id = seed_test_data["video_id"]
        segment_id = seed_test_data["segment_id"]
        language_code = seed_test_data["language_code"]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.post(
                _corrections_url(video_id, segment_id),
                params={"language_code": language_code},
                json={
                    "corrected_text": "the quick brown fox",
                    "correction_type": "spelling",
                    "corrected_by_user_id": None,
                },
            )

        assert response.status_code == 201, response.text
        correction = response.json()["data"]["correction"]
        assert correction["corrected_by_user_id"] == "user:local", (
            f"Expected 'user:local' for explicit null, got: {correction['corrected_by_user_id']}"
        )

    async def test_submit_correction_404_nonexistent_video(
        self,
        async_client: AsyncClient,
        seed_test_data: dict[str, Any],
    ) -> None:
        """POST to a non-existent video_id must return 404 with code=NOT_FOUND."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.post(
                _corrections_url("NONEXISTENT_VID1", 1),
                params={"language_code": "en"},
                json={
                    "corrected_text": "the quick brown fox",
                    "correction_type": "spelling",
                },
            )

        assert response.status_code == 404, response.text
        body = response.json()
        assert body["code"] == "NOT_FOUND"

    async def test_submit_correction_422_nonexistent_segment(
        self,
        async_client: AsyncClient,
        seed_test_data: dict[str, Any],
    ) -> None:
        """POST with a valid video_id but non-existent segment_id must return 422.

        The segment_id 999999 is intentionally unreachable given auto-increment PKs
        starting from 1 in an integration test database.
        """
        video_id = seed_test_data["video_id"]
        language_code = seed_test_data["language_code"]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.post(
                _corrections_url(video_id, 999999),
                params={"language_code": language_code},
                json={
                    "corrected_text": "the quick brown fox",
                    "correction_type": "spelling",
                },
            )

        assert response.status_code == 422, response.text
        body = response.json()
        assert body["code"] == "SEGMENT_NOT_FOUND"

    async def test_submit_correction_422_no_change_detected(
        self,
        async_client: AsyncClient,
        seed_test_data: dict[str, Any],
    ) -> None:
        """Submit a correction identical to the current segment text must return 422.

        The service rejects corrections where the corrected_text matches the
        segment's current effective text (no-op change).
        """
        video_id = seed_test_data["video_id"]
        segment_id = seed_test_data["segment_id"]
        language_code = seed_test_data["language_code"]
        # Same as original_text — no change
        same_text = seed_test_data["original_text"]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.post(
                _corrections_url(video_id, segment_id),
                params={"language_code": language_code},
                json={
                    "corrected_text": same_text,
                    "correction_type": "spelling",
                },
            )

        assert response.status_code == 422, response.text
        body = response.json()
        assert body["code"] == "NO_CHANGE_DETECTED"

    async def test_submit_correction_422_revert_type_rejected(
        self,
        async_client: AsyncClient,
        seed_test_data: dict[str, Any],
    ) -> None:
        """Submit with correction_type='revert' must be rejected by Pydantic validation.

        The field_validator in CorrectionSubmitRequest explicitly rejects the
        REVERT type; callers must use the dedicated /revert endpoint instead.
        """
        video_id = seed_test_data["video_id"]
        segment_id = seed_test_data["segment_id"]
        language_code = seed_test_data["language_code"]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.post(
                _corrections_url(video_id, segment_id),
                params={"language_code": language_code},
                json={
                    "corrected_text": "the quick brown fox",
                    "correction_type": "revert",
                },
            )

        assert response.status_code == 422, response.text

    async def test_submit_correction_422_empty_corrected_text(
        self,
        async_client: AsyncClient,
        seed_test_data: dict[str, Any],
    ) -> None:
        """Submit with corrected_text='' must be rejected by min_length=1 validation."""
        video_id = seed_test_data["video_id"]
        segment_id = seed_test_data["segment_id"]
        language_code = seed_test_data["language_code"]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.post(
                _corrections_url(video_id, segment_id),
                params={"language_code": language_code},
                json={
                    "corrected_text": "",
                    "correction_type": "spelling",
                },
            )

        assert response.status_code == 422, response.text

    async def test_submit_correction_422_whitespace_only_text(
        self,
        async_client: AsyncClient,
        seed_test_data: dict[str, Any],
    ) -> None:
        """Submit with corrected_text='   ' must be rejected.

        CorrectionSubmitRequest uses str_strip_whitespace=True, so '   ' is
        stripped to '' before min_length=1 validation fires.
        """
        video_id = seed_test_data["video_id"]
        segment_id = seed_test_data["segment_id"]
        language_code = seed_test_data["language_code"]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.post(
                _corrections_url(video_id, segment_id),
                params={"language_code": language_code},
                json={
                    "corrected_text": "   ",
                    "correction_type": "spelling",
                },
            )

        assert response.status_code == 422, response.text

    async def test_submit_correction_401_unauthenticated(
        self,
        async_client: AsyncClient,
        seed_test_data: dict[str, Any],
    ) -> None:
        """Submit without authentication must return 401."""
        video_id = seed_test_data["video_id"]
        segment_id = seed_test_data["segment_id"]
        language_code = seed_test_data["language_code"]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = False
            response = await async_client.post(
                _corrections_url(video_id, segment_id),
                params={"language_code": language_code},
                json={
                    "corrected_text": "the quick brown fox",
                    "correction_type": "spelling",
                },
            )

        assert response.status_code == 401, response.text


# ---------------------------------------------------------------------------
# T008 — Revert Correction endpoint tests
# ---------------------------------------------------------------------------


class TestRevertCorrection:
    """Tests for POST /api/v1/videos/{video_id}/transcript/segments/{segment_id}/corrections/revert."""

    async def test_revert_single_correction_success_200(
        self,
        async_client: AsyncClient,
        seed_test_data: dict[str, Any],
    ) -> None:
        """Submit one correction then revert it — segment must return to its original state.

        After revert:
        - correction_type is 'revert'
        - has_correction is False
        - effective_text matches the original segment text
        """
        video_id = seed_test_data["video_id"]
        segment_id = seed_test_data["segment_id"]
        language_code = seed_test_data["language_code"]
        original_text = seed_test_data["original_text"]
        corrected = "the quick brown fox"

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            # Step 1: submit correction
            submit_resp = await async_client.post(
                _corrections_url(video_id, segment_id),
                params={"language_code": language_code},
                json={"corrected_text": corrected, "correction_type": "spelling"},
            )
            assert submit_resp.status_code == 201, submit_resp.text

            # Step 2: revert
            revert_resp = await async_client.post(
                _revert_url(video_id, segment_id),
                params={"language_code": language_code},
            )

        assert revert_resp.status_code == 200, revert_resp.text
        body = revert_resp.json()

        assert "data" in body
        data = body["data"]

        correction = data["correction"]
        assert correction["correction_type"] == "revert"

        segment_state = data["segment_state"]
        assert segment_state["has_correction"] is False
        assert segment_state["effective_text"] == original_text

    async def test_revert_stacked_corrections_restores_prior(
        self,
        async_client: AsyncClient,
        seed_test_data: dict[str, Any],
    ) -> None:
        """Submit correction A, then correction B, then revert B.

        After reverting B, the segment should reflect correction A's text with
        has_correction=True — not the original text.
        """
        video_id = seed_test_data["video_id"]
        segment_id = seed_test_data["segment_id"]
        language_code = seed_test_data["language_code"]
        text_a = "the quick brown fox"
        text_b = "the quick brown fox jumps"

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            # Submit correction A
            resp_a = await async_client.post(
                _corrections_url(video_id, segment_id),
                params={"language_code": language_code},
                json={"corrected_text": text_a, "correction_type": "spelling"},
            )
            assert resp_a.status_code == 201, resp_a.text

            # Submit correction B on top of A
            resp_b = await async_client.post(
                _corrections_url(video_id, segment_id),
                params={"language_code": language_code},
                json={"corrected_text": text_b, "correction_type": "context_correction"},
            )
            assert resp_b.status_code == 201, resp_b.text

            # Revert B
            revert_resp = await async_client.post(
                _revert_url(video_id, segment_id),
                params={"language_code": language_code},
            )

        assert revert_resp.status_code == 200, revert_resp.text
        segment_state = revert_resp.json()["data"]["segment_state"]

        # Segment should now reflect correction A's text
        assert segment_state["has_correction"] is True
        assert segment_state["effective_text"] == text_a

    async def test_revert_404_nonexistent_video(
        self,
        async_client: AsyncClient,
        seed_test_data: dict[str, Any],
    ) -> None:
        """Revert on a non-existent video_id must return 404 with code=NOT_FOUND."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.post(
                _revert_url("NONEXISTENT_VID1", 1),
                params={"language_code": "en"},
            )

        assert response.status_code == 404, response.text
        assert response.json()["code"] == "NOT_FOUND"

    async def test_revert_422_no_active_correction(
        self,
        async_client: AsyncClient,
        seed_test_data: dict[str, Any],
    ) -> None:
        """Revert on a segment with no prior corrections must return 422.

        The service raises a ValueError when there is no correction history to
        revert, which the router maps to NO_ACTIVE_CORRECTION.
        """
        video_id = seed_test_data["video_id"]
        segment_id = seed_test_data["segment_id"]
        language_code = seed_test_data["language_code"]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.post(
                _revert_url(video_id, segment_id),
                params={"language_code": language_code},
            )

        assert response.status_code == 422, response.text
        assert response.json()["code"] == "NO_ACTIVE_CORRECTION"

    async def test_revert_422_nonexistent_segment(
        self,
        async_client: AsyncClient,
        seed_test_data: dict[str, Any],
    ) -> None:
        """Revert on a non-existent segment_id (999999) must return 422.

        The service cannot find a correction for an unknown segment and raises
        a ValueError mapped to SEGMENT_NOT_FOUND or NO_ACTIVE_CORRECTION.
        Both are valid 422 responses from the router.
        """
        video_id = seed_test_data["video_id"]
        language_code = seed_test_data["language_code"]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.post(
                _revert_url(video_id, 999999),
                params={"language_code": language_code},
            )

        assert response.status_code == 422, response.text

    async def test_revert_401_unauthenticated(
        self,
        async_client: AsyncClient,
        seed_test_data: dict[str, Any],
    ) -> None:
        """Revert without authentication must return 401."""
        video_id = seed_test_data["video_id"]
        segment_id = seed_test_data["segment_id"]
        language_code = seed_test_data["language_code"]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = False
            response = await async_client.post(
                _revert_url(video_id, segment_id),
                params={"language_code": language_code},
            )

        assert response.status_code == 401, response.text


# ---------------------------------------------------------------------------
# T010 — Correction History endpoint tests
# ---------------------------------------------------------------------------


class TestCorrectionHistory:
    """Tests for GET /api/v1/videos/{video_id}/transcript/segments/{segment_id}/corrections."""

    async def test_history_with_multiple_corrections(
        self,
        async_client: AsyncClient,
        seed_test_data: dict[str, Any],
    ) -> None:
        """Submit 3 different corrections and verify history returns all 3, newest first.

        The GET endpoint returns records ordered by version_number descending so
        the most recent correction appears at index 0.
        """
        video_id = seed_test_data["video_id"]
        segment_id = seed_test_data["segment_id"]
        language_code = seed_test_data["language_code"]

        corrections_to_submit = [
            ("the quick brown fox", "spelling"),
            ("the quick brown fox runs", "context_correction"),
            ("the quick brown fox runs fast", "formatting"),
        ]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            for corrected_text, correction_type in corrections_to_submit:
                resp = await async_client.post(
                    _corrections_url(video_id, segment_id),
                    params={"language_code": language_code},
                    json={
                        "corrected_text": corrected_text,
                        "correction_type": correction_type,
                    },
                )
                assert resp.status_code == 201, resp.text

            # Fetch history
            history_resp = await async_client.get(
                _corrections_url(video_id, segment_id),
                params={"language_code": language_code},
            )

        assert history_resp.status_code == 200, history_resp.text
        body = history_resp.json()

        assert "data" in body
        records = body["data"]
        assert isinstance(records, list)
        assert len(records) == 3

        # Verify newest-first ordering by version_number
        version_numbers = [r["version_number"] for r in records]
        assert version_numbers == sorted(version_numbers, reverse=True), (
            f"Expected descending version_numbers, got: {version_numbers}"
        )

        # Verify pagination metadata
        pagination = body["pagination"]
        assert pagination["total"] == 3

    async def test_history_pagination_with_limit_offset(
        self,
        async_client: AsyncClient,
        seed_test_data: dict[str, Any],
    ) -> None:
        """Submit 3 corrections and fetch page 2 (limit=1, offset=1).

        Verifies:
        - Exactly 1 record is returned
        - pagination.total remains 3
        - pagination.has_more is True (offset=1 + limit=1 = 2 < 3)
        """
        video_id = seed_test_data["video_id"]
        segment_id = seed_test_data["segment_id"]
        language_code = seed_test_data["language_code"]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            for text in [
                "the quick brown fox",
                "the quick brown fox runs",
                "the quick brown fox runs fast",
            ]:
                resp = await async_client.post(
                    _corrections_url(video_id, segment_id),
                    params={"language_code": language_code},
                    json={"corrected_text": text, "correction_type": "spelling"},
                )
                assert resp.status_code == 201, resp.text

            # Paginated history request
            history_resp = await async_client.get(
                _corrections_url(video_id, segment_id),
                params={"language_code": language_code, "limit": 1, "offset": 1},
            )

        assert history_resp.status_code == 200, history_resp.text
        body = history_resp.json()

        records = body["data"]
        assert len(records) == 1

        pagination = body["pagination"]
        assert pagination["total"] == 3
        assert pagination["limit"] == 1
        assert pagination["offset"] == 1
        assert pagination["has_more"] is True

    async def test_history_404_nonexistent_video(
        self,
        async_client: AsyncClient,
        seed_test_data: dict[str, Any],
    ) -> None:
        """GET history for a non-existent video_id must return 404 with code=NOT_FOUND."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                _corrections_url("NONEXISTENT_VID1", 1),
                params={"language_code": "en"},
            )

        assert response.status_code == 404, response.text
        assert response.json()["code"] == "NOT_FOUND"

    async def test_history_empty_list_for_segment_with_no_corrections(
        self,
        async_client: AsyncClient,
        seed_test_data: dict[str, Any],
    ) -> None:
        """Fetch history for a real segment that has no corrections must return 200 with empty list.

        Per FR-013 spec: the history endpoint never returns 404 for missing
        correction history — it returns an empty result set.
        """
        video_id = seed_test_data["video_id"]
        segment_id = seed_test_data["segment_id"]
        language_code = seed_test_data["language_code"]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                _corrections_url(video_id, segment_id),
                params={"language_code": language_code},
            )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["data"] == []
        assert body["pagination"]["total"] == 0

    async def test_history_empty_list_for_nonexistent_segment(
        self,
        async_client: AsyncClient,
        seed_test_data: dict[str, Any],
    ) -> None:
        """Fetch history with a non-existent segment_id must return 200 with empty list.

        Per FR-013 spec, history returns an empty list rather than 404 when the
        segment_id has no associated corrections (including when it does not exist).
        """
        video_id = seed_test_data["video_id"]
        language_code = seed_test_data["language_code"]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                _corrections_url(video_id, 999999),
                params={"language_code": language_code},
            )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["data"] == []
        assert body["pagination"]["total"] == 0

    async def test_history_401_unauthenticated(
        self,
        async_client: AsyncClient,
        seed_test_data: dict[str, Any],
    ) -> None:
        """GET history without authentication must return 401."""
        video_id = seed_test_data["video_id"]
        segment_id = seed_test_data["segment_id"]
        language_code = seed_test_data["language_code"]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = False
            response = await async_client.get(
                _corrections_url(video_id, segment_id),
                params={"language_code": language_code},
            )

        assert response.status_code == 401, response.text


# ---------------------------------------------------------------------------
# T013 — Segment Enrichment with Correction Metadata (US4)
# ---------------------------------------------------------------------------

_ENR_CHANNEL_ID = "UCtcorr_test_ch001"  # reuse existing channel constant
_ENR_VIDEO_ID = "enr_test_01"  # exactly 11 chars — satisfies Path min/max_length=11
_ENR_LANGUAGE_CODE = "en"


def _segments_url(video_id: str) -> str:
    """Return the transcript segments list URL for a given video."""
    return f"/api/v1/videos/{video_id}/transcript/segments"


@pytest.fixture
async def seed_enrichment_data(
    integration_session_factory: "async_sessionmaker[AsyncSession]",
) -> AsyncGenerator[dict[str, Any], None]:
    """Seed database with a channel, video, transcript, and 2 segments for enrichment tests.

    Uses a video_id of exactly 11 characters to satisfy the Path validation on
    the segments endpoint (``min_length=11, max_length=11``).

    Yields a dict with ``video_id``, ``segment_ids`` (list of 2 ints), and
    ``language_code``.  Cleans up all created rows after each test in
    FK-reverse order to avoid constraint violations.
    """
    async with integration_session_factory() as session:
        # ---- Channel (reuse existing or create) ----
        existing_channel = (
            await session.execute(
                select(ChannelDB).where(ChannelDB.channel_id == _ENR_CHANNEL_ID)
            )
        ).scalar_one_or_none()
        if not existing_channel:
            channel = ChannelDB(
                channel_id=_ENR_CHANNEL_ID,
                title="Transcript Correction Test Channel",
            )
            session.add(channel)

        # ---- Video (11-char ID) ----
        existing_video = (
            await session.execute(
                select(VideoDB).where(VideoDB.video_id == _ENR_VIDEO_ID)
            )
        ).scalar_one_or_none()
        if not existing_video:
            video = VideoDB(
                video_id=_ENR_VIDEO_ID,
                channel_id=_ENR_CHANNEL_ID,
                title="Enrichment Test Video",
                description="Integration test video for T013 segment enrichment",
                upload_date=datetime(2024, 6, 1, tzinfo=timezone.utc),
                duration=120,
            )
            session.add(video)

        # ---- VideoTranscript ----
        existing_transcript = (
            await session.execute(
                select(VideoTranscriptDB).where(
                    VideoTranscriptDB.video_id == _ENR_VIDEO_ID,
                    VideoTranscriptDB.language_code == _ENR_LANGUAGE_CODE,
                )
            )
        ).scalar_one_or_none()
        if not existing_transcript:
            transcript = VideoTranscriptDB(
                video_id=_ENR_VIDEO_ID,
                language_code=_ENR_LANGUAGE_CODE,
                transcript_text="hello world foo bar",
                transcript_type="MANUAL",
                download_reason="USER_REQUEST",
                is_cc=False,
                is_auto_synced=False,
                track_kind="standard",
            )
            session.add(transcript)

        await session.commit()

        # ---- Two TranscriptSegments (created fresh per test invocation) ----
        seg1 = TranscriptSegmentDB(
            video_id=_ENR_VIDEO_ID,
            language_code=_ENR_LANGUAGE_CODE,
            text="hello world",
            start_time=0.0,
            duration=3.0,
            end_time=3.0,
            sequence_number=0,
            has_correction=False,
        )
        seg2 = TranscriptSegmentDB(
            video_id=_ENR_VIDEO_ID,
            language_code=_ENR_LANGUAGE_CODE,
            text="foo bar",
            start_time=3.0,
            duration=2.0,
            end_time=5.0,
            sequence_number=1,
            has_correction=False,
        )
        session.add(seg1)
        session.add(seg2)
        await session.commit()

        # Retrieve auto-generated segment PKs
        result1 = await session.execute(
            select(TranscriptSegmentDB).where(TranscriptSegmentDB.id == seg1.id)
        )
        seeded_seg1 = result1.scalar_one()

        result2 = await session.execute(
            select(TranscriptSegmentDB).where(TranscriptSegmentDB.id == seg2.id)
        )
        seeded_seg2 = result2.scalar_one()

        yield {
            "video_id": _ENR_VIDEO_ID,
            "segment_ids": [seeded_seg1.id, seeded_seg2.id],
            "language_code": _ENR_LANGUAGE_CODE,
        }

        # ---- Cleanup (FK reverse order) ----
        await session.execute(
            delete(TranscriptCorrectionDB).where(
                TranscriptCorrectionDB.video_id == _ENR_VIDEO_ID
            )
        )
        await session.execute(
            delete(TranscriptSegmentDB).where(
                TranscriptSegmentDB.video_id == _ENR_VIDEO_ID
            )
        )
        await session.execute(
            delete(VideoTranscriptDB).where(
                VideoTranscriptDB.video_id == _ENR_VIDEO_ID
            )
        )
        await session.execute(
            delete(VideoDB).where(VideoDB.video_id == _ENR_VIDEO_ID)
        )
        # The channel row is intentionally left in place — it is shared with
        # the seed_test_data fixture scope and will be cleaned up by that
        # fixture's own teardown if both fixtures run in the same session.
        await session.commit()


class TestSegmentEnrichment:
    """Tests for T013 — segment enrichment with correction metadata.

    Verifies that the GET /api/v1/videos/{video_id}/transcript/segments
    endpoint returns the three correction-metadata fields added in Feature 034:

    - ``has_correction`` (bool, default False)
    - ``corrected_at`` (datetime | null, default null)
    - ``correction_count`` (int, default 0)
    """

    async def test_segment_with_correction_shows_enrichment(
        self,
        async_client: AsyncClient,
        seed_enrichment_data: dict[str, Any],
    ) -> None:
        """Submit a correction to one segment and verify enriched fields in segments list.

        After a correction is applied via POST corrections, a subsequent GET
        of the segments list must reflect that correction on the affected
        segment:
        - ``has_correction`` is True
        - ``corrected_at`` is a non-null ISO timestamp string
        - ``correction_count`` is at least 1
        The uncorrected segment must retain default values.
        """
        video_id = seed_enrichment_data["video_id"]
        segment_ids = seed_enrichment_data["segment_ids"]
        language_code = seed_enrichment_data["language_code"]
        target_segment_id = segment_ids[0]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            # Apply correction to the first segment only
            submit_resp = await async_client.post(
                _corrections_url(video_id, target_segment_id),
                params={"language_code": language_code},
                json={
                    "corrected_text": "hello world corrected",
                    "correction_type": "spelling",
                },
            )
            assert submit_resp.status_code == 201, submit_resp.text

            # Fetch segments list
            segments_resp = await async_client.get(
                _segments_url(video_id),
                params={"language": language_code},
            )

        assert segments_resp.status_code == 200, segments_resp.text
        body = segments_resp.json()
        assert "data" in body

        segments = body["data"]
        assert len(segments) >= 1

        # Locate the corrected segment in the response
        corrected_items = [s for s in segments if s["id"] == target_segment_id]
        assert len(corrected_items) == 1, (
            f"Expected segment id={target_segment_id} in response, got ids: "
            f"{[s['id'] for s in segments]}"
        )
        corrected_seg = corrected_items[0]

        assert corrected_seg["has_correction"] is True, (
            "Corrected segment must have has_correction=True"
        )
        assert corrected_seg["corrected_at"] is not None, (
            "Corrected segment must have a non-null corrected_at timestamp"
        )
        assert corrected_seg["correction_count"] >= 1, (
            "Corrected segment must have correction_count >= 1"
        )

    async def test_segment_without_correction_shows_defaults(
        self,
        async_client: AsyncClient,
        seed_enrichment_data: dict[str, Any],
    ) -> None:
        """Fetch segments without applying any corrections and verify default enrichment values.

        All segments must return the three correction-metadata fields with
        their zero/null defaults when no corrections have been submitted:
        - ``has_correction`` is False
        - ``corrected_at`` is null
        - ``correction_count`` is 0
        """
        video_id = seed_enrichment_data["video_id"]
        language_code = seed_enrichment_data["language_code"]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            segments_resp = await async_client.get(
                _segments_url(video_id),
                params={"language": language_code},
            )

        assert segments_resp.status_code == 200, segments_resp.text
        body = segments_resp.json()
        segments = body["data"]
        assert len(segments) >= 2, (
            f"Expected at least 2 seeded segments, got {len(segments)}"
        )

        for seg in segments:
            assert seg["has_correction"] is False, (
                f"Segment id={seg['id']} has_correction must be False before any correction"
            )
            assert seg["corrected_at"] is None, (
                f"Segment id={seg['id']} corrected_at must be null before any correction"
            )
            assert seg["correction_count"] == 0, (
                f"Segment id={seg['id']} correction_count must be 0 before any correction"
            )

    async def test_correction_count_includes_revert_records(
        self,
        async_client: AsyncClient,
        seed_enrichment_data: dict[str, Any],
    ) -> None:
        """Submit a correction then revert it; verify correction_count counts both audit records.

        Both the original submission and the revert operation are stored as
        separate audit records in transcript_corrections.  Therefore after one
        submit + one revert the ``correction_count`` must be >= 2.

        After a revert to the original text ``has_correction`` must reflect the
        final segment state (False, because the segment was restored to its
        pre-correction text).
        """
        video_id = seed_enrichment_data["video_id"]
        segment_ids = seed_enrichment_data["segment_ids"]
        language_code = seed_enrichment_data["language_code"]
        target_segment_id = segment_ids[0]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            # Step 1: submit a correction
            submit_resp = await async_client.post(
                _corrections_url(video_id, target_segment_id),
                params={"language_code": language_code},
                json={
                    "corrected_text": "hello world revised",
                    "correction_type": "spelling",
                },
            )
            assert submit_resp.status_code == 201, submit_resp.text

            # Step 2: revert the correction back to original
            revert_resp = await async_client.post(
                _revert_url(video_id, target_segment_id),
                params={"language_code": language_code},
            )
            assert revert_resp.status_code == 200, revert_resp.text

            # Step 3: fetch segments list
            segments_resp = await async_client.get(
                _segments_url(video_id),
                params={"language": language_code},
            )

        assert segments_resp.status_code == 200, segments_resp.text
        segments = segments_resp.json()["data"]

        target_items = [s for s in segments if s["id"] == target_segment_id]
        assert len(target_items) == 1, (
            f"Expected segment id={target_segment_id} in response, got ids: "
            f"{[s['id'] for s in segments]}"
        )
        target_seg = target_items[0]

        assert target_seg["correction_count"] >= 2, (
            f"Expected correction_count >= 2 (submit + revert), "
            f"got {target_seg['correction_count']}"
        )
        assert target_seg["has_correction"] is False, (
            "After revert-to-original, has_correction must be False"
        )
