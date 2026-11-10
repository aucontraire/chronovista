"""Endpoint tests for the channel-ownership surface (ownership promotion, read-path).

Covers GET /channels/{channel_id}/operators and GET /entities/{entity_id}/channels
against the real (shared, never-reset) integration DB via ASGITransport. Per the
project integration-db shared-state rule, assertions key on the ids/channel THIS test
seeds — never a global count. Seeds the imported ``youtube_channel_id`` identifier block
directly into ``named_entities.properties`` (no schema change — that is the whole point).

Covers: an organization operator surfaces (ownership is NOT person-scoped); the
entity-side in-library vs external distinction; empty states; and the 404 paths
(unknown channel, malformed entity id, unknown entity).
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from httpx import AsyncClient

from tests.factories.entity_association_orm_factory import seed_channel_with_videos
from tests.factories.named_entity_orm_factory import create_named_entity_db

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.asyncio


def _cid(suffix: str) -> str:
    """A valid, exactly-24-char channel id from a short unique suffix."""
    return ("UC" + suffix + "0" * 24)[:24]


_CH_OWNED = _cid("ownOwned")  # in-library channel with an operator
_CH_EXTERNAL = _cid("ownExt")  # NOT seeded in the library (external link)
_CH_NOOP = _cid("ownNoop")  # in-library channel with no operator
_CH_UNKNOWN = _cid("ownNope")  # never created


async def _seed_channel(
    factory: async_sessionmaker[AsyncSession], channel_id: str
) -> None:
    async with factory() as s:
        await seed_channel_with_videos(
            s,
            channel_id=channel_id,
            available=[],
            channel_title="Ownership Test Channel",
        )


async def _seed_owner_entity(
    factory: async_sessionmaker[AsyncSession],
    *,
    channel_values: list[str],
    entity_type: str = "organization",
    with_identifier: bool = True,
) -> uuid.UUID:
    """Seed one active entity whose stored youtube_channel_id operates ``channel_values``.

    Returns the entity id. Names embed the id so the never-reset DB never collides on
    ``uq_named_entity_canonical``.
    """
    eid = uuid.uuid4()
    name = f"Ownership Test Entity {eid.hex}"
    props = (
        {
            "youtube_channel_id": {
                "values": channel_values,
                "source": "wikidata",
                "set_at": "2026-09-14T00:00:00+00:00",
            }
        }
        if with_identifier
        else {}
    )
    async with factory() as s:
        s.add(
            create_named_entity_db(
                id=eid,
                canonical_name=name,
                canonical_name_normalized=name.lower(),
                entity_type=entity_type,
                status="active",
                properties=props,
            )
        )
        await s.commit()
    return eid


class TestChannelOperatorsEndpoint:
    async def test_returns_operator_not_person_scoped(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        await _seed_channel(integration_session_factory, _CH_OWNED)
        eid = await _seed_owner_entity(
            integration_session_factory,
            channel_values=[_CH_OWNED],
            entity_type="organization",  # an ORG operator — ownership is not person-scoped
        )

        r = await async_client.get(f"/api/v1/channels/{_CH_OWNED}/operators")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["channel_id"] == _CH_OWNED
        by_id = {i["entity_id"]: i for i in body["items"]}
        assert str(eid) in by_id, body  # key on the seeded id (shared DB)
        item = by_id[str(eid)]
        assert set(item) == {
            "entity_id",
            "entity_type",
            "canonical_name",
            "provenance",
        }
        assert item["entity_type"] == "organization"
        assert item["provenance"] == "wikidata"
        assert body["total_entities"] == len(body["items"])

    async def test_unknown_channel_returns_404_problem_json(
        self, async_client: AsyncClient
    ) -> None:
        r = await async_client.get(f"/api/v1/channels/{_CH_UNKNOWN}/operators")
        assert r.status_code == 404
        assert "application/problem+json" in r.headers.get("content-type", "")
        assert r.json().get("status") == 404

    async def test_known_channel_no_operator_returns_200_empty(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        await _seed_channel(integration_session_factory, _CH_NOOP)
        r = await async_client.get(f"/api/v1/channels/{_CH_NOOP}/operators")
        assert r.status_code == 200, r.text
        body = r.json()
        # This channel id is unique to this test and nothing ever seeds an operator for
        # it, so the list is deterministically empty even on the shared, never-reset DB.
        assert body["items"] == []
        assert body["total_entities"] == 0


class TestEntityChannelsEndpoint:
    async def test_in_library_channel_has_title_and_flag(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        await _seed_channel(integration_session_factory, _CH_OWNED)
        eid = await _seed_owner_entity(
            integration_session_factory, channel_values=[_CH_OWNED]
        )

        r = await async_client.get(f"/api/v1/entities/{eid}/channels")
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        # This entity operates exactly the one seeded channel.
        links = {d["channel_id"]: d for d in data}
        assert _CH_OWNED in links, data
        link = links[_CH_OWNED]
        assert link["in_library"] is True
        assert link["title"] == "Ownership Test Channel"

    async def test_external_channel_flagged_not_in_library(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        # The channel id is NOT seeded into the library (an external link).
        eid = await _seed_owner_entity(
            integration_session_factory, channel_values=[_CH_EXTERNAL]
        )
        r = await async_client.get(f"/api/v1/entities/{eid}/channels")
        assert r.status_code == 200, r.text
        links = {d["channel_id"]: d for d in r.json()["data"]}
        assert _CH_EXTERNAL in links, links
        assert links[_CH_EXTERNAL]["in_library"] is False
        assert links[_CH_EXTERNAL]["title"] is None

    async def test_entity_without_identifier_returns_empty(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        eid = await _seed_owner_entity(
            integration_session_factory, channel_values=[], with_identifier=False
        )
        r = await async_client.get(f"/api/v1/entities/{eid}/channels")
        assert r.status_code == 200, r.text
        assert r.json()["data"] == []

    async def test_malformed_entity_id_returns_404(
        self, async_client: AsyncClient
    ) -> None:
        r = await async_client.get("/api/v1/entities/not-a-uuid/channels")
        assert r.status_code == 404
        assert "application/problem+json" in r.headers.get("content-type", "")

    async def test_unknown_entity_returns_404(self, async_client: AsyncClient) -> None:
        r = await async_client.get(f"/api/v1/entities/{uuid.uuid4()}/channels")
        assert r.status_code == 404
        assert r.json().get("status") == 404


# --- Feature 109: manual ownership assertions (write path + union) ---

_CH_ADD_EXT = _cid("ownAddExt")  # external, added by hand
_CH_ADD_DUP = _cid("ownAddDup")  # added twice -> second is 409
_CH_ADD_URL = _cid("ownAddUrl")  # added via /channel/ URL
_CH_ADD_WD = _cid("ownAddWd")  # imported; manual add is refused as redundant
_CH_UNION_IMP = _cid("ownUnImp")  # imported arm of the union
_CH_UNION_MAN = _cid("ownUnMan")  # manual arm of the union
_CH_CATCHUP = _cid("ownCatch")  # manual first, then Wikidata catches up


async def _set_imported_channels(
    factory: async_sessionmaker[AsyncSession],
    eid: uuid.UUID,
    values: list[str],
) -> None:
    """Overwrite an entity's imported ``youtube_channel_id`` block (simulate a reground)."""
    from chronovista.db.models import NamedEntity as NamedEntityDB

    async with factory() as s:
        ent = await s.get(NamedEntityDB, eid)
        assert ent is not None
        ent.properties = {
            "youtube_channel_id": {
                "values": values,
                "source": "wikidata",
                "set_at": "2026-09-14T00:00:00+00:00",
            }
        }
        await s.commit()


