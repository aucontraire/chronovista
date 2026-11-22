"""feat(proximity): transcript proximity primitive tables (Feature 116)

Additive: creates ``entity_pair_proximity`` (instance grain),
``entity_pair_proximity_rollup`` (per-pair aggregate), ``proximity_dirty_scopes``
(invalidation queue at ``(video_id, language_code)`` grain) and
``proximity_generation_runs`` (run provenance). No existing table is touched.
Segment ids are INTEGER because ``transcript_segments.id`` is an integer
autoincrement key. The downgrade drops all four tables (data is derived and
rebuildable from ``entity_mentions`` + ``transcript_segments``).

Revision ID: a9d3f6b2c481
Revises: e7a3c5d9b1f2
Create Date: 2026-11-21

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "a9d3f6b2c481"
down_revision = "e7a3c5d9b1f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "entity_pair_proximity",
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
        sa.Column(
            "video_id",
            sa.String(20),
            sa.ForeignKey("videos.video_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("language_code", sa.String(10), nullable=False),
        sa.Column(
            "segment_a_id",
            sa.Integer(),
            sa.ForeignKey("transcript_segments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "segment_b_id",
            sa.Integer(),
            sa.ForeignKey("transcript_segments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("gap_seconds", sa.Float(), nullable=False),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "entity_a_id",
            "entity_b_id",
            "video_id",
            "segment_a_id",
            "segment_b_id",
            name="uq_entity_pair_proximity_instance",
        ),
        sa.CheckConstraint(
            "entity_a_id <> entity_b_id", name="chk_entity_pair_proximity_no_self_pair"
        ),
        sa.CheckConstraint(
            "entity_a_id < entity_b_id",
            name="chk_entity_pair_proximity_canonical_order",
        ),
        sa.CheckConstraint(
            "gap_seconds >= 0", name="chk_entity_pair_proximity_gap_non_negative"
        ),
    )
    op.create_index(
        "idx_entity_pair_proximity_pair",
        "entity_pair_proximity",
        ["entity_a_id", "entity_b_id"],
    )
    op.create_index(
        "idx_entity_pair_proximity_scope",
        "entity_pair_proximity",
        ["video_id", "language_code"],
    )
    op.create_index(
        "idx_entity_pair_proximity_segment_a",
        "entity_pair_proximity",
        ["segment_a_id"],
    )
    op.create_index(
        "idx_entity_pair_proximity_segment_b",
        "entity_pair_proximity",
        ["segment_b_id"],
    )

    op.create_table(
        "entity_pair_proximity_rollup",
        sa.Column(
            "entity_a_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("named_entities.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "entity_b_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("named_entities.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("close_co_mentions_15", sa.Integer(), nullable=False),
        sa.Column("close_co_mentions_30", sa.Integer(), nullable=False),
        sa.Column("close_co_mentions_60", sa.Integer(), nullable=False),
        sa.Column("min_gap_seconds", sa.Float(), nullable=False),
        sa.Column("shared_videos", sa.Integer(), nullable=False),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "entity_a_id < entity_b_id",
            name="chk_entity_pair_proximity_rollup_canonical_order",
        ),
    )
    op.create_index(
        "idx_entity_pair_proximity_rollup_close30",
        "entity_pair_proximity_rollup",
        [sa.text("close_co_mentions_30 DESC")],
    )

    op.create_table(
        "proximity_dirty_scopes",
        sa.Column(
            "video_id",
            sa.String(20),
            sa.ForeignKey("videos.video_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("language_code", sa.String(10), primary_key=True),
        sa.Column(
            "marked_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("reason", sa.String(30), nullable=True),
    )

    op.create_table(
        "proximity_generation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column(
            "scopes_processed",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "instances_written",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "pairs_rolled_up",
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
            name="chk_proximity_generation_run_status_valid",
        ),
    )
    op.create_index(
        "uq_proximity_generation_runs_active",
        "proximity_generation_runs",
        ["status"],
        unique=True,
        postgresql_where=sa.text("status = 'running'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_proximity_generation_runs_active", table_name="proximity_generation_runs"
    )
    op.drop_table("proximity_generation_runs")
    op.drop_table("proximity_dirty_scopes")
    op.drop_index(
        "idx_entity_pair_proximity_rollup_close30",
        table_name="entity_pair_proximity_rollup",
    )
    op.drop_table("entity_pair_proximity_rollup")
    for idx in (
        "idx_entity_pair_proximity_segment_b",
        "idx_entity_pair_proximity_segment_a",
        "idx_entity_pair_proximity_scope",
        "idx_entity_pair_proximity_pair",
    ):
        op.drop_index(idx, table_name="entity_pair_proximity")
    op.drop_table("entity_pair_proximity")
