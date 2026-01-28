"""add_transcript_metadata_indexes

Revision ID: 2a70c9b65b39
Revises: b67b55651f2f
Create Date: 2026-01-27 10:40:52.225246

This migration adds performance indexes for Feature 007 transcript timestamp columns.

Changes:
1. Add partial index on has_timestamps (only for rows where has_timestamps = true)
2. Add B-tree index on segment_count (for range queries)
3. Add B-tree index on total_duration (for range queries)
4. Add B-tree index on source (for equality queries)

These indexes optimize common query patterns for transcript metadata filtering.
"""

from __future__ import annotations

import sqlalchemy as sa


from alembic import op

# revision identifiers, used by Alembic.
revision = "2a70c9b65b39"
down_revision = "b67b55651f2f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Add performance indexes for transcript metadata columns.

    Creates the following indexes on video_transcripts table:
    1. Partial index on has_timestamps (only for TRUE values)
    2. B-tree index on segment_count
    3. B-tree index on total_duration
    4. B-tree index on source

    These indexes optimize common query patterns like:
    - Filtering for transcripts with timestamps
    - Range queries on segment counts (e.g., segment_count > 50)
    - Range queries on duration (e.g., total_duration > 600)
    - Filtering by transcript source type
    """
    # 1. Partial index on has_timestamps (only index TRUE values)
    # Most queries filter for transcripts WITH timestamps, so this saves space
    op.create_index(
        "ix_video_transcripts_has_timestamps_true",
        "video_transcripts",
        ["has_timestamps"],
        unique=False,
        postgresql_where=sa.text("has_timestamps = true"),
    )

    # 2. B-tree index on segment_count for range queries
    op.create_index(
        "ix_video_transcripts_segment_count",
        "video_transcripts",
        ["segment_count"],
        unique=False,
    )

    # 3. B-tree index on total_duration for range queries
    op.create_index(
        "ix_video_transcripts_total_duration",
        "video_transcripts",
        ["total_duration"],
        unique=False,
    )

    # 4. B-tree index on source for equality queries
    op.create_index(
        "ix_video_transcripts_source",
        "video_transcripts",
        ["source"],
        unique=False,
    )


def downgrade() -> None:
    """
    Remove performance indexes for transcript metadata columns.

    Drops all indexes created by the upgrade() function in reverse order:
    1. Drop source index
    2. Drop total_duration index
    3. Drop segment_count index
    4. Drop partial has_timestamps index
    """
    # Drop indexes in reverse order
    op.drop_index(
        "ix_video_transcripts_source",
        table_name="video_transcripts",
    )
    op.drop_index(
        "ix_video_transcripts_total_duration",
        table_name="video_transcripts",
    )
    op.drop_index(
        "ix_video_transcripts_segment_count",
        table_name="video_transcripts",
    )
    op.drop_index(
        "ix_video_transcripts_has_timestamps_true",
        table_name="video_transcripts",
    )
