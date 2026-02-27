"""
Integration tests for Tag Management CLI commands (Feature 031).

Covers `tags merge`, `tags split`, `tags undo`, `tags rename`, `tags classify`,
`tags collisions`, and `tags deprecate` commands.

These tests mock the database layer and the TagManagementService to verify:
- Correct CLI argument parsing and option handling
- Rich output contains expected human-readable strings
- Exit codes for success (0), validation failure (1), and usage error (2)
- --reason flag propagation to the service
- Interactive undo list output formatting

NOTE: The CLI commands use asyncio.run() internally. Tests remain synchronous
and mock db_manager.get_session so no real database connection is needed.
Pattern mirrors tests/integration/cli/test_tag_normalize_commands.py.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from chronovista.services.tag_management import CollisionGroup
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


# ---------------------------------------------------------------------------
# Merge command tests
# ---------------------------------------------------------------------------


class TestMergeCommand:
    """Integration tests for `chronovista tags merge`."""

    def test_successful_single_source_merge_exit_code_zero(self) -> None:
        """Successful single-source merge returns exit code 0."""
        from chronovista.services.tag_management import MergeResult

        mock_result = MergeResult(
            source_tags=["mejico"],
            target_tag="mexico",
            aliases_moved=3,
            new_alias_count=7,
            new_video_count=42,
            operation_id=_OP_ID,
        )

        with patch("chronovista.cli.tag_commands.db_manager") as mock_db, patch(
            "chronovista.cli.tag_commands._create_tag_management_service"
        ) as mock_factory:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            mock_service = AsyncMock()
            mock_service.merge.return_value = mock_result
            mock_factory.return_value = mock_service

            result = runner.invoke(app, ["tags", "merge", "mejico", "--into", "mexico"])

        assert result.exit_code == 0, f"Output: {result.output}"

    def test_successful_merge_output_contains_key_fields(self) -> None:
        """Successful merge output contains source, target, aliases_moved, and operation_id."""
        from chronovista.services.tag_management import MergeResult

        mock_result = MergeResult(
            source_tags=["mejico"],
            target_tag="mexico",
            aliases_moved=3,
            new_alias_count=7,
            new_video_count=42,
            operation_id=_OP_ID,
        )

        with patch("chronovista.cli.tag_commands.db_manager") as mock_db, patch(
            "chronovista.cli.tag_commands._create_tag_management_service"
        ) as mock_factory:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            mock_service = AsyncMock()
            mock_service.merge.return_value = mock_result
            mock_factory.return_value = mock_service

            result = runner.invoke(app, ["tags", "merge", "mejico", "--into", "mexico"])

        assert "Merge Successful" in result.output
        assert "mejico" in result.output
        assert "mexico" in result.output
        assert "3" in result.output  # aliases_moved
        assert str(_OP_ID) in result.output

    def test_successful_merge_with_entity_hint_shows_hint(self) -> None:
        """When merge returns an entity_hint, it is printed in yellow."""
        from chronovista.services.tag_management import MergeResult

        hint = "Source tag(s) had entity type(s): person. Consider classifying target 'mexico'."
        mock_result = MergeResult(
            source_tags=["mejico"],
            target_tag="mexico",
            aliases_moved=1,
            new_alias_count=4,
            new_video_count=10,
            operation_id=_OP_ID,
            entity_hint=hint,
        )

        with patch("chronovista.cli.tag_commands.db_manager") as mock_db, patch(
            "chronovista.cli.tag_commands._create_tag_management_service"
        ) as mock_factory:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            mock_service = AsyncMock()
            mock_service.merge.return_value = mock_result
            mock_factory.return_value = mock_service

            result = runner.invoke(app, ["tags", "merge", "mejico", "--into", "mexico"])

        assert result.exit_code == 0
        # The hint text itself should appear
        assert "Consider classifying" in result.output

    def test_merge_with_reason_flag_propagates_reason(self) -> None:
        """--reason flag is forwarded to service.merge()."""
        from chronovista.services.tag_management import MergeResult

        mock_result = MergeResult(
            source_tags=["mejico"],
            target_tag="mexico",
            aliases_moved=2,
            new_alias_count=5,
            new_video_count=20,
            operation_id=_OP_ID,
        )

        with patch("chronovista.cli.tag_commands.db_manager") as mock_db, patch(
            "chronovista.cli.tag_commands._create_tag_management_service"
        ) as mock_factory:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            mock_service = AsyncMock()
            mock_service.merge.return_value = mock_result
            mock_factory.return_value = mock_service

            result = runner.invoke(
                app,
                ["tags", "merge", "mejico", "--into", "mexico", "--reason", "Test reason"],
            )

        assert result.exit_code == 0
        mock_service.merge.assert_called_once()
        call_kwargs = mock_service.merge.call_args[1]
        assert call_kwargs.get("reason") == "Test reason"

    def test_multi_source_merge_passes_all_sources(self) -> None:
        """Multiple source arguments are all forwarded to service.merge()."""
        from chronovista.services.tag_management import MergeResult

        mock_result = MergeResult(
            source_tags=["mejico", "mexiko"],
            target_tag="mexico",
            aliases_moved=5,
            new_alias_count=9,
            new_video_count=80,
            operation_id=_OP_ID,
        )

        with patch("chronovista.cli.tag_commands.db_manager") as mock_db, patch(
            "chronovista.cli.tag_commands._create_tag_management_service"
        ) as mock_factory:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            mock_service = AsyncMock()
            mock_service.merge.return_value = mock_result
            mock_factory.return_value = mock_service

            result = runner.invoke(
                app, ["tags", "merge", "mejico", "mexiko", "--into", "mexico"]
            )

        assert result.exit_code == 0
        call_kwargs = mock_service.merge.call_args
        sources = call_kwargs[1]["source_normalized_forms"]
        assert "mejico" in sources
        assert "mexiko" in sources

    def test_merge_value_error_exits_code_1(self) -> None:
        """ValueError from service (e.g., tag not found) produces exit code 1."""
        with patch("chronovista.cli.tag_commands.db_manager") as mock_db, patch(
            "chronovista.cli.tag_commands._create_tag_management_service"
        ) as mock_factory:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            mock_service = AsyncMock()
            mock_service.merge.side_effect = ValueError("Tag 'nonexistent' not found")
            mock_factory.return_value = mock_service

            result = runner.invoke(app, ["tags", "merge", "nonexistent", "--into", "mexico"])

        assert result.exit_code == 1

    def test_merge_value_error_shows_error_panel(self) -> None:
        """ValueError message is printed in the output."""
        with patch("chronovista.cli.tag_commands.db_manager") as mock_db, patch(
            "chronovista.cli.tag_commands._create_tag_management_service"
        ) as mock_factory:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            mock_service = AsyncMock()
            mock_service.merge.side_effect = ValueError("Tag 'nonexistent' not found")
            mock_factory.return_value = mock_service

            result = runner.invoke(app, ["tags", "merge", "nonexistent", "--into", "mexico"])

        assert "Merge Failed" in result.output
        assert "nonexistent" in result.output

    def test_merge_self_merge_exits_code_1(self) -> None:
        """Self-merge (source == target) produces exit code 1."""
        with patch("chronovista.cli.tag_commands.db_manager") as mock_db, patch(
            "chronovista.cli.tag_commands._create_tag_management_service"
        ) as mock_factory:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            mock_service = AsyncMock()
            mock_service.merge.side_effect = ValueError(
                "Cannot merge tag 'mexico' into itself"
            )
            mock_factory.return_value = mock_service

            result = runner.invoke(app, ["tags", "merge", "mexico", "--into", "mexico"])

        assert result.exit_code == 1

    def test_merge_reason_too_long_exits_code_2(self) -> None:
        """--reason exceeding 1000 chars triggers Typer bad parameter (exit 2)."""
        long_reason = "x" * 1001

        result = runner.invoke(
            app, ["tags", "merge", "a", "--into", "b", "--reason", long_reason]
        )

        assert result.exit_code == 2

    def test_merge_missing_into_flag_exits_nonzero(self) -> None:
        """Missing required --into option exits with a non-zero code."""
        result = runner.invoke(app, ["tags", "merge", "mejico"])

        assert result.exit_code != 0

    def test_merge_help_flag(self) -> None:
        """--help shows usage text and exits 0."""
        result = runner.invoke(app, ["tags", "merge", "--help"])

        assert result.exit_code == 0
        assert "--into" in result.output
        assert "--reason" in result.output


# ---------------------------------------------------------------------------
# Split command tests
# ---------------------------------------------------------------------------


class TestSplitCommand:
    """Integration tests for `chronovista tags split`."""

    def test_successful_split_exit_code_zero(self) -> None:
        """Successful split returns exit code 0."""
        from chronovista.services.tag_management import SplitResult

        mock_result = SplitResult(
            original_tag="python",
            new_tag="python3",
            new_canonical_form="Python3",
            new_normalized_form="python3",
            aliases_moved=2,
            original_alias_count=5,
            original_video_count=100,
            new_alias_count=2,
            new_video_count=30,
            operation_id=_OP_ID,
        )

        with patch("chronovista.cli.tag_commands.db_manager") as mock_db, patch(
            "chronovista.cli.tag_commands._create_tag_management_service"
        ) as mock_factory:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            mock_service = AsyncMock()
            mock_service.split.return_value = mock_result
            mock_factory.return_value = mock_service

            result = runner.invoke(
                app, ["tags", "split", "python", "--aliases", "Python3,python 3"]
            )

        assert result.exit_code == 0, f"Output: {result.output}"

    def test_successful_split_output_contains_key_fields(self) -> None:
        """Successful split output shows original tag, new tag, and operation ID."""
        from chronovista.services.tag_management import SplitResult

        mock_result = SplitResult(
            original_tag="python",
            new_tag="python3",
            new_canonical_form="Python3",
            new_normalized_form="python3",
            aliases_moved=2,
            original_alias_count=5,
            original_video_count=100,
            new_alias_count=2,
            new_video_count=30,
            operation_id=_OP_ID,
        )

        with patch("chronovista.cli.tag_commands.db_manager") as mock_db, patch(
            "chronovista.cli.tag_commands._create_tag_management_service"
        ) as mock_factory:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            mock_service = AsyncMock()
            mock_service.split.return_value = mock_result
            mock_factory.return_value = mock_service

            result = runner.invoke(
                app, ["tags", "split", "python", "--aliases", "Python3,python 3"]
            )

        assert "Split Successful" in result.output
        assert "python" in result.output
        assert "python3" in result.output
        assert str(_OP_ID) in result.output

    def test_split_with_reason_propagates_reason(self) -> None:
        """--reason flag is forwarded to service.split()."""
        from chronovista.services.tag_management import SplitResult

        mock_result = SplitResult(
            original_tag="python",
            new_tag="python3",
            new_canonical_form="Python3",
            new_normalized_form="python3",
            aliases_moved=1,
            original_alias_count=4,
            original_video_count=80,
            new_alias_count=1,
            new_video_count=20,
            operation_id=_OP_ID,
        )

        with patch("chronovista.cli.tag_commands.db_manager") as mock_db, patch(
            "chronovista.cli.tag_commands._create_tag_management_service"
        ) as mock_factory:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            mock_service = AsyncMock()
            mock_service.split.return_value = mock_result
            mock_factory.return_value = mock_service

            result = runner.invoke(
                app,
                [
                    "tags",
                    "split",
                    "python",
                    "--aliases",
                    "Python3",
                    "--reason",
                    "Version disambiguation",
                ],
            )

        assert result.exit_code == 0
        call_kwargs = mock_service.split.call_args[1]
        assert call_kwargs.get("reason") == "Version disambiguation"

    def test_split_aliases_parsed_as_csv(self) -> None:
        """Comma-separated --aliases are correctly split before passing to service."""
        from chronovista.services.tag_management import SplitResult

        mock_result = SplitResult(
            original_tag="python",
            new_tag="python3",
            new_canonical_form="Python3",
            new_normalized_form="python3",
            aliases_moved=3,
            original_alias_count=6,
            original_video_count=100,
            new_alias_count=3,
            new_video_count=40,
            operation_id=_OP_ID,
        )

        with patch("chronovista.cli.tag_commands.db_manager") as mock_db, patch(
            "chronovista.cli.tag_commands._create_tag_management_service"
        ) as mock_factory:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            mock_service = AsyncMock()
            mock_service.split.return_value = mock_result
            mock_factory.return_value = mock_service

            result = runner.invoke(
                app,
                [
                    "tags",
                    "split",
                    "python",
                    "--aliases",
                    "Python3, python 3, py3",
                ],
            )

        assert result.exit_code == 0
        # Verify the alias list reached the service with whitespace stripped
        call_kwargs = mock_service.split.call_args[1]
        alias_list = call_kwargs.get("alias_raw_forms")
        assert "Python3" in alias_list
        assert "python 3" in alias_list
        assert "py3" in alias_list

    def test_split_value_error_exits_code_1(self) -> None:
        """ValueError from service produces exit code 1."""
        with patch("chronovista.cli.tag_commands.db_manager") as mock_db, patch(
            "chronovista.cli.tag_commands._create_tag_management_service"
        ) as mock_factory:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            mock_service = AsyncMock()
            mock_service.split.side_effect = ValueError(
                "Alias(es) not found on tag 'python': nonexistent_alias"
            )
            mock_factory.return_value = mock_service

            result = runner.invoke(
                app, ["tags", "split", "python", "--aliases", "nonexistent_alias"]
            )

        assert result.exit_code == 1

    def test_split_value_error_shows_split_failed_panel(self) -> None:
        """ValueError message is displayed in Split Failed panel."""
        with patch("chronovista.cli.tag_commands.db_manager") as mock_db, patch(
            "chronovista.cli.tag_commands._create_tag_management_service"
        ) as mock_factory:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            mock_service = AsyncMock()
            mock_service.split.side_effect = ValueError(
                "Cannot split all aliases from 'python'"
            )
            mock_factory.return_value = mock_service

            result = runner.invoke(
                app, ["tags", "split", "python", "--aliases", "python"]
            )

        assert "Split Failed" in result.output

    def test_split_missing_aliases_flag_exits_nonzero(self) -> None:
        """Missing required --aliases option exits with non-zero code."""
        result = runner.invoke(app, ["tags", "split", "python"])

        assert result.exit_code != 0

    def test_split_reason_too_long_exits_code_2(self) -> None:
        """--reason exceeding 1000 chars triggers Typer bad parameter (exit 2)."""
        long_reason = "y" * 1001

        result = runner.invoke(
            app,
            ["tags", "split", "python", "--aliases", "Python3", "--reason", long_reason],
        )

        assert result.exit_code == 2

    def test_split_help_flag(self) -> None:
        """--help shows usage text and exits 0."""
        result = runner.invoke(app, ["tags", "split", "--help"])

        assert result.exit_code == 0
        assert "--aliases" in result.output
        assert "--reason" in result.output


# ---------------------------------------------------------------------------
# Rename command tests
# ---------------------------------------------------------------------------


class TestRenameCommand:
    """Integration tests for `chronovista tags rename`."""

    def test_successful_rename_exit_code_zero(self) -> None:
        """Successful rename returns exit code 0."""
        from chronovista.services.tag_management import RenameResult

        mock_result = RenameResult(
            normalized_form="mexico",
            old_form="Mexico",
            new_form="Mexico City",
            operation_id=_OP_ID,
        )

        with patch("chronovista.cli.tag_commands.db_manager") as mock_db, patch(
            "chronovista.cli.tag_commands._create_tag_management_service"
        ) as mock_factory:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            mock_service = AsyncMock()
            mock_service.rename.return_value = mock_result
            mock_factory.return_value = mock_service

            result = runner.invoke(
                app, ["tags", "rename", "mexico", "--to", "Mexico City"]
            )

        assert result.exit_code == 0, f"Output: {result.output}"

    def test_successful_rename_output_shows_old_and_new_form(self) -> None:
        """Output shows old display form, new display form, and operation ID."""
        from chronovista.services.tag_management import RenameResult

        mock_result = RenameResult(
            normalized_form="mexico",
            old_form="Mexico",
            new_form="Mexico City",
            operation_id=_OP_ID,
        )

        with patch("chronovista.cli.tag_commands.db_manager") as mock_db, patch(
            "chronovista.cli.tag_commands._create_tag_management_service"
        ) as mock_factory:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            mock_service = AsyncMock()
            mock_service.rename.return_value = mock_result
            mock_factory.return_value = mock_service

            result = runner.invoke(
                app, ["tags", "rename", "mexico", "--to", "Mexico City"]
            )

        assert "Rename Successful" in result.output
        assert "Mexico" in result.output
        assert "Mexico City" in result.output
        assert str(_OP_ID) in result.output

    def test_rename_with_reason_propagates_reason(self) -> None:
        """--reason flag is forwarded to service.rename()."""
        from chronovista.services.tag_management import RenameResult

        mock_result = RenameResult(
            normalized_form="mexico",
            old_form="Mexico",
            new_form="Mexico City",
            operation_id=_OP_ID,
        )

        with patch("chronovista.cli.tag_commands.db_manager") as mock_db, patch(
            "chronovista.cli.tag_commands._create_tag_management_service"
        ) as mock_factory:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            mock_service = AsyncMock()
            mock_service.rename.return_value = mock_result
            mock_factory.return_value = mock_service

            result = runner.invoke(
                app,
                [
                    "tags",
                    "rename",
                    "mexico",
                    "--to",
                    "Mexico City",
                    "--reason",
                    "More specific display name",
                ],
            )

        assert result.exit_code == 0
        call_kwargs = mock_service.rename.call_args[1]
        assert call_kwargs.get("reason") == "More specific display name"

    def test_rename_value_error_exits_code_1(self) -> None:
        """ValueError from service produces exit code 1."""
        with patch("chronovista.cli.tag_commands.db_manager") as mock_db, patch(
            "chronovista.cli.tag_commands._create_tag_management_service"
        ) as mock_factory:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            mock_service = AsyncMock()
            mock_service.rename.side_effect = ValueError("Tag 'nonexistent' not found")
            mock_factory.return_value = mock_service

            result = runner.invoke(
                app, ["tags", "rename", "nonexistent", "--to", "Something"]
            )

        assert result.exit_code == 1

    def test_rename_value_error_shows_rename_failed_panel(self) -> None:
        """ValueError message is displayed in Rename Failed panel."""
        with patch("chronovista.cli.tag_commands.db_manager") as mock_db, patch(
            "chronovista.cli.tag_commands._create_tag_management_service"
        ) as mock_factory:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            mock_service = AsyncMock()
            mock_service.rename.side_effect = ValueError("New display form cannot be empty")
            mock_factory.return_value = mock_service

            result = runner.invoke(
                app, ["tags", "rename", "mexico", "--to", "   "]
            )

        assert "Rename Failed" in result.output

    def test_rename_missing_to_flag_exits_nonzero(self) -> None:
        """Missing required --to option exits with non-zero code."""
        result = runner.invoke(app, ["tags", "rename", "mexico"])

        assert result.exit_code != 0

    def test_rename_reason_too_long_exits_code_2(self) -> None:
        """--reason exceeding 1000 chars triggers Typer bad parameter (exit 2)."""
        long_reason = "r" * 1001

        result = runner.invoke(
            app, ["tags", "rename", "mexico", "--to", "Mexico", "--reason", long_reason]
        )

        assert result.exit_code == 2

    def test_rename_help_flag(self) -> None:
        """--help shows usage and exits 0."""
        result = runner.invoke(app, ["tags", "rename", "--help"])

        assert result.exit_code == 0
        assert "--to" in result.output
        assert "--reason" in result.output


# ---------------------------------------------------------------------------
# Undo command tests
# ---------------------------------------------------------------------------


def _make_operation_log_mock(
    op_id: uuid.UUID,
    op_type: str,
    rolled_back: bool = False,
    reason: str | None = None,
) -> MagicMock:
    """Build a MagicMock that looks like a TagOperationLog ORM row."""
    log = MagicMock()
    log.id = op_id
    log.operation_type = op_type
    log.performed_at = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    log.rolled_back = rolled_back
    log.reason = reason
    return log


class TestUndoCommand:
    """Integration tests for `chronovista tags undo`."""

    def test_undo_merge_exit_code_zero(self) -> None:
        """Undoing a merge operation returns exit code 0."""
        from chronovista.services.tag_management import UndoResult

        mock_result = UndoResult(
            operation_type="merge",
            operation_id=_OP_ID,
            details="Unmerged mejico from target",
        )

        with patch("chronovista.cli.tag_commands.db_manager") as mock_db, patch(
            "chronovista.cli.tag_commands._create_tag_management_service"
        ) as mock_factory:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            mock_service = AsyncMock()
            mock_service.undo.return_value = mock_result
            mock_factory.return_value = mock_service

            result = runner.invoke(app, ["tags", "undo", str(_OP_ID)])

        assert result.exit_code == 0, f"Output: {result.output}"

    def test_undo_merge_output_shows_undo_successful(self) -> None:
        """Successful undo output shows 'Undo Successful' panel."""
        from chronovista.services.tag_management import UndoResult

        mock_result = UndoResult(
            operation_type="merge",
            operation_id=_OP_ID,
            details="Unmerged mejico from target",
        )

        with patch("chronovista.cli.tag_commands.db_manager") as mock_db, patch(
            "chronovista.cli.tag_commands._create_tag_management_service"
        ) as mock_factory:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            mock_service = AsyncMock()
            mock_service.undo.return_value = mock_result
            mock_factory.return_value = mock_service

            result = runner.invoke(app, ["tags", "undo", str(_OP_ID)])

        assert "Undo Successful" in result.output
        assert "merge" in result.output
        assert "Unmerged" in result.output

    def test_undo_split_exit_code_zero(self) -> None:
        """Undoing a split operation returns exit code 0."""
        from chronovista.services.tag_management import UndoResult

        mock_result = UndoResult(
            operation_type="split",
            operation_id=_OP_ID,
            details="Reunited 2 aliases back into 'python'",
        )

        with patch("chronovista.cli.tag_commands.db_manager") as mock_db, patch(
            "chronovista.cli.tag_commands._create_tag_management_service"
        ) as mock_factory:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            mock_service = AsyncMock()
            mock_service.undo.return_value = mock_result
            mock_factory.return_value = mock_service

            result = runner.invoke(app, ["tags", "undo", str(_OP_ID)])

        assert result.exit_code == 0

    def test_undo_split_output_shows_reunited_details(self) -> None:
        """Undo split output contains the reunited-aliases detail string."""
        from chronovista.services.tag_management import UndoResult

        mock_result = UndoResult(
            operation_type="split",
            operation_id=_OP_ID,
            details="Reunited 2 aliases back into 'python'",
        )

        with patch("chronovista.cli.tag_commands.db_manager") as mock_db, patch(
            "chronovista.cli.tag_commands._create_tag_management_service"
        ) as mock_factory:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            mock_service = AsyncMock()
            mock_service.undo.return_value = mock_result
            mock_factory.return_value = mock_service

            result = runner.invoke(app, ["tags", "undo", str(_OP_ID)])

        assert "Reunited" in result.output
        assert "python" in result.output

    def test_undo_list_shows_recent_operations_table(self) -> None:
        """--list flag outputs a Recent Tag Operations table."""
        log_entry = _make_operation_log_mock(_OP_ID, "merge", reason="test reason")

        with patch("chronovista.cli.tag_commands.db_manager") as mock_db, patch(
            "chronovista.cli.tag_commands._create_tag_management_service"
        ) as mock_factory:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            mock_service = AsyncMock()
            mock_service.list_recent_operations.return_value = [log_entry]
            mock_factory.return_value = mock_service

            result = runner.invoke(app, ["tags", "undo", "--list"])

        assert result.exit_code == 0
        # Table heading is always present
        assert "Recent Tag Operations" in result.output
        # The Timestamp column header is wide enough to appear untruncated
        assert "Timestamp" in result.output

    def test_undo_list_empty_shows_no_operations_panel(self) -> None:
        """--list with no operations shows 'No Operations' panel."""
        with patch("chronovista.cli.tag_commands.db_manager") as mock_db, patch(
            "chronovista.cli.tag_commands._create_tag_management_service"
        ) as mock_factory:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            mock_service = AsyncMock()
            mock_service.list_recent_operations.return_value = []
            mock_factory.return_value = mock_service

            result = runner.invoke(app, ["tags", "undo", "--list"])

        assert result.exit_code == 0
        assert "No Operations" in result.output

    def test_undo_invalid_uuid_exits_code_1(self) -> None:
        """Passing a non-UUID string produces exit code 1."""
        with patch("chronovista.cli.tag_commands.db_manager") as mock_db, patch(
            "chronovista.cli.tag_commands._create_tag_management_service"
        ) as mock_factory:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            mock_service = AsyncMock()
            mock_factory.return_value = mock_service

            result = runner.invoke(app, ["tags", "undo", "not-a-uuid"])

        assert result.exit_code == 1

    def test_undo_invalid_uuid_shows_invalid_operation_id_panel(self) -> None:
        """Passing a non-UUID string shows 'Invalid Operation ID' panel."""
        with patch("chronovista.cli.tag_commands.db_manager") as mock_db, patch(
            "chronovista.cli.tag_commands._create_tag_management_service"
        ) as mock_factory:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            mock_service = AsyncMock()
            mock_factory.return_value = mock_service

            result = runner.invoke(app, ["tags", "undo", "not-a-uuid"])

        assert "Invalid Operation ID" in result.output

    def test_undo_no_argument_no_list_exits_code_2(self) -> None:
        """Invoking undo with no argument and no --list flag exits with code 2."""
        with patch("chronovista.cli.tag_commands.db_manager") as mock_db, patch(
            "chronovista.cli.tag_commands._create_tag_management_service"
        ) as mock_factory:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            mock_service = AsyncMock()
            mock_factory.return_value = mock_service

            result = runner.invoke(app, ["tags", "undo"])

        assert result.exit_code == 2

    def test_undo_already_undone_exits_code_1(self) -> None:
        """ValueError for already-undone operation produces exit code 1."""
        with patch("chronovista.cli.tag_commands.db_manager") as mock_db, patch(
            "chronovista.cli.tag_commands._create_tag_management_service"
        ) as mock_factory:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            mock_service = AsyncMock()
            mock_service.undo.side_effect = ValueError(
                f"Operation '{_OP_ID}' has already been undone"
            )
            mock_factory.return_value = mock_service

            result = runner.invoke(app, ["tags", "undo", str(_OP_ID)])

        assert result.exit_code == 1

    def test_undo_not_implemented_exits_code_1(self) -> None:
        """UndoNotImplementedError produces exit code 1 with 'Undo Not Available' panel."""
        from chronovista.services.tag_management import UndoNotImplementedError

        with patch("chronovista.cli.tag_commands.db_manager") as mock_db, patch(
            "chronovista.cli.tag_commands._create_tag_management_service"
        ) as mock_factory:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            mock_service = AsyncMock()
            mock_service.undo.side_effect = UndoNotImplementedError(
                "Undo for 'delete' is not yet implemented"
            )
            mock_factory.return_value = mock_service

            result = runner.invoke(app, ["tags", "undo", str(_OP_ID)])

        assert result.exit_code == 1
        assert "Undo Not Available" in result.output

    def test_undo_list_shows_rolled_back_yes_for_rolled_back_ops(self) -> None:
        """Rolled-back operations display 'yes' in the Rolled Back column."""
        log_entry = _make_operation_log_mock(_OP_ID, "rename", rolled_back=True)

        with patch("chronovista.cli.tag_commands.db_manager") as mock_db, patch(
            "chronovista.cli.tag_commands._create_tag_management_service"
        ) as mock_factory:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            mock_service = AsyncMock()
            mock_service.list_recent_operations.return_value = [log_entry]
            mock_factory.return_value = mock_service

            result = runner.invoke(app, ["tags", "undo", "--list"])

        assert result.exit_code == 0
        # Rich renders "yes" in green but strips markup in test output
        assert "yes" in result.output

    def test_undo_help_flag(self) -> None:
        """--help shows usage text and exits 0."""
        result = runner.invoke(app, ["tags", "undo", "--help"])

        assert result.exit_code == 0
        assert "--list" in result.output


# ---------------------------------------------------------------------------
# Classify command tests
# ---------------------------------------------------------------------------


class TestClassifyCommand:
    """Integration tests for `chronovista tags classify`."""

    def test_classify_person_exit_code_zero(self) -> None:
        """Classifying a tag as 'person' returns exit code 0."""
        from chronovista.services.tag_management import ClassifyResult

        mock_result = ClassifyResult(
            normalized_form="elon musk",
            canonical_form="Elon Musk",
            entity_type="person",
            entity_created=True,
            entity_alias_count=3,
            operation_id=_OP_ID,
        )

        with patch("chronovista.cli.tag_commands.db_manager") as mock_db, patch(
            "chronovista.cli.tag_commands._create_tag_management_service"
        ) as mock_factory:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            mock_service = AsyncMock()
            mock_service.classify.return_value = mock_result
            mock_factory.return_value = mock_service

            result = runner.invoke(
                app, ["tags", "classify", "elon musk", "--type", "person"]
            )

        assert result.exit_code == 0, f"Output: {result.output}"

    def test_classify_person_output_shows_classify_successful(self) -> None:
        """Classify output shows 'Classify Successful' panel with entity type."""
        from chronovista.services.tag_management import ClassifyResult

        mock_result = ClassifyResult(
            normalized_form="elon musk",
            canonical_form="Elon Musk",
            entity_type="person",
            entity_created=True,
            entity_alias_count=3,
            operation_id=_OP_ID,
        )

        with patch("chronovista.cli.tag_commands.db_manager") as mock_db, patch(
            "chronovista.cli.tag_commands._create_tag_management_service"
        ) as mock_factory:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            mock_service = AsyncMock()
            mock_service.classify.return_value = mock_result
            mock_factory.return_value = mock_service

            result = runner.invoke(
                app, ["tags", "classify", "elon musk", "--type", "person"]
            )

        assert "Classify Successful" in result.output
        assert "person" in result.output
        assert "Elon Musk" in result.output
        assert str(_OP_ID) in result.output

    def test_classify_topic_exit_code_zero(self) -> None:
        """Classifying a tag as 'topic' (tag-only type) returns exit code 0."""
        from chronovista.services.tag_management import ClassifyResult

        mock_result = ClassifyResult(
            normalized_form="machine learning",
            canonical_form="Machine Learning",
            entity_type="topic",
            entity_created=False,
            entity_alias_count=0,
            operation_id=_OP_ID,
        )

        with patch("chronovista.cli.tag_commands.db_manager") as mock_db, patch(
            "chronovista.cli.tag_commands._create_tag_management_service"
        ) as mock_factory:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            mock_service = AsyncMock()
            mock_service.classify.return_value = mock_result
            mock_factory.return_value = mock_service

            result = runner.invoke(
                app, ["tags", "classify", "machine learning", "--type", "topic"]
            )

        assert result.exit_code == 0

    def test_classify_top_browses_unclassified_tags(self) -> None:
        """--top N shows a table of top unclassified canonical tags."""
        # Build simple ORM-like mocks
        tag1 = MagicMock()
        tag1.normalized_form = "python"
        tag1.canonical_form = "Python"
        tag1.video_count = 500
        tag1.alias_count = 5

        tag2 = MagicMock()
        tag2.normalized_form = "javascript"
        tag2.canonical_form = "JavaScript"
        tag2.video_count = 400
        tag2.alias_count = 3

        with patch("chronovista.cli.tag_commands.db_manager") as mock_db, patch(
            "chronovista.cli.tag_commands._create_tag_management_service"
        ) as mock_factory:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            mock_service = AsyncMock()
            mock_service.classify_top_unclassified.return_value = [tag1, tag2]
            mock_factory.return_value = mock_service

            result = runner.invoke(app, ["tags", "classify", "--top", "2"])

        assert result.exit_code == 0
        assert "python" in result.output
        assert "javascript" in result.output
        mock_service.classify_top_unclassified.assert_called_once()

    def test_classify_top_no_unclassified_shows_empty_panel(self) -> None:
        """--top N with no unclassified tags shows 'No unclassified tags found' panel."""
        with patch("chronovista.cli.tag_commands.db_manager") as mock_db, patch(
            "chronovista.cli.tag_commands._create_tag_management_service"
        ) as mock_factory:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            mock_service = AsyncMock()
            mock_service.classify_top_unclassified.return_value = []
            mock_factory.return_value = mock_service

            result = runner.invoke(app, ["tags", "classify", "--top", "10"])

        assert result.exit_code == 0
        assert "No unclassified tags" in result.output

    def test_classify_force_flag_passed_to_service(self) -> None:
        """--force flag is forwarded to service.classify()."""
        from chronovista.services.tag_management import ClassifyResult

        mock_result = ClassifyResult(
            normalized_form="python",
            canonical_form="Python",
            entity_type="topic",
            entity_created=False,
            entity_alias_count=0,
            operation_id=_OP_ID,
        )

        with patch("chronovista.cli.tag_commands.db_manager") as mock_db, patch(
            "chronovista.cli.tag_commands._create_tag_management_service"
        ) as mock_factory:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            mock_service = AsyncMock()
            mock_service.classify.return_value = mock_result
            mock_factory.return_value = mock_service

            result = runner.invoke(
                app, ["tags", "classify", "python", "--type", "topic", "--force"]
            )

        assert result.exit_code == 0
        call_kwargs = mock_service.classify.call_args[1]
        assert call_kwargs.get("force") is True

    def test_classify_invalid_entity_type_exits_code_1(self) -> None:
        """Invalid --type value exits with code 1 before calling service."""
        with patch("chronovista.cli.tag_commands.db_manager") as mock_db, patch(
            "chronovista.cli.tag_commands._create_tag_management_service"
        ) as mock_factory:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            mock_service = AsyncMock()
            mock_factory.return_value = mock_service

            result = runner.invoke(
                app, ["tags", "classify", "python", "--type", "invalid_type"]
            )

        assert result.exit_code == 1
        # Service should NOT be called — validation happens before service call
        mock_service.classify.assert_not_called()

    def test_classify_invalid_entity_type_shows_invalid_type_panel(self) -> None:
        """Invalid --type shows 'Invalid --type' panel with valid values."""
        with patch("chronovista.cli.tag_commands.db_manager") as mock_db, patch(
            "chronovista.cli.tag_commands._create_tag_management_service"
        ) as mock_factory:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            mock_service = AsyncMock()
            mock_factory.return_value = mock_service

            result = runner.invoke(
                app, ["tags", "classify", "python", "--type", "bad_type"]
            )

        assert "Invalid --type" in result.output
        # Valid type names must be listed
        assert "person" in result.output

    def test_classify_top_and_normalized_form_mutual_exclusion_exits_code_2(self) -> None:
        """Using --top together with a positional tag argument exits with code 2."""
        result = runner.invoke(
            app, ["tags", "classify", "python", "--top", "5"]
        )

        assert result.exit_code == 2

    def test_classify_no_args_exits_code_2(self) -> None:
        """Invoking classify with no positional arg and no --top exits with code 2."""
        result = runner.invoke(app, ["tags", "classify"])

        assert result.exit_code == 2

    def test_classify_missing_type_flag_exits_code_2(self) -> None:
        """Providing a positional tag but omitting --type exits with code 2."""
        result = runner.invoke(app, ["tags", "classify", "python"])

        assert result.exit_code == 2

    def test_classify_value_error_exits_code_1(self) -> None:
        """ValueError from service (e.g., already classified) produces exit code 1."""
        with patch("chronovista.cli.tag_commands.db_manager") as mock_db, patch(
            "chronovista.cli.tag_commands._create_tag_management_service"
        ) as mock_factory:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            mock_service = AsyncMock()
            mock_service.classify.side_effect = ValueError(
                "Tag 'python' is already classified as 'topic'. Use --force to override."
            )
            mock_factory.return_value = mock_service

            result = runner.invoke(
                app, ["tags", "classify", "python", "--type", "topic"]
            )

        assert result.exit_code == 1
        assert "Classify Failed" in result.output

    def test_classify_with_reason_propagates_reason(self) -> None:
        """--reason flag is forwarded to service.classify()."""
        from chronovista.services.tag_management import ClassifyResult

        mock_result = ClassifyResult(
            normalized_form="python",
            canonical_form="Python",
            entity_type="technical_term",
            entity_created=True,
            entity_alias_count=2,
            operation_id=_OP_ID,
        )

        with patch("chronovista.cli.tag_commands.db_manager") as mock_db, patch(
            "chronovista.cli.tag_commands._create_tag_management_service"
        ) as mock_factory:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            mock_service = AsyncMock()
            mock_service.classify.return_value = mock_result
            mock_factory.return_value = mock_service

            result = runner.invoke(
                app,
                [
                    "tags",
                    "classify",
                    "python",
                    "--type",
                    "technical_term",
                    "--reason",
                    "Programming language",
                ],
            )

        assert result.exit_code == 0
        call_kwargs = mock_service.classify.call_args[1]
        assert call_kwargs.get("reason") == "Programming language"

    def test_classify_help_flag(self) -> None:
        """--help shows usage text and exits 0."""
        result = runner.invoke(app, ["tags", "classify", "--help"])

        assert result.exit_code == 0
        assert "--type" in result.output
        assert "--top" in result.output
        assert "--force" in result.output


# ---------------------------------------------------------------------------
# Collisions command tests
# ---------------------------------------------------------------------------


def _make_collision_group(
    canonical_form: str = "Cafe",
    normalized_form: str = "cafe",
    aliases: list[dict[str, Any]] | None = None,
    total_occurrences: int = 10,
) -> "CollisionGroup":
    """Build a CollisionGroup-like mock."""
    from chronovista.services.tag_management import CollisionGroup

    if aliases is None:
        aliases = [
            {"raw_form": "Cafe", "occurrence_count": 6},
            {"raw_form": "Café", "occurrence_count": 4},
        ]

    tag_id = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    return CollisionGroup(
        canonical_form=canonical_form,
        normalized_form=normalized_form,
        canonical_tag_id=tag_id,
        aliases=aliases,
        total_occurrence_count=total_occurrences,
    )


class TestCollisionsCommand:
    """Integration tests for `chronovista tags collisions`."""

    def test_json_format_exits_code_zero(self) -> None:
        """--format json exits with code 0 when collisions exist."""
        collision = _make_collision_group()

        with patch("chronovista.cli.tag_commands.db_manager") as mock_db, patch(
            "chronovista.cli.tag_commands._create_tag_management_service"
        ) as mock_factory:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            mock_service = AsyncMock()
            mock_service.get_collisions.return_value = [collision]
            mock_factory.return_value = mock_service

            result = runner.invoke(app, ["tags", "collisions", "--format", "json"])

        assert result.exit_code == 0, f"Output: {result.output}"

    def test_json_format_output_contains_collision_data(self) -> None:
        """JSON output contains canonical_form, normalized_form, and aliases."""
        import json

        collision = _make_collision_group(
            canonical_form="Cafe", normalized_form="cafe"
        )

        with patch("chronovista.cli.tag_commands.db_manager") as mock_db, patch(
            "chronovista.cli.tag_commands._create_tag_management_service"
        ) as mock_factory:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            mock_service = AsyncMock()
            mock_service.get_collisions.return_value = [collision]
            mock_factory.return_value = mock_service

            result = runner.invoke(app, ["tags", "collisions", "--format", "json"])

        assert result.exit_code == 0
        # Output should be parseable JSON
        parsed = json.loads(result.output)
        assert isinstance(parsed, list)
        assert len(parsed) == 1
        assert parsed[0]["canonical_form"] == "Cafe"
        assert parsed[0]["normalized_form"] == "cafe"
        assert "aliases" in parsed[0]

    def test_json_format_with_limit_respected(self) -> None:
        """--limit is forwarded to service.get_collisions()."""
        with patch("chronovista.cli.tag_commands.db_manager") as mock_db, patch(
            "chronovista.cli.tag_commands._create_tag_management_service"
        ) as mock_factory:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            mock_service = AsyncMock()
            mock_service.get_collisions.return_value = []
            mock_factory.return_value = mock_service

            result = runner.invoke(
                app, ["tags", "collisions", "--format", "json", "--limit", "5"]
            )

        assert result.exit_code == 0
        call_kwargs = mock_service.get_collisions.call_args[1]
        assert call_kwargs.get("limit") == 5

    def test_no_collisions_shows_no_candidates_message(self) -> None:
        """No collision candidates prints a green 'No collision candidates found' message."""
        with patch("chronovista.cli.tag_commands.db_manager") as mock_db, patch(
            "chronovista.cli.tag_commands._create_tag_management_service"
        ) as mock_factory:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            mock_service = AsyncMock()
            mock_service.get_collisions.return_value = []
            mock_factory.return_value = mock_service

            result = runner.invoke(app, ["tags", "collisions", "--format", "json"])

        assert result.exit_code == 0
        assert "No collision candidates found" in result.output

    def test_include_reviewed_flag_forwarded_to_service(self) -> None:
        """--include-reviewed is forwarded to service.get_collisions()."""
        with patch("chronovista.cli.tag_commands.db_manager") as mock_db, patch(
            "chronovista.cli.tag_commands._create_tag_management_service"
        ) as mock_factory:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            mock_service = AsyncMock()
            mock_service.get_collisions.return_value = []
            mock_factory.return_value = mock_service

            result = runner.invoke(
                app,
                ["tags", "collisions", "--format", "json", "--include-reviewed"],
            )

        assert result.exit_code == 0
        call_kwargs = mock_service.get_collisions.call_args[1]
        assert call_kwargs.get("include_reviewed") is True

    def test_json_output_multiple_collisions(self) -> None:
        """JSON output with multiple groups returns a list of correct length."""
        import json

        collisions = [
            _make_collision_group("Cafe", "cafe", total_occurrences=20),
            _make_collision_group("Resume", "resume", total_occurrences=15),
        ]
        # Give second collision a distinct canonical_tag_id
        collisions[1].canonical_tag_id = uuid.UUID(
            "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
        )

        with patch("chronovista.cli.tag_commands.db_manager") as mock_db, patch(
            "chronovista.cli.tag_commands._create_tag_management_service"
        ) as mock_factory:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            mock_service = AsyncMock()
            mock_service.get_collisions.return_value = collisions
            mock_factory.return_value = mock_service

            result = runner.invoke(app, ["tags", "collisions", "--format", "json"])

        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert len(parsed) == 2

    def test_collisions_help_flag(self) -> None:
        """--help shows usage text and exits 0."""
        result = runner.invoke(app, ["tags", "collisions", "--help"])

        assert result.exit_code == 0
        assert "--format" in result.output
        assert "--limit" in result.output


# ---------------------------------------------------------------------------
# Deprecate command tests
# ---------------------------------------------------------------------------


class TestDeprecateCommand:
    """Integration tests for `chronovista tags deprecate`."""

    def test_successful_deprecate_exit_code_zero(self) -> None:
        """Deprecating an active tag returns exit code 0."""
        from chronovista.services.tag_management import DeprecateResult

        mock_result = DeprecateResult(
            normalized_form="old tag",
            canonical_form="Old Tag",
            alias_count=3,
            operation_id=_OP_ID,
        )

        with patch("chronovista.cli.tag_commands.db_manager") as mock_db, patch(
            "chronovista.cli.tag_commands._create_tag_management_service"
        ) as mock_factory:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            mock_service = AsyncMock()
            mock_service.deprecate.return_value = mock_result
            mock_factory.return_value = mock_service

            result = runner.invoke(app, ["tags", "deprecate", "old tag"])

        assert result.exit_code == 0, f"Output: {result.output}"

    def test_successful_deprecate_output_shows_deprecate_successful(self) -> None:
        """Successful deprecation output shows 'Deprecate Successful' panel."""
        from chronovista.services.tag_management import DeprecateResult

        mock_result = DeprecateResult(
            normalized_form="old tag",
            canonical_form="Old Tag",
            alias_count=3,
            operation_id=_OP_ID,
        )

        with patch("chronovista.cli.tag_commands.db_manager") as mock_db, patch(
            "chronovista.cli.tag_commands._create_tag_management_service"
        ) as mock_factory:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            mock_service = AsyncMock()
            mock_service.deprecate.return_value = mock_result
            mock_factory.return_value = mock_service

            result = runner.invoke(app, ["tags", "deprecate", "old tag"])

        assert "Deprecate Successful" in result.output
        assert "old tag" in result.output
        assert "Old Tag" in result.output
        assert str(_OP_ID) in result.output

    def test_deprecate_with_reason_propagates_reason(self) -> None:
        """--reason flag is forwarded to service.deprecate()."""
        from chronovista.services.tag_management import DeprecateResult

        mock_result = DeprecateResult(
            normalized_form="old tag",
            canonical_form="Old Tag",
            alias_count=1,
            operation_id=_OP_ID,
        )

        with patch("chronovista.cli.tag_commands.db_manager") as mock_db, patch(
            "chronovista.cli.tag_commands._create_tag_management_service"
        ) as mock_factory:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            mock_service = AsyncMock()
            mock_service.deprecate.return_value = mock_result
            mock_factory.return_value = mock_service

            result = runner.invoke(
                app,
                ["tags", "deprecate", "old tag", "--reason", "No longer relevant"],
            )

        assert result.exit_code == 0
        call_kwargs = mock_service.deprecate.call_args[1]
        assert call_kwargs.get("reason") == "No longer relevant"

    def test_deprecate_list_shows_deprecated_tags_table(self) -> None:
        """--list flag outputs a table of deprecated canonical tags."""
        tag1 = MagicMock()
        tag1.normalized_form = "old tag"
        tag1.canonical_form = "Old Tag"
        tag1.alias_count = 2
        tag1.video_count = 5

        with patch("chronovista.cli.tag_commands.db_manager") as mock_db, patch(
            "chronovista.cli.tag_commands._create_tag_management_service"
        ) as mock_factory:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            mock_service = AsyncMock()
            mock_service.list_deprecated.return_value = [tag1]
            mock_factory.return_value = mock_service

            result = runner.invoke(app, ["tags", "deprecate", "--list"])

        assert result.exit_code == 0
        assert "Deprecated Tags" in result.output
        assert "old tag" in result.output

    def test_deprecate_list_empty_shows_no_deprecated_panel(self) -> None:
        """--list with no deprecated tags shows 'No deprecated tags found' panel."""
        with patch("chronovista.cli.tag_commands.db_manager") as mock_db, patch(
            "chronovista.cli.tag_commands._create_tag_management_service"
        ) as mock_factory:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            mock_service = AsyncMock()
            mock_service.list_deprecated.return_value = []
            mock_factory.return_value = mock_service

            result = runner.invoke(app, ["tags", "deprecate", "--list"])

        assert result.exit_code == 0
        assert "No deprecated tags found" in result.output

    def test_deprecate_list_and_tag_arg_mutual_exclusion_exits_code_2(self) -> None:
        """Using --list with a positional tag argument exits with code 2."""
        result = runner.invoke(app, ["tags", "deprecate", "sometag", "--list"])

        assert result.exit_code == 2

    def test_deprecate_no_args_exits_code_2(self) -> None:
        """Invoking deprecate with no positional arg and no --list exits with code 2."""
        result = runner.invoke(app, ["tags", "deprecate"])

        assert result.exit_code == 2

    def test_deprecate_value_error_exits_code_1(self) -> None:
        """ValueError from service (tag not found or already deprecated) exits code 1."""
        with patch("chronovista.cli.tag_commands.db_manager") as mock_db, patch(
            "chronovista.cli.tag_commands._create_tag_management_service"
        ) as mock_factory:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            mock_service = AsyncMock()
            mock_service.deprecate.side_effect = ValueError(
                "Tag 'nonexistent' not found"
            )
            mock_factory.return_value = mock_service

            result = runner.invoke(app, ["tags", "deprecate", "nonexistent"])

        assert result.exit_code == 1

    def test_deprecate_value_error_shows_deprecate_failed_panel(self) -> None:
        """ValueError message is displayed in Deprecate Failed panel."""
        with patch("chronovista.cli.tag_commands.db_manager") as mock_db, patch(
            "chronovista.cli.tag_commands._create_tag_management_service"
        ) as mock_factory:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            mock_service = AsyncMock()
            mock_service.deprecate.side_effect = ValueError(
                "Tag 'already-deprecated' exists but has status 'deprecated'"
            )
            mock_factory.return_value = mock_service

            result = runner.invoke(app, ["tags", "deprecate", "already-deprecated"])

        assert "Deprecate Failed" in result.output

    def test_deprecate_reason_too_long_exits_code_2(self) -> None:
        """--reason exceeding 1000 chars triggers Typer bad parameter (exit 2)."""
        long_reason = "d" * 1001

        result = runner.invoke(
            app, ["tags", "deprecate", "sometag", "--reason", long_reason]
        )

        assert result.exit_code == 2

    def test_deprecate_help_flag(self) -> None:
        """--help shows usage text and exits 0."""
        result = runner.invoke(app, ["tags", "deprecate", "--help"])

        assert result.exit_code == 0
        assert "--list" in result.output
        assert "--reason" in result.output

    def test_undo_deprecate_end_to_end(self) -> None:
        """Undo a deprecate restores the tag status (end-to-end via mock)."""
        from chronovista.services.tag_management import UndoResult

        undo_result = UndoResult(
            operation_type="delete",
            operation_id=_OP_ID,
            details="Restored 'old tag' from deprecated to active",
        )

        with patch("chronovista.cli.tag_commands.db_manager") as mock_db, patch(
            "chronovista.cli.tag_commands._create_tag_management_service"
        ) as mock_factory:
            mock_session = AsyncMock()
            mock_db.get_session.return_value = _make_get_session(mock_session)

            mock_service = AsyncMock()
            mock_service.undo.return_value = undo_result
            mock_factory.return_value = mock_service

            result = runner.invoke(app, ["tags", "undo", str(_OP_ID)])

        assert result.exit_code == 0
        assert "Undo Successful" in result.output
        assert "Restored" in result.output
