"""extend entity_operation_type constraint for association exclusions (091)

Revision ID: e3b9a7c15d42
Revises: 7e2d9c4fb118
Create Date: 2026-10-23

Adds the Feature-091 exclude/restore operation types to the
``chk_entity_operation_type_valid`` CHECK so the manual-unlink endpoints can
write ``association_exclude`` / ``association_restore`` audit rows. Kept in
lockstep with the ORM CheckConstraint in ``db/models.py``.
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "e3b9a7c15d42"
down_revision = "7e2d9c4fb118"
branch_labels = None
depends_on = None

_CONSTRAINT = "chk_entity_operation_type_valid"
_TABLE = "entity_operation_logs"

_WITH_EXCLUSIONS = (
    "operation_type IN ('update', 'reground', 'refetch', 'alias_delete', "
    "'association_exclude', 'association_restore')"
)
_WITHOUT_EXCLUSIONS = (
    "operation_type IN ('update', 'reground', 'refetch', 'alias_delete')"
)


def upgrade() -> None:
    """Allow the Feature-091 association exclude/restore operation types."""
    op.drop_constraint(_CONSTRAINT, _TABLE, type_="check")
    op.create_check_constraint(_CONSTRAINT, _TABLE, _WITH_EXCLUSIONS)


def downgrade() -> None:
    """Restore the pre-091 constraint.

    Safe only when no ``association_exclude`` / ``association_restore`` rows
    exist; those would violate the restored constraint. Downgrade in a clean
    state.
    """
    op.drop_constraint(_CONSTRAINT, _TABLE, type_="check")
    op.create_check_constraint(_CONSTRAINT, _TABLE, _WITHOUT_EXCLUSIONS)
