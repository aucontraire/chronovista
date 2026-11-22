"""feat(relationships): candidate signals child table -- EXPAND (Feature 116, Migration A)

Additive plus one minimal relaxation, fully reversible:

* creates ``relationship_candidate_signals`` (per-signal evidence child);
* adds ``relationship_candidates.combined_score`` (NULL; deferred to calibration);
* relaxes ONLY ``relationship_candidates.lift`` (nullable, drops
  ``chk_relationship_lift_min``); ``shared_video_count`` and its CHECK stay intact;
* COPIES (never moves) every existing row's evidence into one ``title_description``
  child. No parent column is dropped (that is the separate contract migration) and no
  verdict column is written.

Child primary keys use ``gen_random_uuid()`` (built in since PostgreSQL 13) because a
set-based copy cannot call the application-side ``uuid7``; the id is opaque.

Revision ID: b4e8a1c7d305
Revises: a9d3f6b2c481
Create Date: 2026-11-21

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "b4e8a1c7d305"
down_revision = "a9d3f6b2c481"
branch_labels = None
depends_on = None

# (child column, parent expression). Exposed so the T025 test can assert the exact set.
CHILD_COPY_COLUMNS: tuple[tuple[str, str], ...] = (
    ("candidate_id", "id"),
    ("support", "shared_video_count"),
    ("lift", "lift"),
    ("entity_a_video_count", "entity_a_video_count"),
    ("entity_b_video_count", "entity_b_video_count"),
    ("signal_universe", "channel_video_universe"),
    ("both_typed_eligible", "both_typed_eligible"),
    ("kb_corroboration_count", "kb_corroboration_count"),
    ("kb_corroboration_detail", "kb_corroboration_detail"),
    ("provenance", "provenance"),
)

CHILD_COPY_SQL = (
    "INSERT INTO relationship_candidate_signals (id, signal, "
    + ", ".join(c for c, _ in CHILD_COPY_COLUMNS)
    + ") SELECT gen_random_uuid(), 'title_description', "
    + ", ".join(p for _, p in CHILD_COPY_COLUMNS)
    + " FROM relationship_candidates WHERE channel = 'title_description'"
)


def upgrade() -> None:
    op.create_table(
        "relationship_candidate_signals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "candidate_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("relationship_candidates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("signal", sa.String(30), nullable=False),
        sa.Column("support", sa.Integer(), nullable=False),
        sa.Column("lift", sa.Float(), nullable=True),
        sa.Column("min_gap_seconds", sa.Float(), nullable=True),
        sa.Column("entity_a_video_count", sa.Integer(), nullable=False),
        sa.Column("entity_b_video_count", sa.Integer(), nullable=False),
        sa.Column("signal_universe", sa.Integer(), nullable=False),
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
        sa.UniqueConstraint("candidate_id", "signal", name="uq_candidate_signal"),
        sa.CheckConstraint(
            "(signal = 'title_description' AND lift IS NOT NULL AND lift >= 5 "
            "AND support >= 5) OR (signal = 'transcript' AND lift IS NULL "
            "AND support >= 1)",
            name="chk_candidate_signal_shape",
        ),
    )

    op.add_column(
        "relationship_candidates",
        sa.Column("combined_score", sa.Float(), nullable=True),
    )

    op.alter_column("relationship_candidates", "lift", nullable=True)
    op.drop_constraint(
        "chk_relationship_lift_min", "relationship_candidates", type_="check"
    )

    op.execute(sa.text(CHILD_COPY_SQL))


def downgrade() -> None:
    op.drop_table("relationship_candidate_signals")
    op.drop_column("relationship_candidates", "combined_score")
    # Re-tightening lift is only valid while no transcript-only (lift NULL) parent
    # exists; Postgres will refuse loudly otherwise, which is the safe outcome.
    op.alter_column("relationship_candidates", "lift", nullable=False)
    op.create_check_constraint(
        "chk_relationship_lift_min", "relationship_candidates", "lift >= 5"
    )
