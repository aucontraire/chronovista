"""alias->mention provenance + undoable alias delete (#298)

Adds entity_mentions.alias_id (nullable FK -> entity_aliases, ON DELETE SET NULL)
so an auto-detected mention records the alias that produced it, and extends the
entity_operation_logs operation-type CHECK to allow 'alias_delete' so a deletion
is logged as a reversible operation.

Revision ID: abb8cf61ed36
Revises: 7c38bd52e115
Create Date: 2026-09-06

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "abb8cf61ed36"
down_revision = "7c38bd52e115"
branch_labels = None
depends_on = None


_OP_CONSTRAINT = "chk_entity_operation_type_valid"
_OP_TABLE = "entity_operation_logs"
_FK_NAME = "fk_entity_mentions_alias_id"
_INDEX_NAME = "idx_entity_mentions_alias_id"


def upgrade() -> None:
    """Add alias_id provenance + allow the 'alias_delete' operation type."""
    op.add_column(
        "entity_mentions",
        sa.Column("alias_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        _FK_NAME,
        source_table="entity_mentions",
        referent_table="entity_aliases",
        local_cols=["alias_id"],
        remote_cols=["id"],
        ondelete="SET NULL",
    )
    op.create_index(_INDEX_NAME, "entity_mentions", ["alias_id"])

    op.drop_constraint(_OP_CONSTRAINT, _OP_TABLE, type_="check")
    op.create_check_constraint(
        _OP_CONSTRAINT,
        _OP_TABLE,
        "operation_type IN ('update', 'reground', 'refetch', 'alias_delete')",
    )


def downgrade() -> None:
    """Restore the pre-#298 schema.

    Dropping alias_id is lossless for the delete/undo *machinery* (mentions are
    unaffected). Restoring the narrower CHECK is safe only when no 'alias_delete'
    rows exist; downgrade in a clean state.
    """
    op.drop_constraint(_OP_CONSTRAINT, _OP_TABLE, type_="check")
    op.create_check_constraint(
        _OP_CONSTRAINT,
        _OP_TABLE,
        "operation_type IN ('update', 'reground', 'refetch')",
    )

    op.drop_index(_INDEX_NAME, table_name="entity_mentions")
    op.drop_constraint(_FK_NAME, "entity_mentions", type_="foreignkey")
    op.drop_column("entity_mentions", "alias_id")
