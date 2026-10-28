"""add candidate_suggestions table (Feature 096)

New table backing the seed-and-grow candidate suggestion queue. Channel-agnostic:
``source_channel`` discriminates the discovery channel (only ``relation`` is
implemented) and ``provenance`` (JSONB) holds channel-specific detail. Unique per
``(source_channel, wikidata_qid)`` — the upsert key for idempotent re-generation.

Kept in lockstep with the ``CandidateSuggestion`` ORM model in ``db/models.py``.
No data migration; no ``CREATE EXTENSION``; UUIDv7 PKs are generated Python-side.

Revision ID: e20c6f3bfc1d
Revises: a1c7e9d2b4f8
Create Date: 2026-10-27

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "e20c6f3bfc1d"
down_revision = "a1c7e9d2b4f8"
branch_labels = None
depends_on = None

_TABLE = "candidate_suggestions"


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
        sa.Column("wikidata_qid", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=500), nullable=False),
        sa.Column("label_normalized", sa.String(length=500), nullable=False),
        sa.Column("type_hint", sa.String(length=50), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column(
            "corroboration_count",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column(
            "dangling_edge_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "salience", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "score",
            sa.Float(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("triage", sa.String(length=20), nullable=False),
        sa.Column(
            "provenance",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("possible_duplicate_of_id", sa.UUID(), nullable=True),
        sa.Column(
            "review_status",
            sa.String(length=20),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("reviewed_by", sa.String(length=255), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_entity_id", sa.UUID(), nullable=True),
        sa.Column(
            "last_generated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
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
        sa.CheckConstraint(
            "source_channel IN ('relation', 'tag_seed', 'category')",
            name="chk_candidate_source_channel_valid",
        ),
        sa.CheckConstraint(
            "triage IN ('worth_review', 'likely_eliminable', 'grounds_nowhere')",
            name="chk_candidate_triage_valid",
        ),
        sa.CheckConstraint(
            "review_status IN ('pending', 'approved', 'rejected', 'superseded')",
            name="chk_candidate_review_status_valid",
        ),
        sa.CheckConstraint(
            "type_hint IN ('person', 'organization', 'place', 'event', 'work', 'technical_term', 'concept', 'other')",
            name="chk_candidate_type_hint_valid",
        ),
        sa.CheckConstraint(
            "wikidata_qid ~ '^Q[0-9]+$'", name="chk_candidate_qid_format"
        ),
        sa.CheckConstraint(
            "review_status <> 'pending' OR "
            "(created_entity_id IS NULL AND reviewed_by IS NULL AND reviewed_at IS NULL)",
            name="chk_candidate_pending_clean",
        ),
        sa.CheckConstraint(
            "token_count >= 1", name="chk_candidate_token_count_positive"
        ),
        sa.CheckConstraint(
            "corroboration_count >= 1", name="chk_candidate_corroboration_positive"
        ),
        sa.CheckConstraint(
            "dangling_edge_count >= 0", name="chk_candidate_dangling_non_negative"
        ),
        sa.CheckConstraint("salience >= 0", name="chk_candidate_salience_non_negative"),
        sa.CheckConstraint("score >= 0", name="chk_candidate_score_non_negative"),
        sa.ForeignKeyConstraint(
            ["possible_duplicate_of_id"], ["named_entities.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["created_entity_id"], ["named_entities.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_channel", "wikidata_qid", name="uq_candidate_channel_qid"
        ),
    )
    op.create_index(
        "idx_candidate_pending_score",
        _TABLE,
        ["score"],
        unique=False,
        postgresql_where=sa.text("review_status = 'pending'"),
    )
    op.create_index(
        "idx_candidate_label_normalized",
        _TABLE,
        ["label_normalized"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade database schema."""
    op.drop_index("idx_candidate_label_normalized", table_name=_TABLE)
    op.drop_index("idx_candidate_pending_score", table_name=_TABLE)
    op.drop_table(_TABLE)
