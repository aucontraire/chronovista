"""add_video_categories_table_and_video_category_id

Revision ID: 8d541f1dd05e
Revises: 8946f611cef1
Create Date: 2026-01-04 13:19:02.045582

"""

from __future__ import annotations

import sqlalchemy as sa


from alembic import op

# revision identifiers, used by Alembic.
revision = "8d541f1dd05e"
down_revision = "8946f611cef1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Upgrade database schema."""
    # Create video_categories table
    op.create_table(
        "video_categories",
        sa.Column("category_id", sa.String(10), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column(
            "assignable",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # Add category_id column to videos table
    op.add_column(
        "videos", sa.Column("category_id", sa.String(10), nullable=True)
    )

    # Add foreign key constraint
    op.create_foreign_key(
        "fk_videos_category_id",
        "videos",
        "video_categories",
        ["category_id"],
        ["category_id"],
    )


def downgrade() -> None:
    """Downgrade database schema."""
    # Drop foreign key constraint
    op.drop_constraint("fk_videos_category_id", "videos", type_="foreignkey")

    # Drop category_id column from videos table
    op.drop_column("videos", "category_id")

    # Drop video_categories table
    op.drop_table("video_categories")
