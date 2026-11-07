"""feat(relationships): novel-relationship candidate queue tables

Creates ``relationship_candidates`` (one row per canonically ordered entity
pair) and ``relationship_candidate_generation_runs`` (per-run provenance).
Schema-only; no data migration. ``review_status`` stays a nullable varchar --
its allowed values are enforced application-side.

Revision ID: e2b8d4f6a1c9
Revises: d9a4b7c2e6f3
Create Date: 2026-11-07

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "e2b8d4f6a1c9"
down_revision = "d9a4b7c2e6f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "relationship_candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "entity_a_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("named_entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "entity_b_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("named_entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("channel", sa.String(30), nullable=False),
        sa.Column("shared_video_count", sa.Integer(), nullable=False),
        sa.Column("lift", sa.Float(), nullable=False),
        sa.Column("entity_a_video_count", sa.Integer(), nullable=False),
        sa.Column("entity_b_video_count", sa.Integer(), nullable=False),
        sa.Column("channel_video_universe", sa.Integer(), nullable=False),
        sa.Column(
            "both_typed_eligible",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "kb_corroboration_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "kb_corroboration_detail",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "provenance",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("review_status", sa.String(30), nullable=True),
        sa.Column("review_taxonomy_version", sa.String(30), nullable=True),
        sa.Column("review_pass_logged_rejections", sa.Boolean(), nullable=True),
        sa.Column("reviewed_by", sa.String(255), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "last_generated_at",
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
        sa.UniqueConstraint("entity_a_id", "entity_b_id", name="uq_relationship_pair"),
        sa.CheckConstraint(
            "entity_a_id <> entity_b_id", name="chk_relationship_no_self_pair"
        ),
        sa.CheckConstraint(
            "entity_a_id < entity_b_id", name="chk_relationship_canonical_order"
        ),
        sa.CheckConstraint(
            "shared_video_count >= 5", name="chk_relationship_shared_min"
        ),
        sa.CheckConstraint("lift >= 5", name="chk_relationship_lift_min"),
    )
    op.create_index(
        "idx_relationship_candidates_lift",
        "relationship_candidates",
        [sa.text("lift DESC")],
    )
    op.create_index(
        "idx_relationship_candidates_entity_a",
        "relationship_candidates",
        ["entity_a_id"],
    )
    op.create_index(
        "idx_relationship_candidates_entity_b",
        "relationship_candidates",
        ["entity_b_id"],
    )

    op.create_table(
        "relationship_candidate_generation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("channel", sa.String(30), nullable=False),
        sa.Column(
            "channel_video_universe",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "corpus_size", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "candidates_written",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "candidates_removed",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("generator_version", sa.String(50), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'failed')",
            name="chk_relationship_generation_run_status_valid",
        ),
    )
    op.create_index(
        "uq_relationship_generation_runs_active",
        "relationship_candidate_generation_runs",
        ["channel"],
        unique=True,
        postgresql_where=sa.text("status = 'running'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_relationship_generation_runs_active",
        table_name="relationship_candidate_generation_runs",
    )
    op.drop_table("relationship_candidate_generation_runs")
    op.drop_index(
        "idx_relationship_candidates_entity_b", table_name="relationship_candidates"
    )
    op.drop_index(
        "idx_relationship_candidates_entity_a", table_name="relationship_candidates"
    )
    op.drop_index(
        "idx_relationship_candidates_lift", table_name="relationship_candidates"
    )
    op.drop_table("relationship_candidates")
