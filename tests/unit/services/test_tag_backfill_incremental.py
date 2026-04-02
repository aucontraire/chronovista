"""
Tests for TagBackfillService.run_incremental_backfill() (T008).

Unit tests for the incremental tag normalization pipeline that processes
only unresolved tags (tags in ``video_tags`` without ``tag_aliases`` entries).

References
----------
- Feature 055: Incremental Tag Normalization
- FR-001 through FR-010, FR-019, FR-020, FR-021, FR-004a, FR-006, FR-006a
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chronovista.services.tag_backfill import TagBackfillService
from chronovista.services.tag_normalization import TagNormalizationService


@pytest.fixture
def normalization_service() -> TagNormalizationService:
    """Use the REAL normalization service (it's pure, no I/O)."""
    return TagNormalizationService()


@pytest.fixture
def service(normalization_service: TagNormalizationService) -> TagBackfillService:
    """Provide a fresh ``TagBackfillService`` instance."""
    return TagBackfillService(normalization_service)


@pytest.fixture
def mock_session() -> AsyncMock:
    """Provide a mock async database session."""
    return AsyncMock()


class TestRunIncrementalBackfill:
    """Tests for ``run_incremental_backfill`` method."""

    @pytest.mark.asyncio
    async def test_unresolved_tags_normalized_and_aliases_created(
        self, service: TagBackfillService, mock_session: AsyncMock
    ) -> None:
        """Unresolved tags are normalized and aliases are created."""
        unresolved = [("Python Tutorial", 5), ("java basics", 3)]

        with (
            patch(
                "chronovista.services.tag_backfill.VideoTagRepository"
            ) as mock_repo_cls,
            patch.object(
                service,
                "_normalize_and_group",
                new_callable=AsyncMock,
            ) as mock_normalize,
            patch.object(
                service,
                "_batch_insert_canonical_tags",
                new_callable=AsyncMock,
                return_value=(1, 0),
            ),
            patch.object(
                service,
                "_batch_insert_tag_aliases",
                new_callable=AsyncMock,
                return_value=(2, 0),
            ),
            patch.object(
                service,
                "_update_video_counts",
                new_callable=AsyncMock,
                return_value=1,
            ),
        ):
            mock_repo = mock_repo_cls.return_value
            mock_repo.get_unresolved_tags_with_counts = AsyncMock(
                return_value=unresolved
            )
            mock_normalize.return_value = (
                [{"id": uuid.uuid4(), "canonical_form": "Python Tutorial"}],
                [
                    {"raw_form": "Python Tutorial", "creation_method": "backfill"},
                    {"raw_form": "java basics", "creation_method": "backfill"},
                ],
                [],
            )

            result = await service.run_incremental_backfill(mock_session)

        assert result["tags_processed"] == 2
        assert result["aliases_created"] == 2

    @pytest.mark.asyncio
    async def test_existing_canonical_tag_reused_no_duplicate(
        self, service: TagBackfillService, mock_session: AsyncMock
    ) -> None:
        """Normalized form matching existing canonical tag reuses it."""
        unresolved = [("AI Tools", 10)]
        existing_ct_id = uuid.uuid4()

        with (
            patch(
                "chronovista.services.tag_backfill.VideoTagRepository"
            ) as mock_repo_cls,
            patch.object(
                service,
                "_normalize_and_group",
                new_callable=AsyncMock,
            ) as mock_normalize,
            patch.object(
                service,
                "_batch_insert_canonical_tags",
                new_callable=AsyncMock,
                return_value=(0, 0),
            ),
            patch.object(
                service,
                "_batch_insert_tag_aliases",
                new_callable=AsyncMock,
                return_value=(1, 0),
            ),
            patch.object(
                service,
                "_update_video_counts",
                new_callable=AsyncMock,
                return_value=1,
            ),
        ):
            mock_repo = mock_repo_cls.return_value
            mock_repo.get_unresolved_tags_with_counts = AsyncMock(
                return_value=unresolved
            )
            # No new canonical tags — existing one is reused
            mock_normalize.return_value = (
                [],  # No new canonical tags
                [
                    {
                        "raw_form": "AI Tools",
                        "canonical_tag_id": existing_ct_id,
                        "creation_method": "backfill",
                    }
                ],
                [],
            )

            result = await service.run_incremental_backfill(mock_session)

        assert result["canonical_tags_created"] == 0
        assert result["aliases_created"] == 1

    @pytest.mark.asyncio
    async def test_new_normalized_form_creates_canonical_tag_and_alias(
        self, service: TagBackfillService, mock_session: AsyncMock
    ) -> None:
        """New normalized form creates a new canonical tag + alias."""
        unresolved = [("brand new concept", 2)]

        with (
            patch(
                "chronovista.services.tag_backfill.VideoTagRepository"
            ) as mock_repo_cls,
            patch.object(
                service,
                "_normalize_and_group",
                new_callable=AsyncMock,
            ) as mock_normalize,
            patch.object(
                service,
                "_batch_insert_canonical_tags",
                new_callable=AsyncMock,
                return_value=(1, 0),
            ),
            patch.object(
                service,
                "_batch_insert_tag_aliases",
                new_callable=AsyncMock,
                return_value=(1, 0),
            ),
            patch.object(
                service,
                "_update_video_counts",
                new_callable=AsyncMock,
                return_value=1,
            ),
        ):
            mock_repo = mock_repo_cls.return_value
            mock_repo.get_unresolved_tags_with_counts = AsyncMock(
                return_value=unresolved
            )
            new_ct_id = uuid.uuid4()
            mock_normalize.return_value = (
                [
                    {
                        "id": new_ct_id,
                        "canonical_form": "Brand New Concept",
                        "normalized_form": "brand new concept",
                    }
                ],
                [
                    {
                        "raw_form": "brand new concept",
                        "canonical_tag_id": new_ct_id,
                        "creation_method": "backfill",
                    }
                ],
                [],
            )

            result = await service.run_incremental_backfill(mock_session)

        assert result["canonical_tags_created"] == 1
        assert result["aliases_created"] == 1

    @pytest.mark.asyncio
    async def test_tags_normalizing_to_none_are_skipped(
        self, service: TagBackfillService, mock_session: AsyncMock
    ) -> None:
        """Tags normalizing to None are skipped and counted."""
        unresolved = [("#", 1), ("...", 2), ("valid tag", 5)]

        with (
            patch(
                "chronovista.services.tag_backfill.VideoTagRepository"
            ) as mock_repo_cls,
            patch.object(
                service,
                "_normalize_and_group",
                new_callable=AsyncMock,
            ) as mock_normalize,
            patch.object(
                service,
                "_batch_insert_canonical_tags",
                new_callable=AsyncMock,
                return_value=(1, 0),
            ),
            patch.object(
                service,
                "_batch_insert_tag_aliases",
                new_callable=AsyncMock,
                return_value=(1, 0),
            ),
            patch.object(
                service,
                "_update_video_counts",
                new_callable=AsyncMock,
                return_value=1,
            ),
        ):
            mock_repo = mock_repo_cls.return_value
            mock_repo.get_unresolved_tags_with_counts = AsyncMock(
                return_value=unresolved
            )
            mock_normalize.return_value = (
                [{"id": uuid.uuid4(), "canonical_form": "Valid Tag"}],
                [{"raw_form": "valid tag", "creation_method": "backfill"}],
                [("#", 1), ("...", 2)],  # skip_list
            )

            result = await service.run_incremental_backfill(mock_session)

        assert result["skipped"] == 2

    @pytest.mark.asyncio
    async def test_empty_unresolved_returns_immediately(
        self, service: TagBackfillService, mock_session: AsyncMock
    ) -> None:
        """Empty unresolved set returns immediately with zero counts."""
        with patch(
            "chronovista.services.tag_backfill.VideoTagRepository"
        ) as mock_repo_cls:
            mock_repo = mock_repo_cls.return_value
            mock_repo.get_unresolved_tags_with_counts = AsyncMock(return_value=[])

            result = await service.run_incremental_backfill(mock_session)

        assert result["tags_processed"] == 0
        assert result["aliases_created"] == 0
        assert result["canonical_tags_created"] == 0
        assert result["canonical_tags_reused"] == 0
        assert result["skipped"] == 0
        assert result["duration"] >= 0

    @pytest.mark.asyncio
    async def test_creation_method_is_auto_normalize(
        self, service: TagBackfillService, mock_session: AsyncMock
    ) -> None:
        """New aliases use creation_method='auto_normalize' (FR-004a)."""
        unresolved = [("New Tag", 3)]

        ta_records_captured: list[list[dict[str, Any]]] = []

        with (
            patch(
                "chronovista.services.tag_backfill.VideoTagRepository"
            ) as mock_repo_cls,
            patch.object(
                service,
                "_normalize_and_group",
                new_callable=AsyncMock,
            ) as mock_normalize,
            patch.object(
                service,
                "_batch_insert_canonical_tags",
                new_callable=AsyncMock,
                return_value=(1, 0),
            ),
            patch.object(
                service,
                "_batch_insert_tag_aliases",
                new_callable=AsyncMock,
                return_value=(1, 0),
            ) as mock_batch_ta,
            patch.object(
                service,
                "_update_video_counts",
                new_callable=AsyncMock,
                return_value=1,
            ),
        ):
            mock_repo = mock_repo_cls.return_value
            mock_repo.get_unresolved_tags_with_counts = AsyncMock(
                return_value=unresolved
            )

            # _normalize_and_group returns 'backfill' as creation_method
            # run_incremental_backfill should override to 'auto_normalize'
            ta_record = {
                "raw_form": "New Tag",
                "creation_method": "backfill",
            }
            mock_normalize.return_value = (
                [{"id": uuid.uuid4()}],
                [ta_record],
                [],
            )

            def capture_ta(session: Any, records: Any, batch_size: Any) -> tuple[int, int]:
                ta_records_captured.append(list(records))
                return (1, 0)

            mock_batch_ta.side_effect = capture_ta

            await service.run_incremental_backfill(mock_session)

        # Verify the creation_method was overridden
        assert len(ta_records_captured) == 1
        for record in ta_records_captured[0]:
            assert record["creation_method"] == "auto_normalize"

    @pytest.mark.asyncio
    async def test_video_count_updated_after_inserts(
        self, service: TagBackfillService, mock_session: AsyncMock
    ) -> None:
        """video_count is updated after inserts (FR-006)."""
        unresolved = [("some tag", 5)]

        with (
            patch(
                "chronovista.services.tag_backfill.VideoTagRepository"
            ) as mock_repo_cls,
            patch.object(
                service,
                "_normalize_and_group",
                new_callable=AsyncMock,
            ) as mock_normalize,
            patch.object(
                service,
                "_batch_insert_canonical_tags",
                new_callable=AsyncMock,
                return_value=(1, 0),
            ),
            patch.object(
                service,
                "_batch_insert_tag_aliases",
                new_callable=AsyncMock,
                return_value=(1, 0),
            ),
            patch.object(
                service,
                "_update_video_counts",
                new_callable=AsyncMock,
                return_value=1,
            ) as mock_update_vc,
        ):
            mock_repo = mock_repo_cls.return_value
            mock_repo.get_unresolved_tags_with_counts = AsyncMock(
                return_value=unresolved
            )
            mock_normalize.return_value = (
                [{"id": uuid.uuid4()}],
                [{"raw_form": "some tag", "creation_method": "backfill"}],
                [],
            )

            await service.run_incremental_backfill(mock_session)

        mock_update_vc.assert_called_once_with(mock_session)

    @pytest.mark.asyncio
    async def test_alias_count_updated_after_inserts(
        self, service: TagBackfillService, mock_session: AsyncMock
    ) -> None:
        """alias_count is updated after inserts (FR-006a)."""
        unresolved = [("some tag", 5)]

        with (
            patch(
                "chronovista.services.tag_backfill.VideoTagRepository"
            ) as mock_repo_cls,
            patch.object(
                service,
                "_normalize_and_group",
                new_callable=AsyncMock,
            ) as mock_normalize,
            patch.object(
                service,
                "_batch_insert_canonical_tags",
                new_callable=AsyncMock,
                return_value=(1, 0),
            ),
            patch.object(
                service,
                "_batch_insert_tag_aliases",
                new_callable=AsyncMock,
                return_value=(1, 0),
            ),
            patch.object(
                service,
                "_update_video_counts",
                new_callable=AsyncMock,
                return_value=1,
            ),
        ):
            mock_repo = mock_repo_cls.return_value
            mock_repo.get_unresolved_tags_with_counts = AsyncMock(
                return_value=unresolved
            )
            mock_normalize.return_value = (
                [{"id": uuid.uuid4()}],
                [{"raw_form": "some tag", "creation_method": "backfill"}],
                [],
            )

            await service.run_incremental_backfill(mock_session)

        # session.execute should have been called for the alias_count update
        # followed by session.commit()
        mock_session.execute.assert_called()
        mock_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_batch_processing_with_configurable_batch_size(
        self, service: TagBackfillService, mock_session: AsyncMock
    ) -> None:
        """Batch processing uses configurable batch_size."""
        unresolved = [("tag1", 1), ("tag2", 2)]

        with (
            patch(
                "chronovista.services.tag_backfill.VideoTagRepository"
            ) as mock_repo_cls,
            patch.object(
                service,
                "_normalize_and_group",
                new_callable=AsyncMock,
            ) as mock_normalize,
            patch.object(
                service,
                "_batch_insert_canonical_tags",
                new_callable=AsyncMock,
                return_value=(2, 0),
            ) as mock_batch_ct,
            patch.object(
                service,
                "_batch_insert_tag_aliases",
                new_callable=AsyncMock,
                return_value=(2, 0),
            ) as mock_batch_ta,
            patch.object(
                service,
                "_update_video_counts",
                new_callable=AsyncMock,
                return_value=2,
            ),
        ):
            mock_repo = mock_repo_cls.return_value
            mock_repo.get_unresolved_tags_with_counts = AsyncMock(
                return_value=unresolved
            )
            mock_normalize.return_value = (
                [{"id": uuid.uuid4()}, {"id": uuid.uuid4()}],
                [
                    {"raw_form": "tag1", "creation_method": "backfill"},
                    {"raw_form": "tag2", "creation_method": "backfill"},
                ],
                [],
            )

            custom_batch_size = 500
            await service.run_incremental_backfill(
                mock_session, batch_size=custom_batch_size
            )

        # Verify batch_size was passed through
        mock_batch_ct.assert_called_once()
        assert mock_batch_ct.call_args[0][2] == custom_batch_size
        mock_batch_ta.assert_called_once()
        assert mock_batch_ta.call_args[0][2] == custom_batch_size

    @pytest.mark.asyncio
    async def test_concurrent_safety_on_conflict_do_nothing(
        self, service: TagBackfillService, mock_session: AsyncMock
    ) -> None:
        """Concurrent safety: ON CONFLICT DO NOTHING skips duplicates."""
        unresolved = [("concurrent tag", 3)]

        with (
            patch(
                "chronovista.services.tag_backfill.VideoTagRepository"
            ) as mock_repo_cls,
            patch.object(
                service,
                "_normalize_and_group",
                new_callable=AsyncMock,
            ) as mock_normalize,
            patch.object(
                service,
                "_batch_insert_canonical_tags",
                new_callable=AsyncMock,
                return_value=(0, 1),  # 0 inserted, 1 skipped (conflict)
            ),
            patch.object(
                service,
                "_batch_insert_tag_aliases",
                new_callable=AsyncMock,
                return_value=(0, 1),  # 0 inserted, 1 skipped (conflict)
            ),
            patch.object(
                service,
                "_update_video_counts",
                new_callable=AsyncMock,
                return_value=0,
            ),
        ):
            mock_repo = mock_repo_cls.return_value
            mock_repo.get_unresolved_tags_with_counts = AsyncMock(
                return_value=unresolved
            )
            mock_normalize.return_value = (
                [{"id": uuid.uuid4()}],
                [{"raw_form": "concurrent tag", "creation_method": "backfill"}],
                [],
            )

            result = await service.run_incremental_backfill(mock_session)

        # Service should complete without error; conflicts are silently skipped
        assert result["aliases_created"] == 0
        assert result["canonical_tags_created"] == 0
        assert result["canonical_tags_reused"] == 1

    @pytest.mark.asyncio
    async def test_dry_run_returns_preview_without_writing(
        self, service: TagBackfillService, mock_session: AsyncMock
    ) -> None:
        """dry_run=True returns preview data without writing to database."""
        unresolved = [("Preview Tag", 4)]

        with (
            patch(
                "chronovista.services.tag_backfill.VideoTagRepository"
            ) as mock_repo_cls,
            patch.object(
                service,
                "_normalize_and_group",
                new_callable=AsyncMock,
            ) as mock_normalize,
            patch.object(
                service,
                "_batch_insert_canonical_tags",
                new_callable=AsyncMock,
            ) as mock_batch_ct,
            patch.object(
                service,
                "_batch_insert_tag_aliases",
                new_callable=AsyncMock,
            ) as mock_batch_ta,
            patch.object(
                service,
                "_update_video_counts",
                new_callable=AsyncMock,
            ) as mock_update_vc,
        ):
            mock_repo = mock_repo_cls.return_value
            mock_repo.get_unresolved_tags_with_counts = AsyncMock(
                return_value=unresolved
            )
            ct_records = [{"id": uuid.uuid4(), "canonical_form": "Preview Tag"}]
            ta_records = [
                {"raw_form": "Preview Tag", "creation_method": "backfill"}
            ]
            mock_normalize.return_value = (ct_records, ta_records, [])

            result = await service.run_incremental_backfill(
                mock_session, dry_run=True
            )

        # No writes should have occurred
        mock_batch_ct.assert_not_called()
        mock_batch_ta.assert_not_called()
        mock_update_vc.assert_not_called()

        assert result["dry_run"] is True
        assert result["tags_processed"] == 1

    @pytest.mark.asyncio
    async def test_progress_callback_invoked(
        self, service: TagBackfillService, mock_session: AsyncMock
    ) -> None:
        """progress_callback is called with 0.0 at start and 100.0 at end."""
        callback = MagicMock()

        with patch(
            "chronovista.services.tag_backfill.VideoTagRepository"
        ) as mock_repo_cls:
            mock_repo = mock_repo_cls.return_value
            mock_repo.get_unresolved_tags_with_counts = AsyncMock(return_value=[])

            await service.run_incremental_backfill(
                mock_session, progress_callback=callback
            )

        # Should be called with 0.0 at start and 100.0 at end
        callback.assert_any_call(0.0)
        callback.assert_any_call(100.0)


class TestEnrichmentServiceNormalizationHook:
    """Tests for automatic normalization after enrichment (T017, T019).

    These tests exercise the normalization hook added at the end of
    ``EnrichmentService.enrich_videos()``.  We construct a real service
    with mocked dependencies and mock the YouTube API to return one video
    so the method reaches the hook code path.
    """

    @staticmethod
    def _make_enrichment_service() -> Any:
        """Create an EnrichmentService with mocked YouTube/repository deps."""
        from chronovista.services.enrichment.enrichment_service import (
            EnrichmentService,
        )

        svc = MagicMock(spec=EnrichmentService)
        # Bind the *real* method so the hook logic actually executes
        svc.enrich_videos = EnrichmentService.enrich_videos.__get__(
            svc, EnrichmentService
        )

        # One fake video so the method proceeds past the early return
        fake_video = MagicMock()
        fake_video.video_id = "TEST_VID_001"
        fake_video.title = "Test Video"
        fake_video.channel_id = "TEST_CH_001"
        svc._get_videos_for_enrichment = AsyncMock(return_value=[fake_video])
        svc.check_prerequisites = AsyncMock()

        # YouTube service returns empty results so per-video processing
        # falls through to "not found" path harmlessly
        svc.youtube_service = AsyncMock()
        svc.youtube_service.fetch_videos_batched = AsyncMock(
            return_value=([], ["TEST_VID_001"])
        )

        # Video repo: mark video as deleted when not found
        svc._video_repo = MagicMock()
        svc._video_repo.get_by_video_id = AsyncMock(return_value=None)

        return svc

    @pytest.mark.asyncio
    async def test_enrichment_calls_run_incremental_backfill_after_tags(
        self,
    ) -> None:
        """Enrichment service calls run_incremental_backfill() after tag processing (T017)."""
        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
        service = self._make_enrichment_service()

        mock_backfill_svc = MagicMock()
        mock_backfill_svc.run_incremental_backfill = AsyncMock(
            return_value={
                "tags_processed": 0,
                "aliases_created": 0,
                "canonical_tags_created": 0,
                "canonical_tags_reused": 0,
                "skipped": 0,
                "duration": 0.1,
            }
        )

        mock_backfill_cls = MagicMock(return_value=mock_backfill_svc)

        with (
            patch(
                "chronovista.services.enrichment.enrichment_service.get_shutdown_handler",
                return_value=MagicMock(check_shutdown=MagicMock()),
            ),
            patch(
                "chronovista.services.tag_backfill.TagBackfillService",
                mock_backfill_cls,
            ),
            patch(
                "chronovista.services.tag_normalization.TagNormalizationService",
            ),
        ):
            await service.enrich_videos(mock_session)

        mock_backfill_svc.run_incremental_backfill.assert_called_once_with(
            mock_session
        )

    @pytest.mark.asyncio
    async def test_enrichment_skips_normalization_when_skip_normalize_true(
        self,
    ) -> None:
        """skip_normalize=True prevents normalization call (T017 inverse)."""
        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
        service = self._make_enrichment_service()

        mock_backfill_svc = MagicMock()
        mock_backfill_svc.run_incremental_backfill = AsyncMock()

        with (
            patch(
                "chronovista.services.enrichment.enrichment_service.get_shutdown_handler",
                return_value=MagicMock(check_shutdown=MagicMock()),
            ),
            patch(
                "chronovista.services.tag_backfill.TagBackfillService",
                return_value=mock_backfill_svc,
            ),
            patch(
                "chronovista.services.tag_normalization.TagNormalizationService",
            ),
        ):
            await service.enrich_videos(mock_session, skip_normalize=True)

        mock_backfill_svc.run_incremental_backfill.assert_not_called()

    @pytest.mark.asyncio
    async def test_normalization_error_logs_warning_does_not_fail_enrichment(
        self,
    ) -> None:
        """Normalization error logs warning but does not fail enrichment (T019)."""
        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
        service = self._make_enrichment_service()

        mock_backfill_svc = MagicMock()
        norm_error = RuntimeError("DB constraint violation")
        mock_backfill_svc.run_incremental_backfill = AsyncMock(
            side_effect=norm_error,
        )

        with (
            patch(
                "chronovista.services.enrichment.enrichment_service.get_shutdown_handler",
                return_value=MagicMock(check_shutdown=MagicMock()),
            ),
            patch(
                "chronovista.services.tag_backfill.TagBackfillService",
                return_value=mock_backfill_svc,
            ),
            patch(
                "chronovista.services.tag_normalization.TagNormalizationService",
            ),
            patch(
                "chronovista.services.enrichment.enrichment_service.logger"
            ) as mock_logger,
        ):
            # Should NOT raise — enrichment completes despite normalization error
            report = await service.enrich_videos(mock_session)

        # Verify warning was logged
        mock_logger.warning.assert_any_call(
            "Automatic tag normalization failed: %s",
            norm_error,
        )

        # Enrichment returned successfully
        assert report is not None
