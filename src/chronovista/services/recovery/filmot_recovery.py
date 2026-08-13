"""
Fill metadata gaps on unavailable videos from the Filmot archive.

A separate path from archived-page recovery, sharing exactly two things with
it: the provenance write and the merge policy. Those are where this project's
expensive defects have lived, and a second copy of either is a second place to
fix them. Everything else differs, because the sources differ in kind — one
parses archived pages and must choose among snapshots, this one queries a
structured index and has no snapshot to choose.

**The correctness mechanism is the conditional write.** Every field's gate is
re-asserted in the UPDATE's own WHERE clause, not only when the candidate was
read. Without that, a concurrent writer could fill a field between selection
and write and this source would overwrite it — making fill-only true by timing
rather than by construction, which is not true at all.

Nothing here assigns ``videos.recovery_source``. That column is a
most-recent-contributor projection maintained by the provenance repository; a
writer that assigns it directly overwrites another source's attribution without
appending a row, which is how 92 rows lost theirs.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import Channel as ChannelDB
from chronovista.db.models import Video as VideoDB
from chronovista.exceptions import FilmotError
from chronovista.models.recovery_provenance import RecoverySourceRecord
from chronovista.repositories.channel_repository import ChannelRepository
from chronovista.repositories.recovery_provenance_repository import (
    RecoveryProvenanceRepository,
)
from chronovista.repositories.video_repository import VideoRepository
from chronovista.services.recovery.filmot_client import FilmotClient, FilmotVideo
from chronovista.services.recovery.merge_policy import (
    build_filmot_update,
    placeholder_title_condition,
)
from chronovista.services.recovery.models import FilmotRecoveryResult

logger = logging.getLogger(__name__)

FILMOT_SOURCE = "filmot"

# Videos per database batch. Independent of the client's request batching:
# this is the commit granularity, so an interrupted run leaves whole batches
# applied and never a partially-applied video.
_COMMIT_BATCH_SIZE = 50

# A run that reaches this has stopped being a normal run. The target is under
# ten minutes for the entire backlog, so a healthy run never approaches it and
# reaching it is itself worth reporting.
_RUN_TIME_LIMIT_SECONDS = 1_800.0


async def run_filmot_recovery(
    session: AsyncSession,
    client: FilmotClient,
    limit: int | None = None,
    dry_run: bool = False,
) -> FilmotRecoveryResult:
    """
    Fill title, channel and duration gaps from the Filmot archive.

    Parameters
    ----------
    session : AsyncSession
        Database session.
    client : FilmotClient
        Configured archive client.
    limit : int | None, optional
        Maximum videos to consider.
    dry_run : bool, optional
        Report intended writes without making them.

    Returns
    -------
    FilmotRecoveryResult
        Every outcome an operator would act on differently, counted separately.
    """
    started = time.monotonic()

    if not client.is_configured:
        logger.info(
            "Filmot recovery skipped: no API key configured. Set FILMOT_API_KEY "
            "to enable this source."
        )
        return FilmotRecoveryResult(dry_run=dry_run, ended_early="not_configured")

    candidates = await VideoRepository().get_filmot_candidates(
        session, placeholder_title_condition(VideoDB.title), limit=limit
    )
    if not candidates:
        logger.info("Filmot recovery: no videos have a gap this source could fill")
        return FilmotRecoveryResult(dry_run=dry_run)

    logger.info(
        "Filmot recovery starting: %d candidate(s), rate limited to 1 request/second",
        len(candidates),
    )

    state = _RunState(dry_run=dry_run, total_candidates=len(candidates))

    for start in range(0, len(candidates), _COMMIT_BATCH_SIZE):
        if time.monotonic() - started > _RUN_TIME_LIMIT_SECONDS:
            state.end_early("time_limit", remaining=len(candidates) - start)
            break

        batch = candidates[start : start + _COMMIT_BATCH_SIZE]
        before_updated, before_held = state.updated, state.held_no_write
        try:
            await _process_batch(session, client, batch, state)
        except _SystemicFailure as exc:
            # This batch was asked about and is already counted as unresolved;
            # only what follows it was never attempted.
            state.end_early(exc.reason, remaining=len(candidates) - start - len(batch))
            break
        except Exception:
            # Every earlier batch is already committed and durable. Letting this
            # escape to the CLI's blanket handler printed "Database error" and
            # exit 2 with no summary at all — so an operator whose run wrote 800
            # titles before failing was never told that titles had changed and
            # that search indexes and entity mentions were now stale. Ending the
            # run here keeps the write durable and the report honest.
            logger.exception("Filmot run ended by an unexpected error")
            try:
                await session.rollback()
            except Exception:
                # A dead connection is the likeliest way to reach this handler,
                # and it is also the likeliest way for the rollback itself to
                # fail. Letting that escape would lose the summary — the very
                # thing this branch exists to preserve.
                logger.exception("Filmot rollback failed after an earlier error")
            state.end_early(
                "unexpected_error", remaining=len(candidates) - start - len(batch)
            )
            break

        if dry_run:
            # Nothing was written, but the read that selected candidates opened
            # a transaction and only a commit or rollback closes it. Without
            # this, a dry run holds one transaction open for its whole length —
            # up to the 30-minute limit — pinning the xmin horizon so autovacuum
            # cannot reclaim dead tuples anywhere in the database.
            await session.rollback()
        else:
            await session.commit()

        logger.info(
            "Filmot batch %d: %d updated, %d held with nothing to write",
            start // _COMMIT_BATCH_SIZE + 1,
            state.updated - before_updated,
            state.held_no_write - before_held,
        )

    result = state.finalise(time.monotonic() - started)
    _log_summary(result)
    return result


class _SystemicFailure(Exception):
    """The source is refusing the run as a whole, not one batch.

    Isolated batch failures continue; systemic ones end the run. Where both
    readings could apply, systemic wins — see FR-018b.
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class _RunState:
    """Mutable tallies for one run.

    Deliberately not the result model: that one is frozen, because a result
    that can be edited after the fact is a result nobody can trust.
    """

    def __init__(self, dry_run: bool, total_candidates: int) -> None:
        self.dry_run = dry_run
        self.total_candidates = total_candidates
        self.submitted = 0
        self.returned = 0
        self.updated = 0
        self.held_no_write = 0
        self.not_held = 0
        self.unresolved = 0
        self.not_attempted = 0
        self.malformed_records = 0
        self.field_counts: dict[str, int] = {}
        self.refused_values: dict[str, int] = {}
        # A set, because ten videos from one unknown channel is one channel the
        # library is missing, not ten. The summary counts these.
        self.unknown_channels: set[str] = set()
        self.ended_early: str | None = None
        self.consecutive_rate_limits = 0

    def end_early(self, reason: str, remaining: int) -> None:
        self.ended_early = reason
        self.not_attempted += remaining
        logger.warning(
            "Filmot run ended early (%s); %d video(s) not attempted", reason, remaining
        )

    def finalise(self, duration: float) -> FilmotRecoveryResult:
        return FilmotRecoveryResult(
            submitted=self.submitted,
            returned=self.returned,
            updated=self.updated,
            held_no_write=self.held_no_write,
            field_counts=dict(self.field_counts),
            not_held=self.not_held,
            unresolved=self.unresolved,
            not_attempted=self.not_attempted,
            unknown_channels=sorted(self.unknown_channels),
            malformed_records=self.malformed_records,
            refused_values=dict(self.refused_values),
            ended_early=self.ended_early,
            dry_run=self.dry_run,
            duration_seconds=duration,
        )


