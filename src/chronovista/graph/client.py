"""Lazy async Neo4j client for the dev-scoped connection explorer (Feature 112).

Read-only, lazy, and graceful: the client connects on first use and raises
:class:`GraphUnavailableError` — never a bare driver exception — when the graph is missing,
unreachable, or the ``neo4j`` driver is not installed, so the CLI degrades cleanly and CI
never needs a running graph. The ``neo4j`` driver is imported lazily, so importing this
module (or the result models) never requires the package.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from chronovista.config.settings import settings

if TYPE_CHECKING:
    from neo4j import AsyncDriver, AsyncSession

logger = logging.getLogger(__name__)


class GraphUnavailableError(RuntimeError):
    """The Neo4j graph cannot be reached (unreachable, unset, or the driver is absent).

    Callers catch this to degrade gracefully ("graph unavailable") instead of crashing.
    """


class Neo4jClient:
    """A lazily-connecting, read-only async Neo4j client.

    The driver is created on the first :meth:`session` / :meth:`verify` call and reused; any
    connection failure surfaces as :class:`GraphUnavailableError`. Pass ``driver`` to inject
    a (mock) driver in tests and skip the real connection.

    Parameters
    ----------
    uri, user, password : str
        Bolt connection settings.
    database : str
        The Neo4j database name (default ``neo4j``).
    driver : AsyncDriver or None
        An injected driver (tests); when ``None`` the real driver is created lazily on first use.
    """

    def __init__(
        self,
        *,
        uri: str,
        user: str,
        password: str,
        database: str = "neo4j",
        driver: AsyncDriver | None = None,
    ) -> None:
        self._uri = uri
        self._user = user
        self._password = password
        self._database = database
        self._driver: AsyncDriver | None = driver

    @classmethod
    def from_settings(cls) -> Neo4jClient:
        """Build a client from app settings (``NEO4J_URI`` / ``NEO4J_USER`` / ``NEO4J_PWD``)."""
        return cls(
            uri=settings.neo4j_uri,
            user=settings.neo4j_user,
            password=settings.neo4j_password,
        )

    async def _ensure_driver(self) -> AsyncDriver:
        if self._driver is not None:
            return self._driver
        try:
            from neo4j import AsyncGraphDatabase
        except ImportError as exc:  # pragma: no cover - neo4j is a declared dependency
            raise GraphUnavailableError("the 'neo4j' driver is not installed") from exc
        driver = AsyncGraphDatabase.driver(self._uri, auth=(self._user, self._password))
        try:
            await driver.verify_connectivity()
        except Exception as exc:
            # driver() already allocated a connection pool; close it before bailing out so
            # the graceful-degradation path (which runs every time the graph is down) can't
            # leak a pool on a long-lived, retrying process.
            await driver.close()
            # FR-015: log the unavailable event with diagnostic context (the target URI and
            # the driver error) — never library content; the URI is configuration, not data.
            logger.warning("Neo4j graph unavailable at %s: %s", self._uri, exc)
            raise GraphUnavailableError(
                f"cannot reach Neo4j at {self._uri}: {exc}"
            ) from exc
        self._driver = driver
        return driver

    async def verify(self) -> None:
        """Eagerly check the graph is reachable; raise :class:`GraphUnavailableError` if not."""
        await self._ensure_driver()

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Yield a read-only async session, connecting lazily.

        Raises
        ------
        GraphUnavailableError
            If the graph cannot be reached.
        """
        from neo4j import READ_ACCESS

        driver = await self._ensure_driver()
        # default_access_mode=READ makes the read-only contract real, not just a docstring:
        # on a cluster it routes to a reader and the server rejects writes — the one guard
        # that survives a future unguarded query, where the test-side Cypher scans cannot.
        sess = driver.session(database=self._database, default_access_mode=READ_ACCESS)
        try:
            yield sess
        finally:
            await sess.close()

    async def close(self) -> None:
        """Close the driver if one was created."""
        if self._driver is not None:
            await self._driver.close()
            self._driver = None
