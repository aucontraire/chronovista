"""update_correction_type_enum

Revision ID: c3f5a7b9d1e6
Revises: b2e4f8a1c9d3
Create Date: 2026-03-11 12:00:00.000000

Migrate the CorrectionType enum used in the transcript_corrections table:
- Add new values: proper_noun, word_boundary, other
- Migrate existing asr_error rows to 'other' (safe neutral default)
- Remove the asr_error value

PostgreSQL cannot drop individual enum values, so the migration recreates
the column using a temporary column swap when removing asr_error.

If you had 'asr_error' corrections, run the reclassification script to
review and assign specific types:

    python scripts/utilities/reclassify_asr_corrections.py --audit
    python scripts/utilities/reclassify_asr_corrections.py --apply

See scripts/utilities/reclassify_asr_corrections.py --help for details.

Related: CorrectionType enum update (Feature 041)
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "c3f5a7b9d1e6"
down_revision = "b2e4f8a1c9d3"
branch_labels = None
depends_on = None

# The new set of allowed values (asr_error removed).
NEW_VALUES = (
    "spelling",
    "proper_noun",
    "context_correction",
    "word_boundary",
    "formatting",
    "profanity_fix",
    "other",
    "revert",
)

# The old set of allowed values (asr_error present, new ones absent).
OLD_VALUES = (
    "spelling",
    "profanity_fix",
    "context_correction",
    "formatting",
    "asr_error",
    "revert",
)


def upgrade() -> None:
    """
    Add proper_noun, word_boundary, other; migrate asr_error -> proper_noun;
    remove asr_error.

    Strategy:
    1. Rename the current correction_type column to correction_type_old.
    2. Add a new correction_type VARCHAR(30) column.
    3. Copy values, mapping asr_error -> proper_noun.
    4. Make the new column NOT NULL.
    5. Drop the old column.
    """
    # Step 1: Rename existing column
    op.alter_column(
        "transcript_corrections",
        "correction_type",
        new_column_name="correction_type_old",
    )

    # Step 2: Add new column (nullable initially for the copy step)
    op.execute(
        "ALTER TABLE transcript_corrections "
        "ADD COLUMN correction_type VARCHAR(30)"
    )

    # Step 3: Copy values with mapping
    op.execute(
        "UPDATE transcript_corrections "
        "SET correction_type = CASE "
        "  WHEN correction_type_old = 'asr_error' THEN 'other' "
        "  ELSE correction_type_old "
        "END"
    )

    # Step 4: Set NOT NULL
    op.execute(
        "ALTER TABLE transcript_corrections "
        "ALTER COLUMN correction_type SET NOT NULL"
    )

    # Step 5: Drop old column
    op.drop_column("transcript_corrections", "correction_type_old")


def downgrade() -> None:
    """
    Reverse: add asr_error back, remove proper_noun/word_boundary/other.

    Maps proper_noun, word_boundary, and other all back to asr_error.
    This is inherently lossy — reclassified rows lose their specific types.
    Uses the same column-swap strategy.
    """
    # Step 1: Rename existing column
    op.alter_column(
        "transcript_corrections",
        "correction_type",
        new_column_name="correction_type_old",
    )

    # Step 2: Add new column
    op.execute(
        "ALTER TABLE transcript_corrections "
        "ADD COLUMN correction_type VARCHAR(30)"
    )

    # Step 3: Copy values with reverse mapping
    op.execute(
        "UPDATE transcript_corrections "
        "SET correction_type = CASE "
        "  WHEN correction_type_old IN ('proper_noun', 'word_boundary', 'other') THEN 'asr_error' "
        "  ELSE correction_type_old "
        "END"
    )

    # Step 4: Set NOT NULL
    op.execute(
        "ALTER TABLE transcript_corrections "
        "ALTER COLUMN correction_type SET NOT NULL"
    )

    # Step 5: Drop old column
    op.drop_column("transcript_corrections", "correction_type_old")
