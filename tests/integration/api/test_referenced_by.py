"""Integration tests for the "Referenced by" endpoint (Feature 087).

Reads **through** the endpoint against seeded `named_entities.properties` relations: synonymous-field
union (membership = member_of + part_of, the 19-not-2 shape), active-only, attribute-field exclusion,
specific+attributed labels, empty, and 404s. Entity names are neutral placeholders (Constitution VI).
The integration DB is shared and never reset, so everything is prefixed and cleaned up.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

import pytest
from httpx import AsyncClient
from sqlalchemy import delete
from uuid_utils import uuid7

from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.repositories.named_entity_repository import NamedEntityRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.asyncio

_PREFIX = "refby087"
_TARGET_QID = "Q087TARGET"


def _u(value: object) -> uuid.UUID:
    return uuid.UUID(str(value))


def _rel(*qids: str) -> dict[str, Any]:
    return {"qids": list(qids), "values": ["placeholder"], "source": "wikidata"}


async def _entity(
    session: AsyncSession,
    name: str,
    *,
    status: str = "active",
    external_ids: dict[str, Any] | None = None,
    properties: dict[str, Any] | None = None,
) -> uuid.UUID:
    entity = NamedEntityDB(
        id=uuid7(),
        canonical_name=f"{_PREFIX} {name}",
        canonical_name_normalized=f"{_PREFIX} {name}".lower(),
        entity_type="organization",
        status=status,
        external_ids=external_ids or {},
        properties=properties or {},
    )
    session.add(entity)
    await session.flush()
    return _u(entity.id)


@pytest.fixture
async def seed(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[dict[str, Any], None]:
    """Target T (QID). Alpha member_of→T; Bravo part_of→T; Cara member_of AND part_of→T; Dan
    employer→T; Eve member_of→T but inactive; Fox country→T (excluded)."""
    async with integration_session_factory() as s:
        target = await _entity(
            s, "target", external_ids={"wikidata": {"id": _TARGET_QID}}
        )
        alpha = await _entity(s, "alpha", properties={"member_of": _rel(_TARGET_QID)})
        bravo = await _entity(s, "bravo", properties={"part_of": _rel(_TARGET_QID)})
        cara = await _entity(
            s,
            "cara",
            properties={"member_of": _rel(_TARGET_QID), "part_of": _rel(_TARGET_QID)},
        )
        dan = await _entity(s, "dan", properties={"employer": _rel(_TARGET_QID)})
        eve = await _entity(
            s, "eve", status="merged", properties={"member_of": _rel(_TARGET_QID)}
        )
        fox = await _entity(s, "fox", properties={"country": _rel(_TARGET_QID)})
        no_qid = await _entity(
            s, "noqid"
        )  # no external_ids → nothing can reference it by id
        await s.commit()
        ids = {
            "target": target,
            "alpha": alpha,
            "bravo": bravo,
            "cara": cara,
            "dan": dan,
            "eve": eve,
            "fox": fox,
            "no_qid": no_qid,
        }

    yield ids

    async with integration_session_factory() as s:
        await s.execute(
            delete(NamedEntityDB).where(NamedEntityDB.id.in_(list(ids.values())))
        )
        await s.commit()


class TestReferencedBy:
    async def test_membership_unions_synonymous_fields(
        self, async_client: AsyncClient, seed: dict[str, Any]
    ) -> None:
        resp = await async_client.get(
            f"/api/v1/entities/{seed['target']}/referenced-by"
        )
        assert resp.status_code == 200
        groups = {g["key"]: g for g in resp.json()["data"]}
        # membership = member_of ∪ part_of: alpha, bravo, cara (deduped) = 3; eve (inactive) absent
        mem = groups["membership"]
        assert mem["member_count"] == 3
        mem_ids = {_u(m["entity_id"]) for m in mem["members"]}
        assert mem_ids == {seed["alpha"], seed["bravo"], seed["cara"]}
        assert seed["eve"] not in mem_ids
        # employment group present with dan
        assert {_u(m["entity_id"]) for m in groups["employment"]["members"]} == {
            seed["dan"]
        }
        # country is an excluded attribute field → no such group
        assert "country" not in groups

    async def test_labels_are_specific_and_attributed(
        self, async_client: AsyncClient, seed: dict[str, Any]
    ) -> None:
        resp = await async_client.get(
            f"/api/v1/entities/{seed['target']}/referenced-by"
        )
        for g in resp.json()["data"]:
            assert "wikidata" in g["attribution"].lower()  # attributed to the source
            low = f"{g['label']} {g['attribution']}".lower()
            assert (
                "related to" not in low and "connected with" not in low
            )  # never generic

    async def test_entity_with_no_qid_is_empty(
        self, async_client: AsyncClient, seed: dict[str, Any]
    ) -> None:
        resp = await async_client.get(
            f"/api/v1/entities/{seed['no_qid']}/referenced-by"
        )
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    async def test_malformed_and_unknown_id_are_404(
        self, async_client: AsyncClient, seed: dict[str, Any]
    ) -> None:
        assert (
            await async_client.get("/api/v1/entities/not-a-uuid/referenced-by")
        ).status_code == 404
        assert (
            await async_client.get(f"/api/v1/entities/{uuid.uuid4()}/referenced-by")
        ).status_code == 404

    async def test_family_relations_are_inverted_not_forward_labelled(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        # FR-004 directional harm: an entity whose `father` names T is T's CHILD; it must appear under
        # "Child", NEVER captioned "Father" (which would assert the child IS T's father). An entity
        # whose `child` names T is T's PARENT.
        qid = "Q087FAMILY"
        async with integration_session_factory() as s:
            target = await _entity(
                s, "fam-target", external_ids={"wikidata": {"id": qid}}
            )
            kid = await _entity(s, "fam-kid", properties={"father": _rel(qid)})
            parent = await _entity(s, "fam-parent", properties={"child": _rel(qid)})
            await s.commit()
            ids = [target, kid, parent]
        try:
            resp = await async_client.get(f"/api/v1/entities/{target}/referenced-by")
            groups = {g["key"]: g for g in resp.json()["data"]}
            labels = {g["label"] for g in resp.json()["data"]}
            # the father-field referrer lands under children/"Child", the child-field under parents/"Parent"
            assert {_u(m["entity_id"]) for m in groups["children"]["members"]} == {kid}
            assert {_u(m["entity_id"]) for m in groups["parents"]["members"]} == {
                parent
            }
            # no forward-worded family label leaks onto the reverse surface
            assert "Father" not in labels and "Mother" not in labels
        finally:
            async with integration_session_factory() as s:
                await s.execute(delete(NamedEntityDB).where(NamedEntityDB.id.in_(ids)))
                await s.commit()

    async def test_entity_excluded_from_its_own_referenced_by(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        # A self-referential relation (entity's own data names its own QID) must NOT list itself.
        self_qid = "Q087SELFREF"
        async with integration_session_factory() as s:
            eid = await _entity(
                s,
                "selfref",
                external_ids={"wikidata": {"id": self_qid}},
                properties={"member_of": _rel(self_qid)},
            )
            await s.commit()
        try:
            resp = await async_client.get(f"/api/v1/entities/{eid}/referenced-by")
            assert resp.status_code == 200
            all_ids = {
                _u(m["entity_id"]) for g in resp.json()["data"] for m in g["members"]
            }
            assert eid not in all_ids
        finally:
            async with integration_session_factory() as s:
                await s.execute(delete(NamedEntityDB).where(NamedEntityDB.id == eid))
                await s.commit()

    async def test_backfill_founder_mirrors_verbatim_and_appears_inverse(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        # US3 end-to-end across the REAL backfill seam (merge_properties, not a mocked write):
        # founder (newly captured, T016) is MERGED onto an org that already has a prior block, then
        # (a) the org's detail endpoint mirrors `properties` verbatim — the prior block survives and
        #     the founder block is added exactly (086 full-replace-wipe lesson), and
        # (b) the founder person's reverse page lists that org under "founded" (X.founder == T → T
        #     founded X), not under any forward-worded label.
        founder_qid = "Q087FOUNDER"
        prior = {
            "member_of": _rel("Q087ORG")
        }  # a pre-existing block the merge must preserve
        async with integration_session_factory() as s:
            founder = await _entity(
                s, "bf-founder", external_ids={"wikidata": {"id": founder_qid}}
            )
            org = await _entity(s, "bf-org", properties=dict(prior))
            await s.commit()
        try:
            # simulate the backfill's one write: additive, merged (|| ), never a bare replace
            async with integration_session_factory() as s:
                await NamedEntityRepository().merge_properties(
                    s, org, {"founder": _rel(founder_qid)}
                )
                await s.commit()

            detail = await async_client.get(f"/api/v1/entities/{org}")
            assert detail.status_code == 200, detail.text
            props = detail.json()["data"]["enrichment"]["properties"]
            # verbatim: the prior block is intact AND founder is present exactly as merged
            assert props["member_of"] == prior["member_of"]
            assert props["founder"] == _rel(founder_qid)

            resp = await async_client.get(f"/api/v1/entities/{founder}/referenced-by")
            assert resp.status_code == 200
            groups = {g["key"]: g for g in resp.json()["data"]}
            assert {_u(m["entity_id"]) for m in groups["founded"]["members"]} == {org}
            labels = {g["label"] for g in resp.json()["data"]}
            assert (
                "Founder" not in labels
            )  # inverse surface never forward-labels founder
        finally:
            async with integration_session_factory() as s:
                await s.execute(
                    delete(NamedEntityDB).where(NamedEntityDB.id.in_([founder, org]))
                )
                await s.commit()

    async def test_members_carry_instance_of_for_the_filter(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        # US2: each referencing member carries its resolved instance_of labels; the distinct present
        # values are derivable (no type with zero matches) and an untyped member reports []. Uses
        # `employer` to show the filter is independent of credits.
        qid = "Q088IOF"

        def _iof(*labels: str) -> dict[str, Any]:
            return {"values": list(labels), "qids": ["Qx"], "source": "wikidata"}

        async with integration_session_factory() as s:
            target = await _entity(
                s, "iof-target", external_ids={"wikidata": {"id": qid}}
            )
            film = await _entity(
                s,
                "iof-film",
                properties={"employer": _rel(qid), "instance_of": _iof("film")},
            )
            show = await _entity(
                s,
                "iof-show",
                properties={
                    "employer": _rel(qid),
                    "instance_of": _iof("television series"),
                },
            )
            untyped = await _entity(
                s, "iof-untyped", properties={"employer": _rel(qid)}
            )
            await s.commit()
            ids = [target, film, show, untyped]
        try:
            resp = await async_client.get(f"/api/v1/entities/{target}/referenced-by")
            assert resp.status_code == 200
            members = {
                _u(m["entity_id"]): m["instance_of"]
                for g in resp.json()["data"]
                for m in g["members"]
            }
            assert members[film] == ["film"]
            assert members[show] == ["television series"]
            assert (
                members[untyped] == []
            )  # untyped → empty, never dropped from the unfiltered list
            # the distinct present values the filter would offer — no dead options
            present = {t for vals in members.values() for t in vals}
            assert present == {"film", "television series"}
        finally:
            async with integration_session_factory() as s:
                await s.execute(delete(NamedEntityDB).where(NamedEntityDB.id.in_(ids)))
                await s.commit()

    async def test_credit_backfill_mirrors_verbatim_and_appears_inverse(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        # US3 across the REAL backfill seam: a work with a prior block gains `cast_member` via
        # merge_properties, then (a) the work's detail mirrors `properties` verbatim (prior block
        # intact + credit added) and (b) the person's reverse page lists the work under cast_of.
        person_qid = "Q088CREDITBF"
        prior = {
            "instance_of": {
                "values": ["film"],
                "qids": ["Q11424"],
                "source": "wikidata",
            }
        }
        async with integration_session_factory() as s:
            person = await _entity(
                s, "bf-cred-person", external_ids={"wikidata": {"id": person_qid}}
            )
            work = await _entity(s, "bf-cred-work", properties=dict(prior))
            await s.commit()
            ids = [person, work]
        try:
            async with integration_session_factory() as s:
                await NamedEntityRepository().merge_properties(
                    s, work, {"cast_member": _rel(person_qid)}
                )
                await s.commit()

            detail = await async_client.get(f"/api/v1/entities/{work}")
            assert detail.status_code == 200, detail.text
            props = detail.json()["data"]["enrichment"]["properties"]
            assert (
                props["instance_of"] == prior["instance_of"]
            )  # verbatim: prior block intact
            assert props["cast_member"] == _rel(person_qid)  # credit added exactly

            resp = await async_client.get(f"/api/v1/entities/{person}/referenced-by")
            groups = {g["key"]: g for g in resp.json()["data"]}
            assert {_u(m["entity_id"]) for m in groups["cast_of"]["members"]} == {work}
        finally:
            async with integration_session_factory() as s:
                await s.execute(delete(NamedEntityDB).where(NamedEntityDB.id.in_(ids)))
                await s.commit()

    async def test_credit_surfaces_both_ends_directionally(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        # US1: a work whose `cast_member` names a library person → on the PERSON's reverse page the
        # work appears under the `cast_of` group, labelled X-centric ("… in its cast"), NEVER the
        # forward "Cast member of" (which attached to the work would read backwards). The work's
        # detail shows the credit forward.
        person_qid = "Q088ACTOR"
        async with integration_session_factory() as s:
            person = await _entity(
                s, "cred-person", external_ids={"wikidata": {"id": person_qid}}
            )
            work = await _entity(
                s, "cred-work", properties={"cast_member": _rel(person_qid)}
            )
            await s.commit()
            ids = [person, work]
        try:
            resp = await async_client.get(f"/api/v1/entities/{person}/referenced-by")
            assert resp.status_code == 200
            groups = {g["key"]: g for g in resp.json()["data"]}
            assert "cast_of" in groups, resp.json()["data"]
            cast = groups["cast_of"]
            assert {_u(m["entity_id"]) for m in cast["members"]} == {work}
            # directional + attributed: X-centric label, Wikidata-attributed, never forward-worded
            assert "in its cast" in cast["label"]
            assert "wikidata" in cast["attribution"].lower()
            labels = {g["label"] for g in resp.json()["data"]}
            assert not any("Cast member of" in lab for lab in labels)
            # forward: the work's detail mirrors the credit block
            detail = await async_client.get(f"/api/v1/entities/{work}")
            assert detail.status_code == 200, detail.text
            assert detail.json()["data"]["enrichment"]["properties"][
                "cast_member"
            ] == _rel(person_qid)
        finally:
            async with integration_session_factory() as s:
                await s.execute(delete(NamedEntityDB).where(NamedEntityDB.id.in_(ids)))
                await s.commit()
