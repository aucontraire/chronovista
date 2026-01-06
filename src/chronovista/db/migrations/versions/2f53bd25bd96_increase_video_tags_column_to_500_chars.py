"""increase_video_tags_column_to_500_chars

Revision ID: 2f53bd25bd96
Revises: 481bf7ae4087
Create Date: 2026-01-05 09:52:46.615702

"""

from __future__ import annotations

import sqlalchemy as sa


from alembic import op

# revision identifiers, used by Alembic.
revision = "2f53bd25bd96"
down_revision = "481bf7ae4087"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Upgrade database schema.

    Increases the video_tags.tag column from VARCHAR(100) to VARCHAR(500)
    to accommodate YouTube tags that can exceed 100 characters.

    YouTube's total tag limit is 500 characters combined for all tags,
    so individual tags could theoretically be up to 500 chars.
    """
    op.alter_column(
        "video_tags",
        "tag",
        existing_type=sa.String(100),
        type_=sa.String(500),
        existing_nullable=False,
    )


def downgrade() -> None:
    """Downgrade database schema.

    Reverts video_tags.tag column back to VARCHAR(100).
    WARNING: This will fail if any tags exceed 100 characters.
    """
    op.alter_column(
        "video_tags",
        "tag",
        existing_type=sa.String(500),
        type_=sa.String(100),
        existing_nullable=False,
    )
