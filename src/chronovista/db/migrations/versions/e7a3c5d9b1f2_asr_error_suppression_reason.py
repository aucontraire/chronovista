"""feat(entity-mentions): add entity_asr_errors.suppression_reason (FR-011)

Records *why* a form is suppressed, complementing ``usable_as_match_pattern`` (which
records only *that* it is). The flag is a capability predicate; the reason is policy.
Without it, once every flagged row reads ``usable_as_match_pattern = false`` a later
"un-flag the provisional ones" cannot tell them apart from the permanent ones.

Semantics: ``NULL`` = no reason recorded (the default, and the only valid value for a
usable form); ``'zero_signal'`` = permanently suppressed (the garble carries no
recoverable signal); ``'mostly_false_redundant'`` = provisionally suppressed (mostly
false, but the recoveries are redundant with other matches, so it may be un-flagged
once video-scoped arbitration ships).

Additive and reversible: a nullable ``VARCHAR(32)`` plus a value-only CHECK, no data
rewrite (existing rows become NULL, i.e. behaviour-preserving). Deliberately NO
cross-column CHECK tying the reason to ``usable_as_match_pattern``: already-flagged
rows carry ``usable_as_match_pattern = false`` with a NULL reason until the separate
reason backfill runs, so such a constraint would reject the existing table. The
invariant is maintained by the writers and the backfill, not here. The downgrade drops
the constraint and column; any recorded reasons are lost.

Revision ID: e7a3c5d9b1f2
Revises: d4b1f8a3c6e5
Create Date: 2026-11-16

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "e7a3c5d9b1f2"
down_revision = "d4b1f8a3c6e5"
branch_labels = None
depends_on = None

_TABLE = "entity_asr_errors"
_COLUMN = "suppression_reason"
_CHECK = "chk_entity_asr_error_suppression_reason_valid"


def upgrade() -> None:
    op.add_column(
        _TABLE,
        sa.Column(_COLUMN, sa.String(length=32), nullable=True),
    )
    op.create_check_constraint(
        _CHECK,
        _TABLE,
        f"{_COLUMN} IS NULL OR {_COLUMN} IN ('zero_signal', 'mostly_false_redundant')",
    )


def downgrade() -> None:
    op.drop_constraint(_CHECK, _TABLE, type_="check")
    op.drop_column(_TABLE, _COLUMN)