async def _process_batch(
    session: AsyncSession,
    client: FilmotClient,
    batch: list[VideoDB],
    state: _RunState,
) -> None:
    """Look up one batch and apply what the policy permits."""
    ids = [v.video_id for v in batch]
    state.submitted += len(ids)

    try:
        found, unresolved = await client.fetch_videos(ids)
    except FilmotError as exc:
        # A credential the archive rejects, or a response shape we do not
        # understand, says nothing about any individual video — and will say
        # nothing about the next batch either.
        #
        # We asked about these ids and learned nothing, which is the definition
        # of unresolved. Counting them before the raise matters: they are
        # already in `submitted`, and the caller is about to record the rest of
        # the run as not-attempted. Omitting them here left them counted twice
        # and bucketed as never-asked — in the one code path where the
        # difference between "no record" and "we failed to ask" decides whether
        # an operator retries.
        state.unresolved += len(ids)
        raise _SystemicFailure(_classify(exc)) from exc

    state.unresolved += len(unresolved)

    if unresolved and len(unresolved) == len(ids):
        state.consecutive_rate_limits += 1
        if state.consecutive_rate_limits >= 3:
            raise _SystemicFailure("rate_limited")
    else:
        state.consecutive_rate_limits = 0

    # Records for identifiers we did not ask about are ignored, and duplicates
    # collapse to the first. Neither is expected; both are logged, because
    # silence would conceal a change in the archive's behaviour.
    requested = set(ids)
    by_id: dict[str, FilmotVideo] = {}
    for record in found:
        if record.video_id not in requested:
            state.malformed_records += 1
            logger.warning(
                "Filmot returned a record for an unrequested id; ignoring it"
            )
            continue
        if record.video_id in by_id:
            state.malformed_records += 1
            logger.warning(
                "Filmot returned duplicate records for one id; using the first"
            )
            continue
        by_id[record.video_id] = record

    state.returned += len(by_id)
    answered = {v.video_id for v in batch} - unresolved
    state.not_held += len(answered - set(by_id))

    for video in batch:
        matched = by_id.get(video.video_id)
        if matched is None:
            continue
        await _apply_to_video(session, video, matched, state)


