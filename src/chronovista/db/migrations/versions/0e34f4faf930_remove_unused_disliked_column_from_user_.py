"""remove_unused_disliked_column_from_user_videos

Revision ID: 0e34f4faf930
Revises: 460ab8982ba4
Create Date: 2026-01-08 22:22:02.127737

"""

from __future__ import annotations

import sqlalchemy as sa


from alembic import op

# revision identifiers, used by Alembic.
revision = "0e34f4faf930"
down_revision = "460ab8982ba4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Remove unused disliked column from user_videos table.

    The disliked column was never populated because YouTube removed the dislike
    count from their API and Google Takeout does not provide dislike history.
    This column serves no purpose and is being removed to simplify the schema.
    """
    op.drop_column("user_videos", "disliked")


def downgrade() -> None:
    """Restore disliked column to user_videos table."""
    op.add_column(
        "user_videos",
        sa.Column("disliked", sa.Boolean(), nullable=True, server_default=sa.false()),
    )
