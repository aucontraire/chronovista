"""add entity-aware corrections schema changes

Revision ID: d4e6f0a2c8b5
Revises: c3f5a7b9d1e6
Create Date: 2026-03-13 12:00:00.000000

This migration extends the entity mentions and named entities tables to support
entity-aware correction workflows (Feature 043).

Changes to named_entities:
1. exclusion_patterns JSONB column — stores patterns that should NOT match this
   entity (e.g. common homographs). Defaults to empty array.

Changes to entity_mentions:
1. match_start Integer — character offset of the match within the segment text
2. match_end Integer   — character offset of the end of the match
3. correction_id UUID  — optional FK to transcript_corrections.id; links the
   mention to the correction that triggered or confirmed it (ON DELETE SET NULL)

Constraint changes on entity_mentions:
- DROP uq_entity_mention_entity_segment_text (entity_id, segment_id, mention_text)
- ADD  uq_entity_mention_entity_segment_position (entity_id, segment_id, match_start)
  Rationale: two different corrections can produce the same mention_text at
  different positions; uniqueness on position is more precise.

- DROP chk_entity_mention_detection_method_valid (old — missing 'user_correction')
- ADD  chk_entity_mention_detection_method_valid (new — includes 'user_correction')

New index:
- ix_entity_mentions_correction_id on entity_mentions.correction_id

All operations are fully reversible via downgrade().

Related: Feature 043 (Entity-Aware Corrections), ADR-006 Increment C
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision = "d4e6f0a2c8b5"
down_revision = "c3f5a7b9d1e6"
branch_labels = None
depends_on = None

# Check constraint expression strings — kept as constants so upgrade/downgrade
# stay in sync with each other and with db/models.py.
_OLD_DETECTION_METHOD_CHECK = (
    "detection_method IN ('rule_match', 'spacy_ner', 'llm_extraction', 'manual')"
)
_NEW_DETECTION_METHOD_CHECK = (
    "detection_method IN ("
    "'rule_match', 'spacy_ner', 'llm_extraction', 'manual', 'user_correction'"
    ")"
)


def upgrade() -> None:
    """
    Apply all entity-aware correction schema changes.

    Operations performed (in dependency order):
    1. ADD named_entities.exclusion_patterns (JSONB, NOT NULL, default '[]')
    2. ADD entity_mentions.match_start (Integer, nullable)
    3. ADD entity_mentions.match_end (Integer, nullable)
    4. ADD entity_mentions.correction_id (UUID, nullable, FK -> transcript_corrections)
    5. DROP unique constraint uq_entity_mention_entity_segment_text
    6. ADD unique constraint uq_entity_mention_entity_segment_position
    7. DROP check constraint chk_entity_mention_detection_method_valid (old)
    8. ADD check constraint chk_entity_mention_detection_method_valid (new + user_correction)
    9. ADD index ix_entity_mentions_correction_id
    """

    # =========================================================================
    # 1. named_entities: add exclusion_patterns JSONB column
    # =========================================================================
    op.add_column(
        "named_entities",
        sa.Column(
            "exclusion_patterns",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )

    # =========================================================================
    # 2. entity_mentions: add match_start Integer column
    # =========================================================================
    op.add_column(
        "entity_mentions",
        sa.Column("match_start", sa.Integer(), nullable=True),
    )

    # =========================================================================
    # 3. entity_mentions: add match_end Integer column
    # =========================================================================
    op.add_column(
        "entity_mentions",
        sa.Column("match_end", sa.Integer(), nullable=True),
    )

    # =========================================================================
    # 4. entity_mentions: add correction_id UUID FK -> transcript_corrections.id
    # =========================================================================
    op.add_column(
        "entity_mentions",
        sa.Column(
            "correction_id",
            UUID(as_uuid=True),
            sa.ForeignKey("transcript_corrections.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    # =========================================================================
    # 5. DROP old unique constraint (entity_id, segment_id, mention_text)
    # =========================================================================
    op.drop_constraint(
        "uq_entity_mention_entity_segment_text",
        "entity_mentions",
        type_="unique",
    )

    # =========================================================================
    # 6. ADD new unique constraint (entity_id, segment_id, match_start)
    # =========================================================================
    op.create_unique_constraint(
        "uq_entity_mention_entity_segment_position",
        "entity_mentions",
        ["entity_id", "segment_id", "match_start"],
    )

    # =========================================================================
    # 7. DROP old check constraint (missing 'user_correction')
    # =========================================================================
    op.drop_constraint(
        "chk_entity_mention_detection_method_valid",
        "entity_mentions",
        type_="check",
    )

    # =========================================================================
    # 8. ADD new check constraint (includes 'user_correction')
    # =========================================================================
    op.create_check_constraint(
        "chk_entity_mention_detection_method_valid",
        "entity_mentions",
        _NEW_DETECTION_METHOD_CHECK,
    )

    # =========================================================================
    # 9. ADD index on correction_id for FK lookup performance
    # =========================================================================
    op.create_index(
        "ix_entity_mentions_correction_id",
        "entity_mentions",
        ["correction_id"],
        unique=False,
    )


def downgrade() -> None:
    """
    Reverse all entity-aware correction schema changes.

    Operations performed in reverse dependency order:
    1. DROP index ix_entity_mentions_correction_id
    2. DROP check constraint chk_entity_mention_detection_method_valid (new)
    3. ADD check constraint chk_entity_mention_detection_method_valid (old)
    4. DROP unique constraint uq_entity_mention_entity_segment_position
    5. ADD unique constraint uq_entity_mention_entity_segment_text (restored)
    6. DROP entity_mentions.correction_id
    7. DROP entity_mentions.match_end
    8. DROP entity_mentions.match_start
    9. DROP named_entities.exclusion_patterns

    WARNING: Rows whose match_start differs but mention_text is identical will
    violate the restored unique constraint. Deduplicate before downgrading if
    such rows exist.
    """

    # =========================================================================
    # 1. DROP index on correction_id
    # =========================================================================
    op.drop_index(
        "ix_entity_mentions_correction_id",
        table_name="entity_mentions",
    )

    # =========================================================================
    # 2. DROP new check constraint (includes 'user_correction')
    # =========================================================================
    op.drop_constraint(
        "chk_entity_mention_detection_method_valid",
        "entity_mentions",
        type_="check",
    )

    # =========================================================================
    # 3. ADD old check constraint (without 'user_correction')
    # =========================================================================
    op.create_check_constraint(
        "chk_entity_mention_detection_method_valid",
        "entity_mentions",
        _OLD_DETECTION_METHOD_CHECK,
    )

    # =========================================================================
    # 4. DROP new unique constraint (entity_id, segment_id, match_start)
    # =========================================================================
    op.drop_constraint(
        "uq_entity_mention_entity_segment_position",
        "entity_mentions",
        type_="unique",
    )

    # =========================================================================
    # 5. ADD original unique constraint (entity_id, segment_id, mention_text)
    # =========================================================================
    op.create_unique_constraint(
        "uq_entity_mention_entity_segment_text",
        "entity_mentions",
        ["entity_id", "segment_id", "mention_text"],
    )

    # =========================================================================
    # 6. DROP entity_mentions.correction_id
    # =========================================================================
    op.drop_column("entity_mentions", "correction_id")

    # =========================================================================
    # 7. DROP entity_mentions.match_end
    # =========================================================================
    op.drop_column("entity_mentions", "match_end")

    # =========================================================================
    # 8. DROP entity_mentions.match_start
    # =========================================================================
    op.drop_column("entity_mentions", "match_start")

    # =========================================================================
    # 9. DROP named_entities.exclusion_patterns
    # =========================================================================
    op.drop_column("named_entities", "exclusion_patterns")
