"""Integration tests for canonical tag API endpoints (Feature 030).

Tests list, detail, and video endpoints for canonical tags, verifying
pagination, search, availability filtering, error responses, fuzzy
suggestions, and rate limiting.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, AsyncGenerator, List
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid_utils import uuid7

from chronovista.api.routers.canonical_tags import _request_counts
from chronovista.db.models import (
    CanonicalTag,
    Channel,
    TagAlias,
    Video,
    VideoTag,
)
from tests.factories.id_factory import YouTubeIdFactory

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

pytestmark = pytest.mark.asyncio

# ---------------------------------------------------------------------------
# Test IDs generated via factory to avoid collisions and ensure validity
# ---------------------------------------------------------------------------
_CHANNEL_ID = YouTubeIdFactory.create_channel_id(seed="ctag_test_channel_001")
_VIDEO_ID_001 = YouTubeIdFactory.create_video_id(seed="ctag_vid_001")
_VIDEO_ID_002 = YouTubeIdFactory.create_video_id(seed="ctag_vid_002")
_VIDEO_ID_003 = YouTubeIdFactory.create_video_id(seed="ctag_vid_003")
_VIDEO_ID_004 = YouTubeIdFactory.create_video_id(seed="ctag_vid_004")
_TAG_PREFIX = "ctag_test_"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def test_data_session(
    integration_session_factory: "async_sessionmaker[AsyncSession]",
) -> AsyncGenerator[AsyncSession, None]:
    """Provide a session for test data setup and cleanup."""
    async with integration_session_factory() as session:
        yield session


@pytest.fixture
async def sample_channel(test_data_session: AsyncSession) -> Channel:
    """Create a sample channel for canonical tag tests."""
    result = await test_data_session.execute(
        select(Channel).where(Channel.channel_id == _CHANNEL_ID)
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing

    channel = Channel(
        channel_id=_CHANNEL_ID,
        title="Canonical Tag Test Channel",
    )
    test_data_session.add(channel)
    await test_data_session.commit()
    await test_data_session.refresh(channel)
    return channel


@pytest.fixture
async def sample_data(
    test_data_session: AsyncSession,
    sample_channel: Channel,
) -> dict[str, Any]:
    """Create canonical tags, aliases, videos, and video_tags for testing.

    Returns a dict with keys: canonical_tags, aliases, videos, video_tags
    so individual tests can reference specific records.
    """
    now = datetime.now(tz=timezone.utc)

    # ---- Canonical Tags ----
    ct_music_id = uuid.UUID(bytes=uuid7().bytes)
    ct_newyork_id = uuid.UUID(bytes=uuid7().bytes)
    ct_python_id = uuid.UUID(bytes=uuid7().bytes)
    ct_merged_id = uuid.UUID(bytes=uuid7().bytes)

    ct_music = CanonicalTag(
        id=ct_music_id,
        canonical_form="Music",
        normalized_form="music",
        alias_count=3,
        video_count=2,
        status="active",
        created_at=now,
        updated_at=now,
    )
    ct_newyork = CanonicalTag(
        id=ct_newyork_id,
        canonical_form="New York",
        normalized_form="new york",
        alias_count=2,
        video_count=1,
        status="active",
        created_at=now,
        updated_at=now,
    )
    ct_python = CanonicalTag(
        id=ct_python_id,
        canonical_form="Python",
        normalized_form="python",
        alias_count=1,
        video_count=1,
        status="active",
        created_at=now,
        updated_at=now,
    )
    ct_merged = CanonicalTag(
        id=ct_merged_id,
        canonical_form="Musica",
        normalized_form="musica",
        alias_count=1,
        video_count=0,
        status="merged",
        merged_into_id=ct_music_id,
        created_at=now,
        updated_at=now,
    )

    for ct in [ct_music, ct_newyork, ct_python, ct_merged]:
        test_data_session.add(ct)
    await test_data_session.flush()

    # ---- Tag Aliases ----
    aliases: list[TagAlias] = []
    alias_specs = [
        # (raw_form, normalized_form, canonical_tag_id, occurrence_count)
        ("Music", "music", ct_music_id, 100),
        ("music", "music", ct_music_id, 80),
        ("MUSIC", "music", ct_music_id, 20),
        ("New York", "new york", ct_newyork_id, 50),
        ("new york", "new york", ct_newyork_id, 30),
        ("Python", "python", ct_python_id, 40),
    ]
    for raw_form, norm_form, ct_id, occ in alias_specs:
        alias = TagAlias(
            id=uuid.UUID(bytes=uuid7().bytes),
            raw_form=f"{_TAG_PREFIX}{raw_form}",
            normalized_form=norm_form,
            canonical_tag_id=ct_id,
            creation_method="backfill",
            normalization_version=1,
            occurrence_count=occ,
            first_seen_at=now,
            last_seen_at=now,
            created_at=now,
        )
        test_data_session.add(alias)
        aliases.append(alias)
    await test_data_session.flush()

    # ---- Videos ----
    vid1 = Video(
        video_id=_VIDEO_ID_001,
        channel_id=_CHANNEL_ID,
        title="Music Video One",
        upload_date=datetime(2024, 6, 15, tzinfo=timezone.utc),
        duration=300,
        availability_status="available",
    )
    vid2 = Video(
        video_id=_VIDEO_ID_002,
        channel_id=_CHANNEL_ID,
        title="Music and New York Video",
        upload_date=datetime(2024, 7, 20, tzinfo=timezone.utc),
        duration=420,
        availability_status="available",
    )
    vid3 = Video(
        video_id=_VIDEO_ID_003,
        channel_id=_CHANNEL_ID,
        title="Python Tutorial",
        upload_date=datetime(2024, 5, 10, tzinfo=timezone.utc),
        duration=600,
        availability_status="available",
    )
    vid4_deleted = Video(
        video_id=_VIDEO_ID_004,
        channel_id=_CHANNEL_ID,
        title="Deleted Music Video",
        upload_date=datetime(2024, 8, 1, tzinfo=timezone.utc),
        duration=180,
        availability_status="deleted",
    )

    for v in [vid1, vid2, vid3, vid4_deleted]:
        test_data_session.add(v)
    await test_data_session.flush()

    # ---- VideoTags (raw tag must match a TagAlias.raw_form) ----
    video_tag_specs = [
        (vid1.video_id, f"{_TAG_PREFIX}Music"),
        (vid2.video_id, f"{_TAG_PREFIX}music"),
        (vid2.video_id, f"{_TAG_PREFIX}New York"),
        (vid3.video_id, f"{_TAG_PREFIX}Python"),
        (vid4_deleted.video_id, f"{_TAG_PREFIX}MUSIC"),
    ]
    video_tags: list[VideoTag] = []
    for vid_id, tag in video_tag_specs:
        vt = VideoTag(video_id=vid_id, tag=tag)
        test_data_session.add(vt)
        video_tags.append(vt)

    await test_data_session.commit()

    return {
        "canonical_tags": {
            "music": ct_music,
            "new_york": ct_newyork,
            "python": ct_python,
            "merged": ct_merged,
        },
        "aliases": aliases,
        "videos": {
            "vid1": vid1,
            "vid2": vid2,
            "vid3": vid3,
            "vid4_deleted": vid4_deleted,
        },
        "video_tags": video_tags,
    }


@pytest.fixture
async def cleanup_test_data(
    test_data_session: AsyncSession,
) -> AsyncGenerator[None, None]:
    """Cleanup all canonical tag test data after tests complete."""
    yield

    video_ids = [
        _VIDEO_ID_001,
        _VIDEO_ID_002,
        _VIDEO_ID_003,
        _VIDEO_ID_004,
    ]

    # Delete in FK-safe order: VideoTag -> Video -> TagAlias -> CanonicalTag -> Channel
    await test_data_session.execute(
        delete(VideoTag).where(VideoTag.video_id.in_(video_ids))
    )
    await test_data_session.execute(
        delete(Video).where(Video.video_id.in_(video_ids))
    )
    await test_data_session.execute(
        delete(TagAlias).where(TagAlias.raw_form.like(f"{_TAG_PREFIX}%"))
    )
    await test_data_session.execute(
        delete(CanonicalTag).where(
            CanonicalTag.normalized_form.in_(
                ["music", "new york", "python", "musica"]
            )
        )
    )
    await test_data_session.execute(
        delete(Channel).where(Channel.channel_id == _CHANNEL_ID)
    )
    await test_data_session.commit()


# ---------------------------------------------------------------------------
# TestListCanonicalTags
# ---------------------------------------------------------------------------


class TestListCanonicalTags:
    """Tests for GET /api/v1/canonical-tags list endpoint."""

    async def test_default_list_sorted_by_video_count_desc(
        self,
        async_client: AsyncClient,
        sample_data: dict[str, Any],
        cleanup_test_data: None,
    ) -> None:
        """Default list returns canonical tags sorted by video_count DESC."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/canonical-tags")

        assert response.status_code == 200
        body = response.json()
        assert "data" in body
        assert "pagination" in body

        # Extract our test tags from the response (other tags may exist)
        our_tags = [
            item
            for item in body["data"]
            if item["normalized_form"] in ("music", "new york", "python")
        ]

        # Verify ordering: video_count should be non-increasing
        for i in range(len(body["data"]) - 1):
            assert body["data"][i]["video_count"] >= body["data"][i + 1]["video_count"]

        # Verify our tags are present and have expected counts
        music_tags = [t for t in our_tags if t["normalized_form"] == "music"]
        assert len(music_tags) == 1
        assert music_tags[0]["video_count"] == 2
        assert music_tags[0]["canonical_form"] == "Music"

    async def test_search_with_q_prefix_returns_matching_tags(
        self,
        async_client: AsyncClient,
        sample_data: dict[str, Any],
        cleanup_test_data: None,
    ) -> None:
        """Search with q=mus returns tags starting with 'mus'."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/canonical-tags?q=mus")

        assert response.status_code == 200
        body = response.json()

        # Should match "music" (active) but NOT "musica" (merged - filtered by status)
        norms = [item["normalized_form"] for item in body["data"]]
        assert "music" in norms
        # Merged tags are filtered by default (status='active')
        assert "musica" not in norms

    async def test_pagination_with_limit_and_offset(
        self,
        async_client: AsyncClient,
        sample_data: dict[str, Any],
        cleanup_test_data: None,
    ) -> None:
        """Pagination with limit and offset returns correct slice."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            # First page: limit=2
            resp1 = await async_client.get("/api/v1/canonical-tags?limit=2&offset=0")
            assert resp1.status_code == 200
            body1 = resp1.json()
            assert len(body1["data"]) <= 2
            assert body1["pagination"]["limit"] == 2
            assert body1["pagination"]["offset"] == 0

            # Second page: limit=2, offset=2
            resp2 = await async_client.get("/api/v1/canonical-tags?limit=2&offset=2")
            assert resp2.status_code == 200
            body2 = resp2.json()
            assert body2["pagination"]["offset"] == 2

            # No overlap between pages
            ids_page1 = {item["normalized_form"] for item in body1["data"]}
            ids_page2 = {item["normalized_form"] for item in body2["data"]}
            assert ids_page1.isdisjoint(ids_page2)

    async def test_empty_results_for_unmatched_query(
        self,
        async_client: AsyncClient,
        sample_data: dict[str, Any],
        cleanup_test_data: None,
    ) -> None:
        """Search for a non-existent prefix returns empty data list."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                "/api/v1/canonical-tags?q=zzz_no_match_ever_xyz"
            )

        assert response.status_code == 200
        body = response.json()
        assert body["data"] == []
        assert body["pagination"]["total"] == 0

    async def test_q_min_length_validated(
        self,
        async_client: AsyncClient,
        sample_data: dict[str, Any],
        cleanup_test_data: None,
    ) -> None:
        """Empty q parameter is rejected by FastAPI validation (min_length=1)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/canonical-tags?q=")

        assert response.status_code == 422

    async def test_merged_tags_not_in_default_list(
        self,
        async_client: AsyncClient,
        sample_data: dict[str, Any],
        cleanup_test_data: None,
    ) -> None:
        """Merged tags should not appear in the default list (status=active filter)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/canonical-tags")

        assert response.status_code == 200
        body = response.json()
        norms = [item["normalized_form"] for item in body["data"]]
        assert "musica" not in norms

    async def test_pagination_has_more_flag(
        self,
        async_client: AsyncClient,
        sample_data: dict[str, Any],
        cleanup_test_data: None,
    ) -> None:
        """Pagination has_more is True when more items exist beyond current page."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                "/api/v1/canonical-tags?limit=1&offset=0"
            )

        assert response.status_code == 200
        body = response.json()
        # We have at least 3 active canonical tags, so with limit=1 has_more=True
        assert body["pagination"]["has_more"] is True


