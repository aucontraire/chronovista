"""Endpoint integration tests for the Feature 091 manual-association exclusion API (T014).

Exercises POST/DELETE/GET ``/api/v1/entities/{entity_id}/excluded-videos`` over real HTTP
against the integration DB: an excluded video drops from ``/videos?entity_id=``, the 404
cases, idempotent re-exclude (FR-006), and the undo + list round-trip (FR-005/FR-009).
The COMPREHENSIVE cross-surface parity is covered at the repository level in
``tests/integration/repositories/test_entity_video_exclusion_parity.py`` (and T016).
Name-free placeholders only (Constitution VI).
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from chronovista.db.models import EntityOperationLog as EntityOperationLogDB
from tests.factories.entity_association_orm_factory import (
    seed_channel_with_videos,
    seed_tag_only_association,
)

pytestmark = pytest.mark.asyncio

_CH = ("UCf091api" + "0" * 24)[:24]


async def _seed_entity_with_video(
    factory: async_sessionmaker[AsyncSession], video_id: str, name: str
) -> str:
    """Seed a channel+video and a tag-only entity↔video association; return the entity id."""
    async with factory() as session:
        await seed_channel_with_videos(session, channel_id=_CH, available=[video_id])
        entity = await seed_tag_only_association(
            session, video_ids=[video_id], entity_name=name
        )
        return str(entity.id)


class TestExcludeEndpoint:
    async def test_exclude_drops_video_from_entity_videos(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        video_id = "f091api1"
        eid = await _seed_entity_with_video(
            integration_session_factory, video_id, "F091 api subject one"
        )

        before = await async_client.get(f"/api/v1/videos?entity_id={eid}")
        assert before.status_code == 200
        assert video_id in {r["video_id"] for r in before.json()["data"]}

        resp = await async_client.post(
            f"/api/v1/entities/{eid}/excluded-videos", json={"video_id": video_id}
        )
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["already_excluded"] is False
        assert body["exclusion"]["video_id"] == video_id
        assert body["exclusion"]["entity_id"] == eid

        after = await async_client.get(f"/api/v1/videos?entity_id={eid}")
        assert video_id not in {r["video_id"] for r in after.json()["data"]}

    async def test_reexclude_is_idempotent_no_op(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        video_id = "f091api2"
        eid = await _seed_entity_with_video(
            integration_session_factory, video_id, "F091 api subject two"
        )
        first = await async_client.post(
            f"/api/v1/entities/{eid}/excluded-videos", json={"video_id": video_id}
        )
        assert first.json()["data"]["already_excluded"] is False
        second = await async_client.post(
            f"/api/v1/entities/{eid}/excluded-videos", json={"video_id": video_id}
        )
        assert second.status_code == 200
        assert second.json()["data"]["already_excluded"] is True

    async def test_404_for_unknown_entity(self, async_client: AsyncClient) -> None:
        resp = await async_client.post(
            f"/api/v1/entities/{uuid.uuid4()}/excluded-videos",
            json={"video_id": "f091apiX"},
        )
        assert resp.status_code == 404

    async def test_404_for_unknown_video(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        eid = await _seed_entity_with_video(
            integration_session_factory, "f091api3", "F091 api subject three"
        )
        resp = await async_client.post(
            f"/api/v1/entities/{eid}/excluded-videos",
            json={"video_id": "f091nope9"},
        )
        assert resp.status_code == 404

    async def test_undo_and_list_round_trip(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        video_id = "f091api4"
        eid = await _seed_entity_with_video(
            integration_session_factory, video_id, "F091 api subject four"
        )
        # Exclude, then it appears in the 'hidden from this entity' list.
        await async_client.post(
            f"/api/v1/entities/{eid}/excluded-videos", json={"video_id": video_id}
        )
        listed = await async_client.get(f"/api/v1/entities/{eid}/excluded-videos")
        assert listed.status_code == 200
        assert video_id in {r["video_id"] for r in listed.json()["data"]}
        assert listed.json()["pagination"]["total"] == 1

        # Undo → 204, gone from the list, and back in the entity's videos.
        undo = await async_client.delete(
            f"/api/v1/entities/{eid}/excluded-videos/{video_id}"
        )
        assert undo.status_code == 204
        listed_after = await async_client.get(f"/api/v1/entities/{eid}/excluded-videos")
        assert listed_after.json()["pagination"]["total"] == 0
        videos = await async_client.get(f"/api/v1/videos?entity_id={eid}")
        assert video_id in {r["video_id"] for r in videos.json()["data"]}

    async def test_undo_absent_exclusion_is_idempotent_204(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        eid = await _seed_entity_with_video(
            integration_session_factory, "f091api5", "F091 api subject five"
        )
        resp = await async_client.delete(
            f"/api/v1/entities/{eid}/excluded-videos/f091api5"
        )
        assert resp.status_code == 204


async def _latest_op_id(
    factory: async_sessionmaker[AsyncSession], entity_id: str, op_type: str
) -> str:
    """The id of the most recent op-log row of ``op_type`` for ``entity_id``."""
    async with factory() as session:
        row = (
            await session.execute(
                select(EntityOperationLogDB.id)
                .where(
                    EntityOperationLogDB.entity_id == uuid.UUID(entity_id),
                    EntityOperationLogDB.operation_type == op_type,
                )
                .order_by(desc(EntityOperationLogDB.performed_at))
                .limit(1)
            )
        ).scalar_one()
        return str(row)


class TestGenericUndoOfExclusionOps:
    """Exclude/restore op-log rows must be undoable through the generic
    operation-history undo endpoint (Q4=B), and a non-undoable op type must fail
    4xx (not 500 from the unconditional rollback-payload validate)."""

    async def test_undo_of_exclude_op_reincludes_video(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        video_id = "f091undo1"
        eid = await _seed_entity_with_video(
            integration_session_factory, video_id, "F091 undo subject one"
        )
        await async_client.post(
            f"/api/v1/entities/{eid}/excluded-videos", json={"video_id": video_id}
        )
        gone = await async_client.get(f"/api/v1/videos?entity_id={eid}")
        assert video_id not in {r["video_id"] for r in gone.json()["data"]}

        op_id = await _latest_op_id(
            integration_session_factory, eid, "association_exclude"
        )
        undo = await async_client.post(f"/api/v1/entities/operations/{op_id}/undo")
        assert undo.status_code == 200

        back = await async_client.get(f"/api/v1/videos?entity_id={eid}")
        assert video_id in {r["video_id"] for r in back.json()["data"]}
        listed = await async_client.get(f"/api/v1/entities/{eid}/excluded-videos")
        assert listed.json()["pagination"]["total"] == 0

    async def test_double_undo_is_conflict_409(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        video_id = "f091undo2"
        eid = await _seed_entity_with_video(
            integration_session_factory, video_id, "F091 undo subject two"
        )
        await async_client.post(
            f"/api/v1/entities/{eid}/excluded-videos", json={"video_id": video_id}
        )
        op_id = await _latest_op_id(
            integration_session_factory, eid, "association_exclude"
        )
        first = await async_client.post(f"/api/v1/entities/operations/{op_id}/undo")
        assert first.status_code == 200
        second = await async_client.post(f"/api/v1/entities/operations/{op_id}/undo")
        assert second.status_code == 409

    async def test_unsupported_op_type_fails_4xx_not_500(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        eid = await _seed_entity_with_video(
            integration_session_factory, "f091undo3", "F091 undo subject three"
        )
        async with integration_session_factory() as session:
            op = EntityOperationLogDB(
                entity_id=uuid.UUID(eid),
                operation_type="refetch",
                rollback_data={},
                performed_by="test",
            )
            session.add(op)
            await session.commit()
            op_id = str(op.id)
        resp = await async_client.post(f"/api/v1/entities/operations/{op_id}/undo")
        assert resp.status_code == 400


class TestExclusionAuditTrail:
    """FR-007 / Q4=B: excluding via POST and restoring via DELETE each write an
    entity-operation-log row (with rollback data + actor), so both appear in the
    entity's operation history."""

    async def _op_row(
        self,
        factory: async_sessionmaker[AsyncSession],
        entity_id: str,
        op_type: str,
    ) -> EntityOperationLogDB:
        async with factory() as session:
            return (
                await session.execute(
                    select(EntityOperationLogDB)
                    .where(
                        EntityOperationLogDB.entity_id == uuid.UUID(entity_id),
                        EntityOperationLogDB.operation_type == op_type,
                    )
                    .order_by(desc(EntityOperationLogDB.performed_at))
                    .limit(1)
                )
            ).scalar_one()

    async def test_exclude_and_restore_write_audit_rows(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        video_id = "f091aud1"
        eid = await _seed_entity_with_video(
            integration_session_factory, video_id, "F091 audit subject"
        )

        await async_client.post(
            f"/api/v1/entities/{eid}/excluded-videos", json={"video_id": video_id}
        )
        excl_row = await self._op_row(
            integration_session_factory, eid, "association_exclude"
        )
        assert excl_row.rollback_data["video_id"] == video_id
        assert excl_row.performed_by

        await async_client.delete(f"/api/v1/entities/{eid}/excluded-videos/{video_id}")
        restore_row = await self._op_row(
            integration_session_factory, eid, "association_restore"
        )
        assert restore_row.rollback_data["video_id"] == video_id
        assert restore_row.performed_by
