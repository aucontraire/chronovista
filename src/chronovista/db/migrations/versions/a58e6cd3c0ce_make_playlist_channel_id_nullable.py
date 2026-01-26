"""make playlist channel_id nullable

Revision ID: a58e6cd3c0ce
Revises: 634986073757
Create Date: 2026-01-25 05:47:55.891174

This migration makes the channel_id column in playlists table nullable to support
system playlists that are not associated with any specific channel.

Changes:
1. ALTER playlists.channel_id to allow NULL values
2. UPDATE playlists to set channel_id=NULL for placeholder channel (UC7cf78b0e4c29369fd64711)
3. DELETE the placeholder channel record after updating playlists

The foreign key constraint to channels.channel_id is preserved, just allows NULL.
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "a58e6cd3c0ce"
down_revision = "634986073757"
branch_labels = None
depends_on = None

# Configure logging
logger = logging.getLogger("alembic.runtime.migration")

# Placeholder channel ID to be removed
PLACEHOLDER_CHANNEL_ID = "UC7cf78b0e4c29369fd64711"


def upgrade() -> None:
    """
    Make playlist.channel_id nullable and clean up placeholder channel.

    Steps:
    1. Make channel_id column nullable
    2. Set channel_id to NULL for all playlists using placeholder channel
    3. Delete the placeholder channel record (now safe since no FK references)
    """
    logger.info("Starting make_playlist_channel_id_nullable migration (a58e6cd3c0ce)")

    # Step 1: Make channel_id nullable
    logger.info("Making playlists.channel_id nullable")
    op.alter_column(
        "playlists",
        "channel_id",
        existing_type=sa.String(24),
        nullable=True,
    )
    logger.info("playlists.channel_id is now nullable")

    # Step 2: Update playlists to set placeholder channel_id to NULL
    logger.info(
        f"Setting channel_id=NULL for playlists using placeholder channel {PLACEHOLDER_CHANNEL_ID}"
    )
    connection = op.get_bind()
    result = connection.execute(
        sa.text(
            """
            UPDATE playlists
            SET channel_id = NULL
            WHERE channel_id = :placeholder_id
        """
        ),
        {"placeholder_id": PLACEHOLDER_CHANNEL_ID},
    )
    rows_updated = result.rowcount
    logger.info(f"Updated {rows_updated} playlist(s) to have NULL channel_id")

    # Step 3: Delete the placeholder channel
    logger.info(f"Deleting placeholder channel {PLACEHOLDER_CHANNEL_ID}")
    result = connection.execute(
        sa.text(
            """
            DELETE FROM channels
            WHERE channel_id = :placeholder_id
        """
        ),
        {"placeholder_id": PLACEHOLDER_CHANNEL_ID},
    )
    rows_deleted = result.rowcount
    logger.info(f"Deleted {rows_deleted} placeholder channel record(s)")

    logger.info("Migration completed successfully - channel_id is now nullable")


def downgrade() -> None:
    """
    Make playlist.channel_id NOT NULL again.

    WARNING: This operation will FAIL if any playlists have NULL channel_id.
    This is expected behavior - downgrade is not supported if NULL values exist.

    To manually downgrade:
    1. Ensure all playlists have a valid channel_id
    2. Then run: ALTER TABLE playlists ALTER COLUMN channel_id SET NOT NULL
    """
    logger.info(
        "Starting rollback of make_playlist_channel_id_nullable migration (a58e6cd3c0ce)"
    )

    logger.warning(
        "WARNING: Downgrade will FAIL if any playlists have NULL channel_id"
    )
    logger.warning(
        "You must manually assign channel_id values before downgrading"
    )

    # Attempt to make column NOT NULL (will fail if NULL values exist)
    logger.info("Making playlists.channel_id NOT NULL")
    op.alter_column(
        "playlists",
        "channel_id",
        existing_type=sa.String(24),
        nullable=False,
    )

    logger.info(
        "Rollback completed - channel_id is now NOT NULL (no NULL values existed)"
    )