# ---------------------------------------------------------------------------
# TestSearchResolvesMergedAliases
# ---------------------------------------------------------------------------

# Prefix used for merge-scenario canonical tags to avoid collisions
_MERGE_TAG_PREFIX = "mrg_test_"


class TestSearchResolvesMergedAliases:
    """Tests verifying that search resolves aliases after a merge operation.

    Regression suite for the bug where searching by the raw_form of a merged
    alias returned zero results because the search only matched
    ``canonical_form``/``normalized_form`` columns, not ``tag_aliases.raw_form``.

    Scenario
    --------
    - "target" canonical tag: ``mrg_test_claudia sheinbaum`` (active)
    - "source" canonical tag: ``mrg_test_sheinbaum presidenta`` (active → merged)
    - Source has two aliases: one with raw_form ``mrg_test_sheinbaum presidenta``
      and one with raw_form ``mrg_test_Sheinbaum Presidenta`` (case variant).
    - Merge is simulated by:
      1. Reassigning all source aliases to the target (update canonical_tag_id
         and normalized_form on each TagAlias row).
      2. Setting source status to ``"merged"`` with ``merged_into_id`` pointing
         to the target.

    After the merge the active tag is *target*.  Searching by a prefix that
    matches the source alias raw_form must return *target*, not *source*.
    """

    # ------------------------------------------------------------------
    # Helper: create a canonical tag row
    # ------------------------------------------------------------------

    async def _insert_canonical_tag(
        self,
        session: AsyncSession,
        canonical_form: str,
        normalized_form: str,
        alias_count: int = 1,
        video_count: int = 0,
        status: str = "active",
        merged_into_id: uuid.UUID | None = None,
    ) -> CanonicalTag:
        """Insert a canonical tag and flush (does not commit).

        Parameters
        ----------
        session : AsyncSession
            Active database session.
        canonical_form : str
            Human-readable tag display form.
        normalized_form : str
            Normalised (lowercased) tag form — must be unique.
        alias_count : int, optional
            Minimum 1 to satisfy the DB check constraint (default 1).
        video_count : int, optional
            Denormalised video count (default 0).
        status : str, optional
            Lifecycle status: "active", "merged", or "deprecated" (default "active").
        merged_into_id : uuid.UUID | None, optional
            UUID of the target canonical tag when status is "merged".

        Returns
        -------
        CanonicalTag
            The flushed ORM instance.
        """
        now = datetime.now(tz=timezone.utc)
        tag = CanonicalTag(
            id=uuid.UUID(bytes=uuid7().bytes),
            canonical_form=canonical_form,
            normalized_form=normalized_form,
            alias_count=alias_count,
            video_count=video_count,
            status=status,
            merged_into_id=merged_into_id,
            created_at=now,
            updated_at=now,
        )
        session.add(tag)
        await session.flush()
        return tag

    async def _insert_alias(
        self,
        session: AsyncSession,
        raw_form: str,
        normalized_form: str,
        canonical_tag_id: uuid.UUID,
        occurrence_count: int = 10,
    ) -> TagAlias:
        """Insert a tag alias and flush (does not commit).

        Parameters
        ----------
        session : AsyncSession
            Active database session.
        raw_form : str
            Raw tag string as it appears in ``video_tags.tag``.
        normalized_form : str
            Normalised form stored on the alias row.
        canonical_tag_id : uuid.UUID
            FK to the owning canonical tag.
        occurrence_count : int, optional
            Minimum 1 to satisfy the DB check constraint (default 10).

        Returns
        -------
        TagAlias
            The flushed ORM instance.
        """
        now = datetime.now(tz=timezone.utc)
        alias = TagAlias(
            id=uuid.UUID(bytes=uuid7().bytes),
            raw_form=raw_form,
            normalized_form=normalized_form,
            canonical_tag_id=canonical_tag_id,
            creation_method="backfill",
            normalization_version=1,
            occurrence_count=occurrence_count,
            first_seen_at=now,
            last_seen_at=now,
            created_at=now,
        )
        session.add(alias)
        await session.flush()
        return alias

    # ------------------------------------------------------------------
    # Fixture: merge scenario data
    # ------------------------------------------------------------------

    @pytest.fixture
    async def merge_scenario(
        self,
        test_data_session: AsyncSession,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Set up the merge scenario and clean up in a finally block.

        Creates:
        - ``ct_target``: active canonical tag with normalized_form
          ``mrg_test_claudia sheinbaum``
        - ``ct_source``: initially active, then merged into target, with
          normalized_form ``mrg_test_sheinbaum presidenta``
        - Two aliases originally belonging to source:
          - raw_form ``mrg_test_sheinbaum presidenta``  (lower-case variant)
          - raw_form ``mrg_test_Sheinbaum Presidenta``  (title-case variant)
        - One alias originally belonging to target:
          - raw_form ``mrg_test_Claudia Sheinbaum``

        After merge simulation (alias reassignment + source status update),
        all three aliases point to ``ct_target`` and ``ct_source.status``
        is ``"merged"``.

        Yields a ``dict`` with:
        - ``"ct_target"``: target CanonicalTag ORM instance
        - ``"ct_source"``: source CanonicalTag ORM instance
        - ``"source_alias_raw_form"``: str — the lower-case source alias raw_form
        - ``"source_alias_raw_form_title"``: str — the title-case source alias raw_form
        - ``"target_alias_raw_form"``: str — the target's own alias raw_form
        - ``"source_normalized_form"``: str — source's original normalized_form
        - ``"target_normalized_form"``: str — target's normalized_form
        """
        # ---- Create target canonical tag (stays active) ----
        target_normalized = f"{_MERGE_TAG_PREFIX}claudia sheinbaum"
        ct_target = await self._insert_canonical_tag(
            test_data_session,
            canonical_form="Mrg_test_Claudia Sheinbaum",
            normalized_form=target_normalized,
            alias_count=3,  # will own 3 aliases after merge
            video_count=5,
        )

        # ---- Create source canonical tag (will be merged) ----
        source_normalized = f"{_MERGE_TAG_PREFIX}sheinbaum presidenta"
        ct_source = await self._insert_canonical_tag(
            test_data_session,
            canonical_form="Mrg_test_Sheinbaum Presidenta",
            normalized_form=source_normalized,
            alias_count=2,  # owns 2 aliases before merge
            video_count=2,
        )

        # ---- Create aliases for target (its own alias) ----
        target_alias_raw_form = f"{_MERGE_TAG_PREFIX}Claudia Sheinbaum"
        await self._insert_alias(
            test_data_session,
            raw_form=target_alias_raw_form,
            normalized_form=target_normalized,
            canonical_tag_id=ct_target.id,
            occurrence_count=50,
        )

        # ---- Create aliases for source (these will be reassigned to target) ----
        source_alias_raw_form = f"{_MERGE_TAG_PREFIX}sheinbaum presidenta"
        source_alias_raw_form_title = f"{_MERGE_TAG_PREFIX}Sheinbaum Presidenta"

        alias_source_lower = await self._insert_alias(
            test_data_session,
            raw_form=source_alias_raw_form,
            normalized_form=source_normalized,
            canonical_tag_id=ct_source.id,
            occurrence_count=20,
        )
        alias_source_title = await self._insert_alias(
            test_data_session,
            raw_form=source_alias_raw_form_title,
            normalized_form=source_normalized,
            canonical_tag_id=ct_source.id,
            occurrence_count=15,
        )

        await test_data_session.flush()

        # ---- Simulate merge: reassign source aliases to target ----
        # Update both canonical_tag_id and normalized_form on alias rows,
        # mirroring what the real merge operation performs.
        alias_source_lower.canonical_tag_id = ct_target.id
        alias_source_lower.normalized_form = target_normalized
        alias_source_title.canonical_tag_id = ct_target.id
        alias_source_title.normalized_form = target_normalized

        # ---- Set source status to merged ----
        ct_source.status = "merged"
        ct_source.merged_into_id = ct_target.id

        await test_data_session.commit()

        try:
            yield {
                "ct_target": ct_target,
                "ct_source": ct_source,
                "source_alias_raw_form": source_alias_raw_form,
                "source_alias_raw_form_title": source_alias_raw_form_title,
                "target_alias_raw_form": target_alias_raw_form,
                "source_normalized_form": source_normalized,
                "target_normalized_form": target_normalized,
            }
        finally:
            # Clean up in FK-safe order: TagAlias → CanonicalTag
            await test_data_session.execute(
                delete(TagAlias).where(
                    TagAlias.raw_form.like(f"{_MERGE_TAG_PREFIX}%")
                )
            )
            await test_data_session.execute(
                delete(CanonicalTag).where(
                    CanonicalTag.normalized_form.like(f"{_MERGE_TAG_PREFIX}%")
                )
            )
            await test_data_session.commit()

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------

    async def test_search_by_merged_alias_raw_form_finds_target(
        self,
        async_client: AsyncClient,
        merge_scenario: dict[str, Any],
    ) -> None:
        """After merging source into target, searching by source alias raw_form prefix returns target.

        This is the primary regression test.  Before the fix, the search query
        only matched ``canonical_form`` and ``normalized_form`` columns.  The
        source alias raw_form was reassigned to the target, so a prefix search
        must traverse ``tag_aliases.raw_form`` and surface the active target tag.

        The search query prefix is derived from the raw_form of the first source
        alias, which starts with ``mrg_test_sheinbaum``.  After the merge that
        alias belongs to the active target tag; the source tag is ``merged`` and
        must not appear in results.
        """
        source_alias_raw = merge_scenario["source_alias_raw_form"]
        # Use the first 24 chars of the raw_form as the search prefix.
        # "mrg_test_sheinbaum presi" is unambiguous and long enough to avoid
        # matching unrelated tags inserted by other tests.
        q = source_alias_raw[:24]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                f"/api/v1/canonical-tags?q={q}"
            )

        assert response.status_code == 200, (
            f"Expected 200 but got {response.status_code}: {response.text}"
        )
        body = response.json()

        # The target tag must appear in results — its alias raw_form matches q
        target_norm = merge_scenario["target_normalized_form"]
        result_norms = [item["normalized_form"] for item in body["data"]]
        assert target_norm in result_norms, (
            f"Expected target tag '{target_norm}' in search results for q='{q}'; "
            f"got: {result_norms}.  "
            "This indicates the alias raw_form JOIN path is not working after merge."
        )

        # The merged source tag must NOT appear — it has status='merged'
        source_norm = merge_scenario["source_normalized_form"]
        assert source_norm not in result_norms, (
            f"Merged source tag '{source_norm}' must not appear in search results "
            "(status='merged' should be filtered out by default)."
        )

    async def test_search_by_source_normalized_form_finds_target(
        self,
        async_client: AsyncClient,
        merge_scenario: dict[str, Any],
    ) -> None:
        """After merge, searching by the source's original normalized_form prefix returns target.

        During the merge, the source aliases have their ``normalized_form``
        column updated to match the target's normalized_form.  The *original*
        source normalized_form (``mrg_test_sheinbaum presidenta``) now lives
        only as the ``normalized_form`` of the source canonical_tag row (which
        is ``merged`` and invisible) — it is no longer on any alias row.

        However, the alias ``raw_form`` still starts with the source's original
        tag text (``mrg_test_sheinbaum presidenta``), so searching by that
        prefix still resolves to the target via the ``tag_aliases.raw_form``
        ILIKE path.

        This test verifies that the updated ``normalized_form`` on alias rows
        does not break the lookup: the raw_form path is sufficient to find
        the target.
        """
        # The source alias raw_form starts with "mrg_test_sheinbaum presidenta".
        # We query with a 22-char prefix to avoid catching unrelated rows.
        source_alias_raw = merge_scenario["source_alias_raw_form"]
        q = source_alias_raw[:22]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                f"/api/v1/canonical-tags?q={q}"
            )

        assert response.status_code == 200, (
            f"Expected 200 but got {response.status_code}: {response.text}"
        )
        body = response.json()

        target_norm = merge_scenario["target_normalized_form"]
        result_norms = [item["normalized_form"] for item in body["data"]]
        assert target_norm in result_norms, (
            f"Expected target tag '{target_norm}' in results for q='{q}'; "
            f"got: {result_norms}.  "
            "Alias raw_form ILIKE path must find the target even after "
            "normalized_form on alias rows has been updated."
        )

    async def test_search_by_target_canonical_form_still_works(
        self,
        async_client: AsyncClient,
        merge_scenario: dict[str, Any],
    ) -> None:
        """After merge, searching by target's own canonical_form continues to work.

        The merge operation must not interfere with the pre-existing search
        behaviour for the target tag.  Querying the target's canonical_form
        prefix must still return the target without regression.
        """
        # "Mrg_test_Claudia Sheinbaum" — use 21 chars as the prefix to keep
        # the query specific enough while exercising the ILIKE path on
        # canonical_form.
        q = "Mrg_test_Claudia Shei"

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                f"/api/v1/canonical-tags?q={q}"
            )

        assert response.status_code == 200, (
            f"Expected 200 but got {response.status_code}: {response.text}"
        )
        body = response.json()

        target_norm = merge_scenario["target_normalized_form"]
        result_norms = [item["normalized_form"] for item in body["data"]]
        assert target_norm in result_norms, (
            f"Expected target tag '{target_norm}' in results for q='{q}'; "
            f"got: {result_norms}.  "
            "Canonical_form ILIKE path on the target tag must not regress "
            "after adding alias-based search."
        )

        # The merged source must not appear either
        source_norm = merge_scenario["source_normalized_form"]
        assert source_norm not in result_norms, (
            f"Merged source tag '{source_norm}' appeared in results for "
            f"q='{q}' — status='merged' filter must still apply."
        )

    async def test_merged_canonical_tag_not_returned_directly(
        self,
        async_client: AsyncClient,
        merge_scenario: dict[str, Any],
    ) -> None:
        """The merged source canonical tag itself must not appear in any search results.

        This test verifies the status filter is applied correctly: even when
        searching for a prefix that historically matched the source tag's own
        canonical_form (``Mrg_test_Sheinbaum Presidenta``), the source must not
        appear because its status is now ``"merged"``.

        The target may or may not appear depending on whether its aliases match;
        the critical assertion is that the *source* is absent.
        """
        # Use the source's own canonical_form prefix — before the merge this
        # would have returned the source directly.
        q = "Mrg_test_Sheinbaum Pre"

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                f"/api/v1/canonical-tags?q={q}"
            )

        assert response.status_code == 200, (
            f"Expected 200 but got {response.status_code}: {response.text}"
        )
        body = response.json()

        source_norm = merge_scenario["source_normalized_form"]
        result_norms = [item["normalized_form"] for item in body["data"]]

        # The merged source tag must be absent — it is status='merged'
        assert source_norm not in result_norms, (
            f"Merged source tag '{source_norm}' must not appear in results for "
            f"q='{q}'.  The default status='active' filter must exclude merged tags."
        )

        # The target must appear: its two reassigned aliases have raw_form
        # starting with "mrg_test_Sheinbaum Pre…" which matches the query.
        target_norm = merge_scenario["target_normalized_form"]
        assert target_norm in result_norms, (
            f"Expected active target tag '{target_norm}' in results for q='{q}'; "
            f"got: {result_norms}.  "
            "The reassigned alias raw_forms (title-case variant) should match "
            "this prefix and surface the target."
        )


# ---------------------------------------------------------------------------
# TestCanonicalTagDetail
# ---------------------------------------------------------------------------


class TestCanonicalTagDetail:
    """Tests for GET /api/v1/canonical-tags/{normalized_form} detail endpoint."""

    async def test_happy_path_with_aliases(
        self,
        async_client: AsyncClient,
        sample_data: dict[str, Any],
        cleanup_test_data: None,
    ) -> None:
        """Detail endpoint returns canonical tag with top aliases."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/canonical-tags/music")

        assert response.status_code == 200
        body = response.json()
        detail = body["data"]

        assert detail["canonical_form"] == "Music"
        assert detail["normalized_form"] == "music"
        assert detail["alias_count"] == 3
        assert detail["video_count"] == 2
        assert "created_at" in detail
        assert "updated_at" in detail

        # Top aliases should be present and ordered by occurrence_count DESC
        aliases = detail["top_aliases"]
        assert len(aliases) > 0
        for i in range(len(aliases) - 1):
            assert aliases[i]["occurrence_count"] >= aliases[i + 1]["occurrence_count"]

        # Check first alias has highest occurrence
        raw_forms = [a["raw_form"] for a in aliases]
        assert f"{_TAG_PREFIX}Music" in raw_forms

    async def test_alias_limit_parameter(
        self,
        async_client: AsyncClient,
        sample_data: dict[str, Any],
        cleanup_test_data: None,
    ) -> None:
        """alias_limit parameter restricts number of returned aliases."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                "/api/v1/canonical-tags/music?alias_limit=1"
            )

        assert response.status_code == 200
        body = response.json()
        aliases = body["data"]["top_aliases"]
        assert len(aliases) == 1
        # The highest-occurrence alias should be returned
        assert aliases[0]["occurrence_count"] == 100

    async def test_404_for_nonexistent_tag(
        self,
        async_client: AsyncClient,
        sample_data: dict[str, Any],
        cleanup_test_data: None,
    ) -> None:
        """Detail endpoint returns 404 for a tag that does not exist."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                "/api/v1/canonical-tags/nonexistent_tag_xyz_999"
            )

        assert response.status_code == 404

    async def test_404_for_merged_tag(
        self,
        async_client: AsyncClient,
        sample_data: dict[str, Any],
        cleanup_test_data: None,
    ) -> None:
        """Detail endpoint returns 404 for a merged tag (status != active)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/canonical-tags/musica")

        assert response.status_code == 404

    async def test_url_encoded_normalized_form(
        self,
        async_client: AsyncClient,
        sample_data: dict[str, Any],
        cleanup_test_data: None,
    ) -> None:
        """Detail endpoint works with URL-encoded normalized_form (e.g. 'new%20york')."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/canonical-tags/new%20york")

        assert response.status_code == 200
        body = response.json()
        detail = body["data"]
        assert detail["canonical_form"] == "New York"
        assert detail["normalized_form"] == "new york"
        assert detail["alias_count"] == 2
        assert detail["video_count"] == 1


