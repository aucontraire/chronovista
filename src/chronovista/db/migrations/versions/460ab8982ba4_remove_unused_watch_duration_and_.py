"""remove unused watch_duration and completion_percentage columns

Revision ID: 460ab8982ba4
Revises: 2f53bd25bd96
Create Date: 2026-01-06 12:01:46.885105

"""

from __future__ import annotations

import sqlalchemy as sa


from alembic import op

# revision identifiers, used by Alembic.
revision = "460ab8982ba4"
down_revision = "2f53bd25bd96"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Remove unused watch_duration and completion_percentage columns.

    These columns were never populated because YouTube API and Google Takeout
    do not provide per-user watch duration or completion percentage data.
    """
    op.drop_column("user_videos", "watch_duration")
    op.drop_column("user_videos", "completion_percentage")


def downgrade() -> None:
    """Restore watch_duration and completion_percentage columns."""
    op.add_column(
        "user_videos",
        sa.Column("completion_percentage", sa.Float(), nullable=True),
    )
    op.add_column(
        "user_videos",
        sa.Column("watch_duration", sa.Integer(), nullable=True),
    )
