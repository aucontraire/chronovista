"""Unit tests for the additive cross-segment detection pass (Feature 081, T010/T011).

Exercises ``EntityMentionScanService._scan_cross_segment`` directly with mocked
transcript fetches and a captured bulk-insert. ALL names are synthetic placeholders —
no library content (Constitution VI). Full-stack behavior is covered by the integration
test; these pin the span-detection contract.
"""

from __future__ import annotations

import re
import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chronovista.models.enums import DetectionMethod
from chronovista.services.entity_mention_scan_service import (
    EntityMentionScanService,
    ScanResult,
    _EntityPattern,
)

pytestmark = pytest.mark.asyncio


def _pattern(name: str) -> _EntityPattern:
    """A minimal entity pattern matching ``name`` (folded alias alternation)."""
    return _EntityPattern(
        entity_id=uuid.uuid4(),
        canonical_name=name,
        entity_type="person",
        pg_pattern=re.escape(name),
        alias_names=[name],
    )


def _seg(seg_id: int, text: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=seg_id,
        text=text,
        corrected_text=None,
        has_correction=False,
        start_time=float(seg_id),
    )


async def _run(
    segments: list[SimpleNamespace],
    patterns: list[_EntityPattern],
    *,
    full_rescan: bool = False,
    dry_run: bool = False,
    delete_affected: list[Any] | None = None,
) -> tuple[list[Any], ScanResult, MagicMock]:
    svc = EntityMentionScanService(session_factory=MagicMock())
    repo = MagicMock()
    captured: list[Any] = []

    async def _bulk(_session: Any, mentions: list[Any]) -> int:
        captured.extend(mentions)
        return len(mentions)

    repo.bulk_create_with_conflict_skip = AsyncMock(side_effect=_bulk)
    repo.delete_spanning_mentions_by_segments = AsyncMock(return_value=0)
    repo.entities_with_transcript_mentions_in_segments = AsyncMock(
        return_value=delete_affected or []
    )
    repo.update_entity_counters = AsyncMock()
    repo.update_alias_counters = AsyncMock()
    svc._mention_repo = repo

    session = AsyncMock()
    result = ScanResult(dry_run=dry_run)
    if dry_run:
        result.dry_run_matches = []
    with (
        patch.object(
            svc,
            "_fetch_transcripts_in_scope",
            AsyncMock(return_value=[("testvideo01", "en")]),
        ),
        patch.object(
            svc, "_fetch_transcript_segments", AsyncMock(return_value=segments)
        ),
    ):
        await svc._scan_cross_segment(
            session,
            patterns,
            video_ids=None,
            language_code=None,
            scoped_entity_ids=[p.entity_id for p in patterns],
            full_rescan=full_rescan,
            dry_run=dry_run,
            limit=None,
            result=result,
        )
    return captured, result, repo


class TestCrossSegmentDetection:
    async def test_two_segment_split_is_one_span(self) -> None:
        pat = _pattern("Alfa Bravo")
        captured, _result, _repo = await _run(
            [_seg(1, "the name is Alfa"), _seg(2, "Bravo speaking")], [pat]
        )
        assert len(captured) == 1
        m = captured[0]
        assert m.segment_id == 1
        assert m.end_segment_id == 2
        assert m.mention_text == "Alfa Bravo"
        assert m.detection_method == DetectionMethod.RULE_MATCH

    async def test_three_segment_split_anchors_first_and_last(self) -> None:
        pat = _pattern("Doc Alfa Bravo")
        captured, _result, _repo = await _run(
            [_seg(1, "start Doc"), _seg(2, "Alfa"), _seg(3, "Bravo end")], [pat]
        )
        assert len(captured) == 1
        assert (captured[0].segment_id, captured[0].end_segment_id) == (1, 3)

    async def test_single_segment_match_is_not_emitted(self) -> None:
        # The whole name sits inside segment 1 -> owned by the per-segment pass,
        # the cross-segment pass must discard it.
        pat = _pattern("Alfa Bravo")
        captured, _result, _repo = await _run(
            [_seg(1, "Alfa Bravo is here"), _seg(2, "unrelated words")], [pat]
        )
        assert captured == []

    async def test_mangled_and_split_is_not_written(self) -> None:
        # Name mis-transcribed ("Alpha" not "Alfa") across the boundary: the regex
        # write-path won't match it; mangled-and-split stays in the suggestion domain.
        pat = _pattern("Alfa Bravo")
        captured, _result, _repo = await _run(
            [_seg(1, "intro Alpha"), _seg(2, "Bravo")], [pat]
        )
        assert captured == []

    async def test_dry_run_writes_nothing_but_previews(self) -> None:
        pat = _pattern("Alfa Bravo")
        captured, result, repo = await _run(
            [_seg(1, "say Alfa"), _seg(2, "Bravo now")], [pat], dry_run=True
        )
        assert captured == []
        repo.bulk_create_with_conflict_skip.assert_not_called()
        assert result.dry_run_matches is not None
        assert len(result.dry_run_matches) == 1

    async def test_full_rescan_deletes_spanning_scope(self) -> None:
        pat = _pattern("Alfa Bravo")
        _captured, _result, repo = await _run(
            [_seg(1, "Alfa"), _seg(2, "Bravo")], [pat], full_rescan=True
        )
        repo.delete_spanning_mentions_by_segments.assert_awaited_once()

    async def test_full_rescan_recounts_deleted_affected_entities(self) -> None:
        # Under --full, an entity whose span was DELETED but not re-detected (a
        # different entity still matches, so the transcript isn't empty) must still be
        # recounted so its stale count is corrected (SC-007 convergence invariant).
        import uuid as _uuid

        gone = _uuid.uuid4()
        pat = _pattern("Alfa Bravo")  # this one still matches -> transcript non-empty
        captured, _result, repo = await _run(
            [_seg(1, "intro Alfa"), _seg(2, "Bravo outro")],
            [pat],
            full_rescan=True,
            delete_affected=[gone],
        )
        assert len(captured) == 1  # the still-matching span is detected
        repo.update_entity_counters.assert_awaited_once()
        _session, ids = repo.update_entity_counters.await_args.args
        assert gone in ids  # the disappeared-span entity is recounted
        assert pat.entity_id in ids  # and the still-detected one

    async def test_single_segment_transcript_skipped(self) -> None:
        pat = _pattern("Alfa Bravo")
        captured, _result, _repo = await _run([_seg(1, "Alfa Bravo")], [pat])
        assert captured == []
