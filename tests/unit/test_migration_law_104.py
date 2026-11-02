"""Feature 104 migration ``c7e3a9d1f5b2`` is internally correct (mirrors the 103 G4 guard).

The integration DB is built from the models via ``create_all``, so the migration's own SQL is
never exercised there. This reads the migration module directly and pins its contract against the
single source. No DB / Alembic run required.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from chronovista.models.enums import entity_type_in_clause

_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "src/chronovista/db/migrations/versions/c7e3a9d1f5b2_law_entity_type_104.py"
)

_EXPECTED = {
    ("chk_entity_type_valid", "named_entities", "entity_type", False),
    ("chk_canonical_tag_entity_type_valid", "canonical_tags", "entity_type", True),
    ("chk_candidate_type_hint_valid", "candidate_suggestions", "type_hint", False),
}


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("mig_c7e3a9d1f5b2", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_revision_chain() -> None:
    m = _load()
    assert m.revision == "c7e3a9d1f5b2"
    assert m.down_revision == "b4d8f2a6c0e1"


def test_covers_all_three_constraints_with_correct_mapping() -> None:
    m = _load()
    assert set(m._CONSTRAINTS) == _EXPECTED


def test_upgrade_sql_is_law_inclusive_from_single_source() -> None:
    m = _load()
    for _name, _table, column, include_tag_only in m._CONSTRAINTS:
        rendered = entity_type_in_clause(column, include_tag_only=include_tag_only)
        assert "'law'" in rendered


def test_downgrade_is_a_true_inverse_without_law_but_with_product() -> None:
    """The downgrade baseline is today's vocabulary minus `law` only — `product` is retained."""
    m = _load()
    assert "'law'" not in m._OLD_PRODUCING
    assert (
        "'product'" in m._OLD_PRODUCING
    )  # 104 downgrades to the post-103 (product-inclusive) set
    assert "'law'" not in m._OLD_TAG_INCLUSIVE
    assert m._OLD_TAG_INCLUSIVE == m._OLD_PRODUCING + ", 'topic', 'descriptor'"
    # The 104 downgrade baseline is the FIXED pre-law vocabulary (post-103: product-inclusive),
    # independent of any type added later — pinned to literals, not the live tuple.
    pre_law = {
        "person",
        "organization",
        "place",
        "event",
        "work",
        "product",
        "technical_term",
        "concept",
        "other",
    }
    old_producing = {v.strip().strip("'") for v in m._OLD_PRODUCING.split(",")}
    assert old_producing == pre_law
    assert {v.strip().strip("'") for v in m._OLD_TAG_INCLUSIVE.split(",")} == (
        pre_law | {"topic", "descriptor"}
    )
