"""
Integration tests for the appears-with panel endpoint (Feature 062, US3).

The centrepiece is the **equality contract** (FR-024b, SC-008a): the count the
panel shows for a partner must equal the ``pagination.total`` the videos list
returns for that pair. Both derive from the same qualification rule, so they
agree by construction -- but only if they also apply the same evidence scope
AND the same video population. The videos list excludes unavailable videos by
default; a co-occurrence count that ignored availability would be inflated, and
a user would be shown one number and land on another.

The plan named this the third-highest risk in the feature and said to assert
it rather than assume it. That is what this module does.
"""

from __future__ import annotations

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
from tests.factories.named_entity_orm_factory import create_named_entity_db

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

# Without this, async tests are silently skipped under coverage.
pytestmark = pytest.mark.asyncio

_CHANNEL_ID = "UCec062co000000000000001"
_PREFIX = "ec062co"
_LANG = "en"
_VIDEOS = [f"{_PREFIX}_v{n}" for n in range(1, 6)]


async def _cleanup(session: AsyncSession) -> None:
    await session.execute(
        delete(EntityMentionDB).where(EntityMentionDB.video_id.in_(_VIDEOS))
    )
    await session.execute(
        delete(NamedEntityDB).where(
            NamedEntityDB.canonical_name_normalized.like(f"{_PREFIX} %")
        )
    )
    await session.execute(delete(VideoDB).where(VideoDB.video_id.in_(_VIDEOS)))
    await session.execute(delete(ChannelDB).where(ChannelDB.channel_id == _CHANNEL_ID))
    await session.commit()


