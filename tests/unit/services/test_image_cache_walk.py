"""The cache walk must survive entries disappearing mid-scan (#101).

``ImageCacheService.get_stats()`` used ``pathlib``'s ``rglob``, which before
Python 3.13 raises ``FileNotFoundError`` when a directory entry vanishes
between enumeration and the follow-up ``stat`` (CPython bpo-33428, fixed by
GH-116380). On Docker's overlay2 that race fires readily against the video
cache — roughly 16,000 thumbnails across ~1,439 sharded prefix directories —
and it failed on a different random directory each run. The container runs
Python 3.11.

These exercise a real directory tree rather than mocking the ``os`` module.
The previous tests for this behaviour patched ``os.walk``, ``os.scandir``,
``os.path.join`` and ``os.stat``, which meant they passed for any
implementation that called those names in the expected order — including one
that still crashed on a vanished file.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from chronovista.services.image_cache import (
    ImageCacheConfig,
    ImageCacheService,
    iter_cached_files,
)

# No module-level `pytest.mark.asyncio`: pytest.ini sets `asyncio_mode = auto`,
# so the async tests here are collected without it, and applying it to a module
# that also holds synchronous tests warns on every one of them.


def _make_cache(root: Path, *, channels: int, videos: int) -> ImageCacheConfig:
    """Build a cache tree shaped like the real one — videos sharded by prefix."""
    channels_dir = root / "images" / "channels"
    videos_dir = root / "images" / "videos"
    channels_dir.mkdir(parents=True)
    videos_dir.mkdir(parents=True)

    for i in range(channels):
        (channels_dir / f"UCchan{i:04d}.jpg").write_bytes(b"x" * 100)
    for i in range(videos):
        shard = videos_dir / f"{i % 7:02d}"
        shard.mkdir(exist_ok=True)
        (shard / f"vid{i:04d}.jpg").write_bytes(b"y" * 200)

    return ImageCacheConfig(
        cache_dir=root, channels_dir=channels_dir, videos_dir=videos_dir
    )


class TestIterCachedFiles:
    def test_finds_flat_files_without_recursion(self, tmp_path: Path) -> None:
        cfg = _make_cache(tmp_path, channels=5, videos=0)
        found = list(iter_cached_files(cfg.channels_dir, ".jpg", recursive=False))
        assert len(found) == 5

    def test_finds_sharded_files_with_recursion(self, tmp_path: Path) -> None:
        """The video cache is nested, so a flat scan would report zero."""
        cfg = _make_cache(tmp_path, channels=0, videos=30)
        assert (
            len(list(iter_cached_files(cfg.videos_dir, ".jpg", recursive=True))) == 30
        )
        assert list(iter_cached_files(cfg.videos_dir, ".jpg", recursive=False)) == []

    def test_missing_directory_yields_nothing(self, tmp_path: Path) -> None:
        assert list(iter_cached_files(tmp_path / "nope", ".jpg", recursive=True)) == []

    def test_suffix_is_respected(self, tmp_path: Path) -> None:
        cfg = _make_cache(tmp_path, channels=3, videos=0)
        (cfg.channels_dir / "UCx.missing").write_bytes(b"")
        assert (
            len(list(iter_cached_files(cfg.channels_dir, ".jpg", recursive=False))) == 3
        )
        assert (
            len(list(iter_cached_files(cfg.channels_dir, ".missing", recursive=False)))
            == 1
        )

    def test_stat_is_returned_so_callers_need_no_second_syscall(
        self, tmp_path: Path
    ) -> None:
        """A caller re-statting the path could itself hit the vanished-file race."""
        cfg = _make_cache(tmp_path, channels=1, videos=0)
        ((_path, stat),) = list(
            iter_cached_files(cfg.channels_dir, ".jpg", recursive=False)
        )
        assert stat.st_size == 100


class TestTheRaceItself:
    """The actual defect: a file that disappears between listing and stat."""

    def test_recursive_walk_survives_a_vanished_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg = _make_cache(tmp_path, channels=0, videos=20)

        real_stat = os.stat
        state = {"first": True}

        def flaky_stat(path: Any, *a: Any, **kw: Any) -> os.stat_result:
            # Exactly what overlay2 does: the entry was listed, then removed
            # before the stat landed.
            if state["first"] and str(path).endswith(".jpg"):
                state["first"] = False
                raise FileNotFoundError(2, "No such file or directory", str(path))
            return real_stat(path, *a, **kw)

        monkeypatch.setattr(os, "stat", flaky_stat)

        found = list(iter_cached_files(cfg.videos_dir, ".jpg", recursive=True))

        assert len(found) == 19, (
            "the vanished file should be skipped and the walk should continue; "
            "rglob raised FileNotFoundError here and aborted the whole scan"
        )

    async def test_get_stats_survives_a_vanished_file(self, tmp_path: Path) -> None:
        """End to end: the call that actually broke on Docker.

        Deletes a file for real, from inside the iteration, so the skip is not
        merely a monkeypatched exception path.
        """
        cfg = _make_cache(tmp_path, channels=2, videos=14)

        victim = next(iter_cached_files(cfg.videos_dir, ".jpg", recursive=True))[0]
        victim.unlink()

        stats = await ImageCacheService(cfg).get_stats()

        assert stats.channel_count == 2
        assert stats.video_count == 13
        assert stats.total_size_bytes == 2 * 100 + 13 * 200


class TestPurge:
    async def test_purge_removes_files_and_reports_bytes(self, tmp_path: Path) -> None:
        cfg = _make_cache(tmp_path, channels=3, videos=10)
        service = ImageCacheService(cfg)

        freed = await service.purge(type_="all")

        assert freed == 3 * 100 + 10 * 200
        assert list(iter_cached_files(cfg.channels_dir, ".jpg", recursive=False)) == []
        assert list(iter_cached_files(cfg.videos_dir, ".jpg", recursive=True)) == []

    async def test_purge_keeps_the_directories(self, tmp_path: Path) -> None:
        """Callers re-fetch into these; removing them would break the next write."""
        cfg = _make_cache(tmp_path, channels=1, videos=3)
        await ImageCacheService(cfg).purge(type_="all")

        assert cfg.channels_dir.is_dir()
        assert cfg.videos_dir.is_dir()

    async def test_purge_counts_bytes_only_for_files_it_actually_removed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A failed unlink must not be reported as freed space.

        The previous implementation added the size and then attempted the
        delete, so a file it could not remove still counted towards the total.
        """
        cfg = _make_cache(tmp_path, channels=0, videos=5)
        service = ImageCacheService(cfg)

        real_unlink = Path.unlink

        def flaky_unlink(self: Path, *a: Any, **kw: Any) -> None:
            if self.name.endswith("0000.jpg"):
                raise PermissionError(13, "Permission denied", str(self))
            real_unlink(self, *a, **kw)

        monkeypatch.setattr(Path, "unlink", flaky_unlink)

        freed = await service.purge(type_="videos")

        assert freed == 4 * 200, "the undeletable file should not count as freed"
