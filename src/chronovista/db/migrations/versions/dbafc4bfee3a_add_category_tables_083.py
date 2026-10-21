"""add wikipedia_categories and entity_categories tables (Feature 083)

Additive: two new tables, no changes to existing tables or data.

Revision ID: dbafc4bfee3a
Revises: c081e5e9a1b2
Create Date: 2026-10-21 13:01:58.260847

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "dbafc4bfee3a"
down_revision = "c081e5e9a1b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Upgrade database schema."""
    op.create_table(
        "wikipedia_categories",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=500), nullable=False),
        sa.Column("global_size", sa.Integer(), nullable=True),
        sa.Column("global_size_fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(
        "idx_wikipedia_categories_global_size",
        "wikipedia_categories",
        ["global_size"],
        unique=False,
    )
    op.create_table(
        "entity_categories",
        sa.Column("entity_id", sa.UUID(), nullable=False),
        sa.Column("category_id", sa.UUID(), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("set_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["category_id"], ["wikipedia_categories.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["entity_id"], ["named_entities.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("entity_id", "category_id"),
    )
    op.create_index(
        "idx_entity_categories_category_id",
        "entity_categories",
        ["category_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade database schema."""
    op.drop_index("idx_entity_categories_category_id", table_name="entity_categories")
    op.drop_table("entity_categories")
    op.drop_index(
        "idx_wikipedia_categories_global_size", table_name="wikipedia_categories"
    )
    op.drop_table("wikipedia_categories")
