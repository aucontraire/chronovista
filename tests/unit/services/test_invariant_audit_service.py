"""Pure logic of the invariant audit: the registry, selection, comparison, exit codes.

No database. The checks themselves are tested against the integration database in
``tests/integration/services/test_invariant_audit.py``.
"""

from __future__ import annotations

import subprocess
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import pytest
from click.testing import Result
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from typer.testing import CliRunner

from chronovista.cli.main import app as cli_app
from chronovista.services.invariant_audit_service import (
    EXIT_CLEAN,
    EXIT_INCOMPLETE,
    EXIT_VIOLATED,
    REGISTRY,
    AuditRun,
    CheckResult,
    InvariantCheck,
    Outcome,
    compare,
    database_hash,
    exit_code,
    select_checks,
    validate_registry,
)


async def _noop(session: AsyncSession) -> dict[str, set[str]]:
    return {}


def _check(check_id: str, entry: str) -> InvariantCheck:
    return InvariantCheck(
        check_id=check_id,
        register_entry=entry,
        rule="test rule",
        rule_version=1,
        key_kind="row_id",
        run=_noop,
    )


def _result(
    check_id: str,
    keys: set[str],
    *,
    outcome: Outcome | None = None,
    version: int = 1,
    kind: Literal["row_id", "library_identifier"] = "row_id",
) -> CheckResult:
    return CheckResult(
        check_id=check_id,
        outcome=outcome or ("violated" if keys else "holds"),
        violation_count=len(keys),
        keys=keys,
        rule_version=version,
        key_kind=kind,
        seconds=0.0,
    )


def _run(*results: CheckResult, db: str = "abc") -> AuditRun:
    return AuditRun(
        started_at=datetime.now(UTC),
        results=list(results),
        chronovista_version="0",
        database_hash=db,
    )


class TestRegistry:
    def test_a_duplicate_check_id_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="duplicate"):
            validate_registry([_check("T1-a", "T1"), _check("T1-a", "T1")])

    @pytest.mark.parametrize("bad", ["t1-flag", "T1_flag", "T-flag", "T1-Flag"])
    def test_a_malformed_check_id_is_rejected(self, bad: str) -> None:
        with pytest.raises(ValidationError):
            _check(bad, "T1")

    def test_a_malformed_register_entry_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _check("T1-flag", "T1a")


class TestSelection:
    registry = (_check("T1-flag", "T1"), _check("T1-count", "T1"), _check("G1-x", "G1"))

    def test_no_selection_is_every_check(self) -> None:
        assert [c.check_id for c in select_checks(self.registry, None)] == [
            "T1-flag",
            "T1-count",
            "G1-x",
        ]

    def test_a_register_entry_selects_all_its_checks(self) -> None:
        """Mutation: match only ``check_id``; ``T1`` is then an unknown ID."""
        assert [c.check_id for c in select_checks(self.registry, ["T1"])] == [
            "T1-flag",
            "T1-count",
        ]

    def test_an_unknown_id_is_named(self) -> None:
        with pytest.raises(ValueError, match="Q9"):
            select_checks(self.registry, ["Q9"])


