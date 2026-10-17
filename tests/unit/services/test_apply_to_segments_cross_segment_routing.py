"""Unit tests for the cross-segment routing + selection-scoping in apply_to_segments.

Feature 081 wiring. These isolate the routing decision from the database: the
collaborators (``_find_cross_segment_matches`` / ``_apply_cross_segment_corrections``)
are mocked, so the tests assert (a) a selected anchor pair is routed to the span
applier with entity+replacement, (b) a pair whose anchor was NOT selected is
filtered out before applying (selection-scoping), and (c) a single-segment-only
selection never calls the span applier (FR-006). Synthetic placeholder names only.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chronovista.models.enums import CorrectionType
from chronovista.services.batch_correction_service import BatchCorrectionService

pytestmark = pytest.mark.asyncio

VID = "testvideo01"


def _segment(seg_id: int, text: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=seg_id,
        video_id=VID,
        language_code="en",
        text=text,
        corrected_text=None,
        has_correction=False,
    )


def _cross_match(anchor_id: int) -> SimpleNamespace:
    combined = "the guest is Alpha Bravado speaks"
    return SimpleNamespace(
        pair=SimpleNamespace(
            segment_a=SimpleNamespace(id=anchor_id, video_id=VID),
            segment_b=SimpleNamespace(id=anchor_id + 1, video_id=VID),
            combined_text=combined,
        ),
        match_start=combined.index("Alpha"),
        match_end=combined.index("Alpha") + len("Alpha Bravado"),
    )


def _entity() -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), status="active")


def _service_with_mocks(
    *,
    fetched_segments: list[SimpleNamespace],
    entity: SimpleNamespace | None,
    cross_found: list[SimpleNamespace],
) -> tuple[BatchCorrectionService, AsyncMock, AsyncMock]:
    svc = BatchCorrectionService(
        correction_service=MagicMock(),
        segment_repo=MagicMock(),
        correction_repo=MagicMock(),
    )
    find_mock = AsyncMock(return_value=cross_found)
    apply_mock = AsyncMock(return_value=(2, 0, 0, 0))
    svc._find_cross_segment_matches = find_mock  # type: ignore[method-assign]
    svc._apply_cross_segment_corrections = apply_mock  # type: ignore[method-assign]
    svc._record_asr_alias_for_batch_replacement = AsyncMock()  # type: ignore[method-assign]
    # Single-segment apply + its per-segment mention (only used in FR-006 case).
    svc._correction_service.apply_correction = AsyncMock(  # type: ignore[attr-defined]
        return_value=SimpleNamespace(id=uuid.uuid4())
    )
    svc._create_entity_mentions_for_segment = AsyncMock()  # type: ignore[method-assign]

    entity_result = MagicMock()
    entity_result.scalar_one_or_none.return_value = entity
    segs_result = MagicMock()
    segs_result.scalars.return_value.all.return_value = fetched_segments

    session = AsyncMock()
    session.execute.side_effect = [entity_result, segs_result]
    svc._session = session  # type: ignore[attr-defined]
    return svc, find_mock, apply_mock


async def _run(
    svc: BatchCorrectionService,
    *,
    segment_ids: list[int],
    entity_id: Any,
) -> Any:
    session = svc._session  # type: ignore[attr-defined]
    with patch(
        "chronovista.services.batch_correction_service.EntityMentionRepository"
    ) as repo_cls:
        repo_cls.return_value = MagicMock(
            update_entity_counters=AsyncMock(),
            update_alias_counters=AsyncMock(),
        )
        return await svc.apply_to_segments(
            session,
            pattern="Alpha Bravado",
            replacement="Alfa Bravo",
            segment_ids=segment_ids,
            cross_segment=True,
            correction_type=CorrectionType.PROPER_NOUN,
            entity_id=entity_id,
            auto_rebuild=False,
        )


class TestCrossSegmentRouting:
    async def test_selected_anchor_pair_routes_to_span_applier(self) -> None:
        entity = _entity()
        seg_a = _segment(100, "the guest is Alpha")  # no single-segment match
        svc, _find, apply_mock = _service_with_mocks(
            fetched_segments=[seg_a],
            entity=entity,
            cross_found=[_cross_match(100)],
        )
        await _run(svc, segment_ids=[100], entity_id=entity.id)

        apply_mock.assert_awaited_once()
        _args, kwargs = apply_mock.await_args
        assert kwargs["entity"] is entity
        assert kwargs["replacement"] == "Alfa Bravo"
        passed_matches = apply_mock.await_args.args[1]
        assert [m.pair.segment_a.id for m in passed_matches] == [100]

    async def test_unselected_sibling_pair_is_filtered_out(self) -> None:
        # Detector returns a selected pair (anchor 100) AND an unselected sibling
        # pair (anchor 900); only the selected one reaches the applier.
        entity = _entity()
        seg_a = _segment(100, "the guest is Alpha")
        svc, _find, apply_mock = _service_with_mocks(
            fetched_segments=[seg_a],
            entity=entity,
            cross_found=[_cross_match(100), _cross_match(900)],
        )
        await _run(svc, segment_ids=[100], entity_id=entity.id)

        apply_mock.assert_awaited_once()
        passed_matches = apply_mock.await_args.args[1]
        assert [m.pair.segment_a.id for m in passed_matches] == [100]

    async def test_single_segment_only_selection_does_not_route(self) -> None:
        # FR-006: the full name sits inside the one selected segment, so it is a
        # single-segment match; the detector finds no span and the applier is
        # never called.
        entity = _entity()
        seg_k = _segment(100, "Alpha Bravado here")  # full garble in one segment
        svc, _find, apply_mock = _service_with_mocks(
            fetched_segments=[seg_k],
            entity=entity,
            cross_found=[],
        )
        await _run(svc, segment_ids=[100], entity_id=entity.id)

        apply_mock.assert_not_awaited()
        # The single-segment match still had its per-segment mention created.
        svc._create_entity_mentions_for_segment.assert_awaited_once()  # type: ignore[attr-defined]
