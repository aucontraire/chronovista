"""add app_identities singleton table

Revision ID: e6f1a2b3c4d5
Revises: d5f9a2c7b1e8
Create Date: 2026-08-02 00:00:00.000000

Creates the singleton ``app_identities`` table (Feature 060) that persists the
canonical local-user identity. Only one row may ever exist (enforced by
``CHECK (id = 1)``). No existing table is altered — this is a pure additive
migration.

New Tables:
1. app_identities — one row holding the resolved canonical ``user_id`` and its
   ``source`` (``channel`` | ``local_constant``).

Related: Feature 060 (Canonical User Identity), Task T004
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "e6f1a2b3c4d5"
down_revision = "d5f9a2c7b1e8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the app_identities singleton table."""
    op.create_table(
        "app_identities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.String(50), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_app_identities"),
        sa.UniqueConstraint("user_id", name="uq_app_identities_user_id"),
        sa.CheckConstraint("id = 1", name="chk_app_identities_singleton"),
    )


def downgrade() -> None:
    """Drop the app_identities table."""
    op.drop_table("app_identities")
