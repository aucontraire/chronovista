"""No-regression baseline for Deliverable B (SC-007).

A small synthetic corpus of plain ``rule_match`` name matches -- no ASR error forms,
no gating, no context features, no aliases, no overlap between names.  The baseline
below is the set of mentions that matched BEFORE the Deliverable-B / US4 changes
(unified name index, single longest-match-wins pool).  The current scan must still
detect every one of them: nothing that matched before may stop matching when no
gating or context applies.  Extra detections are not asserted against (the baseline is
a lower bound, "nothing lost"), but the plain-rule_match provenance is.

All names and ids are invented placeholders.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import EntityMention as EntityMentionDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.models.enums import DetectionMethod
from chronovista.services.entity_mention_scan_service import (
    EntityMentionScanService,
)
from tests.factories.id_factory import video_id
from tests.integration.services.test_entity_mention_scan_integration import (
    _make_session_factory_from_session,
    _seed_channel,
    _seed_entity,
    _seed_segment,
    _seed_transcript,
    _seed_video,
)

# CRITICAL: ensures async tests are not silently skipped under coverage.
pytestmark = pytest.mark.asyncio

# (segment text, ((entity name, entity type), ...))
_CORPUS: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    ("Welcome back, Alpha Bravo is here.", (("Alpha Bravo", "person"),)),
    ("We visited Charlie Delta on Tuesday.", (("Charlie Delta", "place"),)),
    (
        "Echo Foxtrot met Golf Hotel downtown.",
        (("Echo Foxtrot", "person"), ("Golf Hotel", "organization")),
    ),
    ("Nothing relevant is said in this line.", ()),
    ("Alpha Bravo returned, again.", (("Alpha Bravo", "person"),)),
)

# Baseline: (segment sequence number, entity canonical name) -> mention_text, captured
# from the pre-Deliverable-B behaviour on exactly this corpus.
_BASELINE: frozenset[tuple[int, str]] = frozenset(
    {
        (0, "Alpha Bravo"),
        (1, "Charlie Delta"),
        (2, "Echo Foxtrot"),
        (2, "Golf Hotel"),
        (4, "Alpha Bravo"),
    }
)


async def test_plain_rule_matches_are_all_still_detected(
    db_session: AsyncSession,
) -> None:
    vid = video_id(seed="baseline_nr")
    await _seed_channel(db_session)
    await _seed_video(db_session, vid)
    await _seed_transcript(db_session, vid)

    seq_by_seg_id: dict[int, int] = {}
    entities: dict[str, NamedEntityDB] = {}
    for seq, (text, ents) in enumerate(_CORPUS):
        seg = await _seed_segment(
            db_session, vid, text=text, sequence_number=seq, start_time=seq * 5.0
        )
        seq_by_seg_id[seg.id] = seq
        for name, etype in ents:
            if name not in entities:
                entities[name] = await _seed_entity(db_session, name, entity_type=etype)
    await db_session.commit()

    service = EntityMentionScanService(
        session_factory=_make_session_factory_from_session(db_session)
    )
    await service.scan()

    rows = (
        await db_session.execute(
            select(
                EntityMentionDB.segment_id,
                EntityMentionDB.mention_text,
                EntityMentionDB.detection_method,
                EntityMentionDB.entity_id,
            ).where(EntityMentionDB.video_id == vid)
        )
    ).all()

    # ORM ids are uuid_utils.UUID, DB-returned ids asyncpg UUID: compare as str.
    name_by_id = {str(e.id): n for n, e in entities.items()}
    # The integration DB is shared and never reset, so an unscoped scan may also
    # match unrelated pre-existing entities; the baseline concerns only ours.
    ours = [r for r in rows if str(r.entity_id) in name_by_id]
    detected = {
        (seq_by_seg_id[r.segment_id], name_by_id[str(r.entity_id)]) for r in ours
    }

    lost = _BASELINE - detected
    assert not lost, f"baseline mentions no longer detected: {sorted(lost)}"
    assert all(
        r.detection_method == DetectionMethod.RULE_MATCH.value for r in ours
    ), "plain name matches must remain rule_match (no ASR/context provenance)"
