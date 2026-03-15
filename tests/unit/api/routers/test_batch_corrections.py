"""
Unit tests for batch correction API endpoints (Feature 045, T016).

Tests the GET /batches and DELETE /{batch_id} endpoints in:
  src/chronovista/api/routers/batch_corrections.py

Mounted at: /api/v1/corrections/batch

Scenarios covered:
- GET /batches: pagination (offset/limit), corrected_by_user_id filter,
  sort order (most recent first), empty results
- DELETE /{batch_id}: 200 success with revert count, 404 when batch not found,
  409 when batch already reverted
- DELETE /{batch_id}: malformed UUID returns 422
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.api.deps import get_db, require_auth
from chronovista.api.main import app
from chronovista.models.batch_correction_models import BatchCorrectionResult, BatchListItem
from tests.factories.batch_correction_factory import BatchListItemFactory

# CRITICAL: This line ensures async tests work with coverage
pytestmark = pytest.mark.asyncio


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _make_batch_list_item(
    *,
    batch_id: uuid.UUID | None = None,
    correction_count: int = 5,
    corrected_by_user_id: str = "user:batch",
    pattern: str = "Shanebam",
    replacement: str = "Sheinbaum",
    batch_timestamp: datetime | None = None,
) -> BatchListItem:
    """Build a BatchListItem via the factory with optional overrides."""
    kwargs: dict[str, object] = {
        "correction_count": correction_count,
        "corrected_by_user_id": corrected_by_user_id,
        "pattern": pattern,
        "replacement": replacement,
    }
    if batch_id is not None:
        kwargs["batch_id"] = batch_id
    if batch_timestamp is not None:
        kwargs["batch_timestamp"] = batch_timestamp
    return BatchListItemFactory.build(**kwargs)


def _make_revert_result(
    *,
    total_applied: int = 3,
    total_skipped: int = 0,
    total_failed: int = 0,
    total_matched: int = 3,
) -> BatchCorrectionResult:
    """Build a BatchCorrectionResult for mocking batch_revert returns."""
    return BatchCorrectionResult(
        total_scanned=10,
        total_matched=total_matched,
        total_applied=total_applied,
        total_skipped=total_skipped,
        total_failed=total_failed,
        failed_batches=0,
        unique_videos=1,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def mock_session() -> AsyncMock:
    """Provide a clean AsyncSession mock for each test."""
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
async def client(mock_session: AsyncMock) -> AsyncGenerator[AsyncClient, None]:
    """FastAPI test client with DB and auth overridden."""

    async def _get_db() -> AsyncGenerator[AsyncSession, None]:
        yield mock_session

    async def _require_auth() -> None:
        return None

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[require_auth] = _require_auth

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        app.dependency_overrides.clear()


# ═══════════════════════════════════════════════════════════════════════════
# GET /api/v1/corrections/batch/batches  — list batches
# ═══════════════════════════════════════════════════════════════════════════


class TestListBatches:
    """Tests for GET /api/v1/corrections/batch/batches."""

    # ------------------------------------------------------------------
    # Basic 200 / empty result
    # ------------------------------------------------------------------

    @patch(
        "chronovista.api.routers.batch_corrections._correction_repo",
        new_callable=MagicMock,
    )
    async def test_returns_200_with_empty_list(
        self,
        mock_repo: MagicMock,
        client: AsyncClient,
    ) -> None:
        """GET /batches returns 200 with an empty data list when no batches exist."""
        mock_repo.get_batch_list = AsyncMock(return_value=[])

        response = await client.get("/api/v1/corrections/batch/batches")

        assert response.status_code == 200
        body = response.json()
        assert body["data"] == []

    @patch(
        "chronovista.api.routers.batch_corrections._correction_repo",
        new_callable=MagicMock,
    )
    async def test_returns_batch_items(
        self,
        mock_repo: MagicMock,
        client: AsyncClient,
    ) -> None:
        """GET /batches returns each batch's fields in the response data."""
        item = _make_batch_list_item(
            correction_count=7,
            corrected_by_user_id="user:batch",
            pattern="teh",
            replacement="the",
        )
        mock_repo.get_batch_list = AsyncMock(return_value=[item])

        response = await client.get("/api/v1/corrections/batch/batches")

        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data) == 1
        assert data[0]["correction_count"] == 7
        assert data[0]["corrected_by_user_id"] == "user:batch"
        assert data[0]["pattern"] == "teh"
        assert data[0]["replacement"] == "the"

    # ------------------------------------------------------------------
    # Pagination
    # ------------------------------------------------------------------

    @patch(
        "chronovista.api.routers.batch_corrections._correction_repo",
        new_callable=MagicMock,
    )
    async def test_pagination_offset_and_limit_forwarded(
        self,
        mock_repo: MagicMock,
        client: AsyncClient,
    ) -> None:
        """The offset and limit query params are passed to get_batch_list."""
        mock_repo.get_batch_list = AsyncMock(return_value=[])

        await client.get("/api/v1/corrections/batch/batches?offset=10&limit=5")

        mock_repo.get_batch_list.assert_awaited_once()
        call_kwargs = mock_repo.get_batch_list.call_args.kwargs
        assert call_kwargs["offset"] == 10
        assert call_kwargs["limit"] == 5

    @patch(
        "chronovista.api.routers.batch_corrections._correction_repo",
        new_callable=MagicMock,
    )
    async def test_pagination_meta_has_more_false_when_partial_page(
        self,
        mock_repo: MagicMock,
        client: AsyncClient,
    ) -> None:
        """has_more is False when fewer items are returned than the page limit."""
        items = [_make_batch_list_item() for _ in range(3)]
        mock_repo.get_batch_list = AsyncMock(return_value=items)

        response = await client.get("/api/v1/corrections/batch/batches?limit=20")

        assert response.status_code == 200
        pagination = response.json()["pagination"]
        assert pagination["has_more"] is False

    @patch(
        "chronovista.api.routers.batch_corrections._correction_repo",
        new_callable=MagicMock,
    )
    async def test_pagination_meta_has_more_true_when_full_page(
        self,
        mock_repo: MagicMock,
        client: AsyncClient,
    ) -> None:
        """has_more is True when the returned count equals the page limit."""
        items = [_make_batch_list_item() for _ in range(5)]
        mock_repo.get_batch_list = AsyncMock(return_value=items)

        response = await client.get("/api/v1/corrections/batch/batches?limit=5")

        assert response.status_code == 200
        pagination = response.json()["pagination"]
        assert pagination["has_more"] is True

    @patch(
        "chronovista.api.routers.batch_corrections._correction_repo",
        new_callable=MagicMock,
    )
    async def test_default_limit_is_20(
        self,
        mock_repo: MagicMock,
        client: AsyncClient,
    ) -> None:
        """Omitting limit defaults to 20 in the get_batch_list call."""
        mock_repo.get_batch_list = AsyncMock(return_value=[])

        await client.get("/api/v1/corrections/batch/batches")

        call_kwargs = mock_repo.get_batch_list.call_args.kwargs
        assert call_kwargs["limit"] == 20

    @patch(
        "chronovista.api.routers.batch_corrections._correction_repo",
        new_callable=MagicMock,
    )
    async def test_limit_above_100_returns_422(
        self,
        mock_repo: MagicMock,
        client: AsyncClient,
    ) -> None:
        """A limit > 100 is rejected with HTTP 422."""
        mock_repo.get_batch_list = AsyncMock(return_value=[])

        response = await client.get("/api/v1/corrections/batch/batches?limit=101")

        assert response.status_code == 422

    @patch(
        "chronovista.api.routers.batch_corrections._correction_repo",
        new_callable=MagicMock,
    )
    async def test_negative_offset_returns_422(
        self,
        mock_repo: MagicMock,
        client: AsyncClient,
    ) -> None:
        """A negative offset is rejected with HTTP 422."""
        mock_repo.get_batch_list = AsyncMock(return_value=[])

        response = await client.get("/api/v1/corrections/batch/batches?offset=-1")

        assert response.status_code == 422

    # ------------------------------------------------------------------
    # corrected_by_user_id filter
    # ------------------------------------------------------------------

    @patch(
        "chronovista.api.routers.batch_corrections._correction_repo",
        new_callable=MagicMock,
    )
    async def test_user_id_filter_forwarded(
        self,
        mock_repo: MagicMock,
        client: AsyncClient,
    ) -> None:
        """The corrected_by_user_id query param is forwarded to get_batch_list."""
        mock_repo.get_batch_list = AsyncMock(return_value=[])

        await client.get(
            "/api/v1/corrections/batch/batches?corrected_by_user_id=cli"
        )

        call_kwargs = mock_repo.get_batch_list.call_args.kwargs
        assert call_kwargs["corrected_by_user_id"] == "cli"

    @patch(
        "chronovista.api.routers.batch_corrections._correction_repo",
        new_callable=MagicMock,
    )
    async def test_omitting_user_id_filter_passes_none(
        self,
        mock_repo: MagicMock,
        client: AsyncClient,
    ) -> None:
        """Omitting corrected_by_user_id sends None to get_batch_list."""
        mock_repo.get_batch_list = AsyncMock(return_value=[])

        await client.get("/api/v1/corrections/batch/batches")

        call_kwargs = mock_repo.get_batch_list.call_args.kwargs
        assert call_kwargs["corrected_by_user_id"] is None

    @patch(
        "chronovista.api.routers.batch_corrections._correction_repo",
        new_callable=MagicMock,
    )
    async def test_user_id_filter_restricts_results(
        self,
        mock_repo: MagicMock,
        client: AsyncClient,
    ) -> None:
        """When user filter matches, only those items appear in data."""
        item = _make_batch_list_item(corrected_by_user_id="api")
        mock_repo.get_batch_list = AsyncMock(return_value=[item])

        response = await client.get(
            "/api/v1/corrections/batch/batches?corrected_by_user_id=api"
        )

        data = response.json()["data"]
        assert len(data) == 1
        assert data[0]["corrected_by_user_id"] == "api"

    # ------------------------------------------------------------------
    # Sort order / multiple items
    # ------------------------------------------------------------------

    @patch(
        "chronovista.api.routers.batch_corrections._correction_repo",
        new_callable=MagicMock,
    )
    async def test_most_recent_first_order_preserved(
        self,
        mock_repo: MagicMock,
        client: AsyncClient,
    ) -> None:
        """Items are returned in the order provided by get_batch_list (most recent first)."""
        older = _make_batch_list_item(
            pattern="old",
            batch_timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        newer = _make_batch_list_item(
            pattern="new",
            batch_timestamp=datetime(2024, 6, 1, tzinfo=timezone.utc),
        )
        # Simulate repository returning newest first
        mock_repo.get_batch_list = AsyncMock(return_value=[newer, older])

        response = await client.get("/api/v1/corrections/batch/batches")

        data = response.json()["data"]
        assert len(data) == 2
        assert data[0]["pattern"] == "new"
        assert data[1]["pattern"] == "old"

    @patch(
        "chronovista.api.routers.batch_corrections._correction_repo",
        new_callable=MagicMock,
    )
    async def test_batch_id_is_uuid_string_in_response(
        self,
        mock_repo: MagicMock,
        client: AsyncClient,
    ) -> None:
        """The batch_id field in the response is a valid UUID string."""
        fixed_id = uuid.UUID("01932f4a-dead-7000-beef-000000000001")
        item = _make_batch_list_item(batch_id=fixed_id)
        mock_repo.get_batch_list = AsyncMock(return_value=[item])

        response = await client.get("/api/v1/corrections/batch/batches")

        data = response.json()["data"]
        returned_id = data[0]["batch_id"]
        # Validate it round-trips as a UUID
        assert uuid.UUID(returned_id) == fixed_id

    @patch(
        "chronovista.api.routers.batch_corrections._correction_repo",
        new_callable=MagicMock,
    )
    async def test_pagination_meta_limit_and_offset_echoed(
        self,
        mock_repo: MagicMock,
        client: AsyncClient,
    ) -> None:
        """Pagination meta echoes the requested limit and offset."""
        mock_repo.get_batch_list = AsyncMock(return_value=[])

        response = await client.get(
            "/api/v1/corrections/batch/batches?offset=5&limit=10"
        )

        pagination = response.json()["pagination"]
        assert pagination["limit"] == 10
        assert pagination["offset"] == 5


# ═══════════════════════════════════════════════════════════════════════════
# DELETE /api/v1/corrections/batch/{batch_id}  — revert batch
# ═══════════════════════════════════════════════════════════════════════════


class TestRevertBatch:
    """Tests for DELETE /api/v1/corrections/batch/{batch_id}."""

    VALID_BATCH_ID: uuid.UUID = uuid.UUID("01932f4a-dead-7000-beef-000000000001")

    # ------------------------------------------------------------------
    # 200 success
    # ------------------------------------------------------------------

    @patch(
        "chronovista.api.routers.batch_corrections._correction_repo",
        new_callable=MagicMock,
    )
    @patch(
        "chronovista.api.routers.batch_corrections._batch_service",
        new_callable=MagicMock,
    )
    async def test_success_200_returns_reverted_count(
        self,
        mock_svc: MagicMock,
        mock_repo: MagicMock,
        client: AsyncClient,
    ) -> None:
        """DELETE returns 200 with reverted_count matching total_applied."""
        from chronovista.db.models import TranscriptCorrection as TranscriptCorrectionDB

        correction = MagicMock(spec=TranscriptCorrectionDB)
        mock_repo.get_by_batch_id = AsyncMock(return_value=[correction])

        revert_result = _make_revert_result(total_applied=4, total_matched=4)
        mock_svc.batch_revert = AsyncMock(return_value=revert_result)

        response = await client.delete(
            f"/api/v1/corrections/batch/{self.VALID_BATCH_ID}"
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["reverted_count"] == 4

    @patch(
        "chronovista.api.routers.batch_corrections._correction_repo",
        new_callable=MagicMock,
    )
    @patch(
        "chronovista.api.routers.batch_corrections._batch_service",
        new_callable=MagicMock,
    )
    async def test_success_includes_skipped_count(
        self,
        mock_svc: MagicMock,
        mock_repo: MagicMock,
        client: AsyncClient,
    ) -> None:
        """DELETE response includes skipped_count = skipped + failed."""
        from chronovista.db.models import TranscriptCorrection as TranscriptCorrectionDB

        correction = MagicMock(spec=TranscriptCorrectionDB)
        mock_repo.get_by_batch_id = AsyncMock(return_value=[correction])

        revert_result = _make_revert_result(
            total_applied=2,
            total_skipped=1,
            total_failed=1,
            total_matched=4,
        )
        mock_svc.batch_revert = AsyncMock(return_value=revert_result)

        response = await client.delete(
            f"/api/v1/corrections/batch/{self.VALID_BATCH_ID}"
        )

        assert response.status_code == 200
        data = response.json()["data"]
        # skipped_count = total_skipped + total_failed = 1 + 1
        assert data["skipped_count"] == 2

    @patch(
        "chronovista.api.routers.batch_corrections._correction_repo",
        new_callable=MagicMock,
    )
    @patch(
        "chronovista.api.routers.batch_corrections._batch_service",
        new_callable=MagicMock,
    )
    async def test_batch_revert_called_with_correct_batch_id(
        self,
        mock_svc: MagicMock,
        mock_repo: MagicMock,
        client: AsyncClient,
    ) -> None:
        """The batch_id is forwarded correctly to batch_service.batch_revert."""
        from chronovista.db.models import TranscriptCorrection as TranscriptCorrectionDB

        correction = MagicMock(spec=TranscriptCorrectionDB)
        mock_repo.get_by_batch_id = AsyncMock(return_value=[correction])

        revert_result = _make_revert_result(total_applied=1)
        mock_svc.batch_revert = AsyncMock(return_value=revert_result)

        await client.delete(f"/api/v1/corrections/batch/{self.VALID_BATCH_ID}")

        mock_svc.batch_revert.assert_awaited_once()
        call_kwargs = mock_svc.batch_revert.call_args.kwargs
        assert call_kwargs["batch_id"] == self.VALID_BATCH_ID

    # ------------------------------------------------------------------
    # 404 — batch not found
    # ------------------------------------------------------------------

    @patch(
        "chronovista.api.routers.batch_corrections._correction_repo",
        new_callable=MagicMock,
    )
    async def test_404_when_batch_id_not_found(
        self,
        mock_repo: MagicMock,
        client: AsyncClient,
    ) -> None:
        """DELETE returns 404 when no corrections exist for the batch_id."""
        mock_repo.get_by_batch_id = AsyncMock(return_value=[])

        response = await client.delete(
            f"/api/v1/corrections/batch/{self.VALID_BATCH_ID}"
        )

        assert response.status_code == 404

    @patch(
        "chronovista.api.routers.batch_corrections._correction_repo",
        new_callable=MagicMock,
    )
    async def test_404_response_contains_batch_id(
        self,
        mock_repo: MagicMock,
        client: AsyncClient,
    ) -> None:
        """The 404 response body references the missing batch_id."""
        mock_repo.get_by_batch_id = AsyncMock(return_value=[])

        response = await client.delete(
            f"/api/v1/corrections/batch/{self.VALID_BATCH_ID}"
        )

        assert response.status_code == 404
        body = response.text
        assert str(self.VALID_BATCH_ID) in body

    # ------------------------------------------------------------------
    # 409 — already reverted
    # ------------------------------------------------------------------

    @patch(
        "chronovista.api.routers.batch_corrections._correction_repo",
        new_callable=MagicMock,
    )
    @patch(
        "chronovista.api.routers.batch_corrections._batch_service",
        new_callable=MagicMock,
    )
    async def test_409_when_all_corrections_already_reverted(
        self,
        mock_svc: MagicMock,
        mock_repo: MagicMock,
        client: AsyncClient,
    ) -> None:
        """DELETE returns 409 when batch_revert reports 0 applied and 0 matched."""
        from chronovista.db.models import TranscriptCorrection as TranscriptCorrectionDB

        correction = MagicMock(spec=TranscriptCorrectionDB)
        mock_repo.get_by_batch_id = AsyncMock(return_value=[correction])

        # Simulates fully-reverted batch: nothing was matched or applied
        already_reverted = _make_revert_result(
            total_applied=0,
            total_matched=0,
        )
        mock_svc.batch_revert = AsyncMock(return_value=already_reverted)

        response = await client.delete(
            f"/api/v1/corrections/batch/{self.VALID_BATCH_ID}"
        )

        assert response.status_code == 409

    @patch(
        "chronovista.api.routers.batch_corrections._correction_repo",
        new_callable=MagicMock,
    )
    @patch(
        "chronovista.api.routers.batch_corrections._batch_service",
        new_callable=MagicMock,
    )
    async def test_409_response_mentions_batch_id(
        self,
        mock_svc: MagicMock,
        mock_repo: MagicMock,
        client: AsyncClient,
    ) -> None:
        """The 409 response body references the already-reverted batch_id."""
        from chronovista.db.models import TranscriptCorrection as TranscriptCorrectionDB

        correction = MagicMock(spec=TranscriptCorrectionDB)
        mock_repo.get_by_batch_id = AsyncMock(return_value=[correction])

        already_reverted = _make_revert_result(
            total_applied=0,
            total_matched=0,
        )
        mock_svc.batch_revert = AsyncMock(return_value=already_reverted)

        response = await client.delete(
            f"/api/v1/corrections/batch/{self.VALID_BATCH_ID}"
        )

        assert response.status_code == 409
        body = response.text
        assert str(self.VALID_BATCH_ID) in body

    # ------------------------------------------------------------------
    # 422 — malformed UUID
    # ------------------------------------------------------------------

    async def test_422_for_malformed_uuid(self, client: AsyncClient) -> None:
        """DELETE with a non-UUID path segment returns 422 Unprocessable Entity."""
        response = await client.delete(
            "/api/v1/corrections/batch/not-a-real-uuid"
        )
        assert response.status_code == 422

    async def test_422_for_uuid_with_wrong_length(
        self, client: AsyncClient
    ) -> None:
        """DELETE with a truncated UUID-like string returns 422."""
        response = await client.delete(
            "/api/v1/corrections/batch/01932f4a-dead"
        )
        assert response.status_code == 422

    async def test_422_for_numeric_batch_id(self, client: AsyncClient) -> None:
        """DELETE with a plain integer path segment returns 422."""
        response = await client.delete("/api/v1/corrections/batch/12345")
        assert response.status_code == 422

    async def test_422_for_empty_batch_id_segment(
        self, client: AsyncClient
    ) -> None:
        """DELETE with an empty string path segment returns 404 (no route match)."""
        # FastAPI does not match the parameterised route for an empty segment
        response = await client.delete("/api/v1/corrections/batch/")
        # Empty segment either 404s (no route) or 405 (method not allowed on
        # the /batches route).  Either way it is not a successful revert.
        assert response.status_code in (404, 405, 422)
