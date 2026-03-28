"""
Unit tests for EntityMentionScanService.

Tests service-layer logic using mocked repository, session, and session factory
dependencies. No real database connection is required.

All tests cover:
- Pattern construction with re.escape()
- Entity status filtering (active only)
- Segment processing (empty text skips, short alias warnings)
- Filter parameters (entity_type, video_ids, language_code)
- Batch processing mechanics
- ON CONFLICT skip handling via bulk_create_with_conflict_skip
- Counter updates (skipped in dry-run, applied in live mode)
- Full rescan (delete_by_scope before scan)
- New entities only (zero-mention filter)
- ScanResult field population
- Failed batch handling (counted, scan continues)
- ASR-error alias filtering delegation to repository (Feature 044 T010)

Feature 038 -- Entity Mention Detection (T015)
Feature 044 -- Data Accuracy & Search Reliability (T010)
"""

from __future__ import annotations

import re
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# CRITICAL: Module-level asyncio marker ensures async tests run properly
# with coverage tools, avoiding silent test-skipping (see CLAUDE.md).

# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def _make_uuid() -> uuid.UUID:
    """Return a fresh UUID4 for test data."""
    return uuid.uuid4()


def _make_entity_row(
    entity_id: uuid.UUID | None = None,
    canonical_name: str = "Aaron",
    entity_type: str = "person",
    status: str = "active",
) -> MagicMock:
    """Create a mock ORM NamedEntity row."""
    row = MagicMock()
    row.id = entity_id or _make_uuid()
    row.canonical_name = canonical_name
    row.entity_type = entity_type
    row.status = status
    return row


def _make_alias_row(entity_id: uuid.UUID, alias_name: str) -> MagicMock:
    """Create a mock ORM EntityAlias row."""
    row = MagicMock()
    row.entity_id = entity_id
    row.alias_name = alias_name
    return row


def _make_segment_row(
    seg_id: int = 1,
    video_id: str = "dQw4w9WgXcQ",
    language_code: str = "en",
    start_time: float = 0.0,
    effective_text: str = "Aaron is here today",
) -> MagicMock:
    """Create a mock transcript segment row matching service column access."""
    row = MagicMock()
    row.id = seg_id
    row.video_id = video_id
    row.language_code = language_code
    row.start_time = start_time
    row.effective_text = effective_text
    return row


def _build_service(session_factory: Any) -> Any:
    """Import and construct EntityMentionScanService."""
    from chronovista.services.entity_mention_scan_service import (
        EntityMentionScanService,
    )

    return EntityMentionScanService(session_factory=session_factory)


def _make_session_context_manager(session: AsyncMock) -> MagicMock:
    """Async context manager wrapping the given session."""
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def _make_session_factory(session: AsyncMock) -> MagicMock:
    """Session factory callable that returns the async context manager."""
    factory = MagicMock()
    factory.return_value = _make_session_context_manager(session)
    return factory


def _scalars_execute(values: list[Any]) -> MagicMock:
    """Build a mock execute() result where .scalars().all() returns values."""
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = values
    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock
    result_mock.all.return_value = values  # for .all() direct access
    return result_mock


def _raw_execute(rows: list[Any]) -> MagicMock:
    """Build a mock execute() result where .all() returns rows."""
    result_mock = MagicMock()
    result_mock.all.return_value = rows
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = rows
    result_mock.scalars.return_value = scalars_mock
    return result_mock


# ---------------------------------------------------------------------------
# TestConstructor
# ---------------------------------------------------------------------------


class TestConstructor:
    """Verify that the service stores dependencies correctly."""

    def test_stores_session_factory(self) -> None:
        """Constructor must store the session_factory dependency."""
        from chronovista.repositories.entity_mention_repository import (
            EntityMentionRepository,
        )
        from chronovista.services.entity_mention_scan_service import (
            EntityMentionScanService,
        )

        factory = MagicMock()
        svc = EntityMentionScanService(session_factory=factory)

        assert svc._session_factory is factory
        assert isinstance(svc._mention_repo, EntityMentionRepository)


# ---------------------------------------------------------------------------
# TestPatternConstruction
# ---------------------------------------------------------------------------


class TestPatternConstruction:
    """Verify that re.escape() is applied to entity names and aliases."""

    async def _call_load_patterns(
        self,
        entity_row: MagicMock,
        alias_rows: list[MagicMock],
    ) -> list[Any]:
        """Helper: call _load_entity_patterns directly with mocked session."""
        session = AsyncMock()

        entity_result = _scalars_execute([entity_row])
        alias_result = _scalars_execute(alias_rows)

        session.execute = AsyncMock(side_effect=[entity_result, alias_result])

        svc = _build_service(MagicMock())
        result: list[Any] = await svc._load_entity_patterns(
            session, entity_type=None, new_entities_only=False
        )
        return result

    async def test_special_chars_are_escaped_cpp(self) -> None:
        """'C++' must produce re.escape('C++') == 'C\\+\\+' in pg_pattern."""
        entity_id = _make_uuid()
        entity_row = _make_entity_row(entity_id=entity_id, canonical_name="C++")
        patterns = await self._call_load_patterns(entity_row, [])

        assert len(patterns) == 1
        assert re.escape("C++") in patterns[0].pg_pattern

    async def test_special_chars_are_escaped_att(self) -> None:
        """'AT&T' must produce re.escape('AT&T') == 'AT\\&T' in pg_pattern."""
        entity_id = _make_uuid()
        entity_row = _make_entity_row(entity_id=entity_id, canonical_name="AT&T")
        patterns = await self._call_load_patterns(entity_row, [])

        assert len(patterns) == 1
        assert re.escape("AT&T") in patterns[0].pg_pattern

    async def test_alias_special_chars_are_escaped(self) -> None:
        """Alias names with special chars must also be escaped in pg_pattern."""
        entity_id = _make_uuid()
        entity_row = _make_entity_row(entity_id=entity_id, canonical_name="Python")
        alias_row = _make_alias_row(entity_id=entity_id, alias_name="Python (lang.)")
        patterns = await self._call_load_patterns(entity_row, [alias_row])

        assert len(patterns) == 1
        assert re.escape("Python (lang.)") in patterns[0].pg_pattern

    async def test_canonical_name_included_without_alias(self) -> None:
        """Even with zero aliases, the canonical name appears in alias_names."""
        entity_id = _make_uuid()
        entity_row = _make_entity_row(entity_id=entity_id, canonical_name="Google")
        patterns = await self._call_load_patterns(entity_row, [])

        assert len(patterns) == 1
        assert "Google" in patterns[0].alias_names
        assert re.escape("Google") in patterns[0].pg_pattern

    async def test_multiple_aliases_joined_in_pattern(self) -> None:
        """Multiple alias names are joined with '|' in the pg_pattern."""
        entity_id = _make_uuid()
        entity_row = _make_entity_row(entity_id=entity_id, canonical_name="Elon Musk")
        alias1 = _make_alias_row(entity_id=entity_id, alias_name="Musk")
        alias2 = _make_alias_row(entity_id=entity_id, alias_name="Tesla CEO")
        patterns = await self._call_load_patterns(entity_row, [alias1, alias2])

        assert len(patterns) == 1
        pg = patterns[0].pg_pattern
        assert re.escape("Elon Musk") in pg
        assert re.escape("Musk") in pg
        assert re.escape("Tesla CEO") in pg
        # Joined with "|"
        assert "|" in pg

    async def test_duplicate_alias_not_doubled(self) -> None:
        """If an alias name equals the canonical name, it must appear only once."""
        entity_id = _make_uuid()
        entity_row = _make_entity_row(entity_id=entity_id, canonical_name="Google")
        alias_row = _make_alias_row(entity_id=entity_id, alias_name="Google")
        patterns = await self._call_load_patterns(entity_row, [alias_row])

        assert len(patterns) == 1
        assert patterns[0].alias_names.count("Google") == 1

    # ------------------------------------------------------------------
    # Bug fix: asr_error aliases must be excluded from scan patterns
    # ------------------------------------------------------------------

    async def test_alias_query_excludes_asr_error_type_in_sql(self) -> None:
        """The alias query emitted by _load_entity_patterns must filter out asr_error aliases.

        Bug fix (Feature 038/044): Before the fix, alias_stmt had no alias_type
        filter, so ASR-error aliases (e.g. "Bonazo") were included in scan
        patterns and created false rule_match mentions.  After the fix the WHERE
        clause must contain ``alias_type != 'asr_error'`` (or equivalent NOT
        IN / != expression).

        This test inspects the compiled SQL of the *second* execute() call
        (the alias query) to confirm the exclusion filter is present.
        """
        from sqlalchemy.dialects import postgresql as pg_dialect

        entity_id = _make_uuid()
        entity_row = _make_entity_row(entity_id=entity_id, canonical_name="Bonaparte")

        session = AsyncMock()
        entity_result = _scalars_execute([entity_row])
        alias_result = _scalars_execute([])
        session.execute = AsyncMock(side_effect=[entity_result, alias_result])

        svc = _build_service(MagicMock())
        await svc._load_entity_patterns(session, entity_type=None, new_entities_only=False)

        # The alias query is the second execute() call
        assert session.execute.call_count == 2, (
            "Expected exactly two execute() calls: one for entities, one for aliases"
        )
        alias_stmt = session.execute.call_args_list[1].args[0]
        sql_str = str(
            alias_stmt.compile(
                dialect=pg_dialect.dialect(),  # type: ignore[no-untyped-call]
                compile_kwargs={"literal_binds": True},
            )
        )

        assert "asr_error" in sql_str, (
            "Expected 'asr_error' exclusion filter in the alias query SQL; "
            f"got: {sql_str[:600]}"
        )

    async def test_non_asr_error_aliases_are_included_as_scan_patterns(self) -> None:
        """Aliases with types other than asr_error must appear in scan patterns.

        The fix must only exclude asr_error aliases; name_variant, abbreviation,
        nickname, translated_name, and former_name aliases must still be returned
        by the alias query and contribute to pg_pattern.
        """
        entity_id = _make_uuid()
        entity_row = _make_entity_row(entity_id=entity_id, canonical_name="Napoleon")
        # Simulate DB returning non-ASR-error aliases (after SQL filter is applied)
        name_variant_alias = _make_alias_row(entity_id=entity_id, alias_name="Nap")
        abbreviation_alias = _make_alias_row(entity_id=entity_id, alias_name="NB")

        patterns = await self._call_load_patterns(
            entity_row, [name_variant_alias, abbreviation_alias]
        )

        assert len(patterns) == 1
        pat = patterns[0]
        # Both non-ASR-error aliases must appear in the pattern
        assert "Nap" in pat.alias_names, "name_variant alias 'Nap' must be in alias_names"
        assert "NB" in pat.alias_names, "abbreviation alias 'NB' must be in alias_names"
        assert re.escape("Nap") in pat.pg_pattern
        assert re.escape("NB") in pat.pg_pattern

    async def test_asr_error_alias_not_present_in_pattern_names(self) -> None:
        """When the DB returns only non-ASR-error aliases, no ASR noise forms appear.

        This models the post-fix behaviour: the alias query WHERE clause filters
        out asr_error rows at the database level.  If the DB correctly excludes
        them, the resulting alias_names list must not contain ASR noise forms.

        The test simulates the DB having applied the filter already (returning
        only non-asr_error aliases) and confirms the service builds patterns
        from those aliases only.
        """
        entity_id = _make_uuid()
        entity_row = _make_entity_row(entity_id=entity_id, canonical_name="Bonanza")
        # Simulates DB returning zero aliases after WHERE alias_type != 'asr_error'
        # filters out the only alias ("Bonazo") which was an asr_error alias
        patterns = await self._call_load_patterns(entity_row, [])

        assert len(patterns) == 1
        pat = patterns[0]
        # Only the canonical name must appear — no ASR noise forms
        assert pat.alias_names == ["Bonanza"], (
            f"Expected only canonical name in alias_names; got: {pat.alias_names}"
        )
        # The ASR-error form "Bonazo" must not appear in pg_pattern
        assert "Bonazo" not in pat.pg_pattern


