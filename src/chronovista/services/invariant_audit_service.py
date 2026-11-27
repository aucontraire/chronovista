"""Read-only checks that the library's data obeys the invariant register.

Each check verifies one entry in ``docs/architecture/invariants.md`` and returns the
keys of the rows that break it. The audit is the before-and-after gate for changes to
data (register entry D4): save a run before a repair, compare after, and anything new
fails the comparison even when the total fell.

Nothing here writes. The command opens its session on the database's read-only
connections (``db_manager.session(read_only=True)``). The runner reads every check from
one snapshot, and runs each check inside a savepoint it marks read-only and always rolls
back, so a check that tries to write fails as an ``error`` and the next check still runs.

Keys can be library identifiers (a transcript's key is its video ID and language), so
saved runs belong outside the repository, and logs carry IDs and counts only.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista import __version__
from chronovista.repositories.canonical_tag_repository import CanonicalTagRepository
from chronovista.repositories.entity_mention_repository import EntityMentionRepository
from chronovista.repositories.transcript_segment_repository import (
    TranscriptSegmentRepository,
)
from chronovista.services.mention_repair_service import MentionRepairService

logger = logging.getLogger(__name__)

CheckRun = Callable[[AsyncSession], Awaitable[dict[str, set[str]]]]
"""A check's query: the violating keys, by the ID of each check it serves.

A run normally serves one check. M1 and M2 share one pass over the mention repair's
plan, so they share one run, which the runner calls once.
"""

Outcome = Literal["holds", "violated", "error"]

EXIT_CLEAN = 0
EXIT_VIOLATED = 1
EXIT_INCOMPLETE = 75
"""A check could not run (``EX_TEMPFAIL``; not 2, which Click uses for usage errors)."""

_CHECK_ID = re.compile(r"^[A-Z][0-9]+-[a-z0-9-]+$")
_ENTRY_ID = re.compile(r"^[A-Z][0-9]+$")


class InvariantCheck(BaseModel):
    """One named data check and the register entry it verifies."""

    model_config = ConfigDict(frozen=True)

    check_id: str
    register_entry: str
    rule: str
    rule_version: int = Field(ge=1)
    key_kind: Literal["row_id", "library_identifier"]
    run: CheckRun = Field(exclude=True)

    @field_validator("check_id")
    @classmethod
    def _check_id_shape(cls, value: str) -> str:
        if not _CHECK_ID.match(value):
            raise ValueError(f"check ID {value!r} does not match {_CHECK_ID.pattern}")
        return value

    @field_validator("register_entry")
    @classmethod
    def _entry_shape(cls, value: str) -> str:
        if not _ENTRY_ID.match(value):
            raise ValueError(
                f"register entry {value!r} does not match {_ENTRY_ID.pattern}"
            )
        return value


class CheckResult(BaseModel):
    """What one check found."""

    check_id: str
    outcome: Outcome
    violation_count: int = 0
    keys: set[str] = Field(default_factory=set)
    error: str | None = None
    rule_version: int
    key_kind: Literal["row_id", "library_identifier"]
    seconds: float


class AuditRun(BaseModel):
    """One audit run; saved with ``--save`` as a baseline."""

    started_at: datetime
    results: list[CheckResult]
    chronovista_version: str
    database_hash: str


class CheckComparison(BaseModel):
    """One check, compared with a baseline."""

    check_id: str
    status: Literal["compared", "not_compared"]
    reason: str | None = None
    new: int = 0
    resolved: int = 0
    sample_new: list[str] = Field(default_factory=list)
    hidden_keys: bool = False


def validate_registry(checks: Sequence[InvariantCheck]) -> tuple[InvariantCheck, ...]:
    """Reject duplicate check IDs; return the registry as a tuple."""
    seen: set[str] = set()
    for check in checks:
        if check.check_id in seen:
            raise ValueError(f"duplicate check ID {check.check_id!r}")
        seen.add(check.check_id)
    return tuple(checks)


def select_checks(
    registry: Sequence[InvariantCheck], requested: Sequence[str] | None
) -> list[InvariantCheck]:
    """The checks a ``--check`` list names, by check ID or register entry ID.

    Raises ``ValueError`` naming an unknown ID.
    """
    if not requested:
        return list(registry)
    chosen: list[InvariantCheck] = []
    for wanted in requested:
        matches = [c for c in registry if wanted in (c.check_id, c.register_entry)]
        if not matches:
            raise ValueError(wanted)
        chosen.extend(c for c in matches if c not in chosen)
    return chosen


def database_hash(database_url: str) -> str:
    """A short, one-way identity for the database a run came from.

    Built from host, port and database name only, so it never carries a password.
    A URL without a port means PostgreSQL's default, so both spellings agree.
    """
    url = make_url(database_url)
    identity = f"{url.host}:{url.port or 5432}/{url.database}"
    return hashlib.sha256(identity.encode()).hexdigest()[:16]


class _Ran(BaseModel):
    """What one call of a check's run produced."""

    keys_by_check: dict[str, set[str]] | None = None
    error: str | None = None
    ended_transaction: bool = False
    seconds: float


