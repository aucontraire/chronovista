"""add_transcript_raw_data

Revision ID: b67b55651f2f
Revises: a58e6cd3c0ce
Create Date: 2026-01-27 08:57:14.630639

This migration adds timestamp preservation and metadata tracking to video transcripts.

Changes:
1. Add raw_transcript_data JSONB column to store original transcript segments with timestamps
2. Add has_timestamps BOOLEAN column to indicate timestamp availability (default: true)
3. Add segment_count INTEGER column to track number of transcript segments
4. Add total_duration FLOAT column to store total transcript duration in seconds
5. Add source VARCHAR(50) column to track transcript source (default: 'youtube_transcript_api')
6. Add CHECK constraints for data validation

The migration supports transcript timestamp preservation per feature 007.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "b67b55651f2f"
down_revision = "a58e6cd3c0ce"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Add transcript raw data and metadata columns to video_transcripts table.

    Adds the following columns:
    - raw_transcript_data: JSONB storage for original transcript segments
    - has_timestamps: Boolean flag indicating timestamp presence
    - segment_count: Count of transcript segments
    - total_duration: Total duration in seconds
    - source: Transcript source identifier

    Also adds CHECK constraints for data validation.
    """
    # Add columns
    op.add_column(
        "video_transcripts",
        sa.Column("raw_transcript_data", postgresql.JSONB, nullable=True),
    )
    op.add_column(
        "video_transcripts",
        sa.Column(
            "has_timestamps",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "video_transcripts",
        sa.Column("segment_count", sa.Integer, nullable=True),
    )
    op.add_column(
        "video_transcripts",
        sa.Column("total_duration", sa.Float, nullable=True),
    )
    op.add_column(
        "video_transcripts",
        sa.Column(
            "source",
            sa.String(50),
            nullable=False,
            server_default=sa.text("'youtube_transcript_api'"),
        ),
    )

    # Add CHECK constraints
    op.create_check_constraint(
        "ck_video_transcripts_segment_count_non_negative",
        "video_transcripts",
        "segment_count IS NULL OR segment_count >= 0",
    )
    op.create_check_constraint(
        "ck_video_transcripts_total_duration_non_negative",
        "video_transcripts",
        "total_duration IS NULL OR total_duration >= 0.0",
    )
    op.create_check_constraint(
        "ck_video_transcripts_source_valid",
        "video_transcripts",
        "source IN ('youtube_transcript_api', 'youtube_data_api_v3', 'manual_upload', 'unknown')",
    )


def downgrade() -> None:
    """
    Remove transcript raw data and metadata columns from video_transcripts table.

    Drops CHECK constraints first, then removes all added columns in reverse order.

    WARNING: This will permanently delete all raw transcript data, segment counts,
    duration information, and source tracking. Ensure you have backups if this
    data is needed.
    """
    # Drop CHECK constraints first
    op.drop_constraint(
        "ck_video_transcripts_source_valid", "video_transcripts", type_="check"
    )
    op.drop_constraint(
        "ck_video_transcripts_total_duration_non_negative",
        "video_transcripts",
        type_="check",
    )
    op.drop_constraint(
        "ck_video_transcripts_segment_count_non_negative",
        "video_transcripts",
        type_="check",
    )

    # Drop columns in reverse order
    op.drop_column("video_transcripts", "source")
    op.drop_column("video_transcripts", "total_duration")
    op.drop_column("video_transcripts", "segment_count")
    op.drop_column("video_transcripts", "has_timestamps")
    op.drop_column("video_transcripts", "raw_transcript_data")
