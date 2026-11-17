"""Behavioural differentials for Deliverable B -- the ASR-inclusive token relation.

Feature 111 folds admissible ASR-error forms into the match alternation, so an entity
can match through a token only its GARBLE carries. The scoped-scan widening
(``_shared_token_neighbour_ids``) and the cross-segment candidate pre-filter must widen /
admit on that same relation (names + admissible ASR forms), or two opposite defects
appear:

* scope / neighbour widening names-only  -> a scoped scan writes a mention a competing
  ASR-only neighbour should have shadowed (FALSE POSITIVE);
* cross-segment pre-filter names-only     -> a name-disjoint ASR garble spanning a
  segment boundary is pruned before its regex runs and never detected (FALSE NEGATIVE).

These end-to-end / seam tests prove the fix behaviourally (the architecture guard
``test_match_form_tokens_single_source`` proves it structurally).

MUTATION-VERIFIED: revert any consumer in ``_shared_token_neighbour_ids`` /
``_scan_cross_segment`` to names-only (drop the ``asr_folds`` / admissible-ASR arm) and
the matching test below goes RED.

Neutral placeholder tokens only (``qwx``/``zzq`` prefixes), never library content
(Constitution VI). The prefixes are chosen to not collide with real corpus tokens in the
shared integration database.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import Channel as ChannelDB
from chronovista.db.models import EntityAlias as EntityAliasDB
from chronovista.db.models import EntityAsrError
from chronovista.db.models import EntityMention as EntityMentionDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import TranscriptSegment as TranscriptSegmentDB
from chronovista.db.models import Video as VideoDB
from chronovista.db.models import VideoTranscript as VideoTranscriptDB
from chronovista.services.entity_mention_scan_service import (
    EntityMentionScanService,
    _build_entity_pattern,
)
from tests.factories.id_factory import channel_id, video_id

pytestmark = __import__("pytest").mark.asyncio


def _factory(session: AsyncSession) -> object:
    class _CM:
        async def __aenter__(self) -> AsyncSession:
            return session

        async def __aexit__(self, *a: object) -> bool:
            return False

    class _F:
        def __call__(self) -> _CM:
            return _CM()

    return _F()


async def _add_entity(
    session: AsyncSession, name: str, normalized: str
) -> NamedEntityDB:
    entity = NamedEntityDB(
        canonical_name=name,
        canonical_name_normalized=normalized,
        entity_type="person",
        status="active",
        discovery_method="manual",
        confidence=1.0,
        mention_count=0,
        video_count=0,
    )
    session.add(entity)
    await session.flush()
    return entity


async def _add_asr_error(
    session: AsyncSession, entity_id: uuid.UUID, form: str
) -> None:
    session.add(
        EntityAsrError(
            entity_id=entity_id,
            alias_name=form,
            alias_name_normalized=form.lower(),
            case_sensitive=False,
        )
    )
    await session.flush()


class TestWideningIncludesAsr:
    """The scoped-scan widening relates entities by names + admissible ASR forms."""

    async def test_scope_side_asr_fold_widens_neighbour_set(
        self, db_session: AsyncSession
    ) -> None:
        # Neighbour C shares a token with the SCOPE entity only through the scope
        # entity's own ASR fold ("zzqmike"), which is name-disjoint from the scope name.
        neighbour = await _add_entity(db_session, "Zzqmike Foxtrot", "zzqmike foxtrot")
        await db_session.commit()

        scope_pattern = _build_entity_pattern(
            entity_id=uuid.uuid4(),
            canonical_name="Qwxbravo",
            entity_type="person",
            names=["Qwxbravo"],
            case_sensitive_names=set(),
            exclusion_patterns=[],
            asr_forms=["zzqmike qwxecho"],
        )
        assert scope_pattern.asr_folds, "fixture precondition: scope has an ASR fold"

        svc = EntityMentionScanService(session_factory=_factory(db_session))
        neighbours = await svc._shared_token_neighbour_ids(db_session, [scope_pattern])

        # Names-only would miss it (scope token = {qwxbravo}); the ASR fold token
        # "zzqmike" is what relates them. Mutation: drop the scope-side asr_folds arm.
        # str() across the uuid_utils/stdlib UUID boundary -- the service returns
        # stdlib UUIDs from the query; callers feed them to SQL `IN (...)`, never a
        # Python `in`, so this mirrors the real (type-safe) usage.
        assert str(neighbour.id) in {str(n) for n in neighbours}

    async def test_neighbour_side_asr_form_widens_neighbour_set(
        self, db_session: AsyncSession
    ) -> None:
        # Neighbour C shares a token with the scope only through C's OWN ASR garble
        # ("qwxalpha ..."), name-disjoint from C's name.
        neighbour = await _add_entity(db_session, "Zzqcharlie", "zzqcharlie")
        await _add_asr_error(db_session, neighbour.id, "qwxalpha zzqdelta")
        await db_session.commit()

        scope_pattern = _build_entity_pattern(
            entity_id=uuid.uuid4(),
            canonical_name="Qwxalpha",
            entity_type="person",
            names=["Qwxalpha"],
            case_sensitive_names=set(),
            exclusion_patterns=[],
        )

        svc = EntityMentionScanService(session_factory=_factory(db_session))
        neighbours = await svc._shared_token_neighbour_ids(db_session, [scope_pattern])

        # Names-only would miss it (C name token = {zzqcharlie}); C's ASR form token
        # "qwxalpha" is what relates them. Mutation: drop the neighbour-side ASR load.
        # str() across the uuid_utils/stdlib UUID boundary -- the service returns
        # stdlib UUIDs from the query; callers feed them to SQL `IN (...)`, never a
        # Python `in`, so this mirrors the real (type-safe) usage.
        assert str(neighbour.id) in {str(n) for n in neighbours}


class TestCrossSegmentAsrDetected:
    """A name-disjoint ASR garble spanning a segment boundary is detected, not pruned."""

    async def test_cross_segment_name_disjoint_asr_garble_detected(
        self, db_session: AsyncSession
    ) -> None:
        ch = channel_id(seed="dbB_xseg")
        vid = video_id(seed="dbB_xseg_1")
        db_session.add(
            ChannelDB(channel_id=ch, title="C", description="d", is_subscribed=False)
        )
        await db_session.flush()
        db_session.add(
            VideoDB(
                video_id=vid,
                channel_id=ch,
                title="V",
                description="d",
                upload_date=datetime(2024, 1, 1, tzinfo=UTC),
                duration=120,
                made_for_kids=False,
                self_declared_made_for_kids=False,
            )
        )
        await db_session.flush()
        db_session.add(
            VideoTranscriptDB(
                video_id=vid,
                language_code="en",
                transcript_text="",
                transcript_type="auto",
                download_reason="user_request",
                is_cc=False,
                is_auto_synced=True,
                track_kind="standard",
                source="youtube_transcript_api",
            )
        )
        await db_session.flush()

        def _seg(seq: int, body: str) -> TranscriptSegmentDB:
            return TranscriptSegmentDB(
                video_id=vid,
                language_code="en",
                text=body,
                has_correction=False,
                start_time=float(seq),
                duration=1.0,
                end_time=float(seq) + 1.0,
                sequence_number=seq,
            )

        # The ASR garble "zzqzulu whiskey" straddles seq 0/1; NEITHER segment contains
        # a NAME token of the entity ("qwx"/"yankee"), so a names-only pre-filter prunes
        # the entity before its regex ever runs.
        db_session.add_all(
            [_seg(0, "the guest is zzqzulu"), _seg(1, "whiskey is here")]
        )
        await db_session.flush()

        entity = await _add_entity(db_session, "Qwx Yankee", "qwx yankee")
        db_session.add(
            EntityAliasDB(
                entity_id=entity.id,
                alias_name="Qwx Yankee",
                alias_name_normalized="qwx yankee",
                alias_type="name_variant",
                occurrence_count=0,
            )
        )
        await _add_asr_error(db_session, entity.id, "zzqzulu whiskey")
        await db_session.commit()

        svc = EntityMentionScanService(session_factory=_factory(db_session))
        await svc.scan(video_ids=[vid], full_rescan=True)

        rows = (
            (
                await db_session.execute(
                    select(EntityMentionDB).where(
                        EntityMentionDB.entity_id == entity.id,
                        EntityMentionDB.mention_source == "transcript",
                    )
                )
            )
            .scalars()
            .all()
        )
        spanning = [r for r in rows if r.end_segment_id is not None]

        # The spanning ASR garble is now detected. Mutation: revert the cross-segment
        # index (_scan_cross_segment) to names-only and this disappears (len == 0).
        assert len(spanning) == 1, [
            (r.mention_text, r.detection_method, r.end_segment_id) for r in rows
        ]
        assert spanning[0].mention_text.lower() == "zzqzulu whiskey"
