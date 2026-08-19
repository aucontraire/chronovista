"""Unit tests for the ``_folded`` visible-name fold helper (Feature 069).

``_folded(col)`` is the single accent+case fold shared by every visible-name membership site and the
counter recompute. It MUST compile to ``lower(unaccent(<col>))`` and be applied to the SQL column, not
to a Python-side value — a one-sided or Python-side fold would silently reintroduce the accent-
sensitivity bug. These are pure SQL-shape assertions; no database needed.
"""

from __future__ import annotations

from sqlalchemy import Column, String
from sqlalchemy.dialects import postgresql

from chronovista.repositories.entity_mention_repository import _folded


def _compiled(expr: object) -> str:
    return str(
        expr.compile(  # type: ignore[attr-defined]
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    ).lower()


class TestFoldedHelper:
    def test_compiles_to_lower_unaccent(self) -> None:
        col = Column("alias_name", String)
        sql = _compiled(_folded(col))
        # Order matters: unaccent inside lower — lower(unaccent(col)), not unaccent(lower(col)).
        assert "lower(unaccent(" in sql
        assert "alias_name" in sql

    def test_applies_to_the_column_not_a_python_value(self) -> None:
        # The helper must wrap the column reference itself; the compiled SQL references the
        # column, proving the fold runs in the database rather than on a pre-folded literal.
        col = Column("mention_text", String)
        sql = _compiled(_folded(col))
        assert "mention_text" in sql
        assert "unaccent" in sql and "lower" in sql
