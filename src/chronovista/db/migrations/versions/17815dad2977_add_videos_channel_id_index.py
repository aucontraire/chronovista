"""add videos.channel_id index

The existing ``channel_id`` indexes on ``videos`` are both partial
(``WHERE channel_id IS NULL``), so a ``WHERE channel_id = ?`` lookup cannot
use them and falls back to a sequential scan. Confirmed on production
(55,790 rows) via ``EXPLAIN``: a Seq Scan reading 6,274 buffers / all 55,790
rows to return ~2,373 rows for the largest channel. This is app-wide — it
slows ``GET /channels/{id}/videos``, the ``/channels/{id}/entities`` panel's
channel-video lookup, and the ``/videos?channel_id=`` filter.

Plain ``CREATE INDEX`` rather than ``CONCURRENTLY``: this is a single-user
local/deploy database, and Alembic runs migrations inside a transaction,
which ``CONCURRENTLY`` cannot join. A brief table lock on 55,790 rows
(~1s) at deploy time is acceptable.

Revision ID: 17815dad2977
Revises: 1666677f9c25
Create Date: 2026-08-20 00:00:00.000000

"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "17815dad2977"
down_revision = "1666677f9c25"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add a plain btree index on ``videos.channel_id``."""
    op.create_index("idx_videos_channel_id", "videos", ["channel_id"])


def downgrade() -> None:
    """Drop the ``videos.channel_id`` index."""
    op.drop_index("idx_videos_channel_id", table_name="videos")
