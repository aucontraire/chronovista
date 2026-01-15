"""channel_data_cleanup

Revision ID: c4a8b9d7e3f2
Revises: 0e34f4faf930
Create Date: 2026-01-13 00:00:00.000000

This migration implements a comprehensive channel data cleanup strategy to:
1. Add channel_name_hint column for preserving original channel names
2. Populate hints from placeholder channels before deletion
3. Ensure channel_id is nullable to support orphaned videos
4. Remove placeholder/unknown channel records
5. Add partial indexes for efficient orphaned video and enrichment queries
6. Implement backup mechanism for safe rollback
7. Use advisory locks to prevent concurrent enrichment conflicts

Related Tasks: T005-T016
NFRs: NFR-022, NFR-023, NFR-024
"""

from __future__ import annotations

import logging
from typing import Any, Dict

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = "c4a8b9d7e3f2"
down_revision = "0e34f4faf930"
branch_labels = None
depends_on = None

# Advisory lock ID for enrichment operations (prevents concurrent enrichment during migration)
# Uses the same lock ID as EnrichmentLock pattern for consistency
ENRICHMENT_LOCK_ID = hash("chronovista.enrichment") & 0x7FFFFFFF

# Backup storage for rollback capability
PLACEHOLDER_BACKUP: Dict[str, str] = {}

# Batch size for updates
BATCH_SIZE = 1000

# Configure logging
logger = logging.getLogger("alembic.runtime.migration")


def upgrade() -> None:
    """
    Execute 5-phase channel data cleanup with backup mechanism.

    Phase 1: Add channel_name_hint column (T006)
    Phase 2: Populate hints from placeholder channels (T007)
    Phase 3: Make channel_id nullable (T008)
    Phase 4: Nullify placeholder channel references (T009)
    Phase 5: Delete placeholder channels (T010)

    Includes:
    - Advisory lock acquisition (T014)
    - Backup mechanism for rollback (T011)
    - Partial indexes for performance (T013)
    - Progress logging (T015)
    """
    conn = op.get_bind()

    logger.info("Starting channel data cleanup migration (c4a8b9d7e3f2)")

    # T014: Acquire advisory lock to prevent concurrent enrichment
    try:
        logger.info(f"Acquiring advisory lock (ID: {ENRICHMENT_LOCK_ID})")
        result = conn.execute(
            text(f"SELECT pg_try_advisory_lock({ENRICHMENT_LOCK_ID})")
        ).scalar()

        if not result:
            raise RuntimeError(
                "Failed to acquire advisory lock. Another enrichment process may be running. "
                "Please wait for it to complete or manually release the lock."
            )
        logger.info("Advisory lock acquired successfully")

        # Execute migration phases
        _execute_migration_phases(conn)

    finally:
        # Release advisory lock
        logger.info("Releasing advisory lock")
        conn.execute(text(f"SELECT pg_advisory_unlock({ENRICHMENT_LOCK_ID})"))
        logger.info("Advisory lock released")

    logger.info("Channel data cleanup migration completed successfully")


