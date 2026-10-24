"""add manual entity image columns (Feature 092)

Additive: three columns on ``named_entities`` plus a CHECK constraint on the
new source-preference column. No new table, no data migration — the
``image_source_preference`` default of ``'wikidata'`` covers every existing row.

The columns live OUTSIDE the enrichment ``properties`` JSONB so the refetch /
backfill / reground paths (which clear ``properties``) can never clobber an
operator-uploaded image. Kept in lockstep with the ORM columns and the
``chk_named_entity_image_source_valid`` CHECK in ``db/models.py``.

Revision ID: a1c7e9d2b4f8
Revises: f4a2c8b1e6d3
Create Date: 2026-10-24

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "a1c7e9d2b4f8"
down_revision = "f4a2c8b1e6d3"
branch_labels = None
depends_on = None

_TABLE = "named_entities"
_CHECK = "chk_named_entity_image_source_valid"


def upgrade() -> None:
    """Add the three manual-image columns and the source-preference CHECK."""
    op.add_column(
        _TABLE,
        sa.Column("manual_image_ext", sa.String(length=8), nullable=True),
    )
    op.add_column(
        _TABLE,
        sa.Column(
            "manual_image_uploaded_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        _TABLE,
        sa.Column(
            "image_source_preference",
            sa.String(length=16),
            nullable=False,
            server_default="wikidata",
        ),
    )
    op.create_check_constraint(
        _CHECK,
        _TABLE,
        "image_source_preference IN ('manual', 'wikidata')",
    )


def downgrade() -> None:
    """Drop the CHECK constraint, then the three manual-image columns."""
    op.drop_constraint(_CHECK, _TABLE, type_="check")
    op.drop_column(_TABLE, "image_source_preference")
    op.drop_column(_TABLE, "manual_image_uploaded_at")
    op.drop_column(_TABLE, "manual_image_ext")
