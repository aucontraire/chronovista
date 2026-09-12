"""Feature 079 US2 backfill capture seam (T013): merge-preserving replace + detail-endpoint proof.

FR-024 / Cross-Feature Data Contract: the backfill's write —
``wp.merge_wikidata_blocks(current, fresh)`` followed by
``NamedEntityRepository.replace_properties`` — is exercised against the REAL Postgres write path
(repo -> DB) and read back through ``GET /api/v1/entities/{entity_id}`` (the same detail-endpoint
seam ``test_entity_enrichment_expansion_capture.py`` (T009) crosses), not reconstructed from a
mock's return value. The most important assertion here is the data-loss guard: a pre-existing
``source == "dbpedia"`` block MUST survive a Wikidata-only refresh.

Why this test does not drive ``chronovista entities backfill-wikidata-properties`` end-to-end
through ``CliRunner``: ``NamedEntityRepository.list_wikidata_grounded`` sweeps EVERY
Wikidata-grounded entity in the whole table, ordered by id — and the integration DB is shared and
never reset between runs, so it accumulates other tests' grounded placeholder entities over time.
Running the real command with ``--apply`` would overwrite ALL of their ``properties``, not just the
two rows this test seeds, and ``--limit N`` selects the first N *by id* (oldest-created first, since
ids are UUIDv7) — which never lands on freshly-inserted rows, so it cannot be used to scope the run
to just-created rows either. This test instead calls the exact write expression the command's inner
loop uses (``wp.merge_wikidata_blocks`` -> ``repo.replace_properties`` -> ``commit``) against two
entities it seeds and owns — still crossing every seam FR-024 requires (repo -> real UPDATE ->
detail endpoint) without touching any other row in the shared table. The command's own wiring
(argument parsing, the dev-DSN refusal, the backup file) is covered by the mocked CliRunner unit
test, T014, in ``tests/unit/cli/test_entity_backfill_wikidata_properties_command.py``.

Neutral placeholders only (Constitution VI).
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from chronovista.db.models import EntityAlias as EntityAliasDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.repositories.named_entity_repository import NamedEntityRepository
from chronovista.services import wikidata_properties as wp
from tests.factories.entity_association_orm_factory import EntityAliasDBFactory
from tests.factories.named_entity_orm_factory import create_named_entity_db

pytestmark = pytest.mark.asyncio

_BARE_QID = "Q000201"
_STALE_QID = "Q000202"
_SET_AT_STALE = "2020-01-01T00:00:00+00:00"
_SET_AT_FRESH = "2026-01-01T00:00:00+00:00"

# The fresh expanded bag a re-fetch returns (Feature 079): one relation block, one literal/image
# block, and the two display-only reference blocks — built from the REAL assemblers, matching the
# T009 capture test.
_FRESH: dict[str, Any] = {
    "image": wp.assemble_block([], ["Placeholder_Portrait2.jpg"], {}, _SET_AT_FRESH),
    "spouse": wp.assemble_block(
        ["Q000302"], [], {"Q000302": "Placeholder Spouse Two"}, _SET_AT_FRESH
    ),
    "wikidata_description": wp.assemble_reference_block(
        ["a fresh placeholder one-line description"], _SET_AT_FRESH
    ),
    "wikidata_aliases": wp.assemble_reference_block(
        ["Fresh Placeholder Alias"], _SET_AT_FRESH
    ),
}

# A stale wikidata-sourced block (must be DROPPED — the fresh fetch no longer asserts it) and a
# dbpedia-sourced block (must SURVIVE — merge_wikidata_blocks only replaces source=="wikidata").
_STALE_WIKIDATA_BLOCK: dict[str, Any] = wp.assemble_block(
    [], ["Stale Placeholder Occupation"], {}, _SET_AT_STALE
)
_DBPEDIA_BLOCK: dict[str, Any] = {
    "values": ["Placeholder Category"],
    "source": "dbpedia",
    "set_at": _SET_AT_STALE,
}


async def _seed_bare_grounded(
    factory: async_sessionmaker[AsyncSession], qid: str
) -> uuid.UUID:
    """A grounded entity with no properties yet — the simplest backfill case (SC-001)."""
    entity = create_named_entity_db(
        canonical_name=f"Placeholder Bare {uuid.uuid4().hex[:8]}",
        canonical_name_normalized=f"placeholder bare {uuid.uuid4().hex[:8]}",
        entity_type="person",
        external_ids={"wikidata": {"id": qid, "verified": True, "status": "verified"}},
        properties={},
    )
    async with factory() as s:
        s.add(entity)
        await s.commit()
        return uuid.UUID(str(entity.id))


async def _seed_stale_with_dbpedia_and_curated(
    factory: async_sessionmaker[AsyncSession],
    qid: str,
    *,
    description: str,
    alias_name: str,
) -> uuid.UUID:
    """A grounded entity carrying a stale wikidata block, a dbpedia block, and curated fields."""
    entity = create_named_entity_db(
        canonical_name=f"Placeholder Stale {uuid.uuid4().hex[:8]}",
        canonical_name_normalized=f"placeholder stale {uuid.uuid4().hex[:8]}",
        entity_type="person",
        description=description,
        external_ids={"wikidata": {"id": qid, "verified": True, "status": "verified"}},
        properties={
            "occupation": dict(_STALE_WIKIDATA_BLOCK),
            "category": dict(_DBPEDIA_BLOCK),
        },
    )
    async with factory() as s:
        s.add(entity)
        await s.flush()
        entity_id = uuid.UUID(str(entity.id))
        s.add(
            EntityAliasDBFactory.build(
                entity_id=entity_id,
                alias_name=alias_name,
                alias_name_normalized=alias_name.lower(),
                alias_type="nickname",
            )
        )
        await s.commit()
        return entity_id


async def test_backfill_write_path_merges_and_detail_endpoint_reflects_it(
    async_client: AsyncClient,
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The command's exact write expression, crossed for real; verified via GET (FR-024)."""
    repo = NamedEntityRepository()
    curated_description = f"Curated placeholder biography {uuid.uuid4().hex[:8]}."
    curated_alias_name = f"Curated Placeholder Alias {uuid.uuid4().hex[:8]}"

    bare_id = await _seed_bare_grounded(integration_session_factory, _BARE_QID)
    stale_id = await _seed_stale_with_dbpedia_and_curated(
        integration_session_factory,
        _STALE_QID,
        description=curated_description,
        alias_name=curated_alias_name,
    )

    # `list_wikidata_grounded` is exercised for real: confirm it actually finds both seeded rows
    # (rather than assuming its WHERE clause matches without checking). Only the two ids this test
    # owns are processed below — never anything else the shared-DB sweep returns.
    async with integration_session_factory() as s:
        grounded_ids = {e.id for e in await repo.list_wikidata_grounded(s)}
    assert {bare_id, stale_id} <= grounded_ids

    # ---- Dry run over the stale entity: must leave properties unchanged. ----
    async with integration_session_factory() as s:
        row = (
            await s.execute(select(NamedEntityDB).where(NamedEntityDB.id == stale_id))
        ).scalar_one()
        current = row.properties
        merged = wp.merge_wikidata_blocks(current, _FRESH)
        assert merged != current  # a change IS waiting — this isn't a vacuous dry run
        # Exercise the write, then roll back rather than commit — the dry-run discipline the
        # command itself follows (get_session auto-commits on scope exit, so a dry run must roll
        # back explicitly rather than merely skip the commit call).
        await repo.replace_properties(s, stale_id, properties=merged)
        await s.rollback()

    async with integration_session_factory() as s2:
        row = (
            await s2.execute(select(NamedEntityDB).where(NamedEntityDB.id == stale_id))
        ).scalar_one()
        assert row.properties == {
            "occupation": _STALE_WIKIDATA_BLOCK,
            "category": _DBPEDIA_BLOCK,
        }

    # ---- Apply over both seeded entities: the command's real write expression. ----
    for entity_id in (bare_id, stale_id):
        async with integration_session_factory() as s3:
            row = (
                await s3.execute(
                    select(NamedEntityDB).where(NamedEntityDB.id == entity_id)
                )
            ).scalar_one()
            merged = wp.merge_wikidata_blocks(row.properties, _FRESH)
            await repo.replace_properties(s3, entity_id, properties=merged)
            await s3.commit()

    # Bare entity — SC-001: every fresh-asserted field present (nothing to preserve or drop).
    resp_bare = await async_client.get(f"/api/v1/entities/{bare_id}")
    assert resp_bare.status_code == 200, resp_bare.text
    bare_props = resp_bare.json()["data"]["enrichment"]["properties"]
    assert set(_FRESH) <= set(bare_props)
    for key, block in _FRESH.items():
        assert bare_props[key] == block

    # Stale+dbpedia entity — the data-loss guard: dbpedia survives, the stale wikidata key is
    # gone, fresh keys are present, and curated fields are untouched — all through GET.
    resp_stale = await async_client.get(f"/api/v1/entities/{stale_id}")
    assert resp_stale.status_code == 200, resp_stale.text
    stale_data = resp_stale.json()["data"]
    stale_props = stale_data["enrichment"]["properties"]
    assert stale_props["category"] == _DBPEDIA_BLOCK  # dbpedia SURVIVED — the guard
    assert "occupation" not in stale_props  # stale wikidata key dropped
    assert set(_FRESH) <= set(stale_props)  # SC-001
    for key, block in _FRESH.items():
        assert stale_props[key] == block

    assert stale_data["description"] == curated_description
    aliases_by_name = {a["alias_name"]: a for a in stale_data["aliases"]}
    assert curated_alias_name in aliases_by_name

    # And directly against Postgres — the endpoint response renders these columns; confirm the
    # underlying row (not just the response) is untouched too.
    async with integration_session_factory() as s4:
        row = (
            await s4.execute(select(NamedEntityDB).where(NamedEntityDB.id == stale_id))
        ).scalar_one()
        assert row.description == curated_description
        alias_rows = (
            (
                await s4.execute(
                    select(EntityAliasDB).where(EntityAliasDB.entity_id == stale_id)
                )
            )
            .scalars()
            .all()
        )
        assert len(alias_rows) == 1
        assert alias_rows[0].alias_name == curated_alias_name
