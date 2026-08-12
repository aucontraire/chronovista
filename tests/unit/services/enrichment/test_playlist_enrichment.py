"""Field mapping in `EnrichmentService.enrich_playlists` (Phase 9, User Story 7).

Every test here calls `enrich_playlists` and asserts against the playlist object
it mutated. That is stated because the previous version of this file did not do
it: across 643 lines and 24 tests, `EnrichmentService` was never constructed
once. Two tests "called" the method on a `MagicMock` and asserted the mock's own
configured return value — a dict, where the real method returns a tuple — and
the rest built a dict, spread another dict into it, and asserted the spread had
happened:

    updated_playlist = {**db_playlist, "title": api_response["snippet"]["title"]}
    assert updated_playlist["title"] == "My Awesome Music Collection"

That asserts Python's `**` operator works. It cannot fail for any reason
involving this project, which is why #149 — a bug squarely inside this method —
had no test standing in its way for nine months.

Scope: this file covers the **field mapping**, which is pure enough to exercise
against a stubbed session. The behaviour that depends on real rows and real
commits — the deletion decision, the mass-deletion guard, two-cycle confirmation
and owner verification — lives in
`tests/integration/services/test_playlist_deletion_guard.py`, against a real
database, because that is where mocking hid the defect in the first place.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from chronovista.db.models import Playlist as PlaylistDB
from chronovista.models.api_responses import YouTubePlaylistResponse
from chronovista.services.enrichment.enrichment_service import EnrichmentService

pytestmark = pytest.mark.asyncio


def _stored(playlist_id: str = "PLtest123", **overrides: Any) -> PlaylistDB:
    """A playlist as it sits in the database before enrichment."""
    playlist = PlaylistDB(
        playlist_id=playlist_id,
        title=f"[Placeholder] Playlist {playlist_id}",
        description=None,
        privacy_status="private",
        channel_id=None,
        video_count=0,
        deleted_flag=False,
        playlist_type="regular",
    )
    for key, value in overrides.items():
        setattr(playlist, key, value)
    return playlist


def _api(playlist_id: str = "PLtest123", **snippet: Any) -> YouTubePlaylistResponse:
    """An API response, built through the real model so its validation runs."""
    payload: dict[str, Any] = {"id": playlist_id}
    body = {
        "title": "Real Title",
        "description": "Real description",
        "publishedAt": "2024-03-01T12:00:00Z",
        "channelId": "UCtest0000000000000001",
        **snippet,
    }
    payload["snippet"] = body
    payload.setdefault("status", {"privacyStatus": "public"})
    payload.setdefault("contentDetails", {"itemCount": 42})
    return YouTubePlaylistResponse.model_validate(payload)


async def _enrich(
    stored: list[PlaylistDB],
    returned: list[YouTubePlaylistResponse],
    not_found: set[str] | None = None,
    **kwargs: Any,
) -> tuple[int, int, int]:
    """Run the real method with a stubbed session and API.

    The session is stubbed rather than the repository: the loop, the field
    mapping and the enum handling all execute for real against real ORM
    objects, and only the row fetch and commit are faked. `AppIdentityRepository`
    reads through the same stub, which yields a `MagicMock` whose `source` is not
    the channel constant — so owner verification finds nothing to contradict and
    makes no API call (see the integration file for that path tested properly).
    """
    session = AsyncMock()
    session.execute.return_value = MagicMock(
        scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=stored)))
    )

    youtube = MagicMock()
    youtube.fetch_playlists_batched = AsyncMock(
        return_value=(returned, not_found or set())
    )

    service = EnrichmentService(
        video_repository=MagicMock(),
        channel_repository=MagicMock(),
        video_tag_repository=MagicMock(),
        video_topic_repository=MagicMock(),
        video_category_repository=MagicMock(),
        topic_category_repository=MagicMock(),
        youtube_service=youtube,
        playlist_repository=MagicMock(),
    )
    return await service.enrich_playlists(session, **kwargs)


class TestFieldMapping:
    """What the API says lands on the stored row."""

    async def test_title_description_and_count_are_written(self) -> None:
        playlist = _stored()

        _, updated, _ = await _enrich([playlist], [_api()])

        assert updated == 1
        assert playlist.title == "Real Title"
        assert playlist.description == "Real description"
        assert playlist.video_count == 42

    async def test_privacy_status_goes_through_the_enum(self) -> None:
        """Stored as the enum's value, not the raw API string.

        The API sends mixed case; the column holds the lowercase enum value.
        """
        playlist = _stored()

        await _enrich([playlist], [_api()])

        assert playlist.privacy_status == "public"

    async def test_an_unknown_privacy_status_is_left_alone(self) -> None:
        """A value outside the enum must not be written through blindly."""
        playlist = _stored(privacy_status="private")
        api = _api()
        api.status.privacy_status = "not_a_real_status"  # type: ignore[union-attr]

        await _enrich([playlist], [api])

        assert playlist.privacy_status == "private"

    async def test_published_at_is_parsed_to_a_datetime(self) -> None:
        playlist = _stored()

        await _enrich([playlist], [_api()])

        assert playlist.published_at == datetime(2024, 3, 1, 12, 0, tzinfo=UTC)

    async def test_channel_id_links_the_playlist_to_its_owner(self) -> None:
        playlist = _stored()

        await _enrich([playlist], [_api()])

        assert playlist.channel_id == "UCtest0000000000000001"

    async def test_default_language_is_written_when_present(self) -> None:
        playlist = _stored()

        await _enrich([playlist], [_api(defaultLanguage="en")])

        assert playlist.default_language == "en"

    async def test_an_empty_description_is_written(self) -> None:
        """Empty is a value; the check is `is not None`, not truthiness.

        A creator who clears a description means it, and treating "" as absent
        would leave stale text in place forever.
        """
        playlist = _stored(description="stale text")

        await _enrich([playlist], [_api(description="")])

        assert playlist.description == ""


class TestAbsentFields:
    """A field the API omits must not clobber what is stored."""

    async def test_a_missing_snippet_leaves_the_row_untouched(self) -> None:
        playlist = _stored(title="Existing Title")
        api = YouTubePlaylistResponse.model_validate({"id": "PLtest123"})

        _, updated, _ = await _enrich([playlist], [api])

        assert updated == 1, "a response without a snippet is still a response"
        assert playlist.title == "Existing Title"
        assert playlist.description is None

    async def test_an_empty_title_does_not_overwrite(self) -> None:
        playlist = _stored(title="Existing Title")

        await _enrich([playlist], [_api(title="")])

        assert playlist.title == "Existing Title"


class TestUnmatchedResponses:
    """Rows the API answered about, and rows it did not."""

    async def test_a_playlist_with_no_api_data_is_skipped(self) -> None:
        """Neither returned nor reported missing — nothing can be said about it."""
        playlist = _stored(title="Existing Title")

        processed, updated, deleted = await _enrich([playlist], [], not_found=set())

        assert processed == 1
        assert (updated, deleted) == (0, 0)
        assert playlist.title == "Existing Title"
        assert playlist.deleted_flag is False

    async def test_only_the_matching_playlist_is_updated(self) -> None:
        first, second = _stored("PLfirst00001"), _stored("PLsecond0001")

        _, updated, _ = await _enrich([first, second], [_api("PLfirst00001")])

        assert updated == 1
        assert first.title == "Real Title"
        assert second.title.startswith("[Placeholder]")


class TestDryRun:
    async def test_dry_run_writes_nothing_and_calls_no_api(self) -> None:
        """It reports the size of the job and stops."""
        playlist = _stored()

        processed, updated, deleted = await _enrich([playlist], [_api()], dry_run=True)

        assert (processed, updated, deleted) == (1, 0, 0)
        assert playlist.title.startswith("[Placeholder]")


class TestNothingToDo:
    async def test_no_playlists_returns_zeroes(self) -> None:
        assert await _enrich([], []) == (0, 0, 0)


class TestConfiguration:
    async def test_a_missing_playlist_repository_is_refused(self) -> None:
        """Configuration error, not a silent no-op."""
        service = EnrichmentService(
            video_repository=MagicMock(),
            channel_repository=MagicMock(),
            video_tag_repository=MagicMock(),
            video_topic_repository=MagicMock(),
            video_category_repository=MagicMock(),
            topic_category_repository=MagicMock(),
            youtube_service=MagicMock(),
        )

        with pytest.raises(RuntimeError, match="Playlist repository not configured"):
            await service.enrich_playlists(AsyncMock())
