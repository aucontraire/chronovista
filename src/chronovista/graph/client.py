"""Lazy async Neo4j client for the dev-scoped connection explorer (Feature 112).

Read-only, lazy, and graceful: the client connects on first use and surfaces an unreachable
graph as :class:`GraphUnavailableError` — never a bare driver exception — whether the graph
is missing or unreachable on first connect, the ``neo4j`` driver is not installed, OR the
connection is lost mid-session (the cached driver is then invalidated so the next call
reconnects). A genuine query error or a server write-rejection is deliberately NOT masked —
it surfaces as itself, so an unguarded write still fails loudly against the read-only guard.
The CLI degrades cleanly and CI never needs a running graph. The ``neo4j`` driver is imported
lazily, so importing this module (or the result models) never requires the package.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from chronovista.config.settings import settings

if TYPE_CHECKING:
    from neo4j import AsyncDriver, AsyncSession
    from neo4j.exceptions import DriverError, Neo4jError

logger = logging.getLogger(__name__)


class GraphUnavailableError(RuntimeError):
    """The Neo4j graph cannot be reached (unreachable, unset, or the driver is absent).

    Callers catch this to degrade gracefully ("graph unavailable") instead of crashing.
    """


def _is_unavailable(exc: Neo4jError | DriverError) -> bool:
    """Whether a driver error means the graph is UNREACHABLE (vs a query / write-guard error).

    The driver's own ``is_retryable()`` is the primary, upgrade-resistant signal: it marks the
    transient connectivity failures — ``ServiceUnavailable``, ``SessionExpired``, and
    ``DatabaseUnavailable`` (the server restarting, the single most likely error after a
    container bounce), plus the routing variants. We then EXCLUDE the two write-path
    transients, because ``is_retryable()`` answers a subtly different question — "could
    retrying this transaction succeed?" — and for ``NotALeader`` / ``ForbiddenOnReadOnlyDatabase``
    the answer is yes (a retry routes elsewhere), yet those are the server REJECTING A WRITE
    under the ``READ_ACCESS`` guard, not the graph being unreachable. Relabelling them as
    "unavailable" (and reconnecting) would disarm that guard — the one diagnostic that outlives
    the AST write-scans. The exclusion is ours to maintain, pinned by
    ``tests/unit/architecture/test_graph_unavailable_classification.py``.

    NOTE: ``is_retryable()`` is borrowed only as a CLASSIFICATION input. The driver does NOT
    auto-retry our auto-commit ``session.run`` calls regardless of its value.
    """
    from neo4j.exceptions import ForbiddenOnReadOnlyDatabase, NotALeader

    return bool(exc.is_retryable()) and not isinstance(
        exc, NotALeader | ForbiddenOnReadOnlyDatabase
    )


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

    async def _invalidate(self) -> None:
        """Drop (and best-effort close) the cached driver so the next call reconnects.

        Used after a mid-session connectivity loss: the pooled connections are dead, so nulling
        the cached driver makes :meth:`_ensure_driver` recreate and re-verify on the next use —
        which is what lets a long-lived caller self-heal after the graph bounces.
        """
        driver, self._driver = self._driver, None
        if driver is not None:
            try:
                await driver.close()
            except (
                Exception
            ):  # pragma: no cover - teardown of a dead driver is best-effort
                logger.debug("error closing invalidated Neo4j driver", exc_info=True)

    async def verify(self) -> None:
        """Eagerly check the graph is reachable; raise :class:`GraphUnavailableError` if not."""
        await self._ensure_driver()

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Yield a read-only async session, connecting lazily.

        A connectivity loss that surfaces WHILE the caller is using the session (e.g. the graph
        bounces mid-query) is caught here and re-raised as :class:`GraphUnavailableError`, with
        the dead driver invalidated so the next call reconnects. A genuine query error or a
        server write-rejection is NOT wrapped — it propagates as itself (see
        :func:`_is_unavailable`).

        Raises
        ------
        GraphUnavailableError
            If the graph cannot be reached on connect, or the connection is lost mid-session.
        """
        from neo4j import READ_ACCESS
        from neo4j.exceptions import DriverError, Neo4jError

        driver = await self._ensure_driver()
        # default_access_mode=READ makes the read-only contract real, not just a docstring:
        # on a cluster it routes to a reader and the server rejects writes — the one guard
        # that survives a future unguarded query, where the test-side Cypher scans cannot.
        sess = driver.session(database=self._database, default_access_mode=READ_ACCESS)
        try:
            try:
                yield sess
            except (Neo4jError, DriverError) as exc:
                if not _is_unavailable(exc):
                    raise  # query error / write-guard rejection — surface as itself (FR-009)
                # FR-015: log the availability loss at WARNING with no traceback, matching the
                # first-connect path — not the CLI catch-all's logger.error(exc_info=True).
                logger.warning(
                    "Neo4j graph became unavailable at %s: %s", self._uri, exc
                )
                await self._invalidate()
                raise GraphUnavailableError(
                    f"lost connection to Neo4j at {self._uri}: {exc}"
                ) from exc
        finally:
            # A failure while tearing down a dead session must never replace the exception we
            # are raising. The driver's own close() swallows errors, but we do not depend on it.
            try:
                await sess.close()
            except (
                Exception
            ):  # pragma: no cover - teardown must not mask the real error
                logger.debug(
                    "error closing Neo4j session during teardown", exc_info=True
                )

    async def close(self) -> None:
        """Close the driver if one was created."""
        if self._driver is not None:
            await self._driver.close()
            self._driver = None
