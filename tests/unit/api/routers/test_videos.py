"""
Unit tests for video list endpoint sort and filter params (Feature 027, T028).

Tests the VideoSortField enum, sort_by/sort_order query params, liked_only
filter, and their combination with existing filters (has_transcript,
include_unavailable, tag, category, topic_id).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.api.deps import get_db, require_auth
from chronovista.api.main import app
from chronovista.api.routers.videos import VideoSortField

# CRITICAL: This line ensures async tests work with coverage

# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════


def _make_video_row(
    video_id: str,
    title: str = "Test Video",
    upload_date: datetime | None = None,
    channel_id: str = "UC_test_channel_12345_",
) -> MagicMock:
    """Create a mock Video database row."""
    video = MagicMock()
    video.video_id = video_id
    video.title = title
    video.channel_id = channel_id
    video.upload_date = upload_date or datetime(2024, 1, 15, tzinfo=UTC)
    video.duration = 300
    video.view_count = 1000
    video.category_id = None
    video.availability_status = "available"
    video.alternative_url = None
    video.recovered_at = None
    video.recovery_source = None

    # Mock relationships
    video.transcripts = []
    video.channel = MagicMock(title="Test Channel")
    video.tags = []
    video.category = None
    video.video_topics = []

    return video


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Create async test client for FastAPI testing."""
    mock_session = AsyncMock(spec=AsyncSession)

    # Default: return empty result set
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_result.scalar.return_value = 0

    # For count queries
    mock_count_result = MagicMock()
    mock_count_result.scalar.return_value = 0

    mock_session.execute = AsyncMock(return_value=mock_count_result)

    async def mock_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield mock_session

    async def mock_require_auth() -> None:
        return None

    app.dependency_overrides[get_db] = mock_get_db
    app.dependency_overrides[require_auth] = mock_require_auth

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.clear()


# ═══════════════════════════════════════════════════════════════════════════
# VideoSortField Enum Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestVideoSortFieldEnum:
    """Tests for VideoSortField enum definition."""

    def test_upload_date_value(self) -> None:
        """Verify upload_date enum value matches API parameter."""
        assert VideoSortField.UPLOAD_DATE.value == "upload_date"

    def test_title_value(self) -> None:
        """Verify title enum value matches API parameter."""
        assert VideoSortField.TITLE.value == "title"

    def test_enum_holds_exactly_the_supported_sorts(self) -> None:
        """Verify the enum holds exactly the supported sorts, and no date_added.

        The count is not the point -- the guard is that no ``date_added`` member
        appears. The frontend label "Date Added" maps to ``upload_date``
        (FR-017), so a separate member would silently duplicate it. Asserted
        explicitly here rather than implied by a member count, which Feature
        062 legitimately changed by adding ``relevance``.
        """
        members = list(VideoSortField)
        assert set(members) == {
            VideoSortField.UPLOAD_DATE,
            VideoSortField.TITLE,
            VideoSortField.RELEVANCE,
        }
        assert not any(member.value == "date_added" for member in members)

    def test_is_string_enum(self) -> None:
        """Verify VideoSortField is a str enum for FastAPI query param parsing."""
        assert isinstance(VideoSortField.UPLOAD_DATE, str)
        assert isinstance(VideoSortField.TITLE, str)


# ═══════════════════════════════════════════════════════════════════════════
# Default Sort Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestDefaultSort:
    """Tests for default sort behavior (upload_date desc)."""

    async def test_default_sort_returns_200(self, async_client: AsyncClient) -> None:
        """Default request (no sort params) should return 200."""
        response = await async_client.get("/api/v1/videos")
        assert response.status_code == 200

    async def test_default_sort_response_has_data(
        self, async_client: AsyncClient
    ) -> None:
        """Default request should have data and pagination keys."""
        response = await async_client.get("/api/v1/videos")
        body = response.json()
        assert "data" in body
        assert "pagination" in body


# ═══════════════════════════════════════════════════════════════════════════
# Unset-vs-explicit sort, and the relevance guard (Feature 062)
# ═══════════════════════════════════════════════════════════════════════════


class TestSortUnsetState:
    """``sort_by`` carries a distinct unset state (FR-009e).

    The parameter default moved off the signature and into the body so the
    endpoint can tell "caller sent nothing" from "caller explicitly chose
    upload_date". Feature 062 needs that distinction to auto-select relevance
    only when the caller expressed no preference (FR-009b). These tests pin the
    externally visible half of it: existing callers must see no change.
    """

    async def test_omitting_sort_by_still_succeeds(
        self, async_client: AsyncClient
    ) -> None:
        """No sort_by behaves exactly as it did when the default was on the param."""
        response = await async_client.get("/api/v1/videos")
        assert response.status_code == 200

    async def test_explicit_upload_date_still_succeeds(
        self, async_client: AsyncClient
    ) -> None:
        """Explicitly requesting the former default is still accepted."""
        response = await async_client.get("/api/v1/videos?sort_by=upload_date")
        assert response.status_code == 200

    async def test_relevance_without_entity_filter_is_rejected(
        self, async_client: AsyncClient
    ) -> None:
        """Relevance has no meaning without a required entity set.

        Must be a 400 that explains itself -- not a 422 from enum validation,
        and emphatically not a 500 from an unmapped sort column. ``RELEVANCE``
        is deliberately absent from ``_VIDEO_SORT_COLUMN_MAP`` because its
        ordering comes from the entity qualification subquery, so an unguarded
        request would raise KeyError.
        """
        response = await async_client.get("/api/v1/videos?sort_by=relevance")
        assert response.status_code == 400
        assert "relevance" in response.text.lower()

    async def test_unknown_sort_value_still_422(
        self, async_client: AsyncClient
    ) -> None:
        """Adding an enum member must not turn unknown values into 400s."""
        response = await async_client.get("/api/v1/videos?sort_by=not_a_sort")
        assert response.status_code == 422