# ---------------------------------------------------------------------------
# TestEntityStatusFiltering
# ---------------------------------------------------------------------------


class TestEntityStatusFiltering:
    """Verify that only 'active' entities are loaded for scanning."""

    async def test_no_patterns_when_no_entities_returned(self) -> None:
        """When entity query returns empty list, scan returns immediately with zero counts."""
        session = AsyncMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()

        entity_result = _scalars_execute([])
        session.execute = AsyncMock(return_value=entity_result)

        factory = _make_session_factory(session)
        svc = _build_service(factory)

        from chronovista.services.entity_mention_scan_service import ScanResult

        result = await svc.scan()

        assert isinstance(result, ScanResult)
        assert result.segments_scanned == 0
        assert result.mentions_found == 0
        assert result.unique_entities == 0

    async def test_entity_type_filter_forwarded_to_load(self) -> None:
        """The entity_type parameter must be forwarded to _load_entity_patterns."""
        session = AsyncMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()

        # Entities query returns empty → scan exits early
        entity_result = _scalars_execute([])
        session.execute = AsyncMock(return_value=entity_result)

        factory = _make_session_factory(session)
        svc = _build_service(factory)

        captured_args: list[Any] = []

        original_load = svc._load_entity_patterns

        async def spy_load(s: Any, entity_type: Any, new_entities_only: Any, entity_ids: Any = None) -> Any:
            captured_args.append({"entity_type": entity_type, "new_entities_only": new_entities_only, "entity_ids": entity_ids})
            return await original_load(s, entity_type=entity_type, new_entities_only=new_entities_only, entity_ids=entity_ids)

        with patch.object(svc, "_load_entity_patterns", side_effect=spy_load):
            await svc.scan(entity_type="person")

        assert captured_args[0]["entity_type"] == "person"


# ---------------------------------------------------------------------------
# TestEmptyTextSkip
# ---------------------------------------------------------------------------


class TestEmptyTextSkip:
    """Verify that segments with empty effective_text are skipped."""

    async def test_segment_with_empty_string_produces_no_mention(self) -> None:
        """Segment with effective_text='' must not generate a mention."""
        from chronovista.services.entity_mention_scan_service import _EntityPattern

        entity_id = _make_uuid()
        pattern = _EntityPattern(
            entity_id=entity_id,
            canonical_name="Aaron",
            entity_type="person",
            pg_pattern=re.escape("Aaron"),
            alias_names=["Aaron"],
        )

        empty_seg = _make_segment_row(seg_id=1, effective_text="")
        non_empty_seg = _make_segment_row(seg_id=2, effective_text="Aaron was here")

        session = AsyncMock()
        existing_result = _scalars_execute([])
        session.execute = AsyncMock(return_value=existing_result)

        svc = _build_service(MagicMock())

        mentions, skipped, _, _, _ = await svc._scan_batch(
            session,
            batch_rows=[empty_seg, non_empty_seg],
            patterns=[pattern],
            full_rescan=False,
            dry_run=False,
            limit=None,
            current_preview_count=0,
        )

        assert len(mentions) == 1
        assert mentions[0].segment_id == 2

    async def test_segment_with_none_text_produces_no_mention(self) -> None:
        """Segment with effective_text=None must not generate a mention."""
        from chronovista.services.entity_mention_scan_service import _EntityPattern

        entity_id = _make_uuid()
        pattern = _EntityPattern(
            entity_id=entity_id,
            canonical_name="Google",
            entity_type="organization",
            pg_pattern=re.escape("Google"),
            alias_names=["Google"],
        )

        none_seg = _make_segment_row(seg_id=10, effective_text="")
        none_seg.effective_text = None

        session = AsyncMock()
        existing_result = _scalars_execute([])
        session.execute = AsyncMock(return_value=existing_result)

        svc = _build_service(MagicMock())

        mentions, _, _, _, _ = await svc._scan_batch(
            session,
            batch_rows=[none_seg],
            patterns=[pattern],
            full_rescan=False,
            dry_run=False,
            limit=None,
            current_preview_count=0,
        )

        assert mentions == []


# ---------------------------------------------------------------------------
# TestZeroAliasHandling
# ---------------------------------------------------------------------------


class TestZeroAliasHandling:
    """Verify that entities with no aliases scan using canonical_name only."""

    async def test_entity_no_aliases_canonical_name_used_for_matching(self) -> None:
        """Zero aliases: segment matching uses canonical name pattern."""
        from chronovista.services.entity_mention_scan_service import _EntityPattern

        entity_id = _make_uuid()
        pattern = _EntityPattern(
            entity_id=entity_id,
            canonical_name="Tesla",
            entity_type="organization",
            pg_pattern=re.escape("Tesla"),
            alias_names=["Tesla"],  # only canonical
        )

        seg = _make_segment_row(effective_text="Tesla just announced a new car")

        session = AsyncMock()
        existing_result = _scalars_execute([])
        session.execute = AsyncMock(return_value=existing_result)

        svc = _build_service(MagicMock())

        mentions, _, _, _, _ = await svc._scan_batch(
            session,
            batch_rows=[seg],
            patterns=[pattern],
            full_rescan=False,
            dry_run=False,
            limit=None,
            current_preview_count=0,
        )

        assert len(mentions) == 1
        assert mentions[0].mention_text.lower() == "tesla"

    async def test_entity_no_aliases_has_exactly_one_alias_name(self) -> None:
        """Pattern with zero aliases has exactly one alias_name entry (canonical)."""
        from chronovista.services.entity_mention_scan_service import _EntityPattern

        entity_id = _make_uuid()
        pattern = _EntityPattern(
            entity_id=entity_id,
            canonical_name="SpaceX",
            entity_type="organization",
            pg_pattern=re.escape("SpaceX"),
            alias_names=["SpaceX"],
        )

        assert len(pattern.alias_names) == 1
        assert pattern.alias_names[0] == "SpaceX"


# ---------------------------------------------------------------------------
# TestShortAliasWarning
# ---------------------------------------------------------------------------


class TestShortAliasWarning:
    """Verify that aliases shorter than 3 characters trigger a WARNING log."""

    async def test_short_alias_triggers_warning(self, caplog: Any) -> None:
        """An alias of length 2 must emit a WARNING log."""
        import logging

        entity_id = _make_uuid()
        entity_row = _make_entity_row(entity_id=entity_id, canonical_name="Apple Inc")
        short_alias = _make_alias_row(entity_id=entity_id, alias_name="AI")  # 2 chars

        session = AsyncMock()
        entity_result = _scalars_execute([entity_row])
        alias_result = _scalars_execute([short_alias])
        session.execute = AsyncMock(side_effect=[entity_result, alias_result])

        svc = _build_service(MagicMock())

        with caplog.at_level(
            logging.WARNING, logger="chronovista.services.entity_mention_scan_service"
        ):
            await svc._load_entity_patterns(
                session, entity_type=None, new_entities_only=False
            )

        warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert any("AI" in msg for msg in warning_messages), (
            f"Expected WARNING about 'AI', got: {warning_messages}"
        )

    async def test_single_char_alias_triggers_warning(self, caplog: Any) -> None:
        """An alias of length 1 must also emit a WARNING log."""
        import logging

        entity_id = _make_uuid()
        entity_row = _make_entity_row(entity_id=entity_id, canonical_name="X Corp")
        short_alias = _make_alias_row(entity_id=entity_id, alias_name="X")  # 1 char

        session = AsyncMock()
        entity_result = _scalars_execute([entity_row])
        alias_result = _scalars_execute([short_alias])
        session.execute = AsyncMock(side_effect=[entity_result, alias_result])

        svc = _build_service(MagicMock())

        with caplog.at_level(
            logging.WARNING, logger="chronovista.services.entity_mention_scan_service"
        ):
            await svc._load_entity_patterns(
                session, entity_type=None, new_entities_only=False
            )

        warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert any("X" in msg for msg in warning_messages)

    async def test_alias_of_length_3_no_warning(self, caplog: Any) -> None:
        """An alias of exactly 3 characters must NOT emit a WARNING."""
        import logging

        entity_id = _make_uuid()
        entity_row = _make_entity_row(entity_id=entity_id, canonical_name="International Business Machines")
        ok_alias = _make_alias_row(entity_id=entity_id, alias_name="IBM")  # 3 chars

        session = AsyncMock()
        entity_result = _scalars_execute([entity_row])
        alias_result = _scalars_execute([ok_alias])
        session.execute = AsyncMock(side_effect=[entity_result, alias_result])

        svc = _build_service(MagicMock())

        with caplog.at_level(
            logging.WARNING, logger="chronovista.services.entity_mention_scan_service"
        ):
            await svc._load_entity_patterns(
                session, entity_type=None, new_entities_only=False
            )

        warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert not any("IBM" in msg for msg in warning_messages)


