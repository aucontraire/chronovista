"""Integration tests for the entity grounding endpoint (Feature 073, #292).

Covers ``POST /api/v1/entities/{entity_id}/grounding`` re-link (US1):
  - 200 returns the new verified link with ZERO previous-link facts (FR-012),
    the confirmed description applied, and one ``reground`` audit row written.
  - 404 for an unknown entity.
  - 422 for a body that fails ``GroundingRequest`` validation.

All tests require the integration database (chronovista_integration_test).
Each test seeds its own entity and cleans up in FK-reverse order (audit-log
rows before the entity) to preserve isolation from other integration files.

The background fact fetch (``_schedule_enrichment``) is patched to a no-op so
these tests exercise the synchronous re-link contract only — never real
Wikidata network I/O — and leave no dangling task. The fetch-side behaviour is
covered separately by the service unit tests and the graceful-degradation test.

Auth: ``require_auth`` is bypassed by patching
``chronovista.api.deps.youtube_oauth``, following the pattern in
``test_entity_creation_integration.py``.
"""

from __future__ import annotations

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

from chronovista.db.models import CanonicalTag as CanonicalTagDB
from chronovista.db.models import Channel as ChannelDB
from chronovista.db.models import EntityMention as EntityMentionDB
from chronovista.db.models import EntityOperationLog as EntityOperationLogDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import TagAlias as TagAliasDB
from chronovista.db.models import TranscriptSegment as TranscriptSegmentDB
from chronovista.db.models import Video as VideoDB
from chronovista.db.models import VideoTag as VideoTagDB
from chronovista.db.models import VideoTranscript as VideoTranscriptDB
from tests.factories.named_entity_orm_factory import create_named_entity_db

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

pytestmark = pytest.mark.asyncio

_WRONG_QID = "Q_EGT_WRONG"
_RIGHT_QID = "Q_EGT_RIGHT"
_OLD_DBPEDIA = "http://dbpedia.org/resource/Egt_Wrong"


def _grounding_url(entity_id: str) -> str:
    """Return the grounding endpoint URL for an entity."""
    return f"/api/v1/entities/{entity_id}/grounding"


def _authenticated():
    """Patch oauth so ``require_auth`` accepts the request as authenticated."""
    return patch("chronovista.api.deps.youtube_oauth")


def _no_background_fetch():
    """Patch the detached enrichment scheduler to a no-op (no real network)."""
    return patch(
        "chronovista.api.routers.entity_mentions._schedule_enrichment",
        lambda *a, **k: None,
    )


async def _delete_entity(session: AsyncSession, entity_id: uuid.UUID) -> None:
    """Remove an entity and its audit rows in FK-reverse order."""
    await session.execute(
        delete(EntityOperationLogDB).where(EntityOperationLogDB.entity_id == entity_id)
    )
    await session.execute(delete(NamedEntityDB).where(NamedEntityDB.id == entity_id))
    await session.commit()


