"""Tests for the lazy async Neo4j client (Feature 112).

No real graph required: an injected mock driver covers the happy path, and the
unreachable path is simulated by patching the driver factory — exactly the
graceful-degradation seam the client exists to provide.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

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
        driver.session.assert_called_once_with(database="neo4j")

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
        driver.session.assert_called_once_with(database="graph")

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
