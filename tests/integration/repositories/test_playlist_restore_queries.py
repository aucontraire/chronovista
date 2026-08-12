"""The two queries that make a hidden playlist findable again (#149).

Every other query in ``PlaylistRepository`` filters hidden playlists out.
These two are the only way to see them and the only way to bring them back,
so their edge behaviour is worth pinning: what counts as restored, and what a
caller is told when it asks for something that was not hidden.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.repositories.playlist_repository import PlaylistRepository

pytestmark = pytest.mark.asyncio

_CHANNEL_ID = "UCrepohidden0000001"


async def _seed(session: AsyncSession, playlist_id: str, *, hidden: bool) -> None:
    await session.execute(
        text(
            """
            INSERT INTO channels (channel_id, title, is_subscribed,
                                  availability_status)
            VALUES (:cid, 'Repo Hidden Channel', false, 'available')
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
            VALUES (:pid, 'Repo Hidden Playlist', 'private', :cid, 3, :hidden,
                    'regular')
            ON CONFLICT (playlist_id) DO UPDATE SET deleted_flag = :hidden
            """
        ),
        {"pid": playlist_id, "cid": _CHANNEL_ID, "hidden": hidden},
    )
    await session.flush()


class TestGetHiddenPlaylists:
    async def test_it_returns_hidden_and_only_hidden(
        self, db_session: AsyncSession
    ) -> None:
        await _seed(db_session, "PLrepohidden01", hidden=True)
        await _seed(db_session, "PLrepovisible1", hidden=False)

        found = await PlaylistRepository().get_hidden_playlists(db_session)

        ids = {p.playlist_id for p in found}
        assert "PLrepohidden01" in ids
        assert "PLrepovisible1" not in ids


class TestRestorePlaylists:
    async def test_it_clears_the_flag(self, db_session: AsyncSession) -> None:
        await _seed(db_session, "PLrepoclear001", hidden=True)

        changed = await PlaylistRepository().restore_playlists(
            db_session, ["PLrepoclear001"]
        )

        assert changed == 1
        still_hidden = await db_session.execute(
            text("SELECT deleted_flag FROM playlists WHERE playlist_id = :p"),
            {"p": "PLrepoclear001"},
        )
        assert still_hidden.scalar_one() is False

    async def test_an_already_visible_playlist_does_not_count(
        self, db_session: AsyncSession
    ) -> None:
        """The count is playlists restored, not ids supplied.

        A caller that gets back "1" for two ids has been told something true
        and useful; returning len(ids) would be a lie that hides a typo.
        """
        await _seed(db_session, "PLrepovis00001", hidden=False)
        await _seed(db_session, "PLrepohid00001", hidden=True)

        changed = await PlaylistRepository().restore_playlists(
            db_session, ["PLrepovis00001", "PLrepohid00001"]
        )

        assert changed == 1

    async def test_an_unknown_id_counts_zero(self, db_session: AsyncSession) -> None:
        changed = await PlaylistRepository().restore_playlists(
            db_session, ["PLrepodoesnotexist"]
        )

        assert changed == 0

    async def test_an_empty_list_is_a_no_op(self, db_session: AsyncSession) -> None:
        """Guarded explicitly: an unguarded IN () is a SQL error in some
        dialects and a full-table match in others, and this statement writes."""
        await _seed(db_session, "PLrepoempty001", hidden=True)

        changed = await PlaylistRepository().restore_playlists(db_session, [])

        assert changed == 0
        still_hidden = await db_session.execute(
            text("SELECT deleted_flag FROM playlists WHERE playlist_id = :p"),
            {"p": "PLrepoempty001"},
        )
        assert (
            still_hidden.scalar_one() is True
        ), "an empty restore list must not touch any row"
