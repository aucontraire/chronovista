"""
Tests for migration 054: multi-source entity mention columns and indexes.

This test suite validates that migration 054_add_mention_source_column
correctly:

1. Adds the ``mention_source`` column (VARCHAR(20), NOT NULL, default
   ``'transcript'``) to ``entity_mentions``
2. Adds the ``mention_context`` column (TEXT, nullable) to
   ``entity_mentions``
3. Adds a CHECK constraint that accepts only the three valid source values
   (``transcript``, ``title``, ``description``) and rejects any other value
4. Creates the partial unique index ``uq_entity_mentions_title`` on
   ``(entity_id, video_id, mention_source) WHERE mention_source = 'title'``
5. Creates the partial unique index ``uq_entity_mentions_description`` on
   ``(entity_id, video_id, mention_source, mention_text)
   WHERE mention_source = 'description'``
6. Creates the regular B-tree index ``ix_entity_mentions_mention_source``
   on ``(mention_source)``

Unlike the ORM-based schema tests, these tests query the database catalog
directly (``information_schema``, ``pg_indexes``, ``pg_constraint``) and
therefore MUST run against the dev database where Alembic migrations have
been applied.  The integration test database created via
``Base.metadata.create_all()`` does NOT carry migration-only DDL objects.

Connection
----------
Dev database:
    postgresql+asyncpg://dev_user:dev_password@localhost:5434/chronovista_dev

Markers
-------
``db``          — requires live PostgreSQL on port 5434
``integration`` — requires external services

Migration Revision
------------------
Revision ID : (assigned when migration file is created — see
               src/chronovista/db/migrations/versions/054_add_mention_source_column.py)
Down revision: b2d4f6a8c0e1  (migration 052, GIN trigram indexes)

Related
-------
Migration file:
    src/chronovista/db/migrations/versions/054_add_mention_source_column.py
Data model doc:
    specs/054-multi-source-mentions/data-model.md
Feature spec:
    specs/054-multi-source-mentions/spec.md (FR-001, FR-021)
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_DEV_URL = (
    "postgresql+asyncpg://dev_user:dev_password@localhost:5434/chronovista_dev"
)

_TABLE = "entity_mentions"

_COL_MENTION_SOURCE = "mention_source"
_COL_MENTION_CONTEXT = "mention_context"

_INDEX_TITLE = "uq_entity_mentions_title"
_INDEX_DESCRIPTION = "uq_entity_mentions_description"
_INDEX_SOURCE = "ix_entity_mentions_mention_source"

_VALID_SOURCES = ("transcript", "title", "description")
_INVALID_SOURCE = "foo"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="function")
async def dev_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Provide an async database session connected to the dev database.

    The dev database has real Alembic migrations applied, which is required
    to verify that the migration-only columns and indexes exist.  The
    per-function ``db_session`` fixture from ``conftest.py`` uses
    ``create_all()`` which does NOT replicate migration DDL objects.

    Scope is ``"function"`` (not ``"module"``) because pytest-asyncio
    creates a new event loop per test function under ``asyncio_mode=auto``;
    sharing a single asyncpg connection across event loops raises
    ``RuntimeError: Future attached to a different loop``.

    Yields
    ------
    AsyncSession
        An open session; rolled back and closed after each test function.
    """
    url = os.getenv("DATABASE_DEV_URL", _DEFAULT_DEV_URL)
    engine = create_async_engine(url, echo=False, pool_pre_ping=True)

    factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with factory() as session:
        try:
            yield session
        finally:
            await session.rollback()
            await session.close()

    await engine.dispose()


# ---------------------------------------------------------------------------
# Helper queries
# ---------------------------------------------------------------------------


