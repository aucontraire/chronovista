"""Integration tests for entity mention API endpoints (Feature 038 — T024).

Covers:
  - GET /api/v1/videos/{video_id}/entities
  - GET /api/v1/entities/{entity_id}/videos

All tests require an integration database. Each test class seeds its own data
via the ``seed_entity_data`` fixture and cleans up after itself in FK-reverse
order to maintain isolation from other integration test files.

Auth: ``require_auth`` is patched via ``unittest.mock.patch`` so that
tests do not need real OAuth credentials, following the same pattern used in
``test_transcript_corrections_api.py``.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, AsyncGenerator
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select
from uuid_utils import uuid7
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import (
    Channel as ChannelDB,
    EntityMention as EntityMentionDB,
    NamedEntity as NamedEntityDB,
    TranscriptSegment as TranscriptSegmentDB,
    Video as VideoDB,
    VideoTranscript as VideoTranscriptDB,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

# CRITICAL: Ensures all async tests in this module run with pytest-asyncio
pytestmark = pytest.mark.asyncio

# ---------------------------------------------------------------------------
# Unique stable IDs — chosen to avoid collisions with other test files.
# All IDs must respect column length constraints.
# channel_id: max 24 chars, video_id: max 20 chars.
# ---------------------------------------------------------------------------
_CHANNEL_ID = "UCentity_api_test0001"  # 21 chars — within 24-char limit
_VIDEO_ID = "entity_api_vid01"  # 16 chars — within 20-char limit
_LANGUAGE_CODE = "en"

# A second video used for pagination and multi-video entity tests
_VIDEO_ID_2 = "entity_api_vid02"  # 16 chars


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------


def _video_entities_url(video_id: str) -> str:
    """Return the video-entities endpoint URL."""
    return f"/api/v1/videos/{video_id}/entities"


def _entity_videos_url(entity_id: str) -> str:
    """Return the entity-videos endpoint URL."""
    return f"/api/v1/entities/{entity_id}/videos"


def _list_entities_url() -> str:
    """Return the list-entities endpoint URL."""
    return "/api/v1/entities"


def _entity_detail_url(entity_id: str) -> str:
    """Return the entity-detail endpoint URL."""
    return f"/api/v1/entities/{entity_id}"


# ---------------------------------------------------------------------------
# Shared seed fixture
# ---------------------------------------------------------------------------


@pytest.fixture
async def seed_entity_data(
    integration_session_factory: "async_sessionmaker[AsyncSession]",
) -> AsyncGenerator[dict[str, Any], None]:
    """Seed the integration DB with channel, videos, transcripts, segments, entity, and mentions.

    Yields a dict with stable IDs and the seeded entity UUID so individual
    tests can query by entity_id without hard-coding UUIDs.

    Cleanup removes all seeded rows in FK-reverse order after each test.

    Notes
    -----
    - One channel, two videos (``_VIDEO_ID``, ``_VIDEO_ID_2``).
    - Both videos have a single "en" transcript and two transcript segments.
    - One NamedEntity (``"Elon Musk"``, type ``"person"``).
    - Two EntityMention rows linking the entity to segments in ``_VIDEO_ID``.
    - Zero EntityMention rows for ``_VIDEO_ID_2`` (used for empty-data tests).
    """
    # --- Seed phase --------------------------------------------------------
    # Close the session before yielding so the connection returns to the pool.
    # The async_client's override_get_db needs pool connections during API
    # calls; keeping the seed session open would exhaust pool_size=2.
    entity_id = uuid.uuid4()
    segment1_id: int = 0
    segment2_id: int = 0

    async with integration_session_factory() as session:
        # ---- Channel (FK parent for videos) --------------------------------
        existing_channel = (
            await session.execute(
                select(ChannelDB).where(ChannelDB.channel_id == _CHANNEL_ID)
            )
        ).scalar_one_or_none()
        if not existing_channel:
            channel = ChannelDB(
                channel_id=_CHANNEL_ID,
                title="Entity API Test Channel",
            )
            session.add(channel)

        # ---- Video 1 -------------------------------------------------------
        existing_video1 = (
            await session.execute(
                select(VideoDB).where(VideoDB.video_id == _VIDEO_ID)
            )
        ).scalar_one_or_none()
        if not existing_video1:
            video1 = VideoDB(
                video_id=_VIDEO_ID,
                channel_id=_CHANNEL_ID,
                title="Entity API Test Video 1",
                description="Integration test video for Feature 038",
                upload_date=datetime(2024, 3, 1, tzinfo=timezone.utc),
                duration=600,
            )
            session.add(video1)

        # ---- Video 2 (used for empty-mention tests) ------------------------
        existing_video2 = (
            await session.execute(
                select(VideoDB).where(VideoDB.video_id == _VIDEO_ID_2)
            )
        ).scalar_one_or_none()
        if not existing_video2:
            video2 = VideoDB(
                video_id=_VIDEO_ID_2,
                channel_id=_CHANNEL_ID,
                title="Entity API Test Video 2",
                description="Second integration test video for Feature 038",
                upload_date=datetime(2024, 3, 2, tzinfo=timezone.utc),
                duration=300,
            )
            session.add(video2)

        await session.commit()

        # ---- VideoTranscript for video 1 ----------------------------------
        existing_transcript1 = (
            await session.execute(
                select(VideoTranscriptDB).where(
                    VideoTranscriptDB.video_id == _VIDEO_ID,
                    VideoTranscriptDB.language_code == _LANGUAGE_CODE,
                )
            )
        ).scalar_one_or_none()
        if not existing_transcript1:
            transcript1 = VideoTranscriptDB(
                video_id=_VIDEO_ID,
                language_code=_LANGUAGE_CODE,
                transcript_text="Elon Musk founded SpaceX. Later Elon Musk also founded Tesla.",
                transcript_type="MANUAL",
                download_reason="USER_REQUEST",
                is_cc=False,
                is_auto_synced=False,
                track_kind="standard",
            )
            session.add(transcript1)

        # ---- VideoTranscript for video 2 ----------------------------------
        existing_transcript2 = (
            await session.execute(
                select(VideoTranscriptDB).where(
                    VideoTranscriptDB.video_id == _VIDEO_ID_2,
                    VideoTranscriptDB.language_code == _LANGUAGE_CODE,
                )
            )
        ).scalar_one_or_none()
        if not existing_transcript2:
            transcript2 = VideoTranscriptDB(
                video_id=_VIDEO_ID_2,
                language_code=_LANGUAGE_CODE,
                transcript_text="This video has no entity mentions.",
                transcript_type="MANUAL",
                download_reason="USER_REQUEST",
                is_cc=False,
                is_auto_synced=False,
                track_kind="standard",
            )
            session.add(transcript2)

        await session.commit()

        # ---- TranscriptSegments for video 1 (two segments) ----------------
        segment1 = TranscriptSegmentDB(
            video_id=_VIDEO_ID,
            language_code=_LANGUAGE_CODE,
            text="Elon Musk founded SpaceX.",
            start_time=0.0,
            duration=5.0,
            end_time=5.0,
            sequence_number=0,
            has_correction=False,
        )
        segment2 = TranscriptSegmentDB(
            video_id=_VIDEO_ID,
            language_code=_LANGUAGE_CODE,
            text="Later Elon Musk also founded Tesla.",
            start_time=5.0,
            duration=4.0,
            end_time=9.0,
            sequence_number=1,
            has_correction=False,
        )
        session.add(segment1)
        session.add(segment2)
        await session.commit()
        segment1_id = segment1.id
        segment2_id = segment2.id

        # ---- NamedEntity ---------------------------------------------------
        existing_entity = (
            await session.execute(
                select(NamedEntityDB).where(
                    NamedEntityDB.canonical_name == "Elon Musk",
                    NamedEntityDB.entity_type == "person",
                )
            )
        ).scalar_one_or_none()

        if existing_entity:
            entity_id = existing_entity.id
        else:
            entity = NamedEntityDB(
                id=entity_id,
                canonical_name="Elon Musk",
                canonical_name_normalized="elon musk",
                entity_type="person",
                description="Entrepreneur and CEO of SpaceX and Tesla.",
            )
            session.add(entity)
            await session.commit()

        # ---- EntityMention rows -------------------------------------------
        # Explicit id= with uuid.UUID(bytes=...) avoids uuid_utils.UUID vs
        # stdlib uuid.UUID type mismatch in SQLAlchemy's sentinel insert.
        mention1 = EntityMentionDB(
            id=uuid.UUID(bytes=uuid7().bytes),
            entity_id=entity_id,
            segment_id=segment1_id,
            video_id=_VIDEO_ID,
            language_code=_LANGUAGE_CODE,
            mention_text="Elon Musk",
            detection_method="rule_match",
            confidence=1.0,
        )
        mention2 = EntityMentionDB(
            id=uuid.UUID(bytes=uuid7().bytes),
            entity_id=entity_id,
            segment_id=segment2_id,
            video_id=_VIDEO_ID,
            language_code=_LANGUAGE_CODE,
            mention_text="Elon Musk",
            detection_method="rule_match",
            confidence=1.0,
        )
        session.add(mention1)
        session.add(mention2)
        await session.commit()

    # Session closed — pool connection released for test API calls.

    yield {
        "entity_id": str(entity_id),
        "entity_id_uuid": entity_id,
        "video_id": _VIDEO_ID,
        "video_id_2": _VIDEO_ID_2,
        "channel_id": _CHANNEL_ID,
        "language_code": _LANGUAGE_CODE,
        "segment1_id": segment1_id,
        "segment2_id": segment2_id,
    }

    # --- Cleanup phase (FK reverse order) ---------------------------------
    async with integration_session_factory() as session:
        await session.execute(
            delete(EntityMentionDB).where(EntityMentionDB.video_id.in_([_VIDEO_ID, _VIDEO_ID_2]))
        )
        await session.execute(
            delete(TranscriptSegmentDB).where(
                TranscriptSegmentDB.video_id.in_([_VIDEO_ID, _VIDEO_ID_2])
            )
        )
        await session.execute(
            delete(VideoTranscriptDB).where(
                VideoTranscriptDB.video_id.in_([_VIDEO_ID, _VIDEO_ID_2])
            )
        )
        await session.execute(
            delete(VideoDB).where(VideoDB.video_id.in_([_VIDEO_ID, _VIDEO_ID_2]))
        )
        await session.execute(
            delete(NamedEntityDB).where(
                NamedEntityDB.canonical_name == "Elon Musk",
                NamedEntityDB.entity_type == "person",
            )
        )
        await session.execute(
            delete(ChannelDB).where(ChannelDB.channel_id == _CHANNEL_ID)
        )
        await session.commit()


# ---------------------------------------------------------------------------
# T024 — GET /api/v1/videos/{video_id}/entities
# ---------------------------------------------------------------------------


class TestGetVideoEntities:
    """Integration tests for GET /api/v1/videos/{video_id}/entities."""

    async def test_get_video_entities_200_with_data(
        self,
        async_client: AsyncClient,
        seed_entity_data: dict[str, Any],
    ) -> None:
        """200 response contains entity summaries when mentions exist.

        Verifies the response envelope contains a non-empty ``data`` list,
        each item has the required fields (entity_id, canonical_name,
        entity_type, description, mention_count, first_mention_time), and
        the mention_count reflects the two seeded EntityMention rows.
        """
        video_id = seed_entity_data["video_id"]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(_video_entities_url(video_id))

        assert response.status_code == 200, response.text
        body = response.json()

        assert "data" in body
        data = body["data"]
        assert isinstance(data, list)
        assert len(data) >= 1, "Expected at least one entity summary"

        # Find the seeded entity in the response
        entity_summary = next(
            (item for item in data if item["canonical_name"] == "Elon Musk"),
            None,
        )
        assert entity_summary is not None, "Expected 'Elon Musk' in entity summaries"
        assert entity_summary["entity_id"] == seed_entity_data["entity_id"]
        assert entity_summary["entity_type"] == "person"
        assert entity_summary["description"] == "Entrepreneur and CEO of SpaceX and Tesla."
        assert entity_summary["mention_count"] == 2
        # first_mention_time should be 0.0 — the start_time of segment1
        assert entity_summary["first_mention_time"] == pytest.approx(0.0)

    async def test_get_video_entities_200_empty_data(
        self,
        async_client: AsyncClient,
        seed_entity_data: dict[str, Any],
    ) -> None:
        """200 response with empty data list when video exists but has no entity mentions.

        Uses ``_VIDEO_ID_2`` which has a transcript and segments seeded but
        zero EntityMention rows.
        """
        video_id = seed_entity_data["video_id_2"]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(_video_entities_url(video_id))

        assert response.status_code == 200, response.text
        body = response.json()

        assert "data" in body
        assert body["data"] == [], f"Expected empty list, got: {body['data']}"

    async def test_get_video_entities_404_non_existent_video(
        self,
        async_client: AsyncClient,
        seed_entity_data: dict[str, Any],
    ) -> None:
        """404 response when video_id does not exist in the database."""
        non_existent_video_id = "nonexist_v001"

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                _video_entities_url(non_existent_video_id)
            )

        assert response.status_code == 404, response.text

    async def test_get_video_entities_401_unauthenticated(
        self,
        async_client: AsyncClient,
        seed_entity_data: dict[str, Any],
    ) -> None:
        """401 response when the client is not authenticated."""
        video_id = seed_entity_data["video_id"]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = False
            response = await async_client.get(_video_entities_url(video_id))

        assert response.status_code == 401, response.text

    async def test_get_video_entities_language_filter_matching(
        self,
        async_client: AsyncClient,
        seed_entity_data: dict[str, Any],
    ) -> None:
        """200 response with entity data when language_code filter matches seeded mentions.

        The seeded mentions use language_code "en", so filtering by "en" should
        return the same entity summary as the unfiltered request.
        """
        video_id = seed_entity_data["video_id"]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                _video_entities_url(video_id),
                params={"language_code": "en"},
            )

        assert response.status_code == 200, response.text
        body = response.json()
        data = body["data"]
        assert isinstance(data, list)
        assert len(data) >= 1

        entity_summary = next(
            (item for item in data if item["canonical_name"] == "Elon Musk"),
            None,
        )
        assert entity_summary is not None
        assert entity_summary["mention_count"] == 2

    async def test_get_video_entities_language_filter_no_match(
        self,
        async_client: AsyncClient,
        seed_entity_data: dict[str, Any],
    ) -> None:
        """200 response with empty data when language_code filter does not match any mentions.

        Seeded mentions are "en"; filtering by "es" should return empty list.
        """
        video_id = seed_entity_data["video_id"]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                _video_entities_url(video_id),
                params={"language_code": "es"},
            )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["data"] == [], "Expected empty list for non-matching language filter"

    async def test_get_video_entities_response_sorted_by_mention_count_desc(
        self,
        async_client: AsyncClient,
        seed_entity_data: dict[str, Any],
    ) -> None:
        """Entity summaries are sorted by mention_count descending in the response.

        With a single entity, the list has one item. This test documents the
        sort contract and verifies it does not raise an error when only one
        entity is present.
        """
        video_id = seed_entity_data["video_id"]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(_video_entities_url(video_id))

        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert isinstance(data, list)

        # Verify items are in descending mention_count order
        counts = [item["mention_count"] for item in data]
        assert counts == sorted(counts, reverse=True), (
            f"Expected mention_count sorted descending, got: {counts}"
        )

    async def test_get_video_entities_response_schema_fields(
        self,
        async_client: AsyncClient,
        seed_entity_data: dict[str, Any],
    ) -> None:
        """Every item in the data list has all required VideoEntitySummary fields."""
        video_id = seed_entity_data["video_id"]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(_video_entities_url(video_id))

        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert len(data) >= 1

        required_fields = {
            "entity_id",
            "canonical_name",
            "entity_type",
            "description",
            "mention_count",
            "first_mention_time",
        }
        for item in data:
            missing = required_fields - item.keys()
            assert not missing, f"Missing fields in entity summary: {missing}"
            # entity_id must be a valid UUID string
            uuid.UUID(item["entity_id"])
            # mention_count must be a positive integer
            assert isinstance(item["mention_count"], int)
            assert item["mention_count"] > 0
            # first_mention_time must be a non-negative float
            assert isinstance(item["first_mention_time"], float)
            assert item["first_mention_time"] >= 0.0


# ---------------------------------------------------------------------------
# T024 — GET /api/v1/entities/{entity_id}/videos
# ---------------------------------------------------------------------------


class TestGetEntityVideos:
    """Integration tests for GET /api/v1/entities/{entity_id}/videos."""

    async def test_get_entity_videos_200_with_data(
        self,
        async_client: AsyncClient,
        seed_entity_data: dict[str, Any],
    ) -> None:
        """200 response with video list and mention previews when mentions exist.

        Verifies the response has ``data`` (list) and ``pagination`` envelope,
        the seeded video appears in the results, mention_count matches the two
        seeded EntityMention rows, and each result has up to 5 mention previews.
        """
        entity_id = seed_entity_data["entity_id"]
        video_id = seed_entity_data["video_id"]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(_entity_videos_url(entity_id))

        assert response.status_code == 200, response.text
        body = response.json()

        # Top-level envelope
        assert "data" in body
        assert "pagination" in body
        data = body["data"]
        pagination = body["pagination"]

        assert isinstance(data, list)
        assert len(data) >= 1, "Expected at least one video result"

        # Find the seeded video
        video_result = next(
            (item for item in data if item["video_id"] == video_id),
            None,
        )
        assert video_result is not None, f"Expected video_id {video_id!r} in results"
        assert video_result["video_title"] == "Entity API Test Video 1"
        assert isinstance(video_result["channel_name"], str)
        assert len(video_result["channel_name"]) > 0
        assert video_result["mention_count"] == 2

        # Mention previews
        mentions = video_result["mentions"]
        assert isinstance(mentions, list)
        assert len(mentions) <= 5, "At most 5 mention previews per video"
        assert len(mentions) == 2, "Exactly 2 mentions seeded for this video"
        for preview in mentions:
            assert "segment_id" in preview
            assert "start_time" in preview
            assert "mention_text" in preview
            assert preview["mention_text"] == "Elon Musk"

        # Pagination envelope
        assert "total" in pagination
        assert "limit" in pagination
        assert "offset" in pagination
        assert "has_more" in pagination
        assert isinstance(pagination["total"], int)
        assert pagination["total"] >= 1
        assert pagination["offset"] == 0

    async def test_get_entity_videos_200_empty_data(
        self,
        async_client: AsyncClient,
        integration_session_factory: "async_sessionmaker[AsyncSession]",
        seed_entity_data: dict[str, Any],
    ) -> None:
        """200 response with empty data list when entity exists but has no mentions.

        Creates a second NamedEntity with no EntityMention rows, queries it,
        verifies empty data list and total=0 in pagination, then cleans up.
        """
        empty_entity_id = uuid.uuid4()

        async with integration_session_factory() as session:
            empty_entity = NamedEntityDB(
                id=empty_entity_id,
                canonical_name="Empty Entity Test",
                canonical_name_normalized="empty entity test",
                entity_type="person",
                description=None,
            )
            session.add(empty_entity)
            await session.commit()

        try:
            with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
                mock_oauth.is_authenticated.return_value = True
                response = await async_client.get(
                    _entity_videos_url(str(empty_entity_id))
                )

            assert response.status_code == 200, response.text
            body = response.json()

            assert body["data"] == []
            assert body["pagination"]["total"] == 0
            assert body["pagination"]["has_more"] is False
        finally:
            async with integration_session_factory() as session:
                await session.execute(
                    delete(NamedEntityDB).where(NamedEntityDB.id == empty_entity_id)
                )
                await session.commit()

    async def test_get_entity_videos_404_non_existent_entity(
        self,
        async_client: AsyncClient,
        seed_entity_data: dict[str, Any],
    ) -> None:
        """404 response when entity_id is a valid UUID but does not exist in the database."""
        non_existent_entity_id = str(uuid.uuid4())

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                _entity_videos_url(non_existent_entity_id)
            )

        assert response.status_code == 404, response.text

    async def test_get_entity_videos_404_invalid_uuid(
        self,
        async_client: AsyncClient,
        seed_entity_data: dict[str, Any],
    ) -> None:
        """404 response when entity_id is not a valid UUID string.

        The router parses the entity_id to UUID; an invalid format triggers
        NotFoundError (404) by design rather than a 422 validation error.
        """
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(_entity_videos_url("not-a-valid-uuid"))

        assert response.status_code == 404, response.text

    async def test_get_entity_videos_401_unauthenticated(
        self,
        async_client: AsyncClient,
        seed_entity_data: dict[str, Any],
    ) -> None:
        """401 response when the client is not authenticated."""
        entity_id = seed_entity_data["entity_id"]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = False
            response = await async_client.get(_entity_videos_url(entity_id))

        assert response.status_code == 401, response.text

    async def test_get_entity_videos_language_filter_matching(
        self,
        async_client: AsyncClient,
        seed_entity_data: dict[str, Any],
    ) -> None:
        """200 response with data when language_code filter matches seeded mentions (en)."""
        entity_id = seed_entity_data["entity_id"]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                _entity_videos_url(entity_id),
                params={"language_code": "en"},
            )

        assert response.status_code == 200, response.text
        body = response.json()
        assert len(body["data"]) >= 1
        assert body["pagination"]["total"] >= 1

    async def test_get_entity_videos_language_filter_no_match(
        self,
        async_client: AsyncClient,
        seed_entity_data: dict[str, Any],
    ) -> None:
        """200 response with empty data when language_code filter does not match any mentions.

        Seeded mentions are "en"; filtering by "fr" should return empty list with total=0.
        """
        entity_id = seed_entity_data["entity_id"]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                _entity_videos_url(entity_id),
                params={"language_code": "fr"},
            )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["data"] == []
        assert body["pagination"]["total"] == 0

    async def test_get_entity_videos_pagination_limit(
        self,
        async_client: AsyncClient,
        seed_entity_data: dict[str, Any],
    ) -> None:
        """Pagination limit=1 returns at most 1 result.

        With one video seeded, limit=1 returns 1 result and has_more is False
        when total videos equals the limit.
        """
        entity_id = seed_entity_data["entity_id"]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                _entity_videos_url(entity_id),
                params={"limit": 1, "offset": 0},
            )

        assert response.status_code == 200, response.text
        body = response.json()
        data = body["data"]
        pagination = body["pagination"]

        assert len(data) <= 1, "At most 1 result with limit=1"
        assert pagination["limit"] == 1
        assert pagination["offset"] == 0

    async def test_get_entity_videos_pagination_offset(
        self,
        async_client: AsyncClient,
        seed_entity_data: dict[str, Any],
    ) -> None:
        """Pagination offset beyond total returns empty data list.

        With 1 video seeded, offset=100 should return empty results while
        total still reflects the actual count.
        """
        entity_id = seed_entity_data["entity_id"]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                _entity_videos_url(entity_id),
                params={"limit": 20, "offset": 100},
            )

        assert response.status_code == 200, response.text
        body = response.json()
        # offset beyond total returns empty data but total is still > 0
        assert body["data"] == []
        assert body["pagination"]["offset"] == 100
        assert body["pagination"]["total"] >= 1
        assert body["pagination"]["has_more"] is False

    async def test_get_entity_videos_pagination_has_more_false(
        self,
        async_client: AsyncClient,
        seed_entity_data: dict[str, Any],
    ) -> None:
        """has_more is False when total <= offset + limit (default limit=20)."""
        entity_id = seed_entity_data["entity_id"]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(_entity_videos_url(entity_id))

        assert response.status_code == 200, response.text
        pagination = response.json()["pagination"]
        total = pagination["total"]
        limit = pagination["limit"]
        offset = pagination["offset"]
        has_more = pagination["has_more"]

        expected_has_more = offset + limit < total
        assert has_more is expected_has_more, (
            f"has_more={has_more} but expected {expected_has_more} "
            f"(total={total}, limit={limit}, offset={offset})"
        )

    async def test_get_entity_videos_response_schema_fields(
        self,
        async_client: AsyncClient,
        seed_entity_data: dict[str, Any],
    ) -> None:
        """Every item in data has all required EntityVideoResult fields.

        Validates the complete response schema including MentionPreview fields.
        """
        entity_id = seed_entity_data["entity_id"]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(_entity_videos_url(entity_id))

        assert response.status_code == 200, response.text
        body = response.json()
        data = body["data"]
        assert len(data) >= 1

        required_video_fields = {"video_id", "video_title", "channel_name", "mention_count", "mentions"}
        required_mention_fields = {"segment_id", "start_time", "mention_text"}
        required_pagination_fields = {"total", "limit", "offset", "has_more"}

        for video_result in data:
            missing = required_video_fields - video_result.keys()
            assert not missing, f"Missing EntityVideoResult fields: {missing}"
            assert isinstance(video_result["mention_count"], int)
            assert video_result["mention_count"] > 0
            assert isinstance(video_result["mentions"], list)
            assert len(video_result["mentions"]) <= 5

            for preview in video_result["mentions"]:
                missing_preview = required_mention_fields - preview.keys()
                assert not missing_preview, f"Missing MentionPreview fields: {missing_preview}"
                assert isinstance(preview["segment_id"], int)
                assert isinstance(preview["start_time"], float)
                assert isinstance(preview["mention_text"], str)

        pagination = body["pagination"]
        missing_pagination = required_pagination_fields - pagination.keys()
        assert not missing_pagination, f"Missing PaginationMeta fields: {missing_pagination}"

    async def test_get_entity_videos_mention_previews_ordered_by_start_time(
        self,
        async_client: AsyncClient,
        seed_entity_data: dict[str, Any],
    ) -> None:
        """Mention previews within each video result are ordered by start_time ascending.

        The two seeded segments have start_time 0.0 and 5.0; previews should
        appear in ascending order.
        """
        entity_id = seed_entity_data["entity_id"]
        video_id = seed_entity_data["video_id"]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(_entity_videos_url(entity_id))

        assert response.status_code == 200, response.text
        data = response.json()["data"]

        video_result = next(
            (item for item in data if item["video_id"] == video_id),
            None,
        )
        assert video_result is not None
        previews = video_result["mentions"]
        assert len(previews) == 2

        start_times = [p["start_time"] for p in previews]
        assert start_times == sorted(start_times), (
            f"Expected mention previews sorted by start_time ASC, got: {start_times}"
        )
        assert start_times[0] == pytest.approx(0.0)
        assert start_times[1] == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# T038 — GET /api/v1/entities  (list entities)
# ---------------------------------------------------------------------------


class TestListEntities:
    """Integration tests for GET /api/v1/entities.

    The endpoint returns active entities only with optional filtering by
    type, has_mentions (bool), and search (case-insensitive substring),
    sorting by name (default) or mention count (desc), and standard
    limit/offset pagination.

    All tests rely on ``seed_entity_data`` which seeds one active NamedEntity
    (``"Elon Musk"``, type ``"person"``).  Tests that require a second entity
    for sorting/pagination create and clean up their own row.
    """

    async def test_list_entities_200_with_data(
        self,
        async_client: AsyncClient,
        seed_entity_data: dict[str, Any],
    ) -> None:
        """200 response contains ``data`` list and ``pagination`` envelope.

        Verifies that the seeded entity appears in the response, and that
        the pagination object includes the required keys with correct types.
        """
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(_list_entities_url())

        assert response.status_code == 200, response.text
        body = response.json()

        assert "data" in body
        assert "pagination" in body

        data = body["data"]
        pagination = body["pagination"]

        assert isinstance(data, list)
        assert len(data) >= 1, "Expected at least the seeded entity in the list"

        # Verify the seeded entity is present
        elon = next(
            (item for item in data if item["canonical_name"] == "Elon Musk"),
            None,
        )
        assert elon is not None, "Expected 'Elon Musk' in list response"
        assert elon["entity_id"] == seed_entity_data["entity_id"]
        assert elon["entity_type"] == "person"
        assert elon["status"] == "active"
        assert isinstance(elon["mention_count"], int)
        assert isinstance(elon["video_count"], int)

        # Pagination keys
        assert "total" in pagination
        assert "limit" in pagination
        assert "offset" in pagination
        assert "has_more" in pagination
        assert isinstance(pagination["total"], int)
        assert pagination["total"] >= 1
        assert pagination["offset"] == 0

    async def test_list_entities_response_schema_fields(
        self,
        async_client: AsyncClient,
        seed_entity_data: dict[str, Any],
    ) -> None:
        """Every item in ``data`` has all required entity fields.

        Validates entity_id is a parseable UUID, canonical_name and
        entity_type are non-empty strings, status is "active", and
        mention_count / video_count are non-negative integers.
        """
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(_list_entities_url())

        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert len(data) >= 1

        required_fields = {
            "entity_id",
            "canonical_name",
            "entity_type",
            "description",
            "status",
            "mention_count",
            "video_count",
        }
        for item in data:
            missing = required_fields - item.keys()
            assert not missing, f"Missing fields in entity list item: {missing}"
            # entity_id must be a valid UUID string
            uuid.UUID(item["entity_id"])
            assert isinstance(item["canonical_name"], str)
            assert len(item["canonical_name"]) > 0
            assert isinstance(item["entity_type"], str)
            assert item["status"] == "active", (
                f"Expected status='active', got: {item['status']!r}"
            )
            assert isinstance(item["mention_count"], int)
            assert item["mention_count"] >= 0
            assert isinstance(item["video_count"], int)
            assert item["video_count"] >= 0

    async def test_list_entities_filter_by_type(
        self,
        async_client: AsyncClient,
        seed_entity_data: dict[str, Any],
    ) -> None:
        """``type=person`` filter returns only person-type entities.

        The seeded entity is type ``"person"``, so it must appear in the
        filtered response.  Querying for ``type=organization`` should not
        return it.
        """
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            # Filter for person — should include the seeded entity
            response_person = await async_client.get(
                _list_entities_url(), params={"type": "person"}
            )
            # Filter for organization — should NOT include the seeded entity
            response_org = await async_client.get(
                _list_entities_url(), params={"type": "organization"}
            )

        assert response_person.status_code == 200, response_person.text
        person_data = response_person.json()["data"]
        assert all(item["entity_type"] == "person" for item in person_data), (
            "All items must have entity_type='person' when type filter is applied"
        )
        elon = next(
            (item for item in person_data if item["canonical_name"] == "Elon Musk"),
            None,
        )
        assert elon is not None, "Expected 'Elon Musk' in type=person results"

        assert response_org.status_code == 200, response_org.text
        org_data = response_org.json()["data"]
        elon_org = next(
            (item for item in org_data if item["canonical_name"] == "Elon Musk"),
            None,
        )
        assert elon_org is None, "Did not expect 'Elon Musk' in type=organization results"

    async def test_list_entities_filter_has_mentions_true(
        self,
        async_client: AsyncClient,
        integration_session_factory: "async_sessionmaker[AsyncSession]",
        seed_entity_data: dict[str, Any],
    ) -> None:
        """``has_mentions=true`` returns only entities with mention_count > 0.

        Creates a temporary entity with mention_count=5, queries with
        ``has_mentions=true``, verifies all returned items have mention_count > 0,
        then cleans up the temporary entity.
        """
        temp_entity_id = uuid.uuid4()
        async with integration_session_factory() as session:
            temp_entity = NamedEntityDB(
                id=temp_entity_id,
                canonical_name="Mentioned Entity Test",
                canonical_name_normalized="mentioned entity test",
                entity_type="person",
                description=None,
                mention_count=5,
            )
            session.add(temp_entity)
            await session.commit()

        try:
            with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
                mock_oauth.is_authenticated.return_value = True
                response = await async_client.get(
                    _list_entities_url(), params={"has_mentions": "true"}
                )

            assert response.status_code == 200, response.text
            data = response.json()["data"]

            # All returned items must have mention_count > 0
            for item in data:
                assert item["mention_count"] > 0, (
                    f"has_mentions=true must exclude entities with mention_count=0, "
                    f"but got mention_count={item['mention_count']} for {item['canonical_name']!r}"
                )

            # The temp entity with mention_count=5 must appear
            mentioned = next(
                (item for item in data if item["canonical_name"] == "Mentioned Entity Test"),
                None,
            )
            assert mentioned is not None, "Expected temp entity with mention_count=5 in results"
            assert mentioned["mention_count"] == 5
        finally:
            async with integration_session_factory() as session:
                await session.execute(
                    delete(NamedEntityDB).where(NamedEntityDB.id == temp_entity_id)
                )
                await session.commit()

    async def test_list_entities_filter_has_mentions_false(
        self,
        async_client: AsyncClient,
        seed_entity_data: dict[str, Any],
    ) -> None:
        """``has_mentions=false`` returns only entities with mention_count = 0.

        The seeded entity defaults to mention_count=0 in the DB (statistics
        columns are denormalised and not updated by the EntityMention inserts
        in the fixture), so it must appear in the ``has_mentions=false`` results.
        """
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                _list_entities_url(), params={"has_mentions": "false"}
            )

        assert response.status_code == 200, response.text
        data = response.json()["data"]

        # All returned items must have mention_count == 0
        for item in data:
            assert item["mention_count"] == 0, (
                f"has_mentions=false must only return entities with mention_count=0, "
                f"but got mention_count={item['mention_count']} for {item['canonical_name']!r}"
            )

    async def test_list_entities_search_by_name_case_insensitive(
        self,
        async_client: AsyncClient,
        seed_entity_data: dict[str, Any],
    ) -> None:
        """``search`` param performs a case-insensitive substring match on canonical_name.

        Queries ``search=elon`` (lowercase) and verifies "Elon Musk" is returned.
        Also queries ``search=ELON`` (uppercase) to confirm case-insensitivity.
        """
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response_lower = await async_client.get(
                _list_entities_url(), params={"search": "elon"}
            )
            response_upper = await async_client.get(
                _list_entities_url(), params={"search": "ELON"}
            )

        assert response_lower.status_code == 200, response_lower.text
        lower_data = response_lower.json()["data"]
        elon_lower = next(
            (item for item in lower_data if item["canonical_name"] == "Elon Musk"),
            None,
        )
        assert elon_lower is not None, "Expected 'Elon Musk' when searching 'elon'"

        assert response_upper.status_code == 200, response_upper.text
        upper_data = response_upper.json()["data"]
        elon_upper = next(
            (item for item in upper_data if item["canonical_name"] == "Elon Musk"),
            None,
        )
        assert elon_upper is not None, "Expected 'Elon Musk' when searching 'ELON'"

    async def test_list_entities_search_no_match_returns_empty(
        self,
        async_client: AsyncClient,
        seed_entity_data: dict[str, Any],
    ) -> None:
        """``search`` param with a string that matches no entity returns empty data list.

        Uses a highly specific string unlikely to match any real entity.
        """
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                _list_entities_url(),
                params={"search": "zzz_no_match_entity_xyzabc_unique"},
            )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["data"] == [], (
            f"Expected empty data for search that matches nothing, got: {body['data']}"
        )
        assert body["pagination"]["total"] == 0

    async def test_list_entities_sort_by_name_default(
        self,
        async_client: AsyncClient,
        integration_session_factory: "async_sessionmaker[AsyncSession]",
        seed_entity_data: dict[str, Any],
    ) -> None:
        """Default sort (no ``sort`` param) returns entities in alphabetical name order.

        Seeds a second entity with canonical_name ``"Aaron Entity Sort Test"``
        (alphabetically before ``"Elon Musk"``), queries without ``sort``, verifies
        ascending alphabetical ordering, then removes the temporary entity.
        """
        temp_entity_id = uuid.uuid4()
        async with integration_session_factory() as session:
            temp_entity = NamedEntityDB(
                id=temp_entity_id,
                canonical_name="Aaron Entity Sort Test",
                canonical_name_normalized="aaron entity sort test",
                entity_type="person",
                description=None,
            )
            session.add(temp_entity)
            await session.commit()

        try:
            with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
                mock_oauth.is_authenticated.return_value = True
                # Search to limit results to only our two controlled entities
                response = await async_client.get(
                    _list_entities_url(),
                    params={"search": "aaron entity sort test"},
                )

            assert response.status_code == 200, response.text
            data = response.json()["data"]

            # The temp entity should appear — verify ascending canonical_name order for all items
            names = [item["canonical_name"] for item in data]
            assert names == sorted(names), (
                f"Expected alphabetical ascending order, got: {names}"
            )
            # The temp entity starting with 'Aaron' must be first if it appears alongside others
            assert any(item["canonical_name"] == "Aaron Entity Sort Test" for item in data)
        finally:
            async with integration_session_factory() as session:
                await session.execute(
                    delete(NamedEntityDB).where(NamedEntityDB.id == temp_entity_id)
                )
                await session.commit()

    async def test_list_entities_sort_by_mentions_desc(
        self,
        async_client: AsyncClient,
        integration_session_factory: "async_sessionmaker[AsyncSession]",
        seed_entity_data: dict[str, Any],
    ) -> None:
        """``sort=mentions`` returns entities ordered by mention_count descending.

        Seeds two controlled entities with known mention_count values (10 and 2),
        queries with ``sort=mentions``, verifies they appear in descending order,
        then cleans up both temporary entities.
        """
        entity_high_id = uuid.uuid4()
        entity_low_id = uuid.uuid4()
        async with integration_session_factory() as session:
            entity_high = NamedEntityDB(
                id=entity_high_id,
                canonical_name="Zz Sort Mentions High Test",
                canonical_name_normalized="zz sort mentions high test",
                entity_type="person",
                description=None,
                mention_count=10,
            )
            entity_low = NamedEntityDB(
                id=entity_low_id,
                canonical_name="Zz Sort Mentions Low Test",
                canonical_name_normalized="zz sort mentions low test",
                entity_type="person",
                description=None,
                mention_count=2,
            )
            session.add(entity_high)
            session.add(entity_low)
            await session.commit()

        try:
            with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
                mock_oauth.is_authenticated.return_value = True
                response = await async_client.get(
                    _list_entities_url(),
                    params={"sort": "mentions", "search": "Zz Sort Mentions"},
                )

            assert response.status_code == 200, response.text
            data = response.json()["data"]
            assert len(data) == 2, (
                f"Expected exactly 2 results for the controlled search, got: {len(data)}"
            )

            counts = [item["mention_count"] for item in data]
            assert counts == sorted(counts, reverse=True), (
                f"Expected mention_count sorted descending with sort=mentions, got: {counts}"
            )
            assert counts[0] == 10
            assert counts[1] == 2
        finally:
            async with integration_session_factory() as session:
                await session.execute(
                    delete(NamedEntityDB).where(
                        NamedEntityDB.id.in_([entity_high_id, entity_low_id])
                    )
                )
                await session.commit()

    async def test_list_entities_pagination_limit(
        self,
        async_client: AsyncClient,
        seed_entity_data: dict[str, Any],
    ) -> None:
        """``limit=1`` returns at most 1 entity in the data list."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                _list_entities_url(), params={"limit": 1, "offset": 0}
            )

        assert response.status_code == 200, response.text
        body = response.json()
        data = body["data"]
        pagination = body["pagination"]

        assert len(data) <= 1, f"Expected at most 1 result with limit=1, got: {len(data)}"
        assert pagination["limit"] == 1
        assert pagination["offset"] == 0

    async def test_list_entities_pagination_offset_beyond_total_returns_empty(
        self,
        async_client: AsyncClient,
        seed_entity_data: dict[str, Any],
    ) -> None:
        """``offset`` beyond total returns empty data list; ``total`` still reflects real count."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                _list_entities_url(), params={"limit": 50, "offset": 100000}
            )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["data"] == [], (
            f"Expected empty data list with extreme offset, got: {body['data']}"
        )
        assert body["pagination"]["offset"] == 100000
        assert body["pagination"]["total"] >= 1
        assert body["pagination"]["has_more"] is False

    async def test_list_entities_pagination_has_more_true(
        self,
        async_client: AsyncClient,
        integration_session_factory: "async_sessionmaker[AsyncSession]",
        seed_entity_data: dict[str, Any],
    ) -> None:
        """``has_more`` is True when the total exceeds ``offset + limit``.

        Seeds a second active entity so there are at least 2, then queries
        with ``limit=1, offset=0``.  With 2+ entities, ``has_more`` must be True.
        Cleans up the temporary entity afterwards.
        """
        temp_entity_id = uuid.uuid4()
        async with integration_session_factory() as session:
            temp_entity = NamedEntityDB(
                id=temp_entity_id,
                canonical_name="Pagination Has More Test Entity",
                canonical_name_normalized="pagination has more test entity",
                entity_type="person",
                description=None,
            )
            session.add(temp_entity)
            await session.commit()

        try:
            with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
                mock_oauth.is_authenticated.return_value = True
                response = await async_client.get(
                    _list_entities_url(), params={"limit": 1, "offset": 0}
                )

            assert response.status_code == 200, response.text
            pagination = response.json()["pagination"]

            total = pagination["total"]
            assert total >= 2, "Expected at least 2 active entities after seeding temp entity"
            assert pagination["has_more"] is True, (
                f"Expected has_more=True with total={total}, limit=1, offset=0"
            )
        finally:
            async with integration_session_factory() as session:
                await session.execute(
                    delete(NamedEntityDB).where(NamedEntityDB.id == temp_entity_id)
                )
                await session.commit()

    async def test_list_entities_empty_result_set(
        self,
        async_client: AsyncClient,
        seed_entity_data: dict[str, Any],
    ) -> None:
        """Combination of ``type`` and ``search`` that matches nothing returns empty result.

        Uses ``type=organization`` combined with ``search=Elon Musk`` (which is typed
        as ``"person"``), expecting zero results.
        """
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                _list_entities_url(),
                params={"type": "organization", "search": "Elon Musk"},
            )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["data"] == [], (
            f"Expected empty data for type=organization+search=Elon Musk, got: {body['data']}"
        )
        assert body["pagination"]["total"] == 0
        assert body["pagination"]["has_more"] is False

    async def test_list_entities_401_unauthenticated(
        self,
        async_client: AsyncClient,
        seed_entity_data: dict[str, Any],
    ) -> None:
        """401 response when the client is not authenticated."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = False
            response = await async_client.get(_list_entities_url())

        assert response.status_code == 401, response.text


