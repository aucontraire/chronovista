"""Feature 066 edge coverage: resolver on non-first pages, language-filtered panel.

Against a real Postgres. Assertions are keyed on the entity/video this test
seeds (project integration-db rule).

- The resolver runs per page, so an ``offset > 0`` page still gets computed
  counts (not a stale column) — guards list pagination beyond page 1.
- The video panel's mention membership honours ``language_code`` exactly as the
  entity side does: a mention in another language is excluded under a language
  filter (tag/manual associations, which carry no language, are unaffected).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from uuid_utils import uuid7

from chronovista.db.models import Channel as ChannelDB
from chronovista.db.models import EntityMention as EntityMentionDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import Video as VideoDB

pytestmark = pytest.mark.asyncio

_PFX = "assocedge066"


def _uid() -> uuid.UUID:
    return uuid.UUID(bytes=uuid7().bytes)


async def _ensure_video(factory: async_sessionmaker[AsyncSession], vid: str) -> None:
    channel_id = f"UC{_PFX}Chan0000"[:24]
    async with factory() as s:
        if await s.get(ChannelDB, channel_id) is None:
            s.add(ChannelDB(channel_id=channel_id, title="AssocEdge Channel"))
            await s.commit()
        if await s.get(VideoDB, vid) is None:
            s.add(
                VideoDB(
                    video_id=vid,
                    channel_id=channel_id,
                    title=f"AssocEdge {vid}",
                    upload_date=datetime(2026, 1, 1, tzinfo=UTC),
                    duration=60,
                    availability_status="available",
                )
            )
            await s.commit()


class TestResolverRunsOnNonFirstPage:
    async def test_offset_page_still_gets_resolver_counts(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        run = _uid().hex[:10]
        # Three entities sharing a unique search token so they paginate together.
        names = [f"AssocEdge {run} {i}" for i in range(3)]
        ids = [_uid() for _ in names]
        async with integration_session_factory() as s:
            for eid, nm in zip(ids, names, strict=True):
                s.add(
                    NamedEntityDB(
                        id=eid,
                        canonical_name=nm,
                        canonical_name_normalized=nm.lower(),
                        entity_type="person",
                        status="active",
                    )
                )
            await s.commit()

        # Page 2 (offset=2) must still carry resolver-computed fields.
        r = await async_client.get(
            "/api/v1/entities",
            params={"search": f"AssocEdge {run}", "limit": 2, "offset": 2},
        )
        assert r.status_code == 200, r.text
        rows = r.json()["data"]
        assert len(rows) >= 1
        for row in rows:
            assert isinstance(row["video_count"], int)
            assert set(row["by_source"]) == {
                "manual",
                "transcript",
                "title",
                "description",
                "tag",
            }


class TestVideoPanelLanguageFilter:
    async def test_mention_in_other_language_excluded_under_filter(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        vid = f"{_PFX}lang1"[:20]
        await _ensure_video(integration_session_factory, vid)
        entity_id = _uid()
        name = f"AssocEdge Lang {entity_id.hex}"

        async with integration_session_factory() as s:
            s.add(
                NamedEntityDB(
                    id=entity_id,
                    canonical_name=name,
                    canonical_name_normalized=name.lower(),
                    entity_type="person",
                    status="active",
                )
            )
            await s.commit()
            # A visible-name transcript mention in a specific language.
            s.add(
                EntityMentionDB(
                    id=_uid(),
                    entity_id=entity_id,
                    video_id=vid,
                    mention_text=name,
                    mention_source="transcript",
                    detection_method="rule_match",
                    language_code="zz",
                )
            )
            await s.commit()

        async def _present(lang: str | None) -> bool:
            params = {"language_code": lang} if lang else {}
            r = await async_client.get(f"/api/v1/videos/{vid}/entities", params=params)
            assert r.status_code == 200, r.text
            return any(x["entity_id"] == str(entity_id) for x in r.json()["data"])

        # Present with no filter and under its own language; absent under another.
        assert await _present(None) is True
        assert await _present("zz") is True
        assert await _present("qq") is False
