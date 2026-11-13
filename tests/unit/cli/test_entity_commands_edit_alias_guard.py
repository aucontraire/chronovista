"""US4 / FR-007a: `edit-alias` refuses the known-error type.

The free-form ``--new-type`` on ``entity edit-alias`` is bounded by ``allowed_types``
(the five name types), which excludes ``asr_error`` — so the command cannot file a
known-error string among names. The rejection happens before any database session is
opened, so this is a pure CLI unit test.
"""

from __future__ import annotations

from typer.testing import CliRunner

from chronovista.cli.entity_commands import entity_app


class TestEditAliasRejectsKnownErrorType:
    def test_new_type_asr_error_is_rejected(self) -> None:
        runner = CliRunner()
        result = runner.invoke(
            entity_app,
            ["edit-alias", "Invented Person", "--new-type", "asr_error"],
        )
        assert result.exit_code == 1
        assert "not a valid alias type" in result.stdout

    def test_name_type_is_not_rejected_by_the_type_guard(self) -> None:
        """A valid name type passes the type guard (it then proceeds to DB work)."""
        runner = CliRunner()
        result = runner.invoke(
            entity_app,
            ["edit-alias", "Invented Person", "--new-type", "nickname"],
        )
        # It must NOT fail with the invalid-type message; any later outcome
        # (entity not found, etc.) is beyond this guard's scope.
        assert "not a valid alias type" not in result.stdout
