"""
Integration tests for EntityMentionScanService.

Tests end-to-end scanning behaviour against a real PostgreSQL database.
Each test uses the db_session fixture from tests/integration/conftest.py which
creates all tables fresh per test and rolls back on completion.

The session factory used by the service is replaced with a factory that reuses
the test session so all writes/reads participate in the same transaction that
the test can inspect.

Feature 038 -- Entity Mention Detection (T016)
Feature 044 -- Data Accuracy & Search Reliability (T011)

Test coverage:
1. End-to-end scan: entities + aliases + segments → mention records
2. Idempotent re-run: second scan creates zero new mentions
3. Counter updates: mention_count / video_count updated after scan
4. Word boundary matching: "Aaronson" must NOT match entity "Aaron"
5. Multiple aliases: all aliases of an entity trigger mentions
6. Incremental scan: new_entities_only scans only newly added entity
7. ASR-error alias exclusion: asr_error alias mentions excluded from counters (T011)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import (
    Channel as ChannelDB,
    EntityAlias as EntityAliasDB,
    EntityMention as EntityMentionDB,
    NamedEntity as NamedEntityDB,
    TranscriptSegment as TranscriptSegmentDB,
    Video as VideoDB,
    VideoTranscript as VideoTranscriptDB,
)
from chronovista.models.enums import DetectionMethod
from chronovista.services.entity_mention_scan_service import (
    EntityMentionScanService,
    ScanResult,
)
from tests.factories.id_factory import channel_id, video_id

# Factory-generated default IDs — guarantees valid format (11-char video, 24-char channel)
DEFAULT_CHANNEL_ID = channel_id(seed="scan_test")

# CRITICAL: This line ensures async tests work with coverage tools,
# avoiding silent test-skipping (see CLAUDE.md).
pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers for test data construction
# ---------------------------------------------------------------------------


def _new_uuid() -> uuid.UUID:
    """Return a fresh UUID4."""
    return uuid.uuid4()


async def _seed_channel(session: AsyncSession, ch_id: str = DEFAULT_CHANNEL_ID) -> None:
    """Insert a minimal Channel row required as FK for videos."""
    channel = ChannelDB(
        channel_id=ch_id,
        title="Integration Test Channel",
        description="Channel for scan service integration tests",
        is_subscribed=False,
    )
    session.add(channel)
    await session.flush()


async def _seed_video(
    session: AsyncSession,
    vid_id: str,
    ch_id: str = DEFAULT_CHANNEL_ID,
) -> None:
    """Insert a minimal Video row required as FK for transcripts."""
    video = VideoDB(
        video_id=vid_id,
        channel_id=ch_id,
        title=f"Video {vid_id}",
        description="Integration test video",
        upload_date=datetime(2024, 1, 1, tzinfo=UTC),
        duration=120,
        made_for_kids=False,
        self_declared_made_for_kids=False,
    )
    session.add(video)
    await session.flush()


async def _seed_transcript(
    session: AsyncSession,
    vid_id: str,
    language_code: str = "en",
) -> None:
    """Insert a minimal VideoTranscript row required as FK for segments."""
    transcript = VideoTranscriptDB(
        video_id=vid_id,
        language_code=language_code,
        transcript_text="",
        transcript_type="auto",
        download_reason="user_request",
        is_cc=False,
        is_auto_synced=True,
        track_kind="standard",
        source="youtube_transcript_api",
    )
    session.add(transcript)
    await session.flush()


async def _seed_segment(
    session: AsyncSession,
    vid_id: str,
    text: str,
    seg_id: int | None = None,
    language_code: str = "en",
    start_time: float = 0.0,
    sequence_number: int = 0,
) -> TranscriptSegmentDB:
    """Insert a TranscriptSegment and return the ORM object."""
    seg = TranscriptSegmentDB(
        video_id=vid_id,
        language_code=language_code,
        text=text,
        has_correction=False,
        start_time=start_time,
        duration=5.0,
        end_time=start_time + 5.0,
        sequence_number=sequence_number,
    )
    session.add(seg)
    await session.flush()
    return seg


async def _seed_entity(
    session: AsyncSession,
    canonical_name: str,
    entity_type: str = "person",
    status: str = "active",
) -> NamedEntityDB:
    """Insert a NamedEntity and return the ORM object."""
    entity = NamedEntityDB(
        canonical_name=canonical_name,
        canonical_name_normalized=canonical_name.lower(),
        entity_type=entity_type,
        status=status,
        discovery_method="manual",
        confidence=1.0,
        mention_count=0,
        video_count=0,
        channel_count=0,
    )
    session.add(entity)
    await session.flush()
    return entity


async def _seed_alias(
    session: AsyncSession,
    entity_id: uuid.UUID,
    alias_name: str,
    alias_type: str = "name_variant",
) -> EntityAliasDB:
    """Insert an EntityAlias and return the ORM object."""
    alias = EntityAliasDB(
        entity_id=entity_id,
        alias_name=alias_name,
        alias_name_normalized=alias_name.lower(),
        alias_type=alias_type,
        occurrence_count=0,
    )
    session.add(alias)
    await session.flush()
    return alias


def _make_session_factory_from_session(
    session: AsyncSession,
) -> Any:
    """
    Build a fake async_sessionmaker that always returns the provided session.

    This lets the service use the test-managed session so all writes
    are visible to test assertions within the same transaction.
    """

    class _FakeContextManager:
        async def __aenter__(self) -> AsyncSession:
            return session

        async def __aexit__(self, *args: object) -> bool:
            # Do NOT close or roll back — the test fixture handles that.
            return False

    class _FakeFactory:
        def __call__(self) -> _FakeContextManager:
            return _FakeContextManager()

    return _FakeFactory()

# ---------------------------------------------------------------------------
# T016-01: End-to-end scan
# ---------------------------------------------------------------------------


class TestEndToEndScan:
    """Create entities + aliases + segments, run scan, verify mention records."""

    async def test_single_entity_mention_created(
        self, db_session: AsyncSession
    ) -> None:
        """
        A single active entity whose name appears in a segment text must produce
        exactly one EntityMention record with correct field values.
        """
        await _seed_channel(db_session)
        await _seed_video(db_session, video_id(seed="ee_001"))
        await _seed_transcript(db_session, video_id(seed="ee_001"))

        seg = await _seed_segment(
            db_session, video_id(seed="ee_001"), text="Aaron is a famous person", start_time=0.0
        )
        entity = await _seed_entity(db_session, "Aaron", entity_type="person")

        await db_session.commit()

        factory = _make_session_factory_from_session(db_session)
        service = EntityMentionScanService(session_factory=factory)
        result: ScanResult = await service.scan()

        # Query mentions inserted
        rows = (
            await db_session.execute(select(EntityMentionDB))
        ).scalars().all()

        assert len(rows) == 1, f"Expected 1 mention, got {len(rows)}"
        mention = rows[0]
        assert str(mention.entity_id) == str(entity.id)
        assert mention.segment_id == seg.id
        assert mention.video_id == video_id(seed="ee_001")
        assert mention.language_code == "en"
        assert mention.mention_text.lower() == "aaron"
        assert mention.detection_method == DetectionMethod.RULE_MATCH.value

        assert result.mentions_found == 1
        assert result.segments_scanned >= 1

    async def test_no_mention_when_entity_not_in_text(
        self, db_session: AsyncSession
    ) -> None:
        """When the segment text does not contain the entity name, no mention is created."""
        await _seed_channel(db_session)
        await _seed_video(db_session, video_id(seed="ee_002"))
        await _seed_transcript(db_session, video_id(seed="ee_002"))

        await _seed_segment(
            db_session, video_id(seed="ee_002"), text="Today we discuss climate change"
        )
        await _seed_entity(db_session, "Barack Obama", entity_type="person")

        await db_session.commit()

        factory = _make_session_factory_from_session(db_session)
        service = EntityMentionScanService(session_factory=factory)
        result = await service.scan()

        rows = (
            await db_session.execute(select(EntityMentionDB))
        ).scalars().all()

        assert len(rows) == 0
        assert result.mentions_found == 0

    async def test_correct_detection_method_and_confidence(
        self, db_session: AsyncSession
    ) -> None:
        """Scan must store detection_method=rule_match and confidence=1.0."""
        await _seed_channel(db_session)
        await _seed_video(db_session, video_id(seed="ee_003"))
        await _seed_transcript(db_session, video_id(seed="ee_003"))

        await _seed_segment(
            db_session, video_id(seed="ee_003"), text="Tesla released a new model"
        )
        await _seed_entity(db_session, "Tesla", entity_type="organization")

        await db_session.commit()

        factory = _make_session_factory_from_session(db_session)
        service = EntityMentionScanService(session_factory=factory)
        await service.scan()

        rows = (
            await db_session.execute(select(EntityMentionDB))
        ).scalars().all()

        assert len(rows) == 1
        assert rows[0].detection_method == DetectionMethod.RULE_MATCH.value
        assert rows[0].confidence == 1.0


# ---------------------------------------------------------------------------
# T016-02: Idempotent re-run
# ---------------------------------------------------------------------------


class TestIdempotentRerun:
    """Running scan twice must not create duplicate mention records."""

    async def test_second_scan_creates_zero_new_mentions(
        self, db_session: AsyncSession
    ) -> None:
        """
        The second scan (incremental mode) must produce 0 new mentions when
        all matches are already present from the first scan.
        """
        await _seed_channel(db_session)
        await _seed_video(db_session, video_id(seed="ir_001"))
        await _seed_transcript(db_session, video_id(seed="ir_001"))

        await _seed_segment(
            db_session, video_id(seed="ir_001"), text="Google launched a new service"
        )
        await _seed_entity(db_session, "Google", entity_type="organization")

        await db_session.commit()

        factory = _make_session_factory_from_session(db_session)
        service = EntityMentionScanService(session_factory=factory)
        # First scan
        result1 = await service.scan()
        assert result1.mentions_found >= 1

        # Second scan (same session, same data)
        result2 = await service.scan()

        # No new mentions inserted; skipped count covers the prior match
        assert result2.mentions_found == 0

        # Total rows unchanged after second scan
        rows = (
            await db_session.execute(select(EntityMentionDB))
        ).scalars().all()
        assert len(rows) == result1.mentions_found

    async def test_full_rescan_replaces_existing_mentions(
        self, db_session: AsyncSession
    ) -> None:
        """
        full_rescan=True must delete existing mentions and re-detect,
        ending with the same total (not doubled).
        """
        await _seed_channel(db_session)
        await _seed_video(db_session, video_id(seed="ir_002"))
        await _seed_transcript(db_session, video_id(seed="ir_002"))

        await _seed_segment(
            db_session, video_id(seed="ir_002"), text="Microsoft acquired Activision"
        )
        await _seed_entity(db_session, "Microsoft", entity_type="organization")

        await db_session.commit()

        factory = _make_session_factory_from_session(db_session)
        service = EntityMentionScanService(session_factory=factory)
        # First scan
        result1 = await service.scan()
        count_after_first = len(
            (await db_session.execute(select(EntityMentionDB))).scalars().all()
        )

        # Full rescan
        result2 = await service.scan(full_rescan=True)
        count_after_full = len(
            (await db_session.execute(select(EntityMentionDB))).scalars().all()
        )

        # Row count must match — full rescan replaces, not doubles
        assert count_after_full == count_after_first
        assert result2.mentions_found >= 1


# ---------------------------------------------------------------------------
# T016-03: Counter updates
# ---------------------------------------------------------------------------


class TestCounterUpdates:
    """Verify mention_count and video_count on named_entities after scan."""

    async def test_mention_count_updated_after_scan(
        self, db_session: AsyncSession
    ) -> None:
        """
        After a successful scan, named_entities.mention_count must equal
        the number of segments that matched the entity.
        """
        await _seed_channel(db_session)
        await _seed_video(db_session, video_id(seed="cu_001"))
        await _seed_transcript(db_session, video_id(seed="cu_001"))

        # Two segments both mention the entity
        await _seed_segment(
            db_session, video_id(seed="cu_001"), text="SpaceX launched a rocket", sequence_number=0
        )
        await _seed_segment(
            db_session, video_id(seed="cu_001"), text="SpaceX is building Starship", start_time=10.0, sequence_number=1
        )
        entity = await _seed_entity(db_session, "SpaceX", entity_type="organization")

        await db_session.commit()

        factory = _make_session_factory_from_session(db_session)
        service = EntityMentionScanService(session_factory=factory)
        await service.scan()

        # Re-fetch entity to see updated counters
        await db_session.refresh(entity)

        assert entity.mention_count == 2, (
            f"Expected mention_count=2, got {entity.mention_count}"
        )

    async def test_video_count_updated_after_scan(
        self, db_session: AsyncSession
    ) -> None:
        """
        video_count must reflect the number of distinct videos in which
        the entity appears.
        """
        await _seed_channel(db_session)

        # Two videos, same entity mentioned in each
        for vid_idx, vid_id in enumerate([video_id(seed="vc_001"), video_id(seed="vc_002")]):
            await _seed_video(db_session, vid_id)
            await _seed_transcript(db_session, vid_id)
            await _seed_segment(
                db_session, vid_id, text="OpenAI released GPT-5", sequence_number=vid_idx
            )

        entity = await _seed_entity(db_session, "OpenAI", entity_type="organization")

        await db_session.commit()

        factory = _make_session_factory_from_session(db_session)
        service = EntityMentionScanService(session_factory=factory)
        await service.scan()

        await db_session.refresh(entity)

        assert entity.video_count == 2, (
            f"Expected video_count=2, got {entity.video_count}"
        )
        assert entity.mention_count == 2

    async def test_counters_not_updated_in_dry_run(
        self, db_session: AsyncSession
    ) -> None:
        """Counter fields must remain 0 after a dry-run scan."""
        await _seed_channel(db_session)
        await _seed_video(db_session, video_id(seed="cu_002"))
        await _seed_transcript(db_session, video_id(seed="cu_002"))

        await _seed_segment(
            db_session, video_id(seed="cu_002"), text="Nvidia announced new GPUs"
        )
        entity = await _seed_entity(db_session, "Nvidia", entity_type="organization")

        await db_session.commit()

        factory = _make_session_factory_from_session(db_session)
        service = EntityMentionScanService(session_factory=factory)
        await service.scan(dry_run=True)

        await db_session.refresh(entity)

        # In dry-run mode, counters must remain untouched
        assert entity.mention_count == 0
        assert entity.video_count == 0


# ---------------------------------------------------------------------------
# T016-04: Word boundary matching
# ---------------------------------------------------------------------------


class TestWordBoundaryMatching:
    """Verify that entity matching respects word boundaries."""

    async def test_no_match_for_substring(
        self, db_session: AsyncSession
    ) -> None:
        """
        'Aaronson' must NOT match entity 'Aaron' because 'Aaron' ends mid-word.
        The service uses Python \\b word-boundary regex which prevents this.
        """
        await _seed_channel(db_session)
        await _seed_video(db_session, video_id(seed="wb_001"))
        await _seed_transcript(db_session, video_id(seed="wb_001"))

        # Text contains "Aaronson" — substring of entity name pattern
        await _seed_segment(
            db_session, video_id(seed="wb_001"), text="Aaronson wrote the book"
        )
        await _seed_entity(db_session, "Aaron", entity_type="person")

        await db_session.commit()

        factory = _make_session_factory_from_session(db_session)
        service = EntityMentionScanService(session_factory=factory)
        result = await service.scan()

        rows = (
            await db_session.execute(select(EntityMentionDB))
        ).scalars().all()

        assert len(rows) == 0, (
            f"Expected 0 mentions (word boundary mismatch), got {len(rows)}"
        )
        assert result.mentions_found == 0

    async def test_match_when_entity_stands_alone(
        self, db_session: AsyncSession
    ) -> None:
        """
        'Aaron is here' must produce a match for entity 'Aaron' because
        'Aaron' is a complete word.
        """
        await _seed_channel(db_session)
        await _seed_video(db_session, video_id(seed="wb_002"))
        await _seed_transcript(db_session, video_id(seed="wb_002"))

        await _seed_segment(
            db_session, video_id(seed="wb_002"), text="Aaron is here today"
        )
        await _seed_entity(db_session, "Aaron", entity_type="person")

        await db_session.commit()

        factory = _make_session_factory_from_session(db_session)
        service = EntityMentionScanService(session_factory=factory)
        result = await service.scan()

        rows = (
            await db_session.execute(select(EntityMentionDB))
        ).scalars().all()

        assert len(rows) == 1
        assert result.mentions_found == 1

    async def test_case_insensitive_match(
        self, db_session: AsyncSession
    ) -> None:
        """Entity matching is case-insensitive: 'google' must match entity 'Google'."""
        await _seed_channel(db_session)
        await _seed_video(db_session, video_id(seed="wb_003"))
        await _seed_transcript(db_session, video_id(seed="wb_003"))

        # Text has lowercase 'google'
        await _seed_segment(
            db_session, video_id(seed="wb_003"), text="I searched on google for the answer"
        )
        await _seed_entity(db_session, "Google", entity_type="organization")

        await db_session.commit()

        factory = _make_session_factory_from_session(db_session)
        service = EntityMentionScanService(session_factory=factory)
        result = await service.scan()

        rows = (
            await db_session.execute(select(EntityMentionDB))
        ).scalars().all()

        assert len(rows) == 1
        assert result.mentions_found == 1

    async def test_match_at_sentence_boundaries(
        self, db_session: AsyncSession
    ) -> None:
        """Entity at the start or end of text is still detected correctly."""
        await _seed_channel(db_session)
        await _seed_video(db_session, video_id(seed="wb_004"))
        await _seed_transcript(db_session, video_id(seed="wb_004"))

        # Entity at start of text
        await _seed_segment(
            db_session,
            video_id(seed="wb_004"),
            text="Python is a programming language",
            sequence_number=0,
        )
        # Entity at end of text
        await _seed_segment(
            db_session,
            video_id(seed="wb_004"),
            text="We program in Python",
            start_time=10.0,
            sequence_number=1,
        )
        await _seed_entity(db_session, "Python", entity_type="technical_term")

        await db_session.commit()

        factory = _make_session_factory_from_session(db_session)
        service = EntityMentionScanService(session_factory=factory)
        result = await service.scan()

        assert result.mentions_found == 2


# ---------------------------------------------------------------------------
# T016-05: Multiple aliases
# ---------------------------------------------------------------------------


class TestMultipleAliases:
    """Verify that all aliases of an entity trigger mentions."""

    async def test_canonical_and_aliases_all_match(
        self, db_session: AsyncSession
    ) -> None:
        """
        Entity with canonical name + 2 aliases: all three names must be
        detected in distinct segments.
        """
        await _seed_channel(db_session)
        await _seed_video(db_session, video_id(seed="ma_001"))
        await _seed_transcript(db_session, video_id(seed="ma_001"))

        # One segment per name form
        await _seed_segment(
            db_session, video_id(seed="ma_001"), text="Elon Musk spoke at the conference", sequence_number=0
        )
        await _seed_segment(
            db_session, video_id(seed="ma_001"), text="Musk announced new ventures", start_time=10.0, sequence_number=1
        )
        await _seed_segment(
            db_session, video_id(seed="ma_001"), text="Tesla CEO discussed the roadmap", start_time=20.0, sequence_number=2
        )

        entity = await _seed_entity(db_session, "Elon Musk", entity_type="person")
        await _seed_alias(db_session, entity.id, "Musk")
        await _seed_alias(db_session, entity.id, "Tesla CEO")

        await db_session.commit()

        factory = _make_session_factory_from_session(db_session)
        service = EntityMentionScanService(session_factory=factory)
        result = await service.scan()

        rows = (
            await db_session.execute(
                select(EntityMentionDB).where(
                    EntityMentionDB.entity_id == entity.id
                )
            )
        ).scalars().all()

        # All three alias forms should have been matched
        assert len(rows) == 3, (
            f"Expected 3 mentions (canonical + 2 aliases), got {len(rows)}: "
            f"{[r.mention_text for r in rows]}"
        )
        assert result.mentions_found == 3

    async def test_alias_not_duplicated_when_same_as_canonical(
        self, db_session: AsyncSession
    ) -> None:
        """
        If an alias name equals the canonical name, it must not produce
        a duplicate pattern or extra mentions.
        """
        await _seed_channel(db_session)
        await _seed_video(db_session, video_id(seed="ma_002"))
        await _seed_transcript(db_session, video_id(seed="ma_002"))

        await _seed_segment(
            db_session, video_id(seed="ma_002"), text="Amazon shipped the order"
        )
        entity = await _seed_entity(db_session, "Amazon", entity_type="organization")
        # Alias deliberately duplicates canonical name
        await _seed_alias(db_session, entity.id, "Amazon")

        await db_session.commit()

        factory = _make_session_factory_from_session(db_session)
        service = EntityMentionScanService(session_factory=factory)
        result = await service.scan()

        rows = (
            await db_session.execute(select(EntityMentionDB))
        ).scalars().all()

        # Exactly one mention, not two (deduplication within pattern builder)
        assert len(rows) == 1
        assert result.mentions_found == 1


# ---------------------------------------------------------------------------
# T016-06: Incremental scan (new_entities_only)
# ---------------------------------------------------------------------------


class TestIncrementalScan:
    """Verify that new_entities_only=True only scans entities with zero mentions."""

    async def test_new_entities_only_scans_zero_mention_entity(
        self, db_session: AsyncSession
    ) -> None:
        """
        After a first full scan, adding a new entity and running with
        new_entities_only=True must scan ONLY the new entity.
        """
        await _seed_channel(db_session)
        await _seed_video(db_session, video_id(seed="inc_01"))
        await _seed_transcript(db_session, video_id(seed="inc_01"))

        await _seed_segment(
            db_session, video_id(seed="inc_01"), text="Python and JavaScript are both popular", sequence_number=0
        )
        await _seed_segment(
            db_session, video_id(seed="inc_01"), text="I prefer Python for scripting", start_time=10.0, sequence_number=1
        )

        entity_python = await _seed_entity(
            db_session, "Python", entity_type="technical_term"
        )

        await db_session.commit()

        factory = _make_session_factory_from_session(db_session)
        service = EntityMentionScanService(session_factory=factory)
        # First scan: Python gets mentions
        result1 = await service.scan()
        assert result1.mentions_found >= 1

        # Add a new entity that has no mentions yet
        entity_js = await _seed_entity(
            db_session, "JavaScript", entity_type="technical_term"
        )
        await db_session.commit()

        # Incremental scan — only JavaScript (zero mentions) should be processed
        result2 = await service.scan(new_entities_only=True)

        js_rows = (
            await db_session.execute(
                select(EntityMentionDB).where(
                    EntityMentionDB.entity_id == entity_js.id
                )
            )
        ).scalars().all()

        python_rows_before = result1.mentions_found
        python_rows_after = len(
            (
                await db_session.execute(
                    select(EntityMentionDB).where(
                        EntityMentionDB.entity_id == entity_python.id
                    )
                )
            ).scalars().all()
        )

        # JavaScript must now have mentions
        assert len(js_rows) >= 1, (
            f"Expected JavaScript mentions after incremental scan, got {len(js_rows)}"
        )
        # Python mention count must be unchanged (already had mentions → skipped)
        assert python_rows_after == python_rows_before, (
            f"Python mentions changed unexpectedly: {python_rows_before} → {python_rows_after}"
        )

    async def test_new_entities_only_noop_when_all_entities_have_mentions(
        self, db_session: AsyncSession
    ) -> None:
        """
        With new_entities_only=True and all entities already having mentions,
        the result must show 0 mentions_found.
        """
        await _seed_channel(db_session)
        await _seed_video(db_session, video_id(seed="inc_02"))
        await _seed_transcript(db_session, video_id(seed="inc_02"))

        await _seed_segment(
            db_session, video_id(seed="inc_02"), text="Meta announced new features"
        )
        await _seed_entity(db_session, "Meta", entity_type="organization")

        await db_session.commit()

        factory = _make_session_factory_from_session(db_session)
        service = EntityMentionScanService(session_factory=factory)
        # First scan gives Meta some mentions
        await service.scan()

        # Second scan with new_entities_only=True — no new entities exist
        result2 = await service.scan(new_entities_only=True)

        assert result2.mentions_found == 0
        assert result2.segments_scanned == 0


# ---------------------------------------------------------------------------
# T016-07: Merged / deprecated entities excluded
# ---------------------------------------------------------------------------


class TestEntityStatusExclusion:
    """Verify that merged/deprecated entities are not scanned."""

    async def test_merged_entity_not_scanned(
        self, db_session: AsyncSession
    ) -> None:
        """An entity with status='merged' must not produce any mention records."""
        await _seed_channel(db_session)
        await _seed_video(db_session, video_id(seed="st_001"))
        await _seed_transcript(db_session, video_id(seed="st_001"))

        await _seed_segment(
            db_session, video_id(seed="st_001"), text="Alphabet is the parent company of Google"
        )
        # Deliberately set status=merged
        await _seed_entity(db_session, "Alphabet", entity_type="organization", status="merged")

        await db_session.commit()

        factory = _make_session_factory_from_session(db_session)
        service = EntityMentionScanService(session_factory=factory)
        result = await service.scan()

        rows = (
            await db_session.execute(select(EntityMentionDB))
        ).scalars().all()

        assert len(rows) == 0
        assert result.mentions_found == 0

    async def test_deprecated_entity_not_scanned(
        self, db_session: AsyncSession
    ) -> None:
        """An entity with status='deprecated' must not produce any mention records."""
        await _seed_channel(db_session)
        await _seed_video(db_session, video_id(seed="st_002"))
        await _seed_transcript(db_session, video_id(seed="st_002"))

        await _seed_segment(
            db_session, video_id(seed="st_002"), text="Twitter is now called X"
        )
        await _seed_entity(db_session, "Twitter", entity_type="organization", status="deprecated")

        await db_session.commit()

        factory = _make_session_factory_from_session(db_session)
        service = EntityMentionScanService(session_factory=factory)
        result = await service.scan()

        rows = (
            await db_session.execute(select(EntityMentionDB))
        ).scalars().all()

        assert len(rows) == 0
        assert result.mentions_found == 0


# ---------------------------------------------------------------------------
# T016-08: Corrected segment text used for matching
# ---------------------------------------------------------------------------


class TestCorrectedSegmentText:
    """Verify that has_correction=True segments use corrected_text for matching."""

    async def test_corrected_text_used_when_has_correction_true(
        self, db_session: AsyncSession
    ) -> None:
        """
        A segment with has_correction=True must be scanned using corrected_text,
        not the original text field.
        """
        vid = video_id(seed="ct_001")
        await _seed_channel(db_session)
        await _seed_video(db_session, vid)
        await _seed_transcript(db_session, vid)

        # Original text has wrong name; corrected text has entity name
        seg = TranscriptSegmentDB(
            video_id=vid,
            language_code="en",
            text="Elan Musk spoke today",  # ASR error
            corrected_text="Elon Musk spoke today",  # corrected
            has_correction=True,
            start_time=0.0,
            duration=5.0,
            end_time=5.0,
            sequence_number=0,
        )
        db_session.add(seg)
        await db_session.flush()

        await _seed_entity(db_session, "Elon Musk", entity_type="person")

        await db_session.commit()

        factory = _make_session_factory_from_session(db_session)
        service = EntityMentionScanService(session_factory=factory)
        result = await service.scan()

        rows = (
            await db_session.execute(select(EntityMentionDB))
        ).scalars().all()

        # Match via corrected_text, not original text
        assert len(rows) == 1
        assert result.mentions_found == 1


# ---------------------------------------------------------------------------
# T011 (Feature 044 US2): ASR-error alias exclusion from entity counters
# ---------------------------------------------------------------------------


class TestASRErrorAliasCounterExclusion:
    """Verify that ASR-error aliases are excluded from mention_count / video_count.

    Feature 044 US2 modified ``update_entity_counters()`` so that only
    mentions whose ``mention_text`` matches the entity's canonical name or a
    non-ASR-error alias are counted.  Mentions matched via ``asr_error``
    aliases contribute to the ``entity_mentions`` table but must NOT increment
    ``mention_count`` or ``video_count`` on ``named_entities``.
    """

    async def test_asr_error_alias_mention_excluded_from_mention_count(
        self, db_session: AsyncSession
    ) -> None:
        """
        An entity whose mentions are all via ASR-error aliases must end up
        with mention_count=0 after a full scan.

        Setup:
        - Entity "Elon Musk" with an ASR-error alias "Elan Musk"
        - Segment text contains "Elan Musk" only (no canonical name)

        Expected:
        - One EntityMention row is created (detection still fires)
        - mention_count=0 because "elan musk" is an asr_error alias
        """
        vid = video_id(seed="asr_ex_001")
        await _seed_channel(db_session)
        await _seed_video(db_session, vid)
        await _seed_transcript(db_session, vid)

        await _seed_segment(
            db_session,
            vid,
            text="Elan Musk announced a new rocket",
        )
        entity = await _seed_entity(db_session, "Elon Musk", entity_type="person")
        # Register the ASR-error alias so the scanner can match it
        await _seed_alias(db_session, entity.id, "Elan Musk", alias_type="asr_error")

        await db_session.commit()

        factory = _make_session_factory_from_session(db_session)
        service = EntityMentionScanService(session_factory=factory)
        await service.scan()

        await db_session.refresh(entity)

        # The scan creates a mention row (scan still detects)
        mention_rows = (
            await db_session.execute(
                select(EntityMentionDB).where(EntityMentionDB.entity_id == entity.id)
            )
        ).scalars().all()
        assert len(mention_rows) >= 1, (
            "Expected at least one EntityMention row for the ASR-alias match"
        )

        # But the counter must be 0 because all matches were via asr_error alias
        assert entity.mention_count == 0, (
            f"Expected mention_count=0 (ASR-error alias only), got {entity.mention_count}"
        )
        assert entity.video_count == 0, (
            f"Expected video_count=0 (ASR-error alias only), got {entity.video_count}"
        )

    async def test_canonical_name_mention_included_in_mention_count(
        self, db_session: AsyncSession
    ) -> None:
        """
        An entity whose mentions match its canonical name must have
        mention_count > 0 after a full scan.

        Setup:
        - Entity "Elon Musk" (canonical name)
        - Segment text contains "Elon Musk"

        Expected:
        - mention_count=1 because canonical name is always visible
        """
        vid = video_id(seed="asr_ex_002")
        await _seed_channel(db_session)
        await _seed_video(db_session, vid)
        await _seed_transcript(db_session, vid)

        await _seed_segment(
            db_session,
            vid,
            text="Elon Musk is the CEO of SpaceX",
        )
        entity = await _seed_entity(db_session, "Elon Musk", entity_type="person")

        await db_session.commit()

        factory = _make_session_factory_from_session(db_session)
        service = EntityMentionScanService(session_factory=factory)
        await service.scan()

        await db_session.refresh(entity)

        assert entity.mention_count == 1, (
            f"Expected mention_count=1 (canonical name match), got {entity.mention_count}"
        )
        assert entity.video_count == 1, (
            f"Expected video_count=1, got {entity.video_count}"
        )

    async def test_non_asr_alias_mention_included_in_mention_count(
        self, db_session: AsyncSession
    ) -> None:
        """
        Mentions matching a non-ASR-error alias must be counted.

        Setup:
        - Entity "Elon Musk" with a name_variant alias "Musk"
        - Segment text contains "Musk" only

        Expected:
        - mention_count=1 because name_variant aliases are visible
        """
        vid = video_id(seed="asr_ex_003")
        await _seed_channel(db_session)
        await _seed_video(db_session, vid)
        await _seed_transcript(db_session, vid)

        await _seed_segment(
            db_session,
            vid,
            text="Musk tweeted about the new model",
        )
        entity = await _seed_entity(db_session, "Elon Musk", entity_type="person")
        await _seed_alias(db_session, entity.id, "Musk", alias_type="name_variant")

        await db_session.commit()

        factory = _make_session_factory_from_session(db_session)
        service = EntityMentionScanService(session_factory=factory)
        await service.scan()

        await db_session.refresh(entity)

        assert entity.mention_count == 1, (
            f"Expected mention_count=1 (name_variant alias), got {entity.mention_count}"
        )
        assert entity.video_count == 1, (
            f"Expected video_count=1, got {entity.video_count}"
        )

    async def test_mixed_mentions_count_excludes_asr_error_matches(
        self, db_session: AsyncSession
    ) -> None:
        """
        When an entity has both canonical-name matches and ASR-error-alias
        matches, only canonical-name matches must be counted.

        Setup:
        - Entity "Google" with ASR-error alias "Googel"
        - Three segments:
            seg1: "Google announced new products"  (canonical → counted)
            seg2: "Googel launched a service"      (asr_error → excluded)
            seg3: "Google is a search engine"      (canonical → counted)

        Expected:
        - EntityMention rows: 3 (scanner detects all)
        - mention_count: 2 (only the 2 canonical-name segments counted)
        - video_count: 1 (all in same video)
        """
        vid = video_id(seed="asr_ex_004")
        await _seed_channel(db_session)
        await _seed_video(db_session, vid)
        await _seed_transcript(db_session, vid)

        await _seed_segment(
            db_session,
            vid,
            text="Google announced new products",
            start_time=0.0,
            sequence_number=0,
        )
        await _seed_segment(
            db_session,
            vid,
            text="Googel launched a service",
            start_time=10.0,
            sequence_number=1,
        )
        await _seed_segment(
            db_session,
            vid,
            text="Google is a search engine",
            start_time=20.0,
            sequence_number=2,
        )

        entity = await _seed_entity(db_session, "Google", entity_type="organization")
        await _seed_alias(db_session, entity.id, "Googel", alias_type="asr_error")

        await db_session.commit()

        factory = _make_session_factory_from_session(db_session)
        service = EntityMentionScanService(session_factory=factory)
        await service.scan()

        await db_session.refresh(entity)

        mention_rows = (
            await db_session.execute(
                select(EntityMentionDB).where(EntityMentionDB.entity_id == entity.id)
            )
        ).scalars().all()

        # All three matches were detected
        assert len(mention_rows) == 3, (
            f"Expected 3 EntityMention rows (canonical + asr_error), got {len(mention_rows)}"
        )

        # Only the 2 canonical-name matches count
        assert entity.mention_count == 2, (
            f"Expected mention_count=2 (excluding asr_error alias), got {entity.mention_count}"
        )
        assert entity.video_count == 1, (
            f"Expected video_count=1 (single video), got {entity.video_count}"
        )

    async def test_video_count_excludes_videos_with_only_asr_alias_matches(
        self, db_session: AsyncSession
    ) -> None:
        """
        video_count must not count videos where the only mentions are
        ASR-error alias matches.

        Setup:
        - Entity "Tesla" with ASR-error alias "Tezla"
        - Video 1: segment with "Tesla" (canonical — counted)
        - Video 2: segment with "Tezla" (asr_error — excluded)

        Expected:
        - mention_count=1 (only Video 1's canonical match)
        - video_count=1 (only Video 1 qualifies)
        """
        vid1 = video_id(seed="asr_vc_001")
        vid2 = video_id(seed="asr_vc_002")
        await _seed_channel(db_session)

        for vid in [vid1, vid2]:
            await _seed_video(db_session, vid)
            await _seed_transcript(db_session, vid)

        await _seed_segment(
            db_session,
            vid1,
            text="Tesla released a new car",
        )
        await _seed_segment(
            db_session,
            vid2,
            text="Tezla is an ASR error",
        )

        entity = await _seed_entity(db_session, "Tesla", entity_type="organization")
        await _seed_alias(db_session, entity.id, "Tezla", alias_type="asr_error")

        await db_session.commit()

        factory = _make_session_factory_from_session(db_session)
        service = EntityMentionScanService(session_factory=factory)
        await service.scan()

        await db_session.refresh(entity)

        assert entity.mention_count == 1, (
            f"Expected mention_count=1 (Video 1 canonical only), got {entity.mention_count}"
        )
        assert entity.video_count == 1, (
            f"Expected video_count=1 (Video 2 excluded due to asr_error), got {entity.video_count}"
        )

    async def test_full_rescan_preserves_asr_exclusion_in_counters(
        self, db_session: AsyncSession
    ) -> None:
        """
        A full rescan (full_rescan=True) must also apply ASR-error alias
        exclusion when recalculating counters.

        After a first scan followed by a full rescan, an entity with only
        ASR-error-alias mentions must still end up with mention_count=0.
        """
        vid = video_id(seed="asr_ex_005")
        await _seed_channel(db_session)
        await _seed_video(db_session, vid)
        await _seed_transcript(db_session, vid)

        await _seed_segment(
            db_session,
            vid,
            text="Amazzon Prime delivery arrived",
        )
        entity = await _seed_entity(db_session, "Amazon", entity_type="organization")
        await _seed_alias(db_session, entity.id, "Amazzon", alias_type="asr_error")

        await db_session.commit()

        factory = _make_session_factory_from_session(db_session)
        service = EntityMentionScanService(session_factory=factory)

        # First scan
        await service.scan()
        await db_session.refresh(entity)
        assert entity.mention_count == 0, (
            f"After first scan: expected mention_count=0 (ASR-error alias only), "
            f"got {entity.mention_count}"
        )

        # Manually bump the counter to simulate drift (as if a bug had set it)
        entity.mention_count = 99
        entity.video_count = 99
        await db_session.flush()

        # Full rescan must recalculate and restore the correct 0
        await service.scan(full_rescan=True)
        await db_session.refresh(entity)
        assert entity.mention_count == 0, (
            f"After full rescan: expected mention_count=0 (ASR-error alias only), "
            f"got {entity.mention_count}"
        )
        assert entity.video_count == 0, (
            f"After full rescan: expected video_count=0 (ASR-error alias only), "
            f"got {entity.video_count}"
        )
