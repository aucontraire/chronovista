"""feat(channels): channel_principals table

Creates ``channel_principals`` -- channel-level principal (host / cast) links.
Schema-only; no data migration. ``decision`` stays a nullable varchar -- its
vocabulary is enforced application-side.

Revision ID: f3c7a1d9b5e2
Revises: e2b8d4f6a1c9
Create Date: 2026-11-10

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "f3c7a1d9b5e2"
down_revision = "e2b8d4f6a1c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "channel_principals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "channel_id",
            sa.String(24),
            sa.ForeignKey("channels.channel_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "entity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("named_entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("wikidata_linked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("derived_generator_version", sa.String(30), nullable=True),
        sa.Column("tag_credited_count", sa.Integer(), nullable=True),
        sa.Column("text_credited_count", sa.Integer(), nullable=True),
        sa.Column("checkable_video_count", sa.Integer(), nullable=True),
        sa.Column("spoken_video_count", sa.Integer(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision", sa.String(20), nullable=True),
        sa.Column("decided_reason", sa.Text(), nullable=True),
        sa.Column("first_seen", sa.Date(), nullable=True),
        sa.Column("last_seen", sa.Date(), nullable=True),
        sa.Column("through", sa.Date(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("channel_id", "entity_id", name="uq_channel_principals"),
        comment=(
            "Channel cast (DESIGN-CHANNEL-PRINCIPALS): channel-level principal "
            "links; never materialise per-video mentions from these."
        ),
    )
    op.create_index(
        "idx_channel_principals_channel", "channel_principals", ["channel_id"]
    )
    op.create_index(
        "idx_channel_principals_entity", "channel_principals", ["entity_id"]
    )
    op.create_index(
        "idx_channel_principals_current",
        "channel_principals",
        ["channel_id"],
        postgresql_where=sa.text("decision = 'cast' AND through IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_channel_principals_current", table_name="channel_principals")
    op.drop_index("idx_channel_principals_entity", table_name="channel_principals")
    op.drop_index("idx_channel_principals_channel", table_name="channel_principals")
    op.drop_table("channel_principals")
