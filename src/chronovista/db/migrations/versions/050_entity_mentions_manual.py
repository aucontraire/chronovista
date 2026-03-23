"""entity_mentions_manual — support manual entity mentions

Revision ID: f6a8c0b2d4e9
Revises: e5f7a9b1c3d8
Create Date: 2026-03-22 12:00:00.000000

This migration extends the entity_mentions table to support manually-created
entity mentions that are not tied to a specific transcript segment (Feature 050:
Manual Entity Mentions).

Changes to entity_mentions:
1. segment_id   — changed from NOT NULL to nullable (manual mentions have no
   segment; segment-based mentions continue to require a value at the
   application layer)
2. language_code — changed from NOT NULL to nullable (manual mentions may lack
   a specific language context)
3. confidence    — changed from NOT NULL to nullable (manual mentions have no
   statistical confidence; confidence is only meaningful for automated methods)

Constraint changes on entity_mentions:
- DROP uq_entity_mention_entity_segment_position
  (entity_id, segment_id, match_start) — cannot enforce when segment_id is NULL
- ADD  partial unique index uq_entity_mentions_transcript
  on (entity_id, segment_id, match_start) WHERE segment_id IS NOT NULL
  (preserves the uniqueness guarantee for automated, segment-bound mentions)
- ADD  partial unique index uq_entity_mentions_manual
  on (entity_id, video_id, detection_method) WHERE detection_method = 'manual'
  (prevents duplicate manual mentions for the same entity+video pair)

Downgrade safety:
- Manual mentions (detection_method = 'manual') are deleted before the NOT NULL
  constraints are restored.  All other rows are expected to have non-NULL values
  for segment_id, language_code, and confidence as they were inserted under the
  previous schema; the migration does NOT verify this assumption — back up data
  before downgrading in production environments.

Related: Feature 050 (Manual Entity Mentions), ADR-006 Increment D
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "f6a8c0b2d4e9"
down_revision = "e5f7a9b1c3d8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Make segment_id / language_code / confidence nullable and replace the
    non-partial unique constraint with two partial unique indexes.

    Operations performed (in dependency order):
    1. DROP unique constraint uq_entity_mention_entity_segment_position
    2. ALTER segment_id   SET NULL (drop NOT NULL)
    3. ALTER language_code SET NULL (drop NOT NULL)
    4. ALTER confidence    SET NULL (drop NOT NULL)
    5. CREATE partial unique index uq_entity_mentions_transcript
    6. CREATE partial unique index uq_entity_mentions_manual
    """

    # =========================================================================
    # 1. DROP existing unique constraint (blocks nullable segment_id)
    # =========================================================================
    op.drop_constraint(
        "uq_entity_mention_entity_segment_position",
        "entity_mentions",
        type_="unique",
    )

    # =========================================================================
    # 2. Make segment_id nullable
    # =========================================================================
    op.alter_column(
        "entity_mentions",
        "segment_id",
        existing_type=sa.Integer(),
        nullable=True,
    )

    # =========================================================================
    # 3. Make language_code nullable
    # =========================================================================
    op.alter_column(
        "entity_mentions",
        "language_code",
        existing_type=sa.String(10),
        nullable=True,
    )

    # =========================================================================
    # 4. Make confidence nullable
    # =========================================================================
    op.alter_column(
        "entity_mentions",
        "confidence",
        existing_type=sa.Float(),
        nullable=True,
    )

    # =========================================================================
    # 5. Partial unique index for segment-bound (automated) mentions
    #    Replaces the dropped unique constraint with the same semantics but
    #    restricted to rows where segment_id IS NOT NULL.
    # =========================================================================
    op.create_index(
        "uq_entity_mentions_transcript",
        "entity_mentions",
        ["entity_id", "segment_id", "match_start"],
        unique=True,
        postgresql_where=sa.text("segment_id IS NOT NULL"),
    )

    # =========================================================================
    # 6. Partial unique index for manual mentions
    #    One manual mention per (entity, video) — detection_method = 'manual'.
    # =========================================================================
    op.create_index(
        "uq_entity_mentions_manual",
        "entity_mentions",
        ["entity_id", "video_id", "detection_method"],
        unique=True,
        postgresql_where=sa.text("detection_method = 'manual'"),
    )


def downgrade() -> None:
    """
    Reverse the Feature 050 schema changes.

    Operations performed (in reverse dependency order):
    1. DELETE manual mentions (detection_method = 'manual') — they have NULL
       segment_id and cannot satisfy the restored NOT NULL constraint
    2. DROP partial unique index uq_entity_mentions_manual
    3. DROP partial unique index uq_entity_mentions_transcript
    4. ALTER confidence    SET NOT NULL
    5. ALTER language_code SET NOT NULL
    6. ALTER segment_id    SET NOT NULL
    7. RESTORE unique constraint uq_entity_mention_entity_segment_position

    WARNING: This downgrade is lossy — all manual entity mentions will be
    permanently deleted.  Take a backup before running in production.
    """

    # =========================================================================
    # 1. Remove manual mentions so the NOT NULL restore does not fail
    # =========================================================================
    op.execute(
        "DELETE FROM entity_mentions WHERE detection_method = 'manual'"
    )

    # =========================================================================
    # 2. DROP partial unique index for manual mentions
    # =========================================================================
    op.drop_index(
        "uq_entity_mentions_manual",
        table_name="entity_mentions",
    )

    # =========================================================================
    # 3. DROP partial unique index for transcript-bound mentions
    # =========================================================================
    op.drop_index(
        "uq_entity_mentions_transcript",
        table_name="entity_mentions",
    )

    # =========================================================================
    # 4. Restore confidence NOT NULL
    # =========================================================================
    op.alter_column(
        "entity_mentions",
        "confidence",
        existing_type=sa.Float(),
        nullable=False,
    )

    # =========================================================================
    # 5. Restore language_code NOT NULL
    # =========================================================================
    op.alter_column(
        "entity_mentions",
        "language_code",
        existing_type=sa.String(10),
        nullable=False,
    )

    # =========================================================================
    # 6. Restore segment_id NOT NULL
    # =========================================================================
    op.alter_column(
        "entity_mentions",
        "segment_id",
        existing_type=sa.Integer(),
        nullable=False,
    )

    # =========================================================================
    # 7. Restore original unique constraint
    # =========================================================================
    op.create_unique_constraint(
        "uq_entity_mention_entity_segment_position",
        "entity_mentions",
        ["entity_id", "segment_id", "match_start"],
    )
