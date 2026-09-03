"""Integration tests for accent-insensitive, alias-inclusive entity search (Feature 072).

Real-DB tests (chronovista_integration_test). All fixtures use SYNTHETIC names
with unique, feature-tagged (F072) nonce tokens — never library content
(Constitution VI). The nonce keeps each seeded row's search unique so the shared
integration DB's other rows never collide with these assertions.

Note on FR-003 (single-fold reuse): "same normalization as entity membership" is a
code-structure constraint that a black-box API test cannot prove — it is verified
structurally by the repository importing the shared ``_folded`` helper
(``named_entity_repository`` -> ``entity_mention_repository._folded``), not here.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from chronovista.db.models import EntityAlias as EntityAliasDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from tests.factories.named_entity_orm_factory import create_named_entity_db

pytestmark = pytest.mark.asyncio

# Feature-tagged, ASCII-only (unaccent-neutral), globally unique nonce tokens.
_NONCE_A = "F072nameA"  # accent lives in the STORED name
_NONCE_B = "F072nameB"  # accent lives in the QUERY; the stored name is plain
_NORMS = {"renee-072-a", "zoe-072-b"}


@pytest.fixture
async def seeded_entities(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[dict[str, str], None]:
    """Seed two synthetic ``person`` entities and yield their ids.

    A — ``canonical_name`` stored WITH an accent (``"Rénée <nonce>"``).
    B — ``canonical_name`` stored WITHOUT an accent (``"Zoe <nonce>"``).
    """
    a = create_named_entity_db(
        canonical_name=f"Rénée {_NONCE_A}",
        canonical_name_normalized="renee-072-a",
        entity_type="person",
    )
    b = create_named_entity_db(
        canonical_name=f"Zoe {_NONCE_B}",
        canonical_name_normalized="zoe-072-b",
        entity_type="person",
    )
    async with integration_session_factory() as session:
        session.add_all([a, b])
        await session.commit()
    ids = {"a": str(a.id), "b": str(b.id)}

    yield ids

    async with integration_session_factory() as session:
        await session.execute(
            delete(NamedEntityDB).where(
                NamedEntityDB.canonical_name_normalized.in_(_NORMS)
            )
        )
        await session.commit()


async def _search_ids(client: AsyncClient, term: str) -> set[str]:
    resp = await client.get("/api/v1/entities", params={"search": term, "limit": 200})
    assert resp.status_code == 200, resp.text
    return {row["entity_id"] for row in resp.json()["data"]}


class TestAccentInsensitiveNameSearch:
    async def test_unaccented_query_finds_accented_name(
        self, async_client: AsyncClient, seeded_entities: dict[str, str]
    ) -> None:
        # FR-001 direction 1: stored "Rénée…", query "Renee…" (no accent).
        found = await _search_ids(async_client, f"Renee {_NONCE_A}")
        assert seeded_entities["a"] in found

    async def test_accented_query_finds_unaccented_name(
        self, async_client: AsyncClient, seeded_entities: dict[str, str]
    ) -> None:
        # FR-001 direction 2: stored "Zoe…", query "Zoë…" (accented).
        found = await _search_ids(async_client, f"Zoë {_NONCE_B}")
        assert seeded_entities["b"] in found

    async def test_accented_query_matches_accented_name(
        self, async_client: AsyncClient, seeded_entities: dict[str, str]
    ) -> None:
        # Control: exact accented match must keep working.
        found = await _search_ids(async_client, f"Rénée {_NONCE_A}")
        assert seeded_entities["a"] in found

    async def test_case_insensitivity_preserved(
        self, async_client: AsyncClient, seeded_entities: dict[str, str]
    ) -> None:
        # FR-002: a lowercased (and accented) query still matches.
        found = await _search_ids(async_client, f"rénée {_NONCE_A}")
        assert seeded_entities["a"] in found


# --------------------------------------------------------------------------- #
# US2 — alias-inclusive search (search_aliases=true, exclude_alias_types=asr_error)
# --------------------------------------------------------------------------- #

# (key, canonical_name, [(alias_name, alias_type), ...], status). All tokens carry
# the F072 tag + a unique q-suffix so each search matches only its intended rows.
_SEED: list[tuple[str, str, list[tuple[str, str]], str]] = [
    ("alias", "Owner F072q40", [("Wibble F072q40", "nickname")], "active"),
    ("asr", "Plain F072q41", [("Garble F072q41", "asr_error")], "active"),
    ("dup", "Dup F072q42", [("Dup F072q42", "nickname")], "active"),
    ("merged", "Gone F072q43", [("Goalias F072q43", "nickname")], "merged"),
    ("x", "Xowner F072q44", [("Shared F072q44", "asr_error")], "active"),
    ("y", "Shared F072q44", [], "active"),
    ("acc", "Base F072q45", [("Rénée F072q45", "nickname")], "active"),
    # FR-006 reverse: alias stored PLAIN, queried ACCENTED.
    ("accrev", "Basex F072q46", [("Zoe F072q46", "nickname")], "active"),
    # FR-008 multi-alias: two aliases match, canonical does NOT (distinct token).
    (
        "multi",
        "Multibase F072zz99",
        [("Aone F072q47", "nickname"), ("Atwo F072q47", "abbreviation")],
        "active",
    ),
    # FR-005: the other four non-excluded alias types must remain searchable.
    ("nv", "NvBase F072q50", [("NvAlias F072q50", "name_variant")], "active"),
    ("ab", "AbBase F072q51", [("AbAlias F072q51", "abbreviation")], "active"),
    ("tr", "TrBase F072q52", [("TrAlias F072q52", "translated_name")], "active"),
    ("fn", "FnBase F072q53", [("FnAlias F072q53", "former_name")], "active"),
    # count<->list: cnt1 matches by canonical, cnt2 by alias, on a shared token.
    ("cnt1", "Alpha F072q60", [], "active"),
    ("cnt2", "Beta F072q61", [("Gamma F072q60", "nickname")], "active"),
]


async def _search_entities(client: AsyncClient, term: str) -> dict[str, Any]:
    """Search with the /entities-page defaults: aliases on, asr_error excluded."""
    resp = await client.get(
        "/api/v1/entities",
        params={
            "search": term,
            "limit": 200,
            "search_aliases": "true",
            "exclude_alias_types": "asr_error",
        },
    )
    assert resp.status_code == 200, resp.text
    body: dict[str, Any] = resp.json()
    return body


@pytest.fixture
async def seeded_alias_entities(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[dict[str, str], None]:
    """Seed the synthetic entities + aliases covering the US2 scenarios."""
    ids: dict[str, str] = {}
    entities: list[NamedEntityDB] = []
    aliases: list[EntityAliasDB] = []

    for key, cn, alias_specs, status in _SEED:
        entity = create_named_entity_db(
            canonical_name=cn,
            canonical_name_normalized=f"norm-072-{key}",
            entity_type="person",
            status=status,
        )
        ids[key] = str(entity.id)
        entities.append(entity)
        for i, (alias_name, alias_type) in enumerate(alias_specs):
            aliases.append(
                EntityAliasDB(
                    id=uuid.uuid4(),
                    entity_id=entity.id,
                    alias_name=alias_name,
                    alias_name_normalized=f"anorm-072-{key}-{i}",
                    alias_type=alias_type,
                )
            )

    async with integration_session_factory() as session:
        session.add_all(entities)
        await session.flush()
        session.add_all(aliases)
        await session.commit()

    yield ids

    async with integration_session_factory() as session:
        ent_ids = [uuid.UUID(v) for v in ids.values()]
        await session.execute(
            delete(EntityAliasDB).where(EntityAliasDB.entity_id.in_(ent_ids))
        )
        await session.execute(
            delete(NamedEntityDB).where(NamedEntityDB.id.in_(ent_ids))
        )
        await session.commit()


class TestAliasInclusiveSearch:
    async def test_alias_match_returns_owning_entity(
        self, async_client: AsyncClient, seeded_alias_entities: dict[str, str]
    ) -> None:
        # FR-004: a term matching an alias surfaces its owning entity.
        body = await _search_entities(async_client, "Wibble F072q40")
        assert seeded_alias_entities["alias"] in [r["entity_id"] for r in body["data"]]

    async def test_alias_match_accent_insensitive_unaccented_query(
        self, async_client: AsyncClient, seeded_alias_entities: dict[str, str]
    ) -> None:
        # FR-006 direction 1: alias stored "Rénée…"; unaccented query matches.
        body = await _search_entities(async_client, "Renee F072q45")
        assert seeded_alias_entities["acc"] in [r["entity_id"] for r in body["data"]]

    async def test_alias_match_accent_insensitive_accented_query(
        self, async_client: AsyncClient, seeded_alias_entities: dict[str, str]
    ) -> None:
        # FR-006 direction 2: alias stored PLAIN "Zoe…"; accented query matches.
        body = await _search_entities(async_client, "Zoë F072q46")
        assert seeded_alias_entities["accrev"] in [r["entity_id"] for r in body["data"]]

    @pytest.mark.parametrize(
        ("key", "term"),
        [
            ("nv", "NvAlias F072q50"),
            ("ab", "AbAlias F072q51"),
            ("tr", "TrAlias F072q52"),
            ("fn", "FnAlias F072q53"),
        ],
    )
    async def test_non_excluded_alias_types_remain_searchable(
        self,
        async_client: AsyncClient,
        seeded_alias_entities: dict[str, str],
        key: str,
        term: str,
    ) -> None:
        # FR-005: name_variant / abbreviation / translated_name / former_name all
        # remain searchable (only asr_error is excluded).
        body = await _search_entities(async_client, term)
        assert seeded_alias_entities[key] in [r["entity_id"] for r in body["data"]]

    async def test_asr_error_alias_excluded(
        self, async_client: AsyncClient, seeded_alias_entities: dict[str, str]
    ) -> None:
        # FR-005: the asr_error alias text must not surface the entity...
        body = await _search_entities(async_client, "Garble F072q41")
        assert seeded_alias_entities["asr"] not in [
            r["entity_id"] for r in body["data"]
        ]
        # ...but its canonical name still matches (control).
        body2 = await _search_entities(async_client, "Plain F072q41")
        assert seeded_alias_entities["asr"] in [r["entity_id"] for r in body2["data"]]

    async def test_name_and_alias_dedup_single_row(
        self, async_client: AsyncClient, seeded_alias_entities: dict[str, str]
    ) -> None:
        # FR-008: matching by both canonical name and alias yields exactly one row.
        body = await _search_entities(async_client, "Dup F072q42")
        ids = [r["entity_id"] for r in body["data"]]
        assert ids.count(seeded_alias_entities["dup"]) == 1

    async def test_multi_alias_dedup_single_row(
        self, async_client: AsyncClient, seeded_alias_entities: dict[str, str]
    ) -> None:
        # FR-008: an entity matched by TWO different aliases still appears once.
        body = await _search_entities(async_client, "F072q47")
        ids = [r["entity_id"] for r in body["data"]]
        assert ids.count(seeded_alias_entities["multi"]) == 1

    async def test_non_active_not_surfaced_via_alias(
        self, async_client: AsyncClient, seeded_alias_entities: dict[str, str]
    ) -> None:
        # FR-007: a merged entity is not resurrected through its alias.
        body = await _search_entities(async_client, "Goalias F072q43")
        assert seeded_alias_entities["merged"] not in [
            r["entity_id"] for r in body["data"]
        ]

    async def test_excluded_alias_does_not_suppress_legit_entity(
        self, async_client: AsyncClient, seeded_alias_entities: dict[str, str]
    ) -> None:
        # Collision: "Shared F072q44" is X's asr_error alias AND Y's canonical name.
        body = await _search_entities(async_client, "Shared F072q44")
        ids = [r["entity_id"] for r in body["data"]]
        assert seeded_alias_entities["y"] in ids  # Y via canonical
        assert seeded_alias_entities["x"] not in ids  # X only via excluded alias

    async def test_no_match_returns_empty_total_zero(
        self, async_client: AsyncClient, seeded_alias_entities: dict[str, str]
    ) -> None:
        # Edge: a non-empty query matching nothing → empty list, total 0.
        body = await _search_entities(async_client, "Nonexistent F072q99")
        assert body["data"] == []
        assert body["pagination"]["total"] == 0

    async def test_count_equals_distinct_list(
        self, async_client: AsyncClient, seeded_alias_entities: dict[str, str]
    ) -> None:
        # FR-009 / INV-6: "F072q60" matches cnt1 (canonical) + cnt2 (alias) = 2
        # distinct entities; total must equal the distinct-entity count in the list.
        body = await _search_entities(async_client, "F072q60")
        ids = [r["entity_id"] for r in body["data"]]
        expected = {seeded_alias_entities["cnt1"], seeded_alias_entities["cnt2"]}
        assert set(ids) == expected
        assert body["pagination"]["total"] == len(ids) == len(set(ids)) == 2
