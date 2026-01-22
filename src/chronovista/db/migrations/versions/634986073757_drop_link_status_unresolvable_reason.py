"""drop_link_status_unresolvable_reason

Revision ID: 634986073757
Revises: 54fd51e399f4
Create Date: 2026-01-21 10:40:20.017136

This migration removes deprecated playlist linking columns:
1. Drop link_status column (VARCHAR(20), previously tracked playlist linking status)
2. Drop unresolvable_reason column (VARCHAR(50), previously stored failure reason codes)

These columns were part of the automatic playlist resolution feature which has been
refactored. The linking logic is now handled through the playlist_type column only.
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "634986073757"
down_revision = "54fd51e399f4"
branch_labels = None
depends_on = None

# Configure logging
logger = logging.getLogger("alembic.runtime.migration")


def upgrade() -> None:
    """
    Drop deprecated playlist linking columns.

    Removes two columns from the playlists table that were previously used
    for tracking automatic playlist resolution status:
    - link_status: Tracking linking state (pending, linked, unresolvable, manual_required)
    - unresolvable_reason: Storing failure codes (api_blocked, deleted, renamed, ambiguous)
    """
    logger.info(
        "Starting drop_link_status_unresolvable_reason migration (634986073757)"
    )

    # Drop unresolvable_reason column first (no dependencies)
    logger.info("Dropping unresolvable_reason column from playlists table")
    op.drop_column("playlists", "unresolvable_reason")
    logger.info("unresolvable_reason column dropped")

    # Drop link_status column
    logger.info("Dropping link_status column from playlists table")
    op.drop_column("playlists", "link_status")
    logger.info("link_status column dropped")

    logger.info("Migration completed successfully - deprecated columns removed")


def downgrade() -> None:
    """
    Restore deprecated playlist linking columns.

    WARNING: This operation will restore the columns but with NULL/default values.
    Original data cannot be recovered.

    Restores:
    1. link_status column with default 'pending'
    2. unresolvable_reason column (nullable)
    """
    logger.info("Starting rollback of drop_link_status_unresolvable_reason migration")

    # Re-add link_status column
    logger.info("Re-adding link_status column to playlists table")
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
    logger.info(
        "link_status column re-added with default 'pending' (WARNING: No historical data)"
    )

    # Re-add unresolvable_reason column
    logger.info("Re-adding unresolvable_reason column to playlists table")
    op.add_column(
        "playlists",
        sa.Column(
            "unresolvable_reason",
            sa.String(50),
            nullable=True,
            comment="Reason code: api_blocked, deleted, renamed, ambiguous",
        ),
    )
    logger.info(
        "unresolvable_reason column re-added (WARNING: All values will be NULL)"
    )

    logger.info("Rollback completed - columns restored but data cannot be recovered")
