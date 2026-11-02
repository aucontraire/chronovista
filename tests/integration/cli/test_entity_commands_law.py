"""CLI acceptance for the ``law`` entity type (Feature 104, US1 — FR-001).

The CLI ``--type`` vocabulary derives from ``enums.ENTITY_PRODUCING_TYPES``, so ``law`` is
accepted and listed automatically. Verified via the real CLI path (the derived error message)
plus a gate-level assertion; the positive DB path is covered end to end by the API test
(``tests/integration/api/test_entity_law_type.py``).
"""

from __future__ import annotations

from typer.testing import CliRunner

from chronovista.cli.entity_commands import _ENTITY_PRODUCING_TYPES
from chronovista.cli.main import app

runner = CliRunner()


def test_law_is_an_accepted_cli_type() -> None:
    assert "law" in _ENTITY_PRODUCING_TYPES


def test_create_invalid_type_lists_law_as_valid() -> None:
    result = runner.invoke(
        app, ["entities", "create", "Placeholder Name", "--type", "bogus"]
    )
    assert result.exit_code == 1
    assert "law" in result.stdout
