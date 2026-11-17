"""Cross-Feature Data Contract: asr_match mentions qualify as an entity↔video
association on the reader surface (Feature 111 FR-014, spec §Cross-Feature;
Constitution Cross-Feature Data Contract Verification).

The shared qualification rule (``_mention_qualifies_as_association``) admits a
mention when its text folds to a visible name OR its detection method is
name-exempt (``manual`` / ``asr_match``). So a recovered mention counts on
``get_entity_video_list`` even though — in production — its text is a garble that
never folds to a name. This real-DB test seeds a rule_match and an asr_match
mention for one entity on different videos and asserts both are counted, plus a
manual control that stays excluded from the transcript count.

The authoritative end-to-end validation with a REAL garble (text that does not
fold to a visible name) lives in
``tests/integration/services/test_asr_recovery_gating.py`` — which scans a
registered ASR-error form and asserts the recovery counts across the video list
AND the stored counter. This repo-level test uses controlled seed data.

Uses the ``db_session`` fixture (create_all + drop_all per test). Name-free
placeholders only (Constitution VI).
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.repositories.entity_mention_repository import EntityMentionRepository
from tests.factories.entity_association_orm_factory import (
    seed_channel_with_videos,
    seed_mention_association,
)

pytestmark = pytest.mark.asyncio

_CH = ("UCf111asr" + "0" * 24)[:24]


def _as_uuid(value: Any) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


class TestAsrMatchCountedAsTranscript:
    async def test_asr_match_video_is_counted_in_entity_video_list(
        self, db_session: AsyncSession
    ) -> None:
        repo = EntityMentionRepository()
        v_rule = "f111rule"
        v_asr = "f111asrv"
        v_manual = "f111man"

        await seed_channel_with_videos(
            db_session, channel_id=_CH, available=[v_rule, v_asr, v_manual]
        )
        # One entity, three videos: a rule_match mention, an asr_match (recovered)
        # mention, and a manual association.
        entity = await seed_mention_association(
            db_session,
            video_ids=[v_rule],
            entity_name="F111 subject",
            detection_method="rule_match",
        )
        await seed_mention_association(
            db_session,
            video_ids=[v_asr],
            entity=entity,
            detection_method="asr_match",
        )
        await seed_mention_association(
            db_session,
            video_ids=[v_manual],
            entity=entity,
            detection_method="manual",
        )

        videos, total = await repo.get_entity_video_list(db_session, entity.id)
        by_id = {v["video_id"]: v for v in videos}

        # The rule_match and asr_match videos are both counted as transcript
        # appearances; the asr_match one is the regression this guards (FR-014).
        assert v_rule in by_id, "rule_match video missing from entity video list"
        assert v_asr in by_id, "asr_match video missing from entity video list"
        assert by_id[v_rule]["mention_count"] >= 1
        assert by_id[v_asr]["mention_count"] >= 1, (
            "asr_match mention was not counted as an association — the shared "
            "qualification predicate must admit asr_match (FR-014)"
        )

        # The manual-only association is NOT a transcript appearance: either it is
        # absent from the transcript-count surface or it carries a zero count with
        # has_manual set. It must never inflate the transcript mention_count.
        if v_manual in by_id:
            assert by_id[v_manual]["mention_count"] == 0
            assert by_id[v_manual].get("has_manual") is True

        # The recovered-ASR video reports 'transcript' as its location: location
        # is derived from mention_source (asr_match rows are mention_source=
        # 'transcript'), never inferred from detection_method.
        assert "transcript" in (by_id[v_asr].get("sources") or [])
