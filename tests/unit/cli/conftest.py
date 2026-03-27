"""Shared fixtures for CLI unit tests."""

from __future__ import annotations

import re

import pytest

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


@pytest.fixture(autouse=True)
def _strip_ansi_from_cli_output(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip ANSI escape codes from CliRunner results.

    Typer/Rich emit ANSI sequences in CI (no TTY) which break string
    assertions like ``assert '--flag' in result.stdout``.  This fixture
    patches ``click.testing.Result.stdout`` and ``.output`` at the
    property level so every test in this directory gets clean text.
    """
    from click.testing import Result

    _orig_stdout = Result.stdout  # type: ignore[attr-defined]
    _orig_output = Result.output  # type: ignore[attr-defined]

    @property  # type: ignore[misc]
    def _clean_stdout(self: Result) -> str:
        raw = _orig_stdout.fget(self)  # type: ignore[union-attr]
        return _ANSI_RE.sub("", raw) if raw else raw

    @property  # type: ignore[misc]
    def _clean_output(self: Result) -> str:
        raw = _orig_output.fget(self)  # type: ignore[union-attr]
        return _ANSI_RE.sub("", raw) if raw else raw

    monkeypatch.setattr(Result, "stdout", _clean_stdout)
    monkeypatch.setattr(Result, "output", _clean_output)