class TestRegroundRelink:
    """POST /entities/{id}/grounding — re-link branch (US1)."""

    @pytest.fixture
    async def seed_mislinked_entity(
        self,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Seed a person entity linked to the WRONG QID with stale facts.

        Yields ``{"entity_id", "entity_id_str"}``. Cleanup removes the entity
        and any audit rows the test wrote.
        """
        entity_id = uuid.UUID(bytes=uuid7().bytes)

        async with integration_session_factory() as session:
            entity = NamedEntityDB(
                id=entity_id,
                canonical_name="Egt Mislinked Person",
                canonical_name_normalized="egt mislinked person",
                entity_type="person",
                status="active",
                discovery_method="user_created",
                confidence=1.0,
                external_ids={
                    "wikidata": {
                        "id": _WRONG_QID,
                        "verified": True,
                        "status": "verified",
                    },
                    "dbpedia": {"id": _OLD_DBPEDIA},
                },
                properties={"occupation": "wrong-person-fact"},
            )
            session.add(entity)
            await session.commit()

        yield {"entity_id": entity_id, "entity_id_str": str(entity_id)}

        async with integration_session_factory() as session:
            await _delete_entity(session, entity_id)

    async def test_relink_returns_new_link_with_no_previous_facts(
        self,
        async_client: AsyncClient,
        seed_mislinked_entity: dict[str, Any],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Re-link → 200 with the new verified link, no stale facts, audit row.

        Verifies (FR-012 / FR-003 / FR-005 / FR-011):
        - 200 response.
        - enrichment.identifiers holds the new verified wikidata link (Q_RIGHT);
          the old DBpedia link is gone.
        - enrichment.properties is empty — none of the previous link's facts leak.
        - the confirmed description is applied.
        - exactly one 'reground' audit row records before/after link + description.
        """
        entity_uuid = seed_mislinked_entity["entity_id"]
        entity_id_str = seed_mislinked_entity["entity_id_str"]

        with _authenticated() as mock_oauth, _no_background_fetch():
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.post(
                _grounding_url(entity_id_str),
                json={
                    "approved_identifier": {"source": "wikidata", "id": _RIGHT_QID},
                    "description": "curator-confirmed description",
                },
            )

        assert (
            response.status_code == 200
        ), f"Expected 200 but got {response.status_code}: {response.text}"
        data = response.json()["data"]

        # Description applied synchronously.
        assert data["description"] == "curator-confirmed description"

        enrichment = data["enrichment"]
        # New verified wikidata link present; old DBpedia link gone (FR-003).
        by_source = {i["source"]: i for i in enrichment["identifiers"]}
        assert "wikidata" in by_source, f"wikidata link missing: {enrichment}"
        assert by_source["wikidata"]["id"] == _RIGHT_QID
        assert by_source["wikidata"]["verified"] is True
        assert "dbpedia" not in by_source, "old dbpedia link must be dropped"

        # No previous-link facts leak (FR-012) — pending, not stale.
        assert enrichment["properties"] == {}, (
            f"Expected empty properties (facts pending), "
            f"got: {enrichment['properties']}"
        )

        # DB: link + facts persisted; exactly one 'reground' audit row.
        async with integration_session_factory() as session:
            db_entity = await session.get(NamedEntityDB, entity_uuid)
            assert db_entity is not None
            assert db_entity.external_ids["wikidata"]["id"] == _RIGHT_QID
            assert "dbpedia" not in db_entity.external_ids
            assert db_entity.properties == {}
            assert db_entity.description == "curator-confirmed description"

            logs = (
                (
                    await session.execute(
                        select(EntityOperationLogDB).where(
                            EntityOperationLogDB.entity_id == entity_uuid
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert len(logs) == 1, f"Expected 1 audit row, found {len(logs)}"
            log = logs[0]
            assert log.operation_type == "reground"
            rollback = log.rollback_data
            assert rollback["before"]["wikidata_id"] == _WRONG_QID
            assert rollback["before"]["dbpedia_id"] == _OLD_DBPEDIA
            assert rollback["after"]["wikidata_id"] == _RIGHT_QID
            assert rollback["after"]["dbpedia_id"] is None
            assert log.performed_by

    async def test_relink_unknown_entity_returns_404(
        self,
        async_client: AsyncClient,
    ) -> None:
        """Re-link on a non-existent entity → 404."""
        unknown = str(uuid.UUID(bytes=uuid7().bytes))
        with _authenticated() as mock_oauth, _no_background_fetch():
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.post(
                _grounding_url(unknown),
                json={
                    "approved_identifier": {"source": "wikidata", "id": _RIGHT_QID},
                },
            )
        assert (
            response.status_code == 404
        ), f"Expected 404 for unknown entity, got {response.status_code}: {response.text}"

    async def test_relink_invalid_body_returns_422(
        self,
        async_client: AsyncClient,
        seed_mislinked_entity: dict[str, Any],
    ) -> None:
        """A body failing GroundingRequest validation → 422.

        ``approved_identifier.source`` is constrained to Literal["wikidata"];
        an unsupported source must be rejected before any DB work.
        """
        entity_id_str = seed_mislinked_entity["entity_id_str"]
        with _authenticated() as mock_oauth, _no_background_fetch():
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.post(
                _grounding_url(entity_id_str),
                json={
                    "approved_identifier": {"source": "freebase", "id": _RIGHT_QID},
                },
            )
        assert response.status_code == 422, (
            f"Expected 422 for invalid approved_identifier, "
            f"got {response.status_code}: {response.text}"
        )


class TestRegroundRefresh:
    """POST /entities/{id}/grounding — refresh branch (US2, approved_identifier omitted)."""

    @pytest.fixture
    async def seed_linked_entity_with_facts(
        self,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Seed a person entity with a current wikidata link and some facts."""
        entity_id = uuid.UUID(bytes=uuid7().bytes)
        async with integration_session_factory() as session:
            entity = NamedEntityDB(
                id=entity_id,
                canonical_name="Egt Linked Person",
                canonical_name_normalized="egt linked person",
                entity_type="person",
                status="active",
                discovery_method="user_created",
                confidence=1.0,
                external_ids={
                    "wikidata": {
                        "id": _RIGHT_QID,
                        "verified": True,
                        "status": "verified",
                    }
                },
                properties={"occupation": "existing-fact"},
            )
            session.add(entity)
            await session.commit()
        yield {"entity_id": entity_id, "entity_id_str": str(entity_id)}
        async with integration_session_factory() as session:
            await _delete_entity(session, entity_id)

    @pytest.fixture
    async def seed_unlinked_entity(
        self,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Seed a person entity with NO current link."""
        entity_id = uuid.UUID(bytes=uuid7().bytes)
        async with integration_session_factory() as session:
            entity = NamedEntityDB(
                id=entity_id,
                canonical_name="Egt Unlinked Person",
                canonical_name_normalized="egt unlinked person",
                entity_type="person",
                status="active",
                discovery_method="user_created",
                confidence=1.0,
                external_ids={},
                properties={},
            )
            session.add(entity)
            await session.commit()
        yield {"entity_id": entity_id, "entity_id_str": str(entity_id)}
        async with integration_session_factory() as session:
            await _delete_entity(session, entity_id)

    async def test_refresh_keeps_link_and_facts_and_audits_refetch(
        self,
        async_client: AsyncClient,
        seed_linked_entity_with_facts: dict[str, Any],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Refresh (no approved_identifier) → 200, link + facts unchanged, 'refetch' audit.

        Verifies (FR-004 sync side / FR-006 / FR-009): the endpoint dispatches
        the refresh branch, leaves the current link, description, and existing
        facts in place synchronously (the fetch is stubbed), and writes exactly
        one 'refetch' audit row.
        """
        entity_uuid = seed_linked_entity_with_facts["entity_id"]
        entity_id_str = seed_linked_entity_with_facts["entity_id_str"]

        with _authenticated() as mock_oauth, _no_background_fetch():
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.post(
                _grounding_url(entity_id_str),
                json={},  # no approved_identifier → refresh
            )

        assert (
            response.status_code == 200
        ), f"Expected 200 but got {response.status_code}: {response.text}"
        enrichment = response.json()["data"]["enrichment"]
        by_source = {i["source"]: i for i in enrichment["identifiers"]}
        assert by_source["wikidata"]["id"] == _RIGHT_QID
        # Facts stay visible synchronously (fetch stubbed) — not blanked.
        assert enrichment["properties"] == {"occupation": "existing-fact"}

        async with integration_session_factory() as session:
            db_entity = await session.get(NamedEntityDB, entity_uuid)
            assert db_entity is not None
            assert db_entity.external_ids["wikidata"]["id"] == _RIGHT_QID
            assert db_entity.properties == {"occupation": "existing-fact"}
            logs = (
                (
                    await session.execute(
                        select(EntityOperationLogDB).where(
                            EntityOperationLogDB.entity_id == entity_uuid
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert len(logs) == 1
            assert logs[0].operation_type == "refetch"

    async def test_refresh_unlinked_entity_returns_400(
        self,
        async_client: AsyncClient,
        seed_unlinked_entity: dict[str, Any],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Refresh on an entity with no current link → 400, no audit row written."""
        entity_uuid = seed_unlinked_entity["entity_id"]
        entity_id_str = seed_unlinked_entity["entity_id_str"]

        with _authenticated() as mock_oauth, _no_background_fetch():
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.post(_grounding_url(entity_id_str), json={})

        assert (
            response.status_code == 400
        ), f"Expected 400 for unlinked refresh, got {response.status_code}: {response.text}"

        async with integration_session_factory() as session:
            logs = (
                (
                    await session.execute(
                        select(EntityOperationLogDB).where(
                            EntityOperationLogDB.entity_id == entity_uuid
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert logs == [], "No audit row should be written on a 400 refresh"


class TestGroundingAuditTrail:
    """POST /entities/{id}/grounding — US3 traceability across both operations."""

    @pytest.fixture
    async def seed_mislinked_entity(
        self,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Seed a person entity linked to the WRONG QID with a description."""
        entity_id = uuid.UUID(bytes=uuid7().bytes)
        async with integration_session_factory() as session:
            entity = NamedEntityDB(
                id=entity_id,
                canonical_name="Egt Audit Person",
                canonical_name_normalized="egt audit person",
                entity_type="person",
                status="active",
                discovery_method="user_created",
                confidence=1.0,
                external_ids={
                    "wikidata": {
                        "id": _WRONG_QID,
                        "verified": True,
                        "status": "verified",
                    }
                },
                properties={},
                description="old description",
            )
            session.add(entity)
            await session.commit()
        yield {"entity_id": entity_id, "entity_id_str": str(entity_id)}
        async with integration_session_factory() as session:
            await _delete_entity(session, entity_id)

    async def test_relink_then_refresh_records_both_audit_rows(
        self,
        async_client: AsyncClient,
        seed_mislinked_entity: dict[str, Any],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """A re-link followed by a refresh writes one 'reground' then one 'refetch'
        row, each with the correct before/after link + description (FR-005).
        """
        entity_uuid = seed_mislinked_entity["entity_id"]
        entity_id_str = seed_mislinked_entity["entity_id_str"]

        with _authenticated() as mock_oauth, _no_background_fetch():
            mock_oauth.is_authenticated.return_value = True
            relink = await async_client.post(
                _grounding_url(entity_id_str),
                json={
                    "approved_identifier": {"source": "wikidata", "id": _RIGHT_QID},
                    "description": "new description",
                },
            )
            assert relink.status_code == 200, relink.text
            refresh = await async_client.post(_grounding_url(entity_id_str), json={})
            assert refresh.status_code == 200, refresh.text

        async with integration_session_factory() as session:
            logs = (
                (
                    await session.execute(
                        select(EntityOperationLogDB)
                        .where(EntityOperationLogDB.entity_id == entity_uuid)
                        .order_by(EntityOperationLogDB.performed_at)
                    )
                )
                .scalars()
                .all()
            )
            assert [log.operation_type for log in logs] == ["reground", "refetch"]

            reground = logs[0].rollback_data
            assert reground["before"]["wikidata_id"] == _WRONG_QID
            assert reground["before"]["description"] == "old description"
            assert reground["after"]["wikidata_id"] == _RIGHT_QID
            assert reground["after"]["description"] == "new description"

            refetch = logs[1].rollback_data
            # Refresh keeps the (now-corrected) link and description on both sides.
            assert refetch["before"]["wikidata_id"] == _RIGHT_QID
            assert refetch["after"]["wikidata_id"] == _RIGHT_QID
            assert refetch["before"]["description"] == "new description"
            assert refetch["after"]["description"] == "new description"


class TestRegroundCrossFeatureContract:
    """A re-ground must NOT change mentions, tag associations, or co-occurrence.

    The Cross-Feature Data Contract (constitution): a mutation that shares data
    with other features must be verified through every downstream consumer.
    Re-grounding touches only the entity's link / facts / description, so the
    mention count, entity->videos associations (mention AND tag sourced), and
    co-occurrence results must be byte-identical before and after (FR-006).
    """

    _CHANNEL_ID = "UCegtxf00000000000001"  # <= 24 chars
    _VIDEO_ID = "egtxf_vid0001"  # <= 20 chars
    _LANG = "en"
    _TAG = "Egt Xf Tag"
    _TAG_NORM = "egt xf tag"

    @pytest.fixture
    async def seed_associated_entity(
        self,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Seed a mislinked entity with a mention, a tag association, and a
        co-occurring partner entity sharing the same video."""
        main_id = uuid.UUID(bytes=uuid7().bytes)
        partner_id = uuid.UUID(bytes=uuid7().bytes)
        tag_id = uuid.UUID(bytes=uuid7().bytes)

        async def _wipe(session: AsyncSession) -> None:
            await session.execute(
                delete(VideoTagDB).where(VideoTagDB.video_id == self._VIDEO_ID)
            )
            await session.execute(
                delete(EntityMentionDB).where(
                    EntityMentionDB.video_id == self._VIDEO_ID
                )
            )
            await session.execute(
                delete(TranscriptSegmentDB).where(
                    TranscriptSegmentDB.video_id == self._VIDEO_ID
                )
            )
            await session.execute(
                delete(VideoTranscriptDB).where(
                    VideoTranscriptDB.video_id == self._VIDEO_ID
                )
            )
            await session.execute(
                delete(TagAliasDB).where(TagAliasDB.normalized_form == self._TAG_NORM)
            )
            await session.execute(
                delete(CanonicalTagDB).where(
                    CanonicalTagDB.normalized_form == self._TAG_NORM
                )
            )
            await session.execute(
                delete(EntityOperationLogDB).where(
                    EntityOperationLogDB.entity_id.in_([main_id, partner_id])
                )
            )
            await session.execute(
                delete(NamedEntityDB).where(NamedEntityDB.id.in_([main_id, partner_id]))
            )
            await session.execute(
                delete(VideoDB).where(VideoDB.video_id == self._VIDEO_ID)
            )
            await session.execute(
                delete(ChannelDB).where(ChannelDB.channel_id == self._CHANNEL_ID)
            )
            await session.commit()

        async with integration_session_factory() as session:
            session.add(ChannelDB(channel_id=self._CHANNEL_ID, title="EGT XF Channel"))
            session.add(
                VideoDB(
                    video_id=self._VIDEO_ID,
                    channel_id=self._CHANNEL_ID,
                    title="EGT XF Video",
                    description="cross-feature grounding test",
                    upload_date=datetime(2024, 2, 1, tzinfo=UTC),
                    duration=120,
                )
            )
            await session.commit()

            session.add(
                VideoTranscriptDB(
                    video_id=self._VIDEO_ID,
                    language_code=self._LANG,
                    transcript_text="Egt main and partner appear here.",
                    transcript_type="MANUAL",
                    download_reason="USER_REQUEST",
                    is_cc=False,
                    is_auto_synced=False,
                    track_kind="standard",
                )
            )
            await session.commit()

            segment = TranscriptSegmentDB(
                video_id=self._VIDEO_ID,
                language_code=self._LANG,
                text="Egt main and partner appear here.",
                start_time=0.0,
                duration=5.0,
                end_time=5.0,
                sequence_number=0,
                has_correction=False,
            )
            session.add(segment)
            await session.commit()
            segment_id = segment.id

            session.add(
                create_named_entity_db(
                    id=main_id,
                    canonical_name="Egt Main Entity",
                    canonical_name_normalized="egt main entity",
                    entity_type="person",
                    description="seed",
                )
            )
            session.add(
                create_named_entity_db(
                    id=partner_id,
                    canonical_name="Egt Partner Entity",
                    canonical_name_normalized="egt partner entity",
                    entity_type="person",
                    description="seed",
                )
            )
            # Wrong link on the main entity (this is what the test re-grounds).
            await session.commit()
            main = await session.get(NamedEntityDB, main_id)
            assert main is not None
            main.external_ids = {
                "wikidata": {
                    "id": _WRONG_QID,
                    "verified": True,
                    "status": "verified",
                }
            }
            # Denormalized mention counter (surfaced by the detail endpoint as
            # ``mention_count``); reground must leave it untouched.
            main.mention_count = 1
            await session.commit()

            # Both entities mentioned in the same video → co-occurrence.
            for ent_id in (main_id, partner_id):
                session.add(
                    EntityMentionDB(
                        id=uuid.UUID(bytes=uuid7().bytes),
                        entity_id=ent_id,
                        segment_id=segment_id,
                        video_id=self._VIDEO_ID,
                        language_code=self._LANG,
                        mention_text="Egt",
                        detection_method="manual",
                        confidence=1.0,
                    )
                )
            # Canonical tag linked to the main entity + its alias + a matching
            # video tag → a tag-sourced association on the main entity. The join
            # is entity → canonical_tag → tag_alias.raw_form → video_tags.tag
            # (Feature 053), so the TagAlias bridge row is required.
            session.add(
                CanonicalTagDB(
                    id=tag_id,
                    canonical_form=self._TAG,
                    normalized_form=self._TAG_NORM,
                    alias_count=1,
                    video_count=1,
                    status="active",
                    entity_id=main_id,
                    entity_type="person",
                )
            )
            session.add(
                TagAliasDB(
                    id=uuid.UUID(bytes=uuid7().bytes),
                    raw_form=self._TAG,
                    normalized_form=self._TAG_NORM,
                    canonical_tag_id=tag_id,
                    creation_method="auto_normalize",
                    occurrence_count=1,
                )
            )
            session.add(VideoTagDB(video_id=self._VIDEO_ID, tag=self._TAG, tag_order=0))
            await session.commit()

        yield {"main_id": str(main_id), "partner_id": str(partner_id)}

        async with integration_session_factory() as session:
            await _wipe(session)

    async def test_reground_preserves_all_cross_feature_reads(
        self,
        async_client: AsyncClient,
        seed_associated_entity: dict[str, Any],
    ) -> None:
        main_id = seed_associated_entity["main_id"]
        partner_id = seed_associated_entity["partner_id"]

        async def snapshot() -> dict[str, Any]:
            detail = (await async_client.get(f"/api/v1/entities/{main_id}")).json()[
                "data"
            ]
            videos = (
                await async_client.get(f"/api/v1/entities/{main_id}/videos")
            ).json()["data"]
            cooc = (
                await async_client.get(f"/api/v1/entities/{main_id}/co-occurring")
            ).json()["data"]
            return {
                "mention_count": detail["mention_count"],
                "video_count": detail["video_count"],
                "by_source": detail["by_source"],
                "videos": sorted(
                    (v["video_id"], tuple(sorted(v["sources"]))) for v in videos
                ),
                "cooccurring": sorted(
                    (c["entity_id"], c["shared_video_count"]) for c in cooc
                ),
            }

        with _authenticated() as mock_oauth, _no_background_fetch():
            mock_oauth.is_authenticated.return_value = True

            before = await snapshot()

            # The seed must be non-trivial, else equality is vacuous.
            assert before["mention_count"] >= 1
            assert before["video_count"] >= 1
            assert any(cid == partner_id for cid, _ in before["cooccurring"])
            # The tag association contributes a "tag" source to the video.
            assert any("tag" in srcs for _vid, srcs in before["videos"])

            relink = await async_client.post(
                _grounding_url(main_id),
                json={
                    "approved_identifier": {"source": "wikidata", "id": _RIGHT_QID},
                    "description": "regrounded",
                },
            )
            assert relink.status_code == 200, relink.text

            after = await snapshot()

        assert after == before, (
            "Re-grounding changed a cross-feature read that it must not touch "
            f"(FR-006).\nbefore={before}\nafter={after}"
        )
