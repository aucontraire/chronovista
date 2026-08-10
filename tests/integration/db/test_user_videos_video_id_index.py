"""`user_videos.video_id` must stay indexed (#161).

The table's primary key is ``(user_id, video_id)``. A predicate on ``video_id``
alone cannot use it — the leading column is absent from the predicate — so the
playlist detail page, which batch-loads the watched flag for its current page
with ``WHERE video_id IN (...)``, scanned the entire table to resolve at most
100 ids. Measured before the fix: a Seq Scan over 52,668 production rows at
123 ms, on every page view; 253 ms → 2.8 ms on the development database.

Feature 060 sharpened it. Collapsing watch history to a single canonical
identity left ``user_id`` with cardinality 1, so the primary key's leading
column now discriminates nothing.

This asserts the index is *declared on the model*, which is what
``create_all()`` builds the integration database from. The companion guarantee
— that the migration produces the same schema — is the ``alembic check`` step
in CI. Neither substitutes for the other: a model-only index never reaches
production, and a migration-only index drifts from the models.

Deliberately not asserted here: an index on ``watched_at``. Every row has it
set, so there is no selectivity to exploit, and pinning it would enshrine an
index the issue explicitly argues against.
"""

from __future__ import annotations

from typing import Any, cast

import pytest
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio

_TABLE = "user_videos"
_INDEX = "ix_user_videos_video_id"


def _get_indexes_sync(connection: Any, table_name: str) -> list[dict[str, Any]]:
    """Index metadata for *table_name*, from a synchronous connection."""
    inspector = inspect(connection)
    return cast(list[dict[str, Any]], inspector.get_indexes(table_name))


class TestUserVideosVideoIdIndex:
    async def test_index_on_video_id_exists(self, db_session: AsyncSession) -> None:
        connection = await db_session.connection()
        indexes = await connection.run_sync(_get_indexes_sync, _TABLE)

        names = {ix["name"] for ix in indexes}
        assert _INDEX in names, (
            f"{_INDEX} is missing from {_TABLE}. Without it, the playlist "
            "detail page's watched-flag lookup seq-scans the whole table on "
            f"every page view. Present indexes: {sorted(names)}"
        )

    async def test_the_index_is_on_video_id_alone(
        self, db_session: AsyncSession
    ) -> None:
        """A composite starting with another column would not help this query.

        The defect being guarded against is exactly a `video_id` predicate
        that cannot reach a leading column, so an index merely *containing*
        `video_id` is not enough.
        """
        connection = await db_session.connection()
        indexes = await connection.run_sync(_get_indexes_sync, _TABLE)

        match = next((ix for ix in indexes if ix["name"] == _INDEX), None)
        assert match is not None, f"{_INDEX} not found"
        assert list(match["column_names"]) == ["video_id"]

    async def test_a_video_id_lookup_is_supported_by_some_index(
        self, db_session: AsyncSession
    ) -> None:
        """The property that actually matters, stated independently of the name.

        If someone replaces this index with a differently-named equivalent,
        the assertions above fail while the page stays fast. This one passes
        in that case and fails only if the capability is genuinely lost.
        """
        connection = await db_session.connection()
        indexes = await connection.run_sync(_get_indexes_sync, _TABLE)

        leads_with_video_id = [
            ix["name"]
            for ix in indexes
            if ix.get("column_names") and ix["column_names"][0] == "video_id"
        ]
        assert leads_with_video_id, (
            "no index leads with video_id, so a `WHERE video_id IN (...)` "
            "lookup must scan the table"
        )
