"""Repair of aliases stranded on merged canonical tags (#184).

A merge reassigns the source's aliases to the target and rewrites their
``normalized_form``. Aliases that were never moved sit on a deprecated tag: the
canonical relationship cannot reach them, because a merged tag holds no
``entity_id``, while anything matching on ``tag_aliases.normalized_form`` still
finds them. That is why the two entity-association paths disagreed, and why the
rows are invisible in the UI — canonical-tag search filters to active tags.

These tests pin the properties that make the repair safe to run against real
data: it reads the destination rather than guessing, it refuses the cases it
cannot resolve, a dry run writes nothing, and it is idempotent.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from uuid_utils import uuid7

from chronovista.services.tag_management import TagManagementService

pytestmark = pytest.mark.asyncio


def _uuid() -> uuid.UUID:
    return uuid.UUID(bytes=uuid7().bytes)


def _alias(raw_form: str, canonical_tag_id: uuid.UUID, normalized: str) -> MagicMock:
    a = MagicMock()
    a.id = _uuid()
    a.raw_form = raw_form
    a.canonical_tag_id = canonical_tag_id
    a.normalized_form = normalized
    return a


def _tag(
    normalized: str, status: str, merged_into_id: uuid.UUID | None = None
) -> MagicMock:
    t = MagicMock()
    t.id = _uuid()
    t.normalized_form = normalized
    t.status = status
    t.merged_into_id = merged_into_id
    return t


def _service(
    orphan_rows: list[tuple[MagicMock, MagicMock]],
    targets: dict[uuid.UUID, MagicMock | None],
) -> tuple[TagManagementService, MagicMock]:
    """Service wired so the orphan query returns *orphan_rows*."""
    log_repo = MagicMock()
    created = MagicMock()
    created.id = _uuid()
    log_repo.create = AsyncMock(return_value=created)

    service = TagManagementService(
        canonical_tag_repo=MagicMock(),
        tag_alias_repo=MagicMock(),
        named_entity_repo=MagicMock(),
        entity_alias_repo=MagicMock(),
        operation_log_repo=log_repo,
    )

    session = MagicMock(spec=AsyncSession)
    result = MagicMock()
    result.all.return_value = orphan_rows
    session.execute = AsyncMock(return_value=result)
    session.get = AsyncMock(side_effect=lambda _model, tid: targets.get(tid))
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return service, session


class TestOrphanRepair:
    async def test_moves_the_alias_to_the_recorded_merge_target(self) -> None:
        target = _tag("benjamin netanyahu", "active")
        source = _tag("bibi", "merged", merged_into_id=target.id)
        alias = _alias("Bibi", source.id, "bibi")

        service, session = _service([(alias, source)], {target.id: target})
        report = await service.repair_orphaned_aliases(session, dry_run=False)

        assert report.repaired_count == 1
        assert report.skipped_count == 0
        moved = report.repaired[0]
        # The destination is READ from merged_into_id, never inferred from the
        # alias text — inferring is what produced the mess in the first place.
        assert moved.to_canonical_tag_id == target.id
        assert moved.to_normalized_form == "benjamin netanyahu"
        assert moved.from_normalized_form == "bibi"

    async def test_the_update_sets_both_columns(self) -> None:
        # Asserting the report is not enough: the report can be correct while
        # the UPDATE omits normalized_form, leaving the alias discoverable under
        # its old form and the two association paths still in disagreement.
        # Per the Constitution's Cross-Feature Data Contract Verification, an
        # UPDATE test inspects the SET clause rather than the return value.
        target = _tag("benjamin netanyahu", "active")
        source = _tag("bibi", "merged", merged_into_id=target.id)
        alias = _alias("Bibi", source.id, "bibi")

        service, session = _service([(alias, source)], {target.id: target})
        await service.repair_orphaned_aliases(session, dry_run=False)

        # Match on the statement STARTING with UPDATE. A substring test picks up
        # the SELECT as well, because its column list contains `updated_at` —
        # and that select mentions `normalized_form`, so the assertion below
        # would pass against the wrong statement and catch nothing.
        updates = [
            str(call.args[0]).strip()
            for call in session.execute.await_args_list
            if call.args and str(call.args[0]).strip().upper().startswith("UPDATE")
        ]
        assert updates, "expected an UPDATE against tag_aliases"
        set_clause = updates[0].split("WHERE")[0]
        assert "canonical_tag_id" in set_clause
        assert "normalized_form" in set_clause

    async def test_dry_run_writes_nothing_and_logs_nothing(self) -> None:
        target = _tag("target", "active")
        source = _tag("source", "merged", merged_into_id=target.id)
        alias = _alias("Source", source.id, "source")

        service, session = _service([(alias, source)], {target.id: target})
        report = await service.repair_orphaned_aliases(session, dry_run=True)

        assert report.dry_run is True
        assert report.repaired_count == 1  # still reports what it would do
        assert report.operation_id is None
        session.commit.assert_not_awaited()
        session.rollback.assert_awaited()

    async def test_applied_run_logs_the_operation(self) -> None:
        # The orphans exist because something skipped the operation log.
        # Repairing them without one would repeat that mistake and leave the
        # change unreversible.
        target = _tag("target", "active")
        source = _tag("source", "merged", merged_into_id=target.id)
        alias = _alias("Source", source.id, "source")

        service, session = _service([(alias, source)], {target.id: target})
        report = await service.repair_orphaned_aliases(session, dry_run=False)

        assert report.operation_id is not None
        session.commit.assert_awaited()

    async def test_rollback_data_can_restore_the_previous_state(self) -> None:
        target = _tag("target", "active")
        source = _tag("source", "merged", merged_into_id=target.id)
        alias = _alias("Source", source.id, "source")

        service, session = _service([(alias, source)], {target.id: target})
        await service.repair_orphaned_aliases(session, dry_run=False)

        log_call = service._operation_log_repo.create.await_args  # type: ignore[attr-defined]
        rollback: dict[str, Any] = log_call.kwargs["obj_in"].rollback_data
        entry = rollback["aliases"][0]
        assert entry["alias_id"] == str(alias.id)
        assert entry["previous_canonical_tag_id"] == str(source.id)
        assert entry["previous_normalized_form"] == "source"

    async def test_is_idempotent_when_there_is_nothing_to_repair(self) -> None:
        service, session = _service([], {})
        report = await service.repair_orphaned_aliases(session, dry_run=False)

        assert report.repaired_count == 0
        assert report.skipped_count == 0
        assert report.operation_id is None  # nothing happened, nothing logged


class TestOrphanRepairRefusals:
    """Cases the repair reports rather than guessing at."""

    async def test_skips_a_merged_tag_with_no_merged_into_id(self) -> None:
        source = _tag("source", "merged", merged_into_id=None)
        alias = _alias("Source", source.id, "source")

        service, session = _service([(alias, source)], {})
        report = await service.repair_orphaned_aliases(session, dry_run=False)

        assert report.repaired_count == 0
        assert report.skipped_count == 1
        assert "merged_into_id" in report.skipped[0].reason

    async def test_skips_when_the_merge_target_no_longer_exists(self) -> None:
        missing_id = _uuid()
        source = _tag("source", "merged", merged_into_id=missing_id)
        alias = _alias("Source", source.id, "source")

        service, session = _service([(alias, source)], {missing_id: None})
        report = await service.repair_orphaned_aliases(session, dry_run=False)

        assert report.repaired_count == 0
        assert report.skipped_count == 1
        assert "no longer exists" in report.skipped[0].reason

    async def test_skips_a_chained_merge_rather_than_following_it(self) -> None:
        # Following a chain needs cycle detection and a decision about which
        # link is authoritative. Surfacing it is honest; guessing is not.
        final = _tag("final", "active")
        middle = _tag("middle", "merged", merged_into_id=final.id)
        source = _tag("source", "merged", merged_into_id=middle.id)
        alias = _alias("Source", source.id, "source")

        service, session = _service([(alias, source)], {middle.id: middle})
        report = await service.repair_orphaned_aliases(session, dry_run=False)

        assert report.repaired_count == 0
        assert report.skipped_count == 1
        assert "chained" in report.skipped[0].reason

    async def test_one_bad_orphan_does_not_block_the_good_ones(self) -> None:
        good_target = _tag("good target", "active")
        good_source = _tag("good source", "merged", merged_into_id=good_target.id)
        good_alias = _alias("Good", good_source.id, "good source")

        bad_source = _tag("bad source", "merged", merged_into_id=None)
        bad_alias = _alias("Bad", bad_source.id, "bad source")

        service, session = _service(
            [(good_alias, good_source), (bad_alias, bad_source)],
            {good_target.id: good_target},
        )
        report = await service.repair_orphaned_aliases(session, dry_run=False)

        assert report.repaired_count == 1
        assert report.skipped_count == 1
        assert report.repaired[0].raw_form == "Good"