async def run_checks(
    session: AsyncSession,
    checks: Sequence[InvariantCheck],
    *,
    database_url: str,
    take_snapshot: bool = True,
) -> AuditRun:
    """Run ``checks`` read-only from one snapshot and report each one.

    The first statement of the transaction fixes a repeatable-read, read-only
    snapshot, so every check sees the same data; ``session`` must not have run a
    query yet. Tests that seed rows in the same session pass ``take_snapshot=False``
    and rely on their own transaction instead.

    Each check runs in a savepoint that is made read-only and always rolled back. A
    check that fails, including one that tries to write, is an ``error`` and the
    others still run. A check that ends the transaction itself (``commit`` or
    ``rollback``) loses the snapshot, so it and every later check are errors.
    """
    if take_snapshot:
        if session.in_transaction():
            raise RuntimeError(
                "run_checks needs a fresh session to take its snapshot; "
                "pass take_snapshot=False only in tests"
            )
        await session.execute(
            text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        )
    started_at = datetime.now(UTC)
    ran: dict[int, _Ran] = {}
    results: list[CheckResult] = []
    snapshot_lost = False
    for check in checks:
        if snapshot_lost:
            results.append(
                _error_result(
                    check, "not run: an earlier check ended the transaction", 0.0
                )
            )
            continue
        run_key = id(check.run)
        first_use = run_key not in ran
        if first_use:
            ran[run_key] = await _run_one(session, check.run)
        outcome = ran[run_key]
        # A shared run's time is recorded on the first check it serves only.
        seconds = outcome.seconds if first_use else 0.0
        if outcome.ended_transaction:
            snapshot_lost = True
        if outcome.error is not None or outcome.keys_by_check is None:
            results.append(_error_result(check, outcome.error or "no result", seconds))
        elif check.check_id not in outcome.keys_by_check:
            # A typo'd or mismatched key would otherwise read as "holds".
            results.append(
                _error_result(
                    check, "its run returned no result for this check", seconds
                )
            )
        else:
            keys = {str(k) for k in outcome.keys_by_check[check.check_id]}
            results.append(
                CheckResult(
                    check_id=check.check_id,
                    outcome="violated" if keys else "holds",
                    violation_count=len(keys),
                    keys=keys,
                    rule_version=check.rule_version,
                    key_kind=check.key_kind,
                    seconds=seconds,
                )
            )
        logger.info(
            "audit check %s: %s (%d) in %.1fs",
            check.check_id,
            results[-1].outcome,
            results[-1].violation_count,
            seconds,
        )
    return AuditRun(
        started_at=started_at,
        results=results,
        chronovista_version=__version__,
        database_hash=database_hash(database_url),
    )


def _error_result(check: InvariantCheck, error: str, seconds: float) -> CheckResult:
    return CheckResult(
        check_id=check.check_id,
        outcome="error",
        error=error,
        rule_version=check.rule_version,
        key_kind=check.key_kind,
        seconds=seconds,
    )


