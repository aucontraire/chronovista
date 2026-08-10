"""Keyset pagination must actually seek, and callers must actually advance (#204).

``OFFSET n`` makes PostgreSQL walk and discard n rows to reach each window, so
per-batch cost grows with depth and a full table walk costs O(rows²). #202 hit
this in the entity mention scan; #204 is the same defect in four other loops.

Two things make this hard to test, both learned in #202:

* **OFFSET and keyset return identical rows for the first page.** A test that
  only checks returned values passes against either implementation, so the
  emitted SQL has to be asserted directly.
* **A mock that accepts a cursor and ignores it passes whether or not the
  cursor advances.** Every stub here honours the cursor, and the fakes below
  fail loudly rather than hanging if a caller stops advancing it — an
  unbounded loop in a test suite reads as a hung machine, not a bug.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import Video as VideoDB
from chronovista.models.video import VideoCreate, VideoUpdate
from chronovista.repositories.base import BaseSQLAlchemyRepository

pytestmark = pytest.mark.asyncio


class _VideoRepo(BaseSQLAlchemyRepository[VideoDB, VideoCreate, VideoUpdate]):
    def __init__(self) -> None:
        super().__init__(VideoDB)


def _capturing_session() -> tuple[MagicMock, list[Any]]:
    """Session that records every statement and returns no rows."""
    captured: list[Any] = []
    session = MagicMock(spec=AsyncSession)

    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = []
    result.scalars.return_value = scalars

    async def _execute(stmt: Any, *a: Any, **kw: Any) -> Any:
        captured.append(stmt)
        return result

    session.execute = AsyncMock(side_effect=_execute)
    return session, captured


def _sql(stmt: Any) -> str:
    return " ".join(str(stmt.compile()).split()).lower()


class TestEmittedSql:
    """The plan, not the rows — the two are indistinguishable on page one."""

    async def test_no_offset_is_emitted(self) -> None:
        session, captured = _capturing_session()
        await _VideoRepo().get_multi_after(session, after="abc", limit=10)

        assert "offset" not in _sql(
            captured[0]
        ), "OFFSET is back: the walk is quadratic in table size again"

    async def test_seeks_on_the_primary_key(self) -> None:
        session, captured = _capturing_session()
        await _VideoRepo().get_multi_after(session, after="abc", limit=10)

        sql = _sql(captured[0])
        assert "videos.video_id >" in sql, f"no keyset predicate in: {sql}"

    async def test_orders_by_the_primary_key(self) -> None:
        """Without a total order the cursor cannot be resumed from."""
        session, captured = _capturing_session()
        await _VideoRepo().get_multi_after(session, after="abc", limit=10)

        assert "order by videos.video_id asc" in _sql(captured[0])

    async def test_first_page_has_no_predicate(self) -> None:
        """`after=None` starts at the beginning rather than excluding rows."""
        session, captured = _capturing_session()
        await _VideoRepo().get_multi_after(session, after=None, limit=10)

        sql = _sql(captured[0])
        assert "videos.video_id >" not in sql
        assert "order by videos.video_id asc" in sql
        assert "limit" in sql


class TestCompositeKeyIsRefused:
    async def test_composite_primary_key_raises(self) -> None:
        """Ordering by only the first column of a composite key would silently
        skip or repeat rows sharing that value — wrong, not merely slow."""
        from chronovista.db.models import UserVideo

        class _UserVideoRepo(BaseSQLAlchemyRepository[UserVideo, Any, Any]):
            def __init__(self) -> None:
                super().__init__(UserVideo)

        session, _ = _capturing_session()
        with pytest.raises(NotImplementedError, match="single-column primary key"):
            await _UserVideoRepo().get_multi_after(session, after=None, limit=10)


class _FakeKeysetRepo:
    """Repository double that genuinely honours the cursor.

    Returning a fixed sequence regardless of `after` — which is what the
    existing service stubs do — cannot distinguish a caller that advances the
    cursor from one that does not. This one can, and refuses to loop forever.
    """

    MAX_CALLS = 50

    def __init__(self, ids: list[str]) -> None:
        self.ids = sorted(ids)
        self.cursors: list[str | None] = []

    async def get_multi_after(
        self, session: Any, *, after: str | None = None, limit: int = 100
    ) -> list[Any]:
        self.cursors.append(after)
        if len(self.cursors) > self.MAX_CALLS:
            raise AssertionError(
                f"cursor did not advance: {self.MAX_CALLS} calls, "
                f"last cursors {self.cursors[-3:]}. A caller that fails to "
                "advance would otherwise hang rather than fail."
            )
        remaining = [i for i in self.ids if after is None or i > after]
        rows = []
        for vid in remaining[:limit]:
            row = MagicMock()
            row.video_id = vid
            row.channel_id = "UCtest"
            rows.append(row)
        return rows


class TestTheFakeItself:
    """A test double this load-bearing needs its own proof."""

    async def test_walks_every_row_exactly_once(self) -> None:
        repo = _FakeKeysetRepo([f"vid{i:03d}" for i in range(25)])
        seen: list[str] = []
        after: str | None = None
        while True:
            batch = await repo.get_multi_after(None, after=after, limit=10)
            if not batch:
                break
            seen.extend(r.video_id for r in batch)
            after = batch[-1].video_id

        assert seen == sorted(seen)
        assert len(seen) == len(set(seen)) == 25
        assert repo.cursors == [None, "vid009", "vid019", "vid024"]

    async def test_a_non_advancing_caller_fails_instead_of_hanging(self) -> None:
        repo = _FakeKeysetRepo([f"vid{i:03d}" for i in range(25)])
        with pytest.raises(AssertionError, match="cursor did not advance"):
            while True:
                batch = await repo.get_multi_after(None, after=None, limit=10)
                if not batch:
                    break


class TestRealCallSitesAdvanceTheCursor:
    """The call sites, against a double that can tell the difference.

    The service's own suite stubs the repository with a fixed `side_effect`
    sequence, which returns the same batches no matter what cursor it is
    handed — so it passes whether or not the caller advances. These drive the
    real methods through a cursor-honouring fake instead, where failing to
    advance means revisiting the first batch forever.
    """

    async def test_count_placeholder_videos_walks_the_whole_table(self) -> None:
        from chronovista.services.takeout_recovery_service import (
            TakeoutRecoveryService,
        )

        # Batch size inside the method is 100; 250 rows forces three windows
        # plus the terminating empty read.
        ids = [f"vid{i:04d}" for i in range(250)]
        repo = _FakeKeysetRepo(ids)
        service = TakeoutRecoveryService(
            video_repository=repo,  # type: ignore[arg-type]
            channel_repository=MagicMock(),
        )

        count = await service.count_placeholder_videos(MagicMock())

        # The fake's titles are MagicMocks, not placeholder strings, so the
        # count is not the assertion — the walk is.
        assert isinstance(count, int)
        assert repo.cursors == [None, "vid0099", "vid0199", "vid0249"], (
            "the cursor sequence should be the last id of each batch; "
            f"got {repo.cursors}"
        )

    async def test_count_placeholder_channels_walks_the_whole_table(self) -> None:
        from chronovista.services.takeout_recovery_service import (
            TakeoutRecoveryService,
        )

        class _FakeChannelRepo(_FakeKeysetRepo):
            async def get_multi_after(
                self, session: Any, *, after: str | None = None, limit: int = 100
            ) -> list[Any]:
                rows = await super().get_multi_after(session, after=after, limit=limit)
                for row in rows:
                    row.channel_id = row.video_id
                return rows

        ids = [f"UC{i:04d}" for i in range(250)]
        repo = _FakeChannelRepo(ids)
        service = TakeoutRecoveryService(
            video_repository=MagicMock(),
            channel_repository=repo,  # type: ignore[arg-type]
        )

        await service.count_placeholder_channels(MagicMock())

        assert repo.cursors == [None, "UC0099", "UC0199", "UC0249"]

    async def test_image_cache_warm_videos_walks_the_whole_table(
        self, tmp_path: Any
    ) -> None:
        """The fourth site, which builds its own statement rather than using
        the repository.

        `warm_videos` is mocked out wholesale everywhere else in the suite, so
        its loop body had no coverage at all — the conversion would otherwise
        be unverified. Driven in dry-run so nothing is fetched over the
        network.
        """
        from chronovista.services.image_cache import (
            ImageCacheConfig,
            ImageCacheService,
        )

        ids = [f"vid{i:05d}" for i in range(2500)]  # three 1,000-row windows
        cursors: list[str | None] = []

        def _after_from(stmt: Any) -> str | None:
            """Recover the bound cursor from the compiled statement."""
            params = stmt.compile().params
            for key, value in params.items():
                if "video_id" in key and isinstance(value, str):
                    return value
            return None

        session = MagicMock(spec=AsyncSession)
        calls = {"n": 0}

        async def _execute(stmt: Any, *a: Any, **kw: Any) -> Any:
            calls["n"] += 1
            result = MagicMock()
            sql = " ".join(str(stmt).split()).lower()
            if "count" in sql:
                result.scalar_one.return_value = len(ids)
                return result
            after = _after_from(stmt)
            cursors.append(after)
            if len(cursors) > 20:
                raise AssertionError(f"cursor did not advance: {cursors[-3:]}")
            remaining = [i for i in ids if after is None or i > after]
            scalars = MagicMock()
            scalars.all.return_value = remaining[:1000]
            result.scalars.return_value = scalars
            return result

        session.execute = AsyncMock(side_effect=_execute)

        config = ImageCacheConfig(
            cache_dir=tmp_path,
            channels_dir=tmp_path / "channels",
            videos_dir=tmp_path / "videos",
        )
        result = await ImageCacheService(config).warm_videos(
            session, dry_run=True, delay=0
        )

        assert result.downloaded == 2500, "every row should have been visited"
        assert cursors == [None, "vid00999", "vid01999", "vid02499"]
