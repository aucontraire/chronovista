"""
Performance tests for the entity intersection filter (Feature 062).

Success criteria tested:
- SC-005 / FR-035: first page with per-entity counts under 2 seconds, at any
  permitted required-set size -- including the selection ceiling, not merely a
  typical two or three.

**Why this file exists at all.** Research R1 measured two formulations of the
qualification query 8.2x apart -- 806 ms versus 98 ms -- returning *identical*
output. No value-based assertion can tell them apart. R9 then integrated the
fast shape into the videos-list query by joining an aggregate subquery, and
recorded that the integrated form was *reasoned* to preserve the win but had
never been measured. This is where that obligation is discharged on every run.

**What these timings do and do not prove.** The seeded corpus here is small by
design, so the absolute numbers are not the feature's real-world latency -- the
authoritative measurement is recorded in ``research.md`` against production
(152k mentions). What this file catches is a *shape* regression: joining
``transcript_segments`` before pagination, or rebuilding the count by hand,
degrades superlinearly and shows up here long before it becomes a 2-second
user-facing problem. The budget is asserted as a ceiling, not as a baseline to
match, per the spec's assumption that production figures are anchors rather
than constants under test.

Run with: pytest tests/performance/ -v -m performance
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import pytest
from httpx import AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from uuid_utils import uuid7

from chronovista.db.models import Channel as ChannelDB
from chronovista.db.models import EntityMention as EntityMentionDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import Video as VideoDB
from chronovista.models.enums import EvidenceScope
from chronovista.repositories.entity_mention_repository import EntityMentionRepository
from tests.factories.named_entity_orm_factory import create_named_entity_db

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

pytestmark = [pytest.mark.asyncio, pytest.mark.performance]

_BUDGET_SECONDS = 2.0
_CHANNEL_ID = "UCep062pf000000000000001"
_PREFIX = "ep062pf"
_VIDEO_COUNT = 150
_ENTITY_COUNT = 12  # >= the selection ceiling of 10, so the ceiling is testable
_VIDEO_IDS = [f"{_PREFIX}_v{n:04d}" for n in range(_VIDEO_COUNT)]


# Function-scoped: `integration_session_factory` is itself function-scoped, so
# a module-scoped fixture cannot consume it. Reseeding per test costs a second
# or so and keeps each measurement independent of the ones before it.
@pytest.fixture
async def perf_seed(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[dict[str, Any], None]:
    """Seed a corpus dense enough that a shape regression is measurable.

    Every video mentions the first four entities, so a four-way intersection
    still returns the full set rather than collapsing to nothing -- an
    intersection that returns zero rows is fast for the wrong reason and would
    hide exactly the regression this file exists to catch.
    """
    entity_ids = [uuid.uuid4() for _ in range(_ENTITY_COUNT)]

    async with integration_session_factory() as session:
        await _cleanup(session, entity_ids)
        session.add(ChannelDB(channel_id=_CHANNEL_ID, title="EP062 Perf Channel"))
        session.add_all(
            VideoDB(
                video_id=vid,
                channel_id=_CHANNEL_ID,
                title=f"EP062 perf {vid}",
                description="performance fixture",
                upload_date=datetime(2024, 6, 1, tzinfo=UTC),
                duration=600,
            )
            for vid in _VIDEO_IDS
        )
        session.add_all(
            create_named_entity_db(
                id=eid,
                canonical_name=f"{_PREFIX.title()} P{index}",
                canonical_name_normalized=f"{_PREFIX} p{index}",
                entity_type="person",
                description="perf fixture",
            )
            for index, eid in enumerate(entity_ids)
        )
        await session.commit()

        mentions = []
        for index, vid in enumerate(_VIDEO_IDS):
            # First four entities in every video; the rest spread out, so
            # larger required sets narrow realistically.
            present = list(entity_ids[:4]) + [
                entity_ids[4 + (index % (_ENTITY_COUNT - 4))]
            ]
            for eid in present:
                # Duplicate rows per (entity, video) -- the real corpus has
                # them, and a fan-out bug shows up here as a timing cliff.
                #
                # Description-sourced with DISTINCT mention_text: the schema
                # permits duplicates per source only where its partial unique
                # index allows. uq_entity_mentions_description keys on
                # (entity_id, video_id, mention_source, mention_text), so
                # varying the text is how a description mention legitimately
                # repeats. Title mentions cannot repeat at all.
                for occurrence in range(3):
                    mentions.append(
                        EntityMentionDB(
                            id=uuid.UUID(bytes=uuid7().bytes),
                            entity_id=eid,
                            segment_id=None,
                            video_id=vid,
                            language_code="en",
                            mention_text=f"{_PREFIX} mention {occurrence}",
                            detection_method="rule_match",
                            mention_source="description",
                        )
                    )
        session.add_all(mentions)
        await session.commit()

    yield {"entity_ids": entity_ids, "mention_count": len(mentions)}

    async with integration_session_factory() as session:
        await _cleanup(session, entity_ids)


async def _cleanup(session: AsyncSession, entity_ids: list[uuid.UUID]) -> None:
    """Remove this module's rows.

    Entities are deleted by NAME, not by the ids passed in: the integration
    database is never reset between runs, and each run generates fresh uuid4s
    while the canonical names stay deterministic. Deleting by id would leave
    the previous run's rows behind and the next run would collide on
    ``uq_named_entity_canonical``.
    """
    await session.execute(
        delete(EntityMentionDB).where(EntityMentionDB.video_id.in_(_VIDEO_IDS))
    )
    await session.execute(
        delete(NamedEntityDB).where(
            NamedEntityDB.canonical_name_normalized.like(f"{_PREFIX} p%")
        )
    )
    await session.execute(delete(VideoDB).where(VideoDB.video_id.in_(_VIDEO_IDS)))
    await session.execute(delete(ChannelDB).where(ChannelDB.channel_id == _CHANNEL_ID))
    await session.commit()


class TestIntersectionLatency:
    """SC-005 / FR-035 -- the budget holds across the permitted range."""

    @pytest.mark.parametrize("set_size", [2, 3, 4, 10])
    async def test_first_page_within_budget(
        self,
        async_client: AsyncClient,
        perf_seed: dict[str, Any],
        set_size: int,
    ) -> None:
        """The budget applies at ANY permitted set size, not just a typical one.

        ``set_size=10`` is the selection ceiling. SC-005 originally bounded
        only "up to four", which left five through ten unspecified -- the gap
        this parametrisation closes.
        """
        params = "&".join(f"entity_id={e}" for e in perf_seed["entity_ids"][:set_size])
        start = time.perf_counter()
        response = await async_client.get(f"/api/v1/videos?{params}&limit=20")
        elapsed = time.perf_counter() - start

        assert response.status_code == 200
        assert elapsed < _BUDGET_SECONDS, (
            f"N={set_size} took {elapsed:.2f}s against a {_BUDGET_SECONDS}s budget. "
            "The most likely cause is a query-shape regression -- "
            "transcript_segments joined before pagination, or the count "
            "rebuilt by hand instead of derived from the filtered query."
        )

    async def test_counting_does_not_dominate(
        self, async_client: AsyncClient, perf_seed: dict[str, Any]
    ) -> None:
        """The pagination count must stay cheap relative to the page itself.

        The count derives from the same filtered query object, so it should
        cost a fraction of the request. If it ever approaches the full request
        time, someone has rebuilt it separately -- which is also how the count
        silently stops matching the rows.
        """
        params = "&".join(f"entity_id={e}" for e in perf_seed["entity_ids"][:2])
        start = time.perf_counter()
        first_page = await async_client.get(f"/api/v1/videos?{params}&limit=20")
        page_time = time.perf_counter() - start

        start = time.perf_counter()
        single = await async_client.get(f"/api/v1/videos?{params}&limit=1")
        single_time = time.perf_counter() - start

        assert first_page.status_code == single.status_code == 200
        # Both requests pay the same count; the 20-row page additionally pays
        # enrichment. Neither should be an order of magnitude off the other.
        assert single_time < page_time * 5 + 0.5


class TestCooccurrencePanelLatency:
    """SC-012 -- the appears-with panel is the feature's slowest query.

    Measured against production it is roughly ten times the intersection
    itself (923 ms worst case, R5), which is why FR-037 requires it to load
    independently of the entity detail page's initial render. A regression here
    would not fail the page; it would make the page feel broken for precisely
    the entities users open most -- the well-connected ones.
    """

    async def test_panel_within_budget_for_the_most_connected_entity(
        self, async_client: AsyncClient, perf_seed: dict[str, Any]
    ) -> None:
        """The first seeded entity appears in every video, so it is the hub."""
        hub = perf_seed["entity_ids"][0]
        start = time.perf_counter()
        response = await async_client.get(f"/api/v1/entities/{hub}/co-occurring")
        elapsed = time.perf_counter() - start

        assert response.status_code == 200
        assert response.json()["data"], "hub entity must have partners"
        assert elapsed < _BUDGET_SECONDS, (
            f"appears-with panel took {elapsed:.2f}s against a "
            f"{_BUDGET_SECONDS}s budget (SC-012)"
        )

    async def test_raising_the_limit_does_not_change_the_cost_class(
        self, async_client: AsyncClient, perf_seed: dict[str, Any]
    ) -> None:
        """The bound caps the RESULT, not the work.

        Grouping and counting scans the same rows either way, so a much larger
        limit should not multiply the time. If it does, the bound is being
        applied after materialising something it should not have.
        """
        hub = perf_seed["entity_ids"][0]

        start = time.perf_counter()
        await async_client.get(f"/api/v1/entities/{hub}/co-occurring?limit=1")
        small = time.perf_counter() - start

        start = time.perf_counter()
        await async_client.get(f"/api/v1/entities/{hub}/co-occurring?limit=50")
        large = time.perf_counter() - start

        assert large < small * 5 + 0.5, f"limit=1 {small:.3f}s vs limit=50 {large:.3f}s"


class TestQueryShape:
    """The regression no timing threshold reliably catches.

    R1's slow formulation returned identical output. On a small fixture it may
    even be fast enough to pass a 2-second budget, so the shape is asserted
    structurally here rather than left to the clock alone.
    """

    async def test_qualification_never_joins_transcript_segments(
        self,
        perf_seed: dict[str, Any],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Timestamps are fetched for the returned page only (R1)."""
        repo = EntityMentionRepository()
        async with integration_session_factory() as session:
            subquery = await repo.build_entity_qualification_subquery(
                session, perf_seed["entity_ids"][:3], EvidenceScope.ANY
            )
        sql = str(subquery.element.compile()).lower()
        assert "transcript_segments" not in sql
        assert "count(distinct" in sql
