"""Smoke tests for the `chronovista identity` Typer commands (Feature 060, T019).

Sync tests (CliRunner) covering command glue around the tested service core.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from typer.testing import CliRunner

import chronovista.cli.commands.identity as mod
from chronovista.models.app_identity import IdentityInvariants, MergeStats
from chronovista.services.identity_service import (
    RepairReport,
    UnrecognizedIdentityConfigError,
)

runner = CliRunner()

CHANNEL = "UCzYTmeK-6v3DcJ6hzRh1q9w"
_INV = IdentityInvariants(distinct_watched_videos=10, liked_count=3, rewatch_sum=5)


def _patch_db(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    session = AsyncMock()

    async def fake_get_session(echo: bool = False):  # type: ignore[no-untyped-def]
        yield session

    monkeypatch.setattr(
        mod, "DatabaseManager", lambda: SimpleNamespace(get_session=fake_get_session)
    )


def _patch_status(monkeypatch, identity, distinct):  # type: ignore[no-untyped-def]
    _patch_db(monkeypatch)
    id_repo = SimpleNamespace(get_identity=AsyncMock(return_value=identity))
    uv_repo = SimpleNamespace(list_distinct_user_ids=AsyncMock(return_value=distinct))
    monkeypatch.setattr(mod, "AppIdentityRepository", lambda: id_repo)
    monkeypatch.setattr(mod, "UserVideoRepository", lambda: uv_repo)


def _patch_repair(monkeypatch, report=None, exc=None):  # type: ignore[no-untyped-def]
    _patch_db(monkeypatch)
    repair = AsyncMock(side_effect=exc) if exc else AsyncMock(return_value=report)
    monkeypatch.setattr(mod, "IdentityService", lambda: SimpleNamespace(repair=repair))
    return repair


def _report(dry_run: bool) -> RepairReport:
    return RepairReport(
        dry_run=dry_run,
        canonical_user_id=CHANNEL,
        source="channel",
        placeholder_user_ids=["takeout_user"],
        user_videos=MergeStats(merged=5, deleted=5, rekeyed=3),
        language_prefs_rekeyed=0,
        invariants_before=_INV,
        invariants_after=_INV,
        pre_image_path=None if dry_run else "/data/backups/pre.json",
    )


def test_status_multiple_identities_warns(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    identity = SimpleNamespace(user_id=CHANNEL, source="channel")
    _patch_status(monkeypatch, identity, [CHANNEL, "takeout_user"])
    result = runner.invoke(mod.identity_app, ["status"])
    assert result.exit_code == 0
    assert "multiple identities detected" in result.stdout.lower()


def test_status_not_established(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _patch_status(monkeypatch, None, [])
    result = runner.invoke(mod.identity_app, ["status"])
    assert result.exit_code == 0
    assert "not established" in result.stdout.lower()


def test_repair_dry_run_smoke(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _patch_repair(monkeypatch, report=_report(dry_run=True))
    result = runner.invoke(mod.identity_app, ["repair", "--dry-run"])
    assert result.exit_code == 0
    assert "dry-run" in result.stdout.lower()


def test_repair_apply_smoke(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _patch_repair(monkeypatch, report=_report(dry_run=False))
    result = runner.invoke(mod.identity_app, ["repair"])
    assert result.exit_code == 0
    assert "applied" in result.stdout.lower()


def test_repair_refuses_on_error_exit_1(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _patch_repair(
        monkeypatch,
        exc=UnrecognizedIdentityConfigError(canonical=CHANNEL, unrecognized=["UCx"]),
    )
    result = runner.invoke(mod.identity_app, ["repair"])
    assert result.exit_code == 1
    assert "refusing to repair" in result.stdout.lower()


def test_repair_noop_when_single_identity(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    report = _report(dry_run=False)
    report.placeholder_user_ids = []  # nothing to merge
    _patch_repair(monkeypatch, report=report)
    result = runner.invoke(mod.identity_app, ["repair"])
    assert result.exit_code == 0
    assert "nothing to merge" in result.stdout.lower()


def _patch_db_tracking_resumption(monkeypatch, state):  # type: ignore[no-untyped-def]
    """Patch DatabaseManager with a generator that records normal resumption.

    ``state["resumed"]`` is set only if execution continues *past* the yield —
    i.e. the command let the generator finish. If the command instead exits the
    ``async for`` body early (``return``/``sys.exit``), the generator is
    abandoned, GeneratorExit is thrown at the yield, and the flag stays False.
    """
    session = AsyncMock()

    async def fake_get_session(echo: bool = False):  # type: ignore[no-untyped-def]
        yield session
        state["resumed"] = True

    monkeypatch.setattr(
        mod, "DatabaseManager", lambda: SimpleNamespace(get_session=fake_get_session)
    )


def test_repair_noop_does_not_abandon_session_generator(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Regression: the idempotent no-op re-run is the most common operator
    invocation. Returning from inside the `async for` abandoned the session
    generator, forcing its commit/close/dispose to run at loop teardown and
    printing a CancelledError traceback after a successful, exit-0 run.
    """
    state = {"resumed": False}
    _patch_db_tracking_resumption(monkeypatch, state)
    report = _report(dry_run=False)
    report.placeholder_user_ids = []  # the no-op path
    monkeypatch.setattr(
        mod,
        "IdentityService",
        lambda: SimpleNamespace(repair=AsyncMock(return_value=report)),
    )

    result = runner.invoke(mod.identity_app, ["repair"])

    assert result.exit_code == 0
    assert "nothing to merge" in result.stdout.lower()
    assert state["resumed"], "session generator was abandoned (no-op path)"


