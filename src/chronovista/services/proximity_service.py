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
from typing import Literal, NamedTuple

from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from chronovista.config.database import db_manager
from chronovista.db.models import ProximityScopeState as ProximityScopeStateDB
from chronovista.db.models import UserLanguagePreference as UserLanguagePreferenceDB
from chronovista.models.connection_evidence import (
    OTHER_MOMENTS_LIMIT,
    CoMoment,
    FailedScope,
    FartherVideo,
    FartherVideos,
    GroupedPassage,
    LanguagePassage,
    NonTranscriptBasis,
    PairPassages,
    PairPassagesState,
    PassageMoment,
    ProximityWindow,
    VideoPassages,
)
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
from chronovista.models.enums import LanguageCode, LanguagePreferenceType
from chronovista.repositories.entity_mention_repository import (
    EntityMentionRepository,
    PassageText,
)
from chronovista.repositories.entity_pair_proximity_repository import (
    CoMentionRow,
    EntityPairProximityRepository,
)
from chronovista.repositories.user_language_preference_repository import (
    UserLanguagePreferenceRepository,
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


# ----- discussion passages: the evidence panel's read side (Feature 118) ------------

_mention_repo = EntityMentionRepository()
_preference_repo = UserLanguagePreferenceRepository()


class _Passage(NamedTuple):
    """One language passage while grouping: its range and its co-mentions."""

    video_id: str
    language_code: str
    start_time: float
    end_time: float
    comentions: list[CoMentionRow]


def _in_time_order(row: CoMentionRow) -> tuple[float, float, int, int]:
    return (row.start_time, row.end_time, row.segment_lo_id, row.segment_hi_id)


def _closest_first(row: CoMentionRow) -> tuple[float, float, int, int]:
    """Total order for a passage's closest co-mention (gap, then time, then segments)."""
    return (row.gap_seconds, row.start_time, row.segment_lo_id, row.segment_hi_id)


def chain_passages(rows: Sequence[CoMentionRow], window_s: float) -> list[_Passage]:
    """Merge co-mentions into passages, per video and language: passage rule ``118.0``.

    The passage rule (``PASSAGE_RULE_VERSION``, Feature 118 FR-001, FR-005). Within one video and
    transcript language, co-mentions are taken in time order. A co-mention joins the current
    passage when its start is at most ``window_s`` after the latest end of any co-mention already in
    the passage; otherwise it starts a new passage. This chains: a sustained discussion whose
    co-mentions keep arriving within the window becomes ONE long passage, however long. That is
    documented behavior and it is **not** topic separation: a passage is a stretch of nearby
    co-mentions, not a judgement about what was said. Because a new passage starts only after
    everything before it has ended, the passages of one (video, language) never overlap.
    """
    by_scope: dict[tuple[str, str], list[CoMentionRow]] = {}
    for row in rows:
        by_scope.setdefault((row.video_id, row.language_code), []).append(row)
    passages: list[_Passage] = []
    for (video_id, language_code), scope_rows in by_scope.items():
        current: list[CoMentionRow] = []
        end = 0.0
        for row in sorted(scope_rows, key=_in_time_order):
            if current and row.start_time > end + window_s:
                passages.append(
                    _Passage(
                        video_id, language_code, current[0].start_time, end, current
                    )
                )
                current = []
            if not current:
                end = row.end_time
            current.append(row)
            end = max(end, row.end_time)
        passages.append(
            _Passage(video_id, language_code, current[0].start_time, end, current)
        )
    return passages


def group_across_languages(passages: Sequence[_Passage]) -> list[list[_Passage]]:
    """Group one video's passages whose time ranges overlap: grouped discussion passages (FR-011).

    Ranges overlap when one starts before the other ends; ranges that merely touch are not grouped
    (passages that start at the same moment always group, even when zero-length).
    Grouping is transitive (overlap with any member joins the group), so unequal boundaries across
    languages still land in one group, and one language can appear twice in a group. A group is the
    unit the summary counts, so a translation never adds to a count (FR-012). Groups are returned in
    time order.
    """
    groups: list[list[_Passage]] = []
    end = 0.0
    for passage in sorted(
        passages, key=lambda p: (p.start_time, p.end_time, p.language_code)
    ):
        # Overlap, or the same start: two zero-length passages at one moment are one discussion.
        if groups and (
            passage.start_time < end or passage.start_time == groups[-1][0].start_time
        ):
            groups[-1].append(passage)
            end = max(end, passage.end_time)
        else:
            groups.append([passage])
            end = passage.end_time
    return groups


class _LanguageRank(NamedTuple):
    """Where a preferred language ranks: its tier (fluent 0, learning 1) and priority."""

    tier: int
    priority: int


_UNRANKED = _LanguageRank(tier=2, priority=0)


def _language_ranks(
    preferences: Sequence[UserLanguagePreferenceDB],
) -> dict[str, _LanguageRank]:
    """Fluent and learning preferences by BASE language (``es-MX`` and ``es`` match, Principle VII).

    Curious and exclude never promote a variant. When one base language carries several
    preferences, the best-ranked wins.
    """
    tiers = {
        LanguagePreferenceType.FLUENT.value: 0,
        LanguagePreferenceType.LEARNING.value: 1,
    }
    ranks: dict[str, _LanguageRank] = {}
    for pref in preferences:
        tier = tiers.get(pref.preference_type)
        if tier is None:
            continue
        rank = _LanguageRank(tier=tier, priority=pref.priority)
        base = LanguageCode.get_base_language(pref.language_code)
        if base not in ranks or rank < ranks[base]:
            ranks[base] = rank
    return ranks


def _order_variants(
    variants: list[LanguagePassage], ranks: dict[str, _LanguageRank]
) -> list[LanguagePassage]:
    """Which variant of a grouped passage leads (FR-011a, FR-014b).

    The reviewer's preferred language first (fluent before learning, then by preference
    priority); among equally ranked variants, and when no variant is preferred, the closest
    co-mention leads, then language code. Never changes a count or the group's closest gap.
    """
    return sorted(
        variants,
        key=lambda v: (
            ranks.get(LanguageCode.get_base_language(v.language_code), _UNRANKED),
            v.closest_gap_seconds,
            v.language_code,
        ),
    )


def _language_passage(
    passage: _Passage, text: PassageText, *, a_is_lo: bool, name_lists: set[int]
) -> LanguagePassage:
    """One language passage, its closest co-mention rendered and the others listed by time."""
    closest, *others = sorted(passage.comentions, key=_closest_first)
    mention_a, mention_b = (
        (text.mention_lo, text.mention_hi)
        if a_is_lo
        else (text.mention_hi, text.mention_lo)
    )
    lead = min((text.mention_lo, text.mention_hi), key=lambda m: m.start_time)
    one_segment = closest.segment_lo_id == closest.segment_hi_id
    return LanguagePassage(
        language_code=passage.language_code,
        start_time=passage.start_time,
        end_time=passage.end_time,
        co_mention_count=len(passage.comentions),
        closest_gap_seconds=closest.gap_seconds,
        closest=PassageMoment(
            gap_seconds=closest.gap_seconds,
            start_time=closest.start_time,
            segment_id=lead.segment_id,
            mention_a=mention_a,
            mention_b=mention_b,
            segments=text.segments,
        ),
        other_moments=[
            CoMoment(start_time=o.start_time, gap_seconds=o.gap_seconds)
            for o in sorted(others, key=lambda o: (o.start_time, o.gap_seconds))[
                :OTHER_MOMENTS_LIMIT
            ]
        ],
        name_list=one_segment and closest.segment_lo_id in name_lists,
    )


class PassageInvariantError(RuntimeError):
    """A passage's text could not be read although its co-mentions were (Feature 118).

    Inside one snapshot the two reads use the same qualifying mentions, so this means they have
    drifted apart in code. It fails the request loudly rather than return a page whose ``returned``
    no longer matches the videos it consumed (which would make the next page overlap this one).
    """


def _text_for(
    texts: dict[tuple[str, str, int, int], PassageText], passage: _Passage
) -> PassageText:
    key = _moment_key(passage)
    text = texts.get(key)
    if text is None:
        raise PassageInvariantError(
            f"passage text missing for {key}: the co-mention and text reads disagree"
        )
    return text


def _moment_key(passage: _Passage) -> tuple[str, str, int, int]:
    closest = min(passage.comentions, key=_closest_first)
    return (
        passage.video_id,
        passage.language_code,
        closest.segment_lo_id,
        closest.segment_hi_id,
    )


async def begin_read_snapshot(session: AsyncSession) -> None:
    """Start a read-only snapshot on a fresh session, before :func:`pair_passages` reads."""
    await _repo.begin_read_snapshot(session)


async def pair_passages(
    session: AsyncSession,
    *,
    entity_a: uuid.UUID,
    entity_b: uuid.UUID,
    window: ProximityWindow,
    limit: int,
    offset: int,
    user_id: str | None = None,
) -> PairPassages:
    """A pair's discussion passages for one window: the evidence panel's response (Feature 118).

    Read-only, and meant to run inside one snapshot (:func:`begin_read_snapshot` first): the proximity
    worker commits scope replacements concurrently, and a count from one statement must match the
    rows of the next.
    Built from the Feature 117 records, so the videos shown are exactly the videos the measurement
    reports for this pair and window. The summary counts cover every video in the window; only the
    page of videos (closest-first, then by video id) is rendered with text. ``user_id``'s
    language preferences decide which language variant leads; without one, the closest does.
    """
    rows = await _repo.pair_comentions(
        session, entity_a=entity_a, entity_b=entity_b, window_s=float(window)
    )
    lo, hi = sorted((entity_a, entity_b))
    by_video: dict[str, list[_Passage]] = {}
    for passage in chain_passages(rows, float(window)):
        by_video.setdefault(passage.video_id, []).append(passage)
    groups = {
        video_id: group_across_languages(passages)
        for video_id, passages in by_video.items()
    }
    video_gap = {
        video_id: min(r.gap_seconds for p in passages for r in p.comentions)
        for video_id, passages in by_video.items()
    }
    ordered = sorted(by_video, key=lambda v: (video_gap[v], v))
    page = ordered[offset : offset + limit]

    texts = await _mention_repo.passage_texts(
        session,
        entity_lo=lo,
        entity_hi=hi,
        moments=[_moment_key(p) for video_id in page for p in by_video[video_id]],
    )
    titles = await _mention_repo.video_titles(session, page)
    page_closest = [
        min(p.comentions, key=_closest_first) for v in page for p in by_video[v]
    ]
    name_lists = await _repo.name_list_segments(
        session,
        segment_ids={
            c.segment_lo_id for c in page_closest if c.segment_lo_id == c.segment_hi_id
        },
    )
    ranks = (
        _language_ranks(await _preference_repo.get_user_preferences(session, user_id))
        if user_id is not None
        else {}
    )

    items: list[VideoPassages] = []
    for video_id in page:
        grouped: list[GroupedPassage] = []
        for group in groups[video_id]:
            variants = [
                _language_passage(
                    p,
                    _text_for(texts, p),
                    a_is_lo=entity_a == lo,
                    name_lists=name_lists,
                )
                for p in group
            ]
            grouped.append(
                GroupedPassage(
                    start_time=min(v.start_time for v in variants),
                    end_time=max(v.end_time for v in variants),
                    closest_gap_seconds=min(v.closest_gap_seconds for v in variants),
                    variants=_order_variants(variants, ranks),
                )
            )
        video_title, channel_title = titles.get(video_id, (None, None))
        items.append(
            VideoPassages(
                video_id=video_id,
                video_title=video_title,
                channel_title=channel_title,
                closest_gap_seconds=video_gap[video_id],
                passages=grouped,
            )
        )

    pending, failed = await _repo.pair_scope_health(
        session,
        entity_a=entity_a,
        entity_b=entity_b,
        rule_version=MEASUREMENT_RULE_VERSION,
        failing_threshold=FAILING_ATTEMPTS,
    )
    spoken = {
        video_id
        for video_id, _ in _shared_scopes(
            await _mention_repo.pair_mention_starts(
                session, entity_a=entity_a, entity_b=entity_b
            ),
            entity_a,
            entity_b,
        )
    }
    failed_titles = await _mention_repo.video_titles(
        session, sorted({video_id for video_id, _ in failed})
    )

    # FR-015b: exactly one outcome, in this order.
    state: PairPassagesState
    basis: NonTranscriptBasis | None = None
    if by_video:
        state = "passages"
    elif not spoken:
        state = "not_computed" if pending else "no_transcript"
        if state == "no_transcript":
            triples = await _mention_repo.association_triples(
                session, [entity_a, entity_b]
            )
            basis = _mention_repo.non_transcript_basis(triples, entity_a, entity_b)
    elif pending:
        state = "not_computed"
    else:
        state = "no_passage_in_window"

    return PairPassages(
        entity_a_id=entity_a,
        entity_b_id=entity_b,
        window_seconds=window,
        items=items,
        offset=offset,
        video_count=len(by_video),
        passage_count=sum(len(g) for g in groups.values()),
        channel_count=len({r.channel_id for r in rows}),
        closest_gap_seconds=min(video_gap.values()) if video_gap else None,
        farther_video_count=len(spoken - by_video.keys()),
        pending_scopes=pending,
        failed_scopes=[
            FailedScope(
                video_id=video_id,
                language_code=language_code,
                video_title=failed_titles.get(video_id, (None, None))[0],
                channel_title=failed_titles.get(video_id, (None, None))[1],
            )
            for video_id, language_code in failed
        ],
        state=state,
        basis_when_empty=basis,
    )


def _shared_scopes(
    rows: Sequence[tuple[uuid.UUID, str, str, float]],
    entity_a: uuid.UUID,
    entity_b: uuid.UUID,
) -> set[tuple[str, str]]:
    """The ``(video_id, language_code)`` where both entities have a qualifying mention."""
    seen: dict[tuple[str, str], set[uuid.UUID]] = {}
    for entity_id, video_id, language_code, _ in rows:
        seen.setdefault((video_id, language_code), set()).add(entity_id)
    return {scope for scope, ids in seen.items() if {entity_a, entity_b} <= ids}


def _nearest(starts_a: list[float], starts_b: list[float]) -> tuple[float, float]:
    """Smallest start-to-start gap between two mention lists, and that pair's earlier start.

    A sorted merge (each list sorted once), so a video with many mentions stays linear.
    """
    xs, ys = sorted(starts_a), sorted(starts_b)
    best = (abs(xs[0] - ys[0]), min(xs[0], ys[0]))
    i = j = 0
    while i < len(xs) and j < len(ys):
        gap = abs(xs[i] - ys[j])
        if gap < best[0]:
            best = (gap, min(xs[i], ys[j]))
        if xs[i] < ys[j]:
            i += 1
        else:
            j += 1
    return best


async def farther_videos(
    session: AsyncSession,
    *,
    entity_a: uuid.UUID,
    entity_b: uuid.UUID,
    window: ProximityWindow,
    limit: int,
    offset: int,
) -> FartherVideos:
    """Videos where both are spoken but never within the window, nearest-first (FR-010).

    "Both spoken" is qualifying mentions of both in one transcript language; a video with a
    co-mention within the window is a passage video, never listed here. Each row shows the
    smallest start-to-start gap in any shared language. Its total equals the passages
    response's ``farther_video_count`` for the same pair, window and snapshot.
    """
    starts_rows = await _mention_repo.pair_mention_starts(
        session, entity_a=entity_a, entity_b=entity_b
    )
    within = {
        r.video_id
        for r in await _repo.pair_comentions(
            session, entity_a=entity_a, entity_b=entity_b, window_s=float(window)
        )
    }
    # The same "both spoken here" rule as the passages response's farther_video_count.
    farther = {
        scope
        for scope in _shared_scopes(starts_rows, entity_a, entity_b)
        if scope[0] not in within
    }
    starts: dict[tuple[str, str], dict[uuid.UUID, list[float]]] = {}
    for entity_id, video_id, language_code, start in starts_rows:
        if (video_id, language_code) in farther:
            starts.setdefault((video_id, language_code), {}).setdefault(
                entity_id, []
            ).append(start)
    nearest: dict[str, tuple[float, float, str]] = {}
    for (video_id, language_code), by_entity in starts.items():
        gap, at = _nearest(by_entity[entity_a], by_entity[entity_b])
        if video_id not in nearest or (gap, language_code) < nearest[video_id][::2]:
            nearest[video_id] = (gap, at, language_code)
    ordered = sorted(nearest, key=lambda v: (nearest[v][0], v))
    page = ordered[offset : offset + limit]
    titles = await _mention_repo.video_titles(session, page)
    return FartherVideos(
        items=[
            FartherVideo(
                video_id=video_id,
                video_title=titles.get(video_id, (None, None))[0],
                channel_title=titles.get(video_id, (None, None))[1],
                language_code=nearest[video_id][2],
                nearest_gap_seconds=nearest[video_id][0],
                nearest_start_time=nearest[video_id][1],
            )
            for video_id in page
        ],
        offset=offset,
        total=len(nearest),
    )
