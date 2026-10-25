"""Real-DB test for `NamedEntityRepository.list_grounded_without_image` (Feature 093, FR-001/FR-010).

The candidate query is the single predicate that makes the backfill correct and idempotent: it must
select grounded, active, image-less entities and exclude everything that already has an image — a
manual upload, a Wikidata image, OR a prior Wikipedia image — plus ungrounded, merged, and inactive
rows. The exclusion is JSONB-selection semantics (`func.nullif` over `properties->'image'->...`),
which only a real Postgres run can verify, so this is an integration test (not a compiled-SQL mock).

Uses the ``db_session`` fixture (create_all + drop_all per test). Name-free placeholders only
(Constitution VI).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.repositories.named_entity_repository import NamedEntityRepository

pytestmark = pytest.mark.asyncio

_SET_AT = "2026-10-24T00:00:00Z"


def _image_block(source: str) -> dict[str, object]:
    return {
        "values": ["Placeholder_Portrait.jpg"],
        "qids": [],
        "source": source,
        "set_at": _SET_AT,
    }


def _entity(
    *,
    name: str,
    entity_type: str = "person",
    grounded: bool = True,
    image_source: str | None = None,
    manual_ext: str | None = None,
    status: str = "active",
    merged_into_id: uuid.UUID | None = None,
    raw_external_ids: dict[str, object] | None = None,
    raw_properties: dict[str, object] | None = None,
) -> NamedEntityDB:
    external_ids: dict[str, object] = (
        raw_external_ids
        if raw_external_ids is not None
        else ({"wikidata": {"id": "Q000" + name[-3:]}} if grounded else {})
    )
    properties: dict[str, object] = (
        raw_properties
        if raw_properties is not None
        else ({"image": _image_block(image_source)} if image_source else {})
    )
    return NamedEntityDB(
        id=uuid.uuid4(),
        canonical_name=name,
        canonical_name_normalized=name.lower(),
        entity_type=entity_type,
        external_ids=external_ids,
        properties=properties,
        manual_image_ext=manual_ext,
        status=status,
        merged_into_id=merged_into_id,
    )


class TestListGroundedWithoutImage:
    async def test_selects_grounded_image_less_excludes_all_image_holders(
        self, db_session: AsyncSession
    ) -> None:
        repo = NamedEntityRepository()

        candidate = _entity(name="Candidate 001")
        with_manual = _entity(name="Has Manual 002", manual_ext="jpg")
        with_wikidata = _entity(name="Has Wikidata 003", image_source="wikidata")
        with_wikipedia = _entity(name="Has Wikipedia 004", image_source="wikipedia")
        ungrounded = _entity(name="Ungrounded 005", grounded=False)

        db_session.add_all(
            [candidate, with_manual, with_wikidata, with_wikipedia, ungrounded]
        )
        await db_session.flush()

        selected = {e.id for e in await repo.list_grounded_without_image(db_session)}

        assert candidate.id in selected
        # Every entity that already has an image — manual, Wikidata, OR a prior Wikipedia one
        # (the FR-010 re-run skip) — and the ungrounded one are all excluded.
        assert with_manual.id not in selected
        assert with_wikidata.id not in selected
        assert with_wikipedia.id not in selected
        assert ungrounded.id not in selected

    async def test_excludes_merged_and_inactive(self, db_session: AsyncSession) -> None:
        repo = NamedEntityRepository()
        active = _entity(name="Active 010")
        deprecated = _entity(name="Deprecated 011", status="deprecated")
        db_session.add_all([active, deprecated])
        await db_session.flush()

        # status stays 'active' so the exclusion is attributable to merged_into_id alone.
        merged = _entity(name="Merged 012", merged_into_id=active.id)
        db_session.add(merged)
        await db_session.flush()

        selected = {e.id for e in await repo.list_grounded_without_image(db_session)}
        assert active.id in selected
        assert deprecated.id not in selected
        assert merged.id not in selected

    async def test_entity_type_filter_narrows(self, db_session: AsyncSession) -> None:
        repo = NamedEntityRepository()
        person = _entity(name="Person 020", entity_type="person")
        org = _entity(name="Org 021", entity_type="organization")
        db_session.add_all([person, org])
        await db_session.flush()

        all_types = {e.id for e in await repo.list_grounded_without_image(db_session)}
        assert {person.id, org.id} <= all_types

        persons_only = {
            e.id
            for e in await repo.list_grounded_without_image(
                db_session, entity_type="person"
            )
        }
        assert person.id in persons_only
        assert org.id not in persons_only

    @pytest.mark.parametrize(
        "degenerate_properties",
        [
            {},  # no image key at all
            {"image": {}},  # image block with no values key
            {"image": {"values": []}},  # empty values array
            {"image": {"values": [""]}},  # empty-string filename
            {"image": {"values": [None]}},  # JSON null filename
        ],
    )
    async def test_degenerate_image_blocks_are_candidates(
        self, db_session: AsyncSession, degenerate_properties: dict[str, object]
    ) -> None:
        # These are exactly the states the func.nullif(...->>0, '') wrapper exists to treat as
        # "no usable image". If the predicate were weakened to a plain `isnot(None)`, the empty
        # string / JSON-null / empty-array cases would wrongly drop out — this pins that behaviour.
        repo = NamedEntityRepository()
        ent = _entity(name="Degenerate 030", raw_properties=degenerate_properties)
        db_session.add(ent)
        await db_session.flush()

        selected = {e.id for e in await repo.list_grounded_without_image(db_session)}
        assert ent.id in selected

    async def test_external_ids_without_id_is_not_grounded(
        self, db_session: AsyncSession
    ) -> None:
        # A wikidata bag with no usable id (``{"wikidata": {}}``) is not grounded → excluded,
        # pinning the grounding predicate (external_ids->'wikidata'->>'id' present).
        repo = NamedEntityRepository()
        no_id = _entity(name="No Id 031", raw_external_ids={"wikidata": {}})
        db_session.add(no_id)
        await db_session.flush()

        selected = {e.id for e in await repo.list_grounded_without_image(db_session)}
        assert no_id.id not in selected

    async def test_limit_caps_results(self, db_session: AsyncSession) -> None:
        repo = NamedEntityRepository()
        db_session.add_all([_entity(name=f"Many {i:03d}") for i in range(100, 105)])
        await db_session.flush()

        capped = await repo.list_grounded_without_image(db_session, limit=2)
        assert len(capped) == 2
