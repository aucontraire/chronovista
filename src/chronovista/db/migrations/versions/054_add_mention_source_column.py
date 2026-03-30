"""add_mention_source_column — add mention_source and mention_context to entity_mentions

Revision ID: c3e5f7a9b1d4
Revises: b2d4f6a8c0e1
Create Date: 2026-03-26 12:00:00.000000

Extends the entity_mentions table with two new columns:

  mention_source  VARCHAR(20) NOT NULL DEFAULT 'transcript'
      WHERE the entity was found (transcript, title, or description).
      All existing rows are back-filled with 'transcript' via the
      server_default so that no data migration step is required.

  mention_context  TEXT NULLABLE
      A ~150-character snippet around the match, populated for
      description-sourced mentions only (NULL for transcript/title rows).

New indexes added:

  uq_entity_mentions_title      UNIQUE (entity_id, video_id, mention_source)
                                  WHERE mention_source = 'title'
  uq_entity_mentions_description  UNIQUE (entity_id, video_id, mention_source, mention_text)
                                  WHERE mention_source = 'description'
  ix_entity_mentions_mention_source  (mention_source)

New CHECK constraint:

  chk_entity_mention_source_valid
      mention_source IN ('transcript', 'title', 'description')

Migration strategy:
  - ADD COLUMN with server_default='transcript': metadata-only in PostgreSQL 11+
    (milliseconds regardless of row count)
  - ADD CHECK CONSTRAINT: validates existing rows (< 1 sec for 100K rows)
  - CREATE partial UNIQUE indexes: near-instant (no title/description rows exist yet)
  - CREATE regular index: ~1-3 sec for 100K rows

Downgrade is LOSSY — all title and description mention rows are deleted
before the columns are dropped. Manual transcript mentions are preserved.
Back up entity_mentions before downgrading in production.

Related: Feature 054 (Multi-Source Entity Mention Detection)
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# ---------------------------------------------------------------------------
# Revision identifiers
# ---------------------------------------------------------------------------
revision = "c3e5f7a9b1d4"
down_revision = "b2d4f6a8c0e1"
branch_labels = None
depends_on = None

# ---------------------------------------------------------------------------
# CHECK constraint expression — kept as a constant so upgrade/downgrade stay
# in sync with each other and with db/models.py.
# ---------------------------------------------------------------------------
_MENTION_SOURCE_CHECK = (
    "mention_source IN ('transcript', 'title', 'description')"
)


def upgrade() -> None:
    """Add mention_source and mention_context columns plus supporting indexes.

    Operations performed (in dependency order):
    1. ADD COLUMN mention_source  VARCHAR(20) NOT NULL DEFAULT 'transcript'
    2. ADD COLUMN mention_context TEXT NULLABLE
    3. ADD CHECK CONSTRAINT chk_entity_mention_source_valid
    4. CREATE UNIQUE INDEX uq_entity_mentions_title
    5. CREATE UNIQUE INDEX uq_entity_mentions_description
    6. CREATE INDEX ix_entity_mentions_mention_source
    """

    # =========================================================================
    # 1. ADD mention_source column
    #    server_default back-fills all existing rows atomically in PostgreSQL.
    # =========================================================================
    op.add_column(
        "entity_mentions",
        sa.Column(
            "mention_source",
            sa.String(20),
            nullable=False,
            server_default="transcript",
        ),
    )

    # =========================================================================
    # 2. ADD mention_context column (nullable TEXT)
    # =========================================================================
    op.add_column(
        "entity_mentions",
        sa.Column(
            "mention_context",
            sa.Text(),
            nullable=True,
        ),
    )

    # =========================================================================
    # 3. ADD CHECK constraint on mention_source
    # =========================================================================
    op.create_check_constraint(
        "chk_entity_mention_source_valid",
        "entity_mentions",
        _MENTION_SOURCE_CHECK,
    )

    # =========================================================================
    # 4. CREATE partial UNIQUE index for title mentions
    #    One title mention per entity per video.
    # =========================================================================
    op.create_index(
        "uq_entity_mentions_title",
        "entity_mentions",
        ["entity_id", "video_id", "mention_source"],
        unique=True,
        postgresql_where=sa.text("mention_source = 'title'"),
    )

    # =========================================================================
    # 5. CREATE partial UNIQUE index for description mentions
    #    One mention per distinct matched text per entity per video.
    # =========================================================================
    op.create_index(
        "uq_entity_mentions_description",
        "entity_mentions",
        ["entity_id", "video_id", "mention_source", "mention_text"],
        unique=True,
        postgresql_where=sa.text("mention_source = 'description'"),
    )

    # =========================================================================
    # 6. CREATE regular index on mention_source for source-filter queries
    # =========================================================================
    op.create_index(
        "ix_entity_mentions_mention_source",
        "entity_mentions",
        ["mention_source"],
        unique=False,
    )


def downgrade() -> None:
    """Remove mention_source and mention_context columns.

    WARNING: This downgrade is LOSSY.
    All entity_mentions rows with mention_source IN ('title', 'description')
    are permanently deleted before the columns are dropped.  These rows
    have segment_id=NULL and cannot exist under pre-054 assumptions.
    Manual mentions (detection_method='manual') are preserved because
    they have mention_source='transcript' by default.

    Back up entity_mentions before running this downgrade in production.

    Operations performed (in reverse dependency order):
    1. DELETE rows with mention_source IN ('title', 'description')
    2. DROP INDEX ix_entity_mentions_mention_source
    3. DROP UNIQUE INDEX uq_entity_mentions_description
    4. DROP UNIQUE INDEX uq_entity_mentions_title
    5. DROP CHECK CONSTRAINT chk_entity_mention_source_valid
    6. DROP COLUMN mention_context
    7. DROP COLUMN mention_source
    """

    # =========================================================================
    # 1. DELETE title and description mention rows (lossy)
    # =========================================================================
    op.execute(
        "DELETE FROM entity_mentions "
        "WHERE mention_source IN ('title', 'description')"
    )

    # =========================================================================
    # 2. DROP regular index on mention_source
    # =========================================================================
    op.drop_index(
        "ix_entity_mentions_mention_source",
        table_name="entity_mentions",
    )

    # =========================================================================
    # 3. DROP partial UNIQUE index for description mentions
    # =========================================================================
    op.drop_index(
        "uq_entity_mentions_description",
        table_name="entity_mentions",
    )

    # =========================================================================
    # 4. DROP partial UNIQUE index for title mentions
    # =========================================================================
    op.drop_index(
        "uq_entity_mentions_title",
        table_name="entity_mentions",
    )

    # =========================================================================
    # 5. DROP CHECK constraint on mention_source
    # =========================================================================
    op.drop_constraint(
        "chk_entity_mention_source_valid",
        "entity_mentions",
        type_="check",
    )

    # =========================================================================
    # 6. DROP mention_context column
    # =========================================================================
    op.drop_column("entity_mentions", "mention_context")

    # =========================================================================
    # 7. DROP mention_source column
    # =========================================================================
    op.drop_column("entity_mentions", "mention_source")