# ---------------------------------------------------------------------------
# TestCanonicalTagVideos
# ---------------------------------------------------------------------------


class TestCanonicalTagVideos:
    """Tests for GET /api/v1/canonical-tags/{normalized_form}/videos endpoint."""

    async def test_happy_path_returns_videos(
        self,
        async_client: AsyncClient,
        sample_data: dict[str, Any],
        cleanup_test_data: None,
    ) -> None:
        """Videos endpoint returns videos linked to canonical tag with correct structure."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                "/api/v1/canonical-tags/music/videos"
            )

        assert response.status_code == 200
        body = response.json()
        assert "data" in body
        assert "pagination" in body

        # Default: include_unavailable=false, so only available videos
        video_ids = [v["video_id"] for v in body["data"]]
        assert _VIDEO_ID_001 in video_ids
        assert _VIDEO_ID_002 in video_ids
        # Deleted video should NOT be included by default
        assert _VIDEO_ID_004 not in video_ids

        # Verify video structure
        for video_item in body["data"]:
            assert "video_id" in video_item
            assert "title" in video_item
            assert "channel_id" in video_item
            assert "upload_date" in video_item
            assert "duration" in video_item
            assert "transcript_summary" in video_item
            assert "availability_status" in video_item

        assert body["pagination"]["total"] == 2

    async def test_pagination_works(
        self,
        async_client: AsyncClient,
        sample_data: dict[str, Any],
        cleanup_test_data: None,
    ) -> None:
        """Videos endpoint respects limit and offset parameters."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            resp1 = await async_client.get(
                "/api/v1/canonical-tags/music/videos?limit=1&offset=0"
            )
            assert resp1.status_code == 200
            body1 = resp1.json()
            assert len(body1["data"]) == 1
            assert body1["pagination"]["limit"] == 1
            assert body1["pagination"]["offset"] == 0
            assert body1["pagination"]["total"] == 2
            assert body1["pagination"]["has_more"] is True

            resp2 = await async_client.get(
                "/api/v1/canonical-tags/music/videos?limit=1&offset=1"
            )
            assert resp2.status_code == 200
            body2 = resp2.json()
            assert len(body2["data"]) == 1
            assert body2["pagination"]["has_more"] is False

            # Pages should not overlap
            assert body1["data"][0]["video_id"] != body2["data"][0]["video_id"]

    async def test_include_unavailable_false_excludes_deleted(
        self,
        async_client: AsyncClient,
        sample_data: dict[str, Any],
        cleanup_test_data: None,
    ) -> None:
        """include_unavailable=false (default) excludes deleted videos."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                "/api/v1/canonical-tags/music/videos?include_unavailable=false"
            )

        assert response.status_code == 200
        body = response.json()
        video_ids = [v["video_id"] for v in body["data"]]
        assert _VIDEO_ID_004 not in video_ids
        assert body["pagination"]["total"] == 2

    async def test_include_unavailable_true_includes_deleted(
        self,
        async_client: AsyncClient,
        sample_data: dict[str, Any],
        cleanup_test_data: None,
    ) -> None:
        """include_unavailable=true includes deleted videos."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                "/api/v1/canonical-tags/music/videos?include_unavailable=true"
            )

        assert response.status_code == 200
        body = response.json()
        video_ids = [v["video_id"] for v in body["data"]]
        assert _VIDEO_ID_004 in video_ids
        assert body["pagination"]["total"] == 3

    async def test_404_for_nonexistent_tag(
        self,
        async_client: AsyncClient,
        sample_data: dict[str, Any],
        cleanup_test_data: None,
    ) -> None:
        """Videos endpoint returns 404 for a non-existent canonical tag."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                "/api/v1/canonical-tags/nonexistent_tag_xyz_999/videos"
            )

        assert response.status_code == 404

    async def test_results_ordered_by_upload_date_desc(
        self,
        async_client: AsyncClient,
        sample_data: dict[str, Any],
        cleanup_test_data: None,
    ) -> None:
        """Videos are returned ordered by upload_date descending."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                "/api/v1/canonical-tags/music/videos"
            )

        assert response.status_code == 200
        body = response.json()
        videos = body["data"]
        assert len(videos) >= 2

        # Verify descending order by upload_date
        upload_dates = [v["upload_date"] for v in videos]
        for i in range(len(upload_dates) - 1):
            assert upload_dates[i] >= upload_dates[i + 1], (
                f"Videos not in descending upload_date order: "
                f"{upload_dates[i]} < {upload_dates[i + 1]}"
            )

        # vid2 (2024-07-20) should come before vid1 (2024-06-15)
        vid_ids = [v["video_id"] for v in videos]
        idx_vid2 = vid_ids.index(_VIDEO_ID_002)
        idx_vid1 = vid_ids.index(_VIDEO_ID_001)
        assert idx_vid2 < idx_vid1


