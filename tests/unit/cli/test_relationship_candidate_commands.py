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