# ---------------------------------------------------------------------------
# TestFilterParameters
# ---------------------------------------------------------------------------


class TestFilterParameters:
    """Verify that entity_type, video_ids, and language_code filters are forwarded."""

    async def test_video_ids_filter_applied_to_fetch(self) -> None:
        """When video_ids is supplied, _fetch_segment_batch must receive it."""
        entity_id = _make_uuid()
        entity_row = _make_entity_row(entity_id=entity_id)

        session = AsyncMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()

        entity_result = _scalars_execute([entity_row])
        alias_result = _scalars_execute([])
        session.execute = AsyncMock(side_effect=[entity_result, alias_result])

        factory = _make_session_factory(session)
        svc = _build_service(factory)

        captured: list[dict[str, Any]] = []

        async def capture_fetch(
            _session: Any,
            video_ids: list[str] | None,
            language_code: str | None,
            batch_size: int,
            offset: int,
        ) -> list[Any]:
            captured.append({"video_ids": video_ids, "language_code": language_code})
            return []  # End loop

        with patch.object(svc, "_fetch_segment_batch", side_effect=capture_fetch):
            await svc.scan(video_ids=["abc123defgh"])

        assert captured
        assert captured[0]["video_ids"] == ["abc123defgh"]

    async def test_language_code_filter_applied_to_fetch(self) -> None:
        """When language_code is supplied, _fetch_segment_batch must receive it."""
        entity_id = _make_uuid()
        entity_row = _make_entity_row(entity_id=entity_id)

        session = AsyncMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()

        entity_result = _scalars_execute([entity_row])
        alias_result = _scalars_execute([])
        session.execute = AsyncMock(side_effect=[entity_result, alias_result])

        factory = _make_session_factory(session)
        svc = _build_service(factory)

        captured: list[dict[str, Any]] = []

        async def capture_fetch(
            _session: Any,
            video_ids: list[str] | None,
            language_code: str | None,
            batch_size: int,
            offset: int,
        ) -> list[Any]:
            captured.append({"language_code": language_code})
            return []

        with patch.object(svc, "_fetch_segment_batch", side_effect=capture_fetch):
            await svc.scan(language_code="es")

        assert captured
        assert captured[0]["language_code"] == "es"

    async def test_entity_type_forwarded_to_load_patterns(self) -> None:
        """entity_type must be passed to _load_entity_patterns."""
        session = AsyncMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()

        entity_result = _scalars_execute([])
        session.execute = AsyncMock(return_value=entity_result)

        factory = _make_session_factory(session)
        svc = _build_service(factory)

        captured: list[dict[str, Any]] = []

        async def spy_load(s: Any, entity_type: Any, new_entities_only: Any, entity_ids: Any = None) -> list[Any]:
            captured.append({"entity_type": entity_type})
            return []

        with patch.object(svc, "_load_entity_patterns", side_effect=spy_load):
            await svc.scan(entity_type="organization")

        assert captured[0]["entity_type"] == "organization"


# ---------------------------------------------------------------------------
# TestBatchProcessing
# ---------------------------------------------------------------------------


class TestBatchProcessing:
    """Verify that segments are processed in batch_size chunks."""

    async def test_segments_scanned_accumulates_across_batches(self) -> None:
        """segments_scanned increases by the batch length each iteration."""
        from chronovista.services.entity_mention_scan_service import _EntityPattern

        entity_id = _make_uuid()
        fake_pattern = _EntityPattern(
            entity_id=entity_id,
            canonical_name="Foo",
            entity_type="person",
            pg_pattern=re.escape("Foo"),
            alias_names=["Foo"],
        )

        session = AsyncMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()

        factory = _make_session_factory(session)
        svc = _build_service(factory)

        batch1 = [_make_segment_row(seg_id=i, effective_text="no match here") for i in range(3)]
        batch2 = [_make_segment_row(seg_id=i + 10, effective_text="no match here") for i in range(2)]
        batches = [batch1, batch2, []]
        batch_idx = 0

        async def fetch_batches(
            _session: Any,
            video_ids: Any,
            language_code: Any,
            batch_size: int,
            offset: int,
        ) -> list[Any]:
            nonlocal batch_idx
            result = batches[batch_idx] if batch_idx < len(batches) else []
            batch_idx += 1
            return result

        svc._mention_repo.update_entity_counters = AsyncMock()
        svc._mention_repo.update_alias_counters = AsyncMock()
        with (
            patch.object(svc, "_load_entity_patterns", return_value=[fake_pattern]),
            patch.object(svc, "_fetch_segment_batch", side_effect=fetch_batches),
            patch.object(svc, "_scan_batch", return_value=([], 0, [], 0, 0)),
        ):
            result = await svc.scan()

        assert result.segments_scanned == 5  # 3 + 2

    async def test_scan_exits_when_batch_empty(self) -> None:
        """Scan must stop when _fetch_segment_batch returns an empty list."""
        from chronovista.services.entity_mention_scan_service import _EntityPattern

        entity_id = _make_uuid()
        fake_pattern = _EntityPattern(
            entity_id=entity_id,
            canonical_name="Bar",
            entity_type="person",
            pg_pattern=re.escape("Bar"),
            alias_names=["Bar"],
        )

        session = AsyncMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()

        factory = _make_session_factory(session)
        svc = _build_service(factory)

        fetch_calls = 0

        async def one_batch_then_empty(*args: Any, **kwargs: Any) -> list[Any]:
            nonlocal fetch_calls
            fetch_calls += 1
            if fetch_calls == 1:
                return [_make_segment_row()]
            return []

        svc._mention_repo.update_entity_counters = AsyncMock()
        svc._mention_repo.update_alias_counters = AsyncMock()
        with (
            patch.object(svc, "_load_entity_patterns", return_value=[fake_pattern]),
            patch.object(svc, "_fetch_segment_batch", side_effect=one_batch_then_empty),
            patch.object(svc, "_scan_batch", return_value=([], 0, [], 0, 0)),
        ):
            await svc.scan()

        assert fetch_calls == 2  # one with data, one empty to stop


# ---------------------------------------------------------------------------
# TestBulkCreateConflictSkip
# ---------------------------------------------------------------------------


class TestBulkCreateConflictSkip:
    """Verify mentions_skipped calculation from bulk_create_with_conflict_skip."""

    async def test_skipped_count_is_batch_minus_inserted(self) -> None:
        """mentions_skipped = len(batch_mentions) - inserted_count."""
        from chronovista.models.entity_mention import EntityMentionCreate
        from chronovista.models.enums import DetectionMethod
        from chronovista.services.entity_mention_scan_service import _EntityPattern

        entity_id = _make_uuid()
        fake_pattern = _EntityPattern(
            entity_id=entity_id,
            canonical_name="Aaron",
            entity_type="person",
            pg_pattern=re.escape("Aaron"),
            alias_names=["Aaron"],
        )

        session = AsyncMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()

        factory = _make_session_factory(session)
        svc = _build_service(factory)

        # _scan_batch returns 3 EntityMentionCreate objects
        mention_creates = [
            EntityMentionCreate(
                entity_id=entity_id,
                segment_id=i,
                video_id="dQw4w9WgXcQ",
                language_code="en",
                mention_text="Aaron",
                detection_method=DetectionMethod.RULE_MATCH,
                confidence=1.0,
            )
            for i in range(1, 4)
        ]

        # Repository says only 2 were inserted (1 duplicate skipped)
        svc._mention_repo.bulk_create_with_conflict_skip = AsyncMock(return_value=2)
        svc._mention_repo.update_entity_counters = AsyncMock()
        svc._mention_repo.update_alias_counters = AsyncMock()
        with (
            patch.object(svc, "_load_entity_patterns", return_value=[fake_pattern]),
            patch.object(svc, "_fetch_segment_batch", side_effect=[[_make_segment_row()], []]),
            patch.object(svc, "_scan_batch", return_value=(mention_creates, 0, [], 0, 0)),
        ):
            result = await svc.scan()

        assert result.mentions_found == 2
        assert result.mentions_skipped == 1  # 3 found - 2 inserted

    async def test_bulk_create_called_with_mention_list(self) -> None:
        """bulk_create_with_conflict_skip must be called with the mention list."""
        from chronovista.models.entity_mention import EntityMentionCreate
        from chronovista.models.enums import DetectionMethod
        from chronovista.services.entity_mention_scan_service import _EntityPattern

        entity_id = _make_uuid()
        fake_pattern = _EntityPattern(
            entity_id=entity_id,
            canonical_name="Babel",
            entity_type="work",
            pg_pattern=re.escape("Babel"),
            alias_names=["Babel"],
        )

        session = AsyncMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()

        factory = _make_session_factory(session)
        svc = _build_service(factory)

        mention = EntityMentionCreate(
            entity_id=entity_id,
            segment_id=5,
            video_id="dQw4w9WgXcQ",
            language_code="en",
            mention_text="Babel",
            detection_method=DetectionMethod.RULE_MATCH,
            confidence=1.0,
        )
        svc._mention_repo.bulk_create_with_conflict_skip = AsyncMock(return_value=1)
        svc._mention_repo.update_entity_counters = AsyncMock()
        svc._mention_repo.update_alias_counters = AsyncMock()
        with (
            patch.object(svc, "_load_entity_patterns", return_value=[fake_pattern]),
            patch.object(svc, "_fetch_segment_batch", side_effect=[[_make_segment_row()], []]),
            patch.object(svc, "_scan_batch", return_value=([mention], 0, [], 0, 0)),
        ):
            await svc.scan()
        svc._mention_repo.bulk_create_with_conflict_skip.assert_called_once()
        call_args = svc._mention_repo.bulk_create_with_conflict_skip.call_args      # Second positional argument is the mentions list
        assert mention in call_args[0][1]

    async def test_bulk_create_not_called_when_no_mentions(self) -> None:
        """When _scan_batch returns zero mentions, bulk_create must not be called."""
        from chronovista.services.entity_mention_scan_service import _EntityPattern

        entity_id = _make_uuid()
        fake_pattern = _EntityPattern(
            entity_id=entity_id,
            canonical_name="Nobody",
            entity_type="person",
            pg_pattern=re.escape("Nobody"),
            alias_names=["Nobody"],
        )

        session = AsyncMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()

        factory = _make_session_factory(session)
        svc = _build_service(factory)
        svc._mention_repo.bulk_create_with_conflict_skip = AsyncMock(return_value=0)
        svc._mention_repo.update_entity_counters = AsyncMock()
        svc._mention_repo.update_alias_counters = AsyncMock()
        with (
            patch.object(svc, "_load_entity_patterns", return_value=[fake_pattern]),
            patch.object(svc, "_fetch_segment_batch", side_effect=[[_make_segment_row()], []]),
            patch.object(svc, "_scan_batch", return_value=([], 0, [], 0, 0)),
        ):
            await svc.scan()
        svc._mention_repo.bulk_create_with_conflict_skip.assert_not_called()

