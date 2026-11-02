"""feat(entities): add product entity type to check constraints (103)

Widens three entity-type CHECK constraints so the new ``'product'`` value is
accepted: ``chk_entity_type_valid`` (named_entities),
``chk_canonical_tag_entity_type_valid`` (canonical_tags) and
``chk_candidate_type_hint_valid`` (candidate_suggestions). Migration 051 only
covered the first two because candidate_suggestions did not yet exist.

The upgrade renders its SQL from ``entity_type_in_clause`` so it can never drift
from ``db/models.py``. The downgrade spells the pre-``product`` lists out
explicitly so it remains a true inverse. Schema-only; no data migration.

Revision ID: b4d8f2a6c0e1
Revises: f1a7c3e9b2d4
Create Date: 2026-11-02

"""

from __future__ import annotations

from alembic import op

from chronovista.models.enums import entity_type_in_clause

# revision identifiers, used by Alembic.
revision = "b4d8f2a6c0e1"
down_revision = "f1a7c3e9b2d4"
branch_labels = None
depends_on = None

# (constraint name, table, column, include_tag_only)
_CONSTRAINTS = (
    ("chk_entity_type_valid", "named_entities", "entity_type", False),
    ("chk_canonical_tag_entity_type_valid", "canonical_tags", "entity_type", True),
    ("chk_candidate_type_hint_valid", "candidate_suggestions", "type_hint", False),
)

_OLD_PRODUCING = (
    "'person', 'organization', 'place', 'event', 'work', "
    "'technical_term', 'concept', 'other'"
)
_OLD_TAG_INCLUSIVE = _OLD_PRODUCING + ", 'topic', 'descriptor'"


def upgrade() -> None:
    """Rebuild all three constraints from the current (product-inclusive) enums."""
    for name, table, column, include_tag_only in _CONSTRAINTS:
        op.drop_constraint(name, table, type_="check")
        op.create_check_constraint(
            name,
            table,
            entity_type_in_clause(column, include_tag_only=include_tag_only),
        )


def downgrade() -> None:
    """Restore the pre-``product`` constraints.

    Rows with ``'product'`` will violate the restored constraints; reclassify
    or delete them first.
    """
    for name, table, column, include_tag_only in _CONSTRAINTS:
        values = _OLD_TAG_INCLUSIVE if include_tag_only else _OLD_PRODUCING
        op.drop_constraint(name, table, type_="check")
        op.create_check_constraint(name, table, f"{column} IN ({values})")
