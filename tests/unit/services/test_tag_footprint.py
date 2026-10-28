"""Unit tests for ``TagManagementService.tag_footprint`` delta logic (Feature 097).

The three repository methods are stubbed to return controlled id sets so the
subtraction ``tag_videos - baseline`` is the only thing under test. The real
``canonical_tags.entity_id`` write is proven in the integration test
``tests/integration/api/test_candidate_tag_footprint_api.py``.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from chronovista.services.tag_management import TagManagementService

pytestmark = pytest.mark.asyncio

NF = "synthetic footprint tag"


def _service(
    *,
    tag: MagicMock | None,
    tag_videos: set[str],
    name_matched: set[str],
) -> tuple[TagManagementService, AsyncMock]:
    repo = AsyncMock()
    repo.get_by_normalized_form.return_value = tag
    repo.get_video_ids_by_normalized_form.return_value = tag_videos
    repo.get_name_matched_video_ids.return_value = name_matched
    service = TagManagementService(
        canonical_tag_repo=repo,
        tag_alias_repo=AsyncMock(),
        named_entity_repo=AsyncMock(),
        entity_alias_repo=AsyncMock(),
        operation_log_repo=AsyncMock(),
    )
    return service, repo


def _tag(owner: uuid.UUID | None = None) -> MagicMock:
    tag = MagicMock()
    tag.entity_id = owner
    return tag


class TestTagFootprintDelta:
    async def test_pre_approval_baseline_is_name_matched_coverage(self) -> None:
        service, repo = _service(
            tag=_tag(),
            tag_videos={"a", "b", "c", "d"},
            name_matched={"a", "b"},
        )

        result = await service.tag_footprint(MagicMock(), normalized_form=NF)

        assert [m.would_newly_associate for m in result] == [2]
        repo.get_name_matched_video_ids.assert_awaited_once()

    async def test_post_approval_baseline_is_associated_set(self) -> None:
        service, repo = _service(
            tag=_tag(),
            tag_videos={"a", "b", "c", "d"},
            # Deliberately different from `associated` so using the wrong
            # baseline changes the answer.
            name_matched={"a", "b", "c"},
        )

        result = await service.tag_footprint(
            MagicMock(), normalized_form=NF, associated_video_ids={"a"}
        )

        assert [m.would_newly_associate for m in result] == [3]
        repo.get_name_matched_video_ids.assert_not_awaited()

    async def test_baseline_ids_outside_tag_set_do_not_reduce_delta(self) -> None:
        service, _ = _service(tag=_tag(), tag_videos={"a", "b"}, name_matched=set())

        result = await service.tag_footprint(
            MagicMock(), normalized_form=NF, associated_video_ids={"a", "x", "y", "z"}
        )

        # len(tag - baseline) == 1, not len(tag) - len(baseline) (which is -2).
        assert result[0].would_newly_associate == 1

    async def test_fully_covered_tag_yields_zero(self) -> None:
        service, _ = _service(tag=_tag(), tag_videos={"a", "b"}, name_matched=set())

        result = await service.tag_footprint(
            MagicMock(), normalized_form=NF, associated_video_ids={"a", "b"}
        )

        assert result[0].would_newly_associate == 0

    async def test_empty_associated_set_is_a_real_baseline_not_a_fallback(
        self,
    ) -> None:
        """``set()`` is not ``None``: the entity has no associations, so every tag
        video is new — it must NOT fall back to the name-matched baseline."""
        service, repo = _service(
            tag=_tag(), tag_videos={"a", "b"}, name_matched={"a", "b"}
        )

        result = await service.tag_footprint(
            MagicMock(), normalized_form=NF, associated_video_ids=set()
        )

        assert result[0].would_newly_associate == 2
        repo.get_name_matched_video_ids.assert_not_awaited()


class TestTagFootprintShape:
    async def test_no_matching_tag_returns_empty_without_querying_videos(
        self,
    ) -> None:
        service, repo = _service(tag=None, tag_videos={"a"}, name_matched=set())

        assert await service.tag_footprint(MagicMock(), normalized_form=NF) == []
        repo.get_video_ids_by_normalized_form.assert_not_awaited()

    async def test_owner_is_passed_through(self) -> None:
        owner = uuid.uuid4()
        service, _ = _service(tag=_tag(owner), tag_videos={"a"}, name_matched=set())

        result = await service.tag_footprint(MagicMock(), normalized_form=NF)

        assert result[0].owned_by_entity_id == owner
        assert result[0].normalized_form == NF

    async def test_unowned_tag_has_no_owner(self) -> None:
        service, _ = _service(tag=_tag(None), tag_videos={"a"}, name_matched=set())

        result = await service.tag_footprint(MagicMock(), normalized_form=NF)

        assert result[0].owned_by_entity_id is None