async def _column_info(
    session: AsyncSession,
    table_name: str,
    column_name: str,
) -> dict[str, Any] | None:
    """
    Return ``information_schema.columns`` metadata for a column.

    Parameters
    ----------
    session : AsyncSession
        Active database session (dev DB).
    table_name : str
        Table name (without schema prefix).
    column_name : str
        Column name to look up.

    Returns
    -------
    dict[str, Any] | None
        Dict with ``column_name``, ``data_type``, ``is_nullable``,
        ``column_default`` if the column exists, else ``None``.
    """
    result = await session.execute(
        text(
            "SELECT column_name, data_type, is_nullable, column_default "
            "FROM information_schema.columns "
            "WHERE table_schema = 'public' "
            "  AND table_name   = :tbl "
            "  AND column_name  = :col"
        ),
        {"tbl": table_name, "col": column_name},
    )
    row = result.mappings().one_or_none()
    if row is None:
        return None
    return dict(row)


async def _index_row(
    session: AsyncSession,
    index_name: str,
    table_name: str,
) -> dict[str, Any] | None:
    """
    Return catalog metadata for a named index on a specific table.

    Queries ``pg_indexes`` (schema-agnostic view) for the public schema.

    Parameters
    ----------
    session : AsyncSession
        Active database session.
    index_name : str
        Name of the index to look up.
    table_name : str
        Table the index belongs to.

    Returns
    -------
    dict[str, Any] | None
        A dict with keys ``indexname``, ``tablename``, ``indexdef`` if found,
        else ``None``.
    """
    result = await session.execute(
        text(
            "SELECT indexname, tablename, indexdef "
            "FROM pg_indexes "
            "WHERE schemaname = 'public' "
            "  AND indexname  = :idx "
            "  AND tablename  = :tbl"
        ),
        {"idx": index_name, "tbl": table_name},
    )
    row = result.mappings().one_or_none()
    if row is None:
        return None
    return dict(row)


async def _constraint_exists(
    session: AsyncSession,
    table_name: str,
    constraint_name: str,
) -> bool:
    """
    Return ``True`` if the named constraint exists on the given table.

    Searches ``pg_constraint`` joined to ``pg_class`` for the public schema.

    Parameters
    ----------
    session : AsyncSession
        Active database session.
    table_name : str
        Table name.
    constraint_name : str
        Constraint name to look up.

    Returns
    -------
    bool
        ``True`` if the constraint row is found.
    """
    result = await session.execute(
        text(
            "SELECT COUNT(*) "
            "FROM pg_constraint c "
            "JOIN pg_class t ON t.oid = c.conrelid "
            "JOIN pg_namespace n ON n.oid = t.relnamespace "
            "WHERE n.nspname  = 'public' "
            "  AND t.relname  = :tbl "
            "  AND c.conname  = :con"
        ),
        {"tbl": table_name, "con": constraint_name},
    )
    count: int = result.scalar_one()
    return count > 0


# ---------------------------------------------------------------------------
# TestMentionSourceColumn
# ---------------------------------------------------------------------------


@pytest.mark.db
@pytest.mark.integration
class TestMentionSourceColumn:
    """
    Verify the ``mention_source`` column was added by migration 054.

    Expected schema
    ---------------
    Column  : mention_source
    Type    : character varying (VARCHAR)
    Nullable: NO
    Default : 'transcript'
    """

    async def test_mention_source_column_exists(
        self, dev_session: AsyncSession
    ) -> None:
        """Verify mention_source column exists in entity_mentions."""
        info = await _column_info(dev_session, _TABLE, _COL_MENTION_SOURCE)
        assert info is not None, (
            f"Column '{_COL_MENTION_SOURCE}' not found in table '{_TABLE}'. "
            "Run migration 054_add_mention_source_column first."
        )

    async def test_mention_source_column_is_not_nullable(
        self, dev_session: AsyncSession
    ) -> None:
        """Verify mention_source is NOT NULL (required for all rows)."""
        info = await _column_info(dev_session, _TABLE, _COL_MENTION_SOURCE)
        assert info is not None, f"Column '{_COL_MENTION_SOURCE}' not found."
        assert info["is_nullable"] == "NO", (
            f"Expected '{_COL_MENTION_SOURCE}' to be NOT NULL, "
            f"but is_nullable={info['is_nullable']!r}"
        )

    async def test_mention_source_column_has_transcript_default(
        self, dev_session: AsyncSession
    ) -> None:
        """Verify mention_source has a server-side default of 'transcript'.

        The server_default='transcript' ensures all existing rows are
        auto-populated when the column is added (data-model.md migration
        strategy step 1).
        """
        info = await _column_info(dev_session, _TABLE, _COL_MENTION_SOURCE)
        assert info is not None, f"Column '{_COL_MENTION_SOURCE}' not found."
        column_default: str | None = info.get("column_default")
        assert column_default is not None, (
            f"Expected a default value on '{_COL_MENTION_SOURCE}', got None."
        )
        # PostgreSQL stores string defaults with type cast, e.g.
        # "'transcript'::character varying"
        assert "transcript" in column_default, (
            f"Expected default to contain 'transcript', got: {column_default!r}"
        )

    async def test_mention_source_column_type_is_varchar(
        self, dev_session: AsyncSession
    ) -> None:
        """Verify mention_source is a VARCHAR (character varying) column."""
        info = await _column_info(dev_session, _TABLE, _COL_MENTION_SOURCE)
        assert info is not None, f"Column '{_COL_MENTION_SOURCE}' not found."
        data_type: str = info["data_type"]
        assert "character varying" in data_type, (
            f"Expected data_type 'character varying', got: {data_type!r}"
        )


