"""add_cascade_deletes_to_playlist_memberships

Revision ID: 6c1553f17d7a
Revises: 20260116163000
Create Date: 2026-01-16 06:09:21.001445

This migration adds CASCADE DELETE behavior to playlist_memberships foreign keys:
1. Drop existing foreign key constraints without CASCADE
2. Recreate foreign keys with ON DELETE CASCADE
3. Ensures deleting playlists or videos automatically removes memberships

This supports the re-seeding workflow where playlists are deleted and recreated
with new INT_ IDs, and memberships are automatically cleaned up via cascade.
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "6c1553f17d7a"
down_revision = "20260116163000"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")


def upgrade() -> None:
    """Add CASCADE DELETE to playlist_memberships foreign keys."""
    logger.info("Starting CASCADE DELETE migration for playlist_memberships")

    # Drop existing foreign key constraints
    logger.info("Dropping existing foreign key constraints")
    op.drop_constraint(
        "playlist_memberships_playlist_id_fkey",
        "playlist_memberships",
        type_="foreignkey",
    )
    op.drop_constraint(
        "playlist_memberships_video_id_fkey",
        "playlist_memberships",
        type_="foreignkey",
    )

    # Recreate foreign keys with CASCADE DELETE
    logger.info("Recreating foreign keys with CASCADE DELETE")
    op.create_foreign_key(
        "playlist_memberships_playlist_id_fkey",
        "playlist_memberships",
        "playlists",
        ["playlist_id"],
        ["playlist_id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "playlist_memberships_video_id_fkey",
        "playlist_memberships",
        "videos",
        ["video_id"],
        ["video_id"],
        ondelete="CASCADE",
    )

    logger.info("CASCADE DELETE migration completed successfully")


def downgrade() -> None:
    """Remove CASCADE DELETE from playlist_memberships foreign keys."""
    logger.info("Starting rollback of CASCADE DELETE migration")

    # Drop CASCADE foreign key constraints
    logger.info("Dropping CASCADE foreign key constraints")
    op.drop_constraint(
        "playlist_memberships_playlist_id_fkey",
        "playlist_memberships",
        type_="foreignkey",
    )
    op.drop_constraint(
        "playlist_memberships_video_id_fkey",
        "playlist_memberships",
        type_="foreignkey",
    )

    # Recreate foreign keys without CASCADE DELETE (default RESTRICT)
    logger.info("Recreating foreign keys without CASCADE DELETE")
    op.create_foreign_key(
        "playlist_memberships_playlist_id_fkey",
        "playlist_memberships",
        "playlists",
        ["playlist_id"],
        ["playlist_id"],
    )
    op.create_foreign_key(
        "playlist_memberships_video_id_fkey",
        "playlist_memberships",
        "videos",
        ["video_id"],
        ["video_id"],
    )

    logger.info("CASCADE DELETE rollback completed")
