"""add entity_video_exclusions table (Feature 091)

Additive: one new table (the per-(entity, video) exclusion / negative association),
no changes to existing tables or data.

Revision ID: 7e2d9c4fb118
Revises: dbafc4bfee3a
Create Date: 2026-10-23 00:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "7e2d9c4fb118"
down_revision = "dbafc4bfee3a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Upgrade database schema."""
    op.create_table(
        "entity_video_exclusions",
        sa.Column("entity_id", sa.UUID(), nullable=False),
        sa.Column("video_id", sa.String(length=20), nullable=False),
        sa.Column("excluded_by", sa.String(length=100), nullable=False),
        sa.Column(
            "excluded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["entity_id"], ["named_entities.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["video_id"], ["videos.video_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("entity_id", "video_id"),
    )


def downgrade() -> None:
    """Downgrade database schema."""
    op.drop_table("entity_video_exclusions")
