"""
Transcript proximity computor service (Feature 116).

Rebuilds the proximity primitive: the mention×mention self-join bounded to
support-only pairs ∪ reviewed-verdict pairs (FR-019), language-scoped (FR-016),
to a 120s outer window (FR-017), start-anchored for cross-segment mentions
(FR-021), with F091 exclusions removed (D7). The heavy join and every table write
live in :class:`EntityPairProximityRepository`; this service owns the policy
constants and the run / scope orchestration, mirroring
``generate_relationship_candidates``.

The FR-016 language-scoping invariant is NON-NEGOTIABLE. Its single isolatable
clause is :func:`chronovista.repositories.entity_pair_proximity_repository.language_scope_predicate`,
which the mutation-verified guard (T015) removes to prove the join fabricates
cross-language instances without it.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from chronovista.config.database import db_manager
from chronovista.repositories.entity_pair_proximity_repository import (
    EntityPairProximityRepository,
)

# Bump when the self-join shape, the scope bound, or the window policy changes, so a
# run's provenance records which computor produced its instances.
GENERATOR_VERSION = "116.0"

# A pair qualifies for proximity when its transcript co-occurrence clears this many
# shared videos (∪ reviewed-verdict pairs). Support-only — NOT lift (D5): a lift gate
# would drop the hub-anchored orphans the feature exists to rescue.
SUPPORT_MIN = 5

# The instance table stores every close co-mention out to this outer window; the
# 15/30/60s tiers are read-time predicates over it (D3), so the window is not an enum.
OUTER_WINDOW_SECONDS = 120.0

# The three rollup tiers (close_co_mentions_15 / _30 / _60). Fixed by the schema's
# column names; kept here so the computor owns the policy and passes it to the rollup.
CLOSE_WINDOWS: tuple[int, int, int] = (15, 30, 60)


async def rebuild_proximity(
    *,
    video_ids: Sequence[str] | None = None,
    entity_ids: Sequence[uuid.UUID] | None = None,
    dry_run: bool = False,
) -> dict[str, int]:
    """Recompute proximity instances + rollup for a scope (or the whole corpus).

    With neither ``video_ids`` nor ``entity_ids`` this is a full rebuild: every
    instance is dropped and recomputed and the rollup is rebuilt wholesale. With a
    scope, only the matching instances are deleted and reinserted and only the
    affected pairs' rollup is recomputed (the pairs that had an instance in scope
    before, unioned with those that have one after — so a pair whose last instance
    was dropped loses its rollup row too).

    ``dry_run`` rolls the whole run back (writes nothing, leaves no 'running' lock) —
    the session autocommits on scope exit, so dry-run must explicitly roll back.
    Returns a summary of counts.
    """
    repo = EntityPairProximityRepository()
    full = not video_ids and not entity_ids
    summary: dict[str, int] = {
        "instances_written": 0,
        "pairs_rolled_up": 0,
        "instances_deleted": 0,
    }

    async with db_manager.session() as session:
        run = await repo.start_run(session, generator_version=GENERATOR_VERSION)
        if run is None:
            raise RuntimeError("a proximity rebuild is already running")

        affected_before: set[tuple[uuid.UUID, uuid.UUID]] = set()
        if full:
            deleted = await repo.delete_all_instances(session)
        else:
            affected_before = await repo.pairs_in_scope(
                session, video_ids=video_ids, entity_ids=entity_ids
            )
            deleted = await repo.delete_instances_matching(
                session, video_ids=video_ids, entity_ids=entity_ids
            )

        written = await repo.insert_instances_for_scope(
            session,
            support_min=SUPPORT_MIN,
            outer_window=OUTER_WINDOW_SECONDS,
            video_ids=video_ids,
            entity_ids=entity_ids,
        )

        if full:
            rolled = await repo.rebuild_all_rollup(session, windows=CLOSE_WINDOWS)
        else:
            affected_after = await repo.pairs_in_scope(
                session, video_ids=video_ids, entity_ids=entity_ids
            )
            affected = affected_before | affected_after
            rolled = await repo.rebuild_rollup_for_pairs(
                session, pairs=affected, windows=CLOSE_WINDOWS
            )

        # One run == one rebuild invocation, so scopes_processed is 1 for a full
        # rebuild or the count of scoped targets (videos/entities) otherwise.
        scopes_processed = 1 if full else len(video_ids or []) + len(entity_ids or [])
        await repo.finish_run(
            session,
            run_id=run.id,
            status="completed",
            scopes_processed=scopes_processed,
            instances_written=written,
            pairs_rolled_up=rolled,
        )

        summary = {
            "instances_written": written,
            "pairs_rolled_up": rolled,
            "instances_deleted": deleted,
        }

        # dry_run rolls back EVERYTHING — the run row included — so a trial leaves no
        # trace and no stuck 'running' lock. (A real exception's rollback does the same.)
        if dry_run:
            await session.rollback()

    return summary


async def drain_dirty_scopes(*, limit: int | None = None) -> dict[str, int]:
    """Recompute every queued dirty ``(video, language)`` scope, then clear it.

    Reads the invalidation queue (``proximity_dirty_scopes``), capturing each row's
    ``marked_at`` snapshot, then recomputes the DISTINCT dirty videos in ONE batched
    :func:`rebuild_proximity` call (``video_ids=`` every distinct dirty video). The
    support/scope CTE is corpus-wide, so one batched call computes it once and writes a
    single ``proximity_generation_runs`` row — a per-video loop recomputed that CTE N
    times and wrote N runs. A video with several dirty languages recomputes once (its
    rebuild spans every language of the video), not once per language.

    Each drained scope is then deleted CONDITIONALLY — only when its ``marked_at`` is
    still ``<=`` the snapshot captured before the rebuild — so a ``mark_dirty`` that
    lands during the rebuild survives the drain and is picked up next time, rather than
    being silently cleared. ``limit`` caps the number of scopes read per call.
    ``scopes_drained`` is the number of queue rows actually removed. Returns a summary
    of counts.
    """
    repo = EntityPairProximityRepository()

    async with db_manager.session() as session:
        snapshots = [
            (scope.video_id, scope.language_code, scope.marked_at)
            for scope in await repo.list_dirty_scopes(session, limit=limit)
        ]

    if not snapshots:
        return {"scopes_drained": 0, "instances_written": 0}

    video_ids = list(dict.fromkeys(video_id for video_id, _, _ in snapshots))
    result = await rebuild_proximity(video_ids=video_ids)

    scopes_drained = 0
    async with db_manager.session() as session:
        for video_id, language_code, marked_at in snapshots:
            scopes_drained += await repo.delete_dirty_scope(
                session,
                video_id=video_id,
                language_code=language_code,
                before_marked_at=marked_at,
            )

    return {
        "scopes_drained": scopes_drained,
        "instances_written": result["instances_written"],
    }