async def _apply_to_video(
    session: AsyncSession,
    video: VideoDB,
    record: FilmotVideo,
    state: _RunState,
) -> None:
    """Apply the policy to one video, atomically, and record the contribution."""
    channel_known = False
    if record.channel_id:
        channel_known = await ChannelRepository().exists_by_channel_id(
            session, record.channel_id
        )

    outcome = build_filmot_update(
        stored_title=video.title,
        stored_channel_id=video.channel_id,
        stored_duration=video.duration,
        incoming_title=record.title,
        incoming_channel_id=record.channel_id,
        incoming_duration=record.duration,
        channel_known=channel_known,
    )

    for refusal in outcome.refused:
        state.refused_values[refusal] = state.refused_values.get(refusal, 0) + 1
        logger.debug("Filmot refused %s for one video", refusal)
    if outcome.unknown_channel_id:
        state.unknown_channels.add(outcome.unknown_channel_id)

    if not outcome.writes_anything:
        state.held_no_write += 1
        return

    if state.dry_run:
        state.updated += 1
        for field in outcome.fields_written:
            state.field_counts[field] = state.field_counts.get(field, 0) + 1
        return

    applied = await _conditional_update(session, video, outcome.updates)
    if not applied:
        # The gate no longer held: something filled the field between selection
        # and write. Refusing is the correct outcome, not an error.
        state.held_no_write += 1
        logger.debug(
            "Filmot write refused at commit time for one video: a gate no "
            "longer held"
        )
        return

    state.updated += 1
    for field in applied:
        state.field_counts[field] = state.field_counts.get(field, 0) + 1

    await RecoveryProvenanceRepository().record_video(
        session,
        video.video_id,
        RecoverySourceRecord(
            source=FILMOT_SOURCE,
            source_detail=None,
            fields_written=applied,
            # Stamped explicitly because the upsert only advances the timestamp
            # when the record carries one, and a second contribution to the same
            # video is ordinary rather than rare: a run fills the title while the
            # owning channel is still unknown, the channel is synced later, and a
            # later run fills `channel_id`. Left unstamped, that second write kept
            # the first run's timestamp, and `videos.recovery_source` — ordered by
            # `recovered_at DESC` — then credited whichever other source had a
            # newer untouched row. That is ADR-011's 92-row defect arriving through
            # the upsert instead of through an overwrite.
            recovered_at=datetime.now(UTC),
        ),
    )


async def _conditional_update(
    session: AsyncSession, video: VideoDB, updates: dict[str, Any]
) -> list[str]:
    """
    Apply ``updates`` only where each field's gate still holds.

    This is the mechanism behind FR-011b, and the reason fill-only is a
    property rather than a coincidence. The policy decided against values read
    at selection time; between then and now another writer may have filled the
    same field. Re-asserting each gate in the statement's own WHERE clause
    means the database refuses the write rather than this code racing it.

    All of a video's fields move together (FR-011a): one statement, one
    condition, so the row is either updated whole or not at all and the
    recorded field list can never overstate what was applied.

    Returns
    -------
    list[str]
        The fields actually written — empty when the gate no longer held.
    """
    conditions = [VideoDB.video_id == video.video_id]

    if "title" in updates:
        conditions.append(placeholder_title_condition(VideoDB.title))
    if "channel_id" in updates:
        conditions.append(VideoDB.channel_id.is_(None))
        # The channel's existence is a gate like any other, and the only one
        # that was once checked in Python without being re-asserted here. A
        # channel deleted between the two raised a foreign-key violation that
        # no longer belonged to one video: it propagated out of the batch, the
        # run aborted, and the batch's already-applied writes rolled back with
        # it. Re-asserting it turns that into an ordinary refusal.
        conditions.append(
            select(ChannelDB.channel_id)
            .where(ChannelDB.channel_id == updates["channel_id"])
            .exists()
        )
    if "duration" in updates:
        conditions.append(VideoDB.duration.is_(None) | (VideoDB.duration == 0))

    result = await session.execute(update(VideoDB).where(*conditions).values(**updates))
    return sorted(updates) if result.rowcount else []


def _classify(exc: FilmotError) -> str:
    """Name a systemic failure so the summary can explain itself."""
    status = getattr(exc, "status_code", None)
    if status in (401, 403):
        return "credential_rejected"
    if status == 429:
        return "rate_limited"
    return "source_unusable"


def _log_summary(result: FilmotRecoveryResult) -> None:
    """End-of-run summary at informational level (FR-027)."""
    logger.info(
        "Filmot recovery complete in %.1fs: %d submitted, %d returned, "
        "%d updated, %d held with nothing to write, %d not held, "
        "%d unresolved, %d not attempted",
        result.duration_seconds,
        result.submitted,
        result.returned,
        result.updated,
        result.held_no_write,
        result.not_held,
        result.unresolved,
        result.not_attempted,
    )
    if not result.reconciles and not result.unresolved:
        logger.warning(
            "Filmot run does not reconcile: %d updated + %d held != %d returned. "
            "Something was dropped silently.",
            result.updated,
            result.held_no_write,
            result.returned,
        )
