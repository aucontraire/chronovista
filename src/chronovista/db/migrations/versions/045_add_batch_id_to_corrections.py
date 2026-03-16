"""add batch_id column to transcript_corrections

Revision ID: e5f7a9b1c3d8
Revises: d4e6f0a2c8b5
Create Date: 2026-03-15 12:00:00.000000

Add a nullable batch_id UUID column to transcript_corrections to support
batch-level grouping of corrections (Feature 045: Correction Intelligence
Pipeline).

Changes to transcript_corrections:
1. batch_id UUID — nullable FK-free column that groups corrections applied
   together in a single batch operation. NULL for corrections that were not
   part of a batch run.

New index:
- ix_transcript_corrections_batch_id on transcript_corrections.batch_id
  (partial index on non-NULL values for efficient batch lookups)

All operations are fully reversible via downgrade().

Related: Feature 045 (Correction Intelligence Pipeline), ADR-005 Increment 8
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = "e5f7a9b1c3d8"
down_revision = "d4e6f0a2c8b5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Add batch_id column and partial index to transcript_corrections.

    Operations performed:
    1. ADD transcript_corrections.batch_id (UUID, nullable)
    2. ADD partial index ix_transcript_corrections_batch_id WHERE batch_id IS NOT NULL
    """

    # =========================================================================
    # 1. transcript_corrections: add batch_id UUID column (nullable)
    # =========================================================================
    op.add_column(
        "transcript_corrections",
        sa.Column(
            "batch_id",
            UUID(as_uuid=True),
            nullable=True,
        ),
    )

    # =========================================================================
    # 2. ADD partial B-tree index on batch_id (non-NULL values only)
    # =========================================================================
    op.create_index(
        "ix_transcript_corrections_batch_id",
        "transcript_corrections",
        ["batch_id"],
        unique=False,
        postgresql_where=sa.text("batch_id IS NOT NULL"),
    )


def downgrade() -> None:
    """
    Reverse the batch_id addition.

    Operations performed in reverse dependency order:
    1. DROP index ix_transcript_corrections_batch_id
    2. DROP transcript_corrections.batch_id
    """

    # =========================================================================
    # 1. DROP partial index on batch_id
    # =========================================================================
    op.drop_index(
        "ix_transcript_corrections_batch_id",
        table_name="transcript_corrections",
        postgresql_where=sa.text("batch_id IS NOT NULL"),
    )

    # =========================================================================
    # 2. DROP batch_id column
    # =========================================================================
    op.drop_column("transcript_corrections", "batch_id")