# ---------------------------------------------------------------------------
# T038 — GET /api/v1/entities/{entity_id}  (entity detail)
# ---------------------------------------------------------------------------


class TestGetEntityDetail:
    """Integration tests for GET /api/v1/entities/{entity_id}.

    The endpoint returns a single entity wrapped in a ``data`` envelope.
    It parses ``entity_id`` as a UUID; an invalid UUID string triggers a 404
    (not a 422), matching the same pattern used in ``get_entity_videos``.
    """

    async def test_get_entity_detail_200(
        self,
        async_client: AsyncClient,
        seed_entity_data: dict[str, Any],
    ) -> None:
        """200 response returns entity detail in the ``data`` envelope.

        Verifies all expected fields are present with correct values matching
        the seeded NamedEntity for ``"Elon Musk"``.
        """
        entity_id = seed_entity_data["entity_id"]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(_entity_detail_url(entity_id))

        assert response.status_code == 200, response.text
        body = response.json()

        assert "data" in body
        detail = body["data"]

        assert detail["entity_id"] == entity_id
        assert detail["canonical_name"] == "Elon Musk"
        assert detail["entity_type"] == "person"
        assert detail["description"] == "Entrepreneur and CEO of SpaceX and Tesla."
        assert detail["status"] == "active"
        assert isinstance(detail["mention_count"], int)
        assert detail["mention_count"] >= 0

    async def test_get_entity_detail_response_schema_fields(
        self,
        async_client: AsyncClient,
        seed_entity_data: dict[str, Any],
    ) -> None:
        """``data`` object contains exactly the required entity detail fields.

        Validates that ``entity_id`` is a parseable UUID, ``mention_count`` is a
        non-negative integer, and ``description`` may be None.  Also confirms
        ``video_count`` is NOT present (the detail endpoint omits it).
        """
        entity_id = seed_entity_data["entity_id"]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(_entity_detail_url(entity_id))

        assert response.status_code == 200, response.text
        detail = response.json()["data"]

        required_fields = {
            "entity_id",
            "canonical_name",
            "entity_type",
            "description",
            "status",
            "mention_count",
        }
        missing = required_fields - detail.keys()
        assert not missing, f"Missing fields in entity detail: {missing}"

        # entity_id must be a parseable UUID
        uuid.UUID(detail["entity_id"])
        assert isinstance(detail["canonical_name"], str)
        assert isinstance(detail["entity_type"], str)
        assert isinstance(detail["mention_count"], int)
        assert detail["mention_count"] >= 0

        # The detail endpoint does NOT include video_count (list endpoint only)
        assert "video_count" not in detail, (
            "entity detail endpoint must not expose video_count"
        )

    async def test_get_entity_detail_description_may_be_null(
        self,
        async_client: AsyncClient,
        integration_session_factory: "async_sessionmaker[AsyncSession]",
        seed_entity_data: dict[str, Any],
    ) -> None:
        """``description`` field is null when the entity has no description set.

        Creates a temporary entity with ``description=None``, queries its detail,
        verifies ``description`` is null in the JSON response, then removes it.
        """
        temp_entity_id = uuid.uuid4()
        async with integration_session_factory() as session:
            temp_entity = NamedEntityDB(
                id=temp_entity_id,
                canonical_name="No Description Entity Test",
                canonical_name_normalized="no description entity test",
                entity_type="place",
                description=None,
            )
            session.add(temp_entity)
            await session.commit()

        try:
            with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
                mock_oauth.is_authenticated.return_value = True
                response = await async_client.get(
                    _entity_detail_url(str(temp_entity_id))
                )

            assert response.status_code == 200, response.text
            detail = response.json()["data"]
            assert detail["description"] is None, (
                f"Expected description=null for entity with no description, "
                f"got: {detail['description']!r}"
            )
            assert detail["canonical_name"] == "No Description Entity Test"
            assert detail["status"] == "active"
        finally:
            async with integration_session_factory() as session:
                await session.execute(
                    delete(NamedEntityDB).where(NamedEntityDB.id == temp_entity_id)
                )
                await session.commit()

    async def test_get_entity_detail_404_non_existent_uuid(
        self,
        async_client: AsyncClient,
        seed_entity_data: dict[str, Any],
    ) -> None:
        """404 response when entity_id is a valid UUID that does not exist in the database."""
        non_existent_id = str(uuid.uuid4())

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(_entity_detail_url(non_existent_id))

        assert response.status_code == 404, response.text

    async def test_get_entity_detail_404_invalid_uuid_string(
        self,
        async_client: AsyncClient,
        seed_entity_data: dict[str, Any],
    ) -> None:
        """404 response when entity_id is not a valid UUID string.

        The router converts the ValueError from ``uuid.UUID()`` into a
        NotFoundError (404) rather than allowing FastAPI to raise 422.
        This mirrors the behaviour tested in ``TestGetEntityVideos``.
        """
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                _entity_detail_url("not-a-valid-uuid-string")
            )

        assert response.status_code == 404, response.text

    async def test_get_entity_detail_404_short_garbage_string(
        self,
        async_client: AsyncClient,
        seed_entity_data: dict[str, Any],
    ) -> None:
        """404 for a short non-UUID path segment (e.g. ``"abc"``).

        Confirms the invalid-UUID-to-404 conversion works for very short
        strings that could not be mistaken for any UUID format.
        """
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(_entity_detail_url("abc"))

        assert response.status_code == 404, response.text

    async def test_get_entity_detail_401_unauthenticated(
        self,
        async_client: AsyncClient,
        seed_entity_data: dict[str, Any],
    ) -> None:
        """401 response when the client is not authenticated."""
        entity_id = seed_entity_data["entity_id"]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = False
            response = await async_client.get(_entity_detail_url(entity_id))

        assert response.status_code == 401, response.text
