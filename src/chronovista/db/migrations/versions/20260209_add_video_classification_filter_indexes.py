"""add_video_classification_filter_indexes

Revision ID: d3f8a2b9c7e1
Revises: fc247b872aa6
Create Date: 2026-02-09 12:00:00.000000

This migration adds indexes to support efficient filtering by tags, topics,
and categories for Feature 020: Video Classification Filters.

Indexes Added:
- idx_video_tags_tag: Index on video_tags.tag for tag filtering
- idx_video_topics_topic_id: Index on video_topics.topic_id for topic filtering
- idx_videos_category_id: Index on videos.category_id for category filtering

Performance Rationale (per NFR-002, NFR-003):
- Tag filter queries use IN clause on video_tags.tag - index enables index scan
- Topic filter queries use IN clause on video_topics.topic_id - index enables index scan
- Category filter uses equality on videos.category_id - index enables fast lookup

Related: Feature 020, T013
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "d3f8a2b9c7e1"
down_revision = "fc247b872aa6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add indexes for video classification filtering."""
    # Index on video_tags.tag for efficient tag filtering
    # Supports queries like: WHERE video_id IN (SELECT video_id FROM video_tags WHERE tag IN (...))
    op.create_index(
        "idx_video_tags_tag",
        "video_tags",
        ["tag"],
        unique=False,
    )

    # Index on video_topics.topic_id for efficient topic filtering
    # Supports queries like: WHERE video_id IN (SELECT video_id FROM video_topics WHERE topic_id IN (...))
    op.create_index(
        "idx_video_topics_topic_id",
        "video_topics",
        ["topic_id"],
        unique=False,
    )

    # Index on videos.category_id for efficient category filtering
    # Supports queries like: WHERE category_id = ?
    op.create_index(
        "idx_videos_category_id",
        "videos",
        ["category_id"],
        unique=False,
    )


def downgrade() -> None:
    """Remove video classification filter indexes."""
    op.drop_index("idx_videos_category_id", table_name="videos")
    op.drop_index("idx_video_topics_topic_id", table_name="video_topics")
    op.drop_index("idx_video_tags_tag", table_name="video_tags")
