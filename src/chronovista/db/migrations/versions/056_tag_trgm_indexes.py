"""tag trgm indexes for contains-mode search

Revision ID: a7b9c1d3e5f7
Revises: c3e5f7a9b1d4
Create Date: 2026-07-19 00:00:00.000000

Enables the ``pg_trgm`` extension and adds GIN trigram indexes on the columns
searched in contains mode (``ILIKE '%q%'``), which a standard B-tree index
cannot serve. Without these, an unindexed substring scan over ~150k canonical
tags / ~170k aliases measured ~315ms warm / ~640ms cold — too slow for
typeahead (Feature 056, FR-005e, FR-019, SC-007).

The indexes do NOT change search result semantics; they only accelerate the
same substring match.

Related Tasks: T003 (Feature 056: Tag Merge UI - Foundational)
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "a7b9c1d3e5f7"
down_revision = "c3e5f7a9b1d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Enable pg_trgm and create GIN trigram indexes."""
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_canonical_tags_canonical_form_trgm "
        "ON canonical_tags USING gin (canonical_form gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_canonical_tags_normalized_form_trgm "
        "ON canonical_tags USING gin (normalized_form gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_tag_aliases_raw_form_trgm "
        "ON tag_aliases USING gin (raw_form gin_trgm_ops)"
    )


def downgrade() -> None:
    """Drop the trigram indexes.

    The ``pg_trgm`` extension is intentionally left in place — it may be shared
    with other features (FR-019).
    """
    op.execute("DROP INDEX IF EXISTS idx_tag_aliases_raw_form_trgm")
    op.execute("DROP INDEX IF EXISTS idx_canonical_tags_normalized_form_trgm")
    op.execute("DROP INDEX IF EXISTS idx_canonical_tags_canonical_form_trgm")
