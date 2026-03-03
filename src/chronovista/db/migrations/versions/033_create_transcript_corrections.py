"""create_transcript_corrections

Revision ID: a7c3d9e5f1b4
Revises: f9b5c8d6e3a1
Create Date: 2026-03-02 12:00:00.000000

This migration implements the transcript corrections and audit trail schema
for Feature 033 (Transcript Corrections & Audit). It creates the
transcript_corrections table and adds correction-tracking columns to the
video_transcripts table.

New Tables:
1. transcript_corrections - Audit log for individual transcript text corrections

Changes to video_transcripts:
1. has_corrections - Boolean flag indicating any corrections exist
2. last_corrected_at - Timestamp of the most recent correction
3. correction_count - Running total of corrections applied

Key Features:
- UUID primary key for transcript_corrections (PostgreSQL UUID type)
- Composite FK to video_transcripts(video_id, language_code) with RESTRICT
- Optional FK to transcript_segments(id) for segment-level corrections
- CHECK constraint enforcing version_number >= 1
- 2 performance indexes on lookup patterns
- Fully reversible downgrade

Related: Feature 033 (Transcript Corrections & Audit)
Architecture: ADR-003 Tag Normalization (audit log pattern reference)
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = "a7c3d9e5f1b4"
down_revision = "f9b5c8d6e3a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Create transcript_corrections table and add correction-tracking columns
    to video_transcripts.

    Operations performed in dependency order:
    1. Create transcript_corrections table (depends on video_transcripts and
       transcript_segments)
    2. Add has_corrections, last_corrected_at, correction_count to
       video_transcripts
    3. Create indexes on transcript_corrections
    """
    # =========================================================================
    # TABLE: transcript_corrections
    # =========================================================================
    op.create_table(
        "transcript_corrections",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("video_id", sa.String(20), nullable=False),
        sa.Column("language_code", sa.String(10), nullable=False),
        sa.Column("segment_id", sa.Integer(), nullable=True),
        sa.Column("correction_type", sa.String(30), nullable=False),
        sa.Column("original_text", sa.Text(), nullable=False),
        sa.Column("corrected_text", sa.Text(), nullable=False),
        sa.Column("correction_note", sa.Text(), nullable=True),
        sa.Column("corrected_by_user_id", sa.String(100), nullable=True),
        sa.Column(
            "corrected_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_transcript_corrections"),
        sa.ForeignKeyConstraint(
            ["video_id", "language_code"],
            ["video_transcripts.video_id", "video_transcripts.language_code"],
            name="fk_transcript_corrections_transcript",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["segment_id"],
            ["transcript_segments.id"],
            name="fk_transcript_corrections_segment",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "version_number >= 1",
            name="chk_transcript_corrections_version_number_positive",
        ),
    )

    # =========================================================================
    # INDEXES on transcript_corrections
    # =========================================================================

    # Index 1: Primary lookup pattern — by transcript + time ordering
    op.create_index(
        "idx_transcript_corrections_lookup",
        "transcript_corrections",
        ["video_id", "language_code", "corrected_at"],
        unique=False,
    )

    # Index 2: Segment-level correction lookup — by segment + time ordering
    op.create_index(
        "idx_transcript_corrections_segment",
        "transcript_corrections",
        ["segment_id", "corrected_at"],
        unique=False,
    )

    # =========================================================================
    # ADD COLUMNS to video_transcripts
    # =========================================================================

    # Column 1: Flag indicating whether any corrections exist for this transcript
    op.add_column(
        "video_transcripts",
        sa.Column(
            "has_corrections",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    # Column 2: Timestamp of the most recent correction applied
    op.add_column(
        "video_transcripts",
        sa.Column(
            "last_corrected_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    # Column 3: Running total of corrections applied to this transcript
    op.add_column(
        "video_transcripts",
        sa.Column(
            "correction_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )


def downgrade() -> None:
    """
    Drop transcript_corrections table and remove correction-tracking columns
    from video_transcripts.

    WARNING: This will permanently delete all transcript correction records
    including:
    - All correction history (original text, corrected text, notes)
    - Correction authorship and timestamps
    - Version history

    Ensure you have backups if this data is needed.

    Drop order reverses upgrade to respect FK constraints:
    1. Drop indexes on transcript_corrections
    2. Drop transcript_corrections table (removes FKs to video_transcripts)
    3. Remove correction-tracking columns from video_transcripts
    """
    # =========================================================================
    # DROP INDEXES (reverse order of creation)
    # =========================================================================

    op.drop_index(
        "idx_transcript_corrections_segment",
        table_name="transcript_corrections",
    )
    op.drop_index(
        "idx_transcript_corrections_lookup",
        table_name="transcript_corrections",
    )

    # =========================================================================
    # DROP TABLE
    # =========================================================================

    op.drop_table("transcript_corrections")

    # =========================================================================
    # REMOVE COLUMNS from video_transcripts (reverse order of addition)
    # =========================================================================

    op.drop_column("video_transcripts", "correction_count")
    op.drop_column("video_transcripts", "last_corrected_at")
    op.drop_column("video_transcripts", "has_corrections")
