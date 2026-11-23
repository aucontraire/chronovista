"""
Transcript proximity computor service (Features 116, 117).

Measures close co-mentions of library entities in transcripts, one
``(video, language)`` scope at a time: the mention x mention self-join is
language-scoped (FR-005), bounded to a 120 s outer window, start-anchored for
cross-segment mentions, and has both F091-excluded endpoints removed. There is NO
eligibility gate (Feature 117): a pair co-mentioned in a single video is measured.

Producers invalidate scopes (``EntityPairProximityRepository.invalidate_proximity_scopes``);
this service claims stale scopes and recomputes each in its own transaction, so a
scope's records and its "current" state are published together (FR-017). The heavy
join and every table write live in :class:`EntityPairProximityRepository`; this
service owns the policy constants and the per-scope orchestration.

The FR-005 language-scoping invariant is NON-NEGOTIABLE. Its single isolatable
clause is :func:`chronovista.repositories.entity_pair_proximity_repository.language_scope_predicate`,
which the mutation-verified guard removes to prove the join fabricates
cross-language records without it.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import random
import uuid
from collections.abc import Callable, Sequence
from enum import Enum
from typing import Literal

from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from chronovista.config.database import db_manager
from chronovista.db.models import ProximityScopeState as ProximityScopeStateDB
from chronovista.models.entity_pair_proximity import (
    DryRunReport,
    DryRunScope,
    FailingScope,
    ProcessSummary,
    ProximityStatusReport,
    ProximityWorkerState,
    ProximityWorkerStatus,
    RebuildOutcome,
    ScopeFilter,
)
from chronovista.repositories.entity_pair_proximity_repository import (
    EntityPairProximityRepository,
)

# The measurement-rule version recorded with every published scope and run. Bump it
# whenever the qualification rule, the self-join shape, or the window policy
# changes: every scope computed under an older version then reads as stale and is
# recomputed (Feature 117, FR-020).
MEASUREMENT_RULE_VERSION = "117.0"

# Records are stored for every close co-mention out to this outer window; the
# 15/30/60 s windows are read-time predicates over it, so the window is not an enum.
OUTER_WINDOW_SECONDS = 120.0

_repo = EntityPairProximityRepository()
logger = logging.getLogger(__name__)


async def recompute_scope(
    session: AsyncSession, state: ProximityScopeStateDB
) -> tuple[int, bool]:
    """Replace a claimed scope's records and publish it, in the caller's transaction.

    ``state`` must be locked by the caller (see ``claim_next_scope``). The revision
    is read here, under that lock, so the publish marks exactly the revision whose
    source data was computed. Returns ``(records_written, published)``.
    """
    revision = state.revision
    written = await _repo.replace_scope_records(
        session,
        video_id=state.video_id,
        language_code=state.language_code,
        outer_window=OUTER_WINDOW_SECONDS,
    )
    published = await _repo.publish_scope(
        session,
        video_id=state.video_id,
        language_code=state.language_code,
        revision=revision,
        rule_version=MEASUREMENT_RULE_VERSION,
    )
    return written, published


# Lock contention is retried promptly and never counted as a computation failure.
_LOCK_SQLSTATES = frozenset(
    {"40P01", "55P03", "40001"}
)  # deadlock, lock n/a, serialization
LOCK_RETRIES = 3
DEFER_SECONDS = 5.0
# A scope is reported as failing (it is still retried) from this many attempts on.
FAILING_ATTEMPTS = 3


def _jitter() -> float:
    return random.uniform(0.01, 0.05)  # noqa: S311 - retry jitter, not crypto


def _is_lock_contention(exc: BaseException) -> bool:
    return isinstance(exc, DBAPIError) and (
        getattr(exc.orig, "sqlstate", None) in _LOCK_SQLSTATES
    )


class _Outcome(Enum):
    PUBLISHED = "published"
    UNPUBLISHED = "unpublished"
    FAILED = "failed"
    DEFERRED = "deferred"


async def _process_one(
    scope_filter: ScopeFilter | None, attempted: set[tuple[str, str]]
) -> tuple[_Outcome, int] | None:
    """Claim and recompute one scope; None when nothing is claimable.

    The claimed scope is added to ``attempted`` whatever the outcome. A lock error
    re-claims the SAME scope up to ``LOCK_RETRIES`` times after a short jitter, then
    defers it. Any other error rolls back the scope's transaction and records the
    failure in a separate, revision-guarded transaction.
    """
    key: tuple[str, str] | None = None
    revision = 0
    for retry in range(LOCK_RETRIES + 1):
        try:
            async with db_manager.session() as session:
                state = await _repo.claim_next_scope(
                    session,
                    rule_version=MEASUREMENT_RULE_VERSION,
                    scope_filter=scope_filter,
                    exclude=attempted,
                    key=key,
                )
                if state is None:
                    return None if key is None else (_Outcome.UNPUBLISHED, 0)
                key, revision = (state.video_id, state.language_code), state.revision
                written, published = await recompute_scope(session, state)
            attempted.add(key)
            return (_Outcome.PUBLISHED if published else _Outcome.UNPUBLISHED), written
        except Exception as exc:  # every failure is recorded per scope
            if key is None:
                raise  # the claim itself failed: nothing to attribute it to
            if _is_lock_contention(exc) and retry < LOCK_RETRIES:
                await asyncio.sleep(_jitter())
                continue
            attempted.add(key)
            async with db_manager.session() as session:
                if _is_lock_contention(exc):
                    await _repo.defer_scope(
                        session,
                        video_id=key[0],
                        language_code=key[1],
                        attempted_revision=revision,
                        seconds=DEFER_SECONDS,
                    )
                    logger.warning("proximity scope %s deferred: %s", key, exc)
                    return _Outcome.DEFERRED, 0
                await _repo.record_scope_failure(
                    session,
                    video_id=key[0],
                    language_code=key[1],
                    attempted_revision=revision,
                    rule_version=MEASUREMENT_RULE_VERSION,
                    error=f"{type(exc).__name__}: {exc}",
                )
            logger.exception("proximity scope %s failed", key)
            return _Outcome.FAILED, 0
    raise AssertionError("unreachable")  # pragma: no cover


async def process_stale_scopes(
    *,
    limit: int,
    scope_filter: ScopeFilter | None = None,
    count_locked_elsewhere: bool = True,
) -> ProcessSummary:
    """Recompute up to ``limit`` stale scopes, one transaction per scope.

    Claims one claimable scope at a time (``FOR UPDATE SKIP LOCKED``), recomputes it,
    and publishes it on commit. A scope is attempted at most once per call, and a
    failing scope never aborts the call or starves the others (failure handling:
    data-model section 2). The end-of-call counts describe the filtered set:
    ``remaining`` not-current scopes, of which ``locked_elsewhere`` are held by another
    transaction and ``failing`` have failed ``FAILING_ATTEMPTS`` or more times.

    ``count_locked_elsewhere=False`` skips the one count that takes row locks
    (``FOR UPDATE SKIP LOCKED`` over every unsettled scope) and reports 0 for it.
    The worker passes False: that count is for reports a person reads, and taking
    thousands of row locks every cycle would briefly block producers.
    """
    counts = dict.fromkeys(_Outcome, 0)
    records_written = 0
    attempted: set[tuple[str, str]] = set()
    while sum(counts.values()) < limit:
        result = await _process_one(scope_filter, attempted)
        if result is None:
            break
        outcome, written = result
        counts[outcome] += 1
        records_written += written

    remaining, failing, locked_elsewhere, waiting = await _end_counts(
        scope_filter, count_locked_elsewhere=count_locked_elsewhere
    )
    return ProcessSummary(
        processed=counts[_Outcome.PUBLISHED],
        failed=counts[_Outcome.FAILED],
        deferred=counts[_Outcome.DEFERRED],
        records_written=records_written,
        locked_elsewhere=locked_elsewhere,
        failing=failing,
        waiting_to_retry=waiting,
        remaining=remaining,
        complete=remaining == 0,
    )


async def _end_counts(
    scope_filter: ScopeFilter | None, *, count_locked_elsewhere: bool
) -> tuple[int, int, int, int]:
    """``(remaining, failing, locked_elsewhere, waiting_to_retry)`` for the set."""
    rule = MEASUREMENT_RULE_VERSION
    async with db_manager.session() as session:
        remaining = await _repo.count_unsettled(
            session, rule_version=rule, scope_filter=scope_filter
        )
        failing = await _repo.count_failing(
            session,
            rule_version=rule,
            threshold=FAILING_ATTEMPTS,
            scope_filter=scope_filter,
        )
        waiting = await _repo.count_waiting_to_retry(
            session, rule_version=rule, scope_filter=scope_filter
        )
        locked = 0
        if count_locked_elsewhere and remaining:
            lockable = await _repo.count_lockable_unsettled(
                session, rule_version=rule, scope_filter=scope_filter
            )
            locked = max(remaining - lockable, 0)
    return remaining, failing, locked, waiting


worker_status = ProximityWorkerStatus()

# A failed worker cycle backs off up to this long before trying again.
_WORKER_MAX_BACKOFF_SECONDS = 60.0


async def bootstrap_scope_states() -> int:
    """Create missing scope-state rows for every transcript scope (not computed)."""
    async with db_manager.session() as session:
        return await _repo.bootstrap_scope_states(session)


async def run_proximity_worker(
    stop: asyncio.Event, *, interval_s: float, batch: int, reconcile_every: int
) -> None:
    """Recompute stale scopes in the background until ``stop`` is set.

    Bootstraps missing scope rows on start and every ``reconcile_every`` cycles, then
    processes up to ``batch`` scopes per cycle. While work remains it loops without
    sleeping; otherwise it waits ``interval_s`` (or until stopped). A failed cycle is
    logged and retried with backoff. Cancellation is never caught, so shutdown can
    always stop the task.
    """
    worker_status.state = ProximityWorkerState.RUNNING
    cycle = 0
    consecutive_failures = 0
    try:
        while not stop.is_set():
            delay = interval_s
            try:
                if cycle % reconcile_every == 0:
                    created = await bootstrap_scope_states()
                    if created:
                        logger.info("proximity worker: %d new scope(s)", created)
                summary = await process_stale_scopes(
                    limit=batch, count_locked_elsewhere=False
                )
                worker_status.last_cycle_at = datetime.datetime.now(datetime.UTC)
                consecutive_failures = 0
                if summary.processed and summary.remaining:
                    delay = 0.0  # work is queued: keep going
            except Exception:  # one bad cycle must not stop the worker
                consecutive_failures += 1
                delay = min(
                    interval_s * 2**consecutive_failures, _WORKER_MAX_BACKOFF_SECONDS
                )
                logger.exception("proximity worker cycle failed; retrying")
            cycle += 1
            if delay:
                try:
                    await asyncio.wait_for(stop.wait(), timeout=delay)
                except TimeoutError:
                    pass
            else:
                await asyncio.sleep(0)  # yield to the event loop between batches
    finally:
        if worker_status.state is ProximityWorkerState.RUNNING:
            worker_status.state = ProximityWorkerState.STOPPED


def _filters(
    video_ids: Sequence[str] | None, entity_ids: Sequence[uuid.UUID] | None
) -> list[ScopeFilter]:
    """One scope filter per requested selector; empty means "everything"."""
    filters: list[ScopeFilter] = []
    if video_ids:
        filters.append(ScopeFilter(video_ids=tuple(video_ids)))
    filters.extend(ScopeFilter(entity_id=entity_id) for entity_id in entity_ids or ())
    return filters


async def _invalidate_requested(session: AsyncSession, scope: ScopeFilter) -> None:
    if scope.video_ids is not None:
        for video_id in sorted(scope.video_ids):
            await _repo.invalidate_proximity_scopes(
                session, video_id=video_id, reason="rebuild"
            )
    elif scope.entity_id is not None:
        await _repo.invalidate_proximity_scopes(
            session, entity_id=scope.entity_id, reason="rebuild"
        )


async def _release_or_discard(connection: AsyncConnection, *, acquired: bool) -> None:
    """Release the rebuild lock, or discard the connection if that cannot be done.

    Closing a pooled connection returns it to the pool WITHOUT ending its database
    session, and a session-level advisory lock survives that. So if the release fails,
    reports it did not hold the lock, or the acquisition itself was interrupted, the
    connection is invalidated: its session ends and Postgres frees the lock.
    """
    try:
        if acquired and await _repo.release_rebuild_lock(connection):
            return
    except BaseException:
        await connection.invalidate()
        raise
    await connection.invalidate()


async def rebuild_proximity(
    *,
    force: bool = False,
    video_ids: Sequence[str] | None = None,
    entity_ids: Sequence[uuid.UUID] | None = None,
    batch: int = 200,
    progress: Callable[[ProcessSummary], None] | None = None,
) -> RebuildOutcome:
    """Bring the requested scopes (default: all) current, resumably (contracts C4).

    Owns the rebuild advisory lock on a dedicated connection for the whole run, so a
    second rebuild is refused and a killed one releases it. While holding it, leftover
    ``running`` runs are marked ``abandoned`` and missing scope rows are created.
    ``force`` bumps every revision in the set and resets failures; a scoped rebuild
    invalidates the requested scopes. Then scopes are processed in bounded batches,
    each published in its own transaction, so an interrupted run loses at most the
    scope in flight and a rerun resumes: scopes already current are skipped. The run
    is ``completed`` only if every scope in the set ended current.

    When both ``video_ids`` and ``entity_ids`` are given and their scopes overlap, the
    end-of-run counts are summed per selector and may count a shared scope twice.
    """
    requested = _filters(video_ids, entity_ids)
    filters: list[ScopeFilter | None] = list(requested) or [None]
    async with db_manager.get_engine().connect() as lock_connection:
        acquired = False
        try:
            acquired = await _repo.try_acquire_rebuild_lock(lock_connection)
            if not acquired:
                return RebuildOutcome(status="locked")
            async with db_manager.session() as session:
                await _repo.mark_abandoned_runs(session)
                run = await _repo.start_run(
                    session, generator_version=MEASUREMENT_RULE_VERSION
                )
                if run is None:  # cannot happen while we hold the lock
                    raise RuntimeError("a proximity run is already marked running")
                run_id = run.id
                await _repo.bootstrap_scope_states(session)
                for scope in filters:
                    if force:
                        await _repo.force_invalidate_scopes(session, scope_filter=scope)
                    elif scope is not None:
                        await _invalidate_requested(session, scope)

            totals = dict.fromkeys(("processed", "failed", "deferred", "records"), 0)
            remaining = failing = locked_elsewhere = waiting = 0
            for scope in filters:
                while True:
                    step = await process_stale_scopes(
                        limit=batch, scope_filter=scope, count_locked_elsewhere=False
                    )
                    totals["processed"] += step.processed
                    totals["failed"] += step.failed
                    totals["deferred"] += step.deferred
                    totals["records"] += step.records_written
                    if progress is not None:
                        progress(step)
                    if not (step.processed or step.failed or step.deferred):
                        break
                end = await _end_counts(scope, count_locked_elsewhere=True)
                remaining += end[0]
                failing += end[1]
                locked_elsewhere += end[2]
                waiting += end[3]

            summary = ProcessSummary(
                processed=totals["processed"],
                failed=totals["failed"],
                deferred=totals["deferred"],
                records_written=totals["records"],
                locked_elsewhere=locked_elsewhere,
                failing=failing,
                waiting_to_retry=waiting,
                remaining=remaining,
                complete=remaining == 0,
            )
            status: Literal["completed", "incomplete"] = (
                "completed" if summary.complete else "incomplete"
            )
            async with db_manager.session() as session:
                await _repo.finish_run(
                    session,
                    run_id=run_id,
                    status=status,
                    scopes_processed=summary.processed,
                    instances_written=summary.records_written,
                )
            return RebuildOutcome(status=status, run_id=run_id, summary=summary)
        finally:
            await _release_or_discard(lock_connection, acquired=acquired)


async def dry_run_proximity(
    *,
    video_ids: Sequence[str] | None = None,
    entity_ids: Sequence[uuid.UUID] | None = None,
    sample: int = 20,
) -> DryRunReport:
    """Count the records the requested scopes WOULD get, publishing nothing.

    With no scope requested, a bounded ``sample`` of transcript scopes is computed
    instead; its counts cover only those scopes and are not a corpus validation.
    Takes neither the rebuild lock nor any scope row lock, writes no state, and
    creates no run row: it only reads, in one transaction that is rolled back.
    """
    filters = _filters(video_ids, entity_ids)
    async with db_manager.session() as session:
        if filters:
            keys = sorted(
                {
                    key
                    for scope in filters
                    for key in await _repo.list_transcript_scopes(
                        session, scope_filter=scope
                    )
                }
            )
        else:
            keys = await _repo.list_transcript_scopes(session, limit=sample)
        scopes = [
            DryRunScope(
                video_id=video_id,
                language_code=language_code,
                records=await _repo.count_scope_records(
                    session,
                    video_id=video_id,
                    language_code=language_code,
                    outer_window=OUTER_WINDOW_SECONDS,
                ),
            )
            for video_id, language_code in keys
        ]
        await session.rollback()
    return DryRunReport(scopes=scopes, sampled=not filters)


async def drain_stale_scopes(*, limit: int) -> ProcessSummary:
    """What the worker does, once: create missing scope rows, then process.

    For operating without the API. Without the bootstrap, scopes of transcripts
    that never had a state row would stay "not computed" forever.
    """
    await bootstrap_scope_states()
    return await process_stale_scopes(limit=limit)


async def retry_failed(*, video_ids: Sequence[str] | None = None) -> int:
    """Make failing scopes claimable now (no revision bump). Returns the rows reset."""
    async with db_manager.session() as session:
        return await _repo.reset_failures(session, video_ids=video_ids)


async def proximity_status(*, failing_limit: int = 20) -> ProximityStatusReport:
    """Counts by state, failing scopes, the oldest non-current scope, the lock holder."""
    rule = MEASUREMENT_RULE_VERSION
    async with db_manager.session() as session:
        not_computed, current, stale, oldest = await _repo.state_counts(
            session, rule_version=rule
        )
        failing_total = await _repo.count_failing(
            session, rule_version=rule, threshold=FAILING_ATTEMPTS
        )
        failing = await _repo.list_failing(
            session, rule_version=rule, threshold=FAILING_ATTEMPTS, limit=failing_limit
        )
        holder = await _repo.rebuild_lock_holder(session)
    return ProximityStatusReport(
        rule_version=rule,
        not_computed=not_computed,
        current=current,
        stale=stale,
        failing=[
            FailingScope(
                video_id=row.video_id,
                language_code=row.language_code,
                attempts=row.attempts,
                last_error=row.last_error,
                next_attempt_at=row.next_attempt_at,
            )
            for row in failing
        ],
        failing_total=failing_total,
        oldest_not_current_at=oldest,
        rebuild_lock_holder_pid=holder,
    )
