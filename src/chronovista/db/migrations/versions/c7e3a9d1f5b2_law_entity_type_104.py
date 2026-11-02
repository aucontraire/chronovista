"""feat(entities): add law entity type to check constraints (104)

Widens three entity-type CHECK constraints so the new ``'law'`` value is
accepted: ``chk_entity_type_valid`` (named_entities),
``chk_canonical_tag_entity_type_valid`` (canonical_tags) and
``chk_candidate_type_hint_valid`` (candidate_suggestions).

The upgrade renders its SQL from ``entity_type_in_clause`` so it can never drift
from ``db/models.py``. The downgrade spells the pre-``law`` lists out
explicitly so it remains a true inverse. Schema-only; no data migration.

Revision ID: c7e3a9d1f5b2
Revises: b4d8f2a6c0e1
Create Date: 2026-11-02

"""

from __future__ import annotations

from alembic import op

from chronovista.models.enums import entity_type_in_clause

# revision identifiers, used by Alembic.
revision = "c7e3a9d1f5b2"
down_revision = "b4d8f2a6c0e1"
branch_labels = None
depends_on = None

# (constraint name, table, column, include_tag_only)
_CONSTRAINTS = (
    ("chk_entity_type_valid", "named_entities", "entity_type", False),
    ("chk_canonical_tag_entity_type_valid", "canonical_tags", "entity_type", True),
    ("chk_candidate_type_hint_valid", "candidate_suggestions", "type_hint", False),
)

_OLD_PRODUCING = (
    "'person', 'organization', 'place', 'event', 'work', 'product', "
    "'technical_term', 'concept', 'other'"
)
_OLD_TAG_INCLUSIVE = _OLD_PRODUCING + ", 'topic', 'descriptor'"


def upgrade() -> None:
    """Rebuild all three constraints from the current (law-inclusive) enums."""
    for name, table, column, include_tag_only in _CONSTRAINTS:
        op.drop_constraint(name, table, type_="check")
        op.create_check_constraint(
            name,
            table,
            entity_type_in_clause(column, include_tag_only=include_tag_only),
        )


def downgrade() -> None:
    """Restore the pre-``law`` constraints.

    Rows with ``'law'`` will violate the restored constraints; reclassify
    or delete them first.
    """
    for name, table, column, include_tag_only in _CONSTRAINTS:
        values = _OLD_TAG_INCLUSIVE if include_tag_only else _OLD_PRODUCING
        op.drop_constraint(name, table, type_="check")
        op.create_check_constraint(name, table, f"{column} IN ({values})")