class TestCompare:
    def test_unchanged_data_has_nothing_new_and_passes(self) -> None:
        base = _run(_result("G1-x", {"a", "b"}))
        cur = _run(_result("G1-x", {"a", "b"}))
        [c] = compare(base, cur, sample=5, show_library_keys=False)
        assert (c.new, c.resolved) == (0, 0)
        assert exit_code(cur, [c]) == EXIT_CLEAN

    def test_resolved_only_passes(self) -> None:
        [c] = compare(
            _run(_result("G1-x", {"a", "b"})),
            _run(_result("G1-x", {"a"})),
            sample=5,
            show_library_keys=False,
        )
        assert (c.new, c.resolved) == (0, 1)

    def test_anything_new_fails_even_when_the_total_falls(self) -> None:
        """Mutation: compare counts instead of keys; this test goes red."""
        cur = _run(_result("G1-x", {"c"}))
        comps = compare(
            _run(_result("G1-x", {"a", "b"})), cur, sample=5, show_library_keys=False
        )
        assert (comps[0].new, comps[0].resolved) == (1, 2)
        assert exit_code(cur, comps) == EXIT_VIOLATED

    @pytest.mark.parametrize(
        ("base", "cur", "reason"),
        [
            ([], [_result("G1-x", set())], "missing from baseline"),
            ([_result("G1-x", set())], [], "missing from current run"),
            (
                [_result("G1-x", set(), outcome="error")],
                [_result("G1-x", set())],
                "errored",
            ),
            (
                [_result("G1-x", set(), version=1)],
                [_result("G1-x", set(), version=2)],
                "rule changed",
            ),
        ],
    )
    def test_not_compared_has_a_reason(
        self, base: list[CheckResult], cur: list[CheckResult], reason: str
    ) -> None:
        [c] = compare(_run(*base), _run(*cur), sample=5, show_library_keys=False)
        assert c.status == "not_compared"
        assert c.reason is not None and c.reason.startswith(reason)

    def test_the_sample_is_bounded_and_sorted(self) -> None:
        [c] = compare(
            _run(_result("G1-x", set())),
            _run(_result("G1-x", {"e", "a", "d", "b", "c"})),
            sample=3,
            show_library_keys=False,
        )
        assert c.sample_new == ["a", "b", "c"]

    def test_library_identifier_keys_are_hidden_unless_asked(self) -> None:
        """Mutation: ignore ``key_kind``; video-ID keys would print by default."""
        base = _run(_result("T1-x", set(), kind="library_identifier"))
        cur = _run(_result("T1-x", {"vid/en"}, kind="library_identifier"))
        [hidden] = compare(base, cur, sample=5, show_library_keys=False)
        [shown] = compare(base, cur, sample=5, show_library_keys=True)
        assert hidden.sample_new == [] and hidden.hidden_keys
        assert shown.sample_new == ["vid/en"]


class TestExitCode:
    def test_clean(self) -> None:
        assert exit_code(_run(_result("G1-x", set()))) == EXIT_CLEAN

    def test_a_violation(self) -> None:
        assert exit_code(_run(_result("G1-x", {"a"}))) == EXIT_VIOLATED

    def test_an_error_wins_over_a_violation(self) -> None:
        """Mutation: check violations first; an errored run then reads as 1."""
        run = _run(_result("G1-x", {"a"}), _result("G2-y", set(), outcome="error"))
        assert exit_code(run) == EXIT_INCOMPLETE


class TestCompareExitCode:
    def test_a_new_check_that_is_violated_cannot_pass_the_gate(self) -> None:
        """Mutation: exit only on ``new``; a violated check missing from the
        baseline then passes with 0 and this test goes red.
        """
        cur = _run(_result("G1-x", {"a"}))
        comps = compare(_run(), cur, sample=5, show_library_keys=False)
        assert exit_code(cur, comps) == EXIT_INCOMPLETE

    def test_a_changed_rule_with_no_violations_passes(self) -> None:
        cur = _run(_result("G1-x", set(), version=2))
        comps = compare(
            _run(_result("G1-x", set(), version=1)),
            cur,
            sample=5,
            show_library_keys=False,
        )
        assert exit_code(cur, comps) == EXIT_CLEAN


class TestDatabaseHash:
    def test_it_ignores_the_password_and_differs_by_database(self) -> None:
        a = database_hash("postgresql+asyncpg://u:secret@h:5435/one")
        assert a == database_hash("postgresql+asyncpg://u:other@h:5435/one")
        assert a != database_hash("postgresql+asyncpg://u:secret@h:5435/two")
        assert "secret" not in a

    def test_a_missing_port_means_the_default(self) -> None:
        assert database_hash("postgresql+asyncpg://u@h/one") == database_hash(
            "postgresql+asyncpg://u@h:5432/one"
        )


class _Cli:
    """Runs ``chronovista audit-invariants`` with the session and runner faked.

    ``outcomes`` maps a check ID to its violating keys, or to ``None`` for an error.
    Each fake result carries the real check's key kind. ``calls`` records what the
    command asked for.
    """

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._monkeypatch = monkeypatch
        self.calls: dict[str, object] = {}

    def __call__(
        self, *args: str, outcomes: dict[str, set[str] | None] | None = None
    ) -> Result:
        from chronovista.cli import audit_commands

        calls = self.calls
        calls.clear()
        wanted = outcomes or {}

        class _Manager:
            @asynccontextmanager
            async def session(
                self, echo: bool | None = None, *, read_only: bool = False
            ) -> AsyncIterator[object]:
                calls["read_only"] = read_only
                yield object()

        async def run(
            session: object, checks: list[InvariantCheck], *, database_url: str
        ) -> AuditRun:
            calls["checks"] = [c.check_id for c in checks]
            results = []
            for c in checks:
                keys = wanted.get(c.check_id, set())
                results.append(
                    _result(c.check_id, set(), outcome="error", kind=c.key_kind)
                    if keys is None
                    else _result(c.check_id, keys, kind=c.key_kind)
                )
            return _run(*results)

        self._monkeypatch.setattr(audit_commands, "db_manager", _Manager())
        self._monkeypatch.setattr(audit_commands, "run_checks", run)
        return CliRunner().invoke(cli_app, ["audit-invariants", *args])


