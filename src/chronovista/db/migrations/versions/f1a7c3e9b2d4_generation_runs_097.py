"""add candidate_generation_runs table (Feature 097)

Durable status + determinate progress for a background candidate generation
sweep. A partial unique index on ``(source_channel) WHERE status='running'``
enforces at most one active run per channel (FR-024); ``updated_at`` is the
heartbeat used to detect a stale run (FR-025). Kept in lockstep with the
``CandidateGenerationRun`` ORM model in ``db/models.py``. No data migration,
no CREATE EXTENSION; UUIDv7 PKs are generated Python-side.

Revision ID: f1a7c3e9b2d4
Revises: e20c6f3bfc1d
Create Date: 2026-10-28

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "f1a7c3e9b2d4"
down_revision = "e20c6f3bfc1d"
branch_labels = None
depends_on = None

_TABLE = "candidate_generation_runs"


def upgrade() -> None:
    """Upgrade database schema."""
    op.create_table(
        _TABLE,
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "source_channel",
            sa.String(length=30),
            server_default="relation",
            nullable=False,
        ),
        sa.Column(
            "status", sa.String(length=20), server_default="running", nullable=False
        ),
        sa.Column(
            "progress_percent",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "seeds_grounded", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "candidates_discovered",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "candidates_upserted",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "superseded", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "pending_total", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "by_triage",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("empty_reason", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'failed')",
            name="chk_candidate_generation_run_status_valid",
        ),
        sa.CheckConstraint(
            "progress_percent BETWEEN 0 AND 100",
            name="chk_candidate_generation_run_progress_range",
        ),
        sa.CheckConstraint(
            "source_channel IN ('relation', 'tag_seed', 'category')",
            name="chk_candidate_generation_run_channel_valid",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_candidate_generation_runs_active",
        _TABLE,
        ["source_channel"],
        unique=True,
        postgresql_where=sa.text("status = 'running'"),
    )
    op.create_index(
        "idx_candidate_generation_runs_status_updated",
        _TABLE,
        ["status", "updated_at"],
    )


def downgrade() -> None:
    """Downgrade database schema."""
    op.drop_index("idx_candidate_generation_runs_status_updated", table_name=_TABLE)
    op.drop_index("uq_candidate_generation_runs_active", table_name=_TABLE)
    op.drop_table(_TABLE)