# ---------------------------------------------------------------------------
# TestCounterUpdate
# ---------------------------------------------------------------------------


class TestCounterUpdate:
    """Verify that update_entity_counters and update_alias_counters are called only in live mode."""

    async def test_update_entity_counters_called_in_live_mode(self) -> None:
        """In live mode with matches, update_entity_counters must be called."""
        from chronovista.models.entity_mention import EntityMentionCreate
        from chronovista.models.enums import DetectionMethod
        from chronovista.services.entity_mention_scan_service import _EntityPattern

        entity_id = _make_uuid()
        fake_pattern = _EntityPattern(
            entity_id=entity_id,
            canonical_name="OpenAI",
            entity_type="organization",
            pg_pattern=re.escape("OpenAI"),
            alias_names=["OpenAI"],
        )

        session = AsyncMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()

        factory = _make_session_factory(session)
        svc = _build_service(factory)

        mention = EntityMentionCreate(
            entity_id=entity_id,
            segment_id=1,
            video_id="dQw4w9WgXcQ",
            language_code="en",
            mention_text="OpenAI",
            detection_method=DetectionMethod.RULE_MATCH,
            confidence=1.0,
        )
        svc._mention_repo.bulk_create_with_conflict_skip = AsyncMock(return_value=1)
        svc._mention_repo.update_entity_counters = AsyncMock()
        svc._mention_repo.update_alias_counters = AsyncMock()
        with (
            patch.object(svc, "_load_entity_patterns", return_value=[fake_pattern]),
            patch.object(svc, "_fetch_segment_batch", side_effect=[[_make_segment_row()], []]),
            patch.object(svc, "_scan_batch", return_value=([mention], 0, [], 0, 0)),
        ):
            await svc.scan(dry_run=False)
        svc._mention_repo.update_entity_counters.assert_called_once()
        call_args = svc._mention_repo.update_entity_counters.call_args
        assert entity_id in call_args[0][1]
        svc._mention_repo.update_alias_counters.assert_called_once()
        alias_call_args = svc._mention_repo.update_alias_counters.call_args
        assert entity_id in alias_call_args[0][1]

    async def test_update_entity_counters_not_called_in_dry_run(self) -> None:
        """In dry-run mode, update_entity_counters must NOT be called."""
        from chronovista.models.entity_mention import EntityMentionCreate
        from chronovista.models.enums import DetectionMethod
        from chronovista.services.entity_mention_scan_service import _EntityPattern

        entity_id = _make_uuid()
        fake_pattern = _EntityPattern(
            entity_id=entity_id,
            canonical_name="DeepMind",
            entity_type="organization",
            pg_pattern=re.escape("DeepMind"),
            alias_names=["DeepMind"],
        )

        session = AsyncMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()

        factory = _make_session_factory(session)
        svc = _build_service(factory)

        mention = EntityMentionCreate(
            entity_id=entity_id,
            segment_id=1,
            video_id="dQw4w9WgXcQ",
            language_code="en",
            mention_text="DeepMind",
            detection_method=DetectionMethod.RULE_MATCH,
            confidence=1.0,
        )
        svc._mention_repo.bulk_create_with_conflict_skip = AsyncMock(return_value=0)
        svc._mention_repo.update_entity_counters = AsyncMock()
        svc._mention_repo.update_alias_counters = AsyncMock()
        with (
            patch.object(svc, "_load_entity_patterns", return_value=[fake_pattern]),
            patch.object(svc, "_fetch_segment_batch", side_effect=[[_make_segment_row()], []]),
            patch.object(svc, "_scan_batch", return_value=([mention], 0, [], 0, 0)),
        ):
            await svc.scan(dry_run=True)
        svc._mention_repo.update_entity_counters.assert_not_called()
        svc._mention_repo.update_alias_counters.assert_not_called()

    async def test_update_entity_counters_not_called_when_no_matches(self) -> None:
        """When no entities produced mentions, update_entity_counters must not be called."""
        from chronovista.services.entity_mention_scan_service import _EntityPattern

        entity_id = _make_uuid()
        fake_pattern = _EntityPattern(
            entity_id=entity_id,
            canonical_name="Phantom",
            entity_type="person",
            pg_pattern=re.escape("Phantom"),
            alias_names=["Phantom"],
        )

        session = AsyncMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()

        factory = _make_session_factory(session)
        svc = _build_service(factory)
        svc._mention_repo.bulk_create_with_conflict_skip = AsyncMock(return_value=0)
        svc._mention_repo.update_entity_counters = AsyncMock()
        svc._mention_repo.update_alias_counters = AsyncMock()
        with (
            patch.object(svc, "_load_entity_patterns", return_value=[fake_pattern]),
            patch.object(svc, "_fetch_segment_batch", side_effect=[[_make_segment_row()], []]),
            patch.object(svc, "_scan_batch", return_value=([], 0, [], 0, 0)),
        ):
            await svc.scan(dry_run=False)
        svc._mention_repo.update_entity_counters.assert_not_called()
        svc._mention_repo.update_alias_counters.assert_not_called()

    # ------------------------------------------------------------------
    # T010 — US2: Verify delegation of ASR filtering to repository
    # ------------------------------------------------------------------

    async def test_update_entity_counters_receives_all_matched_entity_ids(
        self,
    ) -> None:
        """The service passes ALL matched entity IDs to update_entity_counters.

        The ASR-error alias filtering is entirely the repository's
        responsibility (Feature 044 T008).  The scan service must pass every
        entity that produced at least one mention row — including those whose
        mentions may later be filtered out by the repository.  This test
        verifies that the service does not pre-filter entity IDs before
        delegating to the repository.
        """
        from chronovista.models.entity_mention import EntityMentionCreate
        from chronovista.models.enums import DetectionMethod
        from chronovista.services.entity_mention_scan_service import _EntityPattern

        entity_id_a = _make_uuid()
        entity_id_b = _make_uuid()

        fake_patterns = [
            _EntityPattern(
                entity_id=entity_id_a,
                canonical_name="VisibleEntity",
                entity_type="organization",
                pg_pattern=re.escape("VisibleEntity"),
                alias_names=["VisibleEntity"],
            ),
            _EntityPattern(
                entity_id=entity_id_b,
                canonical_name="ASROnlyEntity",
                entity_type="organization",
                pg_pattern=re.escape("asronlyform"),
                alias_names=["asronlyform"],
            ),
        ]

        session = AsyncMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()

        factory = _make_session_factory(session)
        svc = _build_service(factory)

        # Two mentions: one for each entity
        mentions = [
            EntityMentionCreate(
                entity_id=entity_id_a,
                segment_id=1,
                video_id="dQw4w9WgXcQ",
                language_code="en",
                mention_text="VisibleEntity",
                detection_method=DetectionMethod.RULE_MATCH,
                confidence=1.0,
            ),
            EntityMentionCreate(
                entity_id=entity_id_b,
                segment_id=2,
                video_id="dQw4w9WgXcQ",
                language_code="en",
                mention_text="asronlyform",
                detection_method=DetectionMethod.RULE_MATCH,
                confidence=1.0,
            ),
        ]

        svc._mention_repo.bulk_create_with_conflict_skip = AsyncMock(return_value=2)
        svc._mention_repo.update_entity_counters = AsyncMock()
        svc._mention_repo.update_alias_counters = AsyncMock()
        with (
            patch.object(svc, "_load_entity_patterns", return_value=fake_patterns),
            patch.object(svc, "_fetch_segment_batch", side_effect=[[_make_segment_row()], []]),
            patch.object(svc, "_scan_batch", return_value=(mentions, 0, [], 0, 0)),
        ):
            await svc.scan(dry_run=False)

        svc._mention_repo.update_entity_counters.assert_called_once()
        passed_entity_ids = svc._mention_repo.update_entity_counters.call_args[0][1]

        # Both entities (including the ASR-only one) must be passed to the
        # repository so the repository can apply its own ASR filtering.
        assert entity_id_a in passed_entity_ids, (
            "entity_id_a (visible name) must be in the update_entity_counters call"
        )
        assert entity_id_b in passed_entity_ids, (
            "entity_id_b (ASR-alias-only) must also be passed to update_entity_counters "
            "so the repository can zero it out if it has no visible-name mentions"
        )

    async def test_update_entity_counters_not_called_when_zero_inserts(
        self,
    ) -> None:
        """When bulk_create_with_conflict_skip returns 0, counters are not updated.

        If no new mention rows were actually inserted (all were conflicts),
        the scan service must not call update_entity_counters, because the
        matched_entity_ids set will be empty (no new matches contributed).

        This preserves existing behaviour for the no-new-matches path.
        """
        from chronovista.services.entity_mention_scan_service import _EntityPattern

        entity_id = _make_uuid()
        fake_pattern = _EntityPattern(
            entity_id=entity_id,
            canonical_name="NoNewMatch",
            entity_type="person",
            pg_pattern=re.escape("NoNewMatch"),
            alias_names=["NoNewMatch"],
        )

        session = AsyncMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()

        factory = _make_session_factory(session)
        svc = _build_service(factory)

        svc._mention_repo.bulk_create_with_conflict_skip = AsyncMock(return_value=0)
        svc._mention_repo.update_entity_counters = AsyncMock()
        svc._mention_repo.update_alias_counters = AsyncMock()
        with (
            patch.object(svc, "_load_entity_patterns", return_value=[fake_pattern]),
            patch.object(svc, "_fetch_segment_batch", side_effect=[[_make_segment_row()], []]),
            # _scan_batch returns empty list → matched_entity_ids stays empty
            patch.object(svc, "_scan_batch", return_value=([], 0, [], 0, 0)),
        ):
            await svc.scan(dry_run=False)

        svc._mention_repo.update_entity_counters.assert_not_called()
        svc._mention_repo.update_alias_counters.assert_not_called()


