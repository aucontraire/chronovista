"""Failure handling in Filmot recovery (Feature 065).

Written after coverage measurement showed the systemic-failure paths, the time
limit and the duplicate-record handling were implemented but never exercised —
86%, against a >90% target. Every branch here is a decision about what to
believe when the archive misbehaves, which makes untested exactly the wrong
thing for it to be.

These drive the module's own helpers directly, which is cheap and which is also
how they went wrong: for a while the `FilmotError` cases below mocked a client
shape the real client could not produce. `FilmotClient.fetch_videos` folded
every per-batch error into `unresolved`, so nothing escaped it and `_classify`
was unreachable in production — a rejected credential reached the operator
labelled `rate_limited`, and these tests passed throughout. The client now
raises on 401/403, and `TestTheClientRaisesWhatThisModuleClassifies` pins that
contract so the mocks below cannot drift away from it again.

A test that mocks a collaborator asserts the collaborator's contract as much as
its own subject, and only one of those two is visible in the file.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

import chronovista.services.recovery.filmot_recovery as fr
from chronovista.exceptions import FilmotError
from chronovista.services.recovery.filmot_client import FilmotClient, FilmotVideo

pytestmark = pytest.mark.asyncio


def _video(video_id: str) -> Any:
    v = MagicMock()
    v.video_id = video_id
    v.title = f"https://www.youtube.com/watch?v={video_id}"
    v.channel_id = None
    v.duration = 0
    return v


def _state() -> fr._RunState:
    return fr._RunState(dry_run=False, total_candidates=10)


class TestClassifyingSystemicFailure:
    """Naming the failure is what lets the summary explain itself."""

    @pytest.mark.parametrize(
        ("status", "expected"),
        [
            (401, "credential_rejected"),
            (403, "credential_rejected"),
            (429, "rate_limited"),
            (500, "source_unusable"),
            (None, "source_unusable"),
        ],
    )
    async def test_status_maps_to_a_reason(
        self, status: int | None, expected: str
    ) -> None:
        assert fr._classify(FilmotError("x", status_code=status)) == expected


class TestTheClientRaisesWhatThisModuleClassifies:
    """The seam the mocks in this file assume, asserted against the real client.

    Without this, every `FilmotError` test below is a statement about a mock.
    """

    async def test_a_rejected_credential_escapes_the_client(self) -> None:
        client = FilmotClient(api_key="dead-key")

        with patch.object(
            client,
            "_fetch_batch",
            AsyncMock(side_effect=FilmotError("forbidden", status_code=403)),
        ):
            with pytest.raises(FilmotError) as caught:
                await client.fetch_videos(["v1"])

        assert caught.value.status_code == 403

    @pytest.mark.parametrize("status", [429, 500, None])
    async def test_other_failures_stay_per_batch(self, status: int | None) -> None:
        """Everything else is a fact about one request, not about the run.

        These *are* folded into `unresolved`, and the three-batch streak is
        what escalates them — so the streak's reason is an inference, and only
        the credential case is ever known.
        """
        client = FilmotClient(api_key="k")

        with patch.object(
            client,
            "_fetch_batch",
            AsyncMock(side_effect=FilmotError("nope", status_code=status)),
        ):
            found, unresolved = await client.fetch_videos(["v1"])

        assert found == []
        assert unresolved == {"v1"}


class TestSystemicVersusIsolated:
    """FR-018b. One batch failing is not the source refusing the run."""

    async def test_a_client_error_ends_the_run(self) -> None:
        """A rejected credential says nothing about any video, and will say
        nothing about the next batch either."""
        client = MagicMock()
        client.fetch_videos = AsyncMock(
            side_effect=FilmotError("rejected", status_code=403)
        )

        with pytest.raises(fr._SystemicFailure) as caught:
            await fr._process_batch(AsyncMock(), client, [_video("v1")], _state())

        assert caught.value.reason == "credential_rejected"

    async def test_two_fully_unresolved_batches_do_not_end_the_run(self) -> None:
        """Two is a bad patch; three is the source refusing us."""
        client = MagicMock()
        client.fetch_videos = AsyncMock(return_value=([], {"v1"}))
        state = _state()

        for _ in range(2):
            await fr._process_batch(AsyncMock(), client, [_video("v1")], state)

        assert state.consecutive_rate_limits == 2
        assert state.unresolved == 2

    async def test_three_fully_unresolved_batches_end_the_run(self) -> None:
        client = MagicMock()
        client.fetch_videos = AsyncMock(return_value=([], {"v1"}))
        state = _state()

        for _ in range(2):
            await fr._process_batch(AsyncMock(), client, [_video("v1")], state)

        with pytest.raises(fr._SystemicFailure) as caught:
            await fr._process_batch(AsyncMock(), client, [_video("v1")], state)
        assert caught.value.reason == "rate_limited"

    async def test_a_successful_batch_resets_the_streak(self) -> None:
        """Otherwise three failures spread across an hour would end a healthy
        run, which is the opposite of the intent."""
        client = MagicMock()
        state = _state()

        client.fetch_videos = AsyncMock(return_value=([], {"v1"}))
        await fr._process_batch(AsyncMock(), client, [_video("v1")], state)
        assert state.consecutive_rate_limits == 1

        client.fetch_videos = AsyncMock(return_value=([], set()))
        await fr._process_batch(AsyncMock(), client, [_video("v2")], state)
        assert state.consecutive_rate_limits == 0

    async def test_a_partially_unresolved_batch_is_not_a_streak(self) -> None:
        """Some answers came back, so the source is not refusing us."""
        client = MagicMock()
        client.fetch_videos = AsyncMock(return_value=([], {"v1"}))
        state = _state()

        await fr._process_batch(
            AsyncMock(), client, [_video("v1"), _video("v2")], state
        )

        assert state.consecutive_rate_limits == 0


class TestUnexpectedRecords:
    """FR-016a. The archive is not expected to do either of these."""

    async def test_a_record_for_an_unrequested_id_is_ignored(self) -> None:
        client = MagicMock()
        client.fetch_videos = AsyncMock(
            return_value=([FilmotVideo(id="never-asked", title="T")], set())
        )
        state = _state()

        await fr._process_batch(AsyncMock(), client, [_video("v1")], state)

        assert state.returned == 0
        assert state.not_held == 1, "v1 was answered for and had no record"

    async def test_duplicates_collapse_to_the_first(self) -> None:
        session = AsyncMock()
        session.scalar = AsyncMock(return_value=None)
        client = MagicMock()
        client.fetch_videos = AsyncMock(
            return_value=(
                [
                    FilmotVideo(id="v1", title="First"),
                    FilmotVideo(id="v1", title="Second"),
                ],
                set(),
            )
        )
        state = _state()

        await fr._process_batch(session, client, [_video("v1")], state)

        assert state.returned == 1


def _client(**kwargs: Any) -> Any:
    client = MagicMock()
    client.is_configured = True
    client.fetch_videos = AsyncMock(**kwargs)
    return client


async def _run(candidates: list[Any], client: Any, **kwargs: Any) -> Any:
    """Drive the real orchestration over a stubbed candidate set."""
    repo = MagicMock()
    repo.get_filmot_candidates = AsyncMock(return_value=candidates)
    with patch.object(fr, "VideoRepository", return_value=repo):
        return await fr.run_filmot_recovery(AsyncMock(), client, **kwargs)


class TestEveryCandidateIsCountedExactlyOnce:
    """The buckets must partition the candidate set.

    This is the feature's reason for existing, one level up: "the archive had
    no record" and "we failed to ask" are different facts. A video counted in
    two buckets is that distinction failing in the direction that looks fine.
    """

    async def test_an_abandoned_batch_is_unresolved_not_unattempted(self) -> None:
        """The batch was asked about. It is not "never reached".

        `submitted` was incremented before the systemic raise and `unresolved`
        after it, while the remainder was measured from the batch's *start* —
        so those 50 videos landed in `submitted` and `not_attempted` both, and
        in `unresolved` not at all.
        """
        candidates = [_video(f"v{i}") for i in range(120)]
        client = _client(side_effect=FilmotError("rejected", status_code=403))

        result = await _run(candidates, client)

        assert result.ended_early == "credential_rejected"
        assert result.submitted == 50
        assert result.unresolved == 50
        assert result.not_attempted == 70
        assert result.unresolved + result.not_attempted == len(candidates)

    async def test_the_time_limit_ends_the_run_and_counts_the_rest(self) -> None:
        """The branch that decides to stop, not just the tally that records it.

        Previously only `end_early` was called directly, so the comparison
        against the limit — the part with an operator-visible consequence —
        was never executed.
        """
        candidates = [_video(f"v{i}") for i in range(120)]
        client = _client(return_value=([], set()))

        # started, batch 1 check, batch 2 check, finalise.
        with patch.object(
            fr.time, "monotonic", side_effect=[0.0, 1.0, 9_999.0, 9_999.0]
        ):
            result = await _run(candidates, client)

        assert result.ended_early == "time_limit"
        assert result.not_attempted == 70, "everything from batch 2 onwards"
        assert result.submitted == 50


class TestRunState:
    async def test_ending_early_counts_the_remainder_as_not_attempted(self) -> None:
        """ "Not attempted" is a third thing, distinct from both "no record"
        and "we failed to ask" — those videos were never even reached."""
        state = _state()

        state.end_early("time_limit", remaining=40)

        result = state.finalise(1.0)
        assert result.ended_early == "time_limit"
        assert result.not_attempted == 40
        assert result.not_held == 0
        assert result.unresolved == 0

    async def test_the_result_is_frozen(self) -> None:
        """A result that can be edited after the fact is not evidence.

        Pinned to `ValidationError`. `pytest.raises(Exception)` passed on any
        exception at all — including an `AttributeError` from a renamed field,
        which would mean the assignment failed for a reason with nothing to do
        with immutability.
        """
        result = _state().finalise(1.0)

        with pytest.raises(ValidationError):
            result.updated = 99  # type: ignore[misc]