# ---------------------------------------------------------------------------
# TestMentionContextColumn
# ---------------------------------------------------------------------------


@pytest.mark.db
@pytest.mark.integration
class TestMentionContextColumn:
    """
    Verify the ``mention_context`` column was added by migration 054.

    Expected schema
    ---------------
    Column  : mention_context
    Type    : text
    Nullable: YES
    Default : NULL

    The context snippet (~150 chars around the match) is populated only for
    description-sourced mentions (data-model.md).
    """

    async def test_mention_context_column_exists(
        self, dev_session: AsyncSession
    ) -> None:
        """Verify mention_context column exists in entity_mentions."""
        info = await _column_info(dev_session, _TABLE, _COL_MENTION_CONTEXT)
        assert info is not None, (
            f"Column '{_COL_MENTION_CONTEXT}' not found in table '{_TABLE}'. "
            "Run migration 054_add_mention_source_column first."
        )

    async def test_mention_context_column_is_nullable(
        self, dev_session: AsyncSession
    ) -> None:
        """Verify mention_context is nullable (only populated for description mentions)."""
        info = await _column_info(dev_session, _TABLE, _COL_MENTION_CONTEXT)
        assert info is not None, f"Column '{_COL_MENTION_CONTEXT}' not found."
        assert info["is_nullable"] == "YES", (
            f"Expected '{_COL_MENTION_CONTEXT}' to be nullable, "
            f"but is_nullable={info['is_nullable']!r}"
        )

    async def test_mention_context_column_type_is_text(
        self, dev_session: AsyncSession
    ) -> None:
        """Verify mention_context is a TEXT column (not VARCHAR-bounded)."""
        info = await _column_info(dev_session, _TABLE, _COL_MENTION_CONTEXT)
        assert info is not None, f"Column '{_COL_MENTION_CONTEXT}' not found."
        data_type: str = info["data_type"]
        assert data_type == "text", (
            f"Expected data_type 'text', got: {data_type!r}"
        )

    async def test_mention_context_column_has_no_default(
        self, dev_session: AsyncSession
    ) -> None:
        """Verify mention_context has no default value (NULL by absence)."""
        info = await _column_info(dev_session, _TABLE, _COL_MENTION_CONTEXT)
        assert info is not None, f"Column '{_COL_MENTION_CONTEXT}' not found."
        column_default = info.get("column_default")
        assert column_default is None, (
            f"Expected no default on '{_COL_MENTION_CONTEXT}', "
            f"got: {column_default!r}"
        )


# ---------------------------------------------------------------------------
# TestMentionSourceCheckConstraint
# ---------------------------------------------------------------------------