# ---------------------------------------------------------------------------
# TestDryRunMode
# ---------------------------------------------------------------------------


class TestDryRunMode:
    """Verify that dry-run mode does not write to the database."""

    async def test_dry_run_no_bulk_insert(self) -> None:
        """In dry-run mode, bulk_create_with_conflict_skip must NOT be called."""
        from chronovista.models.entity_mention import EntityMentionCreate
        from chronovista.models.enums import DetectionMethod
        from chronovista.services.entity_mention_scan_service import _EntityPattern

        entity_id = _make_uuid()
        fake_pattern = _EntityPattern(
            entity_id=entity_id,
            canonical_name="Anthropic",
            entity_type="organization",
            pg_pattern=re.escape("Anthropic"),
            alias_names=["Anthropic"],
        )

        session = AsyncMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()

        factory = _make_session_factory(session)
        svc = _build_service(factory)

        mention = EntityMentionCreate(
            entity_id=entity_id,
            segment_id=1,
            video_id="dQw4w9WgXcQ",
            language_code="en",
            mention_text="Anthropic",
            detection_method=DetectionMethod.RULE_MATCH,
            confidence=1.0,
        )
        svc._mention_repo.bulk_create_with_conflict_skip = AsyncMock(return_value=0)
        svc._mention_repo.update_entity_counters = AsyncMock()
        svc._mention_repo.update_alias_counters = AsyncMock()
        with (
            patch.object(svc, "_load_entity_patterns", return_value=[fake_pattern]),
            patch.object(svc, "_fetch_segment_batch", side_effect=[[_make_segment_row()], []]),
            patch.object(svc, "_scan_batch", return_value=([mention], 0, [], 0, 0)),
        ):
            result = await svc.scan(dry_run=True)
        svc._mention_repo.bulk_create_with_conflict_skip.assert_not_called()
        assert result.dry_run is True
        assert result.dry_run_matches is not None

    async def test_dry_run_result_flag_set_when_no_entities(self) -> None:
        """dry_run=True must be reflected in result even when no entities match.

        When patterns is empty, scan returns early. dry_run is True but
        dry_run_matches is None (the early-return path skips initialization).
        """
        session = AsyncMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()

        entity_result = _scalars_execute([])
        session.execute = AsyncMock(return_value=entity_result)

        factory = _make_session_factory(session)
        svc = _build_service(factory)

        result = await svc.scan(dry_run=True)

        assert result.dry_run is True
        # Early-return path: dry_run_matches is None (not initialized)
        assert result.dry_run_matches is None

    async def test_live_mode_dry_run_matches_is_none(self) -> None:
        """In live mode, dry_run_matches must be None."""
        session = AsyncMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()

        entity_result = _scalars_execute([])
        session.execute = AsyncMock(return_value=entity_result)

        factory = _make_session_factory(session)
        svc = _build_service(factory)

        result = await svc.scan(dry_run=False)

        assert result.dry_run is False
        assert result.dry_run_matches is None

    async def test_dry_run_populates_preview_data(self) -> None:
        """dry_run_matches must contain preview dicts when matches exist."""
        from chronovista.models.entity_mention import EntityMentionCreate
        from chronovista.models.enums import DetectionMethod
        from chronovista.services.entity_mention_scan_service import _EntityPattern

        entity_id = _make_uuid()
        fake_pattern = _EntityPattern(
            entity_id=entity_id,
            canonical_name="Palantir",
            entity_type="organization",
            pg_pattern=re.escape("Palantir"),
            alias_names=["Palantir"],
        )

        session = AsyncMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()

        factory = _make_session_factory(session)
        svc = _build_service(factory)

        mention = EntityMentionCreate(
            entity_id=entity_id,
            segment_id=1,
            video_id="dQw4w9WgXcQ",
            language_code="en",
            mention_text="Palantir",
            detection_method=DetectionMethod.RULE_MATCH,
            confidence=1.0,
        )
        preview = {"entity_name": "Palantir", "video_id": "dQw4w9WgXcQ", "context": "..."}

        svc._mention_repo.update_entity_counters = AsyncMock()
        svc._mention_repo.update_alias_counters = AsyncMock()
        with (
            patch.object(svc, "_load_entity_patterns", return_value=[fake_pattern]),
            patch.object(svc, "_fetch_segment_batch", side_effect=[[_make_segment_row()], []]),
            patch.object(svc, "_scan_batch", return_value=([mention], 0, [preview], 0, 0)),
        ):
            result = await svc.scan(dry_run=True)

        assert result.dry_run_matches is not None
        assert len(result.dry_run_matches) == 1
        assert result.dry_run_matches[0]["entity_name"] == "Palantir"


# ---------------------------------------------------------------------------
# TestFullRescan
# ---------------------------------------------------------------------------


class TestFullRescan:
    """Verify that delete_by_scope is called before scanning when full_rescan=True."""

    async def test_delete_by_scope_called_when_full_rescan_true(self) -> None:
        """Full rescan must call delete_by_scope before processing segments."""
        from chronovista.services.entity_mention_scan_service import _EntityPattern

        entity_id = _make_uuid()
        fake_pattern = _EntityPattern(
            entity_id=entity_id,
            canonical_name="SpaceX",
            entity_type="organization",
            pg_pattern=re.escape("SpaceX"),
            alias_names=["SpaceX"],
        )

        session = AsyncMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()

        factory = _make_session_factory(session)
        svc = _build_service(factory)
        svc._mention_repo.delete_by_scope = AsyncMock(return_value=5)
        svc._mention_repo.bulk_create_with_conflict_skip = AsyncMock(return_value=0)
        svc._mention_repo.update_entity_counters = AsyncMock()
        svc._mention_repo.update_alias_counters = AsyncMock()
        with (
            patch.object(svc, "_load_entity_patterns", return_value=[fake_pattern]),
            patch.object(svc, "_fetch_segment_batch", return_value=[]),
        ):
            await svc.scan(full_rescan=True, dry_run=False)
        svc._mention_repo.delete_by_scope.assert_called_once()
        call_kwargs = svc._mention_repo.delete_by_scope.call_args        # entity_ids should contain our entity_id
        passed_entity_ids = call_kwargs.kwargs.get("entity_ids") or call_kwargs[1].get("entity_ids")
        assert entity_id in passed_entity_ids

    async def test_delete_by_scope_not_called_without_full_rescan(self) -> None:
        """Without full_rescan=True, delete_by_scope must NOT be called."""
        from chronovista.services.entity_mention_scan_service import _EntityPattern

        entity_id = _make_uuid()
        fake_pattern = _EntityPattern(
            entity_id=entity_id,
            canonical_name="Meta",
            entity_type="organization",
            pg_pattern=re.escape("Meta"),
            alias_names=["Meta"],
        )

        session = AsyncMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()

        factory = _make_session_factory(session)
        svc = _build_service(factory)
        svc._mention_repo.delete_by_scope = AsyncMock(return_value=0)
        svc._mention_repo.bulk_create_with_conflict_skip = AsyncMock(return_value=0)
        svc._mention_repo.update_entity_counters = AsyncMock()
        svc._mention_repo.update_alias_counters = AsyncMock()
        with (
            patch.object(svc, "_load_entity_patterns", return_value=[fake_pattern]),
            patch.object(svc, "_fetch_segment_batch", return_value=[]),
        ):
            await svc.scan(full_rescan=False)
        svc._mention_repo.delete_by_scope.assert_not_called()
    async def test_delete_by_scope_not_called_in_dry_run_full(self) -> None:
        """Full rescan in dry-run mode must NOT call delete_by_scope."""
        from chronovista.services.entity_mention_scan_service import _EntityPattern

        entity_id = _make_uuid()
        fake_pattern = _EntityPattern(
            entity_id=entity_id,
            canonical_name="Nvidia",
            entity_type="organization",
            pg_pattern=re.escape("Nvidia"),
            alias_names=["Nvidia"],
        )

        session = AsyncMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()

        factory = _make_session_factory(session)
        svc = _build_service(factory)
        svc._mention_repo.delete_by_scope = AsyncMock(return_value=0)
        svc._mention_repo.update_entity_counters = AsyncMock()
        svc._mention_repo.update_alias_counters = AsyncMock()
        with (
            patch.object(svc, "_load_entity_patterns", return_value=[fake_pattern]),
            patch.object(svc, "_fetch_segment_batch", return_value=[]),
        ):
            await svc.scan(full_rescan=True, dry_run=True)
        svc._mention_repo.delete_by_scope.assert_not_called()

# ---------------------------------------------------------------------------
# TestNewEntitiesOnly
# ---------------------------------------------------------------------------


