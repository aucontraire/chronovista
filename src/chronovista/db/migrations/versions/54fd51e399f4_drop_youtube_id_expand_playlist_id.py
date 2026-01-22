"""drop_youtube_id_expand_playlist_id

Revision ID: 54fd51e399f4
Revises: 436fe850b16d
Create Date: 2026-01-21 09:11:37.988262

This migration consolidates playlist_id and youtube_id into a single column:
1. Drop ix_playlists_youtube_id partial index
2. Drop youtube_id column from playlists table
3. Alter playlist_id VARCHAR(36) → VARCHAR(50) in playlists table
4. Alter playlist_id VARCHAR(36) → VARCHAR(50) in playlist_memberships table

Context:
- playlist_id is now the canonical identifier supporting:
  - YouTube IDs (PL prefix, 30-50 chars) like "PLdU2XMVb99xMxwMeeLWDqmyW8GFqpvgVC"
  - Internal IDs (int_ prefix, 36 chars) like "int_5d41402abc4b2a76b9719d911017c592"
  - System playlists (LL, WL, HL)
- youtube_id column is now redundant and removed
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from sqlalchemy import text

from alembic import op

# revision identifiers, used by Alembic.
revision = "54fd51e399f4"
down_revision = "436fe850b16d"
branch_labels = None
depends_on = None

# Configure logging
logger = logging.getLogger("alembic.runtime.migration")


def upgrade() -> None:
    """
    Consolidate playlist_id and youtube_id into single column.

    Phase 1: Drop youtube_id index and column
    Phase 2: Expand playlist_id from VARCHAR(36) to VARCHAR(50)
    """
    logger.info("Starting drop_youtube_id_expand_playlist_id migration (54fd51e399f4)")

    # =================================================================
    # Phase 1: Drop youtube_id infrastructure
    # =================================================================
    logger.info("Phase 1: Dropping youtube_id index and column")

    # Drop the partial index on youtube_id
    logger.info("Dropping ix_playlists_youtube_id partial index")
    op.drop_index(
        "ix_playlists_youtube_id",
        table_name="playlists",
        postgresql_where=text("youtube_id IS NOT NULL"),
    )
    logger.info("Index ix_playlists_youtube_id dropped")

    # Drop the youtube_id column
    logger.info("Dropping youtube_id column from playlists table")
    op.drop_column("playlists", "youtube_id")
    logger.info("youtube_id column dropped")

    logger.info("Phase 1 complete: youtube_id infrastructure removed")

    # =================================================================
    # Phase 2: Expand playlist_id column length (36 -> 50 chars)
    # =================================================================
    logger.info("Phase 2: Expanding playlist_id column length to support YouTube IDs")

    # Update playlists.playlist_id column
    logger.info("Updating playlists.playlist_id to VARCHAR(50)")
    op.alter_column(
        "playlists",
        "playlist_id",
        type_=sa.String(50),
        existing_type=sa.String(36),
        existing_nullable=False,
    )
    logger.info("playlists.playlist_id updated to VARCHAR(50)")

    # Update playlist_memberships.playlist_id FK column
    logger.info("Updating playlist_memberships.playlist_id to VARCHAR(50)")
    op.alter_column(
        "playlist_memberships",
        "playlist_id",
        type_=sa.String(50),
        existing_type=sa.String(36),
        existing_nullable=False,
    )
    logger.info("playlist_memberships.playlist_id updated to VARCHAR(50)")

    logger.info("Phase 2 complete: playlist_id columns expanded to VARCHAR(50)")
    logger.info("Migration completed successfully")


def downgrade() -> None:
    """
    Rollback consolidation of playlist_id and youtube_id.

    WARNING: This operation will:
    1. Shrink playlist_id from VARCHAR(50) to VARCHAR(36) - may fail if YouTube IDs exist
    2. Re-add youtube_id column (empty/NULL for all existing records)
    3. Re-create ix_playlists_youtube_id partial index

    Data Integrity Notes:
    - Playlists with YouTube IDs (>36 chars) will cause downgrade to fail
    - youtube_id column will be re-added but empty (requires manual data migration)
    """
    logger.info("Starting rollback of drop_youtube_id_expand_playlist_id migration")

    # =================================================================
    # Phase 1: Shrink playlist_id column length (50 -> 36 chars)
    # =================================================================
    logger.info(
        "Phase 1: Shrinking playlist_id columns (WARNING: May fail if YouTube IDs exist)"
    )

    # Revert playlist_memberships.playlist_id FK column
    logger.info("Reverting playlist_memberships.playlist_id to VARCHAR(36)")
    op.alter_column(
        "playlist_memberships",
        "playlist_id",
        type_=sa.String(36),
        existing_type=sa.String(50),
        existing_nullable=False,
    )
    logger.info("playlist_memberships.playlist_id reverted to VARCHAR(36)")

    # Revert playlists.playlist_id column
    logger.info("Reverting playlists.playlist_id to VARCHAR(36)")
    op.alter_column(
        "playlists",
        "playlist_id",
        type_=sa.String(36),
        existing_type=sa.String(50),
        existing_nullable=False,
    )
    logger.info("playlists.playlist_id reverted to VARCHAR(36)")

    logger.info("Phase 1 complete: playlist_id columns shrunk to VARCHAR(36)")

    # =================================================================
    # Phase 2: Re-add youtube_id infrastructure
    # =================================================================
    logger.info("Phase 2: Re-adding youtube_id column and index")

    # Re-add youtube_id column
    logger.info("Re-adding youtube_id column to playlists table")
    op.add_column(
        "playlists",
        sa.Column(
            "youtube_id",
            sa.String(50),
            nullable=True,
            comment="Real YouTube playlist ID for linking (PL prefix, 30-50 chars)",
        ),
    )
    logger.info("youtube_id column re-added (WARNING: All values will be NULL)")

    # Re-create partial index on youtube_id
    logger.info("Re-creating ix_playlists_youtube_id partial index")
    op.create_index(
        "ix_playlists_youtube_id",
        "playlists",
        ["youtube_id"],
        unique=True,
        postgresql_where=text("youtube_id IS NOT NULL"),
    )
    logger.info("Index ix_playlists_youtube_id re-created")

    logger.info("Phase 2 complete: youtube_id infrastructure restored")
    logger.info("Rollback completed (WARNING: youtube_id column empty, requires manual data migration)")
