"""Integration tests for accent-insensitive entity membership (Feature 069).

Real PostgreSQL (the ``db_session`` fixture, which enables the ``unaccent`` extension). These cross the
SQL seam the bug lives in: mention *detection* already folds accents, but the *display* membership
queries re-qualified mentions with ``lower()`` only (case-insensitive, accent-SENSITIVE), hiding an
accented mention from the video panel and the entity's video list. Mock-only tests cannot catch this —
the defect is in the data-matching layer (Constitution V, Cross-Feature Verification).

All fixtures use NEUTRAL placeholder names with synthetic accents (`René`, `Zoë`, `Acme`) — never a
real library entity (Constitution VI).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import EntityAlias as EntityAliasDB
from chronovista.db.models import EntityMention as EntityMentionDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import TranscriptSegment as TranscriptSegmentDB
from chronovista.db.models import Video as VideoDB
from chronovista.db.models import VideoTranscript as VideoTranscriptDB
from chronovista.repositories.entity_mention_repository import EntityMentionRepository

_repo = EntityMentionRepository()

# ---------------------------------------------------------------------------
# Seed helpers (neutral placeholders)
# ---------------------------------------------------------------------------


def _norm(s: str) -> str:
    # Membership does NOT read the normalized column (it uses lower(unaccent(...))), so a simple
    # lowercase is sufficient for this required field in fixtures.
    return s.lower()


async def _seed_video(session: AsyncSession, video_id: str) -> None:
    session.add(
        VideoDB(
            video_id=video_id,
            title=f"Video {video_id}",
            upload_date=datetime(2020, 1, 1, tzinfo=UTC),
            duration=300,
        )
    )
    await session.flush()


async def _seed_transcript(
    session: AsyncSession, video_id: str, language_code: str = "en"
) -> None:
    session.add(
        VideoTranscriptDB(
            video_id=video_id,
            language_code=language_code,
            transcript_text="placeholder",
            transcript_type="manual",
            download_reason="user_request",
            is_cc=False,
            is_auto_synced=False,
            track_kind="standard",
            source="youtube_transcript_api",
            has_corrections=False,
            correction_count=0,
            last_corrected_at=None,
        )
    )
    await session.flush()


async def _seed_entity(
    session: AsyncSession, canonical_name: str, entity_type: str = "person"
) -> uuid.UUID:
    entity = NamedEntityDB(
        canonical_name=canonical_name,
        canonical_name_normalized=_norm(canonical_name),
        entity_type=entity_type,
        status="active",
    )
    session.add(entity)
    await session.flush()
    return uuid.UUID(str(entity.id))


async def _seed_alias(
    session: AsyncSession,
    entity_id: uuid.UUID,
    alias_name: str,
    alias_type: str = "name_variant",
) -> None:
    session.add(
        EntityAliasDB(
            entity_id=entity_id,
            alias_name=alias_name,
            alias_name_normalized=_norm(alias_name),
            alias_type=alias_type,
        )
    )
    await session.flush()


async def _seed_segment(
    session: AsyncSession,
    video_id: str,
    text: str,
    sequence_number: int = 0,
    language_code: str = "en",
) -> uuid.UUID:
    seg = TranscriptSegmentDB(
        video_id=video_id,
        language_code=language_code,
        text=text,
        start_time=float(sequence_number),
        duration=2.0,
        end_time=float(sequence_number) + 2.0,
        sequence_number=sequence_number,
    )
    session.add(seg)
    await session.flush()
    return uuid.UUID(str(seg.id))


async def _seed_mention(
    session: AsyncSession,
    entity_id: uuid.UUID,
    video_id: str,
    mention_text: str,
    *,
    mention_source: str = "transcript",
    detection_method: str = "rule_match",
    segment_id: uuid.UUID | None = None,
    language_code: str | None = "en",
) -> None:
    session.add(
        EntityMentionDB(
            entity_id=entity_id,
            video_id=video_id,
            segment_id=segment_id,
            mention_text=mention_text,
            mention_source=mention_source,
            detection_method=detection_method,
            language_code=language_code,
        )
    )
    await session.flush()


async def _panel_entity_ids(session: AsyncSession, video_id: str) -> set[str]:
    rows = await _repo.get_video_entity_associations(session, video_id=video_id)
    return {r["entity_id"] for r in rows}


async def _panel_row(
    session: AsyncSession, video_id: str, entity_id: uuid.UUID
) -> dict | None:
    rows = await _repo.get_video_entity_associations(session, video_id=video_id)
    return next((r for r in rows if r["entity_id"] == str(entity_id)), None)


async def _video_list(
    session: AsyncSession, entity_id: uuid.UUID
) -> tuple[list[dict], int]:
    return await _repo.get_entity_video_list(session, entity_id)


# ---------------------------------------------------------------------------
# US1 — an accented mention surfaces its entity
# ---------------------------------------------------------------------------


class TestAccentedMembershipSurfaces:
    async def test_accented_mention_surfaces_on_video_panel(
        self, db_session: AsyncSession
    ) -> None:
        vid = "vidRene0001"
        await _seed_video(db_session, vid)
        eid = await _seed_entity(db_session, "Rene")  # stored WITHOUT accent
        await _seed_mention(
            db_session, eid, vid, "René", mention_source="description"
        )  # mention WITH accent
        await db_session.flush()

        assert str(eid) in await _panel_entity_ids(db_session, vid)

    async def test_accented_mention_surfaces_on_entity_video_list(
        self, db_session: AsyncSession
    ) -> None:
        vid = "vidRene0002"
        await _seed_video(db_session, vid)
        eid = await _seed_entity(db_session, "Rene")
        await _seed_mention(db_session, eid, vid, "René", mention_source="description")
        await db_session.flush()

        videos, total = await _video_list(db_session, eid)
        assert total >= 1
        assert vid in {v["video_id"] for v in videos}

    async def test_symmetric_direction(self, db_session: AsyncSession) -> None:
        # Stored name carries the accent; the mention lacks it (the mirror of the primary case).
        vid = "vidZoe0001"
        await _seed_video(db_session, vid)
        eid = await _seed_entity(db_session, "Zoë")  # stored WITH accent
        await _seed_mention(
            db_session, eid, vid, "Zoe", mention_source="description"
        )  # mention WITHOUT
        await db_session.flush()

        assert str(eid) in await _panel_entity_ids(db_session, vid)
        _, total = await _video_list(db_session, eid)
        assert total >= 1

    async def test_pure_ascii_unchanged(self, db_session: AsyncSession) -> None:
        vid = "vidAscii001"
        await _seed_video(db_session, vid)
        eid = await _seed_entity(db_session, "Acme Corp")
        await _seed_mention(
            db_session, eid, vid, "Acme Corp", mention_source="description"
        )
        await db_session.flush()

        assert str(eid) in await _panel_entity_ids(db_session, vid)

    async def test_no_spurious_association(self, db_session: AsyncSession) -> None:
        # A mention whose text is an unrelated word must NOT associate to the entity.
        vid = "vidNoAssoc1"
        await _seed_video(db_session, vid)
        eid = await _seed_entity(db_session, "Rene")
        await _seed_mention(
            db_session, eid, vid, "unrelated", mention_source="description"
        )
        await db_session.flush()

        assert str(eid) not in await _panel_entity_ids(db_session, vid)

    async def test_asr_error_alias_stays_excluded(
        self, db_session: AsyncSession
    ) -> None:
        # The bare common word is catalogued as an asr_error alias → excluded from visible names,
        # even under folding. The full-name accent variant still surfaces.
        vid = "vidAcme0001"
        await _seed_video(db_session, vid)
        eid = await _seed_entity(db_session, "Aria Acme")  # full name (person)
        await _seed_alias(
            db_session, eid, "acme", alias_type="asr_error"
        )  # bare common word
        # A bare-word mention (would be a false positive) and a real full-name accented mention.
        await _seed_mention(db_session, eid, vid, "acme", mention_source="description")
        await _seed_mention(
            db_session, eid, vid, "Aria Acmé", mention_source="description"
        )
        await db_session.flush()

        panel = await _panel_row(db_session, vid, eid)
        assert panel is not None  # surfaces via the full-name accent variant
        # It must NOT surface via the bare asr_error word alone: prove by removing the full-name
        # mention in a sibling video.
        vid2 = "vidAcme0002"
        await _seed_video(db_session, vid2)
        await _seed_mention(db_session, eid, vid2, "acme", mention_source="description")
        await db_session.flush()
        assert str(eid) not in await _panel_entity_ids(db_session, vid2)

    async def test_description_only_per_aggregate_counts(
        self, db_session: AsyncSession
    ) -> None:
        # The seam: a description-only accented association is present on BOTH surfaces, shows 1 on
        # the panel (presence-collapsed) and 0 on the video-list per-video transcript count (by
        # design, NOT a fold-induced omission — SC-003).
        vid = "vidSeam0001"
        await _seed_video(db_session, vid)
        eid = await _seed_entity(db_session, "Zoe")  # stored plain
        await _seed_mention(db_session, eid, vid, "Zoë", mention_source="description")
        await db_session.flush()

        panel = await _panel_row(db_session, vid, eid)
        assert panel is not None
        assert panel["mention_count"] == 1  # description collapses to presence

        videos, total = await _video_list(db_session, eid)
        assert total >= 1
        row = next(v for v in videos if v["video_id"] == vid)
        assert row["mention_count"] == 0  # transcript-only per-video count, by design


# ---------------------------------------------------------------------------
# US2 — counters stay consistent with what is shown (folded recompute)
# ---------------------------------------------------------------------------


async def _entity_counts(
    session: AsyncSession, entity_id: uuid.UUID
) -> tuple[int, int]:
    row = (
        await session.execute(
            select(NamedEntityDB.mention_count, NamedEntityDB.video_count).where(
                NamedEntityDB.id == entity_id
            )
        )
    ).one()
    return int(row.mention_count), int(row.video_count)


class TestFoldedRecount:
    async def test_recount_includes_accented_mentions(
        self, db_session: AsyncSession
    ) -> None:
        vid = "vidRcnt0001"
        await _seed_video(db_session, vid)
        eid = await _seed_entity(db_session, "Rene")  # stored plain
        await _seed_alias(
            db_session, eid, "Rene"
        )  # a visible alias to count occurrences
        await _seed_mention(db_session, eid, vid, "René", mention_source="description")
        await db_session.flush()

        # Stored counters start at their create-time defaults (0).
        assert await _entity_counts(db_session, eid) == (0, 0)

        await _repo.update_entity_counters(db_session, [eid])
        await _repo.update_alias_counters(db_session, [eid])
        await db_session.flush()

        mc, vc = await _entity_counts(db_session, eid)
        assert (
            mc >= 1 and vc >= 1
        )  # the accented mention is now counted (all-source stored counter)
        occ = (
            await db_session.execute(
                select(EntityAliasDB.occurrence_count).where(
                    EntityAliasDB.entity_id == eid
                )
            )
        ).scalar_one()
        assert occ >= 1  # alias occurrence count includes the accented mention

    async def test_recount_idempotent(self, db_session: AsyncSession) -> None:
        vid = "vidRcnt0002"
        await _seed_video(db_session, vid)
        eid = await _seed_entity(db_session, "Zoe")
        await _seed_mention(db_session, eid, vid, "Zoë", mention_source="description")
        await db_session.flush()

        before = await _entity_counts(db_session, eid)
        await _repo.update_entity_counters(db_session, [eid])
        await db_session.flush()
        first = await _entity_counts(db_session, eid)
        # The first run MUST actually change state (meaningful idempotency test).
        assert first != before
        await _repo.update_entity_counters(db_session, [eid])
        await db_session.flush()
        second = await _entity_counts(db_session, eid)
        assert second == first  # second run is a no-op

    async def test_recount_common_word_not_inflated(
        self, db_session: AsyncSession
    ) -> None:
        vid = "vidRcnt0003"
        await _seed_video(db_session, vid)
        eid = await _seed_entity(db_session, "Aria Acme")
        await _seed_alias(db_session, eid, "acme", alias_type="asr_error")
        # A bare common-word mention that must NOT count, plus one real full-name mention.
        await _seed_mention(db_session, eid, vid, "acme", mention_source="description")
        await _seed_mention(
            db_session, eid, vid, "Aria Acmé", mention_source="description"
        )
        await db_session.flush()

        await _repo.update_entity_counters(db_session, [eid])
        await db_session.flush()
        mc, _ = await _entity_counts(db_session, eid)
        # Only the full-name mention counts; the bare asr_error word is excluded (not inflated).
        assert mc == 1

    async def test_list_filter_sort_reflect_recount(
        self, db_session: AsyncSession
    ) -> None:
        # FR-011: the entity-list has-mentions filter and mention_count sort read the stored counter,
        # so they reflect the accented entity only AFTER the recount.
        vid = "vidRcnt0004"
        await _seed_video(db_session, vid)
        eid = await _seed_entity(db_session, "Rene")
        await _seed_mention(db_session, eid, vid, "René", mention_source="description")
        await db_session.flush()

        # Before recount: stored counter is 0 → would be filtered out by has-mentions.
        assert (await _entity_counts(db_session, eid))[0] == 0

        await _repo.update_entity_counters(db_session, [eid])
        await db_session.flush()

        # After recount: mention_count > 0, so the entity passes the has-mentions filter.
        rows = (
            await db_session.execute(
                select(NamedEntityDB.id).where(
                    NamedEntityDB.mention_count > 0, NamedEntityDB.id == eid
                )
            )
        ).all()
        assert len(rows) == 1


class TestRecountDryRunSeam:
    """The recount command's dry-run must NOT persist — the real get_session seam.

    Regression for a bug found in deployment: ``db_manager.get_session`` commits on normal scope
    exit, so a dry-run that merely skipped ``commit`` still auto-committed its pending UPDATEs. The
    CLI unit test mocked the session and only checked "commit not called", so it missed the ambient
    auto-commit (a mocked collaborator cannot fail the way the real one does). ``_recount_counters``
    now rolls back explicitly on dry-run; this crosses the real DB seam to prove it.
    """

    async def test_dry_run_persists_nothing_then_apply_writes(
        self, db_session: AsyncSession
    ) -> None:
        from chronovista.cli.entity_commands import _recount_counters

        vid = "vidDrySeam1"
        await _seed_video(db_session, vid)
        eid = await _seed_entity(db_session, "Rene")
        await _seed_mention(db_session, eid, vid, "René", mention_source="description")
        # Commit the seed so a rollback inside the dry-run cannot discard it.
        await db_session.commit()

        before = await _entity_counts(db_session, eid)
        assert before == (0, 0)

        # Dry-run computes a real change but MUST NOT persist it.
        _, entities_changed, _ = await _recount_counters(db_session, dry_run=True)
        assert entities_changed >= 1, "dry-run should detect a pending change"
        assert (
            await _entity_counts(db_session, eid) == before
        ), "dry-run persisted counters — the rollback did not take effect"

        # Apply DOES persist.
        await _recount_counters(db_session, dry_run=False)
        assert await _entity_counts(db_session, eid) != before
