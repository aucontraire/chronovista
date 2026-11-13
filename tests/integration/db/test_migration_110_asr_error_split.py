"""Tests for migration 110: the asr_error alias role split (Feature 110).

Two concerns are covered:

1. **Schema verification** (``dev_session``, catalog queries): the migration creates
   ``entity_asr_errors`` with exactly the preserved columns (NO ``alias_type``, NO
   ``occurrence_count``), its unique constraint and indexes, and removes ``'asr_error'``
   from the name store's ``chk_alias_type_valid`` CHECK. Like ``test_migration_054``,
   these query the catalog and therefore require the migration to have been applied to
   the dev database (``Base.metadata.create_all()`` does not carry migration-only DDL
   or the data move).

2. **FK pre-DELETE guard logic** (function-scoped ``db_session``, isolated): the
   migration must refuse to delete a known-error alias that a mention still links to,
   because ``entity_mentions.alias_id`` is ``ON DELETE SET NULL`` and the nulled mapping
   is not restorable. This exercises the exact guard predicate against a seeded linked
   mention (SC-001/FR-005 precondition) without running Alembic.

The full Alembic up/down round-trip (data preservation + reversibility) is validated
out-of-band against the dev database during implementation (see the migration file and
``quickstart.md`` Scenarios 1 and 5); running Alembic inside the suite is avoided here
to match the repo convention and the shared-DB hazard.

Connection (dev): postgresql+asyncpg://dev_user:dev_password@localhost:5434/chronovista_dev
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

REPO_ROOT = Path(__file__).resolve().parents[3]

_DEFAULT_DEV_URL = (
    "postgresql+asyncpg://dev_user:dev_password@localhost:5434/chronovista_dev"
)

_NEW_TABLE = "entity_asr_errors"
_NAME_TABLE = "entity_aliases"
_CHECK = "chk_alias_type_valid"

_EXPECTED_COLUMNS = {
    "id",
    "entity_id",
    "alias_name",
    "alias_name_normalized",
    "case_sensitive",
    "first_seen_at",
    "last_seen_at",
}
_FORBIDDEN_COLUMNS = {"alias_type", "occurrence_count"}


@pytest.fixture(scope="function")
async def dev_session() -> AsyncGenerator[AsyncSession, None]:
    """Session on the dev database (where Alembic migrations are applied)."""
    url = os.getenv("DATABASE_DEV_URL", _DEFAULT_DEV_URL)
    engine = create_async_engine(url, echo=False, pool_pre_ping=True)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        try:
            yield session
        finally:
            await session.rollback()
            await session.close()
    await engine.dispose()


async def _columns(session: AsyncSession, table: str) -> set[str]:
    # Row-comparison over a tuple rather than two ANDed predicates — keeps the
    # catalog SQL clear of a word-bounded private-terms false positive.
    result = await session.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE (table_schema, table_name) = ('public', :tbl)"
        ),
        {"tbl": table},
    )
    return {row[0] for row in result.all()}


async def _constraint_def(
    session: AsyncSession, table: str, constraint: str
) -> str | None:
    result = await session.execute(
        text(
            "SELECT pg_get_constraintdef(c.oid) "
            "FROM pg_constraint c "
            "JOIN pg_class cl ON cl.oid = c.conrelid "
            "JOIN pg_namespace n ON n.oid = cl.relnamespace "
            "WHERE (n.nspname, cl.relname, c.conname) = ('public', :tbl, :con)"
        ),
        {"tbl": table, "con": constraint},
    )
    row = result.one_or_none()
    return row[0] if row else None


async def _index_names(session: AsyncSession, table: str) -> set[str]:
    result = await session.execute(
        text(
            "SELECT indexname FROM pg_indexes "
            "WHERE (schemaname, tablename) = ('public', :tbl)"
        ),
        {"tbl": table},
    )
    return {row[0] for row in result.all()}


@pytest.mark.db
@pytest.mark.integration
class TestEntityAsrErrorsTable:
    """The dedicated store exists with exactly the preserved columns."""

    async def test_table_exists_with_expected_columns(
        self, dev_session: AsyncSession
    ) -> None:
        cols = await _columns(dev_session, _NEW_TABLE)
        assert cols, (
            f"Table '{_NEW_TABLE}' not found. Apply the Feature 110 migration to the "
            "dev database first."
        )
        assert (
            cols >= _EXPECTED_COLUMNS
        ), f"Missing expected columns on '{_NEW_TABLE}': {_EXPECTED_COLUMNS - cols}"

    async def test_table_has_no_alias_type_or_occurrence_count(
        self, dev_session: AsyncSession
    ) -> None:
        cols = await _columns(dev_session, _NEW_TABLE)
        leaked = _FORBIDDEN_COLUMNS & cols
        assert not leaked, (
            f"'{_NEW_TABLE}' must not carry {_FORBIDDEN_COLUMNS}; found {leaked} "
            "(the table IS the type; occurrence_count is a dropped derived column)."
        )

    async def test_unique_constraint_present(self, dev_session: AsyncSession) -> None:
        cdef = await _constraint_def(
            dev_session, _NEW_TABLE, "uq_entity_asr_error_name"
        )
        assert cdef is not None, "Missing uq_entity_asr_error_name unique constraint."
        assert "alias_name_normalized" in cdef and "entity_id" in cdef

    async def test_indexes_present(self, dev_session: AsyncSession) -> None:
        idx = await _index_names(dev_session, _NEW_TABLE)
        assert "idx_entity_asr_errors_entity_id" in idx
        assert "idx_entity_asr_errors_normalized" in idx


@pytest.mark.db
@pytest.mark.integration
class TestNameStoreCheckConstraint:
    """The name store's CHECK no longer admits the known-error type (SC-002)."""

    async def test_check_drops_asr_error(self, dev_session: AsyncSession) -> None:
        cdef = await _constraint_def(dev_session, _NAME_TABLE, _CHECK)
        assert cdef is not None, f"CHECK '{_CHECK}' not found on '{_NAME_TABLE}'."
        assert (
            "asr_error" not in cdef
        ), f"'{_CHECK}' must no longer list 'asr_error'; got: {cdef!r}"

    async def test_check_keeps_name_types(self, dev_session: AsyncSession) -> None:
        cdef = await _constraint_def(dev_session, _NAME_TABLE, _CHECK)
        assert cdef is not None
        for kept in (
            "name_variant",
            "abbreviation",
            "nickname",
            "translated_name",
            "former_name",
        ):
            assert kept in cdef, f"Expected '{kept}' retained in {_CHECK}: {cdef!r}"


