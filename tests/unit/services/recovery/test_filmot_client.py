"""Tests for the Filmot metadata client.

Every test drives `FilmotClient` itself, patching only `httpx.AsyncClient.get`,
so the batching, retry policy, parsing and the found/unresolved split all run
for real. Two sibling test files in this repository were rewritten this month
for asserting against locally-built objects instead (#221, #225); this one is
written the other way from the start.

The behaviour under most scrutiny is the found/unresolved split. A batch that
fails to complete must not report its ids as "Filmot does not have these" —
that conflation is exactly the defect that hid 288 playlists in #149.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from chronovista.exceptions import FilmotError
from chronovista.services.recovery.filmot_client import FilmotClient, FilmotVideo

pytestmark = pytest.mark.asyncio


def _record(video_id: str, **overrides: Any) -> dict[str, Any]:
    """A record in the shape Filmot actually returns (verified 2026-08-12)."""
    return {
        "id": video_id,
        "uploaddate": "2009-10-25",
        "duration": 214,
        "title": f"Title {video_id}",
        "channelid": "UCuAXFkgsw1L7xaCfnd5JJOw",
        "channelname": "Some Channel",
        **overrides,
    }


def _client() -> FilmotClient:
    """A configured client with the rate limiter effectively disabled.

    The limiter is real code and correct at its default, but a 1 req/s ceiling
    would add a second per batch to the suite. It is exercised for behaviour in
    the CDX client's own tests.
    """
    return FilmotClient(api_key="test-key", requests_per_second=10_000.0)


def _ok(payload: Any) -> httpx.Response:
    return httpx.Response(200, json=payload)


class TestConfiguration:
    async def test_an_unset_key_reports_unconfigured(self) -> None:
        assert FilmotClient(api_key="").is_configured is False

    async def test_a_set_key_reports_configured(self) -> None:
        assert FilmotClient(api_key="k").is_configured is True

    async def test_fetching_without_a_key_raises_rather_than_requesting(
        self,
    ) -> None:
        """An optional source with no key is unavailable, not silently empty.

        Returning ``([], set())`` would look identical to "Filmot has nothing
        for these", which is a different and much worse claim.
        """
        with pytest.raises(FilmotError, match="No Filmot API key"):
            await FilmotClient(api_key="").fetch_videos(["abc"])


class TestFoundAndUnresolved:
    async def test_records_are_returned_for_ids_filmot_has(self) -> None:
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as get:
            get.return_value = _ok([_record("vid1")])
            found, unresolved = await _client().fetch_videos(["vid1"])

        assert [v.video_id for v in found] == ["vid1"]
        assert unresolved == set()

    async def test_an_id_filmot_lacks_is_simply_absent(self) -> None:
        """Absent from ``found``, and NOT reported as unresolved.

        Unresolved means "we failed to ask", not "the answer was no".
        """
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as get:
            get.return_value = _ok([_record("vid1")])
            found, unresolved = await _client().fetch_videos(["vid1", "vid2"])

        assert [v.video_id for v in found] == ["vid1"]
        assert (
            unresolved == set()
        ), "an id the API answered about and did not have is not unresolved"

    async def test_a_failed_batch_reports_its_ids_unresolved(self) -> None:
        """#149's lesson, applied before the bug can happen here.

        Uses 404 rather than 403. Both raise without retrying, so 403 read as a
        convenient stand-in for "this batch failed" — but 403 means the archive
        rejected the credential, which is a condition of the *run*: it will
        recur on every remaining batch, and containing it made a dead key
        indistinguishable from a timeout. See
        `TestARejectedCredentialIsNotContained`.
        """
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as get:
            get.return_value = httpx.Response(404)
            found, unresolved = await _client().fetch_videos(["vid1", "vid2"])

        assert found == []
        assert unresolved == {"vid1", "vid2"}

    async def test_a_failed_batch_does_not_taint_a_successful_one(self) -> None:
        """Containment must not become suppression."""
        ids = [f"v{i:03d}" for i in range(50)] + ["late1"]

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as get:
            get.side_effect = [httpx.Response(404), _ok([_record("late1")])]
            found, unresolved = await _client().fetch_videos(ids)

        assert [v.video_id for v in found] == ["late1"]
        assert unresolved == set(ids[:50])


class TestARejectedCredentialIsNotContained:
    """The one failure that is about the run rather than about a batch.

    Every other failure is contained and reported per-id, which is right: a
    timeout says nothing about the videos it failed to ask about. A rejected
    credential says nothing about them either — but it also guarantees the next
    batch will fail, so containing it meant the run issued every remaining
    request at one per second and then reported `rate_limited`. An operator was
    told to wait out a limit that did not exist instead of rotating a dead key.
    """

    @pytest.mark.parametrize("status", [401, 403])
    async def test_it_escapes_the_client(self, status: int) -> None:
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as get:
            get.return_value = httpx.Response(status)

            with pytest.raises(FilmotError) as caught:
                await _client().fetch_videos(["vid1", "vid2"])

        assert caught.value.status_code == status

    async def test_it_stops_the_run_rather_than_trying_later_batches(self) -> None:
        """The cost of containing it: 1 request/second, all of them doomed."""
        ids = [f"v{i:03d}" for i in range(50)] + ["late1"]

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as get:
            get.side_effect = [httpx.Response(403), _ok([_record("late1")])]

            with pytest.raises(FilmotError):
                await _client().fetch_videos(ids)

        assert get.await_count == 1, "a second batch was attempted after a dead key"


class TestBatching:
    async def test_ids_are_split_into_batches_of_fifty(self) -> None:
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as get:
            get.return_value = _ok([])
            await _client().fetch_videos([f"v{i:03d}" for i in range(120)])

        sizes = [
            len(call.kwargs["params"]["id"].split(",")) for call in get.call_args_list
        ]
        assert sizes == [50, 50, 20]

    async def test_duplicate_ids_are_collapsed(self) -> None:
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as get:
            get.return_value = _ok([])
            await _client().fetch_videos(["a", "b", "a", "b"])

        assert get.call_args_list[0].kwargs["params"]["id"] == "a,b"

    async def test_an_empty_list_issues_no_request(self) -> None:
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as get:
            assert await _client().fetch_videos([]) == ([], set())

        get.assert_not_awaited()


class TestTheRequestItself:
    """What actually goes on the wire.

    Added after mutation testing: with these absent, the client could ship
    unauthenticated, un-rate-limited and pointed at the wrong host with all
    24 other tests green. A mocked transport answers whatever you ask it,
    which makes *what you asked* the thing worth asserting.
    """

    async def test_the_api_key_is_sent(self) -> None:
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as get:
            get.return_value = _ok([])
            await _client().fetch_videos(["vid1"])

        assert get.call_args_list[0].kwargs["params"]["key"] == "test-key"

    async def test_the_documented_endpoint_is_used(self) -> None:
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as get:
            get.return_value = _ok([])
            await _client().fetch_videos(["vid1"])

        assert get.call_args_list[0].args[0] == "https://filmot.com/api/getvideos"

    async def test_the_client_identifies_itself(self) -> None:
        """A named User-Agent is the minimum courtesy to a small archive."""
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as get:
            get.return_value = _ok([])
            await _client().fetch_videos(["vid1"])

        agent = get.call_args_list[0].kwargs["headers"]["User-Agent"]
        assert agent.startswith("chronovista/")

    async def test_every_batch_passes_through_the_rate_limiter(self) -> None:
        """Filmot publishes no limits, so ours is the only one there is.

        Asserted against the limiter rather than wall-clock time, so the test
        stays fast and does not flake on a loaded machine.
        """
        client = _client()
        with (
            patch("httpx.AsyncClient.get", new_callable=AsyncMock) as get,
            patch.object(client._limiter, "acquire", new_callable=AsyncMock) as acquire,
        ):
            get.return_value = _ok([])
            await client.fetch_videos([f"v{i:03d}" for i in range(120)])

        assert acquire.await_count == 3, "one acquisition per batch, not per id"


class TestParsing:
    async def test_fields_are_mapped_from_the_api_names(self) -> None:
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as get:
            get.return_value = _ok([_record("vid1")])
            found, _ = await _client().fetch_videos(["vid1"])

        video = found[0]
        assert video.title == "Title vid1"
        assert video.channel_id == "UCuAXFkgsw1L7xaCfnd5JJOw"
        assert video.channel_name == "Some Channel"
        assert video.upload_date == "2009-10-25"
        assert video.duration == 214

    async def test_a_stringly_typed_duration_is_coerced(self) -> None:
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as get:
            get.return_value = _ok([_record("vid1", duration="214")])
            found, _ = await _client().fetch_videos(["vid1"])

        assert found[0].duration == 214

    async def test_a_zero_duration_becomes_none(self) -> None:
        """Filmot uses 0 for "unknown"; writing it would be confidently wrong."""
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as get:
            get.return_value = _ok([_record("vid1", duration=0)])
            found, _ = await _client().fetch_videos(["vid1"])

        assert found[0].duration is None

    async def test_blank_strings_become_none(self) -> None:
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as get:
            get.return_value = _ok([_record("vid1", title="", channelid="   ")])
            found, _ = await _client().fetch_videos(["vid1"])

        assert found[0].title is None
        assert found[0].channel_id is None

    async def test_one_bad_record_does_not_lose_the_batch(self) -> None:
        """A record with no id is unusable; the other rows are not."""
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as get:
            get.return_value = _ok([{"title": "no id"}, _record("vid2")])
            found, unresolved = await _client().fetch_videos(["vid1", "vid2"])

        assert [v.video_id for v in found] == ["vid2"]
        assert unresolved == set()

    async def test_a_non_list_body_is_an_error_not_an_empty_result(self) -> None:
        """A shape change must surface, never read as "Filmot has nothing"."""
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as get:
            get.return_value = _ok({"error": "bad key"})
            found, unresolved = await _client().fetch_videos(["vid1"])

        assert found == []
        assert unresolved == {"vid1"}

    async def test_a_non_json_body_is_an_error(self) -> None:
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as get:
            get.return_value = httpx.Response(200, text="<html>nope</html>")
            found, unresolved = await _client().fetch_videos(["vid1"])

        assert found == []
        assert unresolved == {"vid1"}


class TestRetries:
    async def test_a_server_error_is_retried_then_gives_up(self) -> None:
        with (
            patch("httpx.AsyncClient.get", new_callable=AsyncMock) as get,
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            get.return_value = httpx.Response(503)
            found, unresolved = await _client().fetch_videos(["vid1"])

        assert get.await_count == 4, "one attempt plus three retries"
        assert found == []
        assert unresolved == {"vid1"}

    async def test_a_transient_error_that_recovers_succeeds(self) -> None:
        with (
            patch("httpx.AsyncClient.get", new_callable=AsyncMock) as get,
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            get.side_effect = [httpx.Response(503), _ok([_record("vid1")])]
            found, unresolved = await _client().fetch_videos(["vid1"])

        assert [v.video_id for v in found] == ["vid1"]
        assert unresolved == set()

    async def test_rate_limiting_honours_retry_after(self) -> None:
        """A stated wait is authoritative in a way a guessed backoff is not."""
        with (
            patch("httpx.AsyncClient.get", new_callable=AsyncMock) as get,
            patch("asyncio.sleep", new_callable=AsyncMock) as sleep,
        ):
            get.side_effect = [
                httpx.Response(429, headers={"Retry-After": "7"}),
                _ok([_record("vid1")]),
            ]
            found, _ = await _client().fetch_videos(["vid1"])

        assert [v.video_id for v in found] == ["vid1"]
        assert 7.0 in [call.args[0] for call in sleep.await_args_list]

    async def test_a_persistent_rate_limit_gives_up_as_unresolved(self) -> None:
        with (
            patch("httpx.AsyncClient.get", new_callable=AsyncMock) as get,
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            get.return_value = httpx.Response(429)
            found, unresolved = await _client().fetch_videos(["vid1"])

        assert found == []
        assert unresolved == {"vid1"}

    async def test_a_malformed_retry_after_falls_back_to_backoff(self) -> None:
        """An unparseable header must not crash the retry path.

        `Retry-After` may legally be an HTTP-date, which this client does not
        parse; treating that as "no guidance" and backing off is correct, while
        letting the ValueError escape would turn a retryable rate limit into a
        hard failure.
        """
        with (
            patch("httpx.AsyncClient.get", new_callable=AsyncMock) as get,
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            get.side_effect = [
                httpx.Response(
                    429, headers={"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}
                ),
                _ok([_record("vid1")]),
            ]
            found, unresolved = await _client().fetch_videos(["vid1"])

        assert [v.video_id for v in found] == ["vid1"]
        assert unresolved == set()

    async def test_a_network_error_is_retried(self) -> None:
        with (
            patch("httpx.AsyncClient.get", new_callable=AsyncMock) as get,
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            get.side_effect = httpx.ConnectError("boom")
            found, unresolved = await _client().fetch_videos(["vid1"])

        assert get.await_count == 4
        assert unresolved == {"vid1"}


class TestModel:
    async def test_video_id_is_required(self) -> None:
        with pytest.raises(ValueError):
            FilmotVideo.model_validate({"title": "no id"})

    async def test_a_record_with_only_an_id_is_valid(self) -> None:
        """Filmot's coverage is uneven; a partial record still gap-fills."""
        video = FilmotVideo.model_validate({"id": "vid1"})

        assert video.video_id == "vid1"
        assert video.title is None
        assert video.duration is None
