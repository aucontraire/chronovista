"""Which export wins when two disagree (#230), against a real database.

The load seeds from every export on disk, because YouTube truncates watch
history and an older export holds events the newest one no longer contains.
Seeding is **fill-only**: a title is written only over a placeholder, a channel
only over NULL. So the *first* export to supply a value wins and every later one
is a no-op for that field, which makes processing order the thing that decides
what the library ends up holding.

The case that discriminates is a video whose title **changed between exports** —
a creator renaming it. Both titles are real, so fill-only keeps whichever
arrives first, and the two orderings give different answers.

A *degraded* title (real, then the bare watch URL) does NOT discriminate: the
seeder normalises a URL to the bracket placeholder on create, and the fill-only
update then replaces that placeholder from any later export. Both orderings
converge, which is why 602 such videos in the production library kept their
titles even while the ordering was wrong. Testing with that shape would look
like coverage and prove nothing.

These tests use two *dated* exports on purpose. Dated names sort chronologically,
so the old `sorted(path.iterdir())` produced oldest-first — and the oldest export
won permanently. The undated case is the one that accidentally worked.

**What this file does and does not guard.** It calls
``discover_historical_takeouts`` directly rather than driving
``OnboardingService._factory_load_data``, which also resolves an identity, runs
recovery and writes a completion marker. So it establishes the *premise* of the
fix — that order decides the outcome, and newest-first yields the newer title —
but it does **not** catch the load step being changed back to oldest-first.
Verified: mutating that call site leaves every test here green.

``test_exports_are_discovered_newest_first`` in
tests/unit/services/test_onboarding_service.py is what guards the call site.
Neither file is sufficient alone; do not delete one on the strength of the other.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.services.takeout_seeding_service import TakeoutSeedingService
from chronovista.services.takeout_service import TakeoutService

pytestmark = pytest.mark.asyncio

_VIDEO_ID = "ordr1TESTx1"
_CHANNEL_ID = "UCorderingtest0000000001"
_OLD_TITLE = "Original Title"
_NEW_TITLE = "Renamed By The Creator"


def _write_export(base: Path, dir_name: str, title: str, watched: str) -> None:
    """Create one dated Takeout export holding a single watch entry."""
    youtube_dir = base / dir_name
    history = youtube_dir / "history"
    history.mkdir(parents=True)
    (history / "watch-history.json").write_text(
        json.dumps(
            [
                {
                    "header": "YouTube",
                    "title": f"Watched {title}",
                    "titleUrl": f"https://www.youtube.com/watch?v={_VIDEO_ID}",
                    "subtitles": [
                        {
                            "name": "Ordering Test Channel",
                            "url": f"https://www.youtube.com/channel/{_CHANNEL_ID}",
                        }
                    ],
                    "time": watched,
                }
            ]
        ),
        encoding="utf-8",
    )


@pytest.fixture
def two_exports(tmp_path: Path) -> Path:
    """Two dated exports that disagree about one video's title.

    The 2026 export is the newer one and carries the renamed title. Note that
    "…2025-01-01" sorts *before* "…2026-01-01", so sorting folder names
    ascending yields oldest-first.
    """
    _write_export(
        tmp_path,
        "YouTube and YouTube Music 2025-01-01",
        _OLD_TITLE,
        "2025-01-01T00:00:00Z",
    )
    _write_export(
        tmp_path,
        "YouTube and YouTube Music 2026-01-01",
        _NEW_TITLE,
        "2026-01-01T00:00:00Z",
    )
    return tmp_path


async def _seed_in_order(
    session: AsyncSession, exports: list[Path], user_id: str
) -> None:
    """Parse and seed each export, in the order given.

    Mirrors what the load step does per directory: `TakeoutService` is built with
    ``object.__new__`` and pointed at the export, because its constructor expects
    the *parent* of a "YouTube and YouTube Music" folder while these directories
    are that folder.
    """
    seeder = TakeoutSeedingService(user_id=user_id)
    for export in exports:
        svc = object.__new__(TakeoutService)
        svc.takeout_path = export.parent
        svc.youtube_path = export
        data = await svc.parse_all()
        await seeder.seed_database(session, data)


async def _stored_title(session: AsyncSession) -> str | None:
    row = (
        await session.execute(
            text("SELECT title FROM videos WHERE video_id = :v"), {"v": _VIDEO_ID}
        )
    ).first()
    return None if row is None else str(row[0])


class TestWhichExportWins:
    async def test_the_newest_export_supplies_the_title(
        self, db_session: AsyncSession, two_exports: Path
    ) -> None:
        """#230: newest-first seeding stores the newer title, against a real DB.

        This establishes the *consequence* of the ordering fix. It does not
        detect the load step asking for a different order — see the note in the
        module docstring — so read it as "newest-first produces this result",
        not as a guard on the production call site.
        """
        discovered = TakeoutService.discover_historical_takeouts(
            two_exports, sort_oldest_first=False
        )
        assert len(discovered) == 2, "both exports should be discovered"

        await _seed_in_order(
            db_session, [t.path for t in discovered], "UCorderingtest_identity"
        )
        await db_session.commit()

        assert await _stored_title(db_session) == _NEW_TITLE, (
            "the older export supplied the title, so a rename made before the "
            "latest download was discarded"
        )

    async def test_the_assertion_is_order_sensitive(
        self, db_session: AsyncSession, two_exports: Path
    ) -> None:
        """Proves the test above can fail.

        Seeding the same two exports oldest-first stores the *old* title. Without
        this, `test_the_newest_export_supplies_the_title` would pass under any
        ordering that happened to produce the right answer for another reason,
        and would be indistinguishable from a test that cannot fail.
        """
        discovered = TakeoutService.discover_historical_takeouts(
            two_exports, sort_oldest_first=True
        )

        await _seed_in_order(
            db_session, [t.path for t in discovered], "UCorderingtest_identity2"
        )
        await db_session.commit()

        assert await _stored_title(db_session) == _OLD_TITLE, (
            "fill-only means the first export to supply a title wins; if this "
            "is not the old title, the premise of the ordering fix is wrong"
        )

    async def test_sorting_folder_names_would_pick_the_wrong_export(
        self, two_exports: Path
    ) -> None:
        """The specific defect: dated names sort oldest-first.

        No database needed. `sorted(path.iterdir())` is what the load used to do,
        and with every export filed under its date it yields the oldest first,
        handing every gap to the oldest archive on disk.
        """
        by_name = sorted(p for p in two_exports.iterdir() if p.is_dir())
        by_date = TakeoutService.discover_historical_takeouts(
            two_exports, sort_oldest_first=False
        )

        assert by_name[0].name.endswith("2025-01-01"), "name order starts oldest"
        assert by_date[0].path.name.endswith("2026-01-01"), "date order starts newest"
        assert (
            by_name[0].name != by_date[0].path.name
        ), "this fixture no longer distinguishes the two orderings"


class TestSeededMetadata:
    async def test_the_watch_record_lands_under_the_given_identity(
        self, db_session: AsyncSession, two_exports: Path
    ) -> None:
        """Guards the seam this test drives directly.

        `_seed_in_order` passes a user_id rather than letting the seeder resolve
        one, so it could drift from what the load step actually does. If the
        watch row is missing, this file is exercising a path the application
        does not take.
        """
        discovered = TakeoutService.discover_historical_takeouts(
            two_exports, sort_oldest_first=False
        )
        user_id = "UCorderingtest_identity3"
        await _seed_in_order(db_session, [t.path for t in discovered], user_id)
        await db_session.commit()

        watched = (
            await db_session.execute(
                text(
                    "SELECT watched_at FROM user_videos "
                    "WHERE video_id = :v AND user_id = :u"
                ),
                {"v": _VIDEO_ID, "u": user_id},
            )
        ).first()

        assert watched is not None, "no watch record was seeded"
        assert isinstance(watched[0], datetime)
        assert watched[0] <= datetime.now(UTC)