def test_repair_refusal_does_not_abandon_session_generator(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Same abandonment hazard on the refuse path (was an inline sys.exit)."""
    state = {"resumed": False}
    _patch_db_tracking_resumption(monkeypatch, state)
    monkeypatch.setattr(
        mod,
        "IdentityService",
        lambda: SimpleNamespace(
            repair=AsyncMock(
                side_effect=UnrecognizedIdentityConfigError(
                    canonical=CHANNEL, unrecognized=["UCx"]
                )
            )
        ),
    )

    result = runner.invoke(mod.identity_app, ["repair"])

    assert result.exit_code == 1
    assert "refusing to repair" in result.stdout.lower()
    assert state["resumed"], "session generator was abandoned (refuse path)"


def _patch_reset(monkeypatch, channel, report=None, exc=None):  # type: ignore[no-untyped-def]
    _patch_db(monkeypatch)
    import chronovista.container as container_mod

    mock_yt = SimpleNamespace(get_my_channel=AsyncMock(return_value=channel))
    monkeypatch.setattr(container_mod.container, "youtube_service", mock_yt)
    reset = AsyncMock(side_effect=exc) if exc else AsyncMock(return_value=report)
    monkeypatch.setattr(
        mod, "IdentityService", lambda: SimpleNamespace(reset_identity=reset)
    )
    return reset


def test_reset_applies_smoke(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    report = _report(dry_run=False)
    reset = _patch_reset(
        monkeypatch, channel=SimpleNamespace(id=CHANNEL), report=report
    )
    result = runner.invoke(mod.identity_app, ["reset"])
    assert result.exit_code == 0
    assert "identity reset" in result.stdout.lower()
    reset.assert_awaited_once()


def test_reset_no_channel_exits_1(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _patch_reset(monkeypatch, channel=None)
    result = runner.invoke(mod.identity_app, ["reset"])
    assert result.exit_code == 1
    assert "no youtube channel" in result.stdout.lower()


def test_reset_refuses_on_error_exit_1(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from chronovista.services.identity_service import IdentityError

    _patch_reset(
        monkeypatch,
        channel=SimpleNamespace(id=CHANNEL),
        exc=IdentityError("nothing to reset"),
    )
    result = runner.invoke(mod.identity_app, ["reset"])
    assert result.exit_code == 1
    assert "nothing to reset" in result.stdout.lower()