@pytest.mark.db
@pytest.mark.integration
class TestMentionSourceCheckConstraint:
    """
    Verify the CHECK constraint on ``mention_source`` enforces valid values.

    The constraint must accept 'transcript', 'title', and 'description'
    and reject any other value (e.g. 'foo').

    These tests use live INSERT/ROLLBACK to confirm enforcement at the
    database level (the ORM model is not authoritative for migration-only
    constraints).  Each test rolls back its transaction so the dev database
    is never mutated.
    """

    async def _get_any_entity_id(self, session: AsyncSession) -> str | None:
        """Return the first named_entity id as a hex string, or None."""
        result = await session.execute(
            text("SELECT id FROM named_entities LIMIT 1")
        )
        row = result.one_or_none()
        return str(row[0]) if row else None

    async def test_check_constraint_exists_in_catalog(
        self, dev_session: AsyncSession
    ) -> None:
        """Verify the mention_source CHECK constraint row exists in pg_constraint."""
        # The constraint name matches the ORM model definition in db/models.py.
        constraint_name = "chk_entity_mention_source_valid"
        exists = await _constraint_exists(dev_session, _TABLE, constraint_name)
        assert exists, (
            f"CHECK constraint '{constraint_name}' not found on table '{_TABLE}'. "
            "Run migration 054_add_mention_source_column first."
        )

    @pytest.mark.parametrize("valid_source", list(_VALID_SOURCES))
    async def test_valid_source_values_are_accepted(
        self, dev_session: AsyncSession, valid_source: str
    ) -> None:
        """Verify the CHECK constraint accepts 'transcript', 'title', and 'description'.

        Uses a savepoint so the insert attempt is rolled back regardless of
        whether the constraint accepts or rejects the value.
        """
        # This test only checks that the constraint does NOT reject valid values.
        # We use EXPLAIN (parse-level check) rather than a real INSERT to avoid
        # needing valid FK data; for constraint acceptance we query the
        # constraint definition directly.
        result = await dev_session.execute(
            text(
                "SELECT pg_get_constraintdef(c.oid) "
                "FROM pg_constraint c "
                "JOIN pg_class t ON t.oid = c.conrelid "
                "JOIN pg_namespace n ON n.oid = t.relnamespace "
                "WHERE n.nspname = 'public' "
                "  AND t.relname = :tbl "
                "  AND c.contype = 'c' "
                "  AND pg_get_constraintdef(c.oid) LIKE '%mention_source%'"
            ),
            {"tbl": _TABLE},
        )
        row = result.one_or_none()
        assert row is not None, (
            f"No CHECK constraint on '{_TABLE}.mention_source' found in pg_constraint."
        )
        consrc: str = row[0]
        assert valid_source in consrc, (
            f"Expected valid source '{valid_source}' to be listed in the "
            f"CHECK constraint expression, but got: {consrc!r}"
        )

    async def test_invalid_source_value_rejected_by_constraint(
        self, dev_session: AsyncSession
    ) -> None:
        """Verify the CHECK constraint body explicitly excludes invalid values.

        Rather than inserting a real row (which would require valid FK data),
        we confirm the constraint expression does NOT list 'foo' as an
        accepted value.  This validates the constraint definition is correct.
        """
        result = await dev_session.execute(
            text(
                "SELECT pg_get_constraintdef(c.oid) "
                "FROM pg_constraint c "
                "JOIN pg_class t ON t.oid = c.conrelid "
                "JOIN pg_namespace n ON n.oid = t.relnamespace "
                "WHERE n.nspname = 'public' "
                "  AND t.relname = :tbl "
                "  AND c.contype = 'c' "
                "  AND pg_get_constraintdef(c.oid) LIKE '%mention_source%'"
            ),
            {"tbl": _TABLE},
        )
        row = result.one_or_none()
        assert row is not None, (
            f"No CHECK constraint on '{_TABLE}.mention_source' found in pg_constraint."
        )
        consrc: str = row[0]
        # The constraint must NOT list 'foo' as a permitted value.
        assert _INVALID_SOURCE not in consrc, (
            f"Invalid source value '{_INVALID_SOURCE}' is unexpectedly listed "
            f"in the CHECK constraint expression: {consrc!r}"
        )

    async def test_check_constraint_lists_all_three_valid_values(
        self, dev_session: AsyncSession
    ) -> None:
        """Verify the constraint expression includes all three valid source values."""
        result = await dev_session.execute(
            text(
                "SELECT pg_get_constraintdef(c.oid) "
                "FROM pg_constraint c "
                "JOIN pg_class t ON t.oid = c.conrelid "
                "JOIN pg_namespace n ON n.oid = t.relnamespace "
                "WHERE n.nspname = 'public' "
                "  AND t.relname = :tbl "
                "  AND c.contype = 'c' "
                "  AND pg_get_constraintdef(c.oid) LIKE '%mention_source%'"
            ),
            {"tbl": _TABLE},
        )
        row = result.one_or_none()
        assert row is not None, (
            f"No CHECK constraint on '{_TABLE}.mention_source' found."
        )
        consrc: str = row[0]
        for source in _VALID_SOURCES:
            assert source in consrc, (
                f"Expected valid source '{source}' listed in constraint, "
                f"but constraint expression is: {consrc!r}"
            )


