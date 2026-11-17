"""feat(entity-mentions): allow detection_method 'asr_match'

Widens ``chk_entity_mention_detection_method_valid`` on ``entity_mentions`` to
accept ``'asr_match'`` so mentions created from ASR-error-form matches are
self-identifying by provenance. Additive: no data rewrite, no column change.

The downgrade restores the original five-value set. It fails if any
``asr_match`` row exists, because re-adding the narrower CHECK validates
existing rows; delete or re-label those rows first.

Revision ID: c5f1a9d3e7b2
Revises: b4e8c2a6d1f9
Create Date: 2026-11-13

"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "c5f1a9d3e7b2"
down_revision = "b4e8c2a6d1f9"
branch_labels = None
depends_on = None

_CONSTRAINT = "chk_entity_mention_detection_method_valid"
_TABLE = "entity_mentions"
_OLD_CHECK = (
    "detection_method IN "
    "('rule_match', 'spacy_ner', 'llm_extraction', 'manual', 'user_correction')"
)
_NEW_CHECK = (
    "detection_method IN "
    "('rule_match', 'spacy_ner', 'llm_extraction', 'manual', 'user_correction', "
    "'asr_match')"
)


def upgrade() -> None:
    op.drop_constraint(_CONSTRAINT, _TABLE, type_="check")
    op.create_check_constraint(_CONSTRAINT, _TABLE, _NEW_CHECK)


def downgrade() -> None:
    op.drop_constraint(_CONSTRAINT, _TABLE, type_="check")
    op.create_check_constraint(_CONSTRAINT, _TABLE, _OLD_CHECK)