class TestAddEntityChannel:
    async def test_add_external_channel_returns_201_manual(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        eid = await _seed_owner_entity(
            integration_session_factory, channel_values=[], with_identifier=False
        )
        r = await async_client.post(
            f"/api/v1/entities/{eid}/channels", json={"channel_ref": _CH_ADD_EXT}
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["channel_id"] == _CH_ADD_EXT
        assert body["provenance"] == "manual"
        assert body["in_library"] is False
        # It now appears in the read, tagged manual.
        g = await async_client.get(f"/api/v1/entities/{eid}/channels")
        links = {d["channel_id"]: d for d in g.json()["data"]}
        assert links[_CH_ADD_EXT]["provenance"] == "manual"

    async def test_add_via_channel_url_returns_201(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        eid = await _seed_owner_entity(
            integration_session_factory, channel_values=[], with_identifier=False
        )
        r = await async_client.post(
            f"/api/v1/entities/{eid}/channels",
            json={"channel_ref": f"https://www.youtube.com/channel/{_CH_ADD_URL}"},
        )
        assert r.status_code == 201, r.text
        assert r.json()["channel_id"] == _CH_ADD_URL

    async def test_add_duplicate_manual_returns_409(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        eid = await _seed_owner_entity(
            integration_session_factory, channel_values=[], with_identifier=False
        )
        first = await async_client.post(
            f"/api/v1/entities/{eid}/channels", json={"channel_ref": _CH_ADD_DUP}
        )
        assert first.status_code == 201, first.text
        dup = await async_client.post(
            f"/api/v1/entities/{eid}/channels", json={"channel_ref": _CH_ADD_DUP}
        )
        assert dup.status_code == 409, dup.text
        assert "already added" in dup.text.lower()

    async def test_add_already_wikidata_returns_409(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        eid = await _seed_owner_entity(
            integration_session_factory, channel_values=[_CH_ADD_WD]
        )
        r = await async_client.post(
            f"/api/v1/entities/{eid}/channels", json={"channel_ref": _CH_ADD_WD}
        )
        assert r.status_code == 409, r.text
        assert "wikidata" in r.text.lower()

    async def test_add_malformed_channel_ref_returns_422(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        eid = await _seed_owner_entity(
            integration_session_factory, channel_values=[], with_identifier=False
        )
        r = await async_client.post(
            f"/api/v1/entities/{eid}/channels",
            json={"channel_ref": "https://youtube.com/@somehandle"},
        )
        assert r.status_code == 422, r.text

    async def test_add_unknown_entity_returns_404(
        self, async_client: AsyncClient
    ) -> None:
        r = await async_client.post(
            f"/api/v1/entities/{uuid.uuid4()}/channels",
            json={"channel_ref": _CH_ADD_EXT},
        )
        assert r.status_code == 404, r.text


class TestEntityChannelsUnion:
    async def test_union_imported_and_manual_both_tagged(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        eid = await _seed_owner_entity(
            integration_session_factory, channel_values=[_CH_UNION_IMP]
        )
        add = await async_client.post(
            f"/api/v1/entities/{eid}/channels", json={"channel_ref": _CH_UNION_MAN}
        )
        assert add.status_code == 201, add.text
        g = await async_client.get(f"/api/v1/entities/{eid}/channels")
        links = {d["channel_id"]: d for d in g.json()["data"]}
        assert links[_CH_UNION_IMP]["provenance"] == "wikidata"
        assert links[_CH_UNION_MAN]["provenance"] == "manual"

    async def test_wikidata_catchup_dedups_to_single_wikidata(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        # Manual add first (Wikidata doesn't have it yet) ...
        eid = await _seed_owner_entity(
            integration_session_factory, channel_values=[], with_identifier=False
        )
        add = await async_client.post(
            f"/api/v1/entities/{eid}/channels", json={"channel_ref": _CH_CATCHUP}
        )
        assert add.status_code == 201, add.text
        # ... then Wikidata catches up (a reground imports the same channel).
        await _set_imported_channels(integration_session_factory, eid, [_CH_CATCHUP])
        g = await async_client.get(f"/api/v1/entities/{eid}/channels")
        matches = [d for d in g.json()["data"] if d["channel_id"] == _CH_CATCHUP]
        assert len(matches) == 1, matches  # deduped to one (FR-013)
        assert matches[0]["provenance"] == "wikidata"  # imported wins


_CH_OP_ADD = _cid("ownOpAdd")  # channel-side assign target
_CH_OP_NO = _cid("ownOpNo")  # channel-side assign against an unknown channel
_CH_RM_ENT = _cid("ownRmEnt")  # entity-side remove
_CH_RM_CHAN = _cid("ownRmChan")  # channel-side remove
_CH_RM_IMP = _cid("ownRmImp")  # imported — not removable


class TestAddChannelOperator:
    async def test_assign_entity_from_channel_side_returns_201_and_mirrors(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        await _seed_channel(integration_session_factory, _CH_OP_ADD)
        eid = await _seed_owner_entity(
            integration_session_factory, channel_values=[], with_identifier=False
        )
        r = await async_client.post(
            f"/api/v1/channels/{_CH_OP_ADD}/operators", json={"entity_id": str(eid)}
        )
        assert r.status_code == 201, r.text
        assert r.json()["provenance"] == "manual"
        # Appears on the channel's operators list (manual) ...
        ops = await async_client.get(f"/api/v1/channels/{_CH_OP_ADD}/operators")
        by_id = {i["entity_id"]: i for i in ops.json()["items"]}
        assert by_id[str(eid)]["provenance"] == "manual"
        # ... and on the entity's operated-channels list (one store, both doors).
        ent = await async_client.get(f"/api/v1/entities/{eid}/channels")
        assert _CH_OP_ADD in {d["channel_id"] for d in ent.json()["data"]}

    async def test_assign_unknown_entity_returns_404(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        await _seed_channel(integration_session_factory, _CH_OP_ADD)
        r = await async_client.post(
            f"/api/v1/channels/{_CH_OP_ADD}/operators",
            json={"entity_id": str(uuid.uuid4())},
        )
        assert r.status_code == 404, r.text

    async def test_assign_already_wikidata_returns_409(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        await _seed_channel(integration_session_factory, _CH_OP_ADD)
        eid = await _seed_owner_entity(
            integration_session_factory, channel_values=[_CH_OP_ADD]
        )
        r = await async_client.post(
            f"/api/v1/channels/{_CH_OP_ADD}/operators", json={"entity_id": str(eid)}
        )
        assert r.status_code == 409, r.text
        assert "wikidata" in r.text.lower()

    async def test_assign_to_unknown_channel_returns_404(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        # The channel side is the in-library surface: an unknown channel is a 404, coherent
        # with its GET sibling, so a created link is always readable back from this endpoint.
        eid = await _seed_owner_entity(
            integration_session_factory, channel_values=[], with_identifier=False
        )
        r = await async_client.post(
            f"/api/v1/channels/{_CH_OP_NO}/operators", json={"entity_id": str(eid)}
        )
        assert r.status_code == 404, r.text


class TestRemoveOwnership:
    async def test_remove_manual_from_entity_side(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        eid = await _seed_owner_entity(
            integration_session_factory, channel_values=[], with_identifier=False
        )
        add = await async_client.post(
            f"/api/v1/entities/{eid}/channels", json={"channel_ref": _CH_RM_ENT}
        )
        assert add.status_code == 201, add.text
        rm = await async_client.delete(f"/api/v1/entities/{eid}/channels/{_CH_RM_ENT}")
        assert rm.status_code == 204, rm.text
        g = await async_client.get(f"/api/v1/entities/{eid}/channels")
        assert _CH_RM_ENT not in {d["channel_id"] for d in g.json()["data"]}

    async def test_remove_manual_from_channel_side(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        await _seed_channel(integration_session_factory, _CH_RM_CHAN)
        eid = await _seed_owner_entity(
            integration_session_factory, channel_values=[], with_identifier=False
        )
        add = await async_client.post(
            f"/api/v1/channels/{_CH_RM_CHAN}/operators", json={"entity_id": str(eid)}
        )
        assert add.status_code == 201, add.text
        rm = await async_client.delete(
            f"/api/v1/channels/{_CH_RM_CHAN}/operators/{eid}"
        )
        assert rm.status_code == 204, rm.text
        ops = await async_client.get(f"/api/v1/channels/{_CH_RM_CHAN}/operators")
        assert str(eid) not in {i["entity_id"] for i in ops.json()["items"]}

    async def test_cannot_remove_imported_link_404(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        # Imported-only link: there is no manual row, so DELETE finds nothing (FR-015).
        eid = await _seed_owner_entity(
            integration_session_factory, channel_values=[_CH_RM_IMP]
        )
        rm = await async_client.delete(f"/api/v1/entities/{eid}/channels/{_CH_RM_IMP}")
        assert rm.status_code == 404, rm.text
        # ... and the imported link is still there.
        g = await async_client.get(f"/api/v1/entities/{eid}/channels")
        assert _CH_RM_IMP in {d["channel_id"] for d in g.json()["data"]}


_CH_REGROUND = _cid("ownRegr")  # manual link that must survive a reground
_CH_REGROUND_IMP = _cid("ownRegrI")  # unrelated imported channel after the reground
_CH_PROP_EXISTING = _cid("ownPropE")  # the entity's pre-existing imported channel
_CH_PROP_ADD = _cid("ownPropA")  # manually added; must NOT touch properties


async def _get_entity_properties(
    factory: async_sessionmaker[AsyncSession], eid: uuid.UUID
) -> dict[str, object]:
    from chronovista.db.models import NamedEntity as NamedEntityDB

    async with factory() as s:
        ent = await s.get(NamedEntityDB, eid)
        assert ent is not None
        return dict(ent.properties or {})


class TestWriteIsolationAndReground:
    async def test_manual_link_survives_reground(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        eid = await _seed_owner_entity(
            integration_session_factory, channel_values=[], with_identifier=False
        )
        add = await async_client.post(
            f"/api/v1/entities/{eid}/channels", json={"channel_ref": _CH_REGROUND}
        )
        assert add.status_code == 201, add.text
        # A reground overwrites named_entities.properties wholesale with unrelated data.
        await _set_imported_channels(
            integration_session_factory, eid, [_CH_REGROUND_IMP]
        )
        g = await async_client.get(f"/api/v1/entities/{eid}/channels")
        links = {d["channel_id"]: d for d in g.json()["data"]}
        assert links[_CH_REGROUND]["provenance"] == "manual"  # survived (FR-010)
        assert links[_CH_REGROUND_IMP]["provenance"] == "wikidata"

    async def test_manual_add_does_not_touch_entity_properties(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        # C1 / FR-008 write-half: the write path must NEVER mutate named_entities.properties.
        eid = await _seed_owner_entity(
            integration_session_factory, channel_values=[_CH_PROP_EXISTING]
        )
        before = await _get_entity_properties(integration_session_factory, eid)
        add = await async_client.post(
            f"/api/v1/entities/{eid}/channels", json={"channel_ref": _CH_PROP_ADD}
        )
        assert add.status_code == 201, add.text
        after = await _get_entity_properties(integration_session_factory, eid)
        assert (
            after == before
        )  # properties untouched — manual link lives in its own table
