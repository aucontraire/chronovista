"""Add GIN trigram indexes for transcript text search.

Revision ID: b2d4f6a8c0e1
Revises: a1b3c5d7e9f2
Create Date: 2026-03-28

Enables the pg_trgm extension and creates GIN trigram indexes on
transcript_segments.text and transcript_segments.corrected_text.

These indexes accelerate the %pattern% ILIKE queries used by the
search endpoint (GET /api/v1/search/segments), which previously
required a sequential scan on every search.

Addresses D2 from the 004-FEEDBACK assessment (flagged as High
priority by Database, Architecture, and Performance reviewers).
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "b2d4f6a8c0e1"
down_revision = "a1b3c5d7e9f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Enable the pg_trgm extension (idempotent)
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # 2. Create GIN trigram index on transcript_segments.text
    op.execute(
        "CREATE INDEX IF NOT EXISTS "
        "idx_segments_text_trgm ON transcript_segments "
        "USING gin(text gin_trgm_ops)"
    )

    # 3. Create GIN trigram index on transcript_segments.corrected_text
    #    Partial index: only rows with corrections get indexed.
    op.execute(
        "CREATE INDEX IF NOT EXISTS "
        "idx_segments_corrected_text_trgm ON transcript_segments "
        "USING gin(corrected_text gin_trgm_ops) "
        "WHERE corrected_text IS NOT NULL"
    )


def downgrade() -> None:
    # Drop indexes (extension is left in place — shared resource)
    op.execute("DROP INDEX IF EXISTS idx_segments_corrected_text_trgm")
    op.execute("DROP INDEX IF EXISTS idx_segments_text_trgm")