class TestNewEntitiesOnly:
    """Verify that new_entities_only restricts scanning to zero-mention entities."""

    async def test_get_entities_with_zero_mentions_called(self) -> None:
        """With new_entities_only=True, get_entities_with_zero_mentions must be called."""
        session = AsyncMock()

        svc = _build_service(MagicMock())
        svc._mention_repo.get_entities_with_zero_mentions = AsyncMock(return_value=[])
        result = await svc._load_entity_patterns(
            session, entity_type=None, new_entities_only=True
        )
        svc._mention_repo.get_entities_with_zero_mentions.assert_called_once_with(            session, entity_type=None
        )
        assert result == []

    async def test_no_zero_mention_entities_returns_empty(self) -> None:
        """When get_entities_with_zero_mentions returns [], result is empty list."""
        session = AsyncMock()

        svc = _build_service(MagicMock())
        svc._mention_repo.get_entities_with_zero_mentions = AsyncMock(return_value=[])
        result = await svc._load_entity_patterns(
            session, entity_type=None, new_entities_only=True
        )

        assert result == []

    async def test_entity_type_forwarded_to_zero_mention_query(self) -> None:
        """entity_type must be forwarded to get_entities_with_zero_mentions."""
        session = AsyncMock()

        svc = _build_service(MagicMock())
        svc._mention_repo.get_entities_with_zero_mentions = AsyncMock(return_value=[])
        await svc._load_entity_patterns(
            session, entity_type="person", new_entities_only=True
        )
        svc._mention_repo.get_entities_with_zero_mentions.assert_called_once_with(            session, entity_type="person"
        )


# ---------------------------------------------------------------------------
# TestScanResult
# ---------------------------------------------------------------------------


class TestScanResult:
    """Verify ScanResult field population."""

    def test_scan_result_defaults(self) -> None:
        """ScanResult must have zero-value defaults for all numeric fields."""
        from chronovista.services.entity_mention_scan_service import ScanResult

        result = ScanResult()
        assert result.segments_scanned == 0
        assert result.mentions_found == 0
        assert result.mentions_skipped == 0
        assert result.unique_entities == 0
        assert result.unique_videos == 0
        assert result.duration_seconds == 0.0
        assert result.dry_run is False
        assert result.failed_batches == 0
        assert result.dry_run_matches is None

    async def test_scan_result_unique_fields_populated(self) -> None:
        """unique_entities and unique_videos must reflect distinct IDs matched."""
        from chronovista.models.entity_mention import EntityMentionCreate
        from chronovista.models.enums import DetectionMethod
        from chronovista.services.entity_mention_scan_service import _EntityPattern

        entity_id_1 = _make_uuid()
        entity_id_2 = _make_uuid()

        fake_patterns = [
            _EntityPattern(
                entity_id=entity_id_1,
                canonical_name="Entity1",
                entity_type="person",
                pg_pattern=re.escape("Entity1"),
                alias_names=["Entity1"],
            ),
            _EntityPattern(
                entity_id=entity_id_2,
                canonical_name="Entity2",
                entity_type="person",
                pg_pattern=re.escape("Entity2"),
                alias_names=["Entity2"],
            ),
        ]

        session = AsyncMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()

        factory = _make_session_factory(session)
        svc = _build_service(factory)

        mentions = [
            EntityMentionCreate(
                entity_id=entity_id_1,
                segment_id=1,
                video_id="dQw4w9WgXcQ",
                language_code="en",
                mention_text="Entity1",
                detection_method=DetectionMethod.RULE_MATCH,
                confidence=1.0,
            ),
            EntityMentionCreate(
                entity_id=entity_id_2,
                segment_id=2,
                video_id="9bZkp7q19f0",
                language_code="en",
                mention_text="Entity2",
                detection_method=DetectionMethod.RULE_MATCH,
                confidence=1.0,
            ),
        ]

        svc._mention_repo.bulk_create_with_conflict_skip = AsyncMock(return_value=2)
        svc._mention_repo.update_entity_counters = AsyncMock()
        svc._mention_repo.update_alias_counters = AsyncMock()
        with (
            patch.object(svc, "_load_entity_patterns", return_value=fake_patterns),
            patch.object(svc, "_fetch_segment_batch", side_effect=[[_make_segment_row()], []]),
            patch.object(svc, "_scan_batch", return_value=(mentions, 0, [], 0, 0)),
        ):
            result = await svc.scan()

        assert result.unique_entities == 2
        assert result.unique_videos == 2

    async def test_scan_result_duration_non_negative(self) -> None:
        """duration_seconds must be >= 0.0 after any scan."""
        session = AsyncMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()

        entity_result = _scalars_execute([])
        session.execute = AsyncMock(return_value=entity_result)

        factory = _make_session_factory(session)
        svc = _build_service(factory)

        result = await svc.scan()

        assert result.duration_seconds >= 0.0

    async def test_scan_result_failed_batches_starts_at_zero(self) -> None:
        """ScanResult.failed_batches must start at zero with no errors."""
        session = AsyncMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()

        entity_result = _scalars_execute([])
        session.execute = AsyncMock(return_value=entity_result)

        factory = _make_session_factory(session)
        svc = _build_service(factory)

        result = await svc.scan()

        assert result.failed_batches == 0


# ---------------------------------------------------------------------------
# TestFailedBatchHandling
# ---------------------------------------------------------------------------


class TestFailedBatchHandling:
    """Verify that batch failures are caught, counted, and the scan continues."""

    async def test_failed_fetch_increments_failed_batches(self) -> None:
        """A fetch exception must increment failed_batches and not abort scan."""
        from chronovista.services.entity_mention_scan_service import _EntityPattern

        entity_id = _make_uuid()
        fake_pattern = _EntityPattern(
            entity_id=entity_id,
            canonical_name="Waymo",
            entity_type="organization",
            pg_pattern=re.escape("Waymo"),
            alias_names=["Waymo"],
        )

        session = AsyncMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()

        factory = _make_session_factory(session)
        svc = _build_service(factory)

        fetch_calls = 0

        async def failing_then_empty(
            _session: Any,
            video_ids: Any,
            language_code: Any,
            batch_size: int,
            offset: int,
        ) -> list[Any]:
            nonlocal fetch_calls
            fetch_calls += 1
            if fetch_calls == 1:
                raise RuntimeError("DB connection timeout")
            return []  # Second call ends the loop

        svc._mention_repo.update_entity_counters = AsyncMock()
        svc._mention_repo.update_alias_counters = AsyncMock()
        with (
            patch.object(svc, "_load_entity_patterns", return_value=[fake_pattern]),
            patch.object(svc, "_fetch_segment_batch", side_effect=failing_then_empty),
        ):
            result = await svc.scan()

        assert result.failed_batches == 1

    async def test_failed_scan_batch_increments_failed_batches(self) -> None:
        """A _scan_batch exception must increment failed_batches and continue."""
        from chronovista.services.entity_mention_scan_service import _EntityPattern

        entity_id = _make_uuid()
        fake_pattern = _EntityPattern(
            entity_id=entity_id,
            canonical_name="Rivian",
            entity_type="organization",
            pg_pattern=re.escape("Rivian"),
            alias_names=["Rivian"],
        )

        session = AsyncMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()

        factory = _make_session_factory(session)
        svc = _build_service(factory)
        svc._mention_repo.update_entity_counters = AsyncMock()
        svc._mention_repo.update_alias_counters = AsyncMock()
        scan_calls = 0

        async def first_scan_fails(*args: Any, **kwargs: Any) -> Any:
            nonlocal scan_calls
            scan_calls += 1
            if scan_calls == 1:
                raise ValueError("Regex compilation error")
            return [], 0, []

        with (
            patch.object(svc, "_load_entity_patterns", return_value=[fake_pattern]),
            patch.object(svc, "_fetch_segment_batch", side_effect=[[_make_segment_row()], []]),
            patch.object(svc, "_scan_batch", side_effect=first_scan_fails),
        ):
            result = await svc.scan()

        assert result.failed_batches == 1

    async def test_scan_continues_to_next_batch_after_failure(self) -> None:
        """Scan must process subsequent batches after a batch scan failure."""
        from chronovista.services.entity_mention_scan_service import _EntityPattern

        entity_id = _make_uuid()
        fake_pattern = _EntityPattern(
            entity_id=entity_id,
            canonical_name="Lucid",
            entity_type="organization",
            pg_pattern=re.escape("Lucid"),
            alias_names=["Lucid"],
        )

        session = AsyncMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()

        factory = _make_session_factory(session)
        svc = _build_service(factory)
        svc._mention_repo.bulk_create_with_conflict_skip = AsyncMock(return_value=0)
        svc._mention_repo.update_entity_counters = AsyncMock()
        svc._mention_repo.update_alias_counters = AsyncMock()
        fetch_call = 0

        async def two_batches_then_empty(*args: Any, **kwargs: Any) -> list[Any]:
            nonlocal fetch_call
            fetch_call += 1
            if fetch_call == 1:
                return [_make_segment_row(seg_id=1)]
            if fetch_call == 2:
                return [_make_segment_row(seg_id=2)]
            return []

        scan_call = 0

        async def first_fails(*args: Any, **kwargs: Any) -> Any:
            nonlocal scan_call
            scan_call += 1
            if scan_call == 1:
                raise RuntimeError("first batch error")
            return [], 0, [], 0, 0

        with (
            patch.object(svc, "_load_entity_patterns", return_value=[fake_pattern]),
            patch.object(svc, "_fetch_segment_batch", side_effect=two_batches_then_empty),
            patch.object(svc, "_scan_batch", side_effect=first_fails),
        ):
            result = await svc.scan()

        assert result.failed_batches == 1
        # Second batch is scanned successfully (segments_scanned counts only successfully fetched)
        assert result.segments_scanned >= 1


# ---------------------------------------------------------------------------
# TestProgressCallback
# ---------------------------------------------------------------------------