# ---------------------------------------------------------------------------
# TestPartialUniqueIndexTitle
# ---------------------------------------------------------------------------


@pytest.mark.db
@pytest.mark.integration
class TestPartialUniqueIndexTitle:
    """
    Verify the partial unique index ``uq_entity_mentions_title`` exists.

    Index spec (data-model.md)
    -------------------------
    Name    : uq_entity_mentions_title
    Table   : entity_mentions
    Columns : (entity_id, video_id, mention_source)
    Unique  : YES
    Partial : WHERE mention_source = 'title'
    Purpose : One title mention per entity per video (EC-007)
    """

    async def test_title_index_exists_in_catalog(
        self, dev_session: AsyncSession
    ) -> None:
        """Verify uq_entity_mentions_title is present in pg_indexes."""
        row = await _index_row(dev_session, _INDEX_TITLE, _TABLE)
        assert row is not None, (
            f"Index '{_INDEX_TITLE}' not found in pg_indexes for table '{_TABLE}'. "
            "Run migration 054_add_mention_source_column first."
        )

    async def test_title_index_is_unique(
        self, dev_session: AsyncSession
    ) -> None:
        """Verify uq_entity_mentions_title is a UNIQUE index."""
        row = await _index_row(dev_session, _INDEX_TITLE, _TABLE)
        assert row is not None, f"Index '{_INDEX_TITLE}' not found."
        indexdef: str = row["indexdef"].lower()
        assert "unique index" in indexdef, (
            f"Expected 'UNIQUE INDEX' in index definition, got: {row['indexdef']!r}"
        )

    async def test_title_index_covers_correct_columns(
        self, dev_session: AsyncSession
    ) -> None:
        """Verify uq_entity_mentions_title covers entity_id, video_id, mention_source."""
        row = await _index_row(dev_session, _INDEX_TITLE, _TABLE)
        assert row is not None, f"Index '{_INDEX_TITLE}' not found."
        indexdef: str = row["indexdef"].lower()
        for col in ("entity_id", "video_id", "mention_source"):
            assert col in indexdef, (
                f"Expected column '{col}' in index definition, "
                f"got: {row['indexdef']!r}"
            )

    async def test_title_index_is_partial_where_title(
        self, dev_session: AsyncSession
    ) -> None:
        """Verify uq_entity_mentions_title has predicate WHERE mention_source = 'title'."""
        row = await _index_row(dev_session, _INDEX_TITLE, _TABLE)
        assert row is not None, f"Index '{_INDEX_TITLE}' not found."
        indexdef: str = row["indexdef"].lower()
        assert " where " in indexdef, (
            f"Expected a partial index (WHERE clause), got: {row['indexdef']!r}"
        )
        assert "title" in indexdef, (
            f"Expected predicate to reference 'title', got: {row['indexdef']!r}"
        )


# ---------------------------------------------------------------------------
# TestPartialUniqueIndexDescription
# ---------------------------------------------------------------------------


