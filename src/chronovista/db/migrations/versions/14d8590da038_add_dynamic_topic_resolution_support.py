"""add_dynamic_topic_resolution_support

Revision ID: 14d8590da038
Revises: c4a8b9d7e3f2
Create Date: 2026-01-14 22:09:27.431438

This migration implements dynamic topic resolution capabilities to enable:
1. Add Wikipedia URL tracking for topic categories
2. Add normalized name field for case-insensitive lookups
3. Add source field to distinguish seeded vs dynamic topics
4. Add last_seen_at timestamp for topic usage tracking
5. Add occurrence_count for topic popularity metrics
6. Create topic_aliases table for handling spelling variants and redirects
7. Backfill existing seeded topics with Wikipedia URLs and normalized names
8. Create performance indexes for efficient lookups

This enables the system to dynamically resolve Wikipedia topic redirects and
handle spelling variations (e.g., "humour" vs "humor") while maintaining
data integrity and topic uniqueness.
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "14d8590da038"
down_revision = "c4a8b9d7e3f2"
branch_labels = None
depends_on = None

# Configure logging
logger = logging.getLogger("alembic.runtime.migration")

# Batch size for backfill operations
BATCH_SIZE = 1000


def upgrade() -> None:
    """
    Execute dynamic topic resolution schema changes.

    Phase 1: Add new columns to topic_categories
    Phase 2: Create topic_aliases table
    Phase 3: Backfill existing seeded topics with data
    Phase 4: Create performance indexes
    """
    conn = op.get_bind()
    logger.info("Starting dynamic topic resolution migration (14d8590da038)")

    # =================================================================
    # Phase 1: Add new columns to topic_categories table
    # =================================================================
    logger.info("Phase 1: Adding new columns to topic_categories table")

    # Add wikipedia_url column
    logger.info("Adding wikipedia_url column")
    op.add_column(
        "topic_categories",
        sa.Column(
            "wikipedia_url",
            sa.String(500),
            nullable=True,
            comment="Full Wikipedia URL (e.g., https://en.wikipedia.org/wiki/Music)",
        ),
    )

    # Add normalized_name column
    logger.info("Adding normalized_name column")
    op.add_column(
        "topic_categories",
        sa.Column(
            "normalized_name",
            sa.String(255),
            nullable=True,
            comment="Lowercase category name with no underscores for lookups",
        ),
    )

    # Add source column with default value
    logger.info("Adding source column")
    op.add_column(
        "topic_categories",
        sa.Column(
            "source",
            sa.String(20),
            nullable=False,
            server_default="seeded",
            comment="Origin of topic: 'seeded' or 'dynamic'",
        ),
    )

    # Add last_seen_at column
    logger.info("Adding last_seen_at column")
    op.add_column(
        "topic_categories",
        sa.Column(
            "last_seen_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=True,
            comment="Last time this topic was seen in API response",
        ),
    )

    # Add occurrence_count column
    logger.info("Adding occurrence_count column")
    op.add_column(
        "topic_categories",
        sa.Column(
            "occurrence_count",
            sa.Integer,
            nullable=False,
            server_default="1",
            comment="Number of times this topic has been encountered",
        ),
    )

    logger.info("Phase 1 complete: All columns added to topic_categories")

    # =================================================================
    # Phase 2: Create topic_aliases table
    # =================================================================
    logger.info("Phase 2: Creating topic_aliases table")

    op.create_table(
        "topic_aliases",
        sa.Column(
            "alias",
            sa.String(255),
            primary_key=True,
            comment="Alias name (e.g., 'humour')",
        ),
        sa.Column(
            "topic_id",
            sa.String(50),
            sa.ForeignKey("topic_categories.topic_id", ondelete="CASCADE"),
            nullable=False,
            comment="Reference to canonical topic",
        ),
        sa.Column(
            "alias_type",
            sa.String(20),
            nullable=False,
            comment="Type: 'spelling', 'redirect', or 'synonym'",
        ),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=text("now()"),
            comment="When this alias was created",
        ),
    )

    logger.info("Phase 2 complete: topic_aliases table created")

    # =================================================================
    # Phase 3: Backfill existing seeded topics
    # =================================================================
    logger.info("Phase 3: Backfilling existing topics with Wikipedia data")

    # Count total topics to backfill
    count_query = text("SELECT COUNT(*) FROM topic_categories")
    total_topics = conn.execute(count_query).scalar() or 0
    logger.info(f"Found {total_topics} topics to backfill")

    if total_topics > 0:
        # Backfill wikipedia_url and normalized_name in a single update
        logger.info("Updating wikipedia_url and normalized_name for all topics")
        backfill_query = text(
            """
            UPDATE topic_categories
            SET
                wikipedia_url = 'https://en.wikipedia.org/wiki/' || REPLACE(category_name, ' ', '_'),
                normalized_name = LOWER(REPLACE(category_name, ' ', '_'))
            WHERE wikipedia_url IS NULL OR normalized_name IS NULL
        """
        )
        result = conn.execute(backfill_query)
        updated_count = result.rowcount
        logger.info(
            f"Backfilled {updated_count} topics with Wikipedia URLs and normalized names"
        )

        # Ensure all existing topics have source = 'seeded' (should be automatic via default)
        verify_query = text(
            """
            SELECT COUNT(*) FROM topic_categories WHERE source != 'seeded'
        """
        )
        non_seeded = conn.execute(verify_query).scalar() or 0
        if non_seeded > 0:
            logger.warning(f"Found {non_seeded} non-seeded topics, correcting...")
            fix_query = text("UPDATE topic_categories SET source = 'seeded'")
            conn.execute(fix_query)
        else:
            logger.info("All existing topics correctly marked as 'seeded'")

    logger.info("Phase 3 complete: Backfill finished")

    # =================================================================
    # Phase 4: Create performance indexes
    # =================================================================
    logger.info("Phase 4: Creating performance indexes")

    # Index for Wikipedia URL lookups (unique constraint)
    logger.info("Creating unique index idx_topic_categories_wikipedia_url")
    op.create_index(
        "idx_topic_categories_wikipedia_url",
        "topic_categories",
        ["wikipedia_url"],
        unique=True,
        postgresql_where=text("wikipedia_url IS NOT NULL"),
    )

    # Index for normalized_name lookups (for case-insensitive searches)
    logger.info("Creating index idx_topic_categories_normalized_name")
    op.create_index(
        "idx_topic_categories_normalized_name",
        "topic_categories",
        ["normalized_name"],
        unique=False,
    )

    # Index for topic_aliases.topic_id (foreign key lookups)
    logger.info("Creating index idx_topic_aliases_topic_id")
    op.create_index(
        "idx_topic_aliases_topic_id",
        "topic_aliases",
        ["topic_id"],
        unique=False,
    )

    # Index for source field (to filter seeded vs dynamic topics)
    logger.info("Creating index idx_topic_categories_source")
    op.create_index(
        "idx_topic_categories_source",
        "topic_categories",
        ["source"],
        unique=False,
    )

    logger.info("Phase 4 complete: All indexes created")
    logger.info("Dynamic topic resolution migration completed successfully")


def downgrade() -> None:
    """
    Rollback dynamic topic resolution schema changes.

    Restores the original schema by:
    1. Dropping all indexes
    2. Dropping topic_aliases table
    3. Removing new columns from topic_categories
    """
    conn = op.get_bind()
    logger.info("Starting rollback of dynamic topic resolution migration")

    # Drop indexes
    logger.info("Dropping performance indexes")
    op.drop_index("idx_topic_categories_source", table_name="topic_categories")
    op.drop_index("idx_topic_aliases_topic_id", table_name="topic_aliases")
    op.drop_index("idx_topic_categories_normalized_name", table_name="topic_categories")
    op.drop_index(
        "idx_topic_categories_wikipedia_url",
        table_name="topic_categories",
        postgresql_where=text("wikipedia_url IS NOT NULL"),
    )
    logger.info("All indexes dropped")

    # Drop topic_aliases table
    logger.info("Dropping topic_aliases table")
    op.drop_table("topic_aliases")
    logger.info("topic_aliases table dropped")

    # Remove columns from topic_categories
    logger.info("Removing columns from topic_categories table")
    op.drop_column("topic_categories", "occurrence_count")
    op.drop_column("topic_categories", "last_seen_at")
    op.drop_column("topic_categories", "source")
    op.drop_column("topic_categories", "normalized_name")
    op.drop_column("topic_categories", "wikipedia_url")
    logger.info("All columns removed from topic_categories")

    logger.info("Rollback of dynamic topic resolution migration completed")
