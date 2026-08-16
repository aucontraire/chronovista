"""add_manual_mention_source_value — widen mention_source CHECK and reclassify manual mentions

Revision ID: 8eefdce24814
Revises: df31c1abd6d0
Create Date: 2026-08-15 18:28:35.550030

Feature 066 US4: `entity_mentions.mention_source` previously allowed only
('transcript', 'title', 'description'). Hand-made associations created via
the manual-mention feature (Feature 050, `detection_method='manual'`) were
written with `mention_source='transcript'` because that was the only value
available at the time — a false label, since those rows were never detected
in a transcript. This migration adds `'manual'` as a valid value and
reclassifies the existing hand-made rows to carry the honest label.

The manual rows are identified by the predicate:

  detection_method = 'manual' AND segment_id IS NULL AND match_start IS NULL

which matches exactly the rows created by the manual-mention feature (no
transcript segment or match offset — those only exist for detected
mentions).

Ordering rationale
-------------------
upgrade(): the CHECK constraint is widened to permit 'manual' BEFORE the
data step writes that value — otherwise the UPDATE would violate the
narrower constraint. Order: drop constraint, recreate constraint (widened),
then UPDATE.

downgrade(): the reverse. The data step must run BEFORE the constraint is
narrowed back to its original three-value form, otherwise re-narrowing
first would make the affected rows read 'manual' under a constraint that no
longer permits it (transiently invalid, and if downgrade stopped between
steps, permanently invalid). Order: UPDATE back to 'transcript', drop
constraint, recreate constraint (original).

Both data steps carry an extra `mention_source = '<expected current value>'`
guard so the migration is safe to re-run against partially-migrated state.

Related: Feature 066 (Entity Association Model), Feature 050 (Manual Entity
Mentions)
"""

from __future__ import annotations

from alembic import op

# ---------------------------------------------------------------------------
# Revision identifiers
# ---------------------------------------------------------------------------
revision = "8eefdce24814"
down_revision = "df31c1abd6d0"
branch_labels = None
depends_on = None

# ---------------------------------------------------------------------------
# CHECK constraint expressions — kept as constants so upgrade/downgrade stay
# in sync with each other and with db/models.py.
# ---------------------------------------------------------------------------
_MENTION_SOURCE_CHECK_WIDENED = (
    "mention_source IN ('transcript', 'title', 'description', 'manual')"
)
_MENTION_SOURCE_CHECK_ORIGINAL = (
    "mention_source IN ('transcript', 'title', 'description')"
)

# Predicate identifying hand-made manual-mention rows (Feature 050): no
# transcript segment or match offset, because they were never detected.
_MANUAL_MENTION_PREDICATE = (
    "detection_method = 'manual' AND segment_id IS NULL AND match_start IS NULL"
)


def upgrade() -> None:
    """Widen the mention_source CHECK constraint, then reclassify manual rows.

    Operations performed (in dependency order):
    1. DROP CHECK CONSTRAINT chk_entity_mention_source_valid
    2. CREATE CHECK CONSTRAINT chk_entity_mention_source_valid (widened, +'manual')
    3. UPDATE mention_source='manual' for hand-made rows currently mislabeled
       'transcript'
    """

    # =========================================================================
    # 1. DROP the existing CHECK constraint
    # =========================================================================
    op.drop_constraint(
        "chk_entity_mention_source_valid",
        "entity_mentions",
        type_="check",
    )

    # =========================================================================
    # 2. RECREATE the CHECK constraint widened to permit 'manual'
    #    Must happen before the data step below, which writes 'manual'.
    # =========================================================================
    op.create_check_constraint(
        "chk_entity_mention_source_valid",
        "entity_mentions",
        _MENTION_SOURCE_CHECK_WIDENED,
    )

    # =========================================================================
    # 3. Reclassify hand-made manual-mention rows from the false 'transcript'
    #    label to the honest 'manual' one. The trailing mention_source='transcript'
    #    guard makes this step idempotent / safe on partially-migrated state.
    # =========================================================================
    op.execute(
        f"UPDATE entity_mentions "
        f"SET mention_source = 'manual' "
        f"WHERE {_MANUAL_MENTION_PREDICATE} AND mention_source = 'transcript'"
    )


def downgrade() -> None:
    """Reclassify manual rows back to 'transcript', then narrow the CHECK constraint.

    Operations performed (in reverse dependency order):
    1. UPDATE mention_source='transcript' for hand-made rows currently 'manual'
    2. DROP CHECK CONSTRAINT chk_entity_mention_source_valid
    3. CREATE CHECK CONSTRAINT chk_entity_mention_source_valid (original, no 'manual')
    """

    # =========================================================================
    # 1. Reclassify hand-made manual-mention rows back to 'transcript'.
    #    Must happen before the constraint is narrowed below, otherwise these
    #    rows would (transiently or permanently) violate the narrower check.
    # =========================================================================
    op.execute(
        f"UPDATE entity_mentions "
        f"SET mention_source = 'transcript' "
        f"WHERE {_MANUAL_MENTION_PREDICATE} AND mention_source = 'manual'"
    )

    # =========================================================================
    # 2. DROP the widened CHECK constraint
    # =========================================================================
    op.drop_constraint(
        "chk_entity_mention_source_valid",
        "entity_mentions",
        type_="check",
    )

    # =========================================================================
    # 3. RECREATE the CHECK constraint with its original three-value expression
    # =========================================================================
    op.create_check_constraint(
        "chk_entity_mention_source_valid",
        "entity_mentions",
        _MENTION_SOURCE_CHECK_ORIGINAL,
    )
