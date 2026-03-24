"""add_concept_other_entity_types — extend entity_type CHECK constraints

Revision ID: a1b3c5d7e9f2
Revises: f6a8c0b2d4e9
Create Date: 2026-03-23 12:00:00.000000

This is a schema-only migration — no data migration is required.

The goal is to widen the allowed values for the ``entity_type`` column on two
tables so that new entity classifications ('concept' and 'other') are accepted
by the database.

Changes to named_entities:
- DROP   chk_entity_type_valid (old — 6 values)
- ADD    chk_entity_type_valid (new — 8 values, adds 'concept' and 'other')

Changes to canonical_tags:
- DROP   chk_canonical_tag_entity_type_valid (old — 8 values + IS NULL)
- ADD    chk_canonical_tag_entity_type_valid (new — 10 values + IS NULL,
         adds 'concept' and 'other')

Constraint expressions (kept as module-level constants so upgrade/downgrade
stay in sync with each other and with db/models.py):

named_entities — old:
    entity_type IN ('person', 'organization', 'place', 'event', 'work',
                    'technical_term')

named_entities — new:
    entity_type IN ('person', 'organization', 'place', 'event', 'work',
                    'technical_term', 'concept', 'other')

canonical_tags — old:
    entity_type IN ('person', 'organization', 'place', 'event', 'work',
                    'technical_term', 'topic', 'descriptor')
    OR entity_type IS NULL

canonical_tags — new:
    entity_type IN ('person', 'organization', 'place', 'event', 'work',
                    'technical_term', 'concept', 'other', 'topic',
                    'descriptor')
    OR entity_type IS NULL

All operations are fully reversible via downgrade().

Related: Feature 051 (Concept/Other Entity Types), ADR-006
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "a1b3c5d7e9f2"
down_revision = "f6a8c0b2d4e9"
branch_labels = None
depends_on = None

# ---------------------------------------------------------------------------
# named_entities — chk_entity_type_valid
# ---------------------------------------------------------------------------
_NAMED_ENTITY_TYPE_CHECK_OLD = (
    "entity_type IN ("
    "'person', 'organization', 'place', 'event', 'work', 'technical_term'"
    ")"
)
_NAMED_ENTITY_TYPE_CHECK_NEW = (
    "entity_type IN ("
    "'person', 'organization', 'place', 'event', 'work', 'technical_term', "
    "'concept', 'other'"
    ")"
)

# ---------------------------------------------------------------------------
# canonical_tags — chk_canonical_tag_entity_type_valid
# ---------------------------------------------------------------------------
_CANONICAL_TAG_ENTITY_TYPE_CHECK_OLD = (
    "entity_type IN ("
    "'person', 'organization', 'place', 'event', 'work', 'technical_term', "
    "'topic', 'descriptor'"
    ") OR entity_type IS NULL"
)
_CANONICAL_TAG_ENTITY_TYPE_CHECK_NEW = (
    "entity_type IN ("
    "'person', 'organization', 'place', 'event', 'work', 'technical_term', "
    "'concept', 'other', 'topic', 'descriptor'"
    ") OR entity_type IS NULL"
)


def upgrade() -> None:
    """
    Widen the entity_type CHECK constraints on named_entities and canonical_tags
    to include 'concept' and 'other'.

    Operations performed (in dependency order):
    1. DROP chk_entity_type_valid on named_entities (old — 6 values)
    2. ADD  chk_entity_type_valid on named_entities (new — 8 values)
    3. DROP chk_canonical_tag_entity_type_valid on canonical_tags (old — 8 values)
    4. ADD  chk_canonical_tag_entity_type_valid on canonical_tags (new — 10 values)
    """

    # =========================================================================
    # 1. DROP old named_entities CHECK constraint
    # =========================================================================
    op.drop_constraint(
        "chk_entity_type_valid",
        "named_entities",
        type_="check",
    )

    # =========================================================================
    # 2. ADD new named_entities CHECK constraint (includes 'concept', 'other')
    # =========================================================================
    op.create_check_constraint(
        "chk_entity_type_valid",
        "named_entities",
        _NAMED_ENTITY_TYPE_CHECK_NEW,
    )

    # =========================================================================
    # 3. DROP old canonical_tags CHECK constraint
    # =========================================================================
    op.drop_constraint(
        "chk_canonical_tag_entity_type_valid",
        "canonical_tags",
        type_="check",
    )

    # =========================================================================
    # 4. ADD new canonical_tags CHECK constraint (includes 'concept', 'other')
    # =========================================================================
    op.create_check_constraint(
        "chk_canonical_tag_entity_type_valid",
        "canonical_tags",
        _CANONICAL_TAG_ENTITY_TYPE_CHECK_NEW,
    )


def downgrade() -> None:
    """
    Restore the original (narrower) entity_type CHECK constraints on both tables.

    Operations performed in reverse dependency order:
    1. DROP new chk_canonical_tag_entity_type_valid on canonical_tags
    2. ADD  old chk_canonical_tag_entity_type_valid on canonical_tags
    3. DROP new chk_entity_type_valid on named_entities
    4. ADD  old chk_entity_type_valid on named_entities

    WARNING: Any rows that have entity_type = 'concept' or entity_type = 'other'
    will violate the restored CHECK constraints.  Delete or reclassify those rows
    before running this downgrade in production environments.
    """

    # =========================================================================
    # 1. DROP new canonical_tags CHECK constraint
    # =========================================================================
    op.drop_constraint(
        "chk_canonical_tag_entity_type_valid",
        "canonical_tags",
        type_="check",
    )

    # =========================================================================
    # 2. ADD old canonical_tags CHECK constraint (without 'concept', 'other')
    # =========================================================================
    op.create_check_constraint(
        "chk_canonical_tag_entity_type_valid",
        "canonical_tags",
        _CANONICAL_TAG_ENTITY_TYPE_CHECK_OLD,
    )

    # =========================================================================
    # 3. DROP new named_entities CHECK constraint
    # =========================================================================
    op.drop_constraint(
        "chk_entity_type_valid",
        "named_entities",
        type_="check",
    )

    # =========================================================================
    # 4. ADD old named_entities CHECK constraint (without 'concept', 'other')
    # =========================================================================
    op.create_check_constraint(
        "chk_entity_type_valid",
        "named_entities",
        _NAMED_ENTITY_TYPE_CHECK_OLD,
    )