# ---------------------------------------------------------------------------
# TestFuzzySuggestions
# ---------------------------------------------------------------------------

# Prefix used for fuzzy-test canonical tags to avoid collisions
_FUZZY_TAG_PREFIX = "fztest_"


class TestFuzzySuggestions:
    """Tests for fuzzy suggestion fallback on GET /api/v1/canonical-tags?q=...

    The fuzzy path fires when:
      - ``q`` is provided
      - prefix search returns zero results
      - ``len(q) >= 2``

    The router loads up to 5,000 active canonical tags ordered by
    video_count DESC, extracts their canonical_form values as the
    candidate pool, and calls ``find_similar`` with max_distance=2.
    """

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _insert_canonical_tag(
        self,
        session: AsyncSession,
        canonical_form: str,
        normalized_form: str,
        video_count: int = 0,
        alias_count: int = 1,
    ) -> CanonicalTag:
        """Insert a single active canonical tag and flush.

        alias_count defaults to 1 to satisfy the database check constraint
        ``chk_canonical_tag_alias_count_positive`` (alias_count >= 1).
        """
        now = datetime.now(tz=timezone.utc)
        tag = CanonicalTag(
            id=uuid.UUID(bytes=uuid7().bytes),
            canonical_form=canonical_form,
            normalized_form=normalized_form,
            alias_count=alias_count,
            video_count=video_count,
            status="active",
            created_at=now,
            updated_at=now,
        )
        session.add(tag)
        await session.flush()
        return tag

    async def _cleanup_fuzzy_tags(self, session: AsyncSession) -> None:
        """Remove all canonical tags whose normalized_form starts with fztest_."""
        await session.execute(
            delete(CanonicalTag).where(
                CanonicalTag.normalized_form.like(f"{_FUZZY_TAG_PREFIX}%")
            )
        )
        await session.commit()

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------

    async def test_typo_query_returns_suggestions_with_canonical_and_normalized_form(
        self,
        async_client: AsyncClient,
        test_data_session: AsyncSession,
    ) -> None:
        """Typo query triggers fuzzy suggestions containing canonical_form and normalized_form.

        We insert a canonical tag "Fztest_Python" (normalized "fztest_python"),
        then query with "fztest_pythn" (one deletion). The prefix search finds
        nothing; fuzzy then returns a suggestion with both fields populated.
        """
        # Arrange: insert a tag close to the upcoming query
        canonical_form = "Fztest_Python"
        normalized_form = f"{_FUZZY_TAG_PREFIX}python"
        await self._insert_canonical_tag(
            test_data_session,
            canonical_form=canonical_form,
            normalized_form=normalized_form,
            video_count=5,
        )
        await test_data_session.commit()

        try:
            # Act: query with a typo that has no prefix match
            with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
                mock_oauth.is_authenticated.return_value = True
                # "fztest_pythn" — one char deleted from "fztest_python"
                response = await async_client.get(
                    "/api/v1/canonical-tags?q=fztest_pythn"
                )

            # Assert
            assert response.status_code == 200
            body = response.json()

            # data must be empty (no prefix match)
            assert body["data"] == [], (
                "Expected empty data list when no prefix match found; "
                f"got: {body['data']}"
            )

            # suggestions must be present and non-empty
            suggestions = body.get("suggestions")
            assert suggestions is not None, "Expected suggestions field in response"
            assert len(suggestions) > 0, "Expected at least one fuzzy suggestion"

            # Every suggestion must expose canonical_form and normalized_form
            for suggestion in suggestions:
                assert "canonical_form" in suggestion, (
                    "Suggestion missing 'canonical_form' field"
                )
                assert "normalized_form" in suggestion, (
                    "Suggestion missing 'normalized_form' field"
                )

            # The inserted tag should appear as a suggestion
            suggestion_canonical_forms = [s["canonical_form"] for s in suggestions]
            assert canonical_form in suggestion_canonical_forms, (
                f"Expected '{canonical_form}' in suggestions; got: {suggestion_canonical_forms}"
            )

            # The matching suggestion should carry the correct normalized_form
            matching = next(
                s for s in suggestions if s["canonical_form"] == canonical_form
            )
            assert matching["normalized_form"] == normalized_form, (
                f"Expected normalized_form='{normalized_form}', "
                f"got '{matching['normalized_form']}'"
            )

        finally:
            await self._cleanup_fuzzy_tags(test_data_session)

    async def test_single_char_query_returns_no_suggestions(
        self,
        async_client: AsyncClient,
        test_data_session: AsyncSession,
    ) -> None:
        """Single-character queries that match nothing return empty suggestions.

        The fuzzy path requires ``len(q) >= 2``.  A one-character query that
        has no prefix match should return an empty suggestions list (or None),
        never a non-empty suggestions list.
        """
        # Use a single char that is extremely unlikely to prefix-match anything
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/canonical-tags?q=Z")

        assert response.status_code == 200
        body = response.json()

        # suggestions must be absent or empty — fuzzy is gated on len(q) >= 2
        suggestions = body.get("suggestions")
        assert not suggestions, (
            "Expected no fuzzy suggestions for a 1-char query; "
            f"got: {suggestions}"
        )

    async def test_prefix_match_returns_data_not_suggestions(
        self,
        async_client: AsyncClient,
        sample_data: dict[str, Any],
        cleanup_test_data: None,
    ) -> None:
        """Query matching an existing prefix returns data array and no suggestions.

        "mus" prefix-matches "Music" from sample_data, so the fuzzy path
        never runs and ``suggestions`` must be None / absent.
        """
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get("/api/v1/canonical-tags?q=mus")

        assert response.status_code == 200
        body = response.json()

        # data must be non-empty (prefix match found)
        assert len(body["data"]) > 0, (
            "Expected data to be non-empty for a known prefix"
        )

        # suggestions must be absent or null — fuzzy only fires on zero data
        suggestions = body.get("suggestions")
        assert not suggestions, (
            "Expected no suggestions when prefix match returned results; "
            f"got: {suggestions}"
        )

    async def test_no_matches_short_query_returns_empty(
        self,
        async_client: AsyncClient,
        sample_data: dict[str, Any],
        cleanup_test_data: None,
    ) -> None:
        """Short query (< 2 chars) with no results returns empty suggestions AND empty data.

        A 1-char query that matches nothing has both data=[] and
        suggestions=None because the fuzzy gate (len(q) >= 2) is not met.
        """
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            # "X" is 1 char and extremely unlikely to prefix-match anything
            response = await async_client.get("/api/v1/canonical-tags?q=X")

        assert response.status_code == 200
        body = response.json()

        assert body["data"] == [], "Expected empty data for unmatched 1-char query"
        suggestions = body.get("suggestions")
        assert not suggestions, (
            "Expected no suggestions for 1-char query (fuzzy gate not met); "
            f"got: {suggestions}"
        )


