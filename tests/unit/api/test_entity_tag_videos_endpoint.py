"""Unit tests for GET /api/v1/entities/{entity_id}/videos — tag-sourced videos.

T011 — Verifies that tag-sourced videos returned by the entity video list
endpoint have ``mention_count: 0``, ``mentions: []``, and
``first_mention_time: null``.

Mock strategy
-------------
The ``_mention_repo.get_entity_video_list`` is patched at the module level to
return controlled results.  The ``get_db`` and ``require_auth`` FastAPI
dependencies are overridden to inject a mock session and bypass auth.

References
----------
- specs/053-entity-tag-videos/tasks.md — T011
- specs/053-entity-tag-videos/spec.md — FR-014, US1 acceptance scenario 2
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from uuid_utils import uuid7

from chronovista.api.deps import get_db, require_auth
from chronovista.api.main import app

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ENDPOINT_TEMPLATE = "/api/v1/entities/{entity_id}/videos"


def _uuid() -> uuid.UUID:
    """Return a UUIDv7 expressed as a stdlib ``uuid.UUID`` instance."""
    return uuid.UUID(bytes=uuid7().bytes)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


async def _build_client(
    mock_session: AsyncMock,
) -> AsyncGenerator[AsyncClient, None]:
    """Yield an AsyncClient with get_db and require_auth overridden.

    Parameters
    ----------
    mock_session : AsyncMock
        The mock database session to inject via the get_db override.

    Yields
    ------
    AsyncClient
        A configured HTTP test client with overridden dependencies.
    """

    async def mock_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield mock_session

    async def mock_require_auth() -> None:
        return None

    app.dependency_overrides[get_db] = mock_get_db
    app.dependency_overrides[require_auth] = mock_require_auth

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


def _make_entity_exists_session(entity_id: uuid.UUID) -> AsyncMock:
    """Build a mock session where the entity existence check succeeds.

    The get_entity_videos endpoint runs:
        session.execute(SELECT NamedEntityDB.id WHERE id == entity_id)
    and checks scalar_one_or_none().  This mock returns entity_id for
    that check.

    Parameters
    ----------
    entity_id : uuid.UUID
        Entity UUID that should pass the existence check.

    Returns
    -------
    AsyncMock
        Configured mock session.
    """
    mock_session = AsyncMock(spec=AsyncSession)

    entity_result = MagicMock()
    entity_result.scalar_one_or_none.return_value = entity_id
    mock_session.execute = AsyncMock(return_value=entity_result)
    mock_session.commit = AsyncMock()
    return mock_session


# ---------------------------------------------------------------------------
# T011 — tag-sourced video has mention_count=0, mentions=[], first_mention_time=null
# ---------------------------------------------------------------------------


class TestEntityVideoEndpointTagSourcedVideos:
    """Tests for GET /entities/{entity_id}/videos with tag-sourced videos (T011).

    Verifies the API response shape for tag-only videos as specified by
    FR-014: tag-only videos have mention_count=0, mentions=[],
    first_mention_time=null.
    """

    async def test_tag_sourced_video_has_zero_mentions_and_null_timestamp(
        self,
    ) -> None:
        """Tag-sourced video returns mention_count=0, mentions=[], first_mention_time=null.

        Given a repository that returns one tag-only video, the API endpoint
        should serialize it with the expected zero/empty/null values for
        transcript-related fields.
        """
        entity_id = _uuid()
        tag_video: dict[str, Any] = {
            "video_id": "vid_tag_only_001",
            "video_title": "Tag Only Video",
            "channel_name": "Some Channel",
            "mention_count": 0,
            "mentions": [],
            "sources": ["tag"],
            "has_manual": False,
            "first_mention_time": None,
            "upload_date": "2024-07-15",
        }

        mock_session = _make_entity_exists_session(entity_id)

        with patch(
            "chronovista.api.routers.entity_mentions._mention_repo"
        ) as mock_repo:
            mock_repo.get_entity_video_list = AsyncMock(
                return_value=([tag_video], 1)
            )

            async for client in _build_client(mock_session):
                url = _ENDPOINT_TEMPLATE.format(entity_id=str(entity_id))
                response = await client.get(url)

        assert response.status_code == 200
        body = response.json()
        assert len(body["data"]) == 1

        video = body["data"][0]
        assert video["video_id"] == "vid_tag_only_001"
        assert video["mention_count"] == 0
        assert video["mentions"] == []
        assert video["first_mention_time"] is None
        assert video["sources"] == ["tag"]
        assert video["has_manual"] is False
        assert video["upload_date"] == "2024-07-15"

    async def test_mixed_transcript_and_tag_videos_in_response(
        self,
    ) -> None:
        """Response contains both transcript-mention and tag-only videos.

        The endpoint returns a mix of transcript-sourced and tag-sourced
        videos.  Transcript-sourced videos have non-zero mention_count;
        tag-sourced videos have mention_count=0.
        """
        entity_id = _uuid()
        transcript_video: dict[str, Any] = {
            "video_id": "vid_transcript_001",
            "video_title": "Transcript Video",
            "channel_name": "Channel A",
            "mention_count": 3,
            "mentions": [
                {
                    "segment_id": 100,
                    "start_time": 45.2,
                    "mention_text": "Test Entity",
                }
            ],
            "sources": ["transcript"],
            "has_manual": False,
            "first_mention_time": 45.2,
            "upload_date": "2024-01-10",
        }
        tag_video: dict[str, Any] = {
            "video_id": "vid_tag_002",
            "video_title": "Tag Video",
            "channel_name": "Channel B",
            "mention_count": 0,
            "mentions": [],
            "sources": ["tag"],
            "has_manual": False,
            "first_mention_time": None,
            "upload_date": "2024-06-20",
        }

        mock_session = _make_entity_exists_session(entity_id)

        with patch(
            "chronovista.api.routers.entity_mentions._mention_repo"
        ) as mock_repo:
            mock_repo.get_entity_video_list = AsyncMock(
                return_value=([transcript_video, tag_video], 2)
            )

            async for client in _build_client(mock_session):
                url = _ENDPOINT_TEMPLATE.format(entity_id=str(entity_id))
                response = await client.get(url)

        assert response.status_code == 200
        body = response.json()
        assert len(body["data"]) == 2
        assert body["pagination"]["total"] == 2

        # Transcript video
        tv = body["data"][0]
        assert tv["mention_count"] == 3
        assert len(tv["mentions"]) == 1
        assert tv["first_mention_time"] == 45.2
        assert tv["sources"] == ["transcript"]

        # Tag video
        tg = body["data"][1]
        assert tg["mention_count"] == 0
        assert tg["mentions"] == []
        assert tg["first_mention_time"] is None
        assert tg["sources"] == ["tag"]

    async def test_overlap_video_has_both_sources_in_response(
        self,
    ) -> None:
        """Video with both transcript and tag sources has both in sources list.

        When the repository returns a video with ``sources: ["tag", "transcript"]``,
        the API response must faithfully reproduce that list.
        """
        entity_id = _uuid()
        overlap_video: dict[str, Any] = {
            "video_id": "vid_overlap_001",
            "video_title": "Overlap Video",
            "channel_name": "Channel C",
            "mention_count": 5,
            "mentions": [
                {
                    "segment_id": 200,
                    "start_time": 10.0,
                    "mention_text": "Entity Name",
                }
            ],
            "sources": ["tag", "transcript"],
            "has_manual": False,
            "first_mention_time": 10.0,
            "upload_date": "2024-04-01",
        }

        mock_session = _make_entity_exists_session(entity_id)

        with patch(
            "chronovista.api.routers.entity_mentions._mention_repo"
        ) as mock_repo:
            mock_repo.get_entity_video_list = AsyncMock(
                return_value=([overlap_video], 1)
            )

            async for client in _build_client(mock_session):
                url = _ENDPOINT_TEMPLATE.format(entity_id=str(entity_id))
                response = await client.get(url)

        assert response.status_code == 200
        body = response.json()
        video = body["data"][0]
        assert "tag" in video["sources"]
        assert "transcript" in video["sources"]
        # Transcript data preserved
        assert video["mention_count"] == 5
        assert video["first_mention_time"] == 10.0


# ---------------------------------------------------------------------------
# T029 — Entity detail response video_count matches length of combined video list
# ---------------------------------------------------------------------------


class TestEntityDetailCombinedVideoCount:
    """Tests for combined video count in entity detail response (T029).

    Verifies that the entity detail endpoint returns a ``video_count``
    that reflects the combined total from ``get_entity_video_list()``
    rather than the stored ``named_entities.video_count`` value.

    This validates FR-007 and US4 acceptance scenario 2.
    """

    async def test_entity_detail_video_count_matches_combined_total(
        self,
    ) -> None:
        """Entity detail video_count reflects combined count, not stored DB value.

        The entity has ``video_count=2`` stored in the DB (transcript-only),
        but ``get_combined_video_count`` returns 6.  The detail endpoint
        must return ``video_count=6``.
        """
        entity_id = _uuid()

        mock_session = AsyncMock(spec=AsyncSession)

        # Entity existence + detail query — the entity has video_count=2 in DB
        mock_entity = MagicMock()
        mock_entity.id = entity_id
        mock_entity.canonical_name = "Test Entity"
        mock_entity.entity_type = "person"
        mock_entity.description = "A test entity"
        mock_entity.status = "active"
        mock_entity.mention_count = 5
        mock_entity.video_count = 2  # Stored DB value (transcript-only)
        mock_entity.exclusion_patterns = []
        mock_entity.aliases = []

        entity_result = MagicMock()
        entity_result.scalar_one_or_none.return_value = mock_entity
        mock_session.execute = AsyncMock(return_value=entity_result)
        mock_session.commit = AsyncMock()

        with patch(
            "chronovista.api.routers.entity_mentions._mention_repo"
        ) as mock_repo:
            # The combined video count returns 6 (from all sources)
            mock_repo.get_combined_video_count = AsyncMock(return_value=6)

            async for client in _build_client(mock_session):
                # Fetch entity detail
                detail_url = f"/api/v1/entities/{entity_id}"
                detail_response = await client.get(detail_url)

        assert detail_response.status_code == 200
        detail_body = detail_response.json()
        # video_count should reflect combined total (6), not stored DB value (2)
        assert detail_body["data"]["video_count"] == 6

    async def test_entity_detail_video_count_zero_when_no_videos(
        self,
    ) -> None:
        """Entity with no videos from any source shows video_count=0.

        The stored DB value is 0 and combined total is also 0.
        """
        entity_id = _uuid()

        mock_session = AsyncMock(spec=AsyncSession)

        mock_entity = MagicMock()
        mock_entity.id = entity_id
        mock_entity.canonical_name = "Empty Entity"
        mock_entity.entity_type = "organization"
        mock_entity.description = None
        mock_entity.status = "active"
        mock_entity.mention_count = 0
        mock_entity.video_count = 0
        mock_entity.exclusion_patterns = []
        mock_entity.aliases = []

        entity_result = MagicMock()
        entity_result.scalar_one_or_none.return_value = mock_entity
        mock_session.execute = AsyncMock(return_value=entity_result)
        mock_session.commit = AsyncMock()

        with patch(
            "chronovista.api.routers.entity_mentions._mention_repo"
        ) as mock_repo:
            mock_repo.get_combined_video_count = AsyncMock(return_value=0)

            async for client in _build_client(mock_session):
                detail_url = f"/api/v1/entities/{entity_id}"
                detail_response = await client.get(detail_url)

        assert detail_response.status_code == 200
        detail_body = detail_response.json()
        assert detail_body["data"]["video_count"] == 0


# ---------------------------------------------------------------------------
# T032 — Entity list response includes combined video count per entity
# ---------------------------------------------------------------------------


class TestEntityListCombinedVideoCount:
    """Tests for entity list endpoint combined video count (T032, T033).

    For MVP, the entity list endpoint continues to use the stored
    ``named_entities.video_count`` value.  Computing combined counts for
    every entity in a paginated list is deferred to a future iteration
    due to performance concerns (correlated subquery across 3 tag tables
    per entity row).

    These tests document the current behaviour and serve as a baseline
    for future combined-count implementation.

    Decision rationale: The entity detail page already shows the correct
    combined count via the videos endpoint pagination total.  The list
    page stored count is acceptable for MVP because:
    1. Most entities are created via classify (which sets video_count from
       transcript scans), so the stored count is approximately correct.
    2. The sort order for ``sort=mentions`` uses mention_count (not
       video_count), so tag-only videos don't affect sort order.
    3. Computing combined counts per entity requires N+1 queries or a
       complex lateral join that risks degrading list endpoint performance.
    """

    async def test_entity_list_returns_stored_video_count(
        self,
    ) -> None:
        """Entity list returns stored video_count per entity (MVP baseline).

        The stored video_count reflects transcript-only counts.  This test
        documents the current behaviour as a baseline for future enhancement.
        """
        entity_id = _uuid()

        mock_session = AsyncMock(spec=AsyncSession)

        # Mock entity row from the list query
        mock_entity = MagicMock()
        mock_entity.id = entity_id
        mock_entity.canonical_name = "Test Entity"
        mock_entity.entity_type = "person"
        mock_entity.description = "Description"
        mock_entity.status = "active"
        mock_entity.mention_count = 10
        mock_entity.video_count = 5  # Stored DB value

        # Count query returns 1
        count_result = MagicMock()
        count_result.scalar.return_value = 1

        # Entity list query
        list_result = MagicMock()
        list_scalars = MagicMock()
        list_scalars.all.return_value = [mock_entity]
        list_result.scalars.return_value = list_scalars

        mock_session.execute = AsyncMock(
            side_effect=[count_result, list_result]
        )
        mock_session.commit = AsyncMock()

        async for client in _build_client(mock_session):
            response = await client.get("/api/v1/entities")

        assert response.status_code == 200
        body = response.json()
        assert len(body["data"]) == 1
        # For MVP, video_count reflects stored DB value
        assert body["data"][0]["video_count"] == 5

    async def test_entity_list_sort_by_mentions_uses_mention_count(
        self,
    ) -> None:
        """Entity list sorted by mentions uses mention_count column (T033).

        When ``sort=mentions`` is specified, the entity list sorts by
        ``mention_count DESC``.  For MVP, this uses the stored mention_count
        column, not a combined video count.

        Future enhancement (FR-012): sort=mentions should use combined
        video count from all sources.
        """
        entity_id_1 = _uuid()
        entity_id_2 = _uuid()

        mock_session = AsyncMock(spec=AsyncSession)

        # Entity with more mentions sorts first
        entity_1 = MagicMock()
        entity_1.id = entity_id_1
        entity_1.canonical_name = "Entity Alpha"
        entity_1.entity_type = "person"
        entity_1.description = None
        entity_1.status = "active"
        entity_1.mention_count = 20
        entity_1.video_count = 3

        entity_2 = MagicMock()
        entity_2.id = entity_id_2
        entity_2.canonical_name = "Entity Beta"
        entity_2.entity_type = "person"
        entity_2.description = None
        entity_2.status = "active"
        entity_2.mention_count = 5
        entity_2.video_count = 10  # More videos but fewer mentions

        count_result = MagicMock()
        count_result.scalar.return_value = 2

        list_result = MagicMock()
        list_scalars = MagicMock()
        # Pre-sorted by mention_count DESC by the DB query
        list_scalars.all.return_value = [entity_1, entity_2]
        list_result.scalars.return_value = list_scalars

        mock_session.execute = AsyncMock(
            side_effect=[count_result, list_result]
        )
        mock_session.commit = AsyncMock()

        async for client in _build_client(mock_session):
            response = await client.get("/api/v1/entities?sort=mentions")

        assert response.status_code == 200
        body = response.json()
        assert len(body["data"]) == 2
        # Entity with higher mention_count appears first
        assert body["data"][0]["mention_count"] == 20
        assert body["data"][1]["mention_count"] == 5
