"""
Tests for EntityMentionScanService.scan_metadata() — title and description scanning.

Feature 054 — Multi-Source Entity Mention Detection (Phases 3 & 4)

T013: Title scanning creates mentions with mention_source='title', segment_id=NULL
T014: Title scanning applies exclusion patterns
T015: Empty title produces no mentions
T021: Description scanning creates mentions with mention_source='description' and context
T022: NULL description skipped without error
T023: mention_context is ~75 chars before + ~75 chars after with ellipsis
T024: Very long description (>10K chars) processes without error
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chronovista.models.enums import MentionSource
from chronovista.services.entity_mention_scan_service import (
    EntityMentionScanService,
)

# CRITICAL: Module-level asyncio marker ensures async tests run properly
# with coverage tools, avoiding silent test-skipping (see CLAUDE.md).
pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def _make_uuid() -> uuid.UUID:
    """Return a fresh UUID4 for test data."""
    return uuid.uuid4()


def _make_entity_row(
    entity_id: uuid.UUID | None = None,
    canonical_name: str = "Noam Chomsky",
    entity_type: str = "person",
    status: str = "active",
    exclusion_patterns: list[str] | None = None,
) -> MagicMock:
    """Create a mock ORM NamedEntity row."""
    row = MagicMock()
    row.id = entity_id or _make_uuid()
    row.canonical_name = canonical_name
    row.entity_type = entity_type
    row.status = status
    row.exclusion_patterns = exclusion_patterns or []
    return row


def _make_alias_row(entity_id: uuid.UUID, alias_name: str) -> MagicMock:
    """Create a mock ORM EntityAlias row."""
    row = MagicMock()
    row.entity_id = entity_id
    row.alias_name = alias_name
    row.alias_type = "name_variant"
    return row


def _make_video_row(
    video_id: str = "dQw4w9WgXcQ",
    title: str = "Noam Chomsky Interview",
    description: str | None = "In this interview, Noam Chomsky discusses linguistics.",
    channel_id: str = "UCtest123",
) -> MagicMock:
    """Create a mock video row matching the _fetch_video_batch columns."""
    row = MagicMock()
    row.video_id = video_id
    row.title = title
    row.description = description
    row.channel_id = channel_id
    return row


def _make_session_factory(
    entities: list[MagicMock],
    aliases: list[MagicMock],
    video_batches: list[list[MagicMock]],
) -> MagicMock:
    """Build a mock session_factory that returns the given data.

    The session.execute mock handles:
    - First call: entity query -> returns entities
    - Second call: alias query -> returns aliases
    - Subsequent calls: video batches + bulk insert results + counter updates
    """
    session = MagicMock()
    session.execute = AsyncMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()

    # Build the sequence of return values for execute()
    call_results: list[MagicMock] = []

    # Entity query result
    entity_result = MagicMock()
    entity_result.scalars.return_value.all.return_value = entities
    call_results.append(entity_result)

    # Alias query result
    alias_result = MagicMock()
    alias_result.scalars.return_value.all.return_value = aliases
    call_results.append(alias_result)

    # Video batch results
    for batch in video_batches:
        batch_result = MagicMock()
        batch_result.all.return_value = batch
        call_results.append(batch_result)

    # Empty batch to signal end of iteration
    empty_result = MagicMock()
    empty_result.all.return_value = []
    call_results.append(empty_result)

    session.execute.side_effect = call_results

    factory = MagicMock()
    ctx_manager = AsyncMock()
    ctx_manager.__aenter__ = AsyncMock(return_value=session)
    ctx_manager.__aexit__ = AsyncMock(return_value=False)
    factory.return_value = ctx_manager

    return factory


# ---------------------------------------------------------------------------
# Tests for User Story 1 — Title Scanning
# ---------------------------------------------------------------------------


class TestScanMetadataTitle:
    """Tests for scan_metadata() with sources=["title"]."""

    async def test_t013_title_scan_creates_mentions_with_title_source(
        self,
    ) -> None:
        """T013: scan_metadata(sources=['title']) creates mentions with
        mention_source='title' and segment_id=NULL.
        """
        entity_id = _make_uuid()
        entity = _make_entity_row(entity_id=entity_id, canonical_name="Noam Chomsky")
        video = _make_video_row(
            video_id="vid00100001",
            title="Noam Chomsky Wins Award",
        )

        factory = _make_session_factory(
            entities=[entity],
            aliases=[],
            video_batches=[[video]],
        )

        service = EntityMentionScanService(factory)

        # Patch bulk_create to capture what gets inserted
        with patch.object(
            service._mention_repo,
            "bulk_create_with_conflict_skip",
            new_callable=AsyncMock,
        ) as mock_bulk:
            mock_bulk.return_value = 1

            with patch.object(
                service._mention_repo,
                "update_entity_counters",
                new_callable=AsyncMock,
            ), patch.object(
                service._mention_repo,
                "update_alias_counters",
                new_callable=AsyncMock,
            ):
                result = await service.scan_metadata(
                    sources=["title"],
                    entity_ids=[entity_id],
                )

        assert result.mentions_found == 1
        assert result.segments_scanned == 1  # 1 video scanned

        # Verify the mention was created correctly
        mock_bulk.assert_called_once()
        mentions = mock_bulk.call_args[0][1]
        assert len(mentions) == 1
        mention = mentions[0]
        assert mention.mention_source == MentionSource.TITLE
        assert mention.segment_id is None
        assert mention.video_id == "vid00100001"
        assert mention.mention_text == "Noam Chomsky"
        assert mention.mention_context is None  # No context for title mentions

    async def test_t014_title_scan_applies_exclusion_patterns(self) -> None:
        """T014: Title scanning with exclusion pattern 'New Mexico' skips
        title 'New Mexico Travel Guide' for entity 'Mexico'.
        """
        entity_id = _make_uuid()
        entity = _make_entity_row(
            entity_id=entity_id,
            canonical_name="Mexico",
            exclusion_patterns=["New Mexico"],
        )
        video = _make_video_row(
            video_id="vid00200002",
            title="New Mexico Travel Guide",
        )

        factory = _make_session_factory(
            entities=[entity],
            aliases=[],
            video_batches=[[video]],
        )

        service = EntityMentionScanService(factory)

        with patch.object(
            service._mention_repo,
            "bulk_create_with_conflict_skip",
            new_callable=AsyncMock,
        ) as mock_bulk, patch.object(
            service._mention_repo,
            "update_entity_counters",
            new_callable=AsyncMock,
        ), patch.object(
            service._mention_repo,
            "update_alias_counters",
            new_callable=AsyncMock,
        ):
            result = await service.scan_metadata(
                sources=["title"],
                entity_ids=[entity_id],
            )

        # No mentions should be created because "Mexico" is inside "New Mexico"
        assert result.mentions_found == 0
        mock_bulk.assert_not_called()

    async def test_t015_empty_title_produces_no_mentions(self) -> None:
        """T015: Title scanning with empty title produces no mentions."""
        entity_id = _make_uuid()
        entity = _make_entity_row(entity_id=entity_id, canonical_name="Noam Chomsky")
        video = _make_video_row(
            video_id="vid00300003",
            title="",
        )

        factory = _make_session_factory(
            entities=[entity],
            aliases=[],
            video_batches=[[video]],
        )

        service = EntityMentionScanService(factory)

        with patch.object(
            service._mention_repo,
            "bulk_create_with_conflict_skip",
            new_callable=AsyncMock,
        ) as mock_bulk, patch.object(
            service._mention_repo,
            "update_entity_counters",
            new_callable=AsyncMock,
        ), patch.object(
            service._mention_repo,
            "update_alias_counters",
            new_callable=AsyncMock,
        ):
            result = await service.scan_metadata(
                sources=["title"],
                entity_ids=[entity_id],
            )

        assert result.mentions_found == 0
        mock_bulk.assert_not_called()

    async def test_title_scan_dry_run_collects_previews(self) -> None:
        """Title scanning in dry-run mode collects preview data without writing."""
        entity_id = _make_uuid()
        entity = _make_entity_row(entity_id=entity_id, canonical_name="Noam Chomsky")
        video = _make_video_row(
            video_id="vid00400004",
            title="Noam Chomsky Discusses Linguistics",
        )

        factory = _make_session_factory(
            entities=[entity],
            aliases=[],
            video_batches=[[video]],
        )

        service = EntityMentionScanService(factory)

        result = await service.scan_metadata(
            sources=["title"],
            entity_ids=[entity_id],
            dry_run=True,
        )

        assert result.dry_run is True
        assert result.mentions_found == 1
        assert result.dry_run_matches is not None
        assert len(result.dry_run_matches) == 1
        preview = result.dry_run_matches[0]
        assert preview["source"] == "title"
        assert preview["segment_id"] is None
        assert preview["start_time"] is None
        assert preview["matched_text"] == "Noam Chomsky"

    async def test_title_scan_full_rescan_deletes_before_scan(self) -> None:
        """Title scanning with full_rescan=True calls delete_by_scope with
        mention_source='title' before scanning.
        """
        entity_id = _make_uuid()
        entity = _make_entity_row(entity_id=entity_id, canonical_name="Noam Chomsky")
        video = _make_video_row(
            video_id="vid00500005",
            title="Noam Chomsky Interview",
        )

        factory = _make_session_factory(
            entities=[entity],
            aliases=[],
            video_batches=[[video]],
        )

        service = EntityMentionScanService(factory)

        with patch.object(
            service._mention_repo,
            "delete_by_scope",
            new_callable=AsyncMock,
        ) as mock_delete, patch.object(
            service._mention_repo,
            "bulk_create_with_conflict_skip",
            new_callable=AsyncMock,
            return_value=1,
        ), patch.object(
            service._mention_repo,
            "update_entity_counters",
            new_callable=AsyncMock,
        ), patch.object(
            service._mention_repo,
            "update_alias_counters",
            new_callable=AsyncMock,
        ):
            await service.scan_metadata(
                sources=["title"],
                entity_ids=[entity_id],
                full_rescan=True,
            )

        mock_delete.assert_called_once()
        call_kwargs = mock_delete.call_args
        assert call_kwargs[1]["mention_source"] == "title"
        assert call_kwargs[1]["detection_method"] == "rule_match"

    async def test_title_scan_with_aliases(self) -> None:
        """Title scanning detects entity aliases in video titles."""
        entity_id = _make_uuid()
        entity = _make_entity_row(
            entity_id=entity_id,
            canonical_name="AMLO",
        )
        alias = _make_alias_row(entity_id, "Lopez Obrador")
        video = _make_video_row(
            video_id="vid00600006",
            title="Lopez Obrador Speaks at Conference",
        )

        factory = _make_session_factory(
            entities=[entity],
            aliases=[alias],
            video_batches=[[video]],
        )

        service = EntityMentionScanService(factory)

        with patch.object(
            service._mention_repo,
            "bulk_create_with_conflict_skip",
            new_callable=AsyncMock,
        ) as mock_bulk, patch.object(
            service._mention_repo,
            "update_entity_counters",
            new_callable=AsyncMock,
        ), patch.object(
            service._mention_repo,
            "update_alias_counters",
            new_callable=AsyncMock,
        ):
            mock_bulk.return_value = 1
            result = await service.scan_metadata(
                sources=["title"],
                entity_ids=[entity_id],
            )

        assert result.mentions_found == 1
        mentions = mock_bulk.call_args[0][1]
        assert mentions[0].mention_text == "Lopez Obrador"

    async def test_title_scan_multiple_entities_same_title(self) -> None:
        """EC-006: Multiple entities found in the same title each create
        separate mention rows.
        """
        entity1_id = _make_uuid()
        entity2_id = _make_uuid()
        entity1 = _make_entity_row(entity_id=entity1_id, canonical_name="Biden")
        entity2 = _make_entity_row(entity_id=entity2_id, canonical_name="Trump")
        video = _make_video_row(
            video_id="vid00700007",
            title="Biden and Trump Debate",
        )

        factory = _make_session_factory(
            entities=[entity1, entity2],
            aliases=[],
            video_batches=[[video]],
        )

        service = EntityMentionScanService(factory)

        with patch.object(
            service._mention_repo,
            "bulk_create_with_conflict_skip",
            new_callable=AsyncMock,
        ) as mock_bulk, patch.object(
            service._mention_repo,
            "update_entity_counters",
            new_callable=AsyncMock,
        ), patch.object(
            service._mention_repo,
            "update_alias_counters",
            new_callable=AsyncMock,
        ):
            mock_bulk.return_value = 2
            result = await service.scan_metadata(
                sources=["title"],
                entity_ids=[entity1_id, entity2_id],
            )

        assert result.mentions_found == 2
        mentions = mock_bulk.call_args[0][1]
        entity_ids_found = {m.entity_id for m in mentions}
        assert entity1_id in entity_ids_found
        assert entity2_id in entity_ids_found

    async def test_title_scan_deduplicates_per_entity(self) -> None:
        """EC-007: Title containing entity name multiple times creates
        only one mention per entity per video.
        """
        entity_id = _make_uuid()
        entity = _make_entity_row(entity_id=entity_id, canonical_name="AI")
        video = _make_video_row(
            video_id="vid00800008",
            title="AI meets AI: The AI Revolution",
        )

        factory = _make_session_factory(
            entities=[entity],
            aliases=[],
            video_batches=[[video]],
        )

        service = EntityMentionScanService(factory)

        with patch.object(
            service._mention_repo,
            "bulk_create_with_conflict_skip",
            new_callable=AsyncMock,
        ) as mock_bulk, patch.object(
            service._mention_repo,
            "update_entity_counters",
            new_callable=AsyncMock,
        ), patch.object(
            service._mention_repo,
            "update_alias_counters",
            new_callable=AsyncMock,
        ):
            mock_bulk.return_value = 1
            await service.scan_metadata(
                sources=["title"],
                entity_ids=[entity_id],
            )

        # Only one mention per entity per video for title
        mentions = mock_bulk.call_args[0][1]
        assert len(mentions) == 1

    async def test_progress_callback_invoked(self) -> None:
        """Progress callback is called with items_scanned and mentions_found."""
        entity_id = _make_uuid()
        entity = _make_entity_row(entity_id=entity_id, canonical_name="Noam Chomsky")
        video = _make_video_row(video_id="vid00900009", title="Noam Chomsky Talk")

        factory = _make_session_factory(
            entities=[entity],
            aliases=[],
            video_batches=[[video]],
        )

        service = EntityMentionScanService(factory)
        callback = MagicMock()

        with patch.object(
            service._mention_repo,
            "bulk_create_with_conflict_skip",
            new_callable=AsyncMock,
            return_value=1,
        ), patch.object(
            service._mention_repo,
            "update_entity_counters",
            new_callable=AsyncMock,
        ), patch.object(
            service._mention_repo,
            "update_alias_counters",
            new_callable=AsyncMock,
        ):
            await service.scan_metadata(
                sources=["title"],
                entity_ids=[entity_id],
                progress_callback=callback,
            )

        assert callback.call_count >= 1


# ---------------------------------------------------------------------------
# Tests for User Story 2 — Description Scanning
# ---------------------------------------------------------------------------


class TestScanMetadataDescription:
    """Tests for scan_metadata() with sources=["description"]."""

    async def test_t021_description_scan_creates_mentions_with_context(
        self,
    ) -> None:
        """T021: scan_metadata(sources=['description']) scans descriptions,
        creates mentions with mention_source='description' and
        mention_context snippet.
        """
        entity_id = _make_uuid()
        entity = _make_entity_row(entity_id=entity_id, canonical_name="Noam Chomsky")
        description_text = (
            "In this interview, Noam Chomsky discusses the future of linguistics "
            "and the role of language in society."
        )
        video = _make_video_row(
            video_id="vid01000010",
            title="Some Title",
            description=description_text,
        )

        factory = _make_session_factory(
            entities=[entity],
            aliases=[],
            video_batches=[[video]],
        )

        service = EntityMentionScanService(factory)

        with patch.object(
            service._mention_repo,
            "bulk_create_with_conflict_skip",
            new_callable=AsyncMock,
        ) as mock_bulk, patch.object(
            service._mention_repo,
            "update_entity_counters",
            new_callable=AsyncMock,
        ), patch.object(
            service._mention_repo,
            "update_alias_counters",
            new_callable=AsyncMock,
        ):
            mock_bulk.return_value = 1
            result = await service.scan_metadata(
                sources=["description"],
                entity_ids=[entity_id],
            )

        assert result.mentions_found == 1
        mentions = mock_bulk.call_args[0][1]
        mention = mentions[0]
        assert mention.mention_source == MentionSource.DESCRIPTION
        assert mention.segment_id is None
        assert mention.mention_context is not None
        assert "Noam Chomsky" in mention.mention_context

    async def test_t022_null_description_skipped_without_error(self) -> None:
        """T022: NULL description is skipped without error."""
        entity_id = _make_uuid()
        entity = _make_entity_row(entity_id=entity_id, canonical_name="Noam Chomsky")
        video = _make_video_row(
            video_id="vid01100011",
            title="Some Title",
            description=None,
        )

        factory = _make_session_factory(
            entities=[entity],
            aliases=[],
            video_batches=[[video]],
        )

        service = EntityMentionScanService(factory)

        with patch.object(
            service._mention_repo,
            "bulk_create_with_conflict_skip",
            new_callable=AsyncMock,
        ) as mock_bulk, patch.object(
            service._mention_repo,
            "update_entity_counters",
            new_callable=AsyncMock,
        ), patch.object(
            service._mention_repo,
            "update_alias_counters",
            new_callable=AsyncMock,
        ):
            result = await service.scan_metadata(
                sources=["description"],
                entity_ids=[entity_id],
            )

        assert result.mentions_found == 0
        mock_bulk.assert_not_called()

    async def test_t023_mention_context_75_chars_before_and_after(self) -> None:
        """T023: mention_context is ~75 chars before + ~75 chars after the
        match, with ellipsis if truncated.
        """
        # Test the static helper directly
        # Build a string with known content around match position
        prefix = "A" * 100  # 100 chars before the match
        suffix = "B" * 100  # 100 chars after the match
        match_text = "Noam Chomsky"
        full_text = prefix + match_text + suffix

        match_start = 100
        match_end = 100 + len(match_text)

        snippet = EntityMentionScanService._extract_context_snippet(
            full_text, match_start, match_end, window=75
        )

        # Should have ellipsis at both ends since we truncated
        assert snippet.startswith("...")
        assert snippet.endswith("...")

        # Should contain the matched text
        assert "Noam Chomsky" in snippet

        # The snippet (excluding ellipsis) should be about 75+len(match)+75 chars
        # 75 before + 12 (match) + 75 after = 162 chars + 6 for "..." on both sides
        inner = snippet[3:-3]  # strip leading/trailing "..."
        assert len(inner) == 75 + len(match_text) + 75

    async def test_t023_context_no_leading_ellipsis_at_start(self) -> None:
        """Context snippet at the start of text has no leading ellipsis."""
        text = "Noam Chomsky discusses linguistics and more content after."
        match_start = 0
        match_end = 12

        snippet = EntityMentionScanService._extract_context_snippet(
            text, match_start, match_end, window=75
        )

        # Should NOT start with "..." since match is at the beginning
        assert not snippet.startswith("...")
        assert "Noam Chomsky" in snippet

    async def test_t023_context_no_trailing_ellipsis_at_end(self) -> None:
        """Context snippet at the end of text has no trailing ellipsis."""
        text = "Some text about Noam Chomsky"
        match_start = text.index("Noam Chomsky")
        match_end = match_start + len("Noam Chomsky")

        snippet = EntityMentionScanService._extract_context_snippet(
            text, match_start, match_end, window=75
        )

        # Should NOT end with "..." since match is at the end
        assert not snippet.endswith("...")
        assert "Noam Chomsky" in snippet

    async def test_t024_very_long_description_processes_without_error(
        self,
    ) -> None:
        """T024: Very long description (>10K chars) processes without error."""
        entity_id = _make_uuid()
        entity = _make_entity_row(entity_id=entity_id, canonical_name="Noam Chomsky")
        # Build a >10K description with the entity name buried in the middle
        long_desc = "x" * 5000 + " Noam Chomsky " + "y" * 5000
        assert len(long_desc) > 10000

        video = _make_video_row(
            video_id="vid01200012",
            title="Some Title",
            description=long_desc,
        )

        factory = _make_session_factory(
            entities=[entity],
            aliases=[],
            video_batches=[[video]],
        )

        service = EntityMentionScanService(factory)

        with patch.object(
            service._mention_repo,
            "bulk_create_with_conflict_skip",
            new_callable=AsyncMock,
        ) as mock_bulk, patch.object(
            service._mention_repo,
            "update_entity_counters",
            new_callable=AsyncMock,
        ), patch.object(
            service._mention_repo,
            "update_alias_counters",
            new_callable=AsyncMock,
        ):
            mock_bulk.return_value = 1
            result = await service.scan_metadata(
                sources=["description"],
                entity_ids=[entity_id],
            )

        assert result.mentions_found == 1
        mentions = mock_bulk.call_args[0][1]
        mention = mentions[0]
        assert mention.mention_source == MentionSource.DESCRIPTION
        assert mention.mention_context is not None
        # Context should be ~150 chars, not the full 10K
        assert len(mention.mention_context) < 200

    async def test_description_scan_multiple_distinct_matches(self) -> None:
        """Description with multiple distinct entity mentions creates
        multiple mention rows (unlike title which deduplicates).
        """
        entity_id = _make_uuid()
        entity = _make_entity_row(entity_id=entity_id, canonical_name="Noam Chomsky")
        description = (
            "Noam Chomsky was interviewed about his work. "
            "Later, Noam Chomsky discussed the implications."
        )
        video = _make_video_row(
            video_id="vid01300013",
            title="Some Title",
            description=description,
        )

        factory = _make_session_factory(
            entities=[entity],
            aliases=[],
            video_batches=[[video]],
        )

        service = EntityMentionScanService(factory)

        with patch.object(
            service._mention_repo,
            "bulk_create_with_conflict_skip",
            new_callable=AsyncMock,
        ) as mock_bulk, patch.object(
            service._mention_repo,
            "update_entity_counters",
            new_callable=AsyncMock,
        ), patch.object(
            service._mention_repo,
            "update_alias_counters",
            new_callable=AsyncMock,
        ):
            mock_bulk.return_value = 2
            result = await service.scan_metadata(
                sources=["description"],
                entity_ids=[entity_id],
            )

        assert result.mentions_found == 2
        mentions = mock_bulk.call_args[0][1]
        assert len(mentions) == 2
        # Both should be description source with different positions
        assert all(m.mention_source == MentionSource.DESCRIPTION for m in mentions)
        assert mentions[0].match_start != mentions[1].match_start

    async def test_description_scan_applies_exclusion_patterns(self) -> None:
        """Description scanning also applies exclusion patterns."""
        entity_id = _make_uuid()
        entity = _make_entity_row(
            entity_id=entity_id,
            canonical_name="Mexico",
            exclusion_patterns=["New Mexico"],
        )
        video = _make_video_row(
            video_id="vid01400014",
            title="Some Title",
            description="Great vacation spots in New Mexico and surrounding areas.",
        )

        factory = _make_session_factory(
            entities=[entity],
            aliases=[],
            video_batches=[[video]],
        )

        service = EntityMentionScanService(factory)

        with patch.object(
            service._mention_repo,
            "bulk_create_with_conflict_skip",
            new_callable=AsyncMock,
        ) as mock_bulk, patch.object(
            service._mention_repo,
            "update_entity_counters",
            new_callable=AsyncMock,
        ), patch.object(
            service._mention_repo,
            "update_alias_counters",
            new_callable=AsyncMock,
        ):
            result = await service.scan_metadata(
                sources=["description"],
                entity_ids=[entity_id],
            )

        assert result.mentions_found == 0
        mock_bulk.assert_not_called()


# ---------------------------------------------------------------------------
# Tests for combined title + description scanning
# ---------------------------------------------------------------------------


class TestScanMetadataCombined:
    """Tests for scan_metadata() with both title and description sources."""

    async def test_combined_title_and_description_scan(self) -> None:
        """scan_metadata(sources=['title', 'description']) scans both fields."""
        entity_id = _make_uuid()
        entity = _make_entity_row(entity_id=entity_id, canonical_name="Noam Chomsky")
        video = _make_video_row(
            video_id="vid01500015",
            title="Noam Chomsky Interview",
            description="In this video, Noam Chomsky talks about AI.",
        )

        factory = _make_session_factory(
            entities=[entity],
            aliases=[],
            video_batches=[[video]],
        )

        service = EntityMentionScanService(factory)

        with patch.object(
            service._mention_repo,
            "bulk_create_with_conflict_skip",
            new_callable=AsyncMock,
        ) as mock_bulk, patch.object(
            service._mention_repo,
            "update_entity_counters",
            new_callable=AsyncMock,
        ), patch.object(
            service._mention_repo,
            "update_alias_counters",
            new_callable=AsyncMock,
        ):
            mock_bulk.return_value = 2
            result = await service.scan_metadata(
                sources=["title", "description"],
                entity_ids=[entity_id],
            )

        assert result.mentions_found == 2
        mentions = mock_bulk.call_args[0][1]
        sources_found = {m.mention_source for m in mentions}
        assert MentionSource.TITLE in sources_found
        assert MentionSource.DESCRIPTION in sources_found

    async def test_no_entities_returns_empty_result(self) -> None:
        """When no entities match filter criteria, returns empty result."""
        factory = _make_session_factory(
            entities=[],
            aliases=[],
            video_batches=[],
        )

        service = EntityMentionScanService(factory)

        result = await service.scan_metadata(
            sources=["title"],
        )

        assert result.mentions_found == 0
        assert result.segments_scanned == 0


# ---------------------------------------------------------------------------
# Tests for _extract_context_snippet static helper
# ---------------------------------------------------------------------------


class TestExtractContextSnippet:
    """Unit tests for the context snippet extraction helper."""

    def test_snippet_with_truncation_both_sides(self) -> None:
        """Snippet adds ellipsis when truncated at both ends."""
        text = "A" * 100 + "MATCH" + "B" * 100
        snippet = EntityMentionScanService._extract_context_snippet(
            text, 100, 105, window=75
        )
        assert snippet.startswith("...")
        assert snippet.endswith("...")
        assert "MATCH" in snippet

    def test_snippet_no_truncation(self) -> None:
        """Short text produces no ellipsis."""
        text = "Hello MATCH world"
        start = text.index("MATCH")
        end = start + 5
        snippet = EntityMentionScanService._extract_context_snippet(
            text, start, end, window=75
        )
        assert not snippet.startswith("...")
        assert not snippet.endswith("...")
        assert snippet == text

    def test_snippet_match_at_very_start(self) -> None:
        """Match at position 0 produces no leading ellipsis."""
        text = "MATCH" + "x" * 200
        snippet = EntityMentionScanService._extract_context_snippet(
            text, 0, 5, window=75
        )
        assert not snippet.startswith("...")
        assert snippet.endswith("...")
        assert snippet[: len("MATCH")] == "MATCH"

    def test_snippet_match_at_very_end(self) -> None:
        """Match at the end produces no trailing ellipsis."""
        text = "x" * 200 + "MATCH"
        start = 200
        end = 205
        snippet = EntityMentionScanService._extract_context_snippet(
            text, start, end, window=75
        )
        assert snippet.startswith("...")
        assert not snippet.endswith("...")
        assert snippet.endswith("MATCH")
