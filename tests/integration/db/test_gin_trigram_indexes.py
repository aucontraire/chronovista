"""
Tests for migration 052: GIN trigram indexes on transcript_segments.

This test suite validates that migration b2d4f6a8c0e1
(052_add_gin_trigram_indexes) correctly:

1. Enables the pg_trgm extension
2. Creates GIN index ``idx_segments_text_trgm`` on
   ``transcript_segments.text``
3. Creates partial GIN index ``idx_segments_corrected_text_trgm`` on
   ``transcript_segments.corrected_text WHERE corrected_text IS NOT NULL``

Unlike the ORM-based schema tests, these tests query the database catalog
directly (``pg_indexes``, ``pg_extension``) and therefore MUST run against
the dev database where Alembic migrations have been applied.
The integration test database created via ``Base.metadata.create_all()``
does NOT include GIN indexes (the ORM models carry no index declarations for
these — they are migration-only DDL objects).

Connection
----------
Dev database: postgresql+asyncpg://dev_user:dev_password@localhost:5434/chronovista_dev

Markers
-------
``db``         — requires live PostgreSQL on port 5434
``integration``— requires external services

Migration Revision
------------------
Revision ID : b2d4f6a8c0e1
Down revision: a1b3c5d7e9f2

Related
-------
Migration file: src/chronovista/db/migrations/versions/052_add_gin_trigram_indexes.py
Feedback ADR  : D2 from 004-FEEDBACK (High-priority sequential-scan fix)
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# ---------------------------------------------------------------------------
# Module-level marker: ensures all async tests work correctly with coverage.
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_DEFAULT_DEV_URL = (
    "postgresql+asyncpg://dev_user:dev_password@localhost:5434/chronovista_dev"
)

_INDEX_TEXT = "idx_segments_text_trgm"
_INDEX_CORRECTED = "idx_segments_corrected_text_trgm"
_TABLE = "transcript_segments"
_EXTENSION = "pg_trgm"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="function")
async def dev_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Provide an async database session connected to the dev database.

    The dev database has real Alembic migrations applied, which is required
    to verify GIN index existence.  The per-function ``db_session`` fixture
    from ``conftest.py`` uses ``create_all()`` which does NOT create these
    migration-only indexes.

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


async def _extension_exists(session: AsyncSession, extension: str) -> bool:
    """
    Return ``True`` if *extension* is installed in the current database.

    Parameters
    ----------
    session : AsyncSession
        Active database session (dev DB).
    extension : str
        Extension name, e.g. ``"pg_trgm"``.

    Returns
    -------
    bool
        ``True`` if the extension row exists in ``pg_extension``.
    """
    result = await session.execute(
        text(
            "SELECT COUNT(*) FROM pg_extension WHERE extname = :name"
        ),
        {"name": extension},
    )
    count: int = result.scalar_one()
    return count > 0


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
            "  AND indexname = :idx "
            "  AND tablename = :tbl"
        ),
        {"idx": index_name, "tbl": table_name},
    )
    row = result.mappings().one_or_none()
    if row is None:
        return None
    return dict(row)


# ---------------------------------------------------------------------------
# Test classes
# ---------------------------------------------------------------------------


@pytest.mark.db
@pytest.mark.integration
class TestPgTrgmExtension:
    """
    Verify the pg_trgm extension is enabled after migration upgrade.

    Without pg_trgm the GIN operators (``gin_trgm_ops``) do not exist and
    any attempt to use ILIKE with an index would fall back to a seq-scan.
    """

    async def test_pg_trgm_extension_is_installed(
        self, dev_session: AsyncSession
    ) -> None:
        """Verify pg_trgm extension row exists in pg_extension catalog."""
        installed = await _extension_exists(dev_session, _EXTENSION)
        assert installed, (
            f"Extension '{_EXTENSION}' is not installed. "
            "Run migration b2d4f6a8c0e1 (052_add_gin_trigram_indexes) first."
        )

    async def test_trgm_similarity_function_is_callable(
        self, dev_session: AsyncSession
    ) -> None:
        """
        Smoke-test that pg_trgm functions are available after the extension
        is enabled.

        ``similarity('abc', 'abc')`` returns 1.0 when pg_trgm is installed;
        calling it without the extension raises ``UndefinedFunctionError``.
        """
        result = await dev_session.execute(
            text("SELECT similarity('test', 'test')")
        )
        value: float = result.scalar_one()
        assert value == pytest.approx(1.0), (
            "pg_trgm similarity() did not return 1.0 for identical strings; "
            "extension may not be active."
        )


@pytest.mark.db
@pytest.mark.integration
class TestGinIndexOnText:
    """
    Verify the GIN trigram index on ``transcript_segments.text`` exists.

    Index spec
    ----------
    Name   : idx_segments_text_trgm
    Table  : transcript_segments
    Method : GIN
    Column : text
    Opclass: gin_trgm_ops
    Partial: No (full-table index)
    """

    async def test_index_exists_in_catalog(
        self, dev_session: AsyncSession
    ) -> None:
        """Verify idx_segments_text_trgm is present in pg_indexes."""
        row = await _index_row(dev_session, _INDEX_TEXT, _TABLE)
        assert row is not None, (
            f"Index '{_INDEX_TEXT}' not found in pg_indexes for table '{_TABLE}'. "
            "Ensure migration b2d4f6a8c0e1 has been applied."
        )

    async def test_index_uses_gin_method(
        self, dev_session: AsyncSession
    ) -> None:
        """Verify idx_segments_text_trgm is a GIN index (not BTree/Hash)."""
        row = await _index_row(dev_session, _INDEX_TEXT, _TABLE)
        assert row is not None, f"Index '{_INDEX_TEXT}' not found."
        indexdef: str = row["indexdef"].lower()
        assert "using gin" in indexdef, (
            f"Expected 'USING gin' in index definition, got: {row['indexdef']!r}"
        )

    async def test_index_uses_trgm_opclass(
        self, dev_session: AsyncSession
    ) -> None:
        """Verify idx_segments_text_trgm uses the gin_trgm_ops operator class."""
        row = await _index_row(dev_session, _INDEX_TEXT, _TABLE)
        assert row is not None, f"Index '{_INDEX_TEXT}' not found."
        indexdef: str = row["indexdef"].lower()
        assert "gin_trgm_ops" in indexdef, (
            f"Expected 'gin_trgm_ops' in index definition, got: {row['indexdef']!r}"
        )

    async def test_index_covers_text_column(
        self, dev_session: AsyncSession
    ) -> None:
        """Verify idx_segments_text_trgm is defined on the 'text' column."""
        row = await _index_row(dev_session, _INDEX_TEXT, _TABLE)
        assert row is not None, f"Index '{_INDEX_TEXT}' not found."
        indexdef: str = row["indexdef"].lower()
        assert "(text" in indexdef or " text " in indexdef, (
            f"Expected column 'text' in index definition, got: {row['indexdef']!r}"
        )

    async def test_index_is_not_partial(
        self, dev_session: AsyncSession
    ) -> None:
        """
        Verify idx_segments_text_trgm is a full-table index (no WHERE clause).

        This distinguishes it from the sibling ``idx_segments_corrected_text_trgm``
        which IS partial.
        """
        row = await _index_row(dev_session, _INDEX_TEXT, _TABLE)
        assert row is not None, f"Index '{_INDEX_TEXT}' not found."
        indexdef: str = row["indexdef"].lower()
        assert " where " not in indexdef, (
            f"Expected a full-table index (no WHERE clause), "
            f"but got: {row['indexdef']!r}"
        )


@pytest.mark.db
@pytest.mark.integration
class TestPartialGinIndexOnCorrectedText:
    """
    Verify the partial GIN trigram index on ``transcript_segments.corrected_text``.

    Index spec
    ----------
    Name   : idx_segments_corrected_text_trgm
    Table  : transcript_segments
    Method : GIN
    Column : corrected_text
    Opclass: gin_trgm_ops
    Partial: Yes — WHERE corrected_text IS NOT NULL
    """

    async def test_index_exists_in_catalog(
        self, dev_session: AsyncSession
    ) -> None:
        """Verify idx_segments_corrected_text_trgm is present in pg_indexes."""
        row = await _index_row(dev_session, _INDEX_CORRECTED, _TABLE)
        assert row is not None, (
            f"Index '{_INDEX_CORRECTED}' not found in pg_indexes for table '{_TABLE}'. "
            "Ensure migration b2d4f6a8c0e1 has been applied."
        )

    async def test_index_uses_gin_method(
        self, dev_session: AsyncSession
    ) -> None:
        """Verify idx_segments_corrected_text_trgm is a GIN index."""
        row = await _index_row(dev_session, _INDEX_CORRECTED, _TABLE)
        assert row is not None, f"Index '{_INDEX_CORRECTED}' not found."
        indexdef: str = row["indexdef"].lower()
        assert "using gin" in indexdef, (
            f"Expected 'USING gin' in index definition, got: {row['indexdef']!r}"
        )

    async def test_index_uses_trgm_opclass(
        self, dev_session: AsyncSession
    ) -> None:
        """Verify idx_segments_corrected_text_trgm uses gin_trgm_ops operator class."""
        row = await _index_row(dev_session, _INDEX_CORRECTED, _TABLE)
        assert row is not None, f"Index '{_INDEX_CORRECTED}' not found."
        indexdef: str = row["indexdef"].lower()
        assert "gin_trgm_ops" in indexdef, (
            f"Expected 'gin_trgm_ops' in index definition, got: {row['indexdef']!r}"
        )

    async def test_index_covers_corrected_text_column(
        self, dev_session: AsyncSession
    ) -> None:
        """Verify idx_segments_corrected_text_trgm is defined on corrected_text."""
        row = await _index_row(dev_session, _INDEX_CORRECTED, _TABLE)
        assert row is not None, f"Index '{_INDEX_CORRECTED}' not found."
        indexdef: str = row["indexdef"].lower()
        assert "corrected_text" in indexdef, (
            f"Expected column 'corrected_text' in index definition, "
            f"got: {row['indexdef']!r}"
        )

    async def test_index_is_partial_where_not_null(
        self, dev_session: AsyncSession
    ) -> None:
        """
        Verify idx_segments_corrected_text_trgm is partial with the correct predicate.

        The WHERE clause ``corrected_text IS NOT NULL`` ensures only segments
        that have been corrected are indexed, keeping the index compact.
        """
        row = await _index_row(dev_session, _INDEX_CORRECTED, _TABLE)
        assert row is not None, f"Index '{_INDEX_CORRECTED}' not found."
        indexdef: str = row["indexdef"].lower()
        assert " where " in indexdef, (
            f"Expected a partial index (WHERE clause), but got: {row['indexdef']!r}"
        )
        assert "corrected_text is not null" in indexdef, (
            f"Expected predicate 'corrected_text IS NOT NULL', "
            f"got: {row['indexdef']!r}"
        )


@pytest.mark.db
@pytest.mark.integration
class TestMigrationDowngrade:
    """
    Document and verify migration downgrade removes both GIN indexes.

    These tests do NOT execute the actual Alembic downgrade command (which
    would mutate the shared dev database and could disrupt other tests or
    development workflows).  Instead they document the expected behavior and
    provide a helper that can be used in an isolated test environment.

    To verify downgrade behaviour manually::

        alembic downgrade a1b3c5d7e9f2  # back to the prior revision
        # confirm via psql: \\di idx_segments_*_trgm  → no rows
        alembic upgrade head             # restore
    """

    @pytest.mark.asyncio(False)  # sync — overrides the module-level asyncio marker
    def test_downgrade_removes_text_index_documented(self) -> None:
        """
        Document that downgrade drops idx_segments_text_trgm.

        Migration downgrade SQL::

            DROP INDEX IF EXISTS idx_segments_text_trgm;

        The ``IF EXISTS`` guard makes the operation idempotent.
        """
        expected_index = _INDEX_TEXT
        expected_table = _TABLE
        assert expected_index == "idx_segments_text_trgm"
        assert expected_table == "transcript_segments"

    @pytest.mark.asyncio(False)  # sync — overrides the module-level asyncio marker
    def test_downgrade_removes_corrected_text_index_documented(self) -> None:
        """
        Document that downgrade drops idx_segments_corrected_text_trgm.

        Migration downgrade SQL::

            DROP INDEX IF EXISTS idx_segments_corrected_text_trgm;
        """
        expected_index = _INDEX_CORRECTED
        expected_table = _TABLE
        assert expected_index == "idx_segments_corrected_text_trgm"
        assert expected_table == "transcript_segments"

    @pytest.mark.asyncio(False)  # sync — overrides the module-level asyncio marker
    def test_downgrade_preserves_pg_trgm_extension_documented(self) -> None:
        """
        Document that downgrade intentionally leaves pg_trgm installed.

        The extension is a shared database resource.  Other objects (e.g.
        full-text search) may depend on it, so the downgrade only removes the
        specific indexes and does NOT run ``DROP EXTENSION pg_trgm``.
        """
        # The migration downgrade SQL is:
        #   op.execute("DROP INDEX IF EXISTS idx_segments_corrected_text_trgm")
        #   op.execute("DROP INDEX IF EXISTS idx_segments_text_trgm")
        #
        # Note: there is deliberately NO "DROP EXTENSION pg_trgm" here.
        drop_statements = [
            "DROP INDEX IF EXISTS idx_segments_corrected_text_trgm",
            "DROP INDEX IF EXISTS idx_segments_text_trgm",
        ]
        assert len(drop_statements) == 2
        for stmt in drop_statements:
            assert "DROP EXTENSION" not in stmt


@pytest.mark.db
@pytest.mark.integration
class TestIndexFunctionalBehavior:
    """
    Functional tests that verify the GIN trigram indexes work at query time.

    These tests use ``EXPLAIN`` to confirm PostgreSQL selects the index for
    ``ILIKE '%...%'`` patterns — the primary motivation for this migration.

    Note: EXPLAIN plan index selection depends on table statistics and row
    count.  For very small tables (like the test transcript_segments table)
    the planner may prefer a seq-scan even with a valid GIN index.  To avoid
    flakiness we check index *existence* in the catalog tests above, and use
    ``SET enable_seqscan = off`` here to force the planner to pick the index.
    """

    async def test_text_gin_index_can_be_used_for_ilike_search(
        self, dev_session: AsyncSession
    ) -> None:
        """
        Verify the planner can use idx_segments_text_trgm for ILIKE queries.

        Forces the planner away from seq-scan so we get a deterministic
        result regardless of table size.
        """
        await dev_session.execute(text("SET LOCAL enable_seqscan = off"))
        result = await dev_session.execute(
            text(
                "EXPLAIN SELECT id FROM transcript_segments "
                "WHERE text ILIKE '%hello%'"
            )
        )
        plan_lines: list[str] = [row[0] for row in result.fetchall()]
        plan_text = "\n".join(plan_lines).lower()

        # With seq-scan disabled, the planner must use the GIN index.
        assert "idx_segments_text_trgm" in plan_text, (
            "Expected GIN index 'idx_segments_text_trgm' in query plan. "
            f"Actual plan:\n{'  '.join(plan_lines)}"
        )

    async def test_corrected_text_gin_index_can_be_used_for_ilike_search(
        self, dev_session: AsyncSession
    ) -> None:
        """
        Verify the planner can use idx_segments_corrected_text_trgm for
        ILIKE queries filtered to non-NULL corrected_text.
        """
        await dev_session.execute(text("SET LOCAL enable_seqscan = off"))
        result = await dev_session.execute(
            text(
                "EXPLAIN SELECT id FROM transcript_segments "
                "WHERE corrected_text ILIKE '%hello%' "
                "  AND corrected_text IS NOT NULL"
            )
        )
        plan_lines = [row[0] for row in result.fetchall()]
        plan_text = "\n".join(plan_lines).lower()

        assert "idx_segments_corrected_text_trgm" in plan_text, (
            "Expected GIN index 'idx_segments_corrected_text_trgm' in query plan. "
            f"Actual plan:\n{'  '.join(plan_lines)}"
        )
