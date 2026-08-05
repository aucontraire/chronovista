"""allow 'repair' in the tag_operation_logs type constraint

Revision ID: a7c2e5d9f4b8
Revises: f1a3c9e2b7d4
Create Date: 2026-08-05 00:00:00.000000

``tags repair-orphans`` records its work as a ``repair`` operation so the audit
trail distinguishes correcting earlier damage from expressing a decision. The
CHECK constraint written in 028a enumerates the five original types, so that
INSERT is rejected at the database even though the enum and the Pydantic
validator both accept it.

The same list lived in three places — the enum-derived validator, the ORM
``CheckConstraint``, and this DDL. Both Python copies now derive from
``TagOperationType``; the DDL cannot, so it is spelled out here and this
migration is what keeps it in step.

Recreating the constraint validates existing rows. Every stored value is one of
the five already permitted, so the check passes and no data is rewritten.

Related: #184
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "a7c2e5d9f4b8"
down_revision = "f1a3c9e2b7d4"
branch_labels = None
depends_on = None

CONSTRAINT_NAME = "chk_tag_operation_type_valid"
TABLE_NAME = "tag_operation_logs"

_WITHOUT_REPAIR = "operation_type IN ('merge', 'split', 'rename', 'delete', 'create')"
_WITH_REPAIR = (
    "operation_type IN ('merge', 'split', 'rename', 'delete', 'create', 'repair')"
)


def upgrade() -> None:
    """Widen the constraint to admit 'repair'."""
    op.drop_constraint(CONSTRAINT_NAME, TABLE_NAME, type_="check")
    op.create_check_constraint(CONSTRAINT_NAME, TABLE_NAME, _WITH_REPAIR)


def downgrade() -> None:
    """Restore the original five types.

    Fails if any 'repair' row exists rather than deleting audit history: those
    rows carry the rollback data for repairs already applied, and dropping them
    would make those repairs unreversible. Remove or reclassify them first.
    """
    op.drop_constraint(CONSTRAINT_NAME, TABLE_NAME, type_="check")
    op.create_check_constraint(CONSTRAINT_NAME, TABLE_NAME, _WITHOUT_REPAIR)