def _execute_migration_phases(conn: Any) -> None:
    """Execute all migration phases with progress tracking."""

    # =================================================================
    # Phase 1 (T006): Add channel_name_hint column if it doesn't exist
    # =================================================================
    logger.info("Phase 1: Checking channel_name_hint column")

    # Check if column already exists
    inspector = sa.inspect(conn)
    columns = [col["name"] for col in inspector.get_columns("videos")]

    if "channel_name_hint" not in columns:
        logger.info("Adding channel_name_hint column to videos table")
        op.add_column(
            "videos",
            sa.Column(
                "channel_name_hint",
                sa.String(255),
                nullable=True,
                comment="Original channel name when channel_id is NULL"
            )
        )
        logger.info("channel_name_hint column added successfully")
    else:
        logger.info("channel_name_hint column already exists, skipping")

    # =================================================================
    # Phase 2 (T007): Populate hints from placeholder channels
    # =================================================================
    logger.info("Phase 2: Populating channel_name_hint from placeholder channels")

    # First, count how many videos will be affected
    count_query = text("""
        SELECT COUNT(*)
        FROM videos v
        JOIN channels c ON v.channel_id = c.channel_id
        WHERE (c.title LIKE '[Placeholder]%' OR c.title LIKE '[Unknown%')
          AND v.channel_name_hint IS NULL
    """)
    total_affected = conn.execute(count_query).scalar() or 0
    logger.info(f"Found {total_affected} videos to update with channel hints")

    if total_affected > 0:
        # Update in batches for large datasets
        processed = 0
        while processed < total_affected:
            update_query = text(f"""
                UPDATE videos v
                SET channel_name_hint = c.title
                FROM channels c
                WHERE v.channel_id = c.channel_id
                  AND (c.title LIKE '[Placeholder]%' OR c.title LIKE '[Unknown%')
                  AND v.channel_name_hint IS NULL
                  AND v.video_id IN (
                      SELECT v2.video_id
                      FROM videos v2
                      JOIN channels c2 ON v2.channel_id = c2.channel_id
                      WHERE (c2.title LIKE '[Placeholder]%' OR c2.title LIKE '[Unknown%')
                        AND v2.channel_name_hint IS NULL
                      LIMIT {BATCH_SIZE}
                  )
            """)
            result = conn.execute(update_query)
            batch_count = result.rowcount
            processed += batch_count

            if batch_count > 0:
                logger.info(f"Updated {processed}/{total_affected} videos with channel hints")

            if batch_count < BATCH_SIZE:
                break

        logger.info(f"Phase 2 complete: {processed} videos updated with channel hints")
    else:
        logger.info("No videos require channel hint updates")

    # =================================================================
    # Phase 3 (T008): Ensure channel_id is nullable
    # =================================================================
    logger.info("Phase 3: Ensuring channel_id column is nullable")

    # Check current nullable status
    video_columns = inspector.get_columns("videos")
    channel_id_col = next((col for col in video_columns if col["name"] == "channel_id"), None)

    if channel_id_col and not channel_id_col["nullable"]:
        logger.info("Making channel_id column nullable")
        op.alter_column("videos", "channel_id", nullable=True)
        logger.info("channel_id is now nullable")
    else:
        logger.info("channel_id is already nullable, skipping")

    # =================================================================
    # Phase 4 (T009): Nullify placeholder channel references
    # =================================================================
    logger.info("Phase 4: Nullifying placeholder channel references in videos")

    # Count videos that will be affected
    count_query = text("""
        SELECT COUNT(*)
        FROM videos
        WHERE channel_id IN (
            SELECT channel_id FROM channels
            WHERE title LIKE '[Placeholder]%' OR title LIKE '[Unknown%'
        )
    """)
    total_to_nullify = conn.execute(count_query).scalar() or 0
    logger.info(f"Found {total_to_nullify} videos referencing placeholder channels")

    if total_to_nullify > 0:
        # Update in batches
        processed = 0
        while processed < total_to_nullify:
            nullify_query = text(f"""
                UPDATE videos
                SET channel_id = NULL
                WHERE channel_id IN (
                    SELECT channel_id FROM channels
                    WHERE title LIKE '[Placeholder]%' OR title LIKE '[Unknown%'
                )
                AND video_id IN (
                    SELECT video_id
                    FROM videos
                    WHERE channel_id IN (
                        SELECT channel_id FROM channels
                        WHERE title LIKE '[Placeholder]%' OR title LIKE '[Unknown%'
                    )
                    LIMIT {BATCH_SIZE}
                )
            """)
            result = conn.execute(nullify_query)
            batch_count = result.rowcount
            processed += batch_count

            if batch_count > 0:
                logger.info(f"Nullified {processed}/{total_to_nullify} video channel references")

            if batch_count < BATCH_SIZE:
                break

        logger.info(f"Phase 4 complete: {processed} video references nullified")
    else:
        logger.info("No videos reference placeholder channels")

    # =================================================================
    # Phase 5 (T010): Delete placeholder channels with backup (T011)
    # =================================================================
    logger.info("Phase 5: Backing up and deleting placeholder channels")

    # T011: Backup placeholder channels for rollback capability
    backup_query = text("""
        SELECT channel_id, title
        FROM channels
        WHERE title LIKE '[Placeholder]%' OR title LIKE '[Unknown%'
    """)
    backup_results = conn.execute(backup_query).fetchall()

    global PLACEHOLDER_BACKUP
    PLACEHOLDER_BACKUP = {row[0]: row[1] for row in backup_results}
    logger.info(f"Backed up {len(PLACEHOLDER_BACKUP)} placeholder channels for rollback")

    if PLACEHOLDER_BACKUP:
        # Log sample of backed up channels
        sample_size = min(5, len(PLACEHOLDER_BACKUP))
        sample = list(PLACEHOLDER_BACKUP.items())[:sample_size]
        logger.info(f"Sample of backed up channels: {sample}")

        # Delete placeholder channels
        delete_query = text("""
            DELETE FROM channels
            WHERE title LIKE '[Placeholder]%' OR title LIKE '[Unknown%'
        """)
        result = conn.execute(delete_query)
        deleted_count = result.rowcount
        logger.info(f"Deleted {deleted_count} placeholder channels")
    else:
        logger.info("No placeholder channels found to delete")

    # =================================================================
    # T013: Add partial indexes for performance (NFR-022/023/024)
    # =================================================================
    logger.info("Adding partial indexes for query optimization")

    # NFR-022: Index for orphaned video queries
    logger.info("Creating idx_videos_null_channel for orphaned video lookups")
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_videos_null_channel
        ON videos (video_id)
        WHERE channel_id IS NULL
    """))

    # NFR-023: Index for unenriched channels
    logger.info("Creating idx_channels_needs_enrichment for unenriched channel lookups")
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_channels_needs_enrichment
        ON channels (channel_id)
        WHERE subscriber_count IS NULL
    """))

    # NFR-024: Index for channel hint lookups
    logger.info("Creating idx_videos_channel_hint for channel hint queries")
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_videos_channel_hint
        ON videos (channel_name_hint)
        WHERE channel_id IS NULL AND channel_name_hint IS NOT NULL
    """))

    logger.info("All partial indexes created successfully")


def downgrade() -> None:
    """
    Rollback channel data cleanup migration.

    Restores:
    1. Placeholder channels from backup (T012)
    2. Video-channel relationships
    3. channel_id NOT NULL constraint
    4. Removes channel_name_hint column
    5. Drops partial indexes
    """
    conn = op.get_bind()

    logger.info("Starting rollback of channel data cleanup migration")

    # T012: Restore placeholder channels from backup
    if PLACEHOLDER_BACKUP:
        logger.info(f"Restoring {len(PLACEHOLDER_BACKUP)} placeholder channels from backup")

        for channel_id, title in PLACEHOLDER_BACKUP.items():
            # Insert placeholder channel back
            insert_query = text("""
                INSERT INTO channels (channel_id, title, is_subscribed, created_at, updated_at)
                VALUES (:channel_id, :title, false, NOW(), NOW())
                ON CONFLICT (channel_id) DO NOTHING
            """)
            conn.execute(insert_query, {"channel_id": channel_id, "title": title})

        logger.info("Placeholder channels restored")

        # Re-link videos to placeholder channels using channel_name_hint
        logger.info("Re-linking videos to restored placeholder channels")

        relink_query = text("""
            UPDATE videos v
            SET channel_id = c.channel_id
            FROM channels c
            WHERE v.channel_id IS NULL
              AND v.channel_name_hint IS NOT NULL
              AND c.title = v.channel_name_hint
              AND (c.title LIKE '[Placeholder]%' OR c.title LIKE '[Unknown%')
        """)
        result = conn.execute(relink_query)
        logger.info(f"Re-linked {result.rowcount} videos to placeholder channels")
    else:
        logger.warning("No backup data available for restoration")

    # Drop partial indexes
    logger.info("Dropping partial indexes")
    op.execute(text("DROP INDEX IF EXISTS idx_videos_channel_hint"))
    op.execute(text("DROP INDEX IF EXISTS idx_channels_needs_enrichment"))
    op.execute(text("DROP INDEX IF EXISTS idx_videos_null_channel"))
    logger.info("Partial indexes dropped")

    # Make channel_id NOT NULL (only if all videos have channels)
    null_count_query = text("SELECT COUNT(*) FROM videos WHERE channel_id IS NULL")
    null_count = conn.execute(null_count_query).scalar() or 0

    if null_count > 0:
        logger.warning(
            f"Cannot restore NOT NULL constraint on channel_id: {null_count} videos have NULL channel_id. "
            "Manual intervention required to assign channels to these videos."
        )
    else:
        logger.info("Making channel_id NOT NULL")
        op.alter_column("videos", "channel_id", nullable=False)
        logger.info("channel_id constraint restored")

    # Drop channel_name_hint column
    logger.info("Dropping channel_name_hint column")
    op.drop_column("videos", "channel_name_hint")
    logger.info("channel_name_hint column dropped")

    logger.info("Rollback of channel data cleanup migration completed")