async def _run_one(session: AsyncSession, run: CheckRun) -> _Ran:
    """Run one check inside a read-only savepoint that is always rolled back.

    If the check ended the transaction itself, the savepoint is already gone; that
    is reported rather than raised, so the run can still finish.
    """
    began = time.monotonic()
    savepoint = await session.begin_nested()
    keys_by_check: dict[str, set[str]] | None = None
    error: str | None = None
    try:
        await session.execute(text("SET TRANSACTION READ ONLY"))
        keys_by_check = await run(session)
    except Exception as exc:  # noqa: BLE001 — a failing check is a result, not a crash
        error = _describe_error(exc)
    if not savepoint.is_active:
        return _Ran(
            error="the check ended the transaction (commit or rollback)",
            ended_transaction=True,
            seconds=time.monotonic() - began,
        )
    await savepoint.rollback()
    return _Ran(
        keys_by_check=keys_by_check, error=error, seconds=time.monotonic() - began
    )


def _describe_error(exc: Exception) -> str:
    """The error's class and SQLSTATE, never its message: messages and parameters
    can hold row data.
    """
    original = getattr(exc, "orig", None)
    cause = getattr(original, "__cause__", None)
    sqlstate = getattr(original, "sqlstate", None)
    name = type(cause or original or exc).__name__
    return f"{name} (SQLSTATE {sqlstate})" if sqlstate else name


def compare(
    baseline: AuditRun,
    current: AuditRun,
    *,
    sample: int,
    show_library_keys: bool,
) -> list[CheckComparison]:
    """What ``current`` found that ``baseline`` did not, and what it no longer finds.

    A check is "not compared" when it is missing from either run, errored in either
    run, or its rule version changed between them. New-key samples are sorted, and
    keys built from library identifiers are left out unless ``show_library_keys``.
    """
    before = {r.check_id: r for r in baseline.results}
    after = {r.check_id: r for r in current.results}
    comparisons: list[CheckComparison] = []
    for check_id in sorted(before.keys() | after.keys()):
        old, new = before.get(check_id), after.get(check_id)
        reason = _not_compared_reason(old, new)
        if reason is not None:
            comparisons.append(
                CheckComparison(check_id=check_id, status="not_compared", reason=reason)
            )
            continue
        assert old is not None and new is not None
        added = sorted(new.keys - old.keys)
        hidden = new.key_kind == "library_identifier" and not show_library_keys
        comparisons.append(
            CheckComparison(
                check_id=check_id,
                status="compared",
                new=len(added),
                resolved=len(old.keys - new.keys),
                sample_new=[] if hidden else added[:sample],
                hidden_keys=hidden and bool(added),
            )
        )
    return comparisons


def _not_compared_reason(
    old: CheckResult | None, new: CheckResult | None
) -> str | None:
    if old is None:
        return "missing from baseline"
    if new is None:
        return "missing from current run"
    if old.outcome == "error" or new.outcome == "error":
        return "errored"
    if old.rule_version != new.rule_version:
        return f"rule changed: v{old.rule_version} → v{new.rule_version}"
    return None


def exit_code(
    run: AuditRun, comparisons: Sequence[CheckComparison] | None = None
) -> int:
    """The command's exit status. An error always wins, so a check that could not
    run never reads as clean. In compare mode, a check that could not be compared
    and is violated now also exits incomplete, rather than passing unseen.
    """
    if any(r.outcome == "error" for r in run.results):
        return EXIT_INCOMPLETE
    if comparisons is not None:
        violated_now = {r.check_id for r in run.results if r.outcome == "violated"}
        # Not compared, yet violated now: nothing says whether those are new, so the
        # gate cannot pass. That covers a baseline error, a new check and a changed
        # rule. (An error in this run already returned above.)
        if any(
            c.status == "not_compared" and c.check_id in violated_now
            for c in comparisons
        ):
            return EXIT_INCOMPLETE
        return EXIT_VIOLATED if any(c.new for c in comparisons) else EXIT_CLEAN
    return (
        EXIT_VIOLATED
        if any(r.outcome == "violated" for r in run.results)
        else EXIT_CLEAN
    )


