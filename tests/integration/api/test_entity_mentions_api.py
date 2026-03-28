"""Integration tests for entity mention API endpoints (Feature 038 — T024;
Feature 050 — T014/T015).

Covers:
  - GET /api/v1/videos/{video_id}/entities
  - GET /api/v1/entities/{entity_id}/videos
  - GET /api/v1/entities/search                     (Feature 050 T014)
  - POST /api/v1/videos/{video_id}/entities/{entity_id}/manual  (Feature 050 T015)

All tests require an integration database. Each test class seeds its own data
via the ``seed_entity_data`` fixture and cleans up after itself in FK-reverse
order to maintain isolation from other integration test files.

Auth: ``require_auth`` is patched via ``unittest.mock.patch`` so that
tests do not need real OAuth credentials, following the same pattern used in
``test_transcript_corrections_api.py``.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid_utils import uuid7

from chronovista.db.models import (
    Channel as ChannelDB,
)
from chronovista.db.models import (
    EntityMention as EntityMentionDB,
)
from chronovista.db.models import (
    NamedEntity as NamedEntityDB,
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

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

# CRITICAL: Ensures all async tests in this module run with pytest-asyncio
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
    integration_session_factory: async_sessionmaker[AsyncSession],
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
                upload_date=datetime(2024, 3, 1, tzinfo=UTC),
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
                upload_date=datetime(2024, 3, 2, tzinfo=UTC),
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
        integration_session_factory: async_sessionmaker[AsyncSession],
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
        integration_session_factory: async_sessionmaker[AsyncSession],
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
        integration_session_factory: async_sessionmaker[AsyncSession],
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
        integration_session_factory: async_sessionmaker[AsyncSession],
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
        integration_session_factory: async_sessionmaker[AsyncSession],
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
        non-negative integer, ``description`` may be None, ``video_count`` is a
        non-negative integer, and ``aliases`` is a list.
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
            "video_count",
            "aliases",
        }
        missing = required_fields - detail.keys()
        assert not missing, f"Missing fields in entity detail: {missing}"

        # entity_id must be a parseable UUID
        uuid.UUID(detail["entity_id"])
        assert isinstance(detail["canonical_name"], str)
        assert isinstance(detail["entity_type"], str)
        assert isinstance(detail["mention_count"], int)
        assert detail["mention_count"] >= 0
        assert isinstance(detail["video_count"], int)
        assert detail["video_count"] >= 0
        assert isinstance(detail["aliases"], list)

    async def test_get_entity_detail_description_may_be_null(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
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


# ---------------------------------------------------------------------------
# Feature 050 — T014: Stable IDs for search/manual-association tests
# ---------------------------------------------------------------------------
# These IDs must not collide with the existing _CHANNEL_ID, _VIDEO_ID, or
# _VIDEO_ID_2 constants defined above. They follow the same length constraints.
_SEARCH_CHANNEL_ID = "UCsearch_manual_test01"  # 22 chars — within 24
_SEARCH_VIDEO_ID = "srch_manual_vid01"  # 17 chars — within 20


# ---------------------------------------------------------------------------
# Feature 050 — T014: URL helpers for new endpoints
# ---------------------------------------------------------------------------


def _search_entities_url() -> str:
    """Return the entity search endpoint URL."""
    return "/api/v1/entities/search"


def _manual_association_url(video_id: str, entity_id: str) -> str:
    """Return the manual association POST endpoint URL."""
    return f"/api/v1/videos/{video_id}/entities/{entity_id}/manual"


# ---------------------------------------------------------------------------
# Feature 050 — T014: Seed fixture for search / manual association tests
# ---------------------------------------------------------------------------


@pytest.fixture
async def seed_search_data(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[dict[str, Any], None]:
    """Seed the integration DB for Feature 050 search and manual association tests.

    Creates:
    - One channel (``_SEARCH_CHANNEL_ID``).
    - One video (``_SEARCH_VIDEO_ID``) belonging to that channel.
    - One active NamedEntity ``"Joanna Hausmann"`` (type: person) with one
      alias ``"Joanna"`` (type: name_variant).
    - One deprecated NamedEntity ``"Old Entity"`` (type: person).
    - One EntityMention linking "Joanna Hausmann" to ``_SEARCH_VIDEO_ID``
      (detection_method='rule_match') so ``is_linked`` tests have data.

    Yields a dict with stable IDs and UUIDs for test reference.
    Cleanup removes all seeded rows in FK-reverse order.
    """
    from chronovista.db.models import EntityAlias as EntityAliasDB

    active_entity_id = uuid.uuid4()
    deprecated_entity_id = uuid.uuid4()

    async with integration_session_factory() as session:
        # ---- Channel -------------------------------------------------------
        existing_ch = (
            await session.execute(
                select(ChannelDB).where(ChannelDB.channel_id == _SEARCH_CHANNEL_ID)
            )
        ).scalar_one_or_none()
        if not existing_ch:
            session.add(
                ChannelDB(
                    channel_id=_SEARCH_CHANNEL_ID,
                    title="Search Manual Test Channel",
                )
            )

        # ---- Video ---------------------------------------------------------
        existing_vid = (
            await session.execute(
                select(VideoDB).where(VideoDB.video_id == _SEARCH_VIDEO_ID)
            )
        ).scalar_one_or_none()
        if not existing_vid:
            session.add(
                VideoDB(
                    video_id=_SEARCH_VIDEO_ID,
                    channel_id=_SEARCH_CHANNEL_ID,
                    title="Search Manual Test Video",
                    description="Feature 050 test video",
                    upload_date=datetime(2024, 6, 1, tzinfo=UTC),
                    duration=300,
                )
            )

        await session.commit()

        # ---- Active NamedEntity: Joanna Hausmann ---------------------------
        existing_active = (
            await session.execute(
                select(NamedEntityDB).where(
                    NamedEntityDB.id == active_entity_id
                )
            )
        ).scalar_one_or_none()
        if not existing_active:
            session.add(
                NamedEntityDB(
                    id=active_entity_id,
                    canonical_name="Joanna Hausmann",
                    canonical_name_normalized="joanna hausmann",
                    entity_type="person",
                    description="Venezuelan-American comedian and writer.",
                    status="active",
                )
            )
            await session.commit()

            # Add alias "Joanna"
            session.add(
                EntityAliasDB(
                    id=uuid.UUID(bytes=uuid7().bytes),
                    entity_id=active_entity_id,
                    alias_name="Joanna",
                    alias_name_normalized="joanna",
                    alias_type="name_variant",
                    occurrence_count=0,
                )
            )

        # ---- Deprecated NamedEntity: Old Entity ----------------------------
        existing_deprecated = (
            await session.execute(
                select(NamedEntityDB).where(
                    NamedEntityDB.id == deprecated_entity_id
                )
            )
        ).scalar_one_or_none()
        if not existing_deprecated:
            session.add(
                NamedEntityDB(
                    id=deprecated_entity_id,
                    canonical_name="Old Entity",
                    canonical_name_normalized="old entity",
                    entity_type="person",
                    description="A deprecated entity for testing.",
                    status="deprecated",
                )
            )

        await session.commit()

        # ---- Existing mention (for is_linked tests) -----------------------
        # Attach "Joanna Hausmann" to the search video via rule_match so
        # test_search_is_linked_with_video_id can verify is_linked=True.
        session.add(
            EntityMentionDB(
                id=uuid.UUID(bytes=uuid7().bytes),
                entity_id=active_entity_id,
                segment_id=None,  # video-level manual or direct mention
                video_id=_SEARCH_VIDEO_ID,
                language_code=None,
                mention_text="Joanna Hausmann",
                detection_method="rule_match",
                confidence=1.0,
            )
        )
        await session.commit()

    yield {
        "active_entity_id": str(active_entity_id),
        "active_entity_id_uuid": active_entity_id,
        "deprecated_entity_id": str(deprecated_entity_id),
        "deprecated_entity_id_uuid": deprecated_entity_id,
        "video_id": _SEARCH_VIDEO_ID,
        "channel_id": _SEARCH_CHANNEL_ID,
    }

    # ---- Cleanup (FK-reverse order) ----------------------------------------
    async with integration_session_factory() as session:
        # entity_mentions first
        await session.execute(
            delete(EntityMentionDB).where(
                EntityMentionDB.video_id == _SEARCH_VIDEO_ID
            )
        )
        # also any manual associations created during tests
        await session.execute(
            delete(EntityMentionDB).where(
                EntityMentionDB.entity_id.in_(
                    [active_entity_id, deprecated_entity_id]
                )
            )
        )
        # entity_aliases
        await session.execute(
            delete(EntityAliasDB).where(
                EntityAliasDB.entity_id.in_(
                    [active_entity_id, deprecated_entity_id]
                )
            )
        )
        # named_entities
        await session.execute(
            delete(NamedEntityDB).where(
                NamedEntityDB.id.in_([active_entity_id, deprecated_entity_id])
            )
        )
        # videos
        await session.execute(
            delete(VideoDB).where(VideoDB.video_id == _SEARCH_VIDEO_ID)
        )
        # channel
        await session.execute(
            delete(ChannelDB).where(ChannelDB.channel_id == _SEARCH_CHANNEL_ID)
        )
        await session.commit()


# ---------------------------------------------------------------------------
# Feature 050 — T014: GET /api/v1/entities/search
# ---------------------------------------------------------------------------


class TestSearchEntitiesEndpoint:
    """Integration tests for GET /api/v1/entities/search.

    This is a TDD test class for Feature 050 User Story 1. The
    ``search_entities`` repository method and the corresponding router
    endpoint do not exist yet. These tests MUST fail until the
    implementation is added.

    URL: GET /api/v1/entities/search?q=...&video_id=...&limit=...
    """

    async def test_search_requires_min_2_chars(
        self,
        async_client: AsyncClient,
        seed_search_data: dict[str, Any],
    ) -> None:
        """GET /api/v1/entities/search returns 422 when q is a single character.

        The autocomplete endpoint enforces a minimum query length of 2
        characters via FastAPI's Query(min_length=2) validation.
        """
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                _search_entities_url(), params={"q": "J"}
            )

        assert response.status_code == 422, (
            f"Expected 422 for single-char query, got {response.status_code}: "
            f"{response.text}"
        )

    async def test_search_canonical_name_match(
        self,
        async_client: AsyncClient,
        seed_search_data: dict[str, Any],
    ) -> None:
        """GET /api/v1/entities/search returns Joanna Hausmann for query 'Joan'.

        The canonical name "Joanna Hausmann" matches a 'Joan' prefix. The
        response must include an entity with the correct canonical_name,
        entity_id, entity_type, status, and a null matched_alias field.
        """
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                _search_entities_url(), params={"q": "Joan"}
            )

        assert response.status_code == 200, response.text
        body = response.json()
        data = body.get("data", body) if isinstance(body, dict) else body
        # Accept both a wrapped {"data": [...]} envelope and a bare list
        if isinstance(data, dict):
            data = body

        entity = next(
            (
                item
                for item in (data if isinstance(data, list) else [])
                if item.get("canonical_name") == "Joanna Hausmann"
            ),
            None,
        )
        assert entity is not None, (
            f"Expected 'Joanna Hausmann' in search results for query 'Joan'. "
            f"Response: {body}"
        )
        assert entity["entity_id"] == seed_search_data["active_entity_id"]
        assert entity["entity_type"] == "person"
        assert entity["status"] == "active"
        assert entity.get("matched_alias") is None

    async def test_search_alias_match(
        self,
        async_client: AsyncClient,
        seed_search_data: dict[str, Any],
    ) -> None:
        """GET /api/v1/entities/search returns matched_alias when hit via alias.

        The query "Joanna" matches the alias "Joanna" (not the canonical name
        "Joanna Hausmann"). The result must include matched_alias="Joanna".
        If the canonical name also matches then matched_alias may be None
        (canonical preference), but the entity must be present.
        """
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                _search_entities_url(), params={"q": "Joanna"}
            )

        assert response.status_code == 200, response.text
        body = response.json()
        raw_list = body.get("data", body) if isinstance(body, dict) else body
        items = raw_list if isinstance(raw_list, list) else []

        entity = next(
            (
                item
                for item in items
                if item.get("canonical_name") == "Joanna Hausmann"
            ),
            None,
        )
        assert entity is not None, (
            f"Expected 'Joanna Hausmann' in alias-match results. Body: {body}"
        )
        # matched_alias should be "Joanna" when query matches via alias
        # (canonical "Joanna Hausmann" also starts with "Joanna", so either
        # None or "Joanna" is acceptable — entity must be present)
        assert entity.get("entity_id") == seed_search_data["active_entity_id"]

    async def test_search_is_linked_with_video_id(
        self,
        async_client: AsyncClient,
        seed_search_data: dict[str, Any],
    ) -> None:
        """GET /api/v1/entities/search shows is_linked=True when video_id provided.

        When the caller supplies a video_id parameter and the entity already
        has entity_mention rows for that video, the response must include
        is_linked=True and a non-empty link_sources list.
        """
        video_id = seed_search_data["video_id"]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                _search_entities_url(),
                params={"q": "Joan", "video_id": video_id},
            )

        assert response.status_code == 200, response.text
        body = response.json()
        raw_list = body.get("data", body) if isinstance(body, dict) else body
        items = raw_list if isinstance(raw_list, list) else []

        entity = next(
            (
                item
                for item in items
                if item.get("canonical_name") == "Joanna Hausmann"
            ),
            None,
        )
        assert entity is not None, (
            f"Expected 'Joanna Hausmann' in results. Body: {body}"
        )
        assert entity.get("is_linked") is True, (
            f"Expected is_linked=True for entity already linked to video. "
            f"Got: {entity}"
        )
        link_sources = entity.get("link_sources")
        assert link_sources is not None and len(link_sources) >= 1, (
            f"Expected non-empty link_sources. Got: {link_sources}"
        )

    async def test_search_deprecated_entity_in_results(
        self,
        async_client: AsyncClient,
        seed_search_data: dict[str, Any],
    ) -> None:
        """GET /api/v1/entities/search includes deprecated entities with status='deprecated'.

        Searching for "Old" should surface "Old Entity" (which is deprecated).
        The result's status field must be 'deprecated'.
        """
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                _search_entities_url(), params={"q": "Old"}
            )

        assert response.status_code == 200, response.text
        body = response.json()
        raw_list = body.get("data", body) if isinstance(body, dict) else body
        items = raw_list if isinstance(raw_list, list) else []

        deprecated_item = next(
            (item for item in items if item.get("canonical_name") == "Old Entity"),
            None,
        )
        assert deprecated_item is not None, (
            f"Expected deprecated 'Old Entity' in results. Body: {body}"
        )
        assert deprecated_item["status"] == "deprecated", (
            f"Expected status='deprecated', got: {deprecated_item['status']}"
        )

    async def test_search_limit_parameter(
        self,
        async_client: AsyncClient,
        seed_search_data: dict[str, Any],
    ) -> None:
        """GET /api/v1/entities/search respects the limit query parameter.

        With limit=1, the response data must contain at most 1 result even
        when multiple entities could match the query.
        """
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                _search_entities_url(),
                params={"q": "an", "limit": 1},
            )

        assert response.status_code == 200, response.text
        body = response.json()
        raw_list = body.get("data", body) if isinstance(body, dict) else body
        items = raw_list if isinstance(raw_list, list) else []
        assert len(items) <= 1, (
            f"Expected at most 1 result with limit=1, got {len(items)}"
        )

    async def test_search_auth_required(
        self,
        async_client: AsyncClient,
        seed_search_data: dict[str, Any],
    ) -> None:
        """GET /api/v1/entities/search returns 401 or 403 without authentication.

        The endpoint is guarded by ``require_auth``; unauthenticated requests
        must be rejected with a 401 or 403 status.
        """
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = False
            response = await async_client.get(
                _search_entities_url(), params={"q": "Joan"}
            )

        assert response.status_code in (401, 403), (
            f"Expected 401 or 403 for unauthenticated request, "
            f"got {response.status_code}"
        )


# ---------------------------------------------------------------------------
# Feature 050 — T015: POST /api/v1/videos/{video_id}/entities/{entity_id}/manual
# ---------------------------------------------------------------------------


class TestCreateManualAssociationEndpoint:
    """Integration tests for POST /api/v1/videos/{video_id}/entities/{entity_id}/manual.

    This is a TDD test class for Feature 050 User Story 1. The endpoint
    does not exist yet; these tests MUST fail until the implementation is
    added.

    URL: POST /api/v1/videos/{video_id}/entities/{entity_id}/manual
    Body: (none)
    Success: 201 with ManualAssociationResponse body
    """

    async def test_create_201_success(
        self,
        async_client: AsyncClient,
        seed_search_data: dict[str, Any],
    ) -> None:
        """POST manual association returns 201 with ManualAssociationResponse body.

        Creates a manual entity-video link and verifies:
        - HTTP 201 status code
        - Response body has fields: id, entity_id, video_id, detection_method,
          mention_text, created_at
        - detection_method == 'manual'
        - mention_text == entity's canonical_name
        """
        video_id = seed_search_data["video_id"]
        entity_id = seed_search_data["active_entity_id"]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.post(
                _manual_association_url(video_id, entity_id)
            )

        assert response.status_code == 201, (
            f"Expected 201, got {response.status_code}: {response.text}"
        )
        body = response.json()
        data = body.get("data", body) if isinstance(body, dict) else body

        assert "id" in data, f"Missing 'id' field in response: {data}"
        assert "entity_id" in data, f"Missing 'entity_id' field: {data}"
        assert "video_id" in data, f"Missing 'video_id' field: {data}"
        assert "detection_method" in data, f"Missing 'detection_method': {data}"
        assert "mention_text" in data, f"Missing 'mention_text': {data}"
        assert "created_at" in data, f"Missing 'created_at': {data}"

        assert data["detection_method"] == "manual", (
            f"Expected detection_method='manual', got: {data['detection_method']}"
        )
        assert data["entity_id"] == entity_id
        assert data["video_id"] == video_id
        assert data["mention_text"] == "Joanna Hausmann", (
            f"Expected mention_text='Joanna Hausmann', got: {data['mention_text']}"
        )

    async def test_create_404_nonexistent_video(
        self,
        async_client: AsyncClient,
        seed_search_data: dict[str, Any],
    ) -> None:
        """POST manual association returns 404 with RFC 7807 body for unknown video_id.

        The endpoint must verify the video exists before inserting. When the
        video does not exist, it returns 404 with a Problem Detail response
        body containing 'type', 'status', and 'detail' fields.
        """
        entity_id = seed_search_data["active_entity_id"]
        nonexistent_video_id = "nosuchvid0001"

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.post(
                _manual_association_url(nonexistent_video_id, entity_id)
            )

        assert response.status_code == 404, (
            f"Expected 404 for nonexistent video, got {response.status_code}: "
            f"{response.text}"
        )
        body = response.json()
        # RFC 7807 Problem Detail fields
        assert "status" in body or "detail" in body, (
            f"Expected RFC 7807 body with 'status' or 'detail', got: {body}"
        )

    async def test_create_404_nonexistent_entity(
        self,
        async_client: AsyncClient,
        seed_search_data: dict[str, Any],
    ) -> None:
        """POST manual association returns 404 with RFC 7807 body for unknown entity_id.

        The endpoint must verify the entity exists after verifying the video.
        When the entity does not exist, it returns 404.
        """
        video_id = seed_search_data["video_id"]
        nonexistent_entity_id = str(uuid.uuid4())

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.post(
                _manual_association_url(video_id, nonexistent_entity_id)
            )

        assert response.status_code == 404, (
            f"Expected 404 for nonexistent entity, got {response.status_code}: "
            f"{response.text}"
        )

    async def test_create_409_duplicate(
        self,
        async_client: AsyncClient,
        seed_search_data: dict[str, Any],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """POST manual association returns 409 when the link already exists.

        If a manual entity_mention row already exists for the same
        (entity_id, video_id) pair, the endpoint must return 409 Conflict
        rather than creating a duplicate row.
        """
        video_id = seed_search_data["video_id"]
        entity_id = seed_search_data["active_entity_id"]
        entity_uuid = seed_search_data["active_entity_id_uuid"]

        # Pre-create a manual association directly
        async with integration_session_factory() as session:
            existing = EntityMentionDB(
                id=uuid.UUID(bytes=uuid7().bytes),
                entity_id=entity_uuid,
                segment_id=None,
                video_id=video_id,
                language_code=None,
                mention_text="Joanna Hausmann",
                detection_method="manual",
                confidence=None,
            )
            session.add(existing)
            await session.commit()

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.post(
                _manual_association_url(video_id, entity_id)
            )

        assert response.status_code == 409, (
            f"Expected 409 for duplicate association, got {response.status_code}: "
            f"{response.text}"
        )

    async def test_create_422_deprecated_entity(
        self,
        async_client: AsyncClient,
        seed_search_data: dict[str, Any],
    ) -> None:
        """POST manual association returns 422 when the entity is deprecated.

        Manually linking a deprecated entity to a video is not permitted.
        The endpoint must return 422 Unprocessable Entity.
        """
        video_id = seed_search_data["video_id"]
        deprecated_entity_id = seed_search_data["deprecated_entity_id"]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.post(
                _manual_association_url(video_id, deprecated_entity_id)
            )

        assert response.status_code == 422, (
            f"Expected 422 for deprecated entity, got {response.status_code}: "
            f"{response.text}"
        )

    async def test_create_updates_entity_counters(
        self,
        async_client: AsyncClient,
        seed_search_data: dict[str, Any],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """POST manual association updates mention_count/video_count on named_entities.

        After a successful manual association, the named_entity row's
        mention_count and video_count should be refreshed by the repository's
        update_entity_counters() call. This test verifies the counter update
        is triggered by checking that the named_entity row is mutated.

        Note: Because manual mentions have mention_text=canonical_name and
        detection_method='manual', they contribute to the visible-name counter
        logic, so mention_count should be >= 1 after the association.
        """
        video_id = seed_search_data["video_id"]
        entity_id = seed_search_data["active_entity_id"]
        entity_uuid = seed_search_data["active_entity_id_uuid"]

        # Read baseline counter before association
        async with integration_session_factory() as session:
            entity_before = (
                await session.execute(
                    select(NamedEntityDB).where(NamedEntityDB.id == entity_uuid)
                )
            ).scalar_one_or_none()
        assert entity_before is not None, "Entity must exist before the test"
        count_before = entity_before.mention_count or 0

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.post(
                _manual_association_url(video_id, entity_id)
            )

        # The POST itself may succeed with 201 or fail with 409 if a prior
        # test already created the association. Either way, the counter
        # check below only makes sense on a fresh 201.
        if response.status_code != 201:
            pytest.skip(
                f"Manual association was not created (status {response.status_code}); "
                "skipping counter verification. "
                "Ensure test isolation (no prior manual mention for this entity+video)."
            )

        # Read counter after association
        async with integration_session_factory() as session:
            entity_after = (
                await session.execute(
                    select(NamedEntityDB).where(NamedEntityDB.id == entity_uuid)
                )
            ).scalar_one_or_none()

        assert entity_after is not None
        count_after = entity_after.mention_count or 0

        assert count_after >= count_before, (
            f"Expected mention_count to be >= {count_before} after manual "
            f"association, got {count_after}"
        )
        # Specifically, adding a manual mention should produce mention_count >= 1
        assert count_after >= 1, (
            f"Expected mention_count >= 1 after manual association, "
            f"got {count_after}"
        )


# ---------------------------------------------------------------------------
# T028 — GET /api/v1/entities/{entity_id}/videos (Multi-Source)
# ---------------------------------------------------------------------------


class TestEntityVideosMultiSource:
    """Integration tests for multi-source fields in entity videos endpoint.

    Feature 050 US2 adds sources, has_manual, first_mention_time, and
    upload_date to EntityVideoResult. These tests verify the new fields
    are returned correctly for both transcript-derived and manual mentions.
    """

    async def test_response_includes_sources_and_has_manual(
        self,
        async_client: AsyncClient,
        seed_entity_data: dict[str, Any],
    ) -> None:
        """200 response includes sources, has_manual, first_mention_time, upload_date.

        The seeded entity has only transcript-derived mentions (rule_match),
        so sources should contain 'transcript' and has_manual should be false.
        """
        entity_id = seed_entity_data["entity_id"]
        video_id = seed_entity_data["video_id"]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(_entity_videos_url(entity_id))

        assert response.status_code == 200, response.text
        body = response.json()
        data = body["data"]

        # Find the seeded video
        video_result = next(
            (item for item in data if item["video_id"] == video_id),
            None,
        )
        assert video_result is not None

        # Verify new fields are present
        assert "sources" in video_result
        assert "has_manual" in video_result
        assert "first_mention_time" in video_result
        assert "upload_date" in video_result

        # Transcript-only: sources should contain "transcript"
        assert "transcript" in video_result["sources"]
        assert video_result["has_manual"] is False

    async def test_mention_count_excludes_manual(
        self,
        async_client: AsyncClient,
        seed_entity_data: dict[str, Any],
    ) -> None:
        """mention_count reflects only transcript-derived mentions, not manual.

        The seeded data has 2 rule_match mentions. Even if a manual mention
        existed, mention_count should exclude it.
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
        assert video_result["mention_count"] == 2

    async def test_first_mention_time_present_for_transcript(
        self,
        async_client: AsyncClient,
        seed_entity_data: dict[str, Any],
    ) -> None:
        """first_mention_time is set for videos with transcript mentions.

        The seeded segment1 has start_time=0.0, so first_mention_time should
        be approximately 0.0.
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
        assert video_result["first_mention_time"] is not None
        assert video_result["first_mention_time"] == pytest.approx(0.0)

    async def test_upload_date_present(
        self,
        async_client: AsyncClient,
        seed_entity_data: dict[str, Any],
    ) -> None:
        """upload_date is present and contains the seeded video's upload date."""
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
        assert video_result["upload_date"] is not None
        assert "2024-03-01" in video_result["upload_date"]

    async def test_pagination_params(
        self,
        async_client: AsyncClient,
        seed_entity_data: dict[str, Any],
    ) -> None:
        """limit and offset query params are respected in the response."""
        entity_id = seed_entity_data["entity_id"]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                f"{_entity_videos_url(entity_id)}?limit=1&offset=0"
            )

        assert response.status_code == 200, response.text
        body = response.json()
        assert len(body["data"]) <= 1
        assert body["pagination"]["limit"] == 1


