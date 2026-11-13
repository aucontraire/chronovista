"""feat(entities): split asr_error out of entity_aliases into entity_asr_errors

Creates ``entity_asr_errors`` (Feature 110), relocates every ``asr_error`` row
out of ``entity_aliases`` as a faithful id-preserving copy, then removes
``'asr_error'`` from the name store's ``chk_alias_type_valid`` CHECK.

Step order is load-bearing: the table must exist before the copy; the copy must
precede the delete; and the FK pre-delete guard must run before the delete
because ``entity_mentions.alias_id`` is ``ON DELETE SET NULL`` -- deleting a
linked alias would irreversibly null the mention-to-alias mapping.

``occurrence_count`` is not copied on upgrade (the new table has no such
column) and is restored as 0 on downgrade (a derived counter that recomputes on
the next counter sync).

Revision ID: b4e8c2a6d1f9
Revises: a7d3e9c1f5b2
Create Date: 2026-11-12

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "b4e8c2a6d1f9"
down_revision = "a7d3e9c1f5b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "entity_asr_errors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "entity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("named_entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("alias_name", sa.String(500), nullable=False),
        sa.Column("alias_name_normalized", sa.String(500), nullable=False),
        sa.Column(
            "case_sensitive",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "alias_name_normalized", "entity_id", name="uq_entity_asr_error_name"
        ),
    )
    op.create_index(
        "idx_entity_asr_errors_entity_id", "entity_asr_errors", ["entity_id"]
    )
    op.create_index(
        "idx_entity_asr_errors_normalized",
        "entity_asr_errors",
        ["alias_name_normalized"],
    )

    op.execute(
        sa.text(
            "INSERT INTO entity_asr_errors "
            "(id, entity_id, alias_name, alias_name_normalized, case_sensitive, "
            "first_seen_at, last_seen_at) "
            "SELECT id, entity_id, alias_name, alias_name_normalized, "
            "case_sensitive, first_seen_at, last_seen_at "
            "FROM entity_aliases WHERE alias_type = 'asr_error'"
        )
    )

    bind = op.get_bind()
    linked = bind.execute(
        sa.text(
            "SELECT count(*) FROM entity_mentions WHERE alias_id IN "
            "(SELECT id FROM entity_aliases WHERE alias_type = 'asr_error')"
        )
    ).scalar()
    if linked:
        raise RuntimeError(
            f"Aborting: {linked} mention(s) link to an asr_error alias being moved; "
            "deleting them would null the mention→alias mapping irreversibly "
            "(entity_mentions.alias_id is ON DELETE SET NULL). Resolve these links first."
        )

    op.execute(sa.text("DELETE FROM entity_aliases WHERE alias_type = 'asr_error'"))

    op.drop_constraint("chk_alias_type_valid", "entity_aliases", type_="check")
    op.create_check_constraint(
        "chk_alias_type_valid",
        "entity_aliases",
        "alias_type IN ('name_variant', 'abbreviation', 'nickname', "
        "'translated_name', 'former_name')",
    )


def downgrade() -> None:
    op.drop_constraint("chk_alias_type_valid", "entity_aliases", type_="check")
    op.create_check_constraint(
        "chk_alias_type_valid",
        "entity_aliases",
        "alias_type IN ('name_variant', 'abbreviation', 'nickname', "
        "'asr_error', 'translated_name', 'former_name')",
    )

    op.execute(
        sa.text(
            "INSERT INTO entity_aliases "
            "(id, entity_id, alias_name, alias_name_normalized, alias_type, "
            "case_sensitive, occurrence_count, first_seen_at, last_seen_at) "
            "SELECT id, entity_id, alias_name, alias_name_normalized, "
            "'asr_error', case_sensitive, 0, first_seen_at, last_seen_at "
            "FROM entity_asr_errors"
        )
    )

    op.drop_index("idx_entity_asr_errors_normalized", table_name="entity_asr_errors")
    op.drop_index("idx_entity_asr_errors_entity_id", table_name="entity_asr_errors")
    op.drop_table("entity_asr_errors")