class TestProgressCallback:
    """Verify progress_callback is invoked after each batch."""

    async def test_progress_callback_called_per_batch(self) -> None:
        """progress_callback must be called with (segments_scanned, mentions_found)."""
        from chronovista.services.entity_mention_scan_service import _EntityPattern

        entity_id = _make_uuid()
        fake_pattern = _EntityPattern(
            entity_id=entity_id,
            canonical_name="Zoom",
            entity_type="organization",
            pg_pattern=re.escape("Zoom"),
            alias_names=["Zoom"],
        )

        session = AsyncMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()

        factory = _make_session_factory(session)
        svc = _build_service(factory)
        svc._mention_repo.update_entity_counters = AsyncMock()
        svc._mention_repo.update_alias_counters = AsyncMock()
        callback_calls: list[tuple[int, int]] = []

        def callback(scanned: int, found: int) -> None:
            callback_calls.append((scanned, found))

        with (
            patch.object(svc, "_load_entity_patterns", return_value=[fake_pattern]),
            patch.object(
                svc, "_fetch_segment_batch", side_effect=[[_make_segment_row()], []]
            ),
            patch.object(svc, "_scan_batch", return_value=([], 0, [], 0, 0)),
        ):
            await svc.scan(progress_callback=callback)

        assert len(callback_calls) >= 1
        scanned, found = callback_calls[0]
        assert scanned > 0

    async def test_progress_callback_not_called_when_no_segments(self) -> None:
        """If no segments are fetched, progress_callback must not be called."""
        from chronovista.services.entity_mention_scan_service import _EntityPattern

        entity_id = _make_uuid()
        fake_pattern = _EntityPattern(
            entity_id=entity_id,
            canonical_name="Nobody",
            entity_type="person",
            pg_pattern=re.escape("Nobody"),
            alias_names=["Nobody"],
        )

        session = AsyncMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()

        factory = _make_session_factory(session)
        svc = _build_service(factory)
        svc._mention_repo.update_entity_counters = AsyncMock()
        svc._mention_repo.update_alias_counters = AsyncMock()
        callback_calls: list[tuple[int, int]] = []

        def callback(scanned: int, found: int) -> None:
            callback_calls.append((scanned, found))

        with (
            patch.object(svc, "_load_entity_patterns", return_value=[fake_pattern]),
            patch.object(svc, "_fetch_segment_batch", return_value=[]),
        ):
            await svc.scan(progress_callback=callback)

        assert len(callback_calls) == 0


# ---------------------------------------------------------------------------
# TestAuditUnregisteredMentions  (T014 — Feature 044, US3)
# ---------------------------------------------------------------------------


def _make_audit_row(
    canonical_name: str,
    entity_id: uuid.UUID,
    mention_text: str,
    segment_count: int,
) -> MagicMock:
    """Create a mock SQLAlchemy Row for audit_unregistered_mentions results.

    The service accesses attributes by name (``row.canonical_name``, etc.),
    so a MagicMock with those attributes set directly is sufficient.
    """
    row = MagicMock()
    row.canonical_name = canonical_name
    row.entity_id = entity_id
    row.mention_text = mention_text
    row.segment_count = segment_count
    return row


class TestAuditUnregisteredMentions:
    """Unit tests for EntityMentionScanService.audit_unregistered_mentions().

    The method opens its own session via ``_session_factory``, executes a
    single compound SELECT, and returns a list of 4-tuples.  These tests mock
    the session and ``session.execute`` to inject canned query results without
    touching the database.

    Covered scenarios
    -----------------
    (a) Returns unmatched mention texts.
    (b) Excludes matches against canonical name (case-insensitive) — the
        query WHERE clause filters them out; simulated by returning no rows
        for those cases.
    (c) Excludes matches against registered aliases (case-insensitive) —
        same mechanism as (b).
    (d) Skips non-active entities — the WHERE clause filters ``status !=
        'active'``; simulated by the query returning nothing for those rows.
    (e) Returns empty list when all mentions match an alias or canonical name.
    (f) Groups by entity and mention_text with correct segment counts.
    """

    # ------------------------------------------------------------------
    # (a) Returns unmatched mention texts
    # ------------------------------------------------------------------

    async def test_returns_unmatched_mention_texts(self) -> None:
        """audit_unregistered_mentions returns rows that have no alias match.

        When the query finds a mention whose text does not match any alias
        or canonical name, the tuple ``(canonical_name, entity_id,
        mention_text, segment_count)`` must appear in the result.
        """
        entity_id = _make_uuid()
        raw_row = _make_audit_row(
            canonical_name="Noam Chomsky",
            entity_id=entity_id,
            mention_text="chomsky",
            segment_count=3,
        )

        session = AsyncMock()
        query_result = MagicMock()
        query_result.all.return_value = [raw_row]
        session.execute = AsyncMock(return_value=query_result)

        factory = _make_session_factory(session)
        svc = _build_service(factory)

        results = await svc.audit_unregistered_mentions()

        assert len(results) == 1
        canonical, eid, text, count = results[0]
        assert canonical == "Noam Chomsky"
        assert eid == entity_id
        assert text == "chomsky"
        assert count == 3

    # ------------------------------------------------------------------
    # (b) Excludes matches against canonical name (case-insensitive)
    # ------------------------------------------------------------------

    async def test_excludes_canonical_name_matches(self) -> None:
        """When mention_text equals canonical_name (any case), no row is returned.

        The SQL WHERE clause ``func.lower(mention_text) !=
        func.lower(canonical_name)`` filters these out before rows reach
        Python.  We simulate this by the mock returning an empty result set,
        matching the real database behavior.
        """
        session = AsyncMock()
        query_result = MagicMock()
        # The query itself excludes canonical-name matches — simulate empty result
        query_result.all.return_value = []
        session.execute = AsyncMock(return_value=query_result)

        factory = _make_session_factory(session)
        svc = _build_service(factory)

        results = await svc.audit_unregistered_mentions()

        assert results == []

    # ------------------------------------------------------------------
    # (c) Excludes matches against registered aliases (case-insensitive)
    # ------------------------------------------------------------------

    async def test_excludes_registered_alias_matches(self) -> None:
        """When mention_text matches an alias (any case), no row is returned.

        The SQL LEFT JOIN on ``EntityAliasDB`` and WHERE
        ``EntityAliasDB.id.is_(None)`` ensures rows with a matching alias
        are filtered out.  Simulated by returning an empty result.
        """
        session = AsyncMock()
        query_result = MagicMock()
        query_result.all.return_value = []
        session.execute = AsyncMock(return_value=query_result)

        factory = _make_session_factory(session)
        svc = _build_service(factory)

        results = await svc.audit_unregistered_mentions()

        assert results == []

    # ------------------------------------------------------------------
    # (d) Skips non-active entities
    # ------------------------------------------------------------------

    async def test_skips_non_active_entities(self) -> None:
        """Mentions for inactive entities must not appear in audit results.

        The SQL WHERE clause ``NamedEntityDB.status == 'active'`` removes
        inactive entities before grouping.  Simulated by the mock returning
        an empty result when only inactive entity rows exist.
        """
        session = AsyncMock()
        query_result = MagicMock()
        # Non-active entity's row is filtered by the WHERE clause → empty
        query_result.all.return_value = []
        session.execute = AsyncMock(return_value=query_result)

        factory = _make_session_factory(session)
        svc = _build_service(factory)

        results = await svc.audit_unregistered_mentions()

        assert results == []

    # ------------------------------------------------------------------
    # (e) Returns empty list when all mentions match
    # ------------------------------------------------------------------

    async def test_returns_empty_when_all_mentions_match(self) -> None:
        """When every user-correction mention matches an alias or canonical name,
        the result list must be empty.
        """
        session = AsyncMock()
        query_result = MagicMock()
        query_result.all.return_value = []
        session.execute = AsyncMock(return_value=query_result)

        factory = _make_session_factory(session)
        svc = _build_service(factory)

        results = await svc.audit_unregistered_mentions()

        assert results == []
        assert isinstance(results, list)

    # ------------------------------------------------------------------
    # (f) Groups by entity and mention_text with correct segment counts
    # ------------------------------------------------------------------

    async def test_groups_by_entity_and_mention_text_with_segment_count(self) -> None:
        """Multiple unregistered texts for the same entity each appear as
        separate tuples with their own segment_count.
        """
        entity_id_a = _make_uuid()
        entity_id_b = _make_uuid()

        row1 = _make_audit_row("Ada Lovelace", entity_id_a, "lovelace", 5)
        row2 = _make_audit_row("Ada Lovelace", entity_id_a, "ada", 2)
        row3 = _make_audit_row("Alan Turing", entity_id_b, "turing", 8)

        session = AsyncMock()
        query_result = MagicMock()
        query_result.all.return_value = [row1, row2, row3]
        session.execute = AsyncMock(return_value=query_result)

        factory = _make_session_factory(session)
        svc = _build_service(factory)

        results = await svc.audit_unregistered_mentions()

        assert len(results) == 3

        # Verify tuples for Ada Lovelace rows
        ada_rows = [r for r in results if r[0] == "Ada Lovelace"]
        assert len(ada_rows) == 2
        ada_texts = {r[2] for r in ada_rows}
        assert "lovelace" in ada_texts
        assert "ada" in ada_texts

        # Verify segment counts are preserved as returned by the query
        lovelace_row = next(r for r in ada_rows if r[2] == "lovelace")
        assert lovelace_row[3] == 5

        # Verify Alan Turing row
        turing_rows = [r for r in results if r[0] == "Alan Turing"]
        assert len(turing_rows) == 1
        assert turing_rows[0][1] == entity_id_b
        assert turing_rows[0][3] == 8

    async def test_result_tuple_fields_in_correct_order(self) -> None:
        """Each result tuple must be (canonical_name, entity_id, mention_text,
        segment_count) in that field order.
        """
        entity_id = _make_uuid()
        raw_row = _make_audit_row(
            canonical_name="Marie Curie",
            entity_id=entity_id,
            mention_text="curie",
            segment_count=11,
        )

        session = AsyncMock()
        query_result = MagicMock()
        query_result.all.return_value = [raw_row]
        session.execute = AsyncMock(return_value=query_result)

        factory = _make_session_factory(session)
        svc = _build_service(factory)

        results = await svc.audit_unregistered_mentions()

        assert len(results) == 1
        # Positional field verification
        assert results[0][0] == "Marie Curie"     # canonical_name
        assert results[0][1] == entity_id          # entity_id
        assert results[0][2] == "curie"            # mention_text
        assert results[0][3] == 11                 # segment_count

    async def test_execute_called_exactly_once(self) -> None:
        """The method must issue exactly one database query per invocation."""
        session = AsyncMock()
        query_result = MagicMock()
        query_result.all.return_value = []
        session.execute = AsyncMock(return_value=query_result)

        factory = _make_session_factory(session)
        svc = _build_service(factory)

        await svc.audit_unregistered_mentions()

        session.execute.assert_called_once()

    async def test_returns_multiple_entities_in_any_order(self) -> None:
        """Multiple distinct entities each appear with their mention text and
        segment_count; ordering is determined by SQL ORDER BY.
        """
        eid1 = _make_uuid()
        eid2 = _make_uuid()

        row1 = _make_audit_row("Bertrand Russell", eid1, "russell", 4)
        row2 = _make_audit_row("Bertrand Russell", eid1, "b. russell", 1)
        row3 = _make_audit_row("Ludwig Wittgenstein", eid2, "wittgenstein", 7)

        session = AsyncMock()
        query_result = MagicMock()
        query_result.all.return_value = [row1, row2, row3]
        session.execute = AsyncMock(return_value=query_result)

        factory = _make_session_factory(session)
        svc = _build_service(factory)

        results = await svc.audit_unregistered_mentions()

        assert len(results) == 3
        entity_names = {r[0] for r in results}
        assert "Bertrand Russell" in entity_names
        assert "Ludwig Wittgenstein" in entity_names

    async def test_session_context_manager_entered_and_exited(self) -> None:
        """The method must open and close the session via __aenter__/__aexit__."""
        session = AsyncMock()
        query_result = MagicMock()
        query_result.all.return_value = []
        session.execute = AsyncMock(return_value=query_result)

        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=session)
        cm.__aexit__ = AsyncMock(return_value=False)

        factory = MagicMock(return_value=cm)
        svc = _build_service(factory)

        await svc.audit_unregistered_mentions()

        cm.__aenter__.assert_called_once()
        cm.__aexit__.assert_called_once()


