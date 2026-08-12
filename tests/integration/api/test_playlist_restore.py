"""Restoring playlists hidden by a bad enrichment run (#149).

A playlist hidden by ``deleted_flag`` never returns on its own: every query
filters it out, and ``enrich_playlists`` selects only live rows, so it leaves
the population permanently. Before this endpoint the sole route back was a
hand-written UPDATE at a psql prompt — which is what the original incident
required, two months after the fact.

These go through the real database rather than a mocked repository, because
the thing worth checking is that the row is visible again afterwards.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio

_CHANNEL_ID = "UCrestore00000000001"


@pytest.fixture
async def test_data_session(
    integration_session_factory: Any,
) -> AsyncGenerator[AsyncSession, None]:
    """A session for seeding, from the API conftest's factory.

    Deliberately **not** the top-level ``db_session`` fixture. That one calls
    ``Base.metadata.drop_all`` at teardown, while this package creates the
    schema once per session (``integration_db_schema_setup``, ``scope="session"``)
    and never recreates it. An API test that touches ``db_session`` therefore
    drops the tables out from under every test that follows — 331 of them,
    all reporting ``relation "channels" does not exist``, none of them at fault.
    """
    async with integration_session_factory() as session:
        yield session


@pytest.fixture(autouse=True)
async def cleanup_seeded_rows(
    test_data_session: AsyncSession,
) -> AsyncGenerator[None, None]:
    """Remove this file's rows after each test.

    Required, not tidiness. The schema in this package is created once per
    session and never reset, so committed rows outlive the test that made
    them — and other files clean up with a bare ``DELETE FROM channels``,
    which a leftover playlist blocks outright with a foreign-key violation.
    Leaking rows here fails tests that have nothing to do with playlists.

    Playlists go first: they hold the foreign key.
    """
    yield
    await test_data_session.execute(
        text("DELETE FROM playlists WHERE channel_id = :cid"), {"cid": _CHANNEL_ID}
    )
    await test_data_session.execute(
        text("DELETE FROM channels WHERE channel_id = :cid"), {"cid": _CHANNEL_ID}
    )
    await test_data_session.commit()


async def _seed(
    session: AsyncSession, playlist_id: str, *, hidden: bool, title: str = "Seeded"
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO channels (channel_id, title, is_subscribed,
                                  availability_status)
            VALUES (:cid, 'Restore Test Channel', false, 'available')
            ON CONFLICT (channel_id) DO NOTHING
            """
        ),
        {"cid": _CHANNEL_ID},
    )
    await session.execute(
        text(
            """
            INSERT INTO playlists (playlist_id, title, privacy_status, channel_id,
                                   video_count, deleted_flag, playlist_type)
            VALUES (:pid, :title, 'private', :cid, 7, :hidden, 'regular')
            ON CONFLICT (playlist_id) DO UPDATE SET deleted_flag = :hidden
            """
        ),
        {"pid": playlist_id, "cid": _CHANNEL_ID, "hidden": hidden, "title": title},
    )
    await session.commit()


async def _is_hidden(session: AsyncSession, playlist_id: str) -> bool:
    row = await session.execute(
        text("SELECT deleted_flag FROM playlists WHERE playlist_id = :p"),
        {"p": playlist_id},
    )
    return bool(row.scalar_one())


class TestRouteOrdering:
    async def test_hidden_is_not_swallowed_by_the_detail_route(
        self, async_client: AsyncClient, test_data_session: AsyncSession
    ) -> None:
        """``/playlists/hidden`` must not be parsed as a playlist id.

        FastAPI matches in definition order and "hidden" satisfies the detail
        route's path constraints, so declaring the routes the other way round
        returns 404 for every request here. Nothing else in the suite would
        catch it, because the handler would still exist and still be correct.
        """
        response = await async_client.get("/api/v1/playlists/hidden")

        assert response.status_code == 200, (
            "the hidden listing was routed to the detail handler — check that "
            "it is declared before /playlists/{playlist_id}"
        )
        assert "data" in response.json()


