"""feat(channels): channel_ownership_assertions table

Creates ``channel_ownership_assertions`` -- user-asserted "entity operates
channel" links (Feature 109). Schema-only; no data migration. ``channel_id`` has
NO foreign key by design: external and defunct channels are the point.

Revision ID: a7d3e9c1f5b2
Revises: f3c7a1d9b5e2
Create Date: 2026-11-10

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "a7d3e9c1f5b2"
down_revision = "f3c7a1d9b5e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "channel_ownership_assertions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "entity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("named_entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("channel_id", sa.String(24), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "asserted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
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
        sa.UniqueConstraint(
            "entity_id", "channel_id", name="uq_channel_ownership_assertions"
        ),
        comment=(
            "User-asserted channel ownership (Feature 109): the DECIDED-space "
            "complement to imported P2397; no FK to channels by design (external/defunct "
            "channels). Never write these into named_entities.properties."
        ),
    )
    op.create_index(
        "idx_channel_ownership_assertions_channel",
        "channel_ownership_assertions",
        ["channel_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_channel_ownership_assertions_channel",
        table_name="channel_ownership_assertions",
    )
    op.drop_table("channel_ownership_assertions")
