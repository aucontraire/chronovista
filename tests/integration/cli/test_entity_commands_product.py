"""CLI acceptance for the ``product`` entity type (Feature 103, US1 — FR-001).

The CLI ``--type`` vocabulary derives from ``enums.ENTITY_PRODUCING_TYPES``, so ``product`` is
accepted and listed automatically. Verified here via the real CLI path (CliRunner) for the
derived error message, plus a gate-level assertion for positive acceptance. The positive create
path writes to the DB and is covered end to end by the API test
(``tests/integration/api/test_entity_product_type.py``).
"""

from __future__ import annotations

from typer.testing import CliRunner

from chronovista.cli.entity_commands import _ENTITY_PRODUCING_TYPES
from chronovista.cli.main import app

runner = CliRunner()


def test_product_is_an_accepted_cli_type() -> None:
    # The CLI create gate derives from the single source → 'product' is accepted.
    assert "product" in _ENTITY_PRODUCING_TYPES


def test_create_invalid_type_lists_product_as_valid() -> None:
    # Real CLI path: a bogus --type is rejected (exit 1), and the derived valid-type list now
    # includes 'product', proving the help/error text picks up the new value automatically.
    result = runner.invoke(
        app, ["entities", "create", "Placeholder Name", "--type", "bogus"]
    )
    assert result.exit_code == 1
    assert "product" in result.stdout