# ---------------------------------------------------------------------------
# TestRateLimiting
# ---------------------------------------------------------------------------


class TestRateLimiting:
    """Tests for in-memory rate limiting on GET /api/v1/canonical-tags?q=...

    Rate limiting applies only when the ``q`` parameter is present.
    The limit is 50 requests per 60-second window per client IP.
    Exceeding the limit returns HTTP 429 with a ``Retry-After`` header.

    Implementation detail: ``_request_counts`` is a module-level
    ``defaultdict(list)`` in ``canonical_tags.py``.  We clear it before
    each test to prevent cross-test interference.
    """

    def _reset_rate_limit_state(self) -> None:
        """Clear all in-memory rate-limit counters before each test."""
        _request_counts.clear()

    async def test_requests_within_limit_succeed(
        self,
        async_client: AsyncClient,
    ) -> None:
        """Several autocomplete requests within the 50 req/min limit all return 200.

        We send 5 requests under the limit and expect each to succeed.
        """
        self._reset_rate_limit_state()

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            for i in range(5):
                response = await async_client.get(
                    "/api/v1/canonical-tags?q=py",
                    headers={"X-Forwarded-For": "10.0.0.1"},
                )
                assert response.status_code == 200, (
                    f"Request {i + 1} expected 200 but got {response.status_code}"
                )

    async def test_exceeding_rate_limit_returns_429(
        self,
        async_client: AsyncClient,
    ) -> None:
        """Exceeding 50 requests per minute returns 429 with a Retry-After header.

        We pre-seed the rate-limit counter for a client IP with 50 timestamps
        (the maximum allowed), then send one more request.  That 51st request
        must be rejected with 429 and include a ``Retry-After`` header.
        """
        self._reset_rate_limit_state()

        import time

        from chronovista.api.routers.canonical_tags import (
            RATE_LIMIT_REQUESTS,
            RATE_LIMIT_WINDOW_SECONDS,
        )

        client_ip = "10.0.0.2"
        now = time.time()

        # Pre-fill the bucket to exactly the limit with recent timestamps
        _request_counts[client_ip] = [
            now - (RATE_LIMIT_WINDOW_SECONDS - 10)  # within the window
            for _ in range(RATE_LIMIT_REQUESTS)
        ]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                "/api/v1/canonical-tags?q=music",
                headers={"X-Forwarded-For": client_ip},
            )

        assert response.status_code == 429, (
            f"Expected 429 when rate limit exceeded; got {response.status_code}"
        )

        # Response body must include retry_after
        body = response.json()
        assert "retry_after" in body, (
            "Expected 'retry_after' field in 429 response body"
        )
        assert body["retry_after"] >= 1, (
            f"retry_after should be >= 1 second; got {body['retry_after']}"
        )

        # Retry-After header must be present
        assert "retry-after" in response.headers, (
            "Expected 'Retry-After' response header on 429"
        )
        retry_header_value = int(response.headers["retry-after"])
        assert retry_header_value >= 1, (
            f"Retry-After header should be >= 1; got {retry_header_value}"
        )

    async def test_different_client_ips_have_independent_counters(
        self,
        async_client: AsyncClient,
    ) -> None:
        """Different X-Forwarded-For IPs do not share rate-limit counters.

        We exhaust the limit for one IP, then verify that a different IP
        is still allowed through on its first request.
        """
        self._reset_rate_limit_state()

        import time

        from chronovista.api.routers.canonical_tags import (
            RATE_LIMIT_REQUESTS,
            RATE_LIMIT_WINDOW_SECONDS,
        )

        exhausted_ip = "192.168.1.10"
        fresh_ip = "192.168.1.20"
        now = time.time()

        # Exhaust the bucket for exhausted_ip
        _request_counts[exhausted_ip] = [
            now - (RATE_LIMIT_WINDOW_SECONDS - 10)
            for _ in range(RATE_LIMIT_REQUESTS)
        ]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            # Exhausted IP must be rate limited
            exhausted_response = await async_client.get(
                "/api/v1/canonical-tags?q=py",
                headers={"X-Forwarded-For": exhausted_ip},
            )
            assert exhausted_response.status_code == 429, (
                f"Expected 429 for exhausted_ip; got {exhausted_response.status_code}"
            )

            # Fresh IP must still be allowed through
            fresh_response = await async_client.get(
                "/api/v1/canonical-tags?q=py",
                headers={"X-Forwarded-For": fresh_ip},
            )
            assert fresh_response.status_code == 200, (
                f"Expected 200 for fresh_ip; got {fresh_response.status_code}. "
                "Rate-limit counters must be independent per client IP."
            )
