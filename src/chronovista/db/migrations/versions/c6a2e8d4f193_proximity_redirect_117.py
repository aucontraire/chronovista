"""feat(proximity): scope-state freshness, drop rollup, widen run statuses (Feature 117)

Upgrades the Feature 116 proximity tables in place. ``proximity_dirty_scopes``
(a queue of pending work, rows deleted once processed) becomes
``proximity_scope_states`` (rows persist; a scope is current when its published
records were computed from its latest ``revision`` under the current rule
version). ``marked_at`` is renamed ``invalidated_at`` and eight columns are
added for revision tracking and failure/retry bookkeeping, guarded by three
CHECK constraints. The primary-key constraint is renamed too so the schema
matches what a fresh ORM ``create_all`` produces (likewise the ``video_id`` foreign key).

``entity_pair_proximity_rollup`` and its index are dropped: the rollup is
derivable from ``entity_pair_proximity`` and is no longer stored. An index on
``entity_pair_proximity.entity_b_id`` is added for entity-scoped reads. The
``proximity_generation_runs`` status CHECK is widened with ``incomplete`` and
``abandoned``.

Downgrade: run rows in the two new statuses become ``failed``; scope-state rows
that are already current (``computed_revision`` equals ``revision`` under rule
version ``117.0``) are deleted because the legacy table only ever held pending
work; the rollup table is recreated EMPTY (schema restored, contents are
derivable). ``entity_pair_proximity`` rows are never touched.

Revision ID: c6a2e8d4f193
Revises: b4e8a1c7d305
Create Date: 2026-11-22

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "c6a2e8d4f193"
down_revision = "b4e8a1c7d305"
branch_labels = None
depends_on = None

_RUN_STATUS_CHECK = "chk_proximity_generation_run_status_valid"


def upgrade() -> None:
    op.rename_table("proximity_dirty_scopes", "proximity_scope_states")
    op.execute(
        "ALTER TABLE proximity_scope_states "
        "RENAME CONSTRAINT proximity_dirty_scopes_pkey TO proximity_scope_states_pkey"
    )
    op.execute(
        "ALTER TABLE proximity_scope_states RENAME CONSTRAINT "
        "proximity_dirty_scopes_video_id_fkey TO proximity_scope_states_video_id_fkey"
    )
    op.alter_column(
        "proximity_scope_states", "marked_at", new_column_name="invalidated_at"
    )

    op.add_column(
        "proximity_scope_states",
        sa.Column(
            "revision", sa.BigInteger(), nullable=False, server_default=sa.text("1")
        ),
    )
    op.add_column(
        "proximity_scope_states",
        sa.Column("computed_revision", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "proximity_scope_states",
        sa.Column("computed_rule_version", sa.String(50), nullable=True),
    )
    op.add_column(
        "proximity_scope_states",
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "proximity_scope_states",
        sa.Column(
            "attempts", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
    )
    op.add_column(
        "proximity_scope_states",
        sa.Column("failed_rule_version", sa.String(50), nullable=True),
    )
    op.add_column(
        "proximity_scope_states",
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "proximity_scope_states",
        sa.Column("last_error", sa.String(500), nullable=True),
    )

    op.create_check_constraint(
        "chk_proximity_scope_state_revision_positive",
        "proximity_scope_states",
        "revision >= 1",
    )
    op.create_check_constraint(
        "chk_proximity_scope_state_computed_le_revision",
        "proximity_scope_states",
        "computed_revision IS NULL OR computed_revision <= revision",
    )
    op.create_check_constraint(
        "chk_proximity_scope_state_computed_pair",
        "proximity_scope_states",
        "(computed_revision IS NULL) = (computed_rule_version IS NULL)",
    )

    op.drop_index(
        "idx_entity_pair_proximity_rollup_close30",
        table_name="entity_pair_proximity_rollup",
    )
    op.drop_table("entity_pair_proximity_rollup")

    # Entity-scoped invalidation and pair reads filter on either endpoint. The pair
    # index leads with entity_a_id, so the entity_b_id side needs its own index or
    # every alias/name-change invalidation would scan the whole record table.
    op.create_index(
        "idx_entity_pair_proximity_entity_b", "entity_pair_proximity", ["entity_b_id"]
    )

    op.drop_constraint(_RUN_STATUS_CHECK, "proximity_generation_runs", type_="check")
    op.create_check_constraint(
        _RUN_STATUS_CHECK,
        "proximity_generation_runs",
        "status IN ('running', 'completed', 'incomplete', 'failed', 'abandoned')",
    )


def downgrade() -> None:
    op.drop_index(
        "idx_entity_pair_proximity_entity_b", table_name="entity_pair_proximity"
    )
    op.execute(
        "UPDATE proximity_generation_runs SET status = 'failed' "
        "WHERE status IN ('incomplete', 'abandoned')"
    )
    op.drop_constraint(_RUN_STATUS_CHECK, "proximity_generation_runs", type_="check")
    op.create_check_constraint(
        _RUN_STATUS_CHECK,
        "proximity_generation_runs",
        "status IN ('running', 'completed', 'failed')",
    )

    # Current scopes are not pending work; the legacy table is a queue only.
    op.execute(
        "DELETE FROM proximity_scope_states "
        "WHERE computed_revision IS NOT DISTINCT FROM revision "
        "AND computed_rule_version = '117.0'"
    )

    for name in (
        "chk_proximity_scope_state_computed_pair",
        "chk_proximity_scope_state_computed_le_revision",
        "chk_proximity_scope_state_revision_positive",
    ):
        op.drop_constraint(name, "proximity_scope_states", type_="check")
    for column in (
        "last_error",
        "next_attempt_at",
        "failed_rule_version",
        "attempts",
        "computed_at",
        "computed_rule_version",
        "computed_revision",
        "revision",
    ):
        op.drop_column("proximity_scope_states", column)

    op.alter_column(
        "proximity_scope_states", "invalidated_at", new_column_name="marked_at"
    )
    op.execute(
        "ALTER TABLE proximity_scope_states "
        "RENAME CONSTRAINT proximity_scope_states_pkey TO proximity_dirty_scopes_pkey"
    )
    op.execute(
        "ALTER TABLE proximity_scope_states RENAME CONSTRAINT "
        "proximity_scope_states_video_id_fkey TO proximity_dirty_scopes_video_id_fkey"
    )
    op.rename_table("proximity_scope_states", "proximity_dirty_scopes")

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
