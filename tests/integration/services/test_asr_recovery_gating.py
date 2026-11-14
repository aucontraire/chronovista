"""Integration test for ASR-error recovery gating in the scan matcher (T015).

Feature 111 US1b wires registered ``entity_asr_errors`` forms into the scan
matcher as a gated, provenance-tagged source. This test seeds one entity with
four registered ASR-error forms spanning the admissibility boundary and asserts
the end-to-end outcome against a real database:

- an **admissible** multi-word form matches and writes an ``asr_match`` mention
  with ``alias_id IS NULL`` (an ASR form is never a name, so it carries no alias
  link — FR-014);
- a single-word form, a form with a one-char token, and an all-stopword form all
  produce **no** mention (the three admissibility gates, defence-in-depth with
  the multi-word SQL filter);
- a genuine canonical-name occurrence still writes a ``rule_match`` mention;
- **collision precedence:** a registered garble whose folded form coincides with
  a real name (here an alias) keeps ``rule_match`` and its alias id — real names
  win provenance.

All seed strings are deliberately INVENTED (no real entity names or ASR garble).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import Channel as ChannelDB
from chronovista.db.models import EntityAlias as EntityAliasDB
from chronovista.db.models import EntityAsrError as EntityAsrErrorDB
from chronovista.db.models import EntityMention as EntityMentionDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import TranscriptSegment as TranscriptSegmentDB
from chronovista.db.models import Video as VideoDB
from chronovista.db.models import VideoTranscript as VideoTranscriptDB
from chronovista.models.enums import DetectionMethod
from chronovista.services.entity_mention_scan_service import EntityMentionScanService
from tests.factories.id_factory import channel_id, video_id

pytestmark = pytest.mark.asyncio

_CHANNEL_ID = channel_id(seed="asr_gate")
_VIDEO_ID = video_id(seed="asr_gate_1")

# Invented strings only.
_CANONICAL_NAME = "John Smithe"
_ALIAS_NAME = "Johnny Smithe"
_ADMISSIBLE_ASR = "jon smithe"  # multi-word, distinctive -> admitted
_SINGLE_WORD_ASR = "jonsmithe"  # one token -> rejected
_ONE_CHAR_TOKEN_ASR = "smith a"  # stray one-char token -> rejected
_ALL_STOPWORD_ASR = "of the"  # every token common -> rejected


async def _seed_scaffolding(session: AsyncSession) -> None:
    """Insert the channel / video / transcript FK chain the scan needs."""
    session.add(
        ChannelDB(
            channel_id=_CHANNEL_ID,
            title="Invented Channel",
            description="ASR gating integration test channel",
            is_subscribed=False,
        )
    )
    await session.flush()
    session.add(
        VideoDB(
            video_id=_VIDEO_ID,
            channel_id=_CHANNEL_ID,
            title="Invented Video",
            description="ASR gating integration test video",
            upload_date=datetime(2024, 1, 1, tzinfo=UTC),
            duration=120,
            made_for_kids=False,
            self_declared_made_for_kids=False,
        )
    )
    await session.flush()
    session.add(
        VideoTranscriptDB(
            video_id=_VIDEO_ID,
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
    await session.flush()


async def _seed_segment(
    session: AsyncSession, text: str, sequence_number: int
) -> TranscriptSegmentDB:
    """Insert one transcript segment carrying ``text``."""
    seg = TranscriptSegmentDB(
        video_id=_VIDEO_ID,
        language_code="en",
        text=text,
        has_correction=False,
        start_time=float(sequence_number * 5),
        duration=5.0,
        end_time=float(sequence_number * 5 + 5),
        sequence_number=sequence_number,
    )
    session.add(seg)
    await session.flush()
    return seg


async def _register_asr_error(
    session: AsyncSession, entity_id: uuid.UUID, form: str
) -> None:
    """Register ``form`` as a confirmed ASR error for the entity."""
    session.add(
        EntityAsrErrorDB(
            entity_id=entity_id,
            alias_name=form,
            alias_name_normalized=form.lower(),
        )
    )
    await session.flush()


def _make_session_factory_from_session(session: AsyncSession) -> Any:
    """Return a fake async_sessionmaker that always yields ``session``.

    Lets the service share the test-managed session so writes are visible to the
    assertions in the same transaction (mirrors the scan integration suite).
    """

    class _FakeContextManager:
        async def __aenter__(self) -> AsyncSession:
            return session

        async def __aexit__(self, *args: object) -> bool:
            return False

    class _FakeFactory:
        def __call__(self) -> _FakeContextManager:
            return _FakeContextManager()

    return _FakeFactory()


@pytest.mark.db
@pytest.mark.integration
class TestAsrRecoveryGating:
    """End-to-end: gated ASR forms match with the right provenance, or not at all."""

    async def test_gated_asr_forms_scan_outcomes(
        self, db_session: AsyncSession
    ) -> None:
        await _seed_scaffolding(db_session)

        entity = NamedEntityDB(
            canonical_name=_CANONICAL_NAME,
            canonical_name_normalized=_CANONICAL_NAME.lower(),
            entity_type="person",
            status="active",
            discovery_method="manual",
            confidence=1.0,
            mention_count=0,
            video_count=0,
        )
        db_session.add(entity)
        await db_session.flush()

        alias = EntityAliasDB(
            entity_id=entity.id,
            alias_name=_ALIAS_NAME,
            alias_name_normalized=_ALIAS_NAME.lower(),
            alias_type="name_variant",
            occurrence_count=0,
        )
        db_session.add(alias)
        await db_session.flush()

        # Four registered ASR-error forms spanning the admissibility boundary,
        # plus one collision garble equal to the alias (real names win provenance).
        for form in (
            _ADMISSIBLE_ASR,
            _SINGLE_WORD_ASR,
            _ONE_CHAR_TOKEN_ASR,
            _ALL_STOPWORD_ASR,
            _ALIAS_NAME,  # collision: coincides with a real alias fold
        ):
            await _register_asr_error(db_session, entity.id, form)

        # One segment per probe string, plus the genuine canonical name.
        await _seed_segment(db_session, f"{_ADMISSIBLE_ASR} appears here", 0)
        await _seed_segment(db_session, f"{_SINGLE_WORD_ASR} appears here", 1)
        await _seed_segment(db_session, f"{_ONE_CHAR_TOKEN_ASR} appears here", 2)
        await _seed_segment(db_session, f"{_ALL_STOPWORD_ASR} appears here", 3)
        await _seed_segment(db_session, f"{_CANONICAL_NAME} appears here", 4)
        await _seed_segment(db_session, f"{_ALIAS_NAME} appears here", 5)

        await db_session.commit()

        service = EntityMentionScanService(
            session_factory=_make_session_factory_from_session(db_session)
        )
        await service.scan()

        rows = (await db_session.execute(select(EntityMentionDB))).scalars().all()
        by_text = {r.mention_text.lower(): r for r in rows}

        # (a) Admissible ASR form -> asr_match, no alias link (FR-014).
        admissible = by_text.get(_ADMISSIBLE_ASR)
        assert admissible is not None, (
            "Admissible multi-word ASR form must produce a mention; "
            f"got mentions for {sorted(by_text)}"
        )
        assert admissible.detection_method == DetectionMethod.ASR_MATCH.value
        assert admissible.alias_id is None

        # (b)(c)(d) Rejected forms -> no mention at all.
        assert _SINGLE_WORD_ASR not in by_text, "single-word form must be gated out"
        assert (
            _ONE_CHAR_TOKEN_ASR not in by_text
        ), "one-char-token form must be gated out"
        assert _ALL_STOPWORD_ASR not in by_text, "all-stopword form must be gated out"

        # Genuine canonical-name occurrence -> rule_match (canonical carries no
        # alias id, so alias_id is None, exactly as before this feature).
        canonical = by_text.get(_CANONICAL_NAME.lower())
        assert canonical is not None, "Canonical name occurrence must still match"
        assert canonical.detection_method == DetectionMethod.RULE_MATCH.value
        assert canonical.alias_id is None

        # Collision precedence: the alias text matches as a real name despite an
        # identical registered garble -> rule_match AND the alias id is kept.
        collision = by_text.get(_ALIAS_NAME.lower())
        assert collision is not None, "Alias occurrence must still match"
        assert collision.detection_method == DetectionMethod.RULE_MATCH.value
        assert str(collision.alias_id) == str(alias.id)

    async def test_full_rescan_deletes_stale_asr_match_when_form_unregistered(
        self, db_session: AsyncSession
    ) -> None:
        """The --full delete predicate must cover asr_match (T042 / FR-015).

        A recovered mention whose ASR-error form is later unregistered must be
        removed by the next --full rescan, not left stale. The re-insert is
        ON CONFLICT DO NOTHING, so a rule_match-only delete would leave the
        asr_match row behind SILENTLY (no crash, just a stale/duplicate row) — the
        quiet failure that would corrupt the backfill's revert and counts.
        """
        await _seed_scaffolding(db_session)
        entity = NamedEntityDB(
            canonical_name=_CANONICAL_NAME,
            canonical_name_normalized=_CANONICAL_NAME.lower(),
            entity_type="person",
            status="active",
            discovery_method="manual",
            confidence=1.0,
            mention_count=0,
            video_count=0,
        )
        db_session.add(entity)
        await db_session.flush()
        await _register_asr_error(db_session, entity.id, _ADMISSIBLE_ASR)
        await _seed_segment(db_session, f"{_ADMISSIBLE_ASR} appears here", 0)
        await db_session.commit()

        service = EntityMentionScanService(
            session_factory=_make_session_factory_from_session(db_session)
        )

        async def _asr_rows() -> list[EntityMentionDB]:
            result = await db_session.execute(
                select(EntityMentionDB).where(
                    EntityMentionDB.detection_method == DetectionMethod.ASR_MATCH.value
                )
            )
            return list(result.scalars().all())

        # Scan 1 (--full): the admissible garble is recovered as an asr_match row.
        # (Its text is a garble, not a visible name, so by design it does not count
        # toward the visible-name-based entity.mention_count — see #262.)
        await service.scan(full_rescan=True)
        assert len(await _asr_rows()) == 1

        # Unregister the ASR-error form, then rescan --full. The form is no longer
        # admissible, so scan 2 re-detects nothing for it; the --full delete must
        # remove the now-stale asr_match row (SCAN_DETECTION_METHODS). The re-insert
        # is ON CONFLICT DO NOTHING, so a rule_match-only delete would leave the row
        # behind silently.
        await db_session.execute(
            delete(EntityAsrErrorDB).where(EntityAsrErrorDB.entity_id == entity.id)
        )
        await db_session.commit()

        await service.scan(full_rescan=True)
        assert await _asr_rows() == [], (
            "a stale asr_match row survived a --full rescan after its ASR form was "
            "unregistered — the --full delete predicates must include asr_match "
            "(SCAN_DETECTION_METHODS), or recovered rows accumulate across rescans"
        )