@pytest.fixture
async def seed(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[dict[str, Any], None]:
    """Seed a subject entity with partners of differing strength.

    ===== =========================================================== =========
    Video Mentions                                                    Available
    ===== =========================================================== =========
    v1    subject, alpha, beta                                        yes
    v2    subject, alpha                                              yes
    v3    subject, alpha (alpha in DESCRIPTION -- scope-sensitive)     yes
    v4    subject, gamma                                              **no**
    v5    delta only -- never shares with the subject                  yes
    ===== =========================================================== =========

    So under ``any``: alpha shares 3, beta 1, gamma 0 (its only shared video is
    unavailable). Under ``transcript``: alpha shares 2, because v3's alpha
    mention is description-sourced.

    v4 is the availability trap. A co-occurrence count that ignored
    availability would report gamma as sharing 1 video, and the intersection it
    opens would report 0.
    """
    ids = {name: uuid.uuid4() for name in ("subject", "alpha", "gamma", "delta")}
    # beta and epsilon get FIXED, ordered ids and are inserted in REVERSE id
    # order below. Natural (insertion) order therefore disagrees with the
    # contract's ascending-id tiebreak, so a test on their relative position
    # can actually detect the tiebreak's removal. With random uuid4s the two
    # orders coincide about half the time and the assertion proves nothing.
    ids["beta"] = uuid.UUID(int=0x0EC062C0_0000_4000_8000_000000000001)
    ids["epsilon"] = uuid.UUID(int=0x0EC062C0_0000_4000_8000_00000000FFFF)

    async with integration_session_factory() as session:
        await _cleanup(session)
        session.add(ChannelDB(channel_id=_CHANNEL_ID, title="EC062 Channel"))
        for index, vid in enumerate(_VIDEOS):
            session.add(
                VideoDB(
                    video_id=vid,
                    channel_id=_CHANNEL_ID,
                    title=f"EC062 {vid}",
                    description="co-occurrence fixture",
                    upload_date=datetime(2024, 7, 1, tzinfo=UTC),
                    duration=300,
                    # v4 (index 3) is deliberately unavailable.
                    availability_status="unavailable" if index == 3 else "available",
                )
            )
        for name, entity_id in ids.items():
            session.add(
                create_named_entity_db(
                    id=entity_id,
                    canonical_name=f"{_PREFIX.title()} {name.title()}",
                    canonical_name_normalized=f"{_PREFIX} {name}",
                    entity_type="person",
                    description="fixture",
                )
            )
        await session.commit()

        def mention(
            entity: str, video: str, source: str = "transcript"
        ) -> EntityMentionDB:
            return EntityMentionDB(
                id=uuid.UUID(bytes=uuid7().bytes),
                entity_id=ids[entity],
                segment_id=None,
                video_id=video,
                language_code=_LANG,
                mention_text=f"{_PREFIX} {entity}",
                detection_method="rule_match",
                mention_source=source,
            )

        for row in [
            mention("subject", _VIDEOS[0]),
            mention("alpha", _VIDEOS[0]),
            # epsilon FIRST, though its id sorts after beta's -- see the id
            # assignment above. The tiebreak must reorder them.
            mention("epsilon", _VIDEOS[0]),
            mention("beta", _VIDEOS[0]),
            mention("subject", _VIDEOS[1]),
            mention("alpha", _VIDEOS[1]),
            mention("subject", _VIDEOS[2]),
            mention("alpha", _VIDEOS[2], source="description"),
            mention("subject", _VIDEOS[3]),
            mention("gamma", _VIDEOS[3]),
            mention("delta", _VIDEOS[4]),
        ]:
            session.add(row)
        await session.commit()

    yield {"ids": ids}

    async with integration_session_factory() as session:
        await _cleanup(session)


class TestEqualityContract:
    """FR-024b, SC-008, SC-008a -- the promise the panel makes."""

    @pytest.mark.parametrize("scope", ["any", "transcript"])
    async def test_panel_count_equals_intersection_total(
        self, async_client: AsyncClient, seed: dict[str, Any], scope: str
    ) -> None:
        """Every partner's count equals the total of the pair it opens.

        Verified under BOTH scopes, because the failure mode is scope drift:
        a panel computing under one definition while the intersection computes
        under another agrees on the default and diverges everywhere else.
        """
        subject = seed["ids"]["subject"]
        panel = await async_client.get(
            f"/api/v1/entities/{subject}/co-occurring?min_evidence={scope}"
        )
        assert panel.status_code == 200
        partners = panel.json()["data"]
        assert partners, "fixture must produce at least one partner"

        for partner in partners:
            intersection = await async_client.get(
                f"/api/v1/videos?entity_id={subject}"
                f"&entity_id={partner['entity_id']}"
                f"&min_evidence={scope}&limit=1"
            )
            assert intersection.status_code == 200
            assert partner["shared_video_count"] == (
                intersection.json()["pagination"]["total"]
            ), (
                f"panel says {partner['shared_video_count']} shared videos with "
                f"{partner['canonical_name']} under scope={scope}, but the "
                f"intersection it opens reports "
                f"{intersection.json()['pagination']['total']}"
            )

    async def test_unavailable_shared_video_is_excluded_from_the_count(
        self, async_client: AsyncClient, seed: dict[str, Any]
    ) -> None:
        """The availability trap, asserted directly.

        gamma shares exactly one video with the subject, and that video is
        unavailable. Counting it would inflate the panel and break the equality
        contract, because the videos list would return zero for that pair.
        """
        subject = seed["ids"]["subject"]
        gamma = seed["ids"]["gamma"]
        panel = await async_client.get(f"/api/v1/entities/{subject}/co-occurring")
        listed = {p["entity_id"] for p in panel.json()["data"]}
        assert str(gamma) not in listed


class TestPartnerRanking:
    """R5 -- bounded, ordered, deterministic."""

    async def test_partners_ordered_by_shared_count_descending(
        self, async_client: AsyncClient, seed: dict[str, Any]
    ) -> None:
        subject = seed["ids"]["subject"]
        response = await async_client.get(f"/api/v1/entities/{subject}/co-occurring")
        counts = [p["shared_video_count"] for p in response.json()["data"]]
        assert counts == sorted(counts, reverse=True)

    async def test_tied_partners_are_ordered_by_id_ascending(
        self, async_client: AsyncClient, seed: dict[str, Any]
    ) -> None:
        """The tiebreak makes a bounded list deterministic (R5).

        beta and epsilon each share exactly one video, so the count alone
        cannot order them. Without the ``entity_id`` tiebreak the database is
        free to return either first, and a "reveal more" page could repeat or
        skip one.

        **This test confirms the rule holds; it cannot prove the ORDER BY is
        what makes it hold.** At this fixture size Postgres returns the group
        in ascending-id order anyway -- verified by removing the tiebreak and
        watching this still pass, even with the tied pair given fixed ids and
        inserted in reverse. The structural assertion in
        ``tests/unit/repositories/test_entity_qualification_properties.py``
        covers the gap by inspecting the compiled SQL directly.
        """
        subject = seed["ids"]["subject"]
        beta, epsilon = str(seed["ids"]["beta"]), str(seed["ids"]["epsilon"])

        response = await async_client.get(f"/api/v1/entities/{subject}/co-occurring")
        returned = [p["entity_id"] for p in response.json()["data"]]

        tied_in_order = [e for e in returned if e in {beta, epsilon}]
        assert tied_in_order == sorted([beta, epsilon]), (
            "partners with equal shared counts must be ordered by entity_id "
            "ascending; got " + str(tied_in_order)
        )

    async def test_ordering_is_repeatable_across_requests(
        self, async_client: AsyncClient, seed: dict[str, Any]
    ) -> None:
        subject = seed["ids"]["subject"]
        first = await async_client.get(f"/api/v1/entities/{subject}/co-occurring")
        second = await async_client.get(f"/api/v1/entities/{subject}/co-occurring")
        assert [p["entity_id"] for p in first.json()["data"]] == [
            p["entity_id"] for p in second.json()["data"]
        ]

    async def test_entity_type_travels_with_each_partner(
        self, async_client: AsyncClient, seed: dict[str, Any]
    ) -> None:
        """FR-031 -- the badge renders without a lookup per partner."""
        subject = seed["ids"]["subject"]
        response = await async_client.get(f"/api/v1/entities/{subject}/co-occurring")
        for partner in response.json()["data"]:
            assert partner["entity_type"] == "person"
            assert partner["canonical_name"]

    async def test_limit_bounds_the_list(
        self, async_client: AsyncClient, seed: dict[str, Any]
    ) -> None:
        subject = seed["ids"]["subject"]
        response = await async_client.get(
            f"/api/v1/entities/{subject}/co-occurring?limit=1"
        )
        assert len(response.json()["data"]) == 1


class TestEvidenceScope:
    """FR-024a -- the panel honours the surrounding view's scope."""

    async def test_transcript_scope_narrows_shared_counts(
        self, async_client: AsyncClient, seed: dict[str, Any]
    ) -> None:
        """alpha shares three videos under `any`, two under `transcript`.

        v3's alpha mention is description-sourced, so it stops counting when
        the scope tightens.
        """
        subject = seed["ids"]["subject"]
        alpha = str(seed["ids"]["alpha"])

        def count_for(payload: dict[str, Any]) -> int:
            return next(
                p["shared_video_count"]
                for p in payload["data"]
                if p["entity_id"] == alpha
            )

        any_scope = await async_client.get(f"/api/v1/entities/{subject}/co-occurring")
        transcript = await async_client.get(
            f"/api/v1/entities/{subject}/co-occurring?min_evidence=transcript"
        )
        assert count_for(any_scope.json()) == 3
        assert count_for(transcript.json()) == 2


class TestEdgeCases:
    """FR-024, FR-023a."""

    async def test_entity_with_no_co_occurrences_returns_empty_not_error(
        self, async_client: AsyncClient, seed: dict[str, Any]
    ) -> None:
        """ "Nothing appears alongside this" is an answer, not a failure."""
        delta = seed["ids"]["delta"]
        response = await async_client.get(f"/api/v1/entities/{delta}/co-occurring")
        assert response.status_code == 200
        assert response.json()["data"] == []

    async def test_unknown_entity_is_404(self, async_client: AsyncClient) -> None:
        response = await async_client.get(
            f"/api/v1/entities/{uuid.uuid4()}/co-occurring"
        )
        assert response.status_code == 404

    async def test_malformed_entity_id_is_404(self, async_client: AsyncClient) -> None:
        response = await async_client.get("/api/v1/entities/not-a-uuid/co-occurring")
        assert response.status_code == 404

    async def test_limit_above_maximum_is_rejected(
        self, async_client: AsyncClient, seed: dict[str, Any]
    ) -> None:
        """FR-023a: bounded by a stated rule, never served unbounded."""
        subject = seed["ids"]["subject"]
        response = await async_client.get(
            f"/api/v1/entities/{subject}/co-occurring?limit=10000"
        )
        assert response.status_code == 422

    async def test_zero_limit_is_rejected(
        self, async_client: AsyncClient, seed: dict[str, Any]
    ) -> None:
        subject = seed["ids"]["subject"]
        response = await async_client.get(
            f"/api/v1/entities/{subject}/co-occurring?limit=0"
        )
        assert response.status_code == 422

    async def test_subject_never_lists_itself(
        self, async_client: AsyncClient, seed: dict[str, Any]
    ) -> None:
        """An entity co-occurs with itself in every video it appears in.

        Including it would put a meaningless row at the top of every panel and
        link to a one-entity "intersection".
        """
        subject = seed["ids"]["subject"]
        response = await async_client.get(f"/api/v1/entities/{subject}/co-occurring")
        assert str(subject) not in {p["entity_id"] for p in response.json()["data"]}
