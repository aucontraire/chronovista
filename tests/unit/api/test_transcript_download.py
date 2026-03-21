"""Unit tests for POST /api/v1/videos/{video_id}/transcript/download endpoint.

Tests the download_transcript function in:
  src/chronovista/api/routers/transcripts.py

Mounted at: /api/v1/videos/{video_id}/transcript/download

Scenarios covered:
- 422 for invalid video_id format (too short, too long, bad characters)
- 401 for unauthenticated requests (require_auth raises HTTPException)
- 404 for transcript not found on YouTube (TranscriptNotFoundError)
- 409 for transcript already in database (existing transcript conflict)
- 503 for YouTube service unavailable (TranscriptServiceUnavailableError)
- 503 for rate-limit errors propagated via TranscriptServiceError
- 200 for successful download with correct response body shape
- 429 for in-flight download guard (concurrent download for same video_id)
- 200 with ?language query parameter forwarded to get_transcript
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, status
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.api.deps import get_db, require_auth
from chronovista.api.main import app
from chronovista.services.transcript_service import (
    TranscriptNotFoundError,
    TranscriptServiceError,
    TranscriptServiceUnavailableError,
)

# CRITICAL: Ensures all async tests work correctly with coverage tools.
# Without this, pytest-cov may skip async tests entirely.
pytestmark = pytest.mark.asyncio

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_VIDEO_ID = "dQw4w9WgXcQ"  # Exactly 11 chars, valid YouTube ID format
DOWNLOAD_URL = f"/api/v1/videos/{VALID_VIDEO_ID}/transcript/download"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db_transcript(
    *,
    video_id: str = VALID_VIDEO_ID,
    language_code: str = "en",
    is_cc: bool = True,
    transcript_type: str = "MANUAL",
    segment_count: int = 42,
    downloaded_at: datetime | None = None,
) -> MagicMock:
    """Build a minimal mock of the SQLAlchemy VideoTranscript DB row.

    The endpoint accesses these attributes directly on the ORM object returned
    by _transcript_repo.create_or_update(), so we set them explicitly.
    """
    if downloaded_at is None:
        downloaded_at = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)

    mock = MagicMock()
    mock.video_id = video_id
    mock.language_code = language_code
    mock.is_cc = is_cc
    mock.transcript_type = transcript_type
    mock.segment_count = segment_count
    mock.downloaded_at = downloaded_at
    return mock


def _make_enhanced_transcript(
    *,
    video_id: str = VALID_VIDEO_ID,
    language_code: str = "en",
    transcript_text: str = "Hello world.",
    transcript_type: str = "manual",
    download_reason: str = "user_request",
    confidence_score: float = 0.95,
    is_cc: bool = True,
    is_auto_synced: bool = False,
    track_kind: str = "standard",
    caption_name: str | None = "English (CC)",
    raw_transcript_data: dict[str, Any] | None = None,
) -> MagicMock:
    """Build a mock EnhancedVideoTranscriptBase returned by TranscriptService.get_transcript.

    transcript_type, download_reason, and track_kind use the *enum values*
    (lowercase) because the endpoint passes them directly into VideoTranscriptCreate,
    which is a Pydantic model that validates against TranscriptType, DownloadReason,
    and TrackKind enums respectively.

    Valid values:
      - transcript_type: 'auto', 'manual', 'translated'
      - download_reason: 'user_request', 'auto_preferred', 'learning_language',
                         'api_enrichment', 'schema_validation'
      - track_kind: 'standard', 'asr', 'forced'
    """
    mock = MagicMock()
    mock.video_id = video_id
    mock.language_code = language_code
    mock.transcript_text = transcript_text
    mock.transcript_type = transcript_type
    mock.download_reason = download_reason
    mock.confidence_score = confidence_score
    mock.is_cc = is_cc
    mock.is_auto_synced = is_auto_synced
    mock.track_kind = track_kind
    mock.caption_name = caption_name
    mock.raw_transcript_data = raw_transcript_data
    return mock


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session() -> AsyncMock:
    """Provide a clean AsyncSession mock for each test."""
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
async def client(mock_session: AsyncMock) -> AsyncGenerator[AsyncClient, None]:
    """FastAPI test client with DB and auth dependencies overridden.

    Both get_db and require_auth are overridden so tests run entirely
    in-process without a real database or OAuth token.
    """

    async def _get_db() -> AsyncGenerator[AsyncSession, None]:
        yield mock_session

    async def _require_auth() -> None:
        return None

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[require_auth] = _require_auth

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
async def unauth_client(mock_session: AsyncMock) -> AsyncGenerator[AsyncClient, None]:
    """FastAPI test client where require_auth raises 401.

    Used to test authentication-gated access to the download endpoint.
    The router is declared with ``dependencies=[Depends(require_auth)]``
    at the router level, so raising HTTPException 401 from the dependency
    override exercises that path.
    """

    async def _get_db() -> AsyncGenerator[AsyncSession, None]:
        yield mock_session

    async def _require_auth_fail() -> None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "NOT_AUTHENTICATED",
                "message": "Not authenticated. Run: chronovista auth login",
            },
        )

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[require_auth] = _require_auth_fail

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Test class: 422 — Invalid video_id format
# ---------------------------------------------------------------------------


class TestDownloadTranscriptVideoIdValidation:
    """Tests for custom video_id format validation inside download_transcript.

    The endpoint uses a module-level regex ``_VIDEO_ID_PATTERN`` to enforce
    exactly 11 characters of ``[A-Za-z0-9_-]``.  FastAPI's ``Path`` does not
    apply ``min_length``/``max_length`` constraints on this endpoint, so the
    validation is done inside the endpoint body via ``APIValidationError``.
    """

    BASE = "/api/v1/videos/{vid}/transcript/download"

    @patch(
        "chronovista.api.routers.transcripts._transcript_repo",
    )
    @patch(
        "chronovista.api.routers.transcripts._transcript_service",
    )
    async def test_too_short_video_id_returns_422(
        self,
        mock_service: MagicMock,
        mock_repo: MagicMock,
        client: AsyncClient,
    ) -> None:
        """A video_id shorter than 11 characters is rejected with 422."""
        url = self.BASE.format(vid="short")
        response = await client.post(url)

        assert response.status_code == 422
        body = response.json()
        # RFC 7807 shape: type, title, status, detail
        assert body["status"] == 422
        assert "video" in body.get("detail", "").lower() or "valid" in body.get("detail", "").lower()

    @patch(
        "chronovista.api.routers.transcripts._transcript_repo",
    )
    @patch(
        "chronovista.api.routers.transcripts._transcript_service",
    )
    async def test_too_long_video_id_returns_422(
        self,
        mock_service: MagicMock,
        mock_repo: MagicMock,
        client: AsyncClient,
    ) -> None:
        """A video_id longer than 11 characters is rejected with 422."""
        url = self.BASE.format(vid="dQw4w9WgXcQ_extra")
        response = await client.post(url)

        assert response.status_code == 422
        body = response.json()
        assert body["status"] == 422

    @patch(
        "chronovista.api.routers.transcripts._transcript_repo",
    )
    @patch(
        "chronovista.api.routers.transcripts._transcript_service",
    )
    async def test_invalid_chars_in_video_id_returns_422(
        self,
        mock_service: MagicMock,
        mock_repo: MagicMock,
        client: AsyncClient,
    ) -> None:
        """A video_id with characters outside [A-Za-z0-9_-] is rejected with 422."""
        # Special chars (dots, spaces, slashes) are not in the valid set
        url = self.BASE.format(vid="dQw4w9WgXc!")
        response = await client.post(url)

        assert response.status_code == 422
        body = response.json()
        assert body["status"] == 422

    @patch(
        "chronovista.api.routers.transcripts._pref_repo",
    )
    @patch(
        "chronovista.api.routers.transcripts._transcript_repo",
    )
    @patch(
        "chronovista.api.routers.transcripts._transcript_service",
    )
    async def test_exactly_11_valid_chars_passes_validation(
        self,
        mock_service: MagicMock,
        mock_repo: MagicMock,
        mock_pref_repo: MagicMock,
        client: AsyncClient,
    ) -> None:
        """An 11-character alphanumeric video_id passes format validation.

        Note: this test only verifies that format validation passes — the
        endpoint then checks the DB and falls through to service calls.
        We short-circuit by having the repo return an existing transcript
        to trigger a 409 (which proves the 422 guard did NOT fire).
        """
        mock_pref_repo.get_user_preferences = AsyncMock(return_value=[])
        existing = _make_db_transcript(video_id=VALID_VIDEO_ID)
        mock_repo.get_video_transcripts = AsyncMock(return_value=[existing])

        url = f"/api/v1/videos/{VALID_VIDEO_ID}/transcript/download"
        response = await client.post(url)

        # 409 Conflict means format validation passed and we reached the DB check
        assert response.status_code == 409

    @patch(
        "chronovista.api.routers.transcripts._transcript_repo",
    )
    @patch(
        "chronovista.api.routers.transcripts._transcript_service",
    )
    async def test_empty_video_id_segment_returns_not_found_or_405(
        self,
        mock_service: MagicMock,
        mock_repo: MagicMock,
        client: AsyncClient,
    ) -> None:
        """An empty video_id path segment is rejected at the routing level."""
        # An empty path segment collapses — FastAPI won't match the route
        response = await client.post("/api/v1/videos//transcript/download")
        # FastAPI returns 307 redirect or 404 for empty path segments; either is acceptable
        assert response.status_code in (307, 404, 405, 422)


# ---------------------------------------------------------------------------
# Test class: 401 — Unauthenticated
# ---------------------------------------------------------------------------


class TestDownloadTranscriptUnauthorized:
    """Tests that the download endpoint requires authentication."""

    async def test_unauthenticated_request_returns_401(
        self,
        unauth_client: AsyncClient,
    ) -> None:
        """Endpoint returns 401 when require_auth dependency raises HTTPException."""
        response = await unauth_client.post(DOWNLOAD_URL)

        assert response.status_code == 401

    async def test_unauthenticated_response_has_error_detail(
        self,
        unauth_client: AsyncClient,
    ) -> None:
        """401 response includes a detail payload from require_auth."""
        response = await unauth_client.post(DOWNLOAD_URL)
        body = response.json()

        # FastAPI wraps HTTPException detail under 'detail'
        assert "detail" in body


# ---------------------------------------------------------------------------
# Test class: 404 — Transcript not found on YouTube
# ---------------------------------------------------------------------------


class TestDownloadTranscriptNotFound:
    """Tests for 404 responses when YouTube has no transcript for the video."""

    @patch("chronovista.api.routers.transcripts._pref_repo")
    @patch("chronovista.api.routers.transcripts._transcript_repo")
    @patch("chronovista.api.routers.transcripts._transcript_service")
    async def test_transcript_not_found_returns_404(
        self,
        mock_service: MagicMock,
        mock_repo: MagicMock,
        mock_pref_repo: MagicMock,
        client: AsyncClient,
    ) -> None:
        """404 is returned when TranscriptNotFoundError is raised."""
        mock_pref_repo.get_user_preferences = AsyncMock(return_value=[])
        # No existing transcripts in DB (empty list → skip 409)
        mock_repo.get_video_transcripts = AsyncMock(return_value=[])
        # Service raises TranscriptNotFoundError
        mock_service.get_transcript = AsyncMock(
            side_effect=TranscriptNotFoundError("No transcript available")
        )

        response = await client.post(DOWNLOAD_URL)

        assert response.status_code == 404

    @patch("chronovista.api.routers.transcripts._pref_repo")
    @patch("chronovista.api.routers.transcripts._transcript_repo")
    @patch("chronovista.api.routers.transcripts._transcript_service")
    async def test_transcript_not_found_rfc7807_body(
        self,
        mock_service: MagicMock,
        mock_repo: MagicMock,
        mock_pref_repo: MagicMock,
        client: AsyncClient,
    ) -> None:
        """404 response body conforms to RFC 7807 Problem Details format."""
        mock_pref_repo.get_user_preferences = AsyncMock(return_value=[])
        mock_repo.get_video_transcripts = AsyncMock(return_value=[])
        mock_service.get_transcript = AsyncMock(
            side_effect=TranscriptNotFoundError("No transcript available")
        )

        response = await client.post(DOWNLOAD_URL)
        body = response.json()

        assert body["status"] == 404
        assert "type" in body
        assert "title" in body
        assert "detail" in body
        # The exception handler wraps this as NotFoundError for "Transcript"
        assert VALID_VIDEO_ID in body["detail"]

    @patch("chronovista.api.routers.transcripts._pref_repo")
    @patch("chronovista.api.routers.transcripts._transcript_repo")
    @patch("chronovista.api.routers.transcripts._transcript_service")
    async def test_get_transcript_called_with_correct_video_id(
        self,
        mock_service: MagicMock,
        mock_repo: MagicMock,
        mock_pref_repo: MagicMock,
        client: AsyncClient,
    ) -> None:
        """Service.get_transcript is called with the video_id from the URL path."""
        mock_pref_repo.get_user_preferences = AsyncMock(return_value=[])
        mock_repo.get_video_transcripts = AsyncMock(return_value=[])
        mock_service.get_transcript = AsyncMock(
            side_effect=TranscriptNotFoundError("No transcript available")
        )

        await client.post(DOWNLOAD_URL)

        mock_service.get_transcript.assert_awaited_once()
        call_kwargs = mock_service.get_transcript.call_args.kwargs
        assert call_kwargs["video_id"] == VALID_VIDEO_ID

    @patch("chronovista.api.routers.transcripts._pref_repo")
    @patch("chronovista.api.routers.transcripts._transcript_repo")
    @patch("chronovista.api.routers.transcripts._transcript_service")
    async def test_get_transcript_called_without_language_codes_by_default(
        self,
        mock_service: MagicMock,
        mock_repo: MagicMock,
        mock_pref_repo: MagicMock,
        client: AsyncClient,
    ) -> None:
        """Without ?language param, service is called with language_codes=None."""
        mock_pref_repo.get_user_preferences = AsyncMock(return_value=[])
        mock_repo.get_video_transcripts = AsyncMock(return_value=[])
        mock_service.get_transcript = AsyncMock(
            side_effect=TranscriptNotFoundError("No transcript available")
        )

        await client.post(DOWNLOAD_URL)

        call_kwargs = mock_service.get_transcript.call_args.kwargs
        assert call_kwargs["language_codes"] is None


# ---------------------------------------------------------------------------
# Test class: 409 — Transcript already exists
# ---------------------------------------------------------------------------


class TestDownloadTranscriptConflict:
    """Tests for 409 Conflict when the transcript already exists in the DB."""

    @patch("chronovista.api.routers.transcripts._pref_repo")
    @patch("chronovista.api.routers.transcripts._transcript_repo")
    @patch("chronovista.api.routers.transcripts._transcript_service")
    async def test_existing_transcript_returns_409(
        self,
        mock_service: MagicMock,
        mock_repo: MagicMock,
        mock_pref_repo: MagicMock,
        client: AsyncClient,
    ) -> None:
        """409 is returned when the repository already holds a transcript."""
        mock_pref_repo.get_user_preferences = AsyncMock(return_value=[])
        existing = _make_db_transcript(video_id=VALID_VIDEO_ID)
        mock_repo.get_video_transcripts = AsyncMock(return_value=[existing])

        response = await client.post(DOWNLOAD_URL)

        assert response.status_code == 409

    @patch("chronovista.api.routers.transcripts._pref_repo")
    @patch("chronovista.api.routers.transcripts._transcript_repo")
    @patch("chronovista.api.routers.transcripts._transcript_service")
    async def test_conflict_rfc7807_body(
        self,
        mock_service: MagicMock,
        mock_repo: MagicMock,
        mock_pref_repo: MagicMock,
        client: AsyncClient,
    ) -> None:
        """409 response body has RFC 7807 fields including status and detail."""
        mock_pref_repo.get_user_preferences = AsyncMock(return_value=[])
        existing = _make_db_transcript(video_id=VALID_VIDEO_ID)
        mock_repo.get_video_transcripts = AsyncMock(return_value=[existing])

        response = await client.post(DOWNLOAD_URL)
        body = response.json()

        assert body["status"] == 409
        assert "type" in body
        assert "title" in body
        assert "detail" in body

    @patch("chronovista.api.routers.transcripts._pref_repo")
    @patch("chronovista.api.routers.transcripts._transcript_repo")
    @patch("chronovista.api.routers.transcripts._transcript_service")
    async def test_service_not_called_when_transcript_exists(
        self,
        mock_service: MagicMock,
        mock_repo: MagicMock,
        mock_pref_repo: MagicMock,
        client: AsyncClient,
    ) -> None:
        """When the transcript already exists, get_transcript is never called."""
        mock_pref_repo.get_user_preferences = AsyncMock(return_value=[])
        existing = _make_db_transcript(video_id=VALID_VIDEO_ID)
        mock_repo.get_video_transcripts = AsyncMock(return_value=[existing])

        await client.post(DOWNLOAD_URL)

        mock_service.get_transcript.assert_not_called()

    @patch("chronovista.api.routers.transcripts._pref_repo")
    @patch("chronovista.api.routers.transcripts._transcript_repo")
    @patch("chronovista.api.routers.transcripts._transcript_service")
    async def test_conflict_includes_video_id_in_detail(
        self,
        mock_service: MagicMock,
        mock_repo: MagicMock,
        mock_pref_repo: MagicMock,
        client: AsyncClient,
    ) -> None:
        """409 detail message references the conflicting video_id."""
        mock_pref_repo.get_user_preferences = AsyncMock(return_value=[])
        existing = _make_db_transcript(video_id=VALID_VIDEO_ID)
        mock_repo.get_video_transcripts = AsyncMock(return_value=[existing])

        response = await client.post(DOWNLOAD_URL)
        body = response.json()

        assert VALID_VIDEO_ID in body["detail"]


# ---------------------------------------------------------------------------
# Test class: 503 — YouTube service unavailable
# ---------------------------------------------------------------------------


class TestDownloadTranscriptServiceUnavailable:
    """Tests for 503 Service Unavailable from YouTube transcript service."""

    @patch("chronovista.api.routers.transcripts._pref_repo")
    @patch("chronovista.api.routers.transcripts._transcript_repo")
    @patch("chronovista.api.routers.transcripts._transcript_service")
    async def test_service_unavailable_error_returns_503(
        self,
        mock_service: MagicMock,
        mock_repo: MagicMock,
        mock_pref_repo: MagicMock,
        client: AsyncClient,
    ) -> None:
        """503 is returned when TranscriptServiceUnavailableError is raised."""
        mock_pref_repo.get_user_preferences = AsyncMock(return_value=[])
        mock_repo.get_video_transcripts = AsyncMock(return_value=[])
        mock_service.get_transcript = AsyncMock(
            side_effect=TranscriptServiceUnavailableError(
                "YouTube transcript service unavailable"
            )
        )

        response = await client.post(DOWNLOAD_URL)

        assert response.status_code == 503

    @patch("chronovista.api.routers.transcripts._pref_repo")
    @patch("chronovista.api.routers.transcripts._transcript_repo")
    @patch("chronovista.api.routers.transcripts._transcript_service")
    async def test_service_unavailable_rfc7807_body(
        self,
        mock_service: MagicMock,
        mock_repo: MagicMock,
        mock_pref_repo: MagicMock,
        client: AsyncClient,
    ) -> None:
        """503 response has RFC 7807 fields with SERVICE_UNAVAILABLE code."""
        mock_pref_repo.get_user_preferences = AsyncMock(return_value=[])
        mock_repo.get_video_transcripts = AsyncMock(return_value=[])
        mock_service.get_transcript = AsyncMock(
            side_effect=TranscriptServiceUnavailableError("YouTube is down")
        )

        response = await client.post(DOWNLOAD_URL)
        body = response.json()

        assert body["status"] == 503
        assert "type" in body
        assert "title" in body
        assert body["code"] == "SERVICE_UNAVAILABLE"

    @patch("chronovista.api.routers.transcripts._pref_repo")
    @patch("chronovista.api.routers.transcripts._transcript_repo")
    @patch("chronovista.api.routers.transcripts._transcript_service")
    async def test_rate_limit_keyword_in_transcript_service_error_returns_503(
        self,
        mock_service: MagicMock,
        mock_repo: MagicMock,
        mock_pref_repo: MagicMock,
        client: AsyncClient,
    ) -> None:
        """503 is returned when TranscriptServiceError message contains 'rate limit'."""
        mock_pref_repo.get_user_preferences = AsyncMock(return_value=[])
        mock_repo.get_video_transcripts = AsyncMock(return_value=[])
        mock_service.get_transcript = AsyncMock(
            side_effect=TranscriptServiceError(
                "YouTube returned 429: rate limit exceeded for this IP"
            )
        )

        response = await client.post(DOWNLOAD_URL)

        assert response.status_code == 503

    @patch("chronovista.api.routers.transcripts._pref_repo")
    @patch("chronovista.api.routers.transcripts._transcript_repo")
    @patch("chronovista.api.routers.transcripts._transcript_service")
    async def test_too_many_keyword_in_error_returns_503(
        self,
        mock_service: MagicMock,
        mock_repo: MagicMock,
        mock_pref_repo: MagicMock,
        client: AsyncClient,
    ) -> None:
        """503 is returned when TranscriptServiceError message contains 'too many'."""
        mock_pref_repo.get_user_preferences = AsyncMock(return_value=[])
        mock_repo.get_video_transcripts = AsyncMock(return_value=[])
        mock_service.get_transcript = AsyncMock(
            side_effect=TranscriptServiceError("too many requests, slow down")
        )

        response = await client.post(DOWNLOAD_URL)

        assert response.status_code == 503

    @patch("chronovista.api.routers.transcripts._pref_repo")
    @patch("chronovista.api.routers.transcripts._transcript_repo")
    @patch("chronovista.api.routers.transcripts._transcript_service")
    async def test_quota_keyword_in_error_returns_503(
        self,
        mock_service: MagicMock,
        mock_repo: MagicMock,
        mock_pref_repo: MagicMock,
        client: AsyncClient,
    ) -> None:
        """503 is returned when TranscriptServiceError message contains 'quota'."""
        mock_pref_repo.get_user_preferences = AsyncMock(return_value=[])
        mock_repo.get_video_transcripts = AsyncMock(return_value=[])
        mock_service.get_transcript = AsyncMock(
            side_effect=TranscriptServiceError("quota exceeded for transcript API")
        )

        response = await client.post(DOWNLOAD_URL)

        assert response.status_code == 503

    @patch("chronovista.api.routers.transcripts._pref_repo")
    @patch("chronovista.api.routers.transcripts._transcript_repo")
    @patch("chronovista.api.routers.transcripts._transcript_service")
    async def test_service_unavailable_includes_instance_uri(
        self,
        mock_service: MagicMock,
        mock_repo: MagicMock,
        mock_pref_repo: MagicMock,
        client: AsyncClient,
    ) -> None:
        """503 response body includes the instance URI for the download endpoint."""
        mock_pref_repo.get_user_preferences = AsyncMock(return_value=[])
        mock_repo.get_video_transcripts = AsyncMock(return_value=[])
        mock_service.get_transcript = AsyncMock(
            side_effect=TranscriptServiceUnavailableError("unavailable")
        )

        response = await client.post(DOWNLOAD_URL)
        body = response.json()

        # The endpoint hardcodes the instance URI as the download path
        assert "instance" in body
        assert VALID_VIDEO_ID in body["instance"]


# ---------------------------------------------------------------------------
# Test class: 200 — Successful download
# ---------------------------------------------------------------------------


class TestDownloadTranscriptSuccess:
    """Tests for successful 200 responses from the download endpoint."""

    @patch("chronovista.api.routers.transcripts._pref_repo")
    @patch("chronovista.api.routers.transcripts._transcript_repo")
    @patch("chronovista.api.routers.transcripts._transcript_service")
    async def test_successful_download_returns_200(
        self,
        mock_service: MagicMock,
        mock_repo: MagicMock,
        mock_pref_repo: MagicMock,
        client: AsyncClient,
    ) -> None:
        """200 is returned when the transcript is downloaded and saved."""
        mock_pref_repo.get_user_preferences = AsyncMock(return_value=[])
        mock_repo.get_video_transcripts = AsyncMock(return_value=[])
        mock_service.get_transcript = AsyncMock(
            return_value=_make_enhanced_transcript()
        )
        db_transcript = _make_db_transcript()
        mock_repo.create_or_update = AsyncMock(return_value=db_transcript)

        response = await client.post(DOWNLOAD_URL)

        assert response.status_code == 200

    @patch("chronovista.api.routers.transcripts._pref_repo")
    @patch("chronovista.api.routers.transcripts._transcript_repo")
    @patch("chronovista.api.routers.transcripts._transcript_service")
    async def test_successful_download_response_shape(
        self,
        mock_service: MagicMock,
        mock_repo: MagicMock,
        mock_pref_repo: MagicMock,
        client: AsyncClient,
    ) -> None:
        """200 response body contains ApiResponse envelope with TranscriptDownloadResponse data."""
        mock_pref_repo.get_user_preferences = AsyncMock(return_value=[])
        mock_repo.get_video_transcripts = AsyncMock(return_value=[])
        mock_service.get_transcript = AsyncMock(
            return_value=_make_enhanced_transcript()
        )
        db_transcript = _make_db_transcript()
        mock_repo.create_or_update = AsyncMock(return_value=db_transcript)

        response = await client.post(DOWNLOAD_URL)
        body = response.json()

        # Outer ApiResponse envelope
        assert "data" in body
        data = body["data"]

        # TranscriptDownloadResponse fields
        assert data["video_id"] == VALID_VIDEO_ID
        assert data["language_code"] == "en"
        assert data["language_name"] == "English"
        assert data["transcript_type"] in ("manual", "auto_generated")
        assert isinstance(data["segment_count"], int)
        assert "downloaded_at" in data

    @patch("chronovista.api.routers.transcripts._pref_repo")
    @patch("chronovista.api.routers.transcripts._transcript_repo")
    @patch("chronovista.api.routers.transcripts._transcript_service")
    async def test_manual_transcript_type_display(
        self,
        mock_service: MagicMock,
        mock_repo: MagicMock,
        mock_pref_repo: MagicMock,
        client: AsyncClient,
    ) -> None:
        """is_cc=True maps to transcript_type='manual' in the response."""
        mock_pref_repo.get_user_preferences = AsyncMock(return_value=[])
        mock_repo.get_video_transcripts = AsyncMock(return_value=[])
        mock_service.get_transcript = AsyncMock(
            return_value=_make_enhanced_transcript(is_cc=True)
        )
        db_transcript = _make_db_transcript(is_cc=True, transcript_type="MANUAL")
        mock_repo.create_or_update = AsyncMock(return_value=db_transcript)

        response = await client.post(DOWNLOAD_URL)
        data = response.json()["data"]

        assert data["transcript_type"] == "manual"

    @patch("chronovista.api.routers.transcripts._pref_repo")
    @patch("chronovista.api.routers.transcripts._transcript_repo")
    @patch("chronovista.api.routers.transcripts._transcript_service")
    async def test_auto_generated_transcript_type_display(
        self,
        mock_service: MagicMock,
        mock_repo: MagicMock,
        mock_pref_repo: MagicMock,
        client: AsyncClient,
    ) -> None:
        """is_cc=False + transcript_type='AUTO' maps to 'auto_generated' in response."""
        mock_pref_repo.get_user_preferences = AsyncMock(return_value=[])
        mock_repo.get_video_transcripts = AsyncMock(return_value=[])
        mock_service.get_transcript = AsyncMock(
            return_value=_make_enhanced_transcript(is_cc=False)
        )
        db_transcript = _make_db_transcript(is_cc=False, transcript_type="AUTO")
        mock_repo.create_or_update = AsyncMock(return_value=db_transcript)

        response = await client.post(DOWNLOAD_URL)
        data = response.json()["data"]

        assert data["transcript_type"] == "auto_generated"

    @patch("chronovista.api.routers.transcripts._pref_repo")
    @patch("chronovista.api.routers.transcripts._transcript_repo")
    @patch("chronovista.api.routers.transcripts._transcript_service")
    async def test_segment_count_from_db_transcript(
        self,
        mock_service: MagicMock,
        mock_repo: MagicMock,
        mock_pref_repo: MagicMock,
        client: AsyncClient,
    ) -> None:
        """segment_count in response matches db_transcript.segment_count."""
        mock_pref_repo.get_user_preferences = AsyncMock(return_value=[])
        mock_repo.get_video_transcripts = AsyncMock(return_value=[])
        mock_service.get_transcript = AsyncMock(
            return_value=_make_enhanced_transcript()
        )
        db_transcript = _make_db_transcript(segment_count=99)
        mock_repo.create_or_update = AsyncMock(return_value=db_transcript)

        response = await client.post(DOWNLOAD_URL)
        data = response.json()["data"]

        assert data["segment_count"] == 99

    @patch("chronovista.api.routers.transcripts._pref_repo")
    @patch("chronovista.api.routers.transcripts._transcript_repo")
    @patch("chronovista.api.routers.transcripts._transcript_service")
    async def test_null_segment_count_defaults_to_zero(
        self,
        mock_service: MagicMock,
        mock_repo: MagicMock,
        mock_pref_repo: MagicMock,
        client: AsyncClient,
    ) -> None:
        """segment_count=None on the DB row is coerced to 0 in the response."""
        mock_pref_repo.get_user_preferences = AsyncMock(return_value=[])
        mock_repo.get_video_transcripts = AsyncMock(return_value=[])
        mock_service.get_transcript = AsyncMock(
            return_value=_make_enhanced_transcript()
        )
        db_transcript = _make_db_transcript(segment_count=0)
        db_transcript.segment_count = None  # Simulate NULL in DB
        mock_repo.create_or_update = AsyncMock(return_value=db_transcript)

        response = await client.post(DOWNLOAD_URL)
        data = response.json()["data"]

        assert data["segment_count"] == 0

    @patch("chronovista.api.routers.transcripts._pref_repo")
    @patch("chronovista.api.routers.transcripts._transcript_repo")
    @patch("chronovista.api.routers.transcripts._transcript_service")
    async def test_language_name_resolved_from_code(
        self,
        mock_service: MagicMock,
        mock_repo: MagicMock,
        mock_pref_repo: MagicMock,
        client: AsyncClient,
    ) -> None:
        """language_name is resolved from the language_code via get_language_name."""
        mock_pref_repo.get_user_preferences = AsyncMock(return_value=[])
        mock_repo.get_video_transcripts = AsyncMock(return_value=[])
        mock_service.get_transcript = AsyncMock(
            return_value=_make_enhanced_transcript(language_code="es")
        )
        db_transcript = _make_db_transcript(language_code="es")
        mock_repo.create_or_update = AsyncMock(return_value=db_transcript)

        response = await client.post(DOWNLOAD_URL)
        data = response.json()["data"]

        assert data["language_code"] == "es"
        assert data["language_name"] == "Spanish"

    @patch("chronovista.api.routers.transcripts._pref_repo")
    @patch("chronovista.api.routers.transcripts._transcript_repo")
    @patch("chronovista.api.routers.transcripts._transcript_service")
    async def test_unknown_language_code_returns_code_as_name(
        self,
        mock_service: MagicMock,
        mock_repo: MagicMock,
        mock_pref_repo: MagicMock,
        client: AsyncClient,
    ) -> None:
        """An unknown language code is returned as-is for language_name."""
        mock_pref_repo.get_user_preferences = AsyncMock(return_value=[])
        mock_repo.get_video_transcripts = AsyncMock(return_value=[])
        mock_service.get_transcript = AsyncMock(
            return_value=_make_enhanced_transcript(language_code="xx-unknown")
        )
        db_transcript = _make_db_transcript(language_code="xx-unknown")
        mock_repo.create_or_update = AsyncMock(return_value=db_transcript)

        response = await client.post(DOWNLOAD_URL)
        data = response.json()["data"]

        assert data["language_name"] == "xx-unknown"

    @patch("chronovista.api.routers.transcripts._pref_repo")
    @patch("chronovista.api.routers.transcripts._transcript_repo")
    @patch("chronovista.api.routers.transcripts._transcript_service")
    async def test_session_commit_called_after_save(
        self,
        mock_service: MagicMock,
        mock_repo: MagicMock,
        mock_pref_repo: MagicMock,
        client: AsyncClient,
        mock_session: AsyncMock,
    ) -> None:
        """session.commit() is called once after a successful transcript save."""
        mock_pref_repo.get_user_preferences = AsyncMock(return_value=[])
        mock_repo.get_video_transcripts = AsyncMock(return_value=[])
        mock_service.get_transcript = AsyncMock(
            return_value=_make_enhanced_transcript()
        )
        db_transcript = _make_db_transcript()
        mock_repo.create_or_update = AsyncMock(return_value=db_transcript)

        await client.post(DOWNLOAD_URL)

        mock_session.commit.assert_awaited_once()

    @patch("chronovista.api.routers.transcripts._pref_repo")
    @patch("chronovista.api.routers.transcripts._transcript_repo")
    @patch("chronovista.api.routers.transcripts._transcript_service")
    async def test_create_or_update_called_with_transcript_create(
        self,
        mock_service: MagicMock,
        mock_repo: MagicMock,
        mock_pref_repo: MagicMock,
        client: AsyncClient,
    ) -> None:
        """repository.create_or_update is called once during a successful download."""
        mock_pref_repo.get_user_preferences = AsyncMock(return_value=[])
        mock_repo.get_video_transcripts = AsyncMock(return_value=[])
        mock_service.get_transcript = AsyncMock(
            return_value=_make_enhanced_transcript()
        )
        db_transcript = _make_db_transcript()
        mock_repo.create_or_update = AsyncMock(return_value=db_transcript)

        await client.post(DOWNLOAD_URL)

        mock_repo.create_or_update.assert_awaited_once()


# ---------------------------------------------------------------------------
# Test class: 429 — In-flight download guard
# ---------------------------------------------------------------------------


class TestDownloadTranscriptInFlightGuard:
    """Tests for the module-level _downloads_in_progress set guard.

    The endpoint inserts the video_id into a module-level ``set`` before
    starting the download and removes it in the ``finally`` block.  A second
    concurrent request for the same video_id should receive 429.
    """

    @patch("chronovista.api.routers.transcripts._downloads_in_progress", new_callable=set)
    @patch("chronovista.api.routers.transcripts._transcript_repo")
    @patch("chronovista.api.routers.transcripts._transcript_service")
    async def test_in_flight_video_id_returns_429(
        self,
        mock_service: MagicMock,
        mock_repo: MagicMock,
        mock_in_flight: set[str],
        client: AsyncClient,
    ) -> None:
        """429 is returned when the video_id is already in _downloads_in_progress."""
        # Pre-populate the in-flight set to simulate a concurrent download
        mock_in_flight.add(VALID_VIDEO_ID)

        response = await client.post(DOWNLOAD_URL)

        assert response.status_code == 429

    @patch("chronovista.api.routers.transcripts._downloads_in_progress", new_callable=set)
    @patch("chronovista.api.routers.transcripts._transcript_repo")
    @patch("chronovista.api.routers.transcripts._transcript_service")
    async def test_in_flight_rfc7807_body(
        self,
        mock_service: MagicMock,
        mock_repo: MagicMock,
        mock_in_flight: set[str],
        client: AsyncClient,
    ) -> None:
        """429 response body has RFC 7807 fields with RATE_LIMITED code."""
        mock_in_flight.add(VALID_VIDEO_ID)

        response = await client.post(DOWNLOAD_URL)
        body = response.json()

        assert body["status"] == 429
        assert "type" in body
        assert "title" in body
        assert "detail" in body

    @patch("chronovista.api.routers.transcripts._downloads_in_progress", new_callable=set)
    @patch("chronovista.api.routers.transcripts._transcript_repo")
    @patch("chronovista.api.routers.transcripts._transcript_service")
    async def test_in_flight_includes_video_id_in_detail(
        self,
        mock_service: MagicMock,
        mock_repo: MagicMock,
        mock_in_flight: set[str],
        client: AsyncClient,
    ) -> None:
        """429 detail message mentions the video_id that is in-flight."""
        mock_in_flight.add(VALID_VIDEO_ID)

        response = await client.post(DOWNLOAD_URL)
        body = response.json()

        assert VALID_VIDEO_ID in body["detail"]

    @patch("chronovista.api.routers.transcripts._pref_repo")
    @patch("chronovista.api.routers.transcripts._downloads_in_progress", new_callable=set)
    @patch("chronovista.api.routers.transcripts._transcript_repo")
    @patch("chronovista.api.routers.transcripts._transcript_service")
    async def test_different_video_id_not_blocked_by_in_flight(
        self,
        mock_service: MagicMock,
        mock_repo: MagicMock,
        mock_in_flight: set[str],
        mock_pref_repo: MagicMock,
        client: AsyncClient,
    ) -> None:
        """A different video_id is NOT blocked by an in-flight download for another video."""
        mock_pref_repo.get_user_preferences = AsyncMock(return_value=[])
        other_video_id = "9bZkp7q19f0"
        mock_in_flight.add(other_video_id)

        # Our target video_id (VALID_VIDEO_ID) is NOT in the set
        # So it proceeds to the DB check and hits 409 (transcript exists)
        existing = _make_db_transcript(video_id=VALID_VIDEO_ID)
        mock_repo.get_video_transcripts = AsyncMock(return_value=[existing])

        response = await client.post(DOWNLOAD_URL)

        # 409 means we got past the in-flight guard (correct behavior)
        assert response.status_code == 409

    @patch("chronovista.api.routers.transcripts._pref_repo")
    @patch("chronovista.api.routers.transcripts._transcript_repo")
    @patch("chronovista.api.routers.transcripts._transcript_service")
    async def test_in_flight_set_cleared_on_success(
        self,
        mock_service: MagicMock,
        mock_repo: MagicMock,
        mock_pref_repo: MagicMock,
        client: AsyncClient,
    ) -> None:
        """After a successful download the video_id is removed from _downloads_in_progress.

        Verifies the ``finally`` block runs on the happy path so subsequent
        requests for the same video_id would not be spuriously blocked.
        """
        import chronovista.api.routers.transcripts as transcripts_module

        mock_pref_repo.get_user_preferences = AsyncMock(return_value=[])
        mock_repo.get_video_transcripts = AsyncMock(return_value=[])
        mock_service.get_transcript = AsyncMock(
            return_value=_make_enhanced_transcript()
        )
        db_transcript = _make_db_transcript()
        mock_repo.create_or_update = AsyncMock(return_value=db_transcript)

        await client.post(DOWNLOAD_URL)

        # After the request completes the in-flight set must not contain the video_id
        assert VALID_VIDEO_ID not in transcripts_module._downloads_in_progress

    @patch("chronovista.api.routers.transcripts._pref_repo")
    @patch("chronovista.api.routers.transcripts._transcript_repo")
    @patch("chronovista.api.routers.transcripts._transcript_service")
    async def test_in_flight_set_cleared_on_404(
        self,
        mock_service: MagicMock,
        mock_repo: MagicMock,
        mock_pref_repo: MagicMock,
        client: AsyncClient,
    ) -> None:
        """After a 404 error the video_id is removed from _downloads_in_progress.

        Verifies the ``finally`` block runs on the error path so subsequent
        requests are not permanently blocked.
        """
        import chronovista.api.routers.transcripts as transcripts_module

        mock_pref_repo.get_user_preferences = AsyncMock(return_value=[])
        mock_repo.get_video_transcripts = AsyncMock(return_value=[])
        mock_service.get_transcript = AsyncMock(
            side_effect=TranscriptNotFoundError("No transcript")
        )

        await client.post(DOWNLOAD_URL)

        assert VALID_VIDEO_ID not in transcripts_module._downloads_in_progress


# ---------------------------------------------------------------------------
# Test class: Language query parameter forwarding
# ---------------------------------------------------------------------------


class TestDownloadTranscriptLanguageParam:
    """Tests that the ?language query parameter is forwarded to the service."""

    @patch("chronovista.api.routers.transcripts._transcript_repo")
    @patch("chronovista.api.routers.transcripts._transcript_service")
    async def test_language_param_forwarded_as_list(
        self,
        mock_service: MagicMock,
        mock_repo: MagicMock,
        client: AsyncClient,
    ) -> None:
        """?language=es is forwarded to get_transcript as language_codes=['es']."""
        mock_repo.get_video_transcripts = AsyncMock(return_value=[])
        mock_service.get_transcript = AsyncMock(
            side_effect=TranscriptNotFoundError("No transcript")
        )

        await client.post(DOWNLOAD_URL, params={"language": "es"})

        call_kwargs = mock_service.get_transcript.call_args.kwargs
        assert call_kwargs["language_codes"] == ["es"]

    @patch("chronovista.api.routers.transcripts._pref_repo")
    @patch("chronovista.api.routers.transcripts._transcript_repo")
    @patch("chronovista.api.routers.transcripts._transcript_service")
    async def test_no_language_param_sends_none(
        self,
        mock_service: MagicMock,
        mock_repo: MagicMock,
        mock_pref_repo: MagicMock,
        client: AsyncClient,
    ) -> None:
        """Without ?language, get_transcript receives language_codes=None."""
        mock_pref_repo.get_user_preferences = AsyncMock(return_value=[])
        mock_repo.get_video_transcripts = AsyncMock(return_value=[])
        mock_service.get_transcript = AsyncMock(
            side_effect=TranscriptNotFoundError("No transcript")
        )

        await client.post(DOWNLOAD_URL)

        call_kwargs = mock_service.get_transcript.call_args.kwargs
        assert call_kwargs["language_codes"] is None

    @patch("chronovista.api.routers.transcripts._transcript_repo")
    @patch("chronovista.api.routers.transcripts._transcript_service")
    async def test_language_param_in_successful_download(
        self,
        mock_service: MagicMock,
        mock_repo: MagicMock,
        client: AsyncClient,
    ) -> None:
        """?language param is forwarded even on a successful 200 download."""
        mock_repo.get_video_transcripts = AsyncMock(return_value=[])
        mock_service.get_transcript = AsyncMock(
            return_value=_make_enhanced_transcript(language_code="fr")
        )
        db_transcript = _make_db_transcript(language_code="fr")
        mock_repo.create_or_update = AsyncMock(return_value=db_transcript)

        response = await client.post(DOWNLOAD_URL, params={"language": "fr"})

        assert response.status_code == 200
        call_kwargs = mock_service.get_transcript.call_args.kwargs
        assert call_kwargs["language_codes"] == ["fr"]
        assert response.json()["data"]["language_code"] == "fr"


# ---------------------------------------------------------------------------
# Test class: Known language names via get_language_name
# ---------------------------------------------------------------------------


class TestDownloadTranscriptLanguageNameResolution:
    """Tests for human-readable language name resolution in response bodies."""

    @pytest.mark.parametrize(
        "code, expected_name",
        [
            ("en", "English"),
            ("en-us", "English (US)"),
            ("en-gb", "English (UK)"),
            ("es", "Spanish"),
            ("fr", "French"),
            ("de", "German"),
            ("ja", "Japanese"),
            ("ko", "Korean"),
            ("zh-cn", "Chinese (Simplified)"),
            ("pt-br", "Portuguese (Brazil)"),
            ("ru", "Russian"),
            ("ar", "Arabic"),
            ("hi", "Hindi"),
        ],
    )
    @patch("chronovista.api.routers.transcripts._pref_repo")
    @patch("chronovista.api.routers.transcripts._transcript_repo")
    @patch("chronovista.api.routers.transcripts._transcript_service")
    async def test_language_name_resolution(
        self,
        mock_service: MagicMock,
        mock_repo: MagicMock,
        mock_pref_repo: MagicMock,
        client: AsyncClient,
        code: str,
        expected_name: str,
    ) -> None:
        """Each BCP-47 code is resolved to its expected human-readable name."""
        mock_pref_repo.get_user_preferences = AsyncMock(return_value=[])
        mock_repo.get_video_transcripts = AsyncMock(return_value=[])
        mock_service.get_transcript = AsyncMock(
            return_value=_make_enhanced_transcript(language_code=code)
        )
        db_transcript = _make_db_transcript(language_code=code)
        mock_repo.create_or_update = AsyncMock(return_value=db_transcript)

        response = await client.post(DOWNLOAD_URL)
        data = response.json()["data"]

        assert data["language_name"] == expected_name


# ---------------------------------------------------------------------------
# Test class: Edge cases and boundary conditions
# ---------------------------------------------------------------------------


class TestDownloadTranscriptEdgeCases:
    """Edge cases not covered by the main scenario classes."""

    @patch("chronovista.api.routers.transcripts._pref_repo")
    @patch("chronovista.api.routers.transcripts._transcript_repo")
    @patch("chronovista.api.routers.transcripts._transcript_service")
    async def test_transcript_type_manual_when_transcript_type_field_is_manual(
        self,
        mock_service: MagicMock,
        mock_repo: MagicMock,
        mock_pref_repo: MagicMock,
        client: AsyncClient,
    ) -> None:
        """is_cc=False but transcript_type='MANUAL' on DB row still yields 'manual' display."""
        mock_pref_repo.get_user_preferences = AsyncMock(return_value=[])
        mock_repo.get_video_transcripts = AsyncMock(return_value=[])
        # Enhanced transcript uses enum value 'manual' (lowercase) for Pydantic validation
        mock_service.get_transcript = AsyncMock(
            return_value=_make_enhanced_transcript(is_cc=False, transcript_type="manual")
        )
        # DB row uses the ORM string "MANUAL" (uppercase) — the endpoint checks this string
        db_transcript = _make_db_transcript(is_cc=False, transcript_type="MANUAL")
        mock_repo.create_or_update = AsyncMock(return_value=db_transcript)

        response = await client.post(DOWNLOAD_URL)
        data = response.json()["data"]

        assert data["transcript_type"] == "manual"

    @patch("chronovista.api.routers.transcripts._pref_repo")
    @patch("chronovista.api.routers.transcripts._transcript_repo")
    @patch("chronovista.api.routers.transcripts._transcript_service")
    async def test_raw_transcript_data_forwarded_to_create_or_update(
        self,
        mock_service: MagicMock,
        mock_repo: MagicMock,
        mock_pref_repo: MagicMock,
        client: AsyncClient,
    ) -> None:
        """raw_transcript_data from enhanced transcript is passed to create_or_update."""
        mock_pref_repo.get_user_preferences = AsyncMock(return_value=[])
        raw_data = {"snippets": [{"text": "Hello", "start": 0.0, "duration": 1.5}]}
        mock_repo.get_video_transcripts = AsyncMock(return_value=[])
        mock_service.get_transcript = AsyncMock(
            return_value=_make_enhanced_transcript(raw_transcript_data=raw_data)
        )
        db_transcript = _make_db_transcript()
        mock_repo.create_or_update = AsyncMock(return_value=db_transcript)

        await client.post(DOWNLOAD_URL)

        call_args = mock_repo.create_or_update.call_args
        assert call_args is not None
        # raw_transcript_data is passed as the second positional kwarg
        called_kwargs = call_args.kwargs
        assert called_kwargs.get("raw_transcript_data") == raw_data

    @patch("chronovista.api.routers.transcripts._pref_repo")
    @patch("chronovista.api.routers.transcripts._transcript_repo")
    @patch("chronovista.api.routers.transcripts._transcript_service")
    async def test_none_raw_transcript_data_passes_none(
        self,
        mock_service: MagicMock,
        mock_repo: MagicMock,
        mock_pref_repo: MagicMock,
        client: AsyncClient,
    ) -> None:
        """When enhanced_transcript.raw_transcript_data is None, None is passed to repo."""
        mock_pref_repo.get_user_preferences = AsyncMock(return_value=[])
        mock_repo.get_video_transcripts = AsyncMock(return_value=[])
        mock_service.get_transcript = AsyncMock(
            return_value=_make_enhanced_transcript(raw_transcript_data=None)
        )
        db_transcript = _make_db_transcript()
        mock_repo.create_or_update = AsyncMock(return_value=db_transcript)

        await client.post(DOWNLOAD_URL)

        call_kwargs = mock_repo.create_or_update.call_args.kwargs
        assert call_kwargs.get("raw_transcript_data") is None

    @patch("chronovista.api.routers.transcripts._pref_repo")
    @patch("chronovista.api.routers.transcripts._transcript_repo")
    @patch("chronovista.api.routers.transcripts._transcript_service")
    async def test_video_id_with_underscores_and_hyphens_passes(
        self,
        mock_service: MagicMock,
        mock_repo: MagicMock,
        mock_pref_repo: MagicMock,
        client: AsyncClient,
    ) -> None:
        """video_id containing underscores and hyphens (valid in YouTube IDs) passes validation."""
        mock_pref_repo.get_user_preferences = AsyncMock(return_value=[])
        vid = "abc_def-ghi"  # Exactly 11 chars with _ and -
        assert len(vid) == 11

        # Short-circuit via 409 to confirm format validation passed
        existing = _make_db_transcript(video_id=vid)
        mock_repo.get_video_transcripts = AsyncMock(return_value=[existing])

        url = f"/api/v1/videos/{vid}/transcript/download"
        response = await client.post(url)

        assert response.status_code == 409

    @patch("chronovista.api.routers.transcripts._pref_repo")
    @patch("chronovista.api.routers.transcripts._transcript_repo")
    @patch("chronovista.api.routers.transcripts._transcript_service")
    async def test_get_video_transcripts_called_with_correct_args(
        self,
        mock_service: MagicMock,
        mock_repo: MagicMock,
        mock_pref_repo: MagicMock,
        client: AsyncClient,
        mock_session: AsyncMock,
    ) -> None:
        """get_video_transcripts is called with the session and the video_id."""
        mock_pref_repo.get_user_preferences = AsyncMock(return_value=[])
        mock_repo.get_video_transcripts = AsyncMock(return_value=[])
        mock_service.get_transcript = AsyncMock(
            side_effect=TranscriptNotFoundError("not found")
        )

        await client.post(DOWNLOAD_URL)

        mock_repo.get_video_transcripts.assert_awaited_once()
        call_args = mock_repo.get_video_transcripts.call_args
        # Second positional argument should be the video_id
        assert VALID_VIDEO_ID in (call_args.args or list(call_args.kwargs.values()))
