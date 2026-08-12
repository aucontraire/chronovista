"""
Tests for YouTubeService batch fetch operations (T067b).

Every test here calls ``fetch_playlists_batched``. That sounds like a given; it
is stated because the previous version of this file did not. All 21 of its
tests defined a *local copy* of the method inside the test body — one of them
under the comment ``# Call the method (simulating what we expect)`` — and
asserted against the copy. Several asserted only on set literals the test had
just constructed. The production method had no test coverage at all, which is
why #149 shipped and survived two occurrences.

A reimplementation cannot fail when the original is wrong. It fails when the
two drift, which nobody notices, because the copy is the thing being asserted.

Covers:
- fetch_playlists_batched() returns playlists and a not_found set
- Batch size limits (max 50) and splitting across batches
- #149: a batch that fails to fetch does not contribute to not_found,
  in both the playlist and the video path
- Partial results (some found, some not)
- Empty input
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from chronovista.services.youtube_service import YouTubeService

pytestmark = pytest.mark.asyncio


def _playlist_item(playlist_id: str) -> dict[str, Any]:
    """A minimal API item that YouTubePlaylistResponse will validate."""
    return {
        "id": playlist_id,
        "snippet": {
            "title": f"Playlist {playlist_id}",
            "description": "",
            "channelId": "UCtest123",
            "publishedAt": "2024-01-01T00:00:00Z",
        },
        "contentDetails": {"itemCount": 10},
        "status": {"privacyStatus": "private"},
    }


@pytest.fixture
def youtube_service() -> YouTubeService:
    """Service with a mocked API client, so no credentials are needed."""
    service = YouTubeService()
    service._service = MagicMock()  # type: ignore[assignment]
    return service


def _respond_with(service: YouTubeService, responses: list[Any]) -> MagicMock:
    """Drive the real fetch path, one entry in ``responses`` per batch.

    Each entry is either a dict (returned as the API response) or an exception
    instance (raised in its place). This patches ``_execute_with_retry`` rather
    than ``get_playlist_details``: the batching loop, the response parsing and
    the not-found arithmetic all run for real, and only the network call is
    replaced.
    """
    calls = AsyncMock()

    def _next(_request: Any) -> Any:
        entry = responses[_next.index]  # type: ignore[attr-defined]
        _next.index += 1  # type: ignore[attr-defined]
        if isinstance(entry, Exception):
            raise entry
        return entry

    _next.index = 0  # type: ignore[attr-defined]
    calls.side_effect = _next
    service._execute_with_retry = calls  # type: ignore[method-assign]
    return calls


class TestNotFoundSemantics:
    """What ``not_found`` is allowed to mean.

    Callers act on this set by hiding playlists from the user, so a member of
    it is an assertion that the API answered and the playlist was not in the
    answer.
    """

    async def test_absent_ids_are_reported_not_found(
        self, youtube_service: YouTubeService
    ) -> None:
        _respond_with(youtube_service, [{"items": [_playlist_item("PLfound")]}])

        playlists, not_found = await youtube_service.fetch_playlists_batched(
            ["PLfound", "PLgone1", "PLgone2"]
        )

        assert [p.id for p in playlists] == ["PLfound"]
        assert not_found == {"PLgone1", "PLgone2"}

    async def test_a_failed_batch_reports_nothing_as_not_found(
        self, youtube_service: YouTubeService
    ) -> None:
        """#149, the whole bug in one assertion.

        The single batch raises, so nothing is known about any of these three
        playlists. Previously they were derived as not-found by subtraction —
        requested minus found — and the caller hid all three.
        """
        _respond_with(youtube_service, [RuntimeError("token expired")])

        playlists, not_found = await youtube_service.fetch_playlists_batched(
            ["PLone", "PLtwo", "PLthree"]
        )

        assert playlists == []
        assert not_found == set(), (
            "a request that never completed is not evidence that these "
            "playlists were deleted"
        )

    async def test_a_failed_batch_does_not_taint_a_successful_one(
        self, youtube_service: YouTubeService
    ) -> None:
        """The genuinely-absent ID in the *successful* batch is still reported.

        Containment must not become suppression: excluding unresolved IDs is
        only correct if real deletions in other batches still surface.
        """
        ids = [f"PL{i:04d}" for i in range(50)] + ["PLalive", "PLdeleted"]
        _respond_with(
            youtube_service,
            [
                RuntimeError("transient failure"),
                {"items": [_playlist_item("PLalive")]},
            ],
        )

        playlists, not_found = await youtube_service.fetch_playlists_batched(ids)

        assert [p.id for p in playlists] == ["PLalive"]
        assert not_found == {"PLdeleted"}

    async def test_an_id_found_in_a_later_batch_is_not_reported_missing(
        self, youtube_service: YouTubeService
    ) -> None:
        """A duplicate ID spanning a failed and a successful batch counts found."""
        ids = ["PLdup"] + [f"PL{i:04d}" for i in range(49)] + ["PLdup"]
        _respond_with(
            youtube_service,
            [RuntimeError("boom"), {"items": [_playlist_item("PLdup")]}],
        )

        _, not_found = await youtube_service.fetch_playlists_batched(ids)

        assert "PLdup" not in not_found


class TestVideoNotFoundSemantics:
    """The same defect lived in the video path (#149).

    Videos are partly shielded downstream by two-cycle confirmation
    (``_mark_video_deleted``), so a single bad run does not flip them — but a
    persistent auth failure across two runs would, and the confirmation logic
    is not a licence for this method to invent absences.

    These patch ``get_video_details`` rather than the transport, because the
    subject here is the batching loop's arithmetic, not video response parsing.
    """

    async def test_a_failed_batch_reports_nothing_as_not_found(
        self, youtube_service: YouTubeService
    ) -> None:
        youtube_service.get_video_details = AsyncMock(  # type: ignore[method-assign]
            side_effect=RuntimeError("token expired")
        )

        videos, not_found = await youtube_service.fetch_videos_batched(
            ["vid1", "vid2", "vid3"]
        )

        assert videos == []
        assert not_found == set()

    async def test_absent_ids_are_still_reported(
        self, youtube_service: YouTubeService
    ) -> None:
        """Containment must not suppress genuine absences."""
        found = MagicMock()
        found.id = "vid1"
        youtube_service.get_video_details = AsyncMock(  # type: ignore[method-assign]
            return_value=[found]
        )

        videos, not_found = await youtube_service.fetch_videos_batched(["vid1", "vid2"])

        assert len(videos) == 1
        assert not_found == {"vid2"}


class TestBatching:
    """Splitting, capping, and that every batch is actually issued."""

    async def test_ids_are_split_into_batches_of_fifty(
        self, youtube_service: YouTubeService
    ) -> None:
        ids = [f"PL{i:04d}" for i in range(120)]
        calls = _respond_with(
            youtube_service, [{"items": []}, {"items": []}, {"items": []}]
        )

        await youtube_service.fetch_playlists_batched(ids)

        assert calls.await_count == 3, "120 ids at 50 per batch is three requests"

    async def test_batch_size_is_capped_at_the_api_limit(
        self, youtube_service: YouTubeService
    ) -> None:
        """A caller asking for 100 per batch must not produce a 100-id request.

        ``get_playlist_details`` raises ValidationError above 50, which the
        batching loop would swallow as a failed batch — so an uncapped size
        would silently return nothing rather than erroring.
        """
        ids = [f"PL{i:04d}" for i in range(100)]
        calls = _respond_with(youtube_service, [{"items": []}, {"items": []}])

        playlists, not_found = await youtube_service.fetch_playlists_batched(
            ids, batch_size=100
        )

        assert calls.await_count == 2
        assert playlists == []
        assert not_found == set(ids), "a capped batch still answers about its ids"

    async def test_a_partial_final_batch_is_issued(
        self, youtube_service: YouTubeService
    ) -> None:
        ids = [f"PL{i:04d}" for i in range(60)]
        calls = _respond_with(youtube_service, [{"items": []}, {"items": []}])

        await youtube_service.fetch_playlists_batched(ids)

        assert calls.await_count == 2

    async def test_empty_input_issues_no_request(
        self, youtube_service: YouTubeService
    ) -> None:
        calls = _respond_with(youtube_service, [])

        playlists, not_found = await youtube_service.fetch_playlists_batched([])

        assert playlists == []
        assert not_found == set()
        assert calls.await_count == 0


class TestResponseHandling:
    """Aggregation across batches and tolerance of imperfect items."""

    async def test_results_from_every_batch_are_aggregated(
        self, youtube_service: YouTubeService
    ) -> None:
        ids = [f"PL{i:04d}" for i in range(50)] + ["PLlast"]
        _respond_with(
            youtube_service,
            [
                {"items": [_playlist_item(f"PL{i:04d}") for i in range(50)]},
                {"items": [_playlist_item("PLlast")]},
            ],
        )

        playlists, not_found = await youtube_service.fetch_playlists_batched(ids)

        assert len(playlists) == 51
        assert not_found == set()

    async def test_all_found_yields_an_empty_not_found_set(
        self, youtube_service: YouTubeService
    ) -> None:
        _respond_with(
            youtube_service,
            [{"items": [_playlist_item("PLa"), _playlist_item("PLb")]}],
        )

        playlists, not_found = await youtube_service.fetch_playlists_batched(
            ["PLa", "PLb"]
        )

        assert len(playlists) == 2
        assert not_found == set()

    async def test_an_unparseable_item_does_not_lose_the_rest_of_the_batch(
        self, youtube_service: YouTubeService
    ) -> None:
        """A malformed item is skipped and reported missing, not fatal."""
        _respond_with(
            youtube_service,
            [{"items": [_playlist_item("PLgood"), {"id": None, "snippet": None}]}],
        )

        playlists, not_found = await youtube_service.fetch_playlists_batched(
            ["PLgood", "PLbad"]
        )

        assert [p.id for p in playlists] == ["PLgood"]
        assert "PLbad" in not_found

    async def test_privacy_status_is_preserved(
        self, youtube_service: YouTubeService
    ) -> None:
        """Private playlists are ordinary results, not a missing-data signal."""
        _respond_with(youtube_service, [{"items": [_playlist_item("PLprivate")]}])

        playlists, not_found = await youtube_service.fetch_playlists_batched(
            ["PLprivate"]
        )

        assert playlists[0].status is not None
        assert playlists[0].status.privacy_status == "private"
        assert not_found == set()

    async def test_item_count_is_preserved(
        self, youtube_service: YouTubeService
    ) -> None:
        _respond_with(youtube_service, [{"items": [_playlist_item("PLcount")]}])

        playlists, _ = await youtube_service.fetch_playlists_batched(["PLcount"])

        assert playlists[0].content_details is not None
        assert playlists[0].content_details.item_count == 10
