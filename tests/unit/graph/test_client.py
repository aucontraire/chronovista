"""Tests for the lazy async Neo4j client (Feature 112).

No real graph required: an injected mock driver covers the happy path, and the
unreachable path is simulated by patching the driver factory — exactly the
graceful-degradation seam the client exists to provide.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from neo4j import READ_ACCESS
from neo4j.exceptions import (
    CypherSyntaxError,
    DatabaseUnavailable,
    ForbiddenOnReadOnlyDatabase,
    ServiceUnavailable,
)

from chronovista.graph import GraphUnavailableError, Neo4jClient

pytestmark = pytest.mark.asyncio


def _mock_driver() -> tuple[MagicMock, AsyncMock]:
    sess = AsyncMock()
    sess.close = AsyncMock()
    driver = MagicMock()
    driver.session = MagicMock(return_value=sess)
    driver.close = AsyncMock()
    return driver, sess


class TestNeo4jClient:
    async def test_injected_driver_session_yields_and_closes(self) -> None:
        driver, sess = _mock_driver()
        client = Neo4jClient(uri="bolt://x", user="u", password="p", driver=driver)
        async with client.session() as opened:
            assert opened is sess
        sess.close.assert_awaited_once()
        # Sessions are opened READ-only (FR-008 enforcement, not just the test-side scan).
        driver.session.assert_called_once_with(
            database="neo4j", default_access_mode=READ_ACCESS
        )

    async def test_session_closes_even_when_caller_raises(self) -> None:
        driver, sess = _mock_driver()
        client = Neo4jClient(uri="bolt://x", user="u", password="p", driver=driver)
        with pytest.raises(RuntimeError):
            async with client.session():
                raise RuntimeError("boom")
        sess.close.assert_awaited_once()

    async def test_injected_driver_is_not_reconnected(self) -> None:
        driver, _ = _mock_driver()
        client = Neo4jClient(uri="bolt://x", user="u", password="p", driver=driver)
        await client.verify()
        # An injected driver must never be probed with verify_connectivity.
        driver.verify_connectivity.assert_not_called()

    async def test_injected_driver_is_reused_across_sessions(self) -> None:
        driver, _ = _mock_driver()
        client = Neo4jClient(uri="bolt://x", user="u", password="p", driver=driver)
        async with client.session():
            pass
        async with client.session():
            pass
        # Same driver, two sessions — the client did not reconnect.
        assert driver.session.call_count == 2

    async def test_custom_database_is_used(self) -> None:
        driver, _ = _mock_driver()
        client = Neo4jClient(
            uri="bolt://x", user="u", password="p", database="graph", driver=driver
        )
        async with client.session():
            pass
        driver.session.assert_called_once_with(
            database="graph", default_access_mode=READ_ACCESS
        )

    async def test_unreachable_wraps_and_closes_the_failed_driver(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import neo4j

        fake = MagicMock()
        fake.verify_connectivity = AsyncMock(side_effect=OSError("connection refused"))
        fake.close = AsyncMock()
        monkeypatch.setattr(neo4j.AsyncGraphDatabase, "driver", lambda *a, **k: fake)
        client = Neo4jClient(uri="bolt://localhost:1", user="u", password="p")
        with pytest.raises(GraphUnavailableError):
            await client.verify()
        # H2: driver() already allocated a pool; it must be closed on the failure path.
        fake.close.assert_awaited_once()

    async def test_close_is_safe_before_connect_and_idempotent(self) -> None:
        # close() before any connect is a no-op (no driver was created yet).
        await Neo4jClient(uri="bolt://x", user="u", password="p").close()
        # after connect, close() closes exactly once; a second close() is a no-op.
        driver, _ = _mock_driver()
        client = Neo4jClient(uri="bolt://x", user="u", password="p", driver=driver)
        await client.verify()
        await client.close()
        await client.close()
        driver.close.assert_awaited_once()

    async def test_from_settings_does_not_connect_on_construct(self) -> None:
        client = Neo4jClient.from_settings()
        assert client._driver is None  # lazy — no driver/connection on construction


class TestMidSessionConnectivityLoss:
    """A graph that drops AFTER the driver is cached: availability loss must be wrapped and the
    driver invalidated, while a query error or a write-guard rejection must surface as itself.
    """

    @pytest.mark.parametrize("exc_type", [ServiceUnavailable, DatabaseUnavailable])
    async def test_availability_loss_wraps_and_invalidates(
        self, exc_type: type[Exception]
    ) -> None:
        # DatabaseUnavailable is the Neo4j-restarting window (Bolt up, db not started) — the
        # single most likely error after a container bounce, and the one a ServiceUnavailable-
        # only list would miss.
        driver, sess = _mock_driver()
        client = Neo4jClient(uri="bolt://x", user="u", password="p", driver=driver)
        with pytest.raises(GraphUnavailableError):
            async with client.session():
                raise exc_type("graph went away")
        sess.close.assert_awaited_once()
        driver.close.assert_awaited_once()  # the dead driver was invalidated
        assert client._driver is None  # so the next call reconnects + re-verifies

    async def test_query_error_is_not_wrapped(self) -> None:
        driver, sess = _mock_driver()
        client = Neo4jClient(uri="bolt://x", user="u", password="p", driver=driver)
        # A bad query is "graph up, query broken" (FR-009) — it must stay itself, not become
        # GraphUnavailableError, and must NOT invalidate the (healthy) driver.
        with pytest.raises(CypherSyntaxError):
            async with client.session():
                raise CypherSyntaxError("bad cypher")
        sess.close.assert_awaited_once()
        driver.close.assert_not_awaited()
        assert client._driver is driver

    async def test_write_rejection_is_not_relabelled_unavailable(self) -> None:
        # The load-bearing case: ForbiddenOnReadOnlyDatabase is is_retryable()==True, but it is
        # the READ_ACCESS write-guard firing, not an outage. It must surface as itself so the
        # unguarded-write diagnostic survives — never be masked as "graph unavailable".
        driver, sess = _mock_driver()
        client = Neo4jClient(uri="bolt://x", user="u", password="p", driver=driver)
        with pytest.raises(ForbiddenOnReadOnlyDatabase):
            async with client.session():
                raise ForbiddenOnReadOnlyDatabase("no writes on a read replica")
        driver.close.assert_not_awaited()  # not invalidated
        assert client._driver is driver

    async def test_session_close_failure_does_not_mask_the_real_error(self) -> None:
        # Teardown of a dead session must not replace the exception being raised. We guard the
        # finally rather than depend on the driver's own close() swallowing.
        driver, sess = _mock_driver()
        sess.close = AsyncMock(side_effect=RuntimeError("close blew up"))
        client = Neo4jClient(uri="bolt://x", user="u", password="p", driver=driver)
        with pytest.raises(GraphUnavailableError):
            async with client.session():
                raise ServiceUnavailable("gone")
