"""add_youtube_id_to_playlists

Revision ID: 20260116163000
Revises: 14d8590da038
Create Date: 2026-01-16 16:30:00.000000

This migration adds support for linking internal playlists to real YouTube playlists:
1. Increase playlist_id VARCHAR(34) → VARCHAR(36) in playlists table to support INT_ prefix
2. Increase playlist_id VARCHAR(34) → VARCHAR(36) in playlist_memberships table for FK consistency
3. Add youtube_id VARCHAR(50) column with UNIQUE constraint (nullable) to playlists table
4. Create partial index ix_playlists_youtube_id WHERE youtube_id IS NOT NULL for efficient lookups

This enables the system to:
- Store real YouTube playlist IDs (PL prefix, 30-50 chars) for API-sourced playlists
- Maintain internal playlists (INT_ prefix) without YouTube IDs
- Efficiently query playlists by YouTube ID when needed
- Support dual-mode playlist management (internal vs YouTube)
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = "20260116163000"
down_revision = "14d8590da038"
branch_labels = None
depends_on = None

# Configure logging
logger = logging.getLogger("alembic.runtime.migration")


def upgrade() -> None:
    """
    Execute youtube_id schema changes.

    Phase 1: Increase playlist_id column length from VARCHAR(34) to VARCHAR(36)
    Phase 2: Add youtube_id column to playlists table
    Phase 3: Create partial index for efficient youtube_id lookups
    """
    logger.info("Starting youtube_id migration (20260116163000)")

    # =================================================================
    # Phase 1: Increase playlist_id column length (34 -> 36 chars)
    # =================================================================
    logger.info("Phase 1: Increasing playlist_id column length to support INT_ prefix")

    # Update playlists.playlist_id column
    logger.info("Updating playlists.playlist_id to VARCHAR(36)")
    op.alter_column(
        "playlists",
        "playlist_id",
        type_=sa.String(36),
        existing_type=sa.String(34),
        existing_nullable=False,
    )

    # Update playlist_memberships.playlist_id FK column
    logger.info("Updating playlist_memberships.playlist_id to VARCHAR(36)")
    op.alter_column(
        "playlist_memberships",
        "playlist_id",
        type_=sa.String(36),
        existing_type=sa.String(34),
        existing_nullable=False,
    )

    logger.info("Phase 1 complete: playlist_id columns increased to VARCHAR(36)")

    # =================================================================
    # Phase 2: Add youtube_id column to playlists table
    # =================================================================
    logger.info("Phase 2: Adding youtube_id column to playlists table")

    op.add_column(
        "playlists",
        sa.Column(
            "youtube_id",
            sa.String(50),
            nullable=True,
            comment="Real YouTube playlist ID for linking (PL prefix, 30-50 chars)",
        ),
    )

    logger.info("Phase 2 complete: youtube_id column added")

    # =================================================================
    # Phase 3: Create partial index for efficient youtube_id lookups
    # =================================================================
    logger.info("Phase 3: Creating partial index for youtube_id lookups")

    op.create_index(
        "ix_playlists_youtube_id",
        "playlists",
        ["youtube_id"],
        unique=True,
        postgresql_where=text("youtube_id IS NOT NULL"),
    )

    logger.info("Phase 3 complete: Partial index ix_playlists_youtube_id created")
    logger.info("youtube_id migration completed successfully")


def downgrade() -> None:
    """
    Rollback youtube_id schema changes.

    WARNING: This operation will result in data loss for youtube_id column values.
    Additionally, playlists with IDs longer than 34 characters (INT_ prefixed)
    will fail to downgrade if they exist.

    Reverses:
    1. Drop partial index ix_playlists_youtube_id
    2. Remove youtube_id column from playlists table
    3. Decrease playlist_id columns back to VARCHAR(34)
    """
    logger.info("Starting rollback of youtube_id migration")

    # Drop partial index
    logger.info("Dropping ix_playlists_youtube_id index")
    op.drop_index(
        "ix_playlists_youtube_id",
        table_name="playlists",
        postgresql_where=text("youtube_id IS NOT NULL"),
    )
    logger.info("Index dropped")

    # Remove youtube_id column (DATA LOSS WARNING)
    logger.info("Removing youtube_id column (WARNING: Data loss)")
    op.drop_column("playlists", "youtube_id")
    logger.info("youtube_id column removed")

    # Revert playlist_id column length changes
    # WARNING: This will fail if any playlist_id values exceed 34 characters
    logger.info(
        "Reverting playlist_id columns to VARCHAR(34) (WARNING: May fail if INT_ playlists exist)"
    )

    # Revert playlist_memberships.playlist_id FK column
    logger.info("Reverting playlist_memberships.playlist_id to VARCHAR(34)")
    op.alter_column(
        "playlist_memberships",
        "playlist_id",
        type_=sa.String(34),
        existing_type=sa.String(36),
        existing_nullable=False,
    )

    # Revert playlists.playlist_id column
    logger.info("Reverting playlists.playlist_id to VARCHAR(34)")
    op.alter_column(
        "playlists",
        "playlist_id",
        type_=sa.String(34),
        existing_type=sa.String(36),
        existing_nullable=False,
    )

    logger.info("Rollback of youtube_id migration completed")
