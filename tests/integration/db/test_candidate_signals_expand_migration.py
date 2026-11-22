"""T025: Feature 116 Migration A (expand) -- candidate signals child table.

Harness choice: no test in this repo runs ``alembic upgrade`` (the integration DB is
built by ``Base.metadata.create_all`` and a shared-DB Alembic run is a hazard), so this
follows the same convention as ``test_migration_110_asr_error_split``:

1. Offline/mock: load the migration module from its file and assert on the *SQL it
   emits* (the exact child-INSERT column list, no verdict column, no parent drop).
2. Real DB (``db_session``, ORM schema == migration schema): seed parents, run the
   migration's own ``CHILD_COPY_SQL`` against them, then assert verdict safety,
   parent<->child consistency, and ``combined_score`` NULL.
3. Structural: the child's per-signal CHECK, UNIQUE and FK-cascade behave, and the
   parent's ``lift`` relaxation is in force while ``shared_video_count`` stays strict.

Name-free placeholders only.
"""

from __future__ import annotations

import importlib.util
import inspect
import re
import uuid
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import NamedEntity as NamedEntityDB

_MIGRATION = (
    Path(__file__).resolve().parents[3]
    / "src/chronovista/db/migrations/versions/b4e8a1c7d305_candidate_signals_expand_116.py"
)

