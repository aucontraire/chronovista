"""Tests for the shared query protections (issue #173).

These helpers were duplicated between two routers. The tests that matter are
the ones pinning the *policy* the module encodes, not just the arithmetic:
a timeout must raise the project's error type rather than return a bespoke
response, and the limiter must expire its window rather than count forever.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from unittest.mock import MagicMock

import pytest

from chronovista.api.query_protection import (
    QUERY_TIMEOUT_SECONDS,
    RATE_LIMIT_WINDOW_SECONDS,
    check_rate_limit,
    get_client_id,
    run_with_timeout,
)
from chronovista.exceptions import QueryTimeoutError


def _request(*, forwarded: str | None = None, host: str | None = "127.0.0.1"):  # type: ignore[no-untyped-def]
    req = MagicMock()
    req.headers = {"x-forwarded-for": forwarded} if forwarded else {}
    req.client = MagicMock(host=host) if host is not None else None
    return req


class TestGetClientId:
    def test_prefers_the_forwarded_header(self) -> None:
        assert (
            get_client_id(_request(forwarded="203.0.113.7, 10.0.0.1")) == "203.0.113.7"
        )

    def test_falls_back_to_the_peer_address(self) -> None:
        assert get_client_id(_request()) == "127.0.0.1"

    def test_reports_unknown_rather_than_raising(self) -> None:
        """A missing client must not turn into a 500 on a read path."""
        assert get_client_id(_request(host=None)) == "unknown"


class TestCheckRateLimit:
    def test_admits_up_to_the_limit_then_rejects(self) -> None:
        counts: dict[str, list[float]] = defaultdict(list)
        for _ in range(3):
            allowed, retry = check_rate_limit("c", counts, 3)
            assert allowed and retry == 0
        allowed, retry = check_rate_limit("c", counts, 3)
        assert not allowed
        assert 1 <= retry <= RATE_LIMIT_WINDOW_SECONDS

    def test_expires_timestamps_outside_the_window(self) -> None:
        """Without expiry the limiter would reject forever after one burst."""
        counts: dict[str, list[float]] = defaultdict(list)
        counts["c"] = [1.0, 2.0, 3.0]  # long past
        allowed, retry = check_rate_limit("c", counts, 3)
        assert allowed and retry == 0
        assert counts["c"] == [pytest.approx(counts["c"][0])], "stale entries retained"

    def test_clients_do_not_share_a_budget(self) -> None:
        counts: dict[str, list[float]] = defaultdict(list)
        check_rate_limit("a", counts, 1)
        allowed, _ = check_rate_limit("b", counts, 1)
        assert allowed, "one client's burst must not lock out another"


@pytest.mark.asyncio
class TestRunWithTimeout:
    async def test_returns_the_result_when_it_finishes(self) -> None:
        async def work() -> str:
            return "done"

        assert await run_with_timeout(work(), operation="test") == "done"

    async def test_raises_the_project_error_type_not_a_response(self) -> None:
        """A 504 must flow through the RFC 7807 handler like every other error.

        Returning a bespoke JSONResponse here — as the videos router does —
        produces a 504 shaped differently from the same router's 404s, which
        every client then has to special-case.
        """

        async def slow() -> None:
            await asyncio.sleep(10)

        with pytest.raises(QueryTimeoutError) as exc_info:
            await run_with_timeout(slow(), operation="slow thing", timeout_seconds=0.01)  # type: ignore[arg-type]

        err = exc_info.value
        assert err.status_code == 504
        assert err.details["operation"] == "slow thing"

    async def test_names_the_operation_so_a_timeout_is_diagnosable(self) -> None:
        async def slow() -> None:
            await asyncio.sleep(10)

        with pytest.raises(QueryTimeoutError) as exc_info:
            await run_with_timeout(
                slow(), operation="co-occurring entities", timeout_seconds=0.01  # type: ignore[arg-type]
            )
        assert "co-occurring entities" in str(exc_info.value.details["operation"])

    async def test_default_ceiling_is_the_shared_constant(self) -> None:
        """Callers should not each invent their own budget."""

        async def work() -> int:
            return QUERY_TIMEOUT_SECONDS

        assert await run_with_timeout(work(), operation="test") == 10
