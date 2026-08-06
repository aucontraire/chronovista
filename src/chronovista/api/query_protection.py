"""Shared query protections for API routers: client identity, rate limits, timeouts.

These helpers were duplicated verbatim between ``videos.py`` and
``entity_mentions.py``, differing only in the per-router request limit. A third
router would have copied them again.

Policy this module encodes
--------------------------
**Timeouts apply to every expensive read.** A query with no ceiling can hang
indefinitely and the interface spins with nothing to show. Bounding it converts
an unbounded wait into a definite, reportable failure. This is worth having
regardless of how many people use the application, because the failure mode is
the same for one user as for a thousand.

**Rate limits apply only where the client calls without debouncing.** They are
not blanket protection here. This is a local, single-user application: the
client identifier resolves to ``127.0.0.1`` for every request, so one bucket is
shared by the whole interface, and a blanket limit turns ordinary bursts —
infinite scroll, scan-job polling — into visible 429s. The limiter earns its
place on endpoints the interface calls in an unthrottled loop, where a render
loop or a fast typist can generate real load. A client-side debounce achieves
the same end; either is sufficient, and neither is needed twice.

Applying that rule today: ``/entities/check-duplicate`` fires on every keystroke
with no debounce, so it is limited. ``/entities/search`` is debounced 300 ms in
its hook, so it is not. That asymmetry is deliberate, not an oversight.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Coroutine
from typing import Any, TypeVar

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.exceptions import QueryTimeoutError

logger = logging.getLogger(__name__)

T = TypeVar("T")

RATE_LIMIT_WINDOW_SECONDS = 60
"""Sliding window, in seconds, over which requests are counted."""

QUERY_TIMEOUT_SECONDS = 8
"""Ceiling for a single read query.

Two constraints set this value. It must sit well above the slowest measured
query — 923 ms on the most connected entity — so it fires only on a genuine
hang. And it must sit **below the client's own timeout**, which is
``API_TIMEOUT = 10000`` ms in ``frontend/src/api/config.ts``.

That second constraint is easy to miss. At an equal 10 s the two race, and the
client generally wins: its budget covers the whole round trip while this one
covers the query alone. The user then sees a generic "the server took too long"
instead of a 504 naming the query that hung — the server-side ceiling would be
real but effectively invisible. Raising this above the client's timeout would
disable it entirely for the browser.

If the client timeout changes, this must move with it."""


def get_client_id(request: Request) -> str:
    """Identify the caller for rate-limiting purposes.

    Prefers ``X-Forwarded-For`` so a proxied deployment distinguishes callers.
    On a local install every request resolves to the same loopback address,
    which is why blanket limiting is inappropriate here — see the module
    docstring.

    Parameters
    ----------
    request : Request
        The incoming request.

    Returns
    -------
    str
        Client identifier, or ``"unknown"`` when none can be determined.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def check_rate_limit(
    client_id: str,
    request_counts: dict[str, list[float]],
    rate_limit: int,
) -> tuple[bool, int]:
    """Record this request and report whether the client is over its limit.

    Expires timestamps outside the window, then admits or rejects. Callers own
    the ``request_counts`` mapping, so each endpoint keeps an independent
    budget rather than competing for one.

    Parameters
    ----------
    client_id : str
        Client identifier from :func:`get_client_id`.
    request_counts : dict[str, list[float]]
        Per-client request timestamps. Mutated in place.
    rate_limit : int
        Maximum requests permitted within the window.

    Returns
    -------
    tuple[bool, int]
        ``(is_allowed, retry_after_seconds)``. ``retry_after`` is 0 when
        allowed, and otherwise the whole seconds until a slot frees.
    """
    now = time.time()
    window_start = now - RATE_LIMIT_WINDOW_SECONDS

    request_counts[client_id] = [
        ts for ts in request_counts[client_id] if ts > window_start
    ]

    if len(request_counts[client_id]) >= rate_limit:
        oldest = min(request_counts[client_id])
        retry_after = int(oldest + RATE_LIMIT_WINDOW_SECONDS - now) + 1
        return False, max(1, retry_after)

    request_counts[client_id].append(now)
    return True, 0


async def run_with_timeout(
    work: Coroutine[Any, Any, T],
    *,
    operation: str,
    session: AsyncSession | None = None,
    timeout_seconds: int = QUERY_TIMEOUT_SECONDS,
) -> T:
    """Run *work* under a ceiling, converting a hang into a 504.

    Raises :class:`QueryTimeoutError` rather than returning a response object,
    so the router's RFC 7807 handler formats it like every other error. A
    router that builds its own ``JSONResponse`` here produces a 504 shaped
    differently from its 404s, which clients then have to special-case.

    Parameters
    ----------
    work : Coroutine
        The query to bound. Cancelled if the ceiling is reached.
    operation : str
        Human-readable label naming the query, used in the log line and the
        error detail so a timeout report identifies which query hung.
    session : AsyncSession, optional
        The session the query runs on. Rolled back when the ceiling fires.
        Cancelling a query mid-flight leaves the transaction in a failed state,
        and the next statement on that session raises ``PendingRollbackError``
        rather than the timeout the caller is expecting. Callers that touch the
        session again after a timeout — or that sit inside a broader
        transaction — should pass it. Verified: the pooled connection itself
        recovers cleanly, so this guards the session, not the pool.
    timeout_seconds : int, optional
        Ceiling in seconds (default :data:`QUERY_TIMEOUT_SECONDS`).

    Returns
    -------
    T
        Whatever *work* returned.

    Raises
    ------
    QueryTimeoutError
        The ceiling elapsed first.
    """
    try:
        return await asyncio.wait_for(work, timeout=timeout_seconds)
    except TimeoutError as exc:
        logger.error(
            "Query timeout exceeded (%ds) for operation %s", timeout_seconds, operation
        )
        if session is not None:
            await session.rollback()
        raise QueryTimeoutError(
            message=(
                f"Query timeout exceeded. Maximum query time is "
                f"{timeout_seconds} seconds."
            ),
            details={"timeout_seconds": timeout_seconds, "operation": operation},
        ) from exc
