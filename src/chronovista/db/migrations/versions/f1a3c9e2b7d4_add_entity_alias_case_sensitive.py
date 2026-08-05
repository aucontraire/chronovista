"""add case_sensitive flag to entity_aliases

Revision ID: f1a3c9e2b7d4
Revises: e6f1a2b3c4d5
Create Date: 2026-08-05 00:00:00.000000

Adds ``entity_aliases.case_sensitive`` so a single alias can opt out of
case-insensitive matching.

An alias that is also an ordinary English word matches every occurrence of that
word, and exclusion patterns cannot close the set — the word appears in
arbitrary constructions. Case is often the discriminator, but *only sometimes*:
measured on real data, one entity's lowercase occurrences were almost entirely
the common noun, while another's were mostly the person with automatic
transcription simply failing to capitalise. The two want opposite settings and
nothing in the schema predicts which, so this is a per-alias human decision
rather than a rule or a heuristic.

Defaults to ``false``, which is exactly today's behaviour, so no existing alias
changes meaning on upgrade and no backfill is required. A rescan is only needed
for entities whose flag someone actually sets.

Related: #177
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "f1a3c9e2b7d4"
down_revision = "e6f1a2b3c4d5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the case_sensitive column, defaulting to current behaviour."""
    op.add_column(
        "entity_aliases",
        sa.Column(
            "case_sensitive",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
            comment=(
                "When true, this alias matches only the exact casing stored in "
                "alias_name. Defaults to false (case-insensitive), which is the "
                "historical behaviour for every alias."
            ),
        ),
    )


def downgrade() -> None:
    """Drop the case_sensitive column.

    Any opt-in settings are lost; on re-upgrade every alias returns to
    case-insensitive matching. Mentions are unaffected until the next rescan,
    which is when matching rules are actually applied.
    """
    op.drop_column("entity_aliases", "case_sensitive")
