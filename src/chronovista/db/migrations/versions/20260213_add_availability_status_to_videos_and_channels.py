"""add_availability_status_to_videos_and_channels

Revision ID: e8a4f5c9d7b2
Revises: d3f8a2b9c7e1
Create Date: 2026-02-13 12:00:00.000000

This migration replaces the deleted_flag column with availability_status on the
videos table and adds availability_status and related recovery tracking columns
to the channels table.

Changes to videos table:
1. Add availability_status VARCHAR(20) NOT NULL DEFAULT 'available'
2. Add alternative_url VARCHAR(500) NULL
3. Add recovered_at TIMESTAMPTZ NULL
4. Add recovery_source VARCHAR(50) NULL
5. Add unavailability_first_detected TIMESTAMPTZ NULL
6. Backfill availability_status from deleted_flag (deleted_flag=true -> 'unavailable')
7. Drop deleted_flag column
8. Add btree index on availability_status

Changes to channels table:
1. Add availability_status VARCHAR(20) NOT NULL DEFAULT 'available'
2. Add recovered_at TIMESTAMPTZ NULL
3. Add recovery_source VARCHAR(50) NULL
4. Add unavailability_first_detected TIMESTAMPTZ NULL
5. Add btree index on availability_status

Note: The playlists.deleted_flag column is intentionally NOT modified (per R8).

Functional Requirements Implemented:
- FR-003: Track video availability states (available, unavailable, region_blocked, private)
- FR-004: Store alternative URLs for recovered content
- FR-005: Track recovery metadata (timestamp, source)
- FR-006: Track when unavailability was first detected
- FR-028: Track channel availability states
- NFR-001: Migration is reversible and atomic

Related: Feature 023 (Deleted Content Visibility), Task T002
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "e8a4f5c9d7b2"
down_revision = "d3f8a2b9c7e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Add availability_status and recovery tracking columns to videos and channels.

    This migration follows a three-step process for videos:
    1. Add new columns (availability_status, alternative_url, recovered_at, etc.)
    2. Backfill availability_status from deleted_flag
    3. Drop deleted_flag column
    4. Add indexes

    For channels, only adds the new columns (no deleted_flag existed).
    """
    # =========================================================================
    # VIDEOS TABLE
    # =========================================================================

    # Step 1: Add new columns to videos table
    op.add_column(
        "videos",
        sa.Column(
            "availability_status",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'available'"),
        ),
    )
    op.add_column(
        "videos",
        sa.Column("alternative_url", sa.String(500), nullable=True),
    )
    op.add_column(
        "videos",
        sa.Column("recovered_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "videos",
        sa.Column("recovery_source", sa.String(50), nullable=True),
    )
    op.add_column(
        "videos",
        sa.Column(
            "unavailability_first_detected",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    # Step 2: Backfill availability_status from deleted_flag
    # Set to 'unavailable' where deleted_flag=true, otherwise keep 'available' (default)
    op.execute(
        """
        UPDATE videos
        SET availability_status = 'unavailable'
        WHERE deleted_flag = true
        """
    )

    # Step 3: Drop the deleted_flag column
    op.drop_column("videos", "deleted_flag")

    # Step 4: Add index on availability_status
    op.create_index(
        "idx_videos_availability_status",
        "videos",
        ["availability_status"],
        unique=False,
    )

    # =========================================================================
    # CHANNELS TABLE
    # =========================================================================

    # Add new columns to channels table (no deleted_flag existed, so no backfill needed)
    op.add_column(
        "channels",
        sa.Column(
            "availability_status",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'available'"),
        ),
    )
    op.add_column(
        "channels",
        sa.Column("recovered_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "channels",
        sa.Column("recovery_source", sa.String(50), nullable=True),
    )
    op.add_column(
        "channels",
        sa.Column(
            "unavailability_first_detected",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    # Add index on availability_status
    op.create_index(
        "idx_channels_availability_status",
        "channels",
        ["availability_status"],
        unique=False,
    )


def downgrade() -> None:
    """
    Remove availability_status and recovery tracking columns from videos and channels.

    This migration reverses the upgrade in the following order:
    1. Drop indexes
    2. For videos: Add deleted_flag back, backfill from availability_status
    3. Drop new columns

    WARNING: This will lose granular availability state information. The downgrade
    converts any non-'available' status back to deleted_flag=true, losing the
    distinction between 'unavailable', 'region_blocked', and 'private' states.
    Alternative URLs and recovery metadata will also be permanently deleted.
    """
    # =========================================================================
    # VIDEOS TABLE
    # =========================================================================

    # Step 1: Drop index
    op.drop_index("idx_videos_availability_status", table_name="videos")

    # Step 2: Re-add deleted_flag column
    op.add_column(
        "videos",
        sa.Column(
            "deleted_flag",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    # Step 3: Backfill deleted_flag from availability_status
    # Set deleted_flag=true for any non-'available' status
    op.execute(
        """
        UPDATE videos
        SET deleted_flag = true
        WHERE availability_status != 'available'
        """
    )

    # Step 4: Drop new columns
    op.drop_column("videos", "unavailability_first_detected")
    op.drop_column("videos", "recovery_source")
    op.drop_column("videos", "recovered_at")
    op.drop_column("videos", "alternative_url")
    op.drop_column("videos", "availability_status")

    # =========================================================================
    # CHANNELS TABLE
    # =========================================================================

    # Drop index
    op.drop_index("idx_channels_availability_status", table_name="channels")

    # Drop columns (no deleted_flag to restore for channels)
    op.drop_column("channels", "unavailability_first_detected")
    op.drop_column("channels", "recovery_source")
    op.drop_column("channels", "recovered_at")
    op.drop_column("channels", "availability_status")
