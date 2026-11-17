"""FR-011 — the per-form ``usable_as_match_pattern`` flag gates matching only.

Feature 111 folds registered ASR-error forms into the match alternation, so a
garble can create a mention. FR-011 adds a reviewer lever to suppress a zero-signal
form (a garble that is also a common phrase, idiom, or wrong-entity collision) from
*matching* while leaving it available to corrections discovery. The two roles live
behind two readers, and the flag must split them:

* the SCAN match reader (``get_multiword_forms_for_matching``) MUST exclude a form
  flagged ``usable_as_match_pattern = false`` — otherwise the suppression does
  nothing and the zero-signal garble keeps producing false mentions;
* the CORRECTIONS-discovery reader (``get_all_multiword_forms_for_discovery``) MUST still return
  it — the flag suppresses matching only, never correction discovery.

And the flag must be DURABLE: ``register_asr_alias`` / ``create_or_update`` runs on
every correction and on every ``--full`` rescan, so a reviewer's ``false`` verdict
must survive re-registration (a bare DELETE did not — it was re-minted). This is the
property that makes FR-011 the real lever rather than a temporary patch.

Neutral placeholder forms only (``zzq``/``qwx`` prefixes), never library content
(Constitution VI). Each form contains a space so it clears the multi-word filter.

MUTATION-VERIFIED:
* drop ``usable_as_match_pattern.is_(True)`` from ``get_multiword_forms_for_matching``
  → ``test_match_reader_excludes_flagged_form`` goes RED;
* make ``create_or_update`` reset the flag on conflict
  → ``test_flag_survives_reregistration`` goes RED.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import EntityAsrError, NamedEntity
from chronovista.db.models import EntityAsrError as EntityAsrErrorDB
from chronovista.db.models import EntityMention as EntityMentionDB
from chronovista.models.entity_asr_error import EntityAsrErrorCreate
from chronovista.models.enums import DetectionMethod
from chronovista.repositories.entity_asr_error_repository import (
    EntityAsrErrorRepository,
)
from chronovista.services.entity_mention_scan_service import (
    EntityMentionScanService,
)
from tests.factories.id_factory import video_id
from tests.integration.services.test_entity_mention_scan_integration import (
    _make_session_factory_from_session,
    _seed_channel,
    _seed_segment,
    _seed_transcript,
    _seed_video,
)
from tests.integration.services.test_entity_mention_scan_integration import (
    _seed_entity as _seed_scan_entity,
)

pytestmark = pytest.mark.asyncio


async def _seed_entity(db_session: AsyncSession, name: str) -> NamedEntity:
    entity = NamedEntity(
        entity_type="person",
        canonical_name=name,
        canonical_name_normalized=name.lower(),
    )
    db_session.add(entity)
    await db_session.flush()
    return entity


async def _add_form(
    db_session: AsyncSession,
    entity: NamedEntity,
    form: str,
    *,
    usable: bool,
) -> None:
    db_session.add(
        EntityAsrError(
            entity_id=entity.id,
            alias_name=form,
            alias_name_normalized=form.lower(),
            case_sensitive=False,
            usable_as_match_pattern=usable,
        )
    )
    await db_session.flush()


@pytest.mark.db
@pytest.mark.integration
class TestFr011GatesMatchingOnly:
    async def test_match_reader_excludes_flagged_form(
        self, db_session: AsyncSession
    ) -> None:
        """The scan match reader drops a ``usable_as_match_pattern=false`` form."""
        entity = await _seed_entity(db_session, "Qwx Fr011 Alpha")
        await _add_form(db_session, entity, "zzq usable alpha", usable=True)
        await _add_form(db_session, entity, "qwx flagged bravo", usable=False)

        repo = EntityAsrErrorRepository()
        by_entity = await repo.get_multiword_forms_for_matching(db_session, [entity.id])
        # str() across the uuid_utils/stdlib UUID boundary (same as the scan service).
        forms = by_entity.get(entity.id) or by_entity.get(str(entity.id)) or []  # type: ignore[call-overload]
        if not forms:  # key may round-trip as a stdlib UUID
            forms = next(
                (v for k, v in by_entity.items() if str(k) == str(entity.id)), []
            )

        assert "zzq usable alpha" in forms
        # The load-bearing assertion. Mutation: drop the is_(True) filter -> RED.
        assert "qwx flagged bravo" not in forms

    async def test_corrections_reader_still_returns_flagged_form(
        self, db_session: AsyncSession
    ) -> None:
        """The flag is match-only: corrections discovery still sees the form.

        The differential that proves FR-011 suppresses *matching*, not the form
        outright — if this reader were also filtered, a legitimate correction-
        discovery input would be lost.
        """
        entity = await _seed_entity(db_session, "Qwx Fr011 Charlie")
        await _add_form(db_session, entity, "qwx flagged delta", usable=False)

        repo = EntityAsrErrorRepository()
        candidates = await repo.get_all_multiword_forms_for_discovery(
            db_session, entity_name="Qwx Fr011 Charlie"
        )
        forms = {row[0] for row in candidates}

        assert "qwx flagged delta" in forms

    async def test_flag_survives_reregistration(self, db_session: AsyncSession) -> None:
        """A reviewer's ``false`` verdict persists across a re-mint (correction / --full).

        ``create_or_update`` on an existing row must bump ``last_seen_at`` only and
        leave ``usable_as_match_pattern`` untouched. Mutation: reset the flag on
        conflict -> RED. This is the durable-lever property a bare DELETE lacked.
        """
        entity = await _seed_entity(db_session, "Qwx Fr011 Echo")
        await _add_form(db_session, entity, "zzq reminted foxtrot", usable=False)

        repo = EntityAsrErrorRepository()
        # Simulate the registration hook re-minting the same normalized form.
        await repo.create_or_update(
            db_session,
            obj_in=EntityAsrErrorCreate(
                # Coerce across the uuid_utils->stdlib boundary (Pydantic UUID is strict).
                entity_id=uuid.UUID(str(entity.id)),
                alias_name="zzq reminted foxtrot",
                alias_name_normalized="zzq reminted foxtrot",
            ),
        )
        await db_session.flush()

        reloaded = await repo.get_by_entity_and_normalized(
            db_session, entity.id, "zzq reminted foxtrot"
        )
        assert reloaded is not None
        # Re-registration did NOT un-suppress the form.
        assert reloaded.usable_as_match_pattern is False


@pytest.mark.db
@pytest.mark.integration
class TestFr011ScanSeam:
    """The flag must gate the SCAN, not only the repository reader."""

    async def test_scan_respects_usable_as_match_pattern_gate(
        self, db_session: AsyncSession
    ) -> None:
        """End-to-end: a flagged garble yields no asr_match; unflagging yields one.

        The garble ``zzq bravo`` is multiword, has no one-char token and is not a
        common phrase, so it clears admission; the canonical name's third token is
        absent from the text, so only the flag can stop the match.
        """
        vid = video_id(seed="fr011_scan_gate")
        await _seed_channel(db_session)
        await _seed_video(db_session, vid)
        await _seed_transcript(db_session, vid)
        await _seed_segment(db_session, vid, text="zzq bravo appears here")
        entity = await _seed_scan_entity(db_session, "Zzq Bravo Delta", "person")
        db_session.add(
            EntityAsrErrorDB(
                entity_id=entity.id,
                alias_name="zzq bravo",
                alias_name_normalized="zzq bravo",
                usable_as_match_pattern=False,
            )
        )
        await db_session.commit()

        service = EntityMentionScanService(
            session_factory=_make_session_factory_from_session(db_session)
        )

        async def _asr_hits() -> int:
            return int(
                (
                    await db_session.execute(
                        select(func.count()).where(
                            EntityMentionDB.entity_id == entity.id,
                            EntityMentionDB.detection_method
                            == DetectionMethod.ASR_MATCH.value,
                            func.lower(EntityMentionDB.mention_text) == "zzq bravo",
                        )
                    )
                ).scalar()
                or 0
            )

        await service.scan(full_rescan=True)
        assert await _asr_hits() == 0, (
            "scan wrote an asr_match for a form flagged "
            "usable_as_match_pattern=False: the flag does not gate the scan"
        )

        await db_session.execute(
            update(EntityAsrErrorDB)
            .where(EntityAsrErrorDB.entity_id == entity.id)
            .values(usable_as_match_pattern=True)
        )
        await db_session.commit()

        await service.scan(full_rescan=True)
        assert await _asr_hits() == 1, (
            "with the flag enabled the garble must yield exactly one asr_match "
            "mention (otherwise the zero above proved nothing about the flag)"
        )
