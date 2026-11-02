"""Architecture fitness test — the entity-type value list has one home.

Pilot-rule application (Constitution Anti-Slop → "Single-Source Operations and Fitness
Guards"): the entity-type vocabulary was spelled out by hand in eight places — the
``EntityType`` enum, two ``_ENTITY_PRODUCING_TYPES`` sets (API + CLI), the CLI ``--type``
help text and its error message, and three ``CheckConstraint`` SQL strings in
``db/models.py`` (named_entities / canonical_tags / candidate_suggestions). Adding one
type meant editing all eight in lockstep; migration 051 (the only precedent) updates two
of the three CHECKs, because it predates ``candidate_suggestions`` — so copying it drops a
value from ``chk_candidate_type_hint_valid`` and candidate generation fails at INSERT, long
after the migration reports success.

The single home is ``chronovista.models.enums``: ``ENTITY_PRODUCING_TYPES`` (ordered),
``TAG_ONLY_ENTITY_TYPES``, ``ENTITY_TAG_TYPES``, and ``entity_type_in_clause()`` which
renders the CHECK SQL. The ordered tuple is pinned to the historical SQL order so the
generated constraints stay byte-identical and Alembic autogenerate proposes nothing.

CAVEAT (honest): these are literal-based guards. They catch **honest duplication, not
deliberate evasion** — someone could rebuild the list from ``EntityType`` members in a
different spelling and slip past. The goal is a reviewable diff that reads "this adds a
second place that spells out the entity-type vocabulary", not a security boundary.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

from chronovista.models.enums import (
    ENTITY_PRODUCING_TYPES,
    ENTITY_TAG_TYPES,
    TAG_ONLY_ENTITY_TYPES,
    EntityType,
    entity_type_in_clause,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCAN_DIRS = (_REPO_ROOT / "src" / "chronovista", _REPO_ROOT / "scripts")


def _py_files() -> Iterator[Path]:
    # Alembic migrations are frozen historical snapshots: they legitimately carry the
    # literal CHECK SQL that was applied to the DB and must never be regenerated, so they
    # are out of scope for a guard about *live* code structure.
    for base in _SCAN_DIRS:
        for path in base.rglob("*.py"):
            parts = path.parts
            if "__pycache__" in parts or "migrations" in parts:
                continue
            yield path


def _sequence_regex(quote: str) -> re.Pattern[str]:
    """Match the canonical entity-producing values, in order, with the given quote char.

    Whitespace/newlines between values are allowed, so it matches both a Python tuple
    laid out one value per line and an inline comma-separated list.
    """
    body = r"\s*,\s*".join(
        f"{quote}{re.escape(v)}{quote}" for v in ENTITY_PRODUCING_TYPES
    )
    return re.compile(body)


def test_producing_value_sequence_has_exactly_one_home() -> None:
    """The ordered value sequence appears as a double-quoted literal in exactly one file.

    That one file is ``enums.py`` (the canonical tuple). Re-inlining the list anywhere else
    — e.g. restoring a literal ``_ENTITY_PRODUCING_TYPES = {...}`` set — makes this 2+ and
    fails, which is the reviewable signal.
    """
    pattern = _sequence_regex('"')
    homes = [
        str(path.relative_to(_REPO_ROOT))
        for path in _py_files()
        if pattern.search(path.read_text(encoding="utf-8"))
    ]
    assert homes == ["src/chronovista/models/enums.py"], (
        "The entity-type value list must be spelled out in exactly one place "
        f"(enums.ENTITY_PRODUCING_TYPES); found it in: {homes}"
    )


def test_check_constraint_sql_is_never_hardcoded() -> None:
    """No module hardcodes the ``IN ('person', ...)`` CHECK SQL — it must be generated.

    Exact-count (zero) rather than a growable allowlist: the three CHECK constraints must
    call ``entity_type_in_clause()``. A re-hardcoded constraint string (the migration-051
    trap) makes this non-empty and fails.
    """
    pattern = re.compile(r"IN \(\s*" + _sequence_regex("'").pattern)
    offenders = [
        str(path.relative_to(_REPO_ROOT))
        for path in _py_files()
        if pattern.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == [], (
        "A module hardcoded the entity-type CHECK SQL instead of calling "
        "entity_type_in_clause(); offenders: " + ", ".join(offenders)
    )


def test_canonical_lists_match_the_enum() -> None:
    """The ordered tuples and the ``EntityType`` enum cannot drift apart."""
    assert set(ENTITY_TAG_TYPES) == {e.value for e in EntityType}
    assert set(ENTITY_PRODUCING_TYPES) == set(ENTITY_TAG_TYPES) - set(
        TAG_ONLY_ENTITY_TYPES
    )
    # Ordered, no duplicates, tag-only appended last (the byte-stability contract).
    assert ENTITY_TAG_TYPES == ENTITY_PRODUCING_TYPES + TAG_ONLY_ENTITY_TYPES
    assert len(set(ENTITY_TAG_TYPES)) == len(ENTITY_TAG_TYPES)


def test_generated_check_sql_is_byte_identical_to_history() -> None:
    """Pin the exact SQL the live migrations produced, so a reorder can't slip through.

    If this fails, the generated ``CheckConstraint`` strings differ textually from what the
    database already holds, and ``alembic revision --autogenerate`` will propose a spurious
    drop-and-recreate of all three constraints (and the integration DB, built via
    ``create_all``, drifts from prod).
    """
    assert entity_type_in_clause("entity_type", include_tag_only=False) == (
        "entity_type IN ('person', 'organization', 'place', 'event', 'work', "
        "'technical_term', 'concept', 'other')"
    )
    assert entity_type_in_clause("entity_type", include_tag_only=True) + (
        " OR entity_type IS NULL"
    ) == (
        "entity_type IN ('person', 'organization', 'place', 'event', 'work', "
        "'technical_term', 'concept', 'other', 'topic', 'descriptor') OR entity_type IS NULL"
    )
    assert entity_type_in_clause("type_hint", include_tag_only=False) == (
        "type_hint IN ('person', 'organization', 'place', 'event', 'work', "
        "'technical_term', 'concept', 'other')"
    )