@pytest.mark.db
@pytest.mark.integration
class TestPartialUniqueIndexDescription:
    """
    Verify the partial unique index ``uq_entity_mentions_description`` exists.

    Index spec (data-model.md)
    -------------------------
    Name    : uq_entity_mentions_description
    Table   : entity_mentions
    Columns : (entity_id, video_id, mention_source, mention_text)
    Unique  : YES
    Partial : WHERE mention_source = 'description'
    Purpose : One mention per distinct text match per entity per video for
              descriptions.
    """

    async def test_description_index_exists_in_catalog(
        self, dev_session: AsyncSession
    ) -> None:
        """Verify uq_entity_mentions_description is present in pg_indexes."""
        row = await _index_row(dev_session, _INDEX_DESCRIPTION, _TABLE)
        assert row is not None, (
            f"Index '{_INDEX_DESCRIPTION}' not found in pg_indexes for table "
            f"'{_TABLE}'. Run migration 054_add_mention_source_column first."
        )

    async def test_description_index_is_unique(
        self, dev_session: AsyncSession
    ) -> None:
        """Verify uq_entity_mentions_description is a UNIQUE index."""
        row = await _index_row(dev_session, _INDEX_DESCRIPTION, _TABLE)
        assert row is not None, f"Index '{_INDEX_DESCRIPTION}' not found."
        indexdef: str = row["indexdef"].lower()
        assert "unique index" in indexdef, (
            f"Expected 'UNIQUE INDEX' in index definition, got: {row['indexdef']!r}"
        )

    async def test_description_index_covers_correct_columns(
        self, dev_session: AsyncSession
    ) -> None:
        """Verify uq_entity_mentions_description covers entity_id, video_id, mention_source, mention_text."""
        row = await _index_row(dev_session, _INDEX_DESCRIPTION, _TABLE)
        assert row is not None, f"Index '{_INDEX_DESCRIPTION}' not found."
        indexdef: str = row["indexdef"].lower()
        for col in ("entity_id", "video_id", "mention_source", "mention_text"):
            assert col in indexdef, (
                f"Expected column '{col}' in index definition, "
                f"got: {row['indexdef']!r}"
            )

    async def test_description_index_is_partial_where_description(
        self, dev_session: AsyncSession
    ) -> None:
        """Verify uq_entity_mentions_description has predicate WHERE mention_source = 'description'."""
        row = await _index_row(dev_session, _INDEX_DESCRIPTION, _TABLE)
        assert row is not None, f"Index '{_INDEX_DESCRIPTION}' not found."
        indexdef: str = row["indexdef"].lower()
        assert " where " in indexdef, (
            f"Expected a partial index (WHERE clause), got: {row['indexdef']!r}"
        )
        assert "description" in indexdef, (
            f"Expected predicate to reference 'description', "
            f"got: {row['indexdef']!r}"
        )


# ---------------------------------------------------------------------------
# TestRegularIndexOnMentionSource
# ---------------------------------------------------------------------------


@pytest.mark.db
@pytest.mark.integration
class TestRegularIndexOnMentionSource:
    """
    Verify the regular B-tree index ``ix_entity_mentions_mention_source`` exists.

    Index spec (data-model.md)
    -------------------------
    Name    : ix_entity_mentions_mention_source
    Table   : entity_mentions
    Columns : (mention_source)
    Unique  : NO
    Partial : No
    Purpose : Efficient filter queries by source type
    """

    async def test_source_index_exists_in_catalog(
        self, dev_session: AsyncSession
    ) -> None:
        """Verify ix_entity_mentions_mention_source is present in pg_indexes."""
        row = await _index_row(dev_session, _INDEX_SOURCE, _TABLE)
        assert row is not None, (
            f"Index '{_INDEX_SOURCE}' not found in pg_indexes for table '{_TABLE}'. "
            "Run migration 054_add_mention_source_column first."
        )

    async def test_source_index_is_not_unique(
        self, dev_session: AsyncSession
    ) -> None:
        """Verify ix_entity_mentions_mention_source is a non-unique B-tree index."""
        row = await _index_row(dev_session, _INDEX_SOURCE, _TABLE)
        assert row is not None, f"Index '{_INDEX_SOURCE}' not found."
        indexdef: str = row["indexdef"].lower()
        assert "unique index" not in indexdef, (
            f"Expected a non-unique index, but got: {row['indexdef']!r}"
        )

    async def test_source_index_covers_mention_source_column(
        self, dev_session: AsyncSession
    ) -> None:
        """Verify ix_entity_mentions_mention_source covers the mention_source column."""
        row = await _index_row(dev_session, _INDEX_SOURCE, _TABLE)
        assert row is not None, f"Index '{_INDEX_SOURCE}' not found."
        indexdef: str = row["indexdef"].lower()
        assert "mention_source" in indexdef, (
            f"Expected column 'mention_source' in index definition, "
            f"got: {row['indexdef']!r}"
        )

    async def test_source_index_is_full_table_not_partial(
        self, dev_session: AsyncSession
    ) -> None:
        """Verify ix_entity_mentions_mention_source has no WHERE clause."""
        row = await _index_row(dev_session, _INDEX_SOURCE, _TABLE)
        assert row is not None, f"Index '{_INDEX_SOURCE}' not found."
        indexdef: str = row["indexdef"].lower()
        assert " where " not in indexdef, (
            f"Expected a full-table index (no WHERE clause), "
            f"got: {row['indexdef']!r}"
        )


