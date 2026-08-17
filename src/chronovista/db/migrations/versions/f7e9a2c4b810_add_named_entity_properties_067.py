"""add_named_entity_properties — add named_entities.properties JSONB (Feature 067)

Revision ID: f7e9a2c4b810
Revises: 8eefdce24814
Create Date: 2026-08-16 00:00:00.000000

Feature 067 (Entity Enrichment Persistence): the entity-resolution pipeline captures a
per-entity knowledge-base property bag that currently lives only in a gitignored ledger
file. This migration adds the column that lands it in the database so every surface can
read it.

Additive and reversible:
  upgrade():   add named_entities.properties JSONB NOT NULL DEFAULT '{}'::jsonb
  downgrade(): drop it

The DEFAULT means existing rows get an empty bag with no backfill needed; the load
command (chronovista entities load-enrichment) populates it afterward. The sibling
`external_ids` value-shape change (bare string -> structured object) needs no migration —
that column already exists as JSONB and its values are widened by the same load, a
coordinated change with no compatibility shim (spec Clarifications).

Related: Feature 067, ADR-010 D3.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# ---------------------------------------------------------------------------
# Revision identifiers
# ---------------------------------------------------------------------------
revision = "f7e9a2c4b810"
down_revision = "8eefdce24814"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the additive properties JSONB column with an empty-object default."""
    op.add_column(
        "named_entities",
        sa.Column(
            "properties",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    """Drop the properties column (the external_ids value-shape change has no schema)."""
    op.drop_column("named_entities", "properties")