# ═══════════════════════════════════════════════════════════════════════════
# Entity filter validation (Feature 062)
# ═══════════════════════════════════════════════════════════════════════════


class TestEntityFilterValidation:
    """Every rejection the entity filter can produce.

    Each of these is a 400 rather than a silently-empty 200 or an ignored
    filter. That diverges from this endpoint's convention for tag / topic /
    category, which ignore unrecognised values and report them in ``warnings``.
    The divergence is deliberate (FR-016b): the entity filter is CONJUNCTIVE,
    so silently dropping a required entity BROADENS the result -- a
    three-entity intersection quietly answered as a two-entity one returns
    more videos, presenting a wrong answer confidently. Dropping one value
    from an OR-filter narrows instead, which is self-evident to the user.
    """

    async def test_unknown_entity_id_is_rejected(
        self, async_client: AsyncClient
    ) -> None:
        """FR-016b: never a silent empty result."""
        unknown = uuid.uuid4()
        response = await async_client.get(f"/api/v1/videos?entity_id={unknown}")
        assert response.status_code == 400
        assert str(unknown) in response.text

    async def test_unknown_excluded_entity_id_is_rejected(
        self, async_client: AsyncClient
    ) -> None:
        """Exclusion gets the same treatment as inclusion."""
        unknown = uuid.uuid4()
        response = await async_client.get(f"/api/v1/videos?exclude_entity_id={unknown}")
        assert response.status_code == 400

    async def test_required_and_excluded_overlap_is_rejected(
        self, async_client: AsyncClient
    ) -> None:
        """FR-016: an entity cannot be both required and excluded.

        Checked before entity existence, so the conflict is reported even for
        ids that do not exist -- the request is incoherent either way.
        """
        same = uuid.uuid4()
        response = await async_client.get(
            f"/api/v1/videos?entity_id={same}&exclude_entity_id={same}"
        )
        assert response.status_code == 400
        assert str(same) in response.text

    async def test_required_set_over_ceiling_is_rejected(
        self, async_client: AsyncClient
    ) -> None:
        """FR-002a/FR-002b: explained, not silently truncated."""
        params = "&".join(f"entity_id={uuid.uuid4()}" for _ in range(11))
        response = await async_client.get(f"/api/v1/videos?{params}")
        assert response.status_code == 400
        assert "10" in response.text

    async def test_excluded_set_over_ceiling_is_rejected(
        self, async_client: AsyncClient
    ) -> None:
        """The ceiling applies to each set SEPARATELY (FR-002a)."""
        params = "&".join(f"exclude_entity_id={uuid.uuid4()}" for _ in range(11))
        response = await async_client.get(f"/api/v1/videos?{params}")
        assert response.status_code == 400

    async def test_ten_per_set_is_within_the_per_set_ceiling(
        self, async_client: AsyncClient
    ) -> None:
        """Ten required and ten excluded is twenty entities in one request.

        Each set is inside its own ceiling of 10 (FR-002a), so the per-set rule
        does not reject it -- but both sets count toward the global filter cap
        of 15 (FR-002d), which does. The request must fail on the GLOBAL limit,
        naming it, rather than on a per-set limit neither set exceeded.
        """
        params = "&".join(
            [f"entity_id={uuid.uuid4()}" for _ in range(10)]
            + [f"exclude_entity_id={uuid.uuid4()}" for _ in range(10)]
        )
        response = await async_client.get(f"/api/v1/videos?{params}")
        assert response.status_code == 400
        assert "15" in response.text

    async def test_unrecognised_min_evidence_is_rejected(
        self, async_client: AsyncClient
    ) -> None:
        """FR-018a: rejected, never silently defaulted.

        422 rather than 400: an enum-typed parameter rejects at the validation
        layer, which is what this endpoint already does for an unknown
        ``sort_by``. FR-018a requires rejection with an explanation, not a
        particular status code.
        """
        response = await async_client.get("/api/v1/videos?min_evidence=bogus")
        assert response.status_code == 422