class TestCommand:
    """The ``audit-invariants`` command's wiring, with the runner patched."""

    @pytest.fixture
    def cli(self, monkeypatch: pytest.MonkeyPatch) -> _Cli:
        return _Cli(monkeypatch)

    def test_clean_violated_and_incomplete_exit_codes(self, cli: _Cli) -> None:
        assert cli().exit_code == EXIT_CLEAN
        assert cli(outcomes={"G1-alias-placement": {"a"}}).exit_code == EXIT_VIOLATED
        assert cli(outcomes={"G2-merge-state": None}).exit_code == EXIT_INCOMPLETE

    def test_the_session_is_read_only(self, cli: _Cli) -> None:
        """Mutation: open ``db_manager.session()`` without ``read_only``."""
        cli()
        assert cli.calls["read_only"] is True

    def test_an_unknown_check_is_a_usage_error(self, cli: _Cli) -> None:
        result = cli("--check", "Q9")
        assert result.exit_code == 2
        assert "Q9" in result.output

    def test_a_register_entry_selects_its_checks(self, cli: _Cli) -> None:
        cli("--check", "T1")
        assert cli.calls["checks"] == [
            "T1-correction-flag",
            "T1-correction-count",
        ]

    def test_list_runs_nothing(self, cli: _Cli) -> None:
        result = cli("--list")
        assert result.exit_code == 0
        assert "checks" not in cli.calls
        assert "M2-one-row-per-occurrence" in result.output

    def test_save_into_the_repository_is_refused_without_force(
        self,
        cli: _Cli,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Mutation: skip the tracked-path check; the baseline is written into the
        repository and this test goes red.
        """
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        target = repo / "baseline.json"

        refused = cli("--save", str(target))
        assert refused.exit_code == 2 and not target.exists()

        forced = cli("--save", str(target), "--force")
        assert forced.exit_code == 0 and target.exists()

    def test_compare_against_another_database_warns_and_compares(
        self, cli: _Cli, tmp_path: Path
    ) -> None:
        baseline = tmp_path / "base.json"
        baseline.write_text(
            _run(_result("G1-alias-placement", set()), db="elsewhere").model_dump_json()
        )
        result = cli(
            "--check",
            "G1",
            "--compare",
            str(baseline),
            outcomes={"G1-alias-placement": {"new"}},
        )
        assert "different database" in result.output
        assert result.exit_code == EXIT_VIOLATED

    def test_a_bad_baseline_is_a_usage_error_that_prints_no_key(
        self, cli: _Cli, tmp_path: Path
    ) -> None:
        """Mutation: let the parser's error through; it exits 1 and quotes the key."""
        bad = tmp_path / "bad.json"
        bad.write_text('{"results": [{"keys": "Abcdefghij9/en"}]}')
        for path in (bad, tmp_path / "missing.json"):
            result = cli("--compare", str(path))
            assert result.exit_code == 2
            assert "Abcdefghij9" not in result.output

    def test_saving_into_a_missing_folder_is_refused_before_running(
        self, cli: _Cli, tmp_path: Path
    ) -> None:
        result = cli("--save", str(tmp_path / "nope" / "run.json"))
        assert result.exit_code == 2
        assert "checks" not in cli.calls


class TestCompareExitCodeBaselineErrors:
    def test_a_baseline_error_on_a_check_that_holds_now_passes(self) -> None:
        """Mutation: return 75 for any errored comparison; this test goes red."""
        cur = _run(_result("G1-x", set()))
        comps = compare(
            _run(_result("G1-x", set(), outcome="error")),
            cur,
            sample=5,
            show_library_keys=False,
        )
        assert exit_code(cur, comps) == EXIT_CLEAN


class TestCommandOutput:
    """What the command prints: never library identifiers unless asked (FR-009)."""

    @pytest.fixture
    def cli(self, monkeypatch: pytest.MonkeyPatch) -> _Cli:
        return _Cli(monkeypatch)

    def _baseline(self, tmp_path: Path, *results: CheckResult) -> Path:
        path = tmp_path / "base.json"
        path.write_text(_run(*results).model_dump_json())
        return path

    def test_transcript_keys_are_hidden_by_default_and_shown_on_request(
        self, cli: _Cli, tmp_path: Path
    ) -> None:
        """Mutation: print ``sample_new`` regardless of ``hidden_keys`` in
        ``_print_comparison``; the video-ID key then appears and this test goes red.
        """
        base = self._baseline(
            tmp_path, _result("T1-correction-flag", set(), kind="library_identifier")
        )
        hidden = cli(
            "--check",
            "T1-correction-flag",
            "--compare",
            str(base),
            outcomes={"T1-correction-flag": {"Abcdefghij9/en"}},
        )
        assert "Abcdefghij9" not in hidden.output
        assert "keys hidden" in hidden.output

        shown = cli(
            "--check",
            "T1-correction-flag",
            "--compare",
            str(base),
            "--show-keys",
            outcomes={"T1-correction-flag": {"Abcdefghij9/en"}},
        )
        assert "Abcdefghij9/en" in shown.output
        assert "contains library identifiers" in shown.output

    def test_row_id_keys_are_sampled_and_not_compared_is_explained(
        self, cli: _Cli, tmp_path: Path
    ) -> None:
        base = self._baseline(tmp_path, _result("G1-alias-placement", set()))
        result = cli(
            "--check",
            "G1",
            "--check",
            "G2",
            "--compare",
            str(base),
            outcomes={"G1-alias-placement": {"row-1"}},
        )
        assert "row-1" in result.output
        assert "G2-merge-state" in result.output and "not compared" in result.output

    def test_save_then_compare_round_trips(self, cli: _Cli, tmp_path: Path) -> None:
        saved = tmp_path / "run.json"
        assert (
            cli(
                "--check",
                "G1",
                "--save",
                str(saved),
                outcomes={"G1-alias-placement": {"k"}},
            ).exit_code
            == 1
        )
        assert oct(saved.stat().st_mode & 0o777) == oct(0o600)
        again = cli(
            "--check",
            "G1",
            "--compare",
            str(saved),
            outcomes={"G1-alias-placement": {"k"}},
        )
        assert again.exit_code == EXIT_CLEAN
        assert "resolved 0" in again.output

    def test_save_into_an_ignored_repository_folder_needs_no_force(
        self, cli: _Cli, tmp_path: Path
    ) -> None:
        """Mutation: refuse every path inside a repository; this save is then refused."""
        repo = tmp_path / "repo"
        (repo / "backups").mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        (repo / ".gitignore").write_text("backups/\n")
        target = repo / "backups" / "run.json"
        assert cli("--save", str(target)).exit_code == EXIT_CLEAN
        assert target.exists()

    def test_a_write_failure_is_a_usage_error(self, cli: _Cli, tmp_path: Path) -> None:
        target = tmp_path / "a-directory"
        target.mkdir()
        assert cli("--save", str(target)).exit_code == 2

    def test_list_shows_id_entry_and_rule(self, cli: _Cli) -> None:
        result = cli("--list")
        assert "G3-tag-counters" in result.output
        assert "G3" in result.output
        assert "recount" in result.output


class TestKeyKinds:
    def test_only_the_transcript_checks_have_library_identifier_keys(self) -> None:
        """A check whose keys are video IDs must say so, or ``--compare`` would print
        them by default. Adding a check means deciding its key kind here, in review.
        """
        assert {c.check_id for c in REGISTRY if c.key_kind == "library_identifier"} == {
            "T1-correction-flag",
            "T1-correction-count",
            "T7-stored-full-text",
        }


class TestTagCountLabels:
    def test_the_recount_builders_keep_the_labels_their_callers_read(self) -> None:
        """``run_recount`` reads ``row.alias_count`` and ``row.video_count``; its unit
        tests mock the rows, so only this pins the real labels.
        """
        from chronovista.repositories.canonical_tag_repository import (
            tag_alias_count_query,
            tag_video_count_query,
        )

        assert list(tag_alias_count_query().selected_columns.keys()) == [
            "canonical_tag_id",
            "alias_count",
        ]
        assert list(tag_video_count_query().selected_columns.keys()) == [
            "canonical_tag_id",
            "video_count",
        ]
