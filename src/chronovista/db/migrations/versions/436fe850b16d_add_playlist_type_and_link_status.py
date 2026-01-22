"""add_playlist_type_and_link_status

Revision ID: 436fe850b16d
Revises: 6c1553f17d7a
Create Date: 2026-01-17 21:49:05.854407

This migration adds support for automatic playlist resolution and linking:
1. Add playlist_type VARCHAR(20) column with default "regular" (NOT NULL)
2. Add link_status VARCHAR(20) column with default "pending" (NOT NULL)
3. Add unresolvable_reason VARCHAR(50) column (nullable)

These columns enable the system to:
- Track playlist types (regular, liked, watch_later, history, favorites)
- Monitor playlist linking status (pending, linked, unresolvable, manual_required)
- Store reason codes when playlists cannot be auto-resolved (api_blocked, deleted, renamed, ambiguous)
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "436fe850b16d"
down_revision = "6c1553f17d7a"
branch_labels = None
depends_on = None

# Configure logging
logger = logging.getLogger("alembic.runtime.migration")


def upgrade() -> None:
    """
    Execute playlist type and link status schema changes.

    Adds three new columns to the playlists table:
    - playlist_type: Categorize playlists (regular, system playlists like "Liked Videos")
    - link_status: Track YouTube ID resolution status
    - unresolvable_reason: Store failure reason codes when auto-resolution fails
    """
    logger.info("Starting playlist type and link status migration (436fe850b16d)")

    # Add playlist_type column
    logger.info("Adding playlist_type column to playlists table")
    op.add_column(
        "playlists",
        sa.Column(
            "playlist_type",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'regular'"),
            comment="PlaylistType enum: regular, liked, watch_later, history, favorites",
        ),
    )
    logger.info("playlist_type column added with default 'regular'")

    # Add link_status column
    logger.info("Adding link_status column to playlists table")
    op.add_column(
        "playlists",
        sa.Column(
            "link_status",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'pending'"),
            comment="PlaylistLinkStatus enum: pending, linked, unresolvable, manual_required",
        ),
    )
    logger.info("link_status column added with default 'pending'")

    # Add unresolvable_reason column
    logger.info("Adding unresolvable_reason column to playlists table")
    op.add_column(
        "playlists",
        sa.Column(
            "unresolvable_reason",
            sa.String(50),
            nullable=True,
            comment="Reason code: api_blocked, deleted, renamed, ambiguous",
        ),
    )
    logger.info("unresolvable_reason column added (nullable)")

    logger.info("Playlist type and link status migration completed successfully")


def downgrade() -> None:
    """
    Rollback playlist type and link status schema changes.

    WARNING: This operation will result in data loss for the three new columns.

    Removes:
    1. unresolvable_reason column
    2. link_status column
    3. playlist_type column
    """
    logger.info("Starting rollback of playlist type and link status migration")

    # Drop unresolvable_reason column
    logger.info("Removing unresolvable_reason column (WARNING: Data loss)")
    op.drop_column("playlists", "unresolvable_reason")
    logger.info("unresolvable_reason column removed")

    # Drop link_status column
    logger.info("Removing link_status column (WARNING: Data loss)")
    op.drop_column("playlists", "link_status")
    logger.info("link_status column removed")

    # Drop playlist_type column
    logger.info("Removing playlist_type column (WARNING: Data loss)")
    op.drop_column("playlists", "playlist_type")
    logger.info("playlist_type column removed")

    logger.info("Rollback of playlist type and link status migration completed")