# ═══════════════════════════════════════════════════════════════════════════
# Sort Field Parameter Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestSortFieldParams:
    """Tests for sort_by and sort_order query parameters."""

    async def test_sort_by_upload_date_asc(self, async_client: AsyncClient) -> None:
        """sort_by=upload_date&sort_order=asc should return 200."""
        response = await async_client.get(
            "/api/v1/videos?sort_by=upload_date&sort_order=asc"
        )
        assert response.status_code == 200

    async def test_sort_by_upload_date_desc(self, async_client: AsyncClient) -> None:
        """sort_by=upload_date&sort_order=desc should return 200."""
        response = await async_client.get(
            "/api/v1/videos?sort_by=upload_date&sort_order=desc"
        )
        assert response.status_code == 200

    async def test_sort_by_title_asc(self, async_client: AsyncClient) -> None:
        """sort_by=title&sort_order=asc should return 200."""
        response = await async_client.get("/api/v1/videos?sort_by=title&sort_order=asc")
        assert response.status_code == 200

    async def test_sort_by_title_desc(self, async_client: AsyncClient) -> None:
        """sort_by=title&sort_order=desc should return 200."""
        response = await async_client.get(
            "/api/v1/videos?sort_by=title&sort_order=desc"
        )
        assert response.status_code == 200

    async def test_invalid_sort_by_returns_422(self, async_client: AsyncClient) -> None:
        """Invalid sort_by value should return 422 validation error."""
        response = await async_client.get("/api/v1/videos?sort_by=invalid_field")
        assert response.status_code == 422

    async def test_invalid_sort_order_returns_422(
        self, async_client: AsyncClient
    ) -> None:
        """Invalid sort_order value should return 422 validation error."""
        response = await async_client.get("/api/v1/videos?sort_order=invalid")
        assert response.status_code == 422

    async def test_sort_by_date_added_returns_422(
        self, async_client: AsyncClient
    ) -> None:
        """sort_by=date_added is NOT a valid field (maps to upload_date on frontend only)."""
        response = await async_client.get("/api/v1/videos?sort_by=date_added")
        assert response.status_code == 422


# ═══════════════════════════════════════════════════════════════════════════
# Liked-Only Filter Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestLikedOnlyFilter:
    """Tests for liked_only query parameter."""

    async def test_liked_only_true_returns_200(self, async_client: AsyncClient) -> None:
        """liked_only=true should return 200."""
        response = await async_client.get("/api/v1/videos?liked_only=true")
        assert response.status_code == 200

    async def test_liked_only_false_returns_200(
        self, async_client: AsyncClient
    ) -> None:
        """liked_only=false should return 200 (effectively no filter)."""
        response = await async_client.get("/api/v1/videos?liked_only=false")
        assert response.status_code == 200

    async def test_liked_only_absent_returns_200(
        self, async_client: AsyncClient
    ) -> None:
        """No liked_only param should return 200 (default false)."""
        response = await async_client.get("/api/v1/videos")
        assert response.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════
# Combined Filter Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestCombinedFilters:
    """Tests for combining sort/liked with existing filter parameters."""

    async def test_liked_with_has_transcript(self, async_client: AsyncClient) -> None:
        """liked_only + has_transcript should both be accepted."""
        response = await async_client.get(
            "/api/v1/videos?liked_only=true&has_transcript=true"
        )
        assert response.status_code == 200

    async def test_liked_with_include_unavailable(
        self, async_client: AsyncClient
    ) -> None:
        """liked_only + include_unavailable should both be accepted."""
        response = await async_client.get(
            "/api/v1/videos?liked_only=true&include_unavailable=true"
        )
        assert response.status_code == 200

    async def test_liked_with_tag_filter(self, async_client: AsyncClient) -> None:
        """liked_only + tag filter should both be accepted."""
        response = await async_client.get("/api/v1/videos?liked_only=true&tag=music")
        assert response.status_code == 200

    async def test_sort_with_existing_filters(self, async_client: AsyncClient) -> None:
        """sort_by + sort_order with existing classification filters."""
        response = await async_client.get(
            "/api/v1/videos?sort_by=title&sort_order=asc&tag=music&category=10"
        )
        assert response.status_code == 200

    async def test_all_filters_combined(self, async_client: AsyncClient) -> None:
        """All filter types combined should return 200."""
        response = await async_client.get(
            "/api/v1/videos"
            "?sort_by=title&sort_order=asc"
            "&liked_only=true"
            "&has_transcript=true"
            "&include_unavailable=true"
            "&tag=music"
        )
        assert response.status_code == 200

    async def test_sort_with_pagination(self, async_client: AsyncClient) -> None:
        """Sort params should work with pagination params."""
        response = await async_client.get(
            "/api/v1/videos?sort_by=title&sort_order=desc&limit=10&offset=5"
        )
        assert response.status_code == 200

    async def test_liked_with_channel_filter(self, async_client: AsyncClient) -> None:
        """liked_only + channel_id should both be accepted."""
        response = await async_client.get(
            "/api/v1/videos?liked_only=true&channel_id=UCtest_channel_123456789"
        )
        assert response.status_code == 200
