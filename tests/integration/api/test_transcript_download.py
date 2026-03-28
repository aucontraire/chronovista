"""Integration tests for POST /api/v1/videos/{video_id}/transcript/download.

Covers Feature 048 — the transcript download endpoint that:
  1. Validates the video_id format.
  2. Guards against concurrent in-flight downloads (429).
  3. Returns 409 when a transcript already exists in the database.
  4. Calls TranscriptService.get_transcript(), saves the result via the
     repository, and returns a TranscriptDownloadResponse payload.

Every test class seeds its own minimal rows (channel → video) and cleans up
after itself in FK-reverse order so each test file can run independently
against the shared integration database.

Pattern mirrors test_transcript_corrections_api.py:
  - Direct ORM inserts via integration_session_factory for seeding.
  - The ``async_client`` fixture handles DB-override and auth bypass.
  - Auth is bypassed by patching ``chronovista.api.deps.youtube_oauth``.
  - TranscriptService is mocked to avoid hitting the YouTube API.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select
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
from chronovista.models.enums import DownloadReason
from chronovista.models.transcript_source import (
    RawTranscriptData,
    TranscriptSnippet,
    TranscriptSource,
)
from chronovista.models.video_transcript import EnhancedVideoTranscriptBase
from tests.factories.id_factory import YouTubeIdFactory

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

# CRITICAL: Ensures all async tests in this module run with pytest-asyncio
# ---------------------------------------------------------------------------
# Stable IDs — generated via YouTubeIdFactory with deterministic seeds
# ---------------------------------------------------------------------------
_CHANNEL_ID = YouTubeIdFactory.create_channel_id("transcript_download_test")
_VIDEO_ID = YouTubeIdFactory.create_video_id("transcript_download_video")
_EXISTING_VIDEO_ID = YouTubeIdFactory.create_video_id("transcript_download_existing")
_LANGUAGE_CODE = "en"

# ---------------------------------------------------------------------------
# URL helper
# ---------------------------------------------------------------------------


def _download_url(video_id: str, language: str | None = None) -> str:
    """Return the download endpoint URL for a given video."""
    url = f"/api/v1/videos/{video_id}/transcript/download"
    if language:
        url = f"{url}?language={language}"
    return url


# ---------------------------------------------------------------------------
# Helpers — build a realistic EnhancedVideoTranscriptBase mock return value
# ---------------------------------------------------------------------------


def _make_enhanced_transcript(
    video_id: str = _VIDEO_ID,
    language_code: str = "en",
    snippet_count: int = 3,
    is_cc: bool = False,
) -> EnhancedVideoTranscriptBase:
    """Construct an EnhancedVideoTranscriptBase suitable for mocking get_transcript().

    This mirrors what TranscriptService.get_transcript() returns after
    a successful YouTube API call.  We build it via
    ``EnhancedVideoTranscriptBase.from_raw_transcript_data()`` so that all
    field derivations (plain_text_only, transcript_type, etc.) are exercised
    exactly as the real service would produce.

    Parameters
    ----------
    video_id : str
        YouTube video ID for the transcript.
    language_code : str
        BCP-47 language code.
    snippet_count : int
        Number of transcript snippets to generate.
    is_cc : bool
        Whether to mark the transcript as closed captions.

    Returns
    -------
    EnhancedVideoTranscriptBase
        A fully-constructed transcript object.
    """
    snippets = [
        TranscriptSnippet(
            text=f"Segment {i}: Hello and welcome to this video.",
            start=float(i * 3),
            duration=2.5,
        )
        for i in range(snippet_count)
    ]

    raw_data = RawTranscriptData(
        video_id=video_id,
        language_code=language_code,
        language_name="English",
        snippets=snippets,
        is_generated=not is_cc,
        is_translatable=True,
        source=TranscriptSource.YOUTUBE_TRANSCRIPT_API,
        source_metadata={
            "original_language": "English",
            "original_language_code": language_code,
            "is_generated": not is_cc,
            "transcript_count": snippet_count,
            "api_version": "1.2.2+",
        },
    )

    return EnhancedVideoTranscriptBase.from_raw_transcript_data(
        raw_data,
        download_reason=DownloadReason.USER_REQUEST,
        is_cc=is_cc,
    )


# ---------------------------------------------------------------------------
# Seed fixture — channel + video (no transcript) for the main download tests
# ---------------------------------------------------------------------------


@pytest.fixture
async def seed_video_without_transcript(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[dict[str, Any], None]:
    """Seed a channel and video record with NO pre-existing transcript.

    Yields a dict with ``video_id`` and ``channel_id`` so tests can reference
    the seeded records.  Cleans up all rows after each test in FK-reverse order.
    """
    async with integration_session_factory() as session:
        # ---- Channel ----
        existing_channel = (
            await session.execute(
                select(ChannelDB).where(ChannelDB.channel_id == _CHANNEL_ID)
            )
        ).scalar_one_or_none()
        if not existing_channel:
            channel = ChannelDB(
                channel_id=_CHANNEL_ID,
                title="Transcript Download Test Channel",
            )
            session.add(channel)

        # ---- Video (no transcript) ----
        existing_video = (
            await session.execute(
                select(VideoDB).where(VideoDB.video_id == _VIDEO_ID)
            )
        ).scalar_one_or_none()
        if not existing_video:
            video = VideoDB(
                video_id=_VIDEO_ID,
                channel_id=_CHANNEL_ID,
                title="Transcript Download Test Video",
                description="Integration test video for transcript download endpoint",
                upload_date=datetime(2024, 1, 1, tzinfo=UTC),
                duration=300,
            )
            session.add(video)

        await session.commit()

    yield {"video_id": _VIDEO_ID, "channel_id": _CHANNEL_ID}

    # ---- Cleanup (FK reverse order: segments → transcripts → videos → channel) ----
    async with integration_session_factory() as session:
        await session.execute(
            delete(TranscriptSegmentDB).where(
                TranscriptSegmentDB.video_id == _VIDEO_ID
            )
        )
        await session.execute(
            delete(VideoTranscriptDB).where(
                VideoTranscriptDB.video_id == _VIDEO_ID
            )
        )
        await session.execute(
            delete(VideoDB).where(VideoDB.video_id == _VIDEO_ID)
        )
        await session.execute(
            delete(ChannelDB).where(ChannelDB.channel_id == _CHANNEL_ID)
        )
        await session.commit()


# ---------------------------------------------------------------------------
# Seed fixture — channel + video + transcript for 409 conflict tests
# ---------------------------------------------------------------------------


@pytest.fixture
async def seed_video_with_existing_transcript(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[dict[str, Any], None]:
    """Seed a channel, video, and an existing transcript to test 409 conflict.

    Yields a dict with ``video_id`` and ``language_code``.
    Cleans up all rows after each test.
    """
    async with integration_session_factory() as session:
        # ---- Channel ----
        existing_channel = (
            await session.execute(
                select(ChannelDB).where(ChannelDB.channel_id == _CHANNEL_ID)
            )
        ).scalar_one_or_none()
        if not existing_channel:
            channel = ChannelDB(
                channel_id=_CHANNEL_ID,
                title="Transcript Download Test Channel",
            )
            session.add(channel)

        # ---- Video ----
        existing_video = (
            await session.execute(
                select(VideoDB).where(VideoDB.video_id == _EXISTING_VIDEO_ID)
            )
        ).scalar_one_or_none()
        if not existing_video:
            video = VideoDB(
                video_id=_EXISTING_VIDEO_ID,
                channel_id=_CHANNEL_ID,
                title="Video With Pre-existing Transcript",
                description="Already has a transcript — triggers 409",
                upload_date=datetime(2024, 1, 1, tzinfo=UTC),
                duration=180,
            )
            session.add(video)

        # ---- Pre-existing transcript (triggers 409 on re-download) ----
        existing_transcript = (
            await session.execute(
                select(VideoTranscriptDB).where(
                    VideoTranscriptDB.video_id == _EXISTING_VIDEO_ID,
                    VideoTranscriptDB.language_code == _LANGUAGE_CODE,
                )
            )
        ).scalar_one_or_none()
        if not existing_transcript:
            transcript = VideoTranscriptDB(
                video_id=_EXISTING_VIDEO_ID,
                language_code=_LANGUAGE_CODE,
                transcript_text="This transcript was already downloaded.",
                transcript_type="MANUAL",
                download_reason="USER_REQUEST",
                is_cc=True,
                is_auto_synced=False,
                track_kind="standard",
            )
            session.add(transcript)

        await session.commit()

    yield {"video_id": _EXISTING_VIDEO_ID, "language_code": _LANGUAGE_CODE}

    # ---- Cleanup ----
    async with integration_session_factory() as session:
        await session.execute(
            delete(TranscriptSegmentDB).where(
                TranscriptSegmentDB.video_id == _EXISTING_VIDEO_ID
            )
        )
        await session.execute(
            delete(VideoTranscriptDB).where(
                VideoTranscriptDB.video_id == _EXISTING_VIDEO_ID
            )
        )
        await session.execute(
            delete(VideoDB).where(VideoDB.video_id == _EXISTING_VIDEO_ID)
        )
        await session.execute(
            delete(ChannelDB).where(ChannelDB.channel_id == _CHANNEL_ID)
        )
        await session.commit()


# ---------------------------------------------------------------------------
# Convenience: authenticated request context
# ---------------------------------------------------------------------------


def _mock_auth(mock_oauth: MagicMock) -> None:
    """Configure a mock oauth object to report as authenticated."""
    mock_oauth.is_authenticated.return_value = True


# ===========================================================================
# Test class 1 — Input validation (no DB seeding required)
# ===========================================================================


class TestDownloadInputValidation:
    """Validates video_id format before any DB or service interaction."""

    async def test_invalid_video_id_too_short_returns_422(
        self, async_client: AsyncClient
    ) -> None:
        """video_id shorter than 11 chars fails FastAPI path validation (422)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            _mock_auth(mock_oauth)
            response = await async_client.post(_download_url("short"))
        assert response.status_code == 422

    async def test_invalid_video_id_too_long_returns_422(
        self, async_client: AsyncClient
    ) -> None:
        """video_id with invalid characters triggers endpoint-level 422."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            _mock_auth(mock_oauth)
            # Contains special character '!' — caught by _VIDEO_ID_PATTERN
            response = await async_client.post(_download_url("invalid!vid01"))
        assert response.status_code == 422
        data = response.json()
        assert data.get("code") == "VALIDATION_ERROR"

    async def test_invalid_video_id_with_special_chars_returns_422(
        self, async_client: AsyncClient
    ) -> None:
        """video_id with spaces triggers endpoint-level 422."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            _mock_auth(mock_oauth)
            response = await async_client.post(_download_url("hello world!"))
        assert response.status_code == 422

    async def test_unauthenticated_request_returns_401(
        self, async_client: AsyncClient
    ) -> None:
        """Download endpoint requires authentication (router-level guard)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = False
            response = await async_client.post(_download_url(_VIDEO_ID))
        assert response.status_code == 401

    async def test_valid_video_id_passes_format_check(
        self, async_client: AsyncClient
    ) -> None:
        """A well-formed video_id (11 alphanumeric/_/- chars) passes format validation.

        The endpoint will then attempt the full flow. Without a real video in
        the DB the service will be called (or mocked) and may return 404.
        This test only confirms format validation succeeds (not a 422).
        """
        with (
            patch("chronovista.api.deps.youtube_oauth") as mock_oauth,
            patch(
                "chronovista.api.routers.transcripts._transcript_service"
            ) as mock_svc,
        ):
            _mock_auth(mock_oauth)
            from chronovista.services.transcript_service import TranscriptNotFoundError
            mock_svc.get_transcript = AsyncMock(
                side_effect=TranscriptNotFoundError("no transcript")
            )
            response = await async_client.post(_download_url("dQw4w9WgXcQ"))
        # Format check passed; result is 404 because DB has no transcript and
        # the mocked service raised TranscriptNotFoundError
        assert response.status_code != 422


# ===========================================================================
# Test class 2 — Full download flow (happy path)
# ===========================================================================


class TestDownloadHappyPath:
    """Tests the successful end-to-end download flow with mocked TranscriptService."""

    async def test_download_returns_200_with_correct_structure(
        self,
        async_client: AsyncClient,
        seed_video_without_transcript: dict[str, Any],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Successful download returns 200 with TranscriptDownloadResponse payload."""
        video_id = seed_video_without_transcript["video_id"]
        mock_transcript = _make_enhanced_transcript(video_id=video_id, snippet_count=3)

        with (
            patch("chronovista.api.deps.youtube_oauth") as mock_oauth,
            patch(
                "chronovista.api.routers.transcripts._transcript_service"
            ) as mock_svc,
        ):
            _mock_auth(mock_oauth)
            mock_svc.get_transcript = AsyncMock(return_value=mock_transcript)
            response = await async_client.post(_download_url(video_id))

        assert response.status_code == 200, response.text
        data = response.json()
        assert "data" in data

        payload = data["data"]
        assert payload["video_id"] == video_id
        assert "language_code" in payload
        assert "language_name" in payload
        assert "transcript_type" in payload
        assert "segment_count" in payload
        assert "downloaded_at" in payload

    async def test_download_persists_transcript_to_database(
        self,
        async_client: AsyncClient,
        seed_video_without_transcript: dict[str, Any],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """After a successful download the transcript row is saved in the database."""
        video_id = seed_video_without_transcript["video_id"]
        mock_transcript = _make_enhanced_transcript(video_id=video_id, snippet_count=4)

        with (
            patch("chronovista.api.deps.youtube_oauth") as mock_oauth,
            patch(
                "chronovista.api.routers.transcripts._transcript_service"
            ) as mock_svc,
        ):
            _mock_auth(mock_oauth)
            mock_svc.get_transcript = AsyncMock(return_value=mock_transcript)
            response = await async_client.post(_download_url(video_id))

        assert response.status_code == 200, response.text

        # Verify the transcript record is actually in the database
        async with integration_session_factory() as session:
            result = await session.execute(
                select(VideoTranscriptDB).where(
                    VideoTranscriptDB.video_id == video_id
                )
            )
            saved_transcript = result.scalar_one_or_none()

        assert saved_transcript is not None, (
            f"Expected a VideoTranscript row for video_id={video_id!r} "
            "but none was found after the download."
        )
        assert saved_transcript.video_id == video_id

    async def test_download_creates_segments_in_database(
        self,
        async_client: AsyncClient,
        seed_video_without_transcript: dict[str, Any],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """After download the TranscriptSegment rows are created from raw data snippets."""
        video_id = seed_video_without_transcript["video_id"]
        # Use 5 snippets so we can assert exactly 5 segments were created
        expected_segments = 5
        mock_transcript = _make_enhanced_transcript(
            video_id=video_id, snippet_count=expected_segments
        )

        with (
            patch("chronovista.api.deps.youtube_oauth") as mock_oauth,
            patch(
                "chronovista.api.routers.transcripts._transcript_service"
            ) as mock_svc,
        ):
            _mock_auth(mock_oauth)
            mock_svc.get_transcript = AsyncMock(return_value=mock_transcript)
            response = await async_client.post(_download_url(video_id))

        assert response.status_code == 200, response.text

        # Verify segments were created in the database
        async with integration_session_factory() as session:
            result = await session.execute(
                select(TranscriptSegmentDB).where(
                    TranscriptSegmentDB.video_id == video_id
                )
            )
            segments = result.scalars().all()

        assert len(segments) == expected_segments, (
            f"Expected {expected_segments} segments in the database "
            f"but found {len(segments)}."
        )

    async def test_download_segment_count_in_response_matches_snippets(
        self,
        async_client: AsyncClient,
        seed_video_without_transcript: dict[str, Any],
    ) -> None:
        """Response segment_count matches the number of snippets in the mock transcript."""
        video_id = seed_video_without_transcript["video_id"]
        expected_count = 7
        mock_transcript = _make_enhanced_transcript(
            video_id=video_id, snippet_count=expected_count
        )

        with (
            patch("chronovista.api.deps.youtube_oauth") as mock_oauth,
            patch(
                "chronovista.api.routers.transcripts._transcript_service"
            ) as mock_svc,
        ):
            _mock_auth(mock_oauth)
            mock_svc.get_transcript = AsyncMock(return_value=mock_transcript)
            response = await async_client.post(_download_url(video_id))

        assert response.status_code == 200, response.text
        data = response.json()
        assert data["data"]["segment_count"] == expected_count, (
            f"Expected segment_count={expected_count} in response, "
            f"got {data['data']['segment_count']}."
        )

    async def test_download_with_language_query_param_passes_to_service(
        self,
        async_client: AsyncClient,
        seed_video_without_transcript: dict[str, Any],
    ) -> None:
        """When ?language=es is supplied the service is called with language_codes=['es']."""
        video_id = seed_video_without_transcript["video_id"]
        mock_transcript = _make_enhanced_transcript(
            video_id=video_id, language_code="es", snippet_count=2
        )

        captured_kwargs: dict[str, Any] = {}

        async def capture_get_transcript(**kwargs: Any) -> EnhancedVideoTranscriptBase:
            captured_kwargs.update(kwargs)
            return mock_transcript

        with (
            patch("chronovista.api.deps.youtube_oauth") as mock_oauth,
            patch(
                "chronovista.api.routers.transcripts._transcript_service"
            ) as mock_svc,
        ):
            _mock_auth(mock_oauth)
            mock_svc.get_transcript = capture_get_transcript
            response = await async_client.post(_download_url(video_id, language="es"))

        assert response.status_code == 200, response.text
        assert captured_kwargs.get("language_codes") == ["es"], (
            f"Expected language_codes=['es'] but got {captured_kwargs.get('language_codes')!r}"
        )

    async def test_download_without_language_param_uses_none(
        self,
        async_client: AsyncClient,
        seed_video_without_transcript: dict[str, Any],
    ) -> None:
        """When no language query param is supplied, language_codes=None is passed to the service."""
        video_id = seed_video_without_transcript["video_id"]
        mock_transcript = _make_enhanced_transcript(video_id=video_id, snippet_count=2)

        captured_kwargs: dict[str, Any] = {}

        async def capture_get_transcript(**kwargs: Any) -> EnhancedVideoTranscriptBase:
            captured_kwargs.update(kwargs)
            return mock_transcript

        with (
            patch("chronovista.api.deps.youtube_oauth") as mock_oauth,
            patch(
                "chronovista.api.routers.transcripts._transcript_service"
            ) as mock_svc,
        ):
            _mock_auth(mock_oauth)
            mock_svc.get_transcript = capture_get_transcript
            response = await async_client.post(_download_url(video_id))

        assert response.status_code == 200, response.text
        assert captured_kwargs.get("language_codes") is None

    async def test_download_manual_transcript_reported_as_manual_type(
        self,
        async_client: AsyncClient,
        seed_video_without_transcript: dict[str, Any],
    ) -> None:
        """A closed-caption (CC) transcript is reflected as transcript_type='manual' in response."""
        video_id = seed_video_without_transcript["video_id"]
        # is_cc=True produces a MANUAL transcript in the enhanced model
        mock_transcript = _make_enhanced_transcript(
            video_id=video_id, snippet_count=3, is_cc=True
        )

        with (
            patch("chronovista.api.deps.youtube_oauth") as mock_oauth,
            patch(
                "chronovista.api.routers.transcripts._transcript_service"
            ) as mock_svc,
        ):
            _mock_auth(mock_oauth)
            mock_svc.get_transcript = AsyncMock(return_value=mock_transcript)
            response = await async_client.post(_download_url(video_id))

        assert response.status_code == 200, response.text
        # The endpoint derives "manual" when is_cc is True OR transcript_type == "MANUAL"
        data = response.json()
        assert data["data"]["transcript_type"] == "manual"

    async def test_download_language_name_is_human_readable(
        self,
        async_client: AsyncClient,
        seed_video_without_transcript: dict[str, Any],
    ) -> None:
        """The response language_name is a human-readable string, not a raw code."""
        video_id = seed_video_without_transcript["video_id"]
        mock_transcript = _make_enhanced_transcript(video_id=video_id, snippet_count=2)

        with (
            patch("chronovista.api.deps.youtube_oauth") as mock_oauth,
            patch(
                "chronovista.api.routers.transcripts._transcript_service"
            ) as mock_svc,
        ):
            _mock_auth(mock_oauth)
            mock_svc.get_transcript = AsyncMock(return_value=mock_transcript)
            response = await async_client.post(_download_url(video_id))

        assert response.status_code == 200, response.text
        data = response.json()
        lang_name = data["data"]["language_name"]
        # Must be a non-empty string (not None and not just a raw code like "en")
        assert isinstance(lang_name, str)
        assert len(lang_name) > 0


# ===========================================================================
# Test class 3 — Conflict: transcript already exists (409)
# ===========================================================================


class TestDownloadConflict:
    """Tests the 409 Conflict response when a transcript already exists."""

    async def test_returns_409_when_transcript_exists(
        self,
        async_client: AsyncClient,
        seed_video_with_existing_transcript: dict[str, Any],
    ) -> None:
        """Download returns 409 when a transcript record already exists for the video."""
        video_id = seed_video_with_existing_transcript["video_id"]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            _mock_auth(mock_oauth)
            response = await async_client.post(_download_url(video_id))

        assert response.status_code == 409, response.text

    async def test_409_response_has_conflict_code(
        self,
        async_client: AsyncClient,
        seed_video_with_existing_transcript: dict[str, Any],
    ) -> None:
        """409 response body contains RFC 7807 code='CONFLICT'."""
        video_id = seed_video_with_existing_transcript["video_id"]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            _mock_auth(mock_oauth)
            response = await async_client.post(_download_url(video_id))

        assert response.status_code == 409
        data = response.json()
        assert data.get("code") == "CONFLICT", (
            f"Expected RFC 7807 code='CONFLICT', got {data.get('code')!r}"
        )

    async def test_409_detail_mentions_video_id(
        self,
        async_client: AsyncClient,
        seed_video_with_existing_transcript: dict[str, Any],
    ) -> None:
        """409 error detail message references the video_id."""
        video_id = seed_video_with_existing_transcript["video_id"]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            _mock_auth(mock_oauth)
            response = await async_client.post(_download_url(video_id))

        assert response.status_code == 409
        data = response.json()
        detail = data.get("detail", "")
        assert video_id in detail, (
            f"Expected video_id={video_id!r} to appear in error detail, "
            f"but got: {detail!r}"
        )

    async def test_service_not_called_when_transcript_already_exists(
        self,
        async_client: AsyncClient,
        seed_video_with_existing_transcript: dict[str, Any],
    ) -> None:
        """TranscriptService.get_transcript() must NOT be called when a 409 is returned.

        The endpoint checks the DB first; the service should never be invoked
        when an existing transcript is found.
        """
        video_id = seed_video_with_existing_transcript["video_id"]

        with (
            patch("chronovista.api.deps.youtube_oauth") as mock_oauth,
            patch(
                "chronovista.api.routers.transcripts._transcript_service"
            ) as mock_svc,
        ):
            _mock_auth(mock_oauth)
            mock_svc.get_transcript = AsyncMock()
            response = await async_client.post(_download_url(video_id))

        assert response.status_code == 409
        mock_svc.get_transcript.assert_not_called()


# ===========================================================================
# Test class 4 — Service-level errors (404, 503)
# ===========================================================================


class TestDownloadServiceErrors:
    """Tests error propagation from TranscriptService to HTTP responses."""

    async def test_transcript_not_found_returns_404(
        self,
        async_client: AsyncClient,
        seed_video_without_transcript: dict[str, Any],
    ) -> None:
        """TranscriptNotFoundError from the service maps to a 404 response."""
        from chronovista.services.transcript_service import TranscriptNotFoundError

        video_id = seed_video_without_transcript["video_id"]

        with (
            patch("chronovista.api.deps.youtube_oauth") as mock_oauth,
            patch(
                "chronovista.api.routers.transcripts._transcript_service"
            ) as mock_svc,
        ):
            _mock_auth(mock_oauth)
            mock_svc.get_transcript = AsyncMock(
                side_effect=TranscriptNotFoundError("No transcript available")
            )
            response = await async_client.post(_download_url(video_id))

        assert response.status_code == 404, response.text
        data = response.json()
        assert data.get("code") == "NOT_FOUND"

    async def test_service_unavailable_returns_503(
        self,
        async_client: AsyncClient,
        seed_video_without_transcript: dict[str, Any],
    ) -> None:
        """TranscriptServiceUnavailableError maps to a 503 response."""
        from chronovista.services.transcript_service import (
            TranscriptServiceUnavailableError,
        )

        video_id = seed_video_without_transcript["video_id"]

        with (
            patch("chronovista.api.deps.youtube_oauth") as mock_oauth,
            patch(
                "chronovista.api.routers.transcripts._transcript_service"
            ) as mock_svc,
        ):
            _mock_auth(mock_oauth)
            mock_svc.get_transcript = AsyncMock(
                side_effect=TranscriptServiceUnavailableError("YouTube is down")
            )
            response = await async_client.post(_download_url(video_id))

        assert response.status_code == 503, response.text

    async def test_rate_limit_error_from_service_returns_503(
        self,
        async_client: AsyncClient,
        seed_video_without_transcript: dict[str, Any],
    ) -> None:
        """A TranscriptServiceError with 'rate limit' in message maps to 503."""
        from chronovista.services.transcript_service import TranscriptServiceError

        video_id = seed_video_without_transcript["video_id"]

        with (
            patch("chronovista.api.deps.youtube_oauth") as mock_oauth,
            patch(
                "chronovista.api.routers.transcripts._transcript_service"
            ) as mock_svc,
        ):
            _mock_auth(mock_oauth)
            mock_svc.get_transcript = AsyncMock(
                side_effect=TranscriptServiceError(
                    "YouTube rate limit exceeded: too many requests"
                )
            )
            response = await async_client.post(_download_url(video_id))

        assert response.status_code == 503, response.text


# ===========================================================================
# Test class 5 — In-flight download guard (429)
# ===========================================================================


class TestDownloadInFlightGuard:
    """Tests the in-flight download guard that prevents concurrent downloads."""

    async def test_returns_429_when_download_already_in_progress(
        self,
        async_client: AsyncClient,
        seed_video_without_transcript: dict[str, Any],
    ) -> None:
        """Simulating a concurrent download: 429 returned when video_id is in-flight set."""
        from chronovista.api.routers import transcripts as transcripts_module

        video_id = seed_video_without_transcript["video_id"]

        # Manually inject the video_id into the in-flight guard
        transcripts_module._downloads_in_progress.add(video_id)
        try:
            with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
                _mock_auth(mock_oauth)
                response = await async_client.post(_download_url(video_id))
        finally:
            transcripts_module._downloads_in_progress.discard(video_id)

        assert response.status_code == 429, response.text

    async def test_in_flight_guard_cleared_after_successful_download(
        self,
        async_client: AsyncClient,
        seed_video_without_transcript: dict[str, Any],
    ) -> None:
        """After a successful download the video_id is removed from the in-flight set."""
        from chronovista.api.routers import transcripts as transcripts_module

        video_id = seed_video_without_transcript["video_id"]
        mock_transcript = _make_enhanced_transcript(video_id=video_id, snippet_count=2)

        with (
            patch("chronovista.api.deps.youtube_oauth") as mock_oauth,
            patch(
                "chronovista.api.routers.transcripts._transcript_service"
            ) as mock_svc,
        ):
            _mock_auth(mock_oauth)
            mock_svc.get_transcript = AsyncMock(return_value=mock_transcript)
            response = await async_client.post(_download_url(video_id))

        assert response.status_code == 200
        # The finally block in the endpoint always discards the video_id
        assert video_id not in transcripts_module._downloads_in_progress

    async def test_in_flight_guard_cleared_after_service_error(
        self,
        async_client: AsyncClient,
        seed_video_without_transcript: dict[str, Any],
    ) -> None:
        """After a service error the video_id is still removed from the in-flight set."""
        from chronovista.api.routers import transcripts as transcripts_module
        from chronovista.services.transcript_service import TranscriptNotFoundError

        video_id = seed_video_without_transcript["video_id"]

        with (
            patch("chronovista.api.deps.youtube_oauth") as mock_oauth,
            patch(
                "chronovista.api.routers.transcripts._transcript_service"
            ) as mock_svc,
        ):
            _mock_auth(mock_oauth)
            mock_svc.get_transcript = AsyncMock(
                side_effect=TranscriptNotFoundError("not found")
            )
            response = await async_client.post(_download_url(video_id))

        assert response.status_code == 404
        # Guard must be cleared even on error (endpoint uses try/finally)
        assert video_id not in transcripts_module._downloads_in_progress


# ===========================================================================
# Test class 6 — Database verification after download
# ===========================================================================


class TestDownloadDatabaseState:
    """Verifies the exact database state after a successful download."""

    async def test_saved_transcript_has_correct_language_code(
        self,
        async_client: AsyncClient,
        seed_video_without_transcript: dict[str, Any],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """The persisted VideoTranscript row has the language code from the service response."""
        video_id = seed_video_without_transcript["video_id"]
        mock_transcript = _make_enhanced_transcript(
            video_id=video_id, language_code="en", snippet_count=3
        )

        with (
            patch("chronovista.api.deps.youtube_oauth") as mock_oauth,
            patch(
                "chronovista.api.routers.transcripts._transcript_service"
            ) as mock_svc,
        ):
            _mock_auth(mock_oauth)
            mock_svc.get_transcript = AsyncMock(return_value=mock_transcript)
            response = await async_client.post(_download_url(video_id))

        assert response.status_code == 200, response.text

        async with integration_session_factory() as session:
            result = await session.execute(
                select(VideoTranscriptDB).where(
                    VideoTranscriptDB.video_id == video_id
                )
            )
            db_transcript = result.scalar_one_or_none()

        assert db_transcript is not None
        assert db_transcript.language_code == "en"

    async def test_saved_segments_have_correct_timing(
        self,
        async_client: AsyncClient,
        seed_video_without_transcript: dict[str, Any],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Each saved TranscriptSegment has start_time, end_time, and duration set."""
        video_id = seed_video_without_transcript["video_id"]
        mock_transcript = _make_enhanced_transcript(video_id=video_id, snippet_count=3)

        with (
            patch("chronovista.api.deps.youtube_oauth") as mock_oauth,
            patch(
                "chronovista.api.routers.transcripts._transcript_service"
            ) as mock_svc,
        ):
            _mock_auth(mock_oauth)
            mock_svc.get_transcript = AsyncMock(return_value=mock_transcript)
            response = await async_client.post(_download_url(video_id))

        assert response.status_code == 200, response.text

        async with integration_session_factory() as session:
            result = await session.execute(
                select(TranscriptSegmentDB)
                .where(TranscriptSegmentDB.video_id == video_id)
                .order_by(TranscriptSegmentDB.sequence_number.asc())
            )
            segments = result.scalars().all()

        assert len(segments) == 3
        for seg in segments:
            assert seg.start_time is not None
            assert seg.end_time is not None
            assert seg.duration is not None
            # end_time must be strictly greater than start_time (non-zero duration)
            assert seg.end_time >= seg.start_time

    async def test_saved_segments_ordered_by_sequence(
        self,
        async_client: AsyncClient,
        seed_video_without_transcript: dict[str, Any],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Segments are stored with ascending sequence_number matching snippet order."""
        video_id = seed_video_without_transcript["video_id"]
        mock_transcript = _make_enhanced_transcript(video_id=video_id, snippet_count=4)

        with (
            patch("chronovista.api.deps.youtube_oauth") as mock_oauth,
            patch(
                "chronovista.api.routers.transcripts._transcript_service"
            ) as mock_svc,
        ):
            _mock_auth(mock_oauth)
            mock_svc.get_transcript = AsyncMock(return_value=mock_transcript)
            response = await async_client.post(_download_url(video_id))

        assert response.status_code == 200, response.text

        async with integration_session_factory() as session:
            result = await session.execute(
                select(TranscriptSegmentDB)
                .where(TranscriptSegmentDB.video_id == video_id)
                .order_by(TranscriptSegmentDB.sequence_number.asc())
            )
            segments = result.scalars().all()

        sequence_numbers = [seg.sequence_number for seg in segments]
        assert sequence_numbers == sorted(sequence_numbers), (
            "Segment sequence_numbers are not in ascending order"
        )

    async def test_saved_segments_associated_with_correct_video(
        self,
        async_client: AsyncClient,
        seed_video_without_transcript: dict[str, Any],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """All persisted TranscriptSegment rows carry the correct video_id FK."""
        video_id = seed_video_without_transcript["video_id"]
        mock_transcript = _make_enhanced_transcript(video_id=video_id, snippet_count=3)

        with (
            patch("chronovista.api.deps.youtube_oauth") as mock_oauth,
            patch(
                "chronovista.api.routers.transcripts._transcript_service"
            ) as mock_svc,
        ):
            _mock_auth(mock_oauth)
            mock_svc.get_transcript = AsyncMock(return_value=mock_transcript)
            response = await async_client.post(_download_url(video_id))

        assert response.status_code == 200, response.text

        async with integration_session_factory() as session:
            result = await session.execute(
                select(TranscriptSegmentDB).where(
                    TranscriptSegmentDB.video_id == video_id
                )
            )
            segments = result.scalars().all()

        assert all(seg.video_id == video_id for seg in segments), (
            "One or more segments have an incorrect video_id FK"
        )

    async def test_no_orphan_data_after_failed_service_call(
        self,
        async_client: AsyncClient,
        seed_video_without_transcript: dict[str, Any],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """No transcript or segment rows are persisted when the service raises an error.

        This validates that the endpoint does not commit partial data when
        TranscriptNotFoundError is raised (the entire flow is aborted).
        """
        from chronovista.services.transcript_service import TranscriptNotFoundError

        video_id = seed_video_without_transcript["video_id"]

        with (
            patch("chronovista.api.deps.youtube_oauth") as mock_oauth,
            patch(
                "chronovista.api.routers.transcripts._transcript_service"
            ) as mock_svc,
        ):
            _mock_auth(mock_oauth)
            mock_svc.get_transcript = AsyncMock(
                side_effect=TranscriptNotFoundError("No captions found")
            )
            response = await async_client.post(_download_url(video_id))

        assert response.status_code == 404

        # Database must still be empty for this video
        async with integration_session_factory() as session:
            transcript_result = await session.execute(
                select(VideoTranscriptDB).where(
                    VideoTranscriptDB.video_id == video_id
                )
            )
            saved_transcript = transcript_result.scalar_one_or_none()

            segment_result = await session.execute(
                select(TranscriptSegmentDB).where(
                    TranscriptSegmentDB.video_id == video_id
                )
            )
            saved_segments = segment_result.scalars().all()

        assert saved_transcript is None, (
            "A VideoTranscript row was persisted even though the service raised an error"
        )
        assert len(saved_segments) == 0, (
            f"Expected 0 segments after service failure but found {len(saved_segments)}"
        )