# ---------------------------------------------------------------------------
# TestEntityIdsFilter — Feature 052
# ---------------------------------------------------------------------------


class TestEntityIdsFilter:
    """Verify entity_ids parameter filters entities in _load_entity_patterns()
    and interacts correctly with entity_type (AND semantics).

    Feature 052 — Targeted Entity & Video-Level Mention Scanning.
    """

    # ------------------------------------------------------------------
    # _load_entity_patterns with entity_ids
    # ------------------------------------------------------------------

    async def test_entity_ids_passed_to_load_entity_patterns(self) -> None:
        """scan(entity_ids=[...]) must forward entity_ids to _load_entity_patterns."""
        session = AsyncMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()

        entity_result = _scalars_execute([])
        session.execute = AsyncMock(return_value=entity_result)

        factory = _make_session_factory(session)
        svc = _build_service(factory)

        target_id = _make_uuid()
        captured_args: list[dict[str, Any]] = []

        original_load = svc._load_entity_patterns

        async def spy_load(
            s: Any,
            entity_type: Any,
            new_entities_only: Any,
            entity_ids: Any = None,
        ) -> Any:
            captured_args.append(
                {
                    "entity_type": entity_type,
                    "new_entities_only": new_entities_only,
                    "entity_ids": entity_ids,
                }
            )
            return await original_load(
                s,
                entity_type=entity_type,
                new_entities_only=new_entities_only,
                entity_ids=entity_ids,
            )

        with patch.object(svc, "_load_entity_patterns", side_effect=spy_load):
            await svc.scan(entity_ids=[target_id])

        assert len(captured_args) == 1
        assert captured_args[0]["entity_ids"] == [target_id]

    async def test_entity_ids_none_loads_all_entities(self) -> None:
        """scan() without entity_ids must pass entity_ids=None to the loader."""
        session = AsyncMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()

        entity_result = _scalars_execute([])
        session.execute = AsyncMock(return_value=entity_result)

        factory = _make_session_factory(session)
        svc = _build_service(factory)

        captured_args: list[dict[str, Any]] = []

        original_load = svc._load_entity_patterns

        async def spy_load(
            s: Any,
            entity_type: Any,
            new_entities_only: Any,
            entity_ids: Any = None,
        ) -> Any:
            captured_args.append({"entity_ids": entity_ids})
            return await original_load(
                s,
                entity_type=entity_type,
                new_entities_only=new_entities_only,
                entity_ids=entity_ids,
            )

        with patch.object(svc, "_load_entity_patterns", side_effect=spy_load):
            await svc.scan()

        assert captured_args[0]["entity_ids"] is None

    async def test_entity_ids_combined_with_entity_type_passed_together(self) -> None:
        """When both entity_ids and entity_type are given, both are forwarded."""
        session = AsyncMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()

        entity_result = _scalars_execute([])
        session.execute = AsyncMock(return_value=entity_result)

        factory = _make_session_factory(session)
        svc = _build_service(factory)

        target_id = _make_uuid()
        captured_args: list[dict[str, Any]] = []

        original_load = svc._load_entity_patterns

        async def spy_load(
            s: Any,
            entity_type: Any,
            new_entities_only: Any,
            entity_ids: Any = None,
        ) -> Any:
            captured_args.append(
                {"entity_type": entity_type, "entity_ids": entity_ids}
            )
            return await original_load(
                s,
                entity_type=entity_type,
                new_entities_only=new_entities_only,
                entity_ids=entity_ids,
            )

        with patch.object(svc, "_load_entity_patterns", side_effect=spy_load):
            await svc.scan(entity_type="person", entity_ids=[target_id])

        assert captured_args[0]["entity_type"] == "person"
        assert captured_args[0]["entity_ids"] == [target_id]

    # ------------------------------------------------------------------
    # _load_entity_patterns SQL filtering with entity_ids
    # ------------------------------------------------------------------

    async def test_load_patterns_with_entity_ids_filters_by_id(self) -> None:
        """When entity_ids is provided, only entities with matching IDs are returned.

        The method should add an ``id IN (...)`` WHERE clause so that only the
        requested entities appear in the pattern list.
        """
        from sqlalchemy.dialects import postgresql as pg_dialect

        entity_id = _make_uuid()
        entity_row = _make_entity_row(entity_id=entity_id, canonical_name="Alice")

        session = AsyncMock()
        entity_result = _scalars_execute([entity_row])
        alias_result = _scalars_execute([])
        session.execute = AsyncMock(side_effect=[entity_result, alias_result])

        svc = _build_service(MagicMock())
        await svc._load_entity_patterns(
            session,
            entity_type=None,
            new_entities_only=False,
            entity_ids=[entity_id],
        )

        # The SQL emitted for the entity query must contain the ID filter
        entity_stmt = session.execute.call_args_list[0].args[0]
        sql_str = str(
            entity_stmt.compile(
                dialect=pg_dialect.dialect(),  # type: ignore[no-untyped-call]
                compile_kwargs={"literal_binds": True},
            )
        )
        # The UUID should appear in the IN clause
        assert str(entity_id) in sql_str, (
            f"Expected entity_id {entity_id} in SQL; got: {sql_str[:600]}"
        )

    async def test_load_patterns_with_entity_ids_and_entity_type_filters_both(
        self,
    ) -> None:
        """With both entity_ids and entity_type, both filters appear in SQL.

        The WHERE clause must contain both the entity_type equality check and
        an id IN (...) filter.
        """
        from sqlalchemy.dialects import postgresql as pg_dialect

        entity_id = _make_uuid()
        entity_row = _make_entity_row(
            entity_id=entity_id,
            canonical_name="Bob",
            entity_type="organization",
        )

        session = AsyncMock()
        entity_result = _scalars_execute([entity_row])
        alias_result = _scalars_execute([])
        session.execute = AsyncMock(side_effect=[entity_result, alias_result])

        svc = _build_service(MagicMock())
        await svc._load_entity_patterns(
            session,
            entity_type="organization",
            new_entities_only=False,
            entity_ids=[entity_id],
        )

        entity_stmt = session.execute.call_args_list[0].args[0]
        sql_str = str(
            entity_stmt.compile(
                dialect=pg_dialect.dialect(),  # type: ignore[no-untyped-call]
                compile_kwargs={"literal_binds": True},
            )
        )
        assert "organization" in sql_str, (
            f"Expected 'organization' in SQL; got: {sql_str[:600]}"
        )
        assert str(entity_id) in sql_str, (
            f"Expected entity_id {entity_id} in SQL; got: {sql_str[:600]}"
        )

    async def test_entity_ids_empty_list_returns_no_patterns(self) -> None:
        """An empty entity_ids list must result in no patterns (no matching entities)."""
        session = AsyncMock()
        entity_result = _scalars_execute([])
        session.execute = AsyncMock(return_value=entity_result)

        svc = _build_service(MagicMock())
        patterns = await svc._load_entity_patterns(
            session,
            entity_type=None,
            new_entities_only=False,
            entity_ids=[],
        )

        # An empty IN clause produces zero results; the result list must be empty
        assert patterns == []

    # ------------------------------------------------------------------
    # Logging at scan start includes entity_ids scope
    # ------------------------------------------------------------------

    async def test_scan_start_log_includes_entity_ids(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The structured log emitted at scan start must record the entity_ids value."""
        import logging

        session = AsyncMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()

        entity_result = _scalars_execute([])
        session.execute = AsyncMock(return_value=entity_result)

        factory = _make_session_factory(session)
        svc = _build_service(factory)

        target_id = _make_uuid()

        with caplog.at_level(
            logging.INFO,
            logger="chronovista.services.entity_mention_scan_service",
        ):
            await svc.scan(entity_ids=[target_id])

        # The INFO log at scan start must reference entity_ids
        log_messages = " ".join(r.getMessage() for r in caplog.records)
        assert "entity_ids" in log_messages.lower(), (
            f"Expected 'entity_ids' in scan start log; log output: {log_messages[:400]}"
        )
