"""create_transcript_segments_table

Revision ID: 45339d47269e
Revises: 2a70c9b65b39
Create Date: 2026-01-28 14:51:44.192673

This migration creates the transcript_segments table for storing individual timed text segments
from video transcripts. Feature 008: Transcript Segment Table (Phase 2).

Changes:
1. Create transcript_segments table with columns:
   - id: SERIAL PRIMARY KEY
   - video_id: VARCHAR(20) NOT NULL
   - language_code: VARCHAR(10) NOT NULL
   - text: TEXT NOT NULL
   - corrected_text: TEXT (nullable, Phase 3 placeholder)
   - has_correction: BOOLEAN DEFAULT FALSE
   - start_time: FLOAT NOT NULL
   - duration: FLOAT NOT NULL
   - end_time: FLOAT NOT NULL
   - sequence_number: INTEGER NOT NULL
   - created_at: TIMESTAMP WITH TIME ZONE DEFAULT NOW()

2. Add composite foreign key constraint to video_transcripts(video_id, language_code)
   with ON DELETE CASCADE

3. Add CHECK constraints:
   - start_time >= 0
   - duration >= 0 (zero duration allowed per FR-EDGE-07)
   - sequence_number >= 0

4. Add performance indexes (NFR-PERF-01):
   - idx_transcript_segments_lookup (video_id, language_code, start_time)
   - idx_transcript_segments_time_range (video_id, language_code, start_time, end_time)
   - idx_transcript_segments_corrected (video_id, language_code, has_correction)
"""

from __future__ import annotations

import sqlalchemy as sa


from alembic import op

# revision identifiers, used by Alembic.
revision = "45339d47269e"
down_revision = "2a70c9b65b39"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Create transcript_segments table with all required columns, constraints, and indexes.

    Creates a table to store individual timed text segments from video transcripts,
    enabling precise timestamp-based querying and future correction tracking.
    """
    # Create the transcript_segments table
    op.create_table(
        "transcript_segments",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("video_id", sa.String(length=20), nullable=False),
        sa.Column("language_code", sa.String(length=10), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("corrected_text", sa.Text(), nullable=True),
        sa.Column("has_correction", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("start_time", sa.Float(), nullable=False),
        sa.Column("duration", sa.Float(), nullable=False),
        sa.Column("end_time", sa.Float(), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_transcript_segments"),
        sa.ForeignKeyConstraint(
            ["video_id", "language_code"],
            ["video_transcripts.video_id", "video_transcripts.language_code"],
            name="fk_transcript_segments_video_transcript",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("start_time >= 0", name="chk_segment_start_time_non_negative"),
        sa.CheckConstraint("duration >= 0", name="chk_segment_duration_non_negative"),
        sa.CheckConstraint("sequence_number >= 0", name="chk_segment_sequence_non_negative"),
    )

    # Create performance indexes (NFR-PERF-01)
    op.create_index(
        "idx_transcript_segments_lookup",
        "transcript_segments",
        ["video_id", "language_code", "start_time"],
    )
    op.create_index(
        "idx_transcript_segments_time_range",
        "transcript_segments",
        ["video_id", "language_code", "start_time", "end_time"],
    )
    op.create_index(
        "idx_transcript_segments_corrected",
        "transcript_segments",
        ["video_id", "language_code", "has_correction"],
    )


def downgrade() -> None:
    """
    Drop transcript_segments table and all associated indexes.

    WARNING: This will permanently delete all transcript segment data including:
    - All individual timed text segments
    - Correction tracking information
    - Timing metadata

    Ensure you have backups if this data is needed.
    """
    # Drop indexes first
    op.drop_index("idx_transcript_segments_corrected", table_name="transcript_segments")
    op.drop_index("idx_transcript_segments_time_range", table_name="transcript_segments")
    op.drop_index("idx_transcript_segments_lookup", table_name="transcript_segments")

    # Drop the table (this will automatically drop constraints)
    op.drop_table("transcript_segments")
