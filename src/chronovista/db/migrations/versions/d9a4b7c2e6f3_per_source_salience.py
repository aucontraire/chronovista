"""feat(candidates): per-source salience columns on candidate_suggestions

Adds ``salience_title``, ``salience_description`` and ``salience_transcript``:
nullable integers, each with a ``>= 0`` CHECK. NULL means "not measured
per-source"; 0 means "measured, found nothing". There is deliberately no
default and no constraint relating the parts to ``salience``: all are counts of
distinct videos, so a video matching in two sources counts once in the total
and once in each part (parts sum to >= ``salience``, never exactly equal).

Schema-only; no data migration.

Revision ID: d9a4b7c2e6f3
Revises: c7e3a9d1f5b2
Create Date: 2026-11-05

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "d9a4b7c2e6f3"
down_revision = "c7e3a9d1f5b2"
branch_labels = None
depends_on = None

_COLUMNS = ("title", "description", "transcript")


def upgrade() -> None:
    for source in _COLUMNS:
        op.add_column(
            "candidate_suggestions",
            sa.Column(f"salience_{source}", sa.Integer(), nullable=True),
        )
    for source in _COLUMNS:
        op.create_check_constraint(
            f"chk_candidate_salience_{source}_non_negative",
            "candidate_suggestions",
            f"salience_{source} >= 0",
        )


def downgrade() -> None:
    for source in _COLUMNS:
        op.drop_constraint(
            f"chk_candidate_salience_{source}_non_negative",
            "candidate_suggestions",
            type_="check",
        )
    for source in _COLUMNS:
        op.drop_column("candidate_suggestions", f"salience_{source}")