class TestHiddenListing:
    async def test_a_hidden_playlist_is_listed(
        self, async_client: AsyncClient, test_data_session: AsyncSession
    ) -> None:
        await _seed(test_data_session, "PLhiddenlisted01", hidden=True)

        body = (await async_client.get("/api/v1/playlists/hidden")).json()

        ids = [p["playlist_id"] for p in body["data"]]
        assert "PLhiddenlisted01" in ids
        assert body["total"] == len(body["data"])

    async def test_a_visible_playlist_is_not_listed(
        self, async_client: AsyncClient, test_data_session: AsyncSession
    ) -> None:
        await _seed(test_data_session, "PLvisible000001", hidden=False)

        body = (await async_client.get("/api/v1/playlists/hidden")).json()

        ids = [p["playlist_id"] for p in body["data"]]
        assert "PLvisible000001" not in ids

    async def test_the_hidden_time_is_reported(
        self, async_client: AsyncClient, test_data_session: AsyncSession
    ) -> None:
        """Approximate, and named so — there is no deletion timestamp column."""
        await _seed(test_data_session, "PLhiddentime001", hidden=True)

        body = (await async_client.get("/api/v1/playlists/hidden")).json()

        entry = next(p for p in body["data"] if p["playlist_id"] == "PLhiddentime001")
        assert entry["hidden_at_approx"] is not None


class TestRestore:
    async def test_restoring_makes_a_playlist_visible_again(
        self, async_client: AsyncClient, test_data_session: AsyncSession
    ) -> None:
        """The whole point: assert against the row, not the response."""
        await _seed(test_data_session, "PLrestoreme0001", hidden=True)

        response = await async_client.post(
            "/api/v1/playlists/restore",
            json={"playlist_ids": ["PLrestoreme0001"]},
        )

        assert response.status_code == 200
        assert response.json()["restored"] == 1
        assert await _is_hidden(test_data_session, "PLrestoreme0001") is False

    async def test_a_playlist_that_was_not_hidden_is_skipped(
        self, async_client: AsyncClient, test_data_session: AsyncSession
    ) -> None:
        """Reported, not fatal — a partial restore is a useful outcome."""
        await _seed(test_data_session, "PLalreadyvis001", hidden=False)
        await _seed(test_data_session, "PLmixedhidden1", hidden=True)

        body = (
            await async_client.post(
                "/api/v1/playlists/restore",
                json={"playlist_ids": ["PLalreadyvis001", "PLmixedhidden1"]},
            )
        ).json()

        assert body["restored"] == 1
        assert body["skipped"] == ["PLalreadyvis001"]

    async def test_an_unknown_id_is_skipped_not_an_error(
        self, async_client: AsyncClient, test_data_session: AsyncSession
    ) -> None:
        body = (
            await async_client.post(
                "/api/v1/playlists/restore",
                json={"playlist_ids": ["PLdoesnotexist9"]},
            )
        ).json()

        assert body["restored"] == 0
        assert body["skipped"] == ["PLdoesnotexist9"]

    async def test_an_empty_request_is_rejected(
        self, async_client: AsyncClient
    ) -> None:
        """There is deliberately no restore-everything request shape.

        An empty body is exactly what an accidental POST sends, and un-hiding
        the whole library must be an explicit act.
        """
        response = await async_client.post(
            "/api/v1/playlists/restore", json={"playlist_ids": []}
        )

        assert response.status_code == 422

    async def test_a_restored_playlist_is_reachable_again(
        self, async_client: AsyncClient, test_data_session: AsyncSession
    ) -> None:
        """The cross-feature check: restoring must actually undo the hiding.

        The detail endpoint filters ``deleted_flag IS FALSE``, so a 404 before
        and a 200 after is the user-visible meaning of this operation.
        """
        await _seed(test_data_session, "PLreachable0001", hidden=True)

        before = await async_client.get("/api/v1/playlists/PLreachable0001")
        assert before.status_code == 404

        await async_client.post(
            "/api/v1/playlists/restore",
            json={"playlist_ids": ["PLreachable0001"]},
        )

        after = await async_client.get("/api/v1/playlists/PLreachable0001")
        assert after.status_code == 200
