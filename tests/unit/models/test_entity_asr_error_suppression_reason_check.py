"""FR-011 -- the ``entity_asr_errors.suppression_reason`` value CHECK.

Enforces the CHECK for real (SQLite evaluates the same predicate text) rather than
string-matching it: ``'bogus'`` is rejected; ``'zero_signal'``,
``'mostly_false_redundant'`` and NULL are accepted. Also pins that the migration's
predicate and the ORM model's predicate are the same text, so they cannot drift.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy import CheckConstraint

from chronovista.db.models import EntityAsrError

_CHECK_NAME = "chk_entity_asr_error_suppression_reason_valid"


def _model_check_sql() -> str:
    for c in EntityAsrError.__table__.constraints:
        if isinstance(c, CheckConstraint) and c.name == _CHECK_NAME:
            return str(c.sqltext)
    raise AssertionError(f"{_CHECK_NAME} missing from EntityAsrError")


def _engine_with_check() -> sa.Engine:
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "CREATE TABLE t (suppression_reason VARCHAR(32), "
                f"CONSTRAINT {_CHECK_NAME} CHECK ({_model_check_sql()}))"
            )
        )
    return engine


def _insert(engine: sa.Engine, value: str | None) -> None:
    with engine.begin() as conn:
        conn.execute(sa.text("INSERT INTO t VALUES (:v)"), {"v": value})


class TestSuppressionReasonCheck:
    @pytest.mark.parametrize("value", ["zero_signal", "mostly_false_redundant", None])
    def test_accepts_valid_values_and_null(self, value: str | None) -> None:
        _insert(_engine_with_check(), value)

    def test_rejects_unknown_value(self) -> None:
        with pytest.raises(sa.exc.IntegrityError):
            _insert(_engine_with_check(), "bogus")

    def test_migration_predicate_matches_model(self) -> None:
        path = next(
            Path(__file__)
            .resolve()
            .parents[3]
            .joinpath("src/chronovista/db/migrations/versions")
            .glob("*_asr_error_suppression_reason.py")
        )
        spec = importlib.util.spec_from_file_location("_mig", path)
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert mod._CHECK == _CHECK_NAME
        assert mod.down_revision == "d4b1f8a3c6e5"
        source = path.read_text()
        for token in ("IS NULL OR", "'zero_signal'", "'mostly_false_redundant'"):
            assert token in source
            assert token in _model_check_sql()
