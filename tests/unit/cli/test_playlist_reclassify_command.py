"""Smoke tests for the `playlist reclassify` Typer command wrapper (Feature 058).

Covers the command glue (session plumbing + Rich output) around the tested
`_reclassify` core. Sync tests (CliRunner), kept out of the asyncio-marked
core-logic module.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from typer.testing import CliRunner

import chronovista.cli.commands.playlist as mod

runner = CliRunner()


def _patch_env(monkeypatch, regulars: list[SimpleNamespace]) -> AsyncMock:
    session = AsyncMock()

    async def fake_get_session(echo: bool = False):  # type: ignore[no-untyped-def]
        yield session

    monkeypatch.setattr(
        mod, "DatabaseManager", lambda: SimpleNamespace(get_session=fake_get_session)
    )
    repo = AsyncMock()
    repo.get_playlists_by_type = AsyncMock(return_value=regulars)
    repo.promote_playlist_type = AsyncMock()
    monkeypatch.setattr(mod, "PlaylistRepository", lambda: repo)
    return repo


def _pl(playlist_id: str, title: str) -> SimpleNamespace:
    return SimpleNamespace(playlist_id=playlist_id, title=title)


def test_reclassify_dry_run_smoke(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    repo = _patch_env(monkeypatch, [_pl("PL1", "Watch later"), _pl("PL2", "AI")])
    result = runner.invoke(mod.playlist_app, ["reclassify", "--dry-run"])
    assert result.exit_code == 0
    assert "dry-run" in result.stdout.lower()
    assert "watch_later" in result.stdout
    repo.promote_playlist_type.assert_not_awaited()


def test_reclassify_apply_smoke(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    repo = _patch_env(monkeypatch, [_pl("PL1", "Watch later"), _pl("PL2", "AI")])
    result = runner.invoke(mod.playlist_app, ["reclassify"])
    assert result.exit_code == 0
    assert "updated" in result.stdout.lower()
    repo.promote_playlist_type.assert_awaited_once()


def test_reclassify_nothing_to_do_smoke(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _patch_env(monkeypatch, [_pl("PL2", "AI"), _pl("PL3", "Cooking")])
    result = runner.invoke(mod.playlist_app, ["reclassify"])
    assert result.exit_code == 0
    assert "nothing to reclassify" in result.stdout.lower()
