"""add end_segment_id to entity_mentions (cross-segment mentions, Feature 081)

Adds entity_mentions.end_segment_id, a nullable FK -> transcript_segments
(ON DELETE CASCADE). Existing rows stay NULL (single-segment mentions); the
uq_entity_mentions_transcript index is unchanged.

Revision ID: c081e5e9a1b2
Revises: abb8cf61ed36
Create Date: 2026-10-16

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "c081e5e9a1b2"
down_revision = "abb8cf61ed36"
branch_labels = None
depends_on = None

_FK_NAME = "fk_entity_mentions_end_segment_id"
_INDEX_NAME = "idx_entity_mentions_end_segment_id"


def upgrade() -> None:
    """Add the nullable end_segment_id column, FK, and index."""
    op.add_column(
        "entity_mentions",
        sa.Column("end_segment_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        _FK_NAME,
        "entity_mentions",
        "transcript_segments",
        ["end_segment_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(_INDEX_NAME, "entity_mentions", ["end_segment_id"])


def downgrade() -> None:
    """Drop the index, FK, and column."""
    op.drop_index(_INDEX_NAME, table_name="entity_mentions")
    op.drop_constraint(_FK_NAME, "entity_mentions", type_="foreignkey")
    op.drop_column("entity_mentions", "end_segment_id")
