"""
Integration tests for Entity CLI commands (Feature 037).

Covers `entities create` and `entities list` commands.

These tests mock the database layer, NamedEntityRepository, and
EntityAliasRepository to verify:
- Correct CLI argument parsing and option handling
- Rich output contains expected human-readable strings
- Exit codes for success (0), validation failure (1), and usage error (2)
- Duplicate detection via session.execute scalar_one_or_none
- Alias creation count (canonical alias + additional aliases)

NOTE: The CLI commands use asyncio.run() internally. Tests remain synchronous
and mock db_manager.get_session so no real database connection is needed.
Pattern mirrors tests/integration/cli/test_tag_management_commands.py.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from typer.testing import CliRunner

from chronovista.cli.main import app

runner = CliRunner()

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_OP_ID = uuid.UUID("12345678-1234-5678-1234-567812345678")


def _make_get_session(mock_session: AsyncMock) -> Any:
    """
    Return an async generator factory that yields *mock_session* once,
    matching the signature of db_manager.get_session(echo=False).
    """

    async def _gen(echo: bool = False) -> AsyncGenerator[AsyncSession, None]:
        yield mock_session

    return _gen()


def _make_mock_entity(
    name: str = "Noam Chomsky",
    entity_type: str = "person",
    description: str | None = None,
    entity_id: uuid.UUID | None = None,
) -> MagicMock:
    """Build a MagicMock that looks like a NamedEntity ORM row."""
    entity = MagicMock()
    entity.id = entity_id or uuid.uuid4()
    entity.canonical_name = name
    entity.entity_type = entity_type
    entity.description = description
    entity.created_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
    entity.status = "active"
    return entity


# ---------------------------------------------------------------------------
# Create entity command tests
# ---------------------------------------------------------------------------


class TestCreateEntityCommand:
    """Integration tests for `chronovista entities create`."""

    def test_create_entity_person_exit_code_zero(self) -> None:
        """Creating a person entity successfully returns exit code 0."""
        mock_entity = _make_mock_entity()

        with (
            patch("chronovista.cli.entity_commands.db_manager") as mock_db,
            patch(
                "chronovista.cli.entity_commands.NamedEntityRepository"
            ) as MockEntityRepo,
            patch(
                "chronovista.cli.entity_commands.EntityAliasRepository"
            ) as MockAliasRepo,
        ):
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            # Duplicate check returns None (no existing entity)
            mock_execute_result = MagicMock()
            mock_execute_result.scalar_one_or_none.return_value = None
            mock_session.execute.return_value = mock_execute_result

            mock_entity_repo = AsyncMock()
            mock_entity_repo.create.return_value = mock_entity
            MockEntityRepo.return_value = mock_entity_repo

            mock_alias_repo = AsyncMock()
            mock_alias_repo.create.return_value = MagicMock()
            MockAliasRepo.return_value = mock_alias_repo

            result = runner.invoke(
                app, ["entities", "create", "Noam Chomsky", "--type", "person"]
            )

        assert result.exit_code == 0, f"Output: {result.output}"

    def test_create_entity_output_shows_entity_created(self) -> None:
        """Output contains 'Entity Created', entity name, type, and ID."""
        entity_id = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        mock_entity = _make_mock_entity(entity_id=entity_id)

        with (
            patch("chronovista.cli.entity_commands.db_manager") as mock_db,
            patch(
                "chronovista.cli.entity_commands.NamedEntityRepository"
            ) as MockEntityRepo,
            patch(
                "chronovista.cli.entity_commands.EntityAliasRepository"
            ) as MockAliasRepo,
        ):
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            mock_execute_result = MagicMock()
            mock_execute_result.scalar_one_or_none.return_value = None
            mock_session.execute.return_value = mock_execute_result

            mock_entity_repo = AsyncMock()
            mock_entity_repo.create.return_value = mock_entity
            MockEntityRepo.return_value = mock_entity_repo

            mock_alias_repo = AsyncMock()
            mock_alias_repo.create.return_value = MagicMock()
            MockAliasRepo.return_value = mock_alias_repo

            result = runner.invoke(
                app, ["entities", "create", "Noam Chomsky", "--type", "person"]
            )

        assert result.exit_code == 0, f"Output: {result.output}"
        assert "Entity Created" in result.output
        assert "Noam Chomsky" in result.output
        assert "person" in result.output
        assert str(entity_id) in result.output

    def test_create_entity_with_description(self) -> None:
        """--description is accepted and command still exits 0."""
        mock_entity = _make_mock_entity(description="American linguist")

        with (
            patch("chronovista.cli.entity_commands.db_manager") as mock_db,
            patch(
                "chronovista.cli.entity_commands.NamedEntityRepository"
            ) as MockEntityRepo,
            patch(
                "chronovista.cli.entity_commands.EntityAliasRepository"
            ) as MockAliasRepo,
        ):
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            mock_execute_result = MagicMock()
            mock_execute_result.scalar_one_or_none.return_value = None
            mock_session.execute.return_value = mock_execute_result

            mock_entity_repo = AsyncMock()
            mock_entity_repo.create.return_value = mock_entity
            MockEntityRepo.return_value = mock_entity_repo

            mock_alias_repo = AsyncMock()
            mock_alias_repo.create.return_value = MagicMock()
            MockAliasRepo.return_value = mock_alias_repo

            result = runner.invoke(
                app,
                [
                    "entities",
                    "create",
                    "Noam Chomsky",
                    "--type",
                    "person",
                    "--description",
                    "American linguist",
                ],
            )

        assert result.exit_code == 0, f"Output: {result.output}"
        # Verify the description was passed to the repo create call
        create_call_kwargs = mock_entity_repo.create.call_args[1]
        obj_in = create_call_kwargs["obj_in"]
        assert obj_in.description == "American linguist"

    def test_create_entity_with_aliases_calls_alias_repo_three_times(self) -> None:
        """--alias creates the canonical alias plus each additional alias (3 total)."""
        mock_entity = _make_mock_entity()

        with (
            patch("chronovista.cli.entity_commands.db_manager") as mock_db,
            patch(
                "chronovista.cli.entity_commands.NamedEntityRepository"
            ) as MockEntityRepo,
            patch(
                "chronovista.cli.entity_commands.EntityAliasRepository"
            ) as MockAliasRepo,
        ):
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            mock_execute_result = MagicMock()
            mock_execute_result.scalar_one_or_none.return_value = None
            mock_session.execute.return_value = mock_execute_result

            mock_entity_repo = AsyncMock()
            mock_entity_repo.create.return_value = mock_entity
            MockEntityRepo.return_value = mock_entity_repo

            mock_alias_repo = AsyncMock()
            mock_alias_repo.create.return_value = MagicMock()
            MockAliasRepo.return_value = mock_alias_repo

            result = runner.invoke(
                app,
                [
                    "entities",
                    "create",
                    "Noam Chomsky",
                    "--type",
                    "person",
                    "--alias",
                    "N. Chomsky",
                    "--alias",
                    "Avram Noam Chomsky",
                ],
            )

        assert result.exit_code == 0, f"Output: {result.output}"
        # 1 canonical alias + 2 additional aliases = 3 alias repo create calls
        assert mock_alias_repo.create.call_count == 3

    def test_create_entity_duplicate_exits_code_1(self) -> None:
        """When a duplicate entity exists (same normalized name + type), exit code is 1."""
        existing_entity = _make_mock_entity()

        with (
            patch("chronovista.cli.entity_commands.db_manager") as mock_db,
            patch("chronovista.cli.entity_commands.NamedEntityRepository"),
            patch("chronovista.cli.entity_commands.EntityAliasRepository"),
        ):
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            # Duplicate check returns an existing entity
            mock_execute_result = MagicMock()
            mock_execute_result.scalar_one_or_none.return_value = existing_entity
            mock_session.execute.return_value = mock_execute_result

            result = runner.invoke(
                app, ["entities", "create", "Noam Chomsky", "--type", "person"]
            )

        assert result.exit_code == 1, f"Output: {result.output}"
        assert "Duplicate Entity" in result.output

    def test_create_entity_invalid_type_topic_exits_code_1(self) -> None:
        """--type topic is rejected as not valid for entity creation (exit code 1)."""
        result = runner.invoke(
            app, ["entities", "create", "Machine Learning", "--type", "topic"]
        )

        assert result.exit_code == 1, f"Output: {result.output}"
        assert "Invalid Type" in result.output

    def test_create_entity_invalid_type_descriptor_exits_code_1(self) -> None:
        """--type descriptor is rejected as not valid for entity creation (exit code 1)."""
        result = runner.invoke(
            app, ["entities", "create", "Interesting", "--type", "descriptor"]
        )

        assert result.exit_code == 1, f"Output: {result.output}"
        assert "Invalid Type" in result.output

    def test_create_entity_auto_title_cases_name(self) -> None:
        """Lowercase input name is title-cased when passed to NamedEntityCreate."""
        mock_entity = _make_mock_entity(name="Noam Chomsky")

        with (
            patch("chronovista.cli.entity_commands.db_manager") as mock_db,
            patch(
                "chronovista.cli.entity_commands.NamedEntityRepository"
            ) as MockEntityRepo,
            patch(
                "chronovista.cli.entity_commands.EntityAliasRepository"
            ) as MockAliasRepo,
        ):
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            mock_execute_result = MagicMock()
            mock_execute_result.scalar_one_or_none.return_value = None
            mock_session.execute.return_value = mock_execute_result

            mock_entity_repo = AsyncMock()
            mock_entity_repo.create.return_value = mock_entity
            MockEntityRepo.return_value = mock_entity_repo

            mock_alias_repo = AsyncMock()
            mock_alias_repo.create.return_value = MagicMock()
            MockAliasRepo.return_value = mock_alias_repo

            result = runner.invoke(
                app,
                ["entities", "create", "noam chomsky", "--type", "person"],
            )

        assert result.exit_code == 0, f"Output: {result.output}"
        create_call_kwargs = mock_entity_repo.create.call_args[1]
        obj_in = create_call_kwargs["obj_in"]
        # "noam chomsky".title() == "Noam Chomsky"
        assert obj_in.canonical_name == "Noam Chomsky"

    def test_create_entity_empty_normalized_name_exits_code_1(self) -> None:
        """Name that normalizes to empty (e.g. '###') exits with code 1."""
        result = runner.invoke(
            app, ["entities", "create", "###", "--type", "person"]
        )

        assert result.exit_code == 1, f"Output: {result.output}"
        assert "Invalid Name" in result.output

    def test_create_entity_missing_type_flag_exits_nonzero(self) -> None:
        """Missing required --type option exits with a non-zero code."""
        result = runner.invoke(app, ["entities", "create", "Noam Chomsky"])

        assert result.exit_code != 0

    def test_create_entity_organization_type_accepted(self) -> None:
        """--type organization is a valid entity-producing type and exits 0."""
        mock_entity = _make_mock_entity(name="MIT", entity_type="organization")

        with (
            patch("chronovista.cli.entity_commands.db_manager") as mock_db,
            patch(
                "chronovista.cli.entity_commands.NamedEntityRepository"
            ) as MockEntityRepo,
            patch(
                "chronovista.cli.entity_commands.EntityAliasRepository"
            ) as MockAliasRepo,
        ):
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            mock_execute_result = MagicMock()
            mock_execute_result.scalar_one_or_none.return_value = None
            mock_session.execute.return_value = mock_execute_result

            mock_entity_repo = AsyncMock()
            mock_entity_repo.create.return_value = mock_entity
            MockEntityRepo.return_value = mock_entity_repo

            mock_alias_repo = AsyncMock()
            mock_alias_repo.create.return_value = MagicMock()
            MockAliasRepo.return_value = mock_alias_repo

            result = runner.invoke(
                app, ["entities", "create", "MIT", "--type", "organization"]
            )

        assert result.exit_code == 0, f"Output: {result.output}"

    def test_create_entity_output_shows_description_when_set(self) -> None:
        """Output shows the entity description when it is not None."""
        mock_entity = _make_mock_entity(description="American linguist and philosopher")

        with (
            patch("chronovista.cli.entity_commands.db_manager") as mock_db,
            patch(
                "chronovista.cli.entity_commands.NamedEntityRepository"
            ) as MockEntityRepo,
            patch(
                "chronovista.cli.entity_commands.EntityAliasRepository"
            ) as MockAliasRepo,
        ):
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            mock_execute_result = MagicMock()
            mock_execute_result.scalar_one_or_none.return_value = None
            mock_session.execute.return_value = mock_execute_result

            mock_entity_repo = AsyncMock()
            mock_entity_repo.create.return_value = mock_entity
            MockEntityRepo.return_value = mock_entity_repo

            mock_alias_repo = AsyncMock()
            mock_alias_repo.create.return_value = MagicMock()
            MockAliasRepo.return_value = mock_alias_repo

            result = runner.invoke(
                app,
                [
                    "entities",
                    "create",
                    "Noam Chomsky",
                    "--type",
                    "person",
                    "--description",
                    "American linguist and philosopher",
                ],
            )

        assert result.exit_code == 0, f"Output: {result.output}"
        assert "American linguist and philosopher" in result.output

    def test_create_entity_output_shows_none_for_missing_description(self) -> None:
        """Output shows '(none)' when entity has no description."""
        mock_entity = _make_mock_entity(description=None)

        with (
            patch("chronovista.cli.entity_commands.db_manager") as mock_db,
            patch(
                "chronovista.cli.entity_commands.NamedEntityRepository"
            ) as MockEntityRepo,
            patch(
                "chronovista.cli.entity_commands.EntityAliasRepository"
            ) as MockAliasRepo,
        ):
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            mock_execute_result = MagicMock()
            mock_execute_result.scalar_one_or_none.return_value = None
            mock_session.execute.return_value = mock_execute_result

            mock_entity_repo = AsyncMock()
            mock_entity_repo.create.return_value = mock_entity
            MockEntityRepo.return_value = mock_entity_repo

            mock_alias_repo = AsyncMock()
            mock_alias_repo.create.return_value = MagicMock()
            MockAliasRepo.return_value = mock_alias_repo

            result = runner.invoke(
                app, ["entities", "create", "Noam Chomsky", "--type", "person"]
            )

        assert result.exit_code == 0, f"Output: {result.output}"
        assert "(none)" in result.output

    def test_create_entity_help_flag(self) -> None:
        """--help shows usage text and exits 0."""
        result = runner.invoke(app, ["entities", "create", "--help"])

        assert result.exit_code == 0
        assert "--type" in result.output
        assert "--description" in result.output
        assert "--alias" in result.output


# ---------------------------------------------------------------------------
# List entities command tests
# ---------------------------------------------------------------------------


class TestListEntitiesCommand:
    """Integration tests for `chronovista entities list`."""

    def test_list_entities_exit_code_zero(self) -> None:
        """Listing entities when some exist returns exit code 0."""
        mock_entity = _make_mock_entity()

        with patch("chronovista.cli.entity_commands.db_manager") as mock_db:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            # Call 1: main query returns entities
            entities_result = MagicMock()
            entities_result.scalars.return_value.all.return_value = [mock_entity]

            # Call 2: count query
            count_result = MagicMock()
            count_result.scalar.return_value = 1

            # Call 3: alias count per entity
            alias_count_result = MagicMock()
            alias_count_result.scalar.return_value = 2

            mock_session.execute.side_effect = [
                entities_result,
                count_result,
                alias_count_result,
            ]

            result = runner.invoke(app, ["entities", "list"])

        assert result.exit_code == 0, f"Output: {result.output}"

    def test_list_entities_shows_table_with_entity_names(self) -> None:
        """Listing 2 entities shows a 'Named Entities' table with their names."""
        entity1 = _make_mock_entity(name="Noam Chomsky")
        entity2 = _make_mock_entity(name="Edward Said", entity_type="person")

        with patch("chronovista.cli.entity_commands.db_manager") as mock_db:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            entities_result = MagicMock()
            entities_result.scalars.return_value.all.return_value = [entity1, entity2]

            count_result = MagicMock()
            count_result.scalar.return_value = 2

            # Two alias count queries (one per entity)
            alias_count_1 = MagicMock()
            alias_count_1.scalar.return_value = 2
            alias_count_2 = MagicMock()
            alias_count_2.scalar.return_value = 1

            mock_session.execute.side_effect = [
                entities_result,
                count_result,
                alias_count_1,
                alias_count_2,
            ]

            result = runner.invoke(app, ["entities", "list"])

        assert result.exit_code == 0, f"Output: {result.output}"
        assert "Named Entities" in result.output
        assert "Noam Chomsky" in result.output
        assert "Edward Said" in result.output

    def test_list_entities_empty_shows_no_entities_panel(self) -> None:
        """When no entities match the criteria, 'No Entities' panel is shown."""
        with patch("chronovista.cli.entity_commands.db_manager") as mock_db:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            entities_result = MagicMock()
            entities_result.scalars.return_value.all.return_value = []

            count_result = MagicMock()
            count_result.scalar.return_value = 0

            mock_session.execute.side_effect = [entities_result, count_result]

            result = runner.invoke(app, ["entities", "list"])

        assert result.exit_code == 0, f"Output: {result.output}"
        assert "No Entities" in result.output

    def test_list_entities_with_type_filter_exits_code_zero(self) -> None:
        """--type person filter is accepted and returns exit code 0."""
        mock_entity = _make_mock_entity()

        with patch("chronovista.cli.entity_commands.db_manager") as mock_db:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            entities_result = MagicMock()
            entities_result.scalars.return_value.all.return_value = [mock_entity]

            count_result = MagicMock()
            count_result.scalar.return_value = 1

            alias_count_result = MagicMock()
            alias_count_result.scalar.return_value = 1

            mock_session.execute.side_effect = [
                entities_result,
                count_result,
                alias_count_result,
            ]

            result = runner.invoke(app, ["entities", "list", "--type", "person"])

        assert result.exit_code == 0, f"Output: {result.output}"

    def test_list_entities_with_search_exits_code_zero(self) -> None:
        """--search chomsky filter is accepted and returns exit code 0."""
        mock_entity = _make_mock_entity()

        with patch("chronovista.cli.entity_commands.db_manager") as mock_db:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            entities_result = MagicMock()
            entities_result.scalars.return_value.all.return_value = [mock_entity]

            count_result = MagicMock()
            count_result.scalar.return_value = 1

            alias_count_result = MagicMock()
            alias_count_result.scalar.return_value = 1

            mock_session.execute.side_effect = [
                entities_result,
                count_result,
                alias_count_result,
            ]

            result = runner.invoke(app, ["entities", "list", "--search", "chomsky"])

        assert result.exit_code == 0, f"Output: {result.output}"

    def test_list_entities_invalid_type_exits_code_1(self) -> None:
        """--type with an invalid enum value exits with code 1."""
        result = runner.invoke(app, ["entities", "list", "--type", "invalid_type"])

        assert result.exit_code == 1, f"Output: {result.output}"
        assert "Invalid --type" in result.output

    def test_list_entities_shows_count_footer(self) -> None:
        """Output contains 'Showing N of M total entities' footer."""
        mock_entity = _make_mock_entity()

        with patch("chronovista.cli.entity_commands.db_manager") as mock_db:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            entities_result = MagicMock()
            entities_result.scalars.return_value.all.return_value = [mock_entity]

            count_result = MagicMock()
            count_result.scalar.return_value = 42

            alias_count_result = MagicMock()
            alias_count_result.scalar.return_value = 3

            mock_session.execute.side_effect = [
                entities_result,
                count_result,
                alias_count_result,
            ]

            result = runner.invoke(app, ["entities", "list"])

        assert result.exit_code == 0, f"Output: {result.output}"
        # Footer: "Showing 1 of 42 total entities"
        assert "Showing" in result.output
        assert "total entities" in result.output
        assert "42" in result.output

    def test_list_entities_alias_count_query_is_executed_per_entity(self) -> None:
        """The command issues an alias count query for each entity row returned.

        Note: Rich truncates the Aliases column header and cell to '…' in the
        narrow terminal width that CliRunner provides, so we verify the behaviour
        by asserting that session.execute was called three times total:
        main query + count query + one alias-count query per entity.
        """
        mock_entity = _make_mock_entity()

        with patch("chronovista.cli.entity_commands.db_manager") as mock_db:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            entities_result = MagicMock()
            entities_result.scalars.return_value.all.return_value = [mock_entity]

            count_result = MagicMock()
            count_result.scalar.return_value = 1

            alias_count_result = MagicMock()
            alias_count_result.scalar.return_value = 5

            mock_session.execute.side_effect = [
                entities_result,
                count_result,
                alias_count_result,
            ]

            result = runner.invoke(app, ["entities", "list"])

        assert result.exit_code == 0, f"Output: {result.output}"
        assert "Named Entities" in result.output
        # 3 execute calls: main query + count query + 1 alias-count per entity
        assert mock_session.execute.call_count == 3

    def test_list_entities_with_limit_option(self) -> None:
        """--limit option is accepted and returns exit code 0."""
        mock_entity = _make_mock_entity()

        with patch("chronovista.cli.entity_commands.db_manager") as mock_db:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            entities_result = MagicMock()
            entities_result.scalars.return_value.all.return_value = [mock_entity]

            count_result = MagicMock()
            count_result.scalar.return_value = 1

            alias_count_result = MagicMock()
            alias_count_result.scalar.return_value = 1

            mock_session.execute.side_effect = [
                entities_result,
                count_result,
                alias_count_result,
            ]

            result = runner.invoke(app, ["entities", "list", "--limit", "10"])

        assert result.exit_code == 0, f"Output: {result.output}"

    def test_list_entities_help_flag(self) -> None:
        """--help shows usage text and exits 0."""
        result = runner.invoke(app, ["entities", "list", "--help"])

        assert result.exit_code == 0
        assert "--type" in result.output
        assert "--search" in result.output
        assert "--limit" in result.output


# ---------------------------------------------------------------------------
# Backfill descriptions command tests
# ---------------------------------------------------------------------------


class TestBackfillDescriptionsCommand:
    """Integration tests for `chronovista entities backfill-descriptions`.

    The backfill command makes multiple session.execute() calls:
    - First call: main query returning TagOperationLog rows (uses .all())
    - Subsequent calls: one per row to look up the NamedEntity (uses .scalar_one_or_none())

    We therefore use side_effect on mock_session.execute to drive each call
    independently, exactly as the command issues them.
    """

    def test_backfill_dry_run_shows_preview(self) -> None:
        """--dry-run with matching entities shows a preview table and 'would be updated'."""
        # Build two mock log rows
        mock_row_1 = MagicMock()
        mock_row_1.entity_id_str = "12345678-1234-5678-1234-567812345678"
        mock_row_1.reason = "British journalist"

        mock_row_2 = MagicMock()
        mock_row_2.entity_id_str = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        mock_row_2.reason = "American linguist"

        # Main query result: .all() returns both rows
        main_result = MagicMock()
        main_result.all.return_value = [mock_row_1, mock_row_2]

        # Entity lookup results for each row
        mock_entity_1 = MagicMock()
        mock_entity_1.id = uuid.UUID("12345678-1234-5678-1234-567812345678")
        mock_entity_1.canonical_name = "Vanessa Beeley"
        mock_entity_1.description = None

        entity_result_1 = MagicMock()
        entity_result_1.scalar_one_or_none.return_value = mock_entity_1

        mock_entity_2 = MagicMock()
        mock_entity_2.id = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        mock_entity_2.canonical_name = "Noam Chomsky"
        mock_entity_2.description = None

        entity_result_2 = MagicMock()
        entity_result_2.scalar_one_or_none.return_value = mock_entity_2

        with patch("chronovista.cli.entity_commands.db_manager") as mock_db:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            # First execute = main query, second and third = per-row entity lookups
            mock_session.execute.side_effect = [
                main_result,
                entity_result_1,
                entity_result_2,
            ]

            result = runner.invoke(
                app, ["entities", "backfill-descriptions", "--dry-run"]
            )

        assert result.exit_code == 0, f"Output: {result.output}"
        assert "Backfill Preview" in result.output
        assert "would be updated" in result.output

    def test_backfill_applies_descriptions(self) -> None:
        """Without --dry-run, entities are updated and commit is called."""
        mock_row_1 = MagicMock()
        mock_row_1.entity_id_str = "12345678-1234-5678-1234-567812345678"
        mock_row_1.reason = "British journalist"

        mock_row_2 = MagicMock()
        mock_row_2.entity_id_str = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        mock_row_2.reason = "American linguist"

        main_result = MagicMock()
        main_result.all.return_value = [mock_row_1, mock_row_2]

        mock_entity_1 = MagicMock()
        mock_entity_1.id = uuid.UUID("12345678-1234-5678-1234-567812345678")
        mock_entity_1.canonical_name = "Vanessa Beeley"
        mock_entity_1.description = None

        entity_result_1 = MagicMock()
        entity_result_1.scalar_one_or_none.return_value = mock_entity_1

        mock_entity_2 = MagicMock()
        mock_entity_2.id = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        mock_entity_2.canonical_name = "Noam Chomsky"
        mock_entity_2.description = None

        entity_result_2 = MagicMock()
        entity_result_2.scalar_one_or_none.return_value = mock_entity_2

        with patch("chronovista.cli.entity_commands.db_manager") as mock_db:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            mock_session.execute.side_effect = [
                main_result,
                entity_result_1,
                entity_result_2,
            ]

            result = runner.invoke(app, ["entities", "backfill-descriptions"])

        assert result.exit_code == 0, f"Output: {result.output}"
        assert "Backfill Complete" in result.output
        assert "Updated" in result.output
        mock_session.commit.assert_called_once()

    def test_backfill_no_operations_found(self) -> None:
        """When the main query returns no rows, 'Nothing to Backfill' panel is shown."""
        main_result = MagicMock()
        main_result.all.return_value = []

        with patch("chronovista.cli.entity_commands.db_manager") as mock_db:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            mock_session.execute.return_value = main_result

            result = runner.invoke(app, ["entities", "backfill-descriptions"])

        assert result.exit_code == 0, f"Output: {result.output}"
        assert "Nothing to Backfill" in result.output

    def test_backfill_skips_entities_with_existing_description(self) -> None:
        """When entity lookup returns None (entity not found or already has description), row is skipped."""
        mock_row_1 = MagicMock()
        mock_row_1.entity_id_str = "12345678-1234-5678-1234-567812345678"
        mock_row_1.reason = "British journalist"

        main_result = MagicMock()
        main_result.all.return_value = [mock_row_1]

        # Entity lookup returns None → entity has description or does not exist
        entity_result = MagicMock()
        entity_result.scalar_one_or_none.return_value = None

        with patch("chronovista.cli.entity_commands.db_manager") as mock_db:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            mock_session.execute.side_effect = [main_result, entity_result]

            result = runner.invoke(app, ["entities", "backfill-descriptions"])

        assert result.exit_code == 0, f"Output: {result.output}"
        # The non-dry-run panel prints "Skipped: 1 (...)" with a capital S
        assert "Skipped:" in result.output

    def test_backfill_help_flag(self) -> None:
        """--help shows usage text including --dry-run and exits 0."""
        result = runner.invoke(
            app, ["entities", "backfill-descriptions", "--help"]
        )

        assert result.exit_code == 0
        assert "--dry-run" in result.output