# -- The checks. Each rule's SQL lives in the repository that owns the data, next to
# the rule it mirrors; these adapters only name the result.

_segments = TranscriptSegmentRepository()
_tags = CanonicalTagRepository()
_mentions = EntityMentionRepository()


async def _t1_flag(session: AsyncSession) -> dict[str, set[str]]:
    return {"T1-correction-flag": await _segments.correction_flag_mismatches(session)}


async def _t1_count(session: AsyncSession) -> dict[str, set[str]]:
    return {"T1-correction-count": await _segments.correction_count_mismatches(session)}


async def _t7(session: AsyncSession) -> dict[str, set[str]]:
    return {"T7-stored-full-text": await _segments.stale_full_texts(session)}


async def _g1(session: AsyncSession) -> dict[str, set[str]]:
    return {"G1-alias-placement": await _tags.alias_placement_violations(session)}


async def _g2(session: AsyncSession) -> dict[str, set[str]]:
    return {"G2-merge-state": await _tags.merge_state_violations(session)}


async def _g3(session: AsyncSession) -> dict[str, set[str]]:
    return {"G3-tag-counters": await _tags.tag_counter_drift(session)}


async def _c3(session: AsyncSession) -> dict[str, set[str]]:
    return {"C3-entity-counters": await _mentions.entity_counter_drift(session)}


async def _m9(session: AsyncSession) -> dict[str, set[str]]:
    return {"M9-mention-shape": await _mentions.mention_shape_violations(session)}


async def _m1_m2(session: AsyncSession) -> dict[str, set[str]]:
    found = await MentionRepairService().findings(session)
    return {
        "M1-mention-reads": {str(mention_id) for mention_id in found.stale},
        "M2-one-row-per-occurrence": {
            str(mention_id) for mention_id in found.duplicates
        },
    }


def _check(
    check_id: str,
    rule: str,
    run: CheckRun,
    key_kind: Literal["row_id", "library_identifier"] = "row_id",
) -> InvariantCheck:
    return InvariantCheck(
        check_id=check_id,
        register_entry=check_id.split("-", 1)[0],
        rule=rule,
        rule_version=1,
        key_kind=key_kind,
        run=run,
    )


REGISTRY: tuple[InvariantCheck, ...] = validate_registry(
    [
        _check(
            "T1-correction-flag",
            "A transcript's correction flag equals whether any of its segments is corrected.",
            _t1_flag,
            "library_identifier",
        ),
        _check(
            "T1-correction-count",
            "A transcript's correction count equals its currently corrected segments.",
            _t1_count,
            "library_identifier",
        ),
        _check(
            "T7-stored-full-text",
            "A corrected transcript's stored full text equals its segments' effective text.",
            _t7,
            "library_identifier",
        ),
        _check(
            "G1-alias-placement",
            "No tag alias sits on a merged tag, and an active tag's aliases share its form.",
            _g1,
        ),
        _check(
            "G2-merge-state",
            "A merged tag points to another tag and owns nothing; an entity has one active tag.",
            _g2,
        ),
        _check(
            "G3-tag-counters",
            "An active tag's stored alias and video counts equal a recount.",
            _g3,
        ),
        _check(
            "C3-entity-counters",
            "An entity's stored mention and video counts equal a recount by the one rule.",
            _c3,
        ),
        _check(
            "M9-mention-shape",
            "A mention's row shape matches its method, and its segments' video and language.",
            _m9,
        ),
        _check(
            "M1-mention-reads",
            "A transcript mention reads as its text (the repair's candidate transcripts).",
            _m1_m2,
        ),
        _check(
            "M2-one-row-per-occurrence",
            "No entity has two transcript mentions over one occurrence.",
            _m1_m2,
        ),
    ]
)
