"""SQL-shape guard: visible-name membership folds BOTH operands (Feature 069).

A one-sided fold (folding the name but not the mention text, or vice versa) would silently reintroduce
the accent-sensitivity bug while passing a naive "does it return rows" test. This inspects the compiled
SQL of a representative membership query and asserts the mention_text side AND the name side are both
wrapped in ``lower(unaccent(...))``. Pure SQL-shape; no DB.
"""

from __future__ import annotations

from sqlalchemy.dialects import postgresql

from chronovista.repositories.entity_mention_repository import (
    EntityMentionRepository,
    _folded,
)


def test_visible_name_query_folds_both_operands() -> None:
    repo = EntityMentionRepository()
    # _mention_assoc_stmt is the Feature 066 shared resolver feeding list/detail/panel/provenance.
    import uuid

    stmt = repo._mention_assoc_stmt([uuid.uuid4()])  # type: ignore[attr-defined]
    sql = str(
        stmt.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    ).lower()
    # The fold must wrap BOTH specific operands — the mention text AND a visible name. A count-only
    # check (>= 2) has a blind spot: the two name operands (canonical + alias) alone give 2, so a
    # one-sided regression that un-folds mention_text would slip through. Assert each column by name.
    assert (
        "unaccent(entity_mentions.mention_text" in sql
    ), "the mention_text operand is not folded — one-sided fold reintroduces the bug"
    assert (
        "unaccent(named_entities.canonical_name" in sql
        or "unaccent(entity_aliases.alias_name" in sql
    ), "no visible-name operand is folded"
    assert "lower(unaccent(" in sql


def test_folded_helper_is_lower_of_unaccent() -> None:
    from sqlalchemy import Column, String

    sql = str(
        _folded(Column("x", String)).compile(dialect=postgresql.dialect())
    ).lower()
    assert sql == "lower(unaccent(x))"
