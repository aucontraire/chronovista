"""extend entity_operation_type constraint for grounding 073

Revision ID: 7c38bd52e115
Revises: 17815dad2977
Create Date: 2026-09-05 18:02:07.407345

"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "7c38bd52e115"
down_revision = "17815dad2977"
branch_labels = None
depends_on = None


_CONSTRAINT = "chk_entity_operation_type_valid"
_TABLE = "entity_operation_logs"


def upgrade() -> None:
    """Allow the grounding operation types (Feature 073, #292)."""
    op.drop_constraint(_CONSTRAINT, _TABLE, type_="check")
    op.create_check_constraint(
        _CONSTRAINT,
        _TABLE,
        "operation_type IN ('update', 'reground', 'refetch')",
    )


def downgrade() -> None:
    """Restore the update-only constraint.

    Safe only if no 'reground'/'refetch' rows exist; those would violate the
    restored constraint. Downgrade in a clean state.
    """
    op.drop_constraint(_CONSTRAINT, _TABLE, type_="check")
    op.create_check_constraint(
        _CONSTRAINT,
        _TABLE,
        "operation_type IN ('update')",
    )
