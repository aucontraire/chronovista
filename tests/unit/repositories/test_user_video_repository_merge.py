"""Constitution SQL-shape tests for the identity merge (Feature 060, T017).

Mock strategy: ``MagicMock(spec=AsyncSession)`` with ``AsyncMock`` execute —
we capture and compile the emitted statements to inspect the SET/DELETE shape,
not just return values — a column absent from SET returns success while
writing nothing.

NOTE: the substring assertions below are coupled to SQLAlchemy's compiler output
(e.g. ``liked=(user_videos.liked or (select``) and a SQLAlchemy version bump can
break them *spuriously*. They are a fast structural tripwire, NOT the semantic
authority — the merge's actual per-field GREATEST/OR behavior is proven against a
real database by ``tests/integration/test_identity_dedup.py``. If these break,
check that integration test first to tell a real regression from a formatting
change.
"""

from __future__ import annotations

import re
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.repositories.user_video_repository import UserVideoRepository

pytestmark = pytest.mark.asyncio

FROM_ID = "takeout_user"
TO_ID = "UCzYTmeK-6v3DcJ6hzRh1q9w"


def _mock_session() -> MagicMock:
    session = MagicMock(spec=AsyncSession)
    result = MagicMock()
    result.rowcount = 0
    session.execute = AsyncMock(return_value=result)
    return session


def _sql(stmt) -> str:
    """Compile to Postgres SQL with whitespace collapsed for stable matching."""
    raw = str(
        stmt.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    return re.sub(r"\s+", " ", raw).lower()


class TestMergeSqlShape:
    async def test_merge_update_binds_each_column_to_its_merge_formula(self) -> None:
        repo = UserVideoRepository()
        session = _mock_session()

        await repo.merge_user_identity(session, from_user_id=FROM_ID, to_user_id=TO_ID)

        # 3 statements: merge-overlaps UPDATE, delete-overlap DELETE, re-key UPDATE
        assert session.execute.await_count == 3
        merge_sql = _sql(session.execute.await_args_list[0].args[0])

        assert merge_sql.startswith("update user_videos set")
        # Bind the *formula* to the *column* — a regression that swapped GREATEST
        # for a naive overwrite, or OR for AND, would pass a "keyword present
        # somewhere" check but must fail here.
        assert "watched_at=greatest(user_videos.watched_at," in merge_sql
        assert "rewatch_count=greatest(user_videos.rewatch_count," in merge_sql
        assert "liked=(user_videos.liked or (select" in merge_sql
        assert (
            "saved_to_playlist=(user_videos.saved_to_playlist or (select" in merge_sql
        )
        # Only overlapping survivor rows are merged (EXISTS on the placeholder).
        assert f"user_videos.user_id = '{TO_ID}'".lower() in merge_sql
        assert "exists (select" in merge_sql

    async def test_delete_targets_only_overlapping_placeholder_rows(self) -> None:
        repo = UserVideoRepository()
        session = _mock_session()

        await repo.merge_user_identity(session, from_user_id=FROM_ID, to_user_id=TO_ID)

        delete_sql = _sql(session.execute.await_args_list[1].args[0])
        assert delete_sql.startswith("delete from user_videos")
        # Placeholder-scoped AND overlap-scoped: deletes only placeholder rows
        # whose video_id already exists under the survivor. A regression that
        # dropped the overlap subquery (deleting ALL placeholder rows before the
        # re-key merged them in) would fail this assertion.
        assert f"user_videos.user_id = '{FROM_ID}'".lower() in delete_sql
        assert (
            f"user_videos.video_id in (select user_videos.video_id from "
            f"user_videos where user_videos.user_id = '{TO_ID}'".lower()
        ) in delete_sql

    async def test_rekey_sets_user_id_to_survivor(self) -> None:
        repo = UserVideoRepository()
        session = _mock_session()

        await repo.merge_user_identity(session, from_user_id=FROM_ID, to_user_id=TO_ID)

        rekey_sql = _sql(session.execute.await_args_list[2].args[0])
        assert rekey_sql.startswith("update user_videos set user_id")
        assert f"user_videos.user_id = '{FROM_ID}'".lower() in rekey_sql
        assert f"'{TO_ID}'".lower() in rekey_sql