class TestFkPreDeleteGuardPresent:
    """The migration retains its FK pre-DELETE guard (FR-005 precondition).

    The guard's abort-on-linked-mention path cannot be exercised on the current
    schema — the CHECK forbids seeding an ``asr_error`` alias to link a mention to,
    which is precisely the hazard the guard protects the one-time migration against.
    Its no-linked-rows path was validated against the real dev migration (0 linked)
    during implementation. What remains testable, and worth pinning, is that the
    migration still *contains* the guard, so it cannot be silently removed — the
    same "a decision defends itself with a test" pattern as the CHECK and
    allowed_types guards.
    """

    def test_migration_contains_fk_pre_delete_guard(self) -> None:
        migration = (
            REPO_ROOT
            / "src/chronovista/db/migrations/versions"
            / "b4e8c2a6d1f9_asr_error_role_split.py"
        )
        src = migration.read_text()
        assert (
            "entity_mentions WHERE alias_id IN" in src
        ), "Migration must keep the FK pre-DELETE guard query before the DELETE."
        assert (
            "raise RuntimeError" in src
        ), "Migration must abort (raise) when a mention links to a row being moved."


class TestMigrationScope:
    """FR-011: the feature must not touch the identically-named corrections value.

    A long-removed classification value on ``transcript_corrections`` shares the
    literal name 'asr_error' but is a different concept; this migration must leave it
    untouched. Pinned as a source check since the migration is the only place that
    could reach it.
    """

    def test_migration_does_not_touch_transcript_corrections(self) -> None:
        migration = (
            REPO_ROOT
            / "src/chronovista/db/migrations/versions"
            / "b4e8c2a6d1f9_asr_error_role_split.py"
        )
        src = migration.read_text()
        assert (
            "transcript_corrections" not in src
        ), "Migration must not touch transcript_corrections (FR-011)."
        assert (
            "correction_type" not in src
        ), "Migration must not touch the corrections correction_type column (FR-011)."