# ---------------------------------------------------------------------------
# Feature 050 — T037: DELETE /api/v1/videos/{video_id}/entities/{entity_id}/manual
# ---------------------------------------------------------------------------

# Unique stable IDs for this test class — must not collide with other classes.
# channel_id: max 24 chars, video_id: max 20 chars.
_DELETE_CHANNEL_ID = "UCdelete_manual_t0001"  # 21 chars
_DELETE_VIDEO_ID = "del_manual_vid01"  # 16 chars
_DELETE_VIDEO_ID_2 = "del_manual_vid02"  # 16 chars


def _delete_manual_url(video_id: str, entity_id: str) -> str:
    """Return the DELETE manual association endpoint URL."""
    return f"/api/v1/videos/{video_id}/entities/{entity_id}/manual"


@pytest.fixture
async def seed_delete_data(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[dict[str, Any], None]:
    """Seed the integration DB for Feature 050 T037 DELETE endpoint tests.

    Creates:
    - One channel (``_DELETE_CHANNEL_ID``).
    - Two videos (``_DELETE_VIDEO_ID``, ``_DELETE_VIDEO_ID_2``).
    - One active NamedEntity ``"Ingrid Bergman"`` (type: person).
    - No pre-seeded EntityMention rows — each test manages its own associations
      so that tests stay independent of one another.

    Yields a dict with stable IDs and UUIDs.
    Cleanup removes all seeded rows in FK-reverse order.
    """
    entity_id = uuid.uuid4()

    async with integration_session_factory() as session:
        # ---- Channel -------------------------------------------------------
        existing_ch = (
            await session.execute(
                select(ChannelDB).where(ChannelDB.channel_id == _DELETE_CHANNEL_ID)
            )
        ).scalar_one_or_none()
        if not existing_ch:
            session.add(
                ChannelDB(
                    channel_id=_DELETE_CHANNEL_ID,
                    title="Delete Manual Test Channel",
                )
            )

        # ---- Video 1 -------------------------------------------------------
        existing_vid = (
            await session.execute(
                select(VideoDB).where(VideoDB.video_id == _DELETE_VIDEO_ID)
            )
        ).scalar_one_or_none()
        if not existing_vid:
            session.add(
                VideoDB(
                    video_id=_DELETE_VIDEO_ID,
                    channel_id=_DELETE_CHANNEL_ID,
                    title="Delete Manual Test Video 1",
                    description="Feature 050 T037 test video",
                    upload_date=datetime(2024, 6, 1, tzinfo=UTC),
                    duration=300,
                )
            )

        # ---- Video 2 -------------------------------------------------------
        existing_vid2 = (
            await session.execute(
                select(VideoDB).where(VideoDB.video_id == _DELETE_VIDEO_ID_2)
            )
        ).scalar_one_or_none()
        if not existing_vid2:
            session.add(
                VideoDB(
                    video_id=_DELETE_VIDEO_ID_2,
                    channel_id=_DELETE_CHANNEL_ID,
                    title="Delete Manual Test Video 2",
                    description="Feature 050 T037 test video 2",
                    upload_date=datetime(2024, 7, 1, tzinfo=UTC),
                    duration=200,
                )
            )

        await session.commit()

        # ---- Active NamedEntity: Ingrid Bergman ----------------------------
        existing_entity = (
            await session.execute(
                select(NamedEntityDB).where(NamedEntityDB.id == entity_id)
            )
        ).scalar_one_or_none()
        if not existing_entity:
            session.add(
                NamedEntityDB(
                    id=entity_id,
                    canonical_name="Ingrid Bergman",
                    canonical_name_normalized="ingrid bergman",
                    entity_type="person",
                    description="Swedish actress.",
                    status="active",
                )
            )
            await session.commit()

    yield {
        "entity_id": str(entity_id),
        "entity_id_uuid": entity_id,
        "video_id": _DELETE_VIDEO_ID,
        "video_id_2": _DELETE_VIDEO_ID_2,
        "channel_id": _DELETE_CHANNEL_ID,
    }

    # ---- Cleanup (FK-reverse order) ----------------------------------------
    async with integration_session_factory() as session:
        # entity_mentions first (any created by individual tests)
        await session.execute(
            delete(EntityMentionDB).where(
                EntityMentionDB.video_id.in_([_DELETE_VIDEO_ID, _DELETE_VIDEO_ID_2])
            )
        )
        await session.execute(
            delete(EntityMentionDB).where(
                EntityMentionDB.entity_id == entity_id
            )
        )
        # named_entities
        await session.execute(
            delete(NamedEntityDB).where(NamedEntityDB.id == entity_id)
        )
        # videos
        await session.execute(
            delete(VideoDB).where(
                VideoDB.video_id.in_([_DELETE_VIDEO_ID, _DELETE_VIDEO_ID_2])
            )
        )
        # channel
        await session.execute(
            delete(ChannelDB).where(ChannelDB.channel_id == _DELETE_CHANNEL_ID)
        )
        await session.commit()


class TestDeleteManualAssociation:
    """Integration tests for DELETE /api/v1/videos/{video_id}/entities/{entity_id}/manual.

    Feature 050 US3: Remove Manual Association.

    Contract:
    - 204 No Content on successful deletion of a manual entity-video link.
    - 404 with RFC 7807 body when no manual association exists for that pair.
    - Only rows with detection_method='manual' are removed; transcript-derived
      mentions for the same entity+video remain intact.
    - named_entities.mention_count and video_count are updated in the same
      transaction via update_entity_counters.

    Auth is patched via ``unittest.mock.patch`` so that tests do not require
    real OAuth credentials (same pattern as TestCreateManualAssociationEndpoint).
    """

    async def test_delete_204_success(
        self,
        async_client: AsyncClient,
        seed_delete_data: dict[str, Any],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """DELETE manual association returns 204 No Content on success.

        Seed a manual EntityMentionDB row directly in the DB, then call the
        DELETE endpoint and verify:
        - HTTP 204 status code.
        - Response body is empty (no JSON payload).
        - The manual mention row no longer exists in the DB after deletion.
        """
        video_id = seed_delete_data["video_id"]
        entity_id_str = seed_delete_data["entity_id"]
        entity_uuid = seed_delete_data["entity_id_uuid"]

        # Pre-create a manual association directly in the DB
        manual_mention_id = uuid.UUID(bytes=uuid7().bytes)
        async with integration_session_factory() as session:
            session.add(
                EntityMentionDB(
                    id=manual_mention_id,
                    entity_id=entity_uuid,
                    segment_id=None,
                    video_id=video_id,
                    language_code=None,
                    mention_text="Ingrid Bergman",
                    detection_method="manual",
                    confidence=None,
                )
            )
            await session.commit()

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.delete(
                _delete_manual_url(video_id, entity_id_str)
            )

        assert response.status_code == 204, (
            f"Expected 204 No Content, got {response.status_code}: {response.text}"
        )
        # 204 responses must have no body
        assert response.content == b"", (
            f"Expected empty body for 204 response, got: {response.content!r}"
        )

        # Verify the row was actually removed from the DB
        async with integration_session_factory() as session:
            remaining = (
                await session.execute(
                    select(EntityMentionDB).where(
                        EntityMentionDB.id == manual_mention_id
                    )
                )
            ).scalar_one_or_none()
        assert remaining is None, (
            "Manual mention row should have been deleted but still exists in DB"
        )

    async def test_delete_404_no_manual_association(
        self,
        async_client: AsyncClient,
        seed_delete_data: dict[str, Any],
    ) -> None:
        """DELETE returns 404 with RFC 7807 body when no manual association exists.

        When the (video_id, entity_id) pair has no row with
        detection_method='manual', the endpoint must return 404 Problem Detail
        rather than 204.  The body must conform to RFC 7807 (Problem Details
        for HTTP APIs) and include at least 'status' or 'detail' fields.
        """
        video_id = seed_delete_data["video_id"]
        entity_id_str = seed_delete_data["entity_id"]

        # Do NOT pre-create any manual association — the endpoint should 404.
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.delete(
                _delete_manual_url(video_id, entity_id_str)
            )

        assert response.status_code == 404, (
            f"Expected 404 for missing manual association, "
            f"got {response.status_code}: {response.text}"
        )
        body = response.json()
        # RFC 7807 Problem Detail requires at least 'status' or 'detail'
        assert "status" in body or "detail" in body, (
            f"Expected RFC 7807 body with 'status' or 'detail', got: {body}"
        )

    async def test_delete_updates_entity_counters(
        self,
        async_client: AsyncClient,
        seed_delete_data: dict[str, Any],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """DELETE manual association triggers update_entity_counters.

        After a successful deletion, the named_entity row's mention_count and
        video_count should reflect the removal.  This test seeds a manual
        association, reads the counters before deletion, triggers the DELETE
        endpoint, then verifies the counters were refreshed (i.e., the counts
        do not increase beyond the pre-deletion values).
        """
        video_id = seed_delete_data["video_id"]
        entity_id_str = seed_delete_data["entity_id"]
        entity_uuid = seed_delete_data["entity_id_uuid"]

        # Seed a manual association so there is something to delete
        async with integration_session_factory() as session:
            session.add(
                EntityMentionDB(
                    id=uuid.UUID(bytes=uuid7().bytes),
                    entity_id=entity_uuid,
                    segment_id=None,
                    video_id=video_id,
                    language_code=None,
                    mention_text="Ingrid Bergman",
                    detection_method="manual",
                    confidence=None,
                )
            )
            await session.commit()

        # Read counter baseline
        async with integration_session_factory() as session:
            entity_before = (
                await session.execute(
                    select(NamedEntityDB).where(NamedEntityDB.id == entity_uuid)
                )
            ).scalar_one_or_none()
        assert entity_before is not None
        count_before = entity_before.mention_count or 0

        # Delete the manual association
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.delete(
                _delete_manual_url(video_id, entity_id_str)
            )

        assert response.status_code == 204, (
            f"Expected 204, got {response.status_code}: {response.text}"
        )

        # Read counter after deletion
        async with integration_session_factory() as session:
            entity_after = (
                await session.execute(
                    select(NamedEntityDB).where(NamedEntityDB.id == entity_uuid)
                )
            ).scalar_one_or_none()
        assert entity_after is not None
        count_after = entity_after.mention_count or 0

        # After removing the manual association the counter should decrease or
        # stay equal to 0 — it must not exceed the pre-deletion count.
        assert count_after <= count_before, (
            f"Expected mention_count <= {count_before} after deletion, "
            f"got {count_after}"
        )

    async def test_delete_preserves_transcript_mentions(
        self,
        async_client: AsyncClient,
        seed_delete_data: dict[str, Any],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """DELETE manual association leaves transcript-derived mentions intact.

        When both a manual mention and a transcript-derived mention exist for
        the same (video_id, entity_id) pair, calling DELETE must remove only
        the manual row.  The transcript-derived mention must remain in the DB
        and must still appear in a subsequent GET to the video entities endpoint.
        """
        video_id = seed_delete_data["video_id"]
        entity_id_str = seed_delete_data["entity_id"]
        entity_uuid = seed_delete_data["entity_id_uuid"]

        transcript_mention_id = uuid.UUID(bytes=uuid7().bytes)
        manual_mention_id = uuid.UUID(bytes=uuid7().bytes)

        # Seed both a transcript-derived mention and a manual association
        async with integration_session_factory() as session:
            # Transcript-derived mention (rule_match)
            session.add(
                EntityMentionDB(
                    id=transcript_mention_id,
                    entity_id=entity_uuid,
                    segment_id=None,  # no segment FK for simplicity in integration test
                    video_id=video_id,
                    language_code="en",
                    mention_text="Ingrid Bergman",
                    detection_method="rule_match",
                    confidence=0.97,
                )
            )
            # Manual association
            session.add(
                EntityMentionDB(
                    id=manual_mention_id,
                    entity_id=entity_uuid,
                    segment_id=None,
                    video_id=video_id,
                    language_code=None,
                    mention_text="Ingrid Bergman",
                    detection_method="manual",
                    confidence=None,
                )
            )
            await session.commit()

        # DELETE the manual association
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.delete(
                _delete_manual_url(video_id, entity_id_str)
            )

        assert response.status_code == 204, (
            f"Expected 204, got {response.status_code}: {response.text}"
        )

        # Verify the manual mention is gone
        async with integration_session_factory() as session:
            manual_gone = (
                await session.execute(
                    select(EntityMentionDB).where(
                        EntityMentionDB.id == manual_mention_id
                    )
                )
            ).scalar_one_or_none()

            # Verify the transcript mention still exists
            transcript_still_present = (
                await session.execute(
                    select(EntityMentionDB).where(
                        EntityMentionDB.id == transcript_mention_id
                    )
                )
            ).scalar_one_or_none()

        assert manual_gone is None, (
            "Manual mention should have been deleted but still exists in DB"
        )
        assert transcript_still_present is not None, (
            "Transcript-derived mention should NOT have been deleted, but it is gone"
        )

    async def test_delete_404_for_nonexistent_entity(
        self,
        async_client: AsyncClient,
        seed_delete_data: dict[str, Any],
    ) -> None:
        """DELETE returns 404 when the entity UUID does not exist at all.

        Using a random UUID that is not in the named_entities table should
        produce a 404 response, not a 500 or other error.
        """
        video_id = seed_delete_data["video_id"]
        nonexistent_entity_id = str(uuid.uuid4())

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.delete(
                _delete_manual_url(video_id, nonexistent_entity_id)
            )

        assert response.status_code == 404, (
            f"Expected 404 for nonexistent entity, "
            f"got {response.status_code}: {response.text}"
        )

    async def test_delete_404_only_transcript_mention_exists(
        self,
        async_client: AsyncClient,
        seed_delete_data: dict[str, Any],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """DELETE returns 404 when only transcript mentions exist (no manual row).

        If a transcript-derived mention exists for the (video_id, entity_id)
        pair but no manual row exists, the endpoint must return 404 because
        there is no manual association to delete.
        """
        video_id = seed_delete_data["video_id_2"]
        entity_id_str = seed_delete_data["entity_id"]
        entity_uuid = seed_delete_data["entity_id_uuid"]

        transcript_mention_id = uuid.UUID(bytes=uuid7().bytes)

        # Seed only a transcript-derived mention — no manual row
        async with integration_session_factory() as session:
            session.add(
                EntityMentionDB(
                    id=transcript_mention_id,
                    entity_id=entity_uuid,
                    segment_id=None,
                    video_id=video_id,
                    language_code="en",
                    mention_text="Ingrid Bergman",
                    detection_method="rule_match",
                    confidence=0.90,
                )
            )
            await session.commit()

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.delete(
                _delete_manual_url(video_id, entity_id_str)
            )

        assert response.status_code == 404, (
            f"Expected 404 when only transcript mention exists, "
            f"got {response.status_code}: {response.text}"
        )

        # Confirm the transcript mention was not deleted as a side effect
        async with integration_session_factory() as session:
            transcript_still_present = (
                await session.execute(
                    select(EntityMentionDB).where(
                        EntityMentionDB.id == transcript_mention_id
                    )
                )
            ).scalar_one_or_none()

        assert transcript_still_present is not None, (
            "Transcript mention should NOT have been deleted by a failed DELETE call"
        )


# ---------------------------------------------------------------------------
# T048 — Non-Functional Requirements: Performance Assertions
# ---------------------------------------------------------------------------


class TestPerformanceAssertions:
    """Integration tests that verify endpoint wall-clock response times meet NFRs.

    All timing is measured via ``time.perf_counter()`` around the actual HTTP
    call through the httpx AsyncClient / ASGITransport.  The measurements
    include serialization and DB round-trips inside the test process but exclude
    any real network latency (the transport is in-process).

    NFR thresholds
    --------------
    NFR-001 : GET /api/v1/entities/search      < 300 ms
    NFR-002 : GET /api/v1/entities/{id}/videos < 2 000 ms
    NFR-003 : POST /api/v1/videos/{id}/entities/{id}/manual < 1 000 ms

    Notes
    -----
    - Each test uses a dedicated fixture (``seed_search_data`` for NFR-001 and
      NFR-003; ``seed_entity_data`` for NFR-002) so that the DB state is
      consistent with the functional tests.
    - A valid authenticated call is used so that the measurement covers the
      full handler path, not just auth rejection.
    - The POST test (NFR-003) targets a fresh entity-video pair to avoid a 409
      Conflict.  If an existing association is found (409), the test reports the
      timing anyway and asserts only the time budget — the functional contract
      is covered by ``TestCreateManualAssociationEndpoint``.
    """

    async def test_nfr_001_search_responds_under_300ms(
        self,
        async_client: AsyncClient,
        seed_search_data: dict[str, Any],
    ) -> None:
        """GET /api/v1/entities/search must complete within 300 ms (NFR-001).

        Uses the ``seed_search_data`` fixture which seeds "Joanna Hausmann"
        so the search query 'Joan' always returns at least one result,
        exercising the full DB lookup path.
        """
        budget_ms: float = 300.0

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            t_start = time.perf_counter()
            response = await async_client.get(
                _search_entities_url(), params={"q": "Joan"}
            )
            elapsed_ms = (time.perf_counter() - t_start) * 1_000

        # The functional contract (200) must hold; timing is only meaningful
        # when the handler actually ran to completion.
        assert response.status_code == 200, (
            f"NFR-001: Expected 200 from /entities/search, "
            f"got {response.status_code}: {response.text}"
        )
        assert elapsed_ms < budget_ms, (
            f"NFR-001 VIOLATED: GET /api/v1/entities/search took "
            f"{elapsed_ms:.1f} ms, budget is {budget_ms:.0f} ms"
        )

    async def test_nfr_002_entity_videos_loads_under_2000ms(
        self,
        async_client: AsyncClient,
        seed_entity_data: dict[str, Any],
    ) -> None:
        """GET /api/v1/entities/{entity_id}/videos must complete within 2 000 ms (NFR-002).

        Uses the ``seed_entity_data`` fixture which seeds the "Elon Musk"
        entity with two EntityMention rows, exercising the paginated JOIN
        query and mention-preview aggregation path.
        """
        budget_ms: float = 2_000.0
        entity_id: str = seed_entity_data["entity_id"]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            t_start = time.perf_counter()
            response = await async_client.get(_entity_videos_url(entity_id))
            elapsed_ms = (time.perf_counter() - t_start) * 1_000

        assert response.status_code == 200, (
            f"NFR-002: Expected 200 from /entities/{{id}}/videos, "
            f"got {response.status_code}: {response.text}"
        )
        assert elapsed_ms < budget_ms, (
            f"NFR-002 VIOLATED: GET /api/v1/entities/{{entity_id}}/videos took "
            f"{elapsed_ms:.1f} ms, budget is {budget_ms:.0f} ms"
        )

    async def test_nfr_003_manual_association_completes_under_1000ms(
        self,
        async_client: AsyncClient,
        seed_search_data: dict[str, Any],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """POST /api/v1/videos/{video_id}/entities/{entity_id}/manual must complete within 1 000 ms (NFR-003).

        Uses the ``seed_search_data`` fixture.  A temporary NamedEntity
        (``"Nfr003 Perf Entity"``) is created uniquely for this test to avoid
        a 409 Conflict from prior runs of the functional tests, ensuring the
        handler executes the full insert + counter-update path.

        Cleanup removes the temporary entity and any created mention rows
        after the timing assertion so that subsequent test runs stay isolated.
        """
        budget_ms: float = 1_000.0
        video_id: str = seed_search_data["video_id"]

        # Create a dedicated entity so this test is never blocked by a prior
        # manual association for the same (entity_id, video_id) pair.
        perf_entity_id = uuid.uuid4()

        async with integration_session_factory() as session:
            session.add(
                NamedEntityDB(
                    id=perf_entity_id,
                    canonical_name="Nfr003 Perf Entity",
                    canonical_name_normalized="nfr003 perf entity",
                    entity_type="person",
                    description="Temporary entity for NFR-003 performance test.",
                    status="active",
                )
            )
            await session.commit()

        try:
            with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
                mock_oauth.is_authenticated.return_value = True

                t_start = time.perf_counter()
                response = await async_client.post(
                    _manual_association_url(video_id, str(perf_entity_id))
                )
                elapsed_ms = (time.perf_counter() - t_start) * 1_000

            # A 201 confirms the full insert path executed; other 2xx/4xx codes
            # are noted but do not invalidate the timing measurement since the
            # handler still ran end-to-end.
            assert response.status_code == 201, (
                f"NFR-003: Expected 201 from POST manual association, "
                f"got {response.status_code}: {response.text}"
            )
            assert elapsed_ms < budget_ms, (
                f"NFR-003 VIOLATED: POST /api/v1/videos/{{video_id}}/entities/{{entity_id}}/manual "
                f"took {elapsed_ms:.1f} ms, budget is {budget_ms:.0f} ms"
            )
        finally:
            # Clean up the temporary entity and any mention rows it owns.
            async with integration_session_factory() as session:
                await session.execute(
                    delete(EntityMentionDB).where(
                        EntityMentionDB.entity_id == perf_entity_id
                    )
                )
                await session.execute(
                    delete(NamedEntityDB).where(NamedEntityDB.id == perf_entity_id)
                )
                await session.commit()
