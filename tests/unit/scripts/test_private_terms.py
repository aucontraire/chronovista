"""The privacy hook: ``check_private_terms.py`` and ``gen_private_terms.py``.

Both scripts share one term-file contract, so they are tested together. Every name
and identifier here is a made-up placeholder; none comes from any library. Each
docstring that guards a specific rule names the ``Mutation`` that turns it red.
"""

from __future__ import annotations

import logging
import os
import pathlib
import subprocess
import time

import pytest

from scripts.utilities import check_private_terms as checker
from scripts.utilities import gen_private_terms as generator

SALT = "testsalt"
VIDEO = "Abcdefghij9"  # an 11-character placeholder video ID
CHANNEL = "UC" + "q" * 22
OWNER = "UC" + "w" * 22
PLAYLIST = "PL" + "x" * 32
INTERNAL = "int_" + "0123456789abcdef" * 2
PREFIX = "PLzzqqzzqq"


def _write_terms(path: pathlib.Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _id(id_class: str, value: str) -> str:
    return f"@id {id_class} {checker.hash_identifier(SALT, value)}"


@pytest.fixture
def terms_file(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    path = tmp_path / ".private-terms"
    monkeypatch.setattr(checker, "TERMS_FILE", path)
    _write_terms(
        path,
        [
            "Zeta Quux",
            "ZAP",
            "X9Z",
            f"@salt {SALT}",
            _id("video", VIDEO),
            _id("channel", CHANNEL),
            _id("owner", OWNER),
            _id("channel", OWNER),
            _id("playlist", PLAYLIST),
            _id("playlist", INTERNAL),
            f"@prefix playlist {PREFIX}",
        ],
    )
    return path


def _findings(text: str) -> list[str]:
    terms = checker.parse_terms(checker.TERMS_FILE.read_text().splitlines())
    return checker.Matcher(terms).findings(text)


class TestNames:
    def test_a_names_only_file_reads_as_it_always_did(
        self, tmp_path: pathlib.Path
    ) -> None:
        terms = checker.parse_terms(["Zeta Quux", "", "Yodel Vance"])
        assert terms.names == ["Zeta Quux", "Yodel Vance"]
        assert checker.Matcher(terms).findings("we met zeta quux today") == [
            "zeta quux"
        ]

    def test_an_accented_spelling_still_matches(self, terms_file: pathlib.Path) -> None:
        assert _findings("Zéta Quux was there") == ["Zeta Quux"]

    def test_an_acronym_matches_only_in_capitals(
        self, terms_file: pathlib.Path
    ) -> None:
        """Mutation: build the acronym pattern with ``re.IGNORECASE``; the ordinary
        word then matches and this test goes red.
        """
        assert _findings("zap the cache, then Zap it again") == []
        assert _findings("the ZAP report") == ["ZAP"]

    def test_an_acronym_may_contain_digits(self, terms_file: pathlib.Path) -> None:
        assert _findings("the X9Z summit") == ["X9Z"]
        assert _findings("the x9z summit") == []

    def test_an_acronym_matches_only_as_a_whole_word(
        self, terms_file: pathlib.Path
    ) -> None:
        """Mutation: drop the word boundary from the acronym pattern; ``ZAPPER`` then
        matches and this test goes red.
        """
        assert _findings("the ZAPPER tool") == []

    def test_six_capitals_is_an_acronym_and_seven_is_not(self) -> None:
        assert checker.is_acronym("ABCDEF")
        assert not checker.is_acronym("ABCDEFG")

    def test_a_long_capitalised_name_is_not_an_acronym(self) -> None:
        assert not checker.is_acronym("ABCDEFG")
        assert not checker.is_acronym("A")
        assert not checker.is_acronym("Ab")
        assert checker.is_acronym("AB")


class TestIdentifiers:
    @pytest.mark.parametrize(
        ("text", "label"),
        [
            (
                f"see https://youtube.com/watch?v={VIDEO}&t=3",
                "library video identifier",
            ),
            (f"channel {CHANNEL} here", "library channel identifier"),
            (f"owner {OWNER}", "owner account identifier"),
            (f"playlist {PLAYLIST}", "library playlist identifier"),
            (f"internal {INTERNAL.upper()}", "library playlist identifier"),
        ],
    )
    def test_each_class_is_caught_and_named(
        self, terms_file: pathlib.Path, text: str, label: str
    ) -> None:
        """Mutation: skip hashing in ``Matcher.findings``; nothing is caught."""
        assert _findings(text) == [label]

    def test_the_owner_wins_over_the_channel_class(
        self, terms_file: pathlib.Path
    ) -> None:
        assert _findings(OWNER) == ["owner account identifier"]

    def test_a_lookalike_not_in_the_library_is_not_flagged(
        self, terms_file: pathlib.Path
    ) -> None:
        assert _findings("Zyxwvutsrqp and UC" + "r" * 22) == []

    @pytest.mark.parametrize(
        "text",
        [
            f"prefix_{VIDEO}",
            f"{VIDEO}_en.vtt",
            f"https%3A%2F%2Fyoutu.be%2F{VIDEO}",
            f"line\\n{VIDEO}",
            f"{VIDEO}-{VIDEO}",
        ],
    )
    def test_an_identifier_glued_into_a_longer_token_is_caught(
        self, terms_file: pathlib.Path, text: str
    ) -> None:
        """Mutation: hash only whole tokens in ``candidate_identifiers``; a glued ID
        is then missed and this test goes red.
        """
        assert "library video identifier" in _findings(text)

    def test_an_identifier_split_across_lines_is_a_stated_gap(
        self, terms_file: pathlib.Path
    ) -> None:
        assert _findings(VIDEO[:5]) == [] and _findings(VIDEO[5:]) == []

    def test_a_glued_owner_prefix_is_caught(self, terms_file: pathlib.Path) -> None:
        """Mutation: anchor the prefix at a token start; a prefix behind ``UC`` is then
        missed and this test goes red.
        """
        assert _findings(f"UC{PREFIX}SyntheticTail") == ["owner playlist prefix"]

    def test_the_owner_prefix_is_matched_literally(
        self, terms_file: pathlib.Path
    ) -> None:
        assert _findings(f"{PREFIX}AnythingElse123") == ["owner playlist prefix"]
        assert _findings(PREFIX.lower()) == []


class TestModes:
    def test_text_mode_reports_classes_never_values(
        self,
        terms_file: pathlib.Path,
        tmp_path: pathlib.Path,
        capsys: pytest.CaptureFixture[str],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Mutation: report the matched token instead of its class; the value then
        appears in stderr and this test goes red.
        """
        body = tmp_path / "body.md"
        body.write_text(f"Zeta Quux in {VIDEO} and {OWNER}\n", encoding="utf-8")
        with caplog.at_level(logging.DEBUG):
            assert checker.main(["--text", str(body)]) == 1
        out = capsys.readouterr()
        for value in (VIDEO, OWNER):
            assert value not in out.out + out.err
            assert value not in caplog.text
        assert "library video identifier" in out.err
        assert "owner account identifier" in out.err

    def test_message_mode_uses_the_same_rules(
        self, terms_file: pathlib.Path, tmp_path: pathlib.Path
    ) -> None:
        message = tmp_path / "msg"
        message.write_text("fix: zap the stale cache\n", encoding="utf-8")
        assert checker.main(["--msg", str(message)]) == 0
        message.write_text(f"fix: drop {PLAYLIST}\n", encoding="utf-8")
        assert checker.main(["--msg", str(message)]) == 1

    def test_tree_mode_scans_tracked_files_and_skips_binaries(
        self,
        terms_file: pathlib.Path,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        (repo / "notes.md").write_text("clean line\nmet Zeta Quux\n", encoding="utf-8")
        (repo / "blob.bin").write_bytes(b"\x00\x01Zeta Quux")
        (repo / "latin1.txt").write_bytes("caf\xe9".encode("latin-1"))
        subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
        monkeypatch.chdir(repo)

        assert checker.main(["--tree"]) == 1

        err = capsys.readouterr().err
        assert "notes.md:2" in err
        assert "blob.bin" not in err.split("Scanned")[0]
        assert "latin1.txt" not in err  # scanned, but holds nothing
        assert "2 tracked files (1 binary skipped)" in err

    def test_a_missing_list_fails_open_with_a_notice(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setattr(checker, "TERMS_FILE", tmp_path / "absent")
        assert checker.main(["--text", "-"]) == 0
        assert "did NOT run" in capsys.readouterr().err

    def test_a_stale_list_warns_and_still_runs(
        self,
        terms_file: pathlib.Path,
        tmp_path: pathlib.Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Mutation: return early on a stale list; the finding is then missed."""
        old = time.time() - 20 * 86400
        os.utime(terms_file, (old, old))
        body = tmp_path / "body.md"
        body.write_text("Zeta Quux\n", encoding="utf-8")
        assert checker.main(["--text", str(body)]) == 1
        assert "days old" in capsys.readouterr().err


class TestGenerator:
    def test_the_owner_prefix_needs_a_90_percent_share(self) -> None:
        shared = [PREFIX + f"{i:022d}" for i in range(9)]
        assert (
            generator.owner_playlist_prefix([*shared, "PL" + "y" * 32])
            == PREFIX + "0" * 21
        )
        assert (
            generator.owner_playlist_prefix(
                [*shared[:5], *("PL" + c * 32 for c in "abcde")]
            )
            is None
        )

    def test_a_short_shared_prefix_is_not_recorded(self) -> None:
        """Every YouTube playlist starts with ``PL``; that alone identifies no one."""
        assert (
            generator.owner_playlist_prefix(["PL" + c * 32 for c in "abcdefghij"])
            is None
        )

    def test_a_spelling_that_undoes_an_acronym_is_dropped(self) -> None:
        """Mutation: keep every spelling; ``Zap`` would re-flag the ordinary word."""
        assert generator.drop_acronym_collisions(["ZAP", "Zap", "Zeta Quux"]) == [
            "ZAP",
            "Zeta Quux",
        ]

    def test_names_starting_with_at_are_rejected(self) -> None:
        kept, rejected = generator.prepare_names(["Zeta Quux", "@salt x"])
        assert kept == ["Zeta Quux"] and rejected == ["@salt x"]

    def test_identifier_records_match_the_checker_and_skip_exemptions(self) -> None:
        """Mutation: hash with a different rule in the generator; the checker's
        lookup then misses and this test goes red.
        """
        records, counts = generator.identifier_records(
            SALT,
            owner_ids=[OWNER, "local_user"],
            library_ids={
                "video": [VIDEO, next(iter(generator.PLACEHOLDER_IDENTIFIERS))],
                "playlist": [PLAYLIST, "LL"],
            },
        )
        terms = checker.parse_terms([f"@salt {SALT}", *records])
        matcher = checker.Matcher(terms)
        assert matcher.findings(VIDEO) == ["library video identifier"]
        assert matcher.findings(next(iter(generator.PLACEHOLDER_IDENTIFIERS))) == []
        assert counts["video"] == 1 and counts["playlist"] == 1 and counts["owner"] == 1
        assert counts["owner (unrecognised shape, not covered)"] == 1
        assert all(VIDEO not in r and OWNER not in r for r in records)


class TestTermFileProblems:
    @pytest.mark.parametrize(
        ("lines", "problem"),
        [
            ([_id("video", VIDEO)], "0 @salt lines"),
            ([f"@salt {SALT}", "@salt other", _id("video", VIDEO)], "2 @salt lines"),
            ([f"@salt {SALT}", "@id vidoe abc"], "unknown class"),
            ([f"@salt {SALT}", "@id video"], "malformed"),
        ],
    )
    def test_a_problem_is_reported_not_silent(
        self, lines: list[str], problem: str
    ) -> None:
        """Mutation: drop a problem from ``parse_terms``; the coverage loss is then
        silent and this test goes red.
        """
        assert any(problem in p for p in checker.parse_terms(lines).problems)

    def test_without_its_salt_no_identifier_is_trusted(self) -> None:
        terms = checker.parse_terms([_id("video", VIDEO)])
        assert terms.id_hashes == {}

    def test_a_byte_order_mark_does_not_hide_the_first_name(self) -> None:
        terms = checker.parse_terms(["\ufeffZeta Quux"])
        assert checker.Matcher(terms).findings("Zeta Quux") == ["Zeta Quux"]

    def test_uppercase_hashes_still_match(self) -> None:
        line = _id("video", VIDEO)
        terms = checker.parse_terms(
            [f"@salt {SALT}", line[: line.rindex(" ") + 1] + line.split()[-1].upper()]
        )
        assert checker.Matcher(terms).findings(VIDEO) == ["library video identifier"]


class TestStagedLines:
    def test_an_added_line_starting_with_plus_plus_is_scanned(
        self,
        terms_file: pathlib.Path,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A diff shows it as ``+++ …``, like a file header.

        Mutation: treat every ``+++`` line as a header; this line is then dropped and
        the commit passes.
        """
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        (repo / "notes.md").write_text("++ Zeta Quux here\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
        monkeypatch.chdir(repo)

        assert checker.main([]) == 1

    def test_a_staged_identifier_is_refused_by_class_only(
        self,
        terms_file: pathlib.Path,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        (repo / "fixture.py").write_text(f'OWNER = "{OWNER}"\n', encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
        monkeypatch.chdir(repo)

        assert checker.main([]) == 1
        err = capsys.readouterr().err
        assert "fixture.py" in err and "owner account identifier" in err
        assert OWNER not in err

    def test_a_plus_plus_line_after_a_removed_dash_dash_line_is_scanned(
        self,
        terms_file: pathlib.Path,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A removed ``-- x`` line then an added ``++ y`` line look like a file header.

        Mutation: accept any ``--- `` line before ``+++ ``; the added line is then
        taken for a header and skipped.
        """
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        notes = repo / "notes.sql"
        notes.write_text("-- old comment\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(repo),
                "-c",
                "user.email=t@t",
                "-c",
                "user.name=t",
                "commit",
                "-q",
                "-m",
                "seed",
            ],
            check=True,
        )
        notes.write_text("++ Zeta Quux here\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
        monkeypatch.chdir(repo)

        assert checker.main([]) == 1


class TestGeneratorExemptions:
    def test_an_exemption_spares_an_acronym_only_when_it_is_the_acronym(self) -> None:
        """Mutation: compare exemptions case-insensitively for acronyms too; the
        acronym is then exempted by an ordinary word and this test goes red.
        """
        assert generator.exempt("CAST", {"Cast"}) is False
        assert generator.exempt("CAST", {"CAST"}) is True
        assert generator.exempt("Cast Iron", {"cast iron"}) is True


class TestTreeIdentifiers:
    def test_tree_mode_reports_an_identifier_by_class_with_file_and_line(
        self,
        terms_file: pathlib.Path,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        (repo / "docs.md").write_text(f"intro\nsee {VIDEO}_en.vtt\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
        monkeypatch.chdir(repo)

        assert checker.main(["--tree"]) == 1
        err = capsys.readouterr().err
        assert "docs.md:2" in err and "library video identifier" in err
        assert VIDEO not in err
