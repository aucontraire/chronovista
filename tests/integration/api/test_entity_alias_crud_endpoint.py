"""Integration tests for entity-alias delete + name/type edit (#289).

Covers the CRUD gap filled by #289 on
``/api/v1/entities/{entity_id}/aliases/{alias_id}``:
  - DELETE removes the alias (200 returns the deleted summary; row gone), with
    404 ownership/existence guards and no collateral change on rejection.
  - PATCH now edits ``alias_name`` and ``alias_type`` (not just
    ``case_sensitive``): rename re-normalizes, a rename colliding with another
    of the entity's aliases is 409, a case/accent-only rename onto the alias's
    OWN normalized form is allowed, and an empty body is 422.

Requires the integration database (chronovista_integration_test).

Auth: ``require_auth`` is bypassed by patching
``chronovista.api.deps.youtube_oauth`` (same pattern as the sibling alias
endpoint tests).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import Channel as ChannelDB
from chronovista.db.models import EntityAlias as EntityAliasDB
from chronovista.db.models import EntityMention as EntityMentionDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import TranscriptSegment as TranscriptSegmentDB
from chronovista.db.models import Video as VideoDB
from chronovista.db.models import VideoTranscript as VideoTranscriptDB
from tests.factories.named_entity_orm_factory import create_named_entity_db

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

pytestmark = pytest.mark.asyncio

_PREFIX = "eac289"
_NORMS = [f"{_PREFIX} primary", f"{_PREFIX} other"]


def _url(entity_id: uuid.UUID, alias_id: uuid.UUID) -> str:
    return f"/api/v1/entities/{entity_id}/aliases/{alias_id}"


def _auth():  # type: ignore[no-untyped-def]
    return patch("chronovista.api.deps.youtube_oauth")


async def _purge(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as session:
        ids = (
            (
                await session.execute(
                    select(NamedEntityDB.id).where(
                        NamedEntityDB.canonical_name_normalized.in_(_NORMS)
                    )
                )
            )
            .scalars()
            .all()
        )
        if ids:
            await session.execute(
                delete(EntityAliasDB).where(EntityAliasDB.entity_id.in_(list(ids)))
            )
            await session.execute(
                delete(NamedEntityDB).where(NamedEntityDB.id.in_(list(ids)))
            )
        await session.commit()


async def _seed_entity(
    factory: async_sessionmaker[AsyncSession],
    *,
    normalized: str,
) -> uuid.UUID:
    entity_id = uuid.uuid4()
    async with factory() as session:
        session.add(
            create_named_entity_db(
                id=entity_id,
                canonical_name=normalized.title(),
                canonical_name_normalized=normalized,
                entity_type="person",
            )
        )
        await session.commit()
    return entity_id


async def _add_alias(
    factory: async_sessionmaker[AsyncSession],
    *,
    entity_id: uuid.UUID,
    alias_name: str,
    normalized: str,
    occurrence_count: int = 0,
) -> uuid.UUID:
    alias_id = uuid.uuid4()
    async with factory() as session:
        session.add(
            EntityAliasDB(
                id=alias_id,
                entity_id=entity_id,
                alias_name=alias_name,
                alias_name_normalized=normalized,
                alias_type="name_variant",
                occurrence_count=occurrence_count,
            )
        )
        await session.commit()
    return alias_id


@pytest.fixture
async def seeded(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[dict[str, uuid.UUID], None]:
    """Seed one entity with two aliases: 'Aardvark' (matched 3×) and 'Bumblebee'."""
    await _purge(integration_session_factory)
    entity_id = await _seed_entity(
        integration_session_factory, normalized=f"{_PREFIX} primary"
    )
    alias_a = await _add_alias(
        integration_session_factory,
        entity_id=entity_id,
        alias_name="Aardvark",
        normalized="aardvark",
        occurrence_count=3,
    )
    alias_b = await _add_alias(
        integration_session_factory,
        entity_id=entity_id,
        alias_name="Bumblebee",
        normalized="bumblebee",
    )
    yield {"entity_id": entity_id, "alias_a": alias_a, "alias_b": alias_b}
    await _purge(integration_session_factory)


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------


class TestDeleteEntityAlias:
    async def test_delete_removes_the_row_and_returns_summary(
        self,
        async_client: AsyncClient,
        seeded: dict[str, uuid.UUID],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        entity_id, alias_a = seeded["entity_id"], seeded["alias_a"]
        with _auth() as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            resp = await async_client.delete(_url(entity_id, alias_a))
        assert resp.status_code == 200, resp.text
        # Returns the deleted alias (incl. occurrence_count as a signal).
        data = resp.json()["data"]
        assert data["alias_name"] == "Aardvark"
        assert data["occurrence_count"] == 3

        async with integration_session_factory() as session:
            gone = (
                await session.execute(
                    select(EntityAliasDB).where(EntityAliasDB.id == alias_a)
                )
            ).scalar_one_or_none()
            assert gone is None, "alias row must be deleted"
            # The sibling alias is untouched.
            others = (
                (
                    await session.execute(
                        select(EntityAliasDB.id).where(
                            EntityAliasDB.entity_id == entity_id
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert others == [seeded["alias_b"]]

    async def test_delete_alias_of_another_entity_is_404_and_no_op(
        self,
        async_client: AsyncClient,
        seeded: dict[str, uuid.UUID],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        alias_a = seeded["alias_a"]
        other_entity = await _seed_entity(
            integration_session_factory, normalized=f"{_PREFIX} other"
        )
        with _auth() as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            resp = await async_client.delete(_url(other_entity, alias_a))
        assert resp.status_code == 404, resp.text
        # Rejected delete must not remove the alias.
        async with integration_session_factory() as session:
            still = (
                await session.execute(
                    select(EntityAliasDB).where(EntityAliasDB.id == alias_a)
                )
            ).scalar_one_or_none()
            assert still is not None

    async def test_delete_unknown_alias_is_404(
        self, async_client: AsyncClient, seeded: dict[str, uuid.UUID]
    ) -> None:
        entity_id = seeded["entity_id"]
        with _auth() as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            resp = await async_client.delete(_url(entity_id, uuid.uuid4()))
        assert resp.status_code == 404, resp.text

    async def test_delete_unknown_entity_is_404(
        self, async_client: AsyncClient, seeded: dict[str, uuid.UUID]
    ) -> None:
        alias_a = seeded["alias_a"]
        with _auth() as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            resp = await async_client.delete(_url(uuid.uuid4(), alias_a))
        assert resp.status_code == 404, resp.text


# ---------------------------------------------------------------------------
# PATCH name / type
# ---------------------------------------------------------------------------


class TestEditEntityAliasNameType:
    async def test_rename_updates_name_and_normalized(
        self,
        async_client: AsyncClient,
        seeded: dict[str, uuid.UUID],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        entity_id, alias_a = seeded["entity_id"], seeded["alias_a"]
        with _auth() as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            resp = await async_client.patch(
                _url(entity_id, alias_a), json={"alias_name": "Anteater"}
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["alias_name"] == "Anteater"

        async with integration_session_factory() as session:
            alias = (
                await session.execute(
                    select(EntityAliasDB).where(EntityAliasDB.id == alias_a)
                )
            ).scalar_one()
            assert alias.alias_name == "Anteater"
            assert alias.alias_name_normalized == "anteater"

    async def test_retype_updates_type(
        self,
        async_client: AsyncClient,
        seeded: dict[str, uuid.UUID],
    ) -> None:
        entity_id, alias_a = seeded["entity_id"], seeded["alias_a"]
        with _auth() as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            resp = await async_client.patch(
                _url(entity_id, alias_a), json={"alias_type": "nickname"}
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["alias_type"] == "nickname"

    async def test_combined_name_type_case_in_one_patch(
        self,
        async_client: AsyncClient,
        seeded: dict[str, uuid.UUID],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        entity_id, alias_a = seeded["entity_id"], seeded["alias_a"]
        with _auth() as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            resp = await async_client.patch(
                _url(entity_id, alias_a),
                json={
                    "alias_name": "Anteater",
                    "alias_type": "former_name",
                    "case_sensitive": True,
                },
            )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["alias_name"] == "Anteater"
        assert data["alias_type"] == "former_name"
        assert data["case_sensitive"] is True

    async def test_rename_colliding_with_sibling_is_409(
        self,
        async_client: AsyncClient,
        seeded: dict[str, uuid.UUID],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        # Renaming Bumblebee to a variant of Aardvark (same entity) must 409 —
        # accents/case are folded, so "AARDVARK" collides with "aardvark".
        entity_id, alias_b = seeded["entity_id"], seeded["alias_b"]
        with _auth() as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            resp = await async_client.patch(
                _url(entity_id, alias_b), json={"alias_name": "AARDVARK"}
            )
        assert resp.status_code == 409, resp.text
        # The rejected rename must leave Bumblebee unchanged.
        async with integration_session_factory() as session:
            alias = (
                await session.execute(
                    select(EntityAliasDB).where(EntityAliasDB.id == alias_b)
                )
            ).scalar_one()
            assert alias.alias_name == "Bumblebee"

    async def test_case_only_rename_onto_own_normalized_is_allowed(
        self,
        async_client: AsyncClient,
        seeded: dict[str, uuid.UUID],
    ) -> None:
        # "AARDVARK" normalizes to the alias's OWN current normalized form —
        # that is a display-casing change, not a collision.
        entity_id, alias_a = seeded["entity_id"], seeded["alias_a"]
        with _auth() as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            resp = await async_client.patch(
                _url(entity_id, alias_a), json={"alias_name": "AARDVARK"}
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["alias_name"] == "AARDVARK"

    async def test_empty_body_is_422(
        self,
        async_client: AsyncClient,
        seeded: dict[str, uuid.UUID],
    ) -> None:
        entity_id, alias_a = seeded["entity_id"], seeded["alias_a"]
        with _auth() as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            resp = await async_client.patch(_url(entity_id, alias_a), json={})
        assert resp.status_code == 422, resp.text


class TestDeleteRemovesAutoMentions:
    """Deleting an alias removes its auto-detected associations (#289, Level 1).

    Auto-detected (``rule_match``) mentions of the deleted alias are removed so
    the association does not linger as an illusion; hand-made (``manual``) and
    correction-derived (``user_correction``) mentions are preserved, and a
    sibling alias's mentions are untouched. The entity's mention counter is
    recomputed.
    """

    _CHANNEL_ID = "UCeac289crud00000001"  # <= 24 chars
    _VIDEO_ID = "eac289_vid01"  # <= 20 chars
    _LANG = "en"
    _ENTITY_NORM = f"{_PREFIX} primary"  # reuses the purge set (_NORMS)

    @pytest.fixture
    async def seeded_with_mentions(
        self,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> AsyncGenerator[dict[str, uuid.UUID], None]:
        entity_id = uuid.uuid4()
        alias_aardvark = uuid.uuid4()
        alias_bumblebee = uuid.uuid4()

        async def _wipe(session: AsyncSession) -> None:
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
            ids = (
                (
                    await session.execute(
                        select(NamedEntityDB.id).where(
                            NamedEntityDB.canonical_name_normalized == self._ENTITY_NORM
                        )
                    )
                )
                .scalars()
                .all()
            )
            if ids:
                await session.execute(
                    delete(EntityAliasDB).where(EntityAliasDB.entity_id.in_(list(ids)))
                )
                await session.execute(
                    delete(NamedEntityDB).where(NamedEntityDB.id.in_(list(ids)))
                )
            await session.execute(
                delete(VideoDB).where(VideoDB.video_id == self._VIDEO_ID)
            )
            await session.execute(
                delete(ChannelDB).where(ChannelDB.channel_id == self._CHANNEL_ID)
            )
            await session.commit()

        async with integration_session_factory() as session:
            await _wipe(session)
            session.add(
                ChannelDB(channel_id=self._CHANNEL_ID, title="EAC289 CRUD Channel")
            )
            session.add(
                VideoDB(
                    video_id=self._VIDEO_ID,
                    channel_id=self._CHANNEL_ID,
                    title="EAC289 CRUD Video",
                    description="alias-delete cascade test",
                    upload_date=datetime(2024, 4, 1, tzinfo=UTC),
                    duration=90,
                )
            )
            await session.commit()
            session.add(
                VideoTranscriptDB(
                    video_id=self._VIDEO_ID,
                    language_code=self._LANG,
                    transcript_text="Aardvark and Bumblebee appear here.",
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
                text="Aardvark and Bumblebee appear here.",
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
                    id=entity_id,
                    canonical_name="Eac289 Primary",
                    canonical_name_normalized=self._ENTITY_NORM,
                    entity_type="person",
                )
            )
            await session.flush()
            for aid, name, norm in (
                (alias_aardvark, "Aardvark", "aardvark"),
                (alias_bumblebee, "Bumblebee", "bumblebee"),
            ):
                session.add(
                    EntityAliasDB(
                        id=aid,
                        entity_id=entity_id,
                        alias_name=name,
                        alias_name_normalized=norm,
                        alias_type="name_variant",
                        occurrence_count=0,
                    )
                )
            # Four mentions on the same segment: three of "Aardvark" (one per
            # detection method) and one auto "Bumblebee".
            for text, method in (
                ("Aardvark", "rule_match"),
                ("Aardvark", "manual"),
                ("Aardvark", "user_correction"),
                ("Bumblebee", "rule_match"),
            ):
                session.add(
                    EntityMentionDB(
                        id=uuid.UUID(bytes=uuid.uuid4().bytes),
                        entity_id=entity_id,
                        segment_id=segment_id,
                        video_id=self._VIDEO_ID,
                        language_code=self._LANG,
                        mention_text=text,
                        detection_method=method,
                        confidence=1.0,
                    )
                )
            await session.commit()

        yield {
            "entity_id": entity_id,
            "alias_aardvark": alias_aardvark,
            "alias_bumblebee": alias_bumblebee,
        }
        async with integration_session_factory() as session:
            await _wipe(session)

    async def test_delete_removes_auto_keeps_manual_and_correction(
        self,
        async_client: AsyncClient,
        seeded_with_mentions: dict[str, uuid.UUID],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        entity_id = seeded_with_mentions["entity_id"]
        alias_aardvark = seeded_with_mentions["alias_aardvark"]

        with _auth() as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            resp = await async_client.delete(_url(entity_id, alias_aardvark))
        assert resp.status_code == 200, resp.text
        # Only the single auto-detected "Aardvark" mention is removed.
        assert resp.json()["data"]["removed_mention_count"] == 1

        async with integration_session_factory() as session:
            surviving = (
                await session.execute(
                    select(
                        EntityMentionDB.mention_text,
                        EntityMentionDB.detection_method,
                    ).where(EntityMentionDB.entity_id == entity_id)
                )
            ).all()
            surviving_set = {(t, m) for t, m in surviving}
            # Auto "Aardvark" gone; manual + correction "Aardvark" preserved;
            # the sibling "Bumblebee" auto mention untouched.
            assert ("Aardvark", "rule_match") not in surviving_set
            assert ("Aardvark", "manual") in surviving_set
            assert ("Aardvark", "user_correction") in surviving_set
            assert ("Bumblebee", "rule_match") in surviving_set

        # Counter recomputed: only mentions matching a *surviving* visible name
        # are counted, so the two preserved "Aardvark" mentions (whose alias is
        # gone) no longer count — leaving just the "Bumblebee" mention.
        with _auth() as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            detail = await async_client.get(f"/api/v1/entities/{entity_id}")
        assert detail.status_code == 200, detail.text
        assert detail.json()["data"]["mention_count"] == 1


class TestDeleteFoldedCollisionKeepsSiblingMentions:
    """Deleting one alias must not strip a folded-colliding sibling's mentions.

    ``pena`` and ``peña`` have distinct ``alias_name_normalized`` (the normalizer
    keeps the tilde) so both can exist on one entity, yet they fold to the same
    ``lower(unaccent(...))`` value. Deleting ``pena`` must NOT remove the
    surviving ``peña`` alias's still-covered mentions (#289 adversarial guard).
    """

    _CHANNEL_ID = "UCeac289coll000000001"  # <= 24 chars
    _VIDEO_ID = "eac289_coll01"  # <= 20 chars
    _LANG = "en"
    _ENTITY_NORM = "eac289 collision"

    @pytest.fixture
    async def seeded_collision(
        self,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> AsyncGenerator[dict[str, uuid.UUID], None]:
        entity_id = uuid.uuid4()
        alias_pena = uuid.uuid4()
        alias_penya = uuid.uuid4()

        async def _wipe(session: AsyncSession) -> None:
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
            ids = (
                (
                    await session.execute(
                        select(NamedEntityDB.id).where(
                            NamedEntityDB.canonical_name_normalized == self._ENTITY_NORM
                        )
                    )
                )
                .scalars()
                .all()
            )
            if ids:
                await session.execute(
                    delete(EntityAliasDB).where(EntityAliasDB.entity_id.in_(list(ids)))
                )
                await session.execute(
                    delete(NamedEntityDB).where(NamedEntityDB.id.in_(list(ids)))
                )
            await session.execute(
                delete(VideoDB).where(VideoDB.video_id == self._VIDEO_ID)
            )
            await session.execute(
                delete(ChannelDB).where(ChannelDB.channel_id == self._CHANNEL_ID)
            )
            await session.commit()

        async with integration_session_factory() as session:
            await _wipe(session)
            session.add(ChannelDB(channel_id=self._CHANNEL_ID, title="EAC289 Coll"))
            session.add(
                VideoDB(
                    video_id=self._VIDEO_ID,
                    channel_id=self._CHANNEL_ID,
                    title="EAC289 Coll Video",
                    description="folded-collision test",
                    upload_date=datetime(2024, 5, 1, tzinfo=UTC),
                    duration=90,
                )
            )
            await session.commit()
            session.add(
                VideoTranscriptDB(
                    video_id=self._VIDEO_ID,
                    language_code=self._LANG,
                    transcript_text="peña appears here.",
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
                text="peña appears here.",
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
                    id=entity_id,
                    canonical_name="Eac289 Collision",
                    canonical_name_normalized=self._ENTITY_NORM,
                    entity_type="person",
                )
            )
            await session.flush()
            for aid, name, norm in (
                (alias_pena, "pena", "pena"),
                (alias_penya, "peña", "peña"),
            ):
                session.add(
                    EntityAliasDB(
                        id=aid,
                        entity_id=entity_id,
                        alias_name=name,
                        alias_name_normalized=norm,
                        alias_type="name_variant",
                        occurrence_count=0,
                    )
                )
            # One auto mention of "peña" — folds to "pena", so BOTH aliases cover it.
            session.add(
                EntityMentionDB(
                    id=uuid.UUID(bytes=uuid.uuid4().bytes),
                    entity_id=entity_id,
                    segment_id=segment_id,
                    video_id=self._VIDEO_ID,
                    language_code=self._LANG,
                    mention_text="peña",
                    detection_method="rule_match",
                    confidence=1.0,
                )
            )
            await session.commit()

        yield {"entity_id": entity_id, "alias_pena": alias_pena}
        async with integration_session_factory() as session:
            await _wipe(session)

    async def test_deleting_pena_keeps_penya_mention(
        self,
        async_client: AsyncClient,
        seeded_collision: dict[str, uuid.UUID],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        entity_id, alias_pena = (
            seeded_collision["entity_id"],
            seeded_collision["alias_pena"],
        )
        with _auth() as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            resp = await async_client.delete(_url(entity_id, alias_pena))
        assert resp.status_code == 200, resp.text
        # The "peña" mention is still covered by the surviving "peña" alias, so
        # nothing is removed by deleting "pena".
        assert resp.json()["data"]["removed_mention_count"] == 0

        async with integration_session_factory() as session:
            survivor = (
                await session.execute(
                    select(EntityMentionDB.mention_text).where(
                        EntityMentionDB.entity_id == entity_id
                    )
                )
            ).all()
            assert [t for (t,) in survivor] == ["peña"], "sibling's mention must remain"


class TestDeleteByRecordedLink:
    """Deletion uses the recorded ``alias_id`` link, not just the fold (#298, US2).

    A ``rule_match`` mention linked to the alias via ``alias_id`` is removed on
    delete even when its text does NOT fold to the alias name — which is exactly
    what makes the link survive an alias rename (the folded heuristic alone would
    miss it).
    """

    _CHANNEL_ID = "UCeac289link00000001"
    _VIDEO_ID = "eac289_link01"
    _LANG = "en"
    _ENTITY_NORM = "eac289 linktest"

    @pytest.fixture
    async def seeded_linked(
        self,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> AsyncGenerator[dict[str, uuid.UUID], None]:
        entity_id = uuid.uuid4()
        alias_id = uuid.uuid4()

        async def _wipe(session: AsyncSession) -> None:
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
            ids = (
                (
                    await session.execute(
                        select(NamedEntityDB.id).where(
                            NamedEntityDB.canonical_name_normalized == self._ENTITY_NORM
                        )
                    )
                )
                .scalars()
                .all()
            )
            if ids:
                await session.execute(
                    delete(EntityAliasDB).where(EntityAliasDB.entity_id.in_(list(ids)))
                )
                await session.execute(
                    delete(NamedEntityDB).where(NamedEntityDB.id.in_(list(ids)))
                )
            await session.execute(
                delete(VideoDB).where(VideoDB.video_id == self._VIDEO_ID)
            )
            await session.execute(
                delete(ChannelDB).where(ChannelDB.channel_id == self._CHANNEL_ID)
            )
            await session.commit()

        async with integration_session_factory() as session:
            await _wipe(session)
            session.add(ChannelDB(channel_id=self._CHANNEL_ID, title="EAC Link"))
            session.add(
                VideoDB(
                    video_id=self._VIDEO_ID,
                    channel_id=self._CHANNEL_ID,
                    title="EAC Link Video",
                    description="recorded-link delete test",
                    upload_date=datetime(2024, 7, 1, tzinfo=UTC),
                    duration=90,
                )
            )
            await session.commit()
            session.add(
                VideoTranscriptDB(
                    video_id=self._VIDEO_ID,
                    language_code=self._LANG,
                    transcript_text="filler",
                    transcript_type="MANUAL",
                    download_reason="USER_REQUEST",
                    is_cc=False,
                    is_auto_synced=False,
                    track_kind="standard",
                )
            )
            await session.commit()
            seg = TranscriptSegmentDB(
                video_id=self._VIDEO_ID,
                language_code=self._LANG,
                text="filler",
                start_time=0.0,
                duration=5.0,
                end_time=5.0,
                sequence_number=0,
                has_correction=False,
            )
            session.add(seg)
            await session.commit()
            session.add(
                create_named_entity_db(
                    id=entity_id,
                    canonical_name="Eac289 Linktest",
                    canonical_name_normalized=self._ENTITY_NORM,
                    entity_type="person",
                )
            )
            session.add(
                EntityAliasDB(
                    id=alias_id,
                    entity_id=entity_id,
                    alias_name="Ikelink",
                    alias_name_normalized="ikelink",
                    alias_type="name_variant",
                    occurrence_count=1,
                )
            )
            await session.flush()
            # A rule_match mention LINKED to the alias, but whose frozen text
            # does NOT fold to the alias name — only the alias_id link can select
            # it (mirrors what happens after the alias is renamed).
            session.add(
                EntityMentionDB(
                    id=uuid.uuid4(),
                    entity_id=entity_id,
                    segment_id=seg.id,
                    video_id=self._VIDEO_ID,
                    language_code=self._LANG,
                    mention_text="Zzznomatch",
                    detection_method="rule_match",
                    confidence=1.0,
                    alias_id=alias_id,
                )
            )
            await session.commit()
        yield {"entity_id": entity_id, "alias_id": alias_id}
        async with integration_session_factory() as session:
            await _wipe(session)

    async def test_delete_removes_linked_mention_despite_nonmatching_text(
        self,
        async_client: AsyncClient,
        seeded_linked: dict[str, uuid.UUID],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        entity_id, alias_id = seeded_linked["entity_id"], seeded_linked["alias_id"]
        with _auth() as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            resp = await async_client.delete(_url(entity_id, alias_id))
        assert resp.status_code == 200, resp.text
        # Removed via the recorded alias_id link, though "Zzznomatch" doesn't
        # fold to "ikelink".
        assert resp.json()["data"]["removed_mention_count"] == 1

        async with integration_session_factory() as session:
            rows = (
                (
                    await session.execute(
                        select(EntityMentionDB.id).where(
                            EntityMentionDB.entity_id == entity_id
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert rows == []


class TestDeleteCanonicalAliasKeepsCanonicalMentions:
    """Deleting the canonical self-alias must NOT strip the entity's own-name
    mentions (#298 guard fix): the canonical_name column survives the alias
    deletion and still covers them, so they are kept."""

    _CHANNEL_ID = "UCeac289canon00000001"
    _VIDEO_ID = "eac289_canon1"
    _LANG = "en"
    _ENTITY_NORM = "eac289 canontest"

    @pytest.fixture
    async def seeded_canonical(
        self,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> AsyncGenerator[dict[str, uuid.UUID], None]:
        entity_id = uuid.uuid4()
        self_alias_id = uuid.uuid4()
        other_alias_id = uuid.uuid4()

        async def _wipe(session: AsyncSession) -> None:
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
            ids = (
                (
                    await session.execute(
                        select(NamedEntityDB.id).where(
                            NamedEntityDB.canonical_name_normalized == self._ENTITY_NORM
                        )
                    )
                )
                .scalars()
                .all()
            )
            if ids:
                await session.execute(
                    delete(EntityAliasDB).where(EntityAliasDB.entity_id.in_(list(ids)))
                )
                await session.execute(
                    delete(NamedEntityDB).where(NamedEntityDB.id.in_(list(ids)))
                )
            await session.execute(
                delete(VideoDB).where(VideoDB.video_id == self._VIDEO_ID)
            )
            await session.execute(
                delete(ChannelDB).where(ChannelDB.channel_id == self._CHANNEL_ID)
            )
            await session.commit()

        async with integration_session_factory() as session:
            await _wipe(session)
            session.add(ChannelDB(channel_id=self._CHANNEL_ID, title="EAC Canon"))
            session.add(
                VideoDB(
                    video_id=self._VIDEO_ID,
                    channel_id=self._CHANNEL_ID,
                    title="EAC Canon Video",
                    description="canonical self-alias guard test",
                    upload_date=datetime(2024, 8, 1, tzinfo=UTC),
                    duration=90,
                )
            )
            await session.commit()
            session.add(
                VideoTranscriptDB(
                    video_id=self._VIDEO_ID,
                    language_code=self._LANG,
                    transcript_text="Canontest and Othername here.",
                    transcript_type="MANUAL",
                    download_reason="USER_REQUEST",
                    is_cc=False,
                    is_auto_synced=False,
                    track_kind="standard",
                )
            )
            await session.commit()
            seg = TranscriptSegmentDB(
                video_id=self._VIDEO_ID,
                language_code=self._LANG,
                text="Canontest and Othername here.",
                start_time=0.0,
                duration=5.0,
                end_time=5.0,
                sequence_number=0,
                has_correction=False,
            )
            session.add(seg)
            await session.commit()
            # Canonical name == the self-alias name.
            session.add(
                create_named_entity_db(
                    id=entity_id,
                    canonical_name="Canontest",
                    canonical_name_normalized=self._ENTITY_NORM,
                    entity_type="person",
                )
            )
            for aid, name, norm in (
                (self_alias_id, "Canontest", "canontest"),  # the canonical self-alias
                (other_alias_id, "Othername", "othername"),
            ):
                session.add(
                    EntityAliasDB(
                        id=aid,
                        entity_id=entity_id,
                        alias_name=name,
                        alias_name_normalized=norm,
                        alias_type="name_variant",
                        occurrence_count=1,
                    )
                )
            await session.flush()
            # One rule_match mention of the canonical name, one of the other alias.
            for text in ("Canontest", "Othername"):
                session.add(
                    EntityMentionDB(
                        id=uuid.uuid4(),
                        entity_id=entity_id,
                        segment_id=seg.id,
                        video_id=self._VIDEO_ID,
                        language_code=self._LANG,
                        mention_text=text,
                        detection_method="rule_match",
                        confidence=1.0,
                    )
                )
            await session.commit()
        yield {
            "entity_id": entity_id,
            "self_alias_id": self_alias_id,
            "other_alias_id": other_alias_id,
        }
        async with integration_session_factory() as session:
            await _wipe(session)

    async def test_deleting_canonical_self_alias_keeps_canonical_mentions(
        self,
        async_client: AsyncClient,
        seeded_canonical: dict[str, uuid.UUID],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        entity_id = seeded_canonical["entity_id"]
        self_alias_id = seeded_canonical["self_alias_id"]
        with _auth() as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            resp = await async_client.delete(_url(entity_id, self_alias_id))
        assert resp.status_code == 200, resp.text
        # The canonical name still covers its mention → nothing is stripped.
        assert resp.json()["data"]["removed_mention_count"] == 0

        async with integration_session_factory() as session:
            texts = sorted(
                t
                for (t,) in (
                    await session.execute(
                        select(EntityMentionDB.mention_text).where(
                            EntityMentionDB.entity_id == entity_id
                        )
                    )
                ).all()
            )
            # Both mentions survive (the canonical one was NOT stripped).
            assert texts == ["Canontest", "Othername"]

    async def test_deleting_other_alias_still_removes_its_mention(
        self,
        async_client: AsyncClient,
        seeded_canonical: dict[str, uuid.UUID],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        # Control: a non-canonical alias still has its mention removed.
        entity_id = seeded_canonical["entity_id"]
        other_alias_id = seeded_canonical["other_alias_id"]
        with _auth() as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            resp = await async_client.delete(_url(entity_id, other_alias_id))
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["removed_mention_count"] == 1
        async with integration_session_factory() as session:
            texts = sorted(
                t
                for (t,) in (
                    await session.execute(
                        select(EntityMentionDB.mention_text).where(
                            EntityMentionDB.entity_id == entity_id
                        )
                    )
                ).all()
            )
            assert texts == ["Canontest"]  # "Othername" removed, canonical kept
