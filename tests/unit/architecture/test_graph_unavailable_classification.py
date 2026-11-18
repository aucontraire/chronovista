"""Architecture invariant: graph-unavailability = ``is_retryable()`` MINUS the write-path
transients — and the guard pins OUR predicate, not the driver's.

The client treats a mid-session driver error as "graph unavailable" (wrap as
``GraphUnavailableError`` + invalidate the driver + reconnect) iff ``_is_unavailable(exc)`` is
True. That predicate is ``exc.is_retryable()`` with ``NotALeader`` / ``ForbiddenOnReadOnlyDatabase``
excluded: ``is_retryable()`` answers "could retrying this transaction succeed?" — which is True
for those two as well (a retry routes to another cluster member), yet they are the server
REJECTING A WRITE under the ``READ_ACCESS`` guard, not the graph being unreachable. Masking a
write-rejection as "unavailable" would disarm that guard.

Mutation-verified, no DB, no graph:
  - This guard asserts on ``_is_unavailable`` — the function the handler actually calls — NOT on
    the driver's ``is_retryable()``. A guard pinned to ``is_retryable()`` would pass VACUOUSLY:
    it returns True for ``NotALeader``, the opposite of what the handler must do, so the
    exclusion list could rot undetected (same shape as a vacuous invariant).
  - Drop an entry from the ``_WRITE_REJECTION`` tuple in ``client.py`` and the two write-path
    cases flip to True → this test goes red.
  - A ``neo4j`` upgrade that moved a class's ``is_retryable()`` flips a pinned case red too —
    the cross-version protection (classification measured identical in the locked 5.28.8 and the
    locally-installed 6.4.1 at build time).
"""

from __future__ import annotations

import pytest
from neo4j.exceptions import (
    ConfigurationError,
    CypherSyntaxError,
    DatabaseUnavailable,
    ForbiddenOnReadOnlyDatabase,
    NotALeader,
    ResultConsumedError,
    ServiceUnavailable,
    SessionExpired,
)

from chronovista.graph.client import _is_unavailable

# Connectivity losses → the graph is genuinely unreachable (wrap + invalidate + reconnect).
_UNAVAILABLE = [ServiceUnavailable, SessionExpired, DatabaseUnavailable]

# NOT the graph being down → must surface as themselves, never be relabelled "unavailable".
_NOT_UNAVAILABLE = [
    NotALeader,  # write-path transient: the READ_ACCESS guard firing, not an outage
    ForbiddenOnReadOnlyDatabase,  # same — the case a raw is_retryable() split would have missed
    CypherSyntaxError,  # a query bug (FR-009); the graph is up
    ConfigurationError,  # permanent (bad URI/auth) — wrapping it would reconnect-loop forever
    ResultConsumedError,  # a bug in OUR repo code, not the graph
]


@pytest.mark.parametrize("exc_type", _UNAVAILABLE)
def test_connectivity_errors_classify_as_unavailable(
    exc_type: type[Exception],
) -> None:
    assert _is_unavailable(exc_type("x")) is True


@pytest.mark.parametrize("exc_type", _NOT_UNAVAILABLE)
def test_query_and_write_guard_errors_do_not_classify_as_unavailable(
    exc_type: type[Exception],
) -> None:
    assert _is_unavailable(exc_type("x")) is False


def test_write_rejections_are_retryable_yet_excluded() -> None:
    # The exclusion earns its keep: these ARE is_retryable()==True, so only the explicit
    # exclusion keeps them out of the unavailable set. If is_retryable() ever reads False here,
    # the driver changed (the exclusion became dead weight); if _is_unavailable reads True, the
    # exclusion rotted and the READ_ACCESS write guard is disarmed.
    for exc_type in (NotALeader, ForbiddenOnReadOnlyDatabase):
        exc = exc_type("x")
        assert exc.is_retryable() is True
        assert _is_unavailable(exc) is False