_EXPECTED_INSERT_COLUMNS = {
    "id",
    "signal",
    "candidate_id",
    "support",
    "lift",
    "entity_a_video_count",
    "entity_b_video_count",
    "signal_universe",
    "both_typed_eligible",
    "kb_corroboration_count",
    "kb_corroboration_detail",
    "provenance",
}
_VERDICT_COLUMNS = (
    "review_status",
    "review_taxonomy_version",
    "review_pass_logged_rejections",
    "reviewed_by",
    "reviewed_at",
)


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("mig_b4e8a1c7d305", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestMigrationSql:
    """Offline: inspect the SQL/ops the migration emits (no DB)."""

    def test_revision_chain(self) -> None:
        mig = _load_migration()
        assert mig.revision == "b4e8a1c7d305"
        assert mig.down_revision == "a9d3f6b2c481"

    def test_child_insert_column_list_is_exact(self) -> None:
        sql: str = _load_migration().CHILD_COPY_SQL
        match = re.match(
            r"INSERT INTO relationship_candidate_signals \(([^)]*)\) SELECT", sql
        )
        assert match is not None
        columns = [c.strip() for c in match.group(1).split(",")]
        assert len(columns) == len(set(columns))
        assert set(columns) == _EXPECTED_INSERT_COLUMNS
        # min_gap_seconds is transcript-only: deliberately not copied for title/desc.
        assert "min_gap_seconds" not in columns

    def test_child_insert_source_mapping(self) -> None:
        sql: str = _load_migration().CHILD_COPY_SQL
        select_list = sql.split(") SELECT ", 1)[1].split(" FROM ", 1)[0]
        assert [s.strip() for s in select_list.split(",")] == [
            "gen_random_uuid()",
            "'title_description'",
            "id",
            "shared_video_count",
            "lift",
            "entity_a_video_count",
            "entity_b_video_count",
            "channel_video_universe",
            "both_typed_eligible",
            "kb_corroboration_count",
            "kb_corroboration_detail",
            "provenance",
        ]
        assert sql.endswith(
            "FROM relationship_candidates WHERE channel = 'title_description'"
        )

    def test_copy_sql_is_insert_only_and_touches_no_verdict_column(self) -> None:
        sql: str = _load_migration().CHILD_COPY_SQL
        assert sql.startswith("INSERT INTO relationship_candidate_signals")
        for verb in ("UPDATE", "DELETE", "DROP", "ALTER"):
            assert verb not in sql.upper()
        for column in _VERDICT_COLUMNS:
            assert column not in sql

    def test_upgrade_source_never_mentions_verdict_or_drops_parent_columns(
        self,
    ) -> None:
        mig = _load_migration()
        src = inspect.getsource(mig.upgrade)
        for column in _VERDICT_COLUMNS:
            assert column not in src
        assert "drop_column" not in src
        assert "combined_score" in src and "shared_video_count" not in src
        # Only lift is relaxed; the shared-count constraint is left alone.
        assert "chk_relationship_lift_min" in src
        assert "chk_relationship_shared_min" not in src
        assert "UPDATE" not in src.upper()

    def test_downgrade_restores_lift_and_drops_new_objects(self) -> None:
        src = inspect.getsource(_load_migration().downgrade)
        assert 'drop_table("relationship_candidate_signals")' in src
        assert '"combined_score"' in src
        assert "chk_relationship_lift_min" in src
        assert "nullable=False" in src


async def _entity(session: AsyncSession, tag: str) -> uuid.UUID:
    entity = NamedEntityDB(
        id=uuid.uuid4(),
        canonical_name=tag,
        canonical_name_normalized=tag.lower(),
        entity_type="person",
    )
    session.add(entity)
    await session.flush()
    return entity.id


async def _seed_parents(session: AsyncSession) -> list[uuid.UUID]:
    """Seed parents incl. one with a verdict; raw INSERT mirrors pre-expand rows."""
    ids: list[uuid.UUID] = []
    for i in range(3):
        a, b = sorted(
            [await _entity(session, f"Ent{i}A"), await _entity(session, f"Ent{i}B")]
        )
        cid = uuid.uuid4()
        ids.append(cid)
        await session.execute(
            text(
                "INSERT INTO relationship_candidates (id, entity_a_id, entity_b_id, "
                "channel, shared_video_count, lift, entity_a_video_count, "
                "entity_b_video_count, channel_video_universe, both_typed_eligible, "
                "kb_corroboration_count, kb_corroboration_detail, provenance, "
                "review_status, review_taxonomy_version, reviewed_by) VALUES "
                "(:id, :a, :b, 'title_description', :sv, :lift, :ac, :bc, :n, :elig, "
                ":kb, CAST(:kbd AS jsonb), CAST(:prov AS jsonb), :rs, :rtax, :rb)"
            ),
            {
                "id": cid,
                "a": a,
                "b": b,
                "sv": 5 + i,
                "lift": 6.5 + i,
                "ac": 10 + i,
                "bc": 20 + i,
                "n": 1000 + i,
                "elig": i % 2 == 0,
                "kb": i,
                "kbd": f'{{"k": {i}}}',
                "prov": f'{{"gen": "v{i}"}}',
                "rs": "reviewed_placeholder" if i == 0 else None,
                "rtax": "v-test" if i == 0 else None,
                "rb": "tester" if i == 0 else None,
            },
        )
    return ids


async def _verdict_snapshot(session: AsyncSession) -> list[Any]:
    cols = ", ".join(_VERDICT_COLUMNS)
    result = await session.execute(
        text(f"SELECT id, {cols} FROM relationship_candidates ORDER BY id")
    )
    return [tuple(r) for r in result.all()]


@pytest.mark.asyncio
class TestExpandAgainstDb:
    async def test_copy_consistency_verdict_safety_and_combined_score(
        self, db_session: AsyncSession
    ) -> None:
        parent_ids = await _seed_parents(db_session)
        before = await _verdict_snapshot(db_session)
        assert any(row[1] is not None for row in before)  # a real verdict exists

        await db_session.execute(text(_load_migration().CHILD_COPY_SQL))

        # Verdict safety: before/after review columns are identical (empty diff).
        assert await _verdict_snapshot(db_session) == before

        # Exactly one title_description child per parent.
        per_parent = await db_session.execute(
            text(
                "SELECT p.id, count(c.id) FROM relationship_candidates p "
                "LEFT JOIN relationship_candidate_signals c "
                "ON c.candidate_id = p.id AND c.signal = 'title_description' "
                "GROUP BY p.id"
            )
        )
        assert {r[0]: r[1] for r in per_parent.all()} == dict.fromkeys(parent_ids, 1)

        # Identical copied values (IS DISTINCT FROM => NULL-safe).
        mismatches = await db_session.execute(
            text(
                "SELECT count(*) FROM relationship_candidates p "
                "JOIN relationship_candidate_signals c ON c.candidate_id = p.id "
                "WHERE p.lift IS DISTINCT FROM c.lift "
                "OR p.shared_video_count IS DISTINCT FROM c.support "
                "OR p.entity_a_video_count IS DISTINCT FROM c.entity_a_video_count "
                "OR p.entity_b_video_count IS DISTINCT FROM c.entity_b_video_count "
                "OR p.channel_video_universe IS DISTINCT FROM c.signal_universe "
                "OR p.both_typed_eligible IS DISTINCT FROM c.both_typed_eligible "
                "OR p.kb_corroboration_count IS DISTINCT FROM c.kb_corroboration_count "
                "OR p.kb_corroboration_detail IS DISTINCT FROM c.kb_corroboration_detail "
                "OR p.provenance IS DISTINCT FROM c.provenance "
                "OR c.min_gap_seconds IS NOT NULL"
            )
        )
        assert mismatches.scalar_one() == 0

        # combined_score deliberately left NULL on every parent.
        non_null = await db_session.execute(
            text(
                "SELECT count(*) FROM relationship_candidates WHERE combined_score IS NOT NULL"
            )
        )
        assert non_null.scalar_one() == 0

    async def test_parent_lift_relaxed_shared_count_still_strict(
        self, db_session: AsyncSession
    ) -> None:
        a, b = sorted(
            [await _entity(db_session, "RelaxA"), await _entity(db_session, "RelaxB")]
        )
        insert = (
            "INSERT INTO relationship_candidates (id, entity_a_id, entity_b_id, channel, "
            "shared_video_count, lift, entity_a_video_count, entity_b_video_count, "
            "channel_video_universe) VALUES (:id, :a, :b, 'transcript', :sv, NULL, 1, 1, 1)"
        )
        # lift NULL is now allowed (transcript-style parent) ...
        await db_session.execute(
            text(insert), {"id": uuid.uuid4(), "a": a, "b": b, "sv": 5}
        )
        # ... but shared_video_count >= 5 is retained.
        c, d = sorted(
            [await _entity(db_session, "RelaxC"), await _entity(db_session, "RelaxD")]
        )
        with pytest.raises(IntegrityError):
            async with db_session.begin_nested():
                await db_session.execute(
                    text(insert), {"id": uuid.uuid4(), "a": c, "b": d, "sv": 4}
                )

    async def test_child_constraints(self, db_session: AsyncSession) -> None:
        (parent_id,) = (await _seed_parents(db_session))[:1]
        ins = (
            "INSERT INTO relationship_candidate_signals (id, candidate_id, signal, "
            "support, lift, entity_a_video_count, entity_b_video_count, signal_universe) "
            "VALUES (gen_random_uuid(), :c, :s, :sup, :lift, 1, 1, 1)"
        )

        async def attempt(signal: str, support: int, lift: float | None) -> None:
            async with db_session.begin_nested():
                await db_session.execute(
                    text(ins),
                    {"c": parent_id, "s": signal, "sup": support, "lift": lift},
                )

        # Valid transcript signal: lift NULL, support >= 1.
        await attempt("transcript", 1, None)
        # Duplicate (candidate_id, signal) rejected.
        with pytest.raises(IntegrityError):
            await attempt("transcript", 2, None)
        # Structural CHECK violations.
        for bad in (
            ("title_description", 5, None),  # title/desc needs lift
            ("title_description", 4, 6.0),  # support floor
            ("title_description", 5, 4.9),  # lift floor
            ("transcript", 1, 6.0),  # transcript must not carry lift
            ("transcript", 0, None),  # support >= 1
            ("bogus", 5, 6.0),  # unknown signal
        ):
            with pytest.raises(IntegrityError):
                await attempt(*bad)

    async def test_deleting_parent_cascades_to_children(
        self, db_session: AsyncSession
    ) -> None:
        await _seed_parents(db_session)
        await db_session.execute(text(_load_migration().CHILD_COPY_SQL))
        await db_session.execute(text("DELETE FROM relationship_candidates"))
        left = await db_session.execute(
            text("SELECT count(*) FROM relationship_candidate_signals")
        )
        assert left.scalar_one() == 0