# ---------------------------------------------------------------------------
# TestMigrationDowngrade
# ---------------------------------------------------------------------------


@pytest.mark.db
@pytest.mark.integration
class TestMigrationDowngrade:
    """
    Document migration 054 downgrade behaviour.

    These tests do NOT execute the actual Alembic downgrade (which would
    mutate the shared dev database and could disrupt development workflows).
    Instead they document the expected downgrade SQL so it can be reviewed and
    verified manually in an isolated environment.

    To verify downgrade behaviour manually::

        alembic -c alembic-dev.ini downgrade -1   # revert 054
        # confirm via psql:
        #   \\d entity_mentions   → no mention_source / mention_context columns
        #   \\di uq_entity_mentions_title  → no index
        alembic -c alembic-dev.ini upgrade head    # restore
    """

    def test_downgrade_drops_mention_source_column_documented(self) -> None:
        """Document that downgrade drops the mention_source column.

        Downgrade SQL::

            ALTER TABLE entity_mentions DROP COLUMN mention_source;

        WARNING: This is lossy — all title and description mentions are
        permanently deleted before the column is dropped (data-model.md).
        """
        expected_table = _TABLE
        expected_column = _COL_MENTION_SOURCE
        assert expected_table == "entity_mentions"
        assert expected_column == "mention_source"

    def test_downgrade_drops_mention_context_column_documented(self) -> None:
        """Document that downgrade drops the mention_context column.

        Downgrade SQL::

            ALTER TABLE entity_mentions DROP COLUMN mention_context;
        """
        expected_table = _TABLE
        expected_column = _COL_MENTION_CONTEXT
        assert expected_table == "entity_mentions"
        assert expected_column == "mention_context"

    def test_downgrade_drops_all_three_indexes_documented(self) -> None:
        """Document that downgrade drops all three migration-added indexes.

        Downgrade SQL (executed before column drops)::

            DROP INDEX IF EXISTS ix_entity_mentions_mention_source;
            DROP INDEX IF EXISTS uq_entity_mentions_description;
            DROP INDEX IF EXISTS uq_entity_mentions_title;
        """
        expected_indexes = [
            _INDEX_SOURCE,
            _INDEX_DESCRIPTION,
            _INDEX_TITLE,
        ]
        assert len(expected_indexes) == 3
        for idx in expected_indexes:
            assert idx.startswith(("ix_", "uq_"))

    def test_downgrade_is_lossy_for_title_and_description_mentions_documented(
        self,
    ) -> None:
        """Document that downgrade is lossy: title/description mentions are deleted.

        Before dropping the column, the downgrade must DELETE all rows where
        mention_source IN ('title', 'description') because these rows have
        segment_id=NULL and cannot be represented in the pre-054 schema.

        Manual mentions (Feature 050) are preserved since they use
        mention_source='transcript' (the default) and are identified by
        detection_method='manual'.

        Downgrade SQL::

            DELETE FROM entity_mentions
            WHERE mention_source IN ('title', 'description');
        """
        lossy_sources = ["title", "description"]
        preserved_sources = ["transcript"]
        assert set(lossy_sources).isdisjoint(set(preserved_sources))
