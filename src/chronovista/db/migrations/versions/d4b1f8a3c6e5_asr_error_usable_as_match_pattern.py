"""feat(entity-mentions): add entity_asr_errors.usable_as_match_pattern (FR-011)

Adds a per-form reviewer flag to ``entity_asr_errors``. Feature 111 folds
registered ASR-error forms into the match alternation, so a garble can now
*create* a mention. Most such recoveries are correct, but a minority of forms are
zero-signal — the garble is also a common phrase, an idiom, or a wrong-entity
collision — and should never be used as a match pattern even though they remain
valid ``/corrections/batch`` discovery input. ``usable_as_match_pattern`` is the
lever that separates those two roles per form.

Semantics: ``TRUE`` (default) = the form may be used as a match pattern; ``FALSE``
= suppressed from matching only. The corrections-discovery reader
(``get_all_multiword_forms_for_discovery``) ignores the flag; only the scan match reader
(``get_multiword_forms_for_matching``) filters on it.

Additive and reversible: a new ``NOT NULL DEFAULT TRUE`` boolean, no data rewrite
(existing rows become usable, i.e. behaviour-preserving). The downgrade drops the
column; any reviewer verdicts stored in it are lost on downgrade (they live
durably in tasks.md as well).

Revision ID: d4b1f8a3c6e5
Revises: c5f1a9d3e7b2
Create Date: 2026-11-15

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "d4b1f8a3c6e5"
down_revision = "c5f1a9d3e7b2"
branch_labels = None
depends_on = None

_TABLE = "entity_asr_errors"
_COLUMN = "usable_as_match_pattern"


def upgrade() -> None:
    op.add_column(
        _TABLE,
        sa.Column(
            _COLUMN,
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )


def downgrade() -> None:
    op.drop_column(_TABLE, _COLUMN)
