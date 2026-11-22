"""Unit tests for the relationship-candidate CLI (Feature 107).

Mocks the generator service so these test only the command wiring: the --dry-run
flag reaches the service, and the result counts are rendered.
"""

from __future__ import annotations

from typing import Any

import pytest
from typer.testing import CliRunner

from chronovista.cli import relationship_candidate_commands as mod

runner = CliRunner()


@pytest.fixture
def _capture(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    calls: dict[str, Any] = {}

    async def _fake(*, dry_run: bool) -> dict[str, int]:
        calls["dry_run"] = dry_run
        return {
            "written": 42,
            "removed": 3,
            "channel_video_universe": 1000,
            "corpus_size": 50,
        }

    monkeypatch.setattr(mod, "generate_relationship_candidates", _fake)
    return calls


def test_generate_reports_counts(_capture: dict[str, Any]) -> None:
    result = runner.invoke(mod.relationship_app, ["generate"])
    assert result.exit_code == 0
    assert _capture["dry_run"] is False
    assert "42" in result.stdout
    assert "Generation complete" in result.stdout


def test_generate_dry_run_passes_flag(_capture: dict[str, Any]) -> None:
    result = runner.invoke(mod.relationship_app, ["generate", "--dry-run"])
    assert result.exit_code == 0
    assert _capture["dry_run"] is True
    assert "DRY RUN" in result.stdout


@pytest.fixture
def _capture_transcript(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    calls: dict[str, Any] = {}

    async def _fake_transcript(*, dry_run: bool) -> dict[str, int]:
        calls["transcript_dry_run"] = dry_run
        return {
            "written": 17,
            "children": 23,
            "merged": 9,
            "dropped": 4,
            "channel_video_universe": 777,
            "corpus_size": 60,
        }

    async def _fake_title(*, dry_run: bool) -> dict[str, int]:
        calls["title_called"] = True
        return {}

    monkeypatch.setattr(mod, "generate_transcript_candidates", _fake_transcript)
    monkeypatch.setattr(mod, "generate_relationship_candidates", _fake_title)
    return calls


def test_transcript_channel_dispatches_and_renders_fields(
    _capture_transcript: dict[str, Any],
) -> None:
    result = runner.invoke(
        mod.relationship_app, ["generate", "--channel", "transcript"]
    )
    assert result.exit_code == 0
    assert _capture_transcript["transcript_dry_run"] is False
    assert "title_called" not in _capture_transcript
    assert "Generation complete" in result.stdout
    assert "merged" in result.stdout and "9" in result.stdout
    assert "dropped" in result.stdout and "4" in result.stdout
    assert "evidence rows" in result.stdout and "23" in result.stdout
    assert "17" in result.stdout


def test_transcript_channel_dry_run_passes_flag(
    _capture_transcript: dict[str, Any],
) -> None:
    result = runner.invoke(
        mod.relationship_app, ["generate", "--channel", "transcript", "--dry-run"]
    )
    assert result.exit_code == 0
    assert _capture_transcript["transcript_dry_run"] is True
    assert "DRY RUN" in result.stdout


def test_default_channel_does_not_call_transcript(
    _capture: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _boom(*, dry_run: bool) -> dict[str, int]:
        raise AssertionError("transcript generator must not run by default")

    monkeypatch.setattr(mod, "generate_transcript_candidates", _boom)
    result = runner.invoke(mod.relationship_app, ["generate"])
    assert result.exit_code == 0
    assert "removed (stale)" in result.stdout


def test_invalid_channel_rejected() -> None:
    result = runner.invoke(mod.relationship_app, ["generate", "--channel", "bogus"])
    assert result.exit_code != 0
