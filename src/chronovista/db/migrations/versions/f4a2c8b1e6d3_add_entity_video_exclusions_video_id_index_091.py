"""add reverse-lookup index on entity_video_exclusions.video_id (091)

Revision ID: f4a2c8b1e6d3
Revises: e3b9a7c15d42
Create Date: 2026-10-24

The composite primary key ``(entity_id, video_id)`` only serves entity-leading
seeks. A lookup by ``video_id`` alone — the video→entities panel and the
``ON DELETE CASCADE`` from ``videos`` — cannot use that prefix, so this adds a
dedicated index. A separate, additive migration (not an edit to
``7e2d9c4fb118``) because that table-creation revision has already been applied
to production: Alembic tracks applied revisions by id, so only a new revision
reaches an already-migrated database. Kept in lockstep with the ORM
``Index`` in ``db/models.py``.
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "f4a2c8b1e6d3"
down_revision = "e3b9a7c15d42"
branch_labels = None
depends_on = None

_INDEX = "idx_entity_video_exclusions_video_id"
_TABLE = "entity_video_exclusions"


def upgrade() -> None:
    """Add the reverse-lookup index on ``video_id``."""
    op.create_index(_INDEX, _TABLE, ["video_id"])


def downgrade() -> None:
    """Drop the reverse-lookup index."""
    op.drop_index(_INDEX, table_name=_TABLE)
