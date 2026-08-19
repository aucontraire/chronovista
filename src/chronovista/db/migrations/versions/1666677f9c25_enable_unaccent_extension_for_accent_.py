"""enable unaccent extension for accent-insensitive membership

Revision ID: 1666677f9c25
Revises: f7e9a2c4b810
Create Date: 2026-08-18 17:42:21.201703

"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "1666677f9c25"
down_revision = "f7e9a2c4b810"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Enable the ``unaccent`` extension.

    Used by the entity-mention membership queries so a visible-name match folds accents
    (``lower(unaccent(...))``), agreeing with the scan's NFD accent-folding — an accented mention
    (e.g. a description mention carrying a diacritic the stored name lacks) is no longer hidden from
    the video panel / entity video list. ``unaccent`` is a trusted extension (PG13+), so the database
    owner can create it without superuser.

    Schema-only: this migration does NOT recompute any counters. The one-time counter reconciliation
    is a separate operator-invoked step (``chronovista entity recount``) run after a backup, so a data
    rewrite never rides along with the auto-migrate on deploy.
    """
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")


def downgrade() -> None:
    """Drop the ``unaccent`` extension.

    Safe because nothing in the schema (no index or generated column) depends on it — it is only
    referenced at query time.
    """
    op.execute("DROP EXTENSION IF EXISTS unaccent")
