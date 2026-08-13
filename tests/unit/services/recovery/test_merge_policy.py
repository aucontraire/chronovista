"""Tests for the shared fill-only merge policy (Feature 065).

The policy's whole job is to refuse. Most of these tests therefore assert that
nothing was written — which is a shape of test that passes trivially if the
function is broken in the direction of doing nothing at all. Each refusal test
is paired with a positive case proving the same field *can* be written, so
"refused" is distinguishable from "inert".

The single failing condition of the feature's central invariant (FR-015) is
*this source wrote a field that already held a real value*, and
`TestNeverContestsARealValue` is where that lives.
"""

from __future__ import annotations

import pytest

from chronovista.db.models import Video as VideoDB
from chronovista.services.recovery.merge_policy import (
    _TRIMMED_WHITESPACE,
    MAX_PLAUSIBLE_DURATION_SECONDS,
    PLACEHOLDER_TITLE_SQL_PATTERNS,
    build_filmot_update,
    is_placeholder_title,
    placeholder_title_condition,
)

REAL_TITLE = "An Actual Video Title"
URL_PLACEHOLDER = "https://www.youtube.com/watch?v=abcdefghijk"
BRACKET_PLACEHOLDER = "[Placeholder] Video abcdefghijk"


class TestIsPlaceholderTitle:
    """FR-004a, exhaustively — every form the definition names."""

    @pytest.mark.parametrize(
        "title",
        [None, "", "   ", "\t\n", URL_PLACEHOLDER, BRACKET_PLACEHOLDER],
        ids=["null", "empty", "spaces", "whitespace", "url-form", "bracket-form"],
    )
    def test_placeholder_forms_are_recognised(self, title: str | None) -> None:
        assert is_placeholder_title(title) is True

    @pytest.mark.parametrize(
        "title",
        [
            REAL_TITLE,
            "Talk about https://www.youtube.com/watch in the middle",
            "[placeholder] video abcdefghijk",
            "http://www.youtube.com/watch?v=abcdefghijk",
            "Placeholder",
        ],
        ids=["real", "url-mid-string", "wrong-case", "http-scheme", "bare-word"],
    )
    def test_real_titles_are_not_placeholders(self, title: str) -> None:
        """The near-misses matter more than the obvious cases.

        A mid-string URL, a lowercased bracket form and an `http://` variant all
        look like placeholders to a careless predicate. The bracketed form is
        machine-generated so case-sensitivity is correct; no `http://` form
        exists in the data, so matching it would serve zero rows.
        """
        assert is_placeholder_title(title) is False


class TestSqlPatternsAgreeWithTheMatcher:
    """FR-004c: the query and the policy must not be able to disagree."""

    def test_prefix_patterns_are_derived_not_restated(self) -> None:
        assert len(PLACEHOLDER_TITLE_SQL_PATTERNS) == 2
        for pattern in PLACEHOLDER_TITLE_SQL_PATTERNS:
            assert pattern.endswith("%")
            # The literal part must itself be recognised by the matcher, or the
            # query would select rows the policy then refuses.
            assert is_placeholder_title(pattern[:-1]) is True

    def test_patterns_contain_no_unescaped_like_wildcards(self) -> None:
        """Both LIKE wildcards, not just one.

        The rule this enforces names `_` *and* `%`; checking only `_` let a
        future prefix containing `%` through, and `%` is the wildcard that
        over-selects catastrophically rather than subtly.
        """
        for pattern in PLACEHOLDER_TITLE_SQL_PATTERNS:
            assert "_" not in pattern[:-1]
            assert "%" not in pattern[:-1]


class TestTheSqlConditionIsTheSameRule:
    """FR-004c, structurally.

    The candidate query and the conditional UPDATE's write gate must apply one
    predicate, not two that resemble each other. When they merely resembled
    each other, a whitespace-only title was selected, approved, and refused at
    write — re-selected on every run forever, and because all fields move in a
    single statement (FR-011a) the row's valid channel and duration fills were
    discarded with it.
    """

    @staticmethod
    def _compiled() -> str:
        return str(
            placeholder_title_condition(VideoDB.title).compile(
                compile_kwargs={"literal_binds": True}
            )
        )

    def test_it_names_every_disjunct_the_matcher_has(self) -> None:
        sql = self._compiled()

        assert "IS NULL" in sql
        assert "btrim" in sql.lower()
        for pattern in PLACEHOLDER_TITLE_SQL_PATTERNS:
            assert pattern in sql

    def test_the_patterns_are_not_indexed_positionally(self) -> None:
        """A third placeholder form must reach the gate, not just the query.

        The gate used to read ``PATTERNS[0]`` and ``PATTERNS[1]``, so a third
        entry would have been selected and then silently never written.
        """
        sql = self._compiled()

        assert sql.count("LIKE") == len(PLACEHOLDER_TITLE_SQL_PATTERNS)

    def test_sql_trims_exactly_what_python_trims(self) -> None:
        """The charset is named in both halves, so they cannot drift.

        Left to the defaults they disagree: `str.strip()` removes every Unicode
        space, `btrim(col)` removes ASCII space alone.
        """
        assert _TRIMMED_WHITESPACE in self._compiled()

    # Whether PostgreSQL and Python *actually* agree cannot be settled in
    # this file: restating `btrim` in Python would only assert that Python
    # equals Python. `TestBlankTitleAgreement` in the integration suite puts
    # each title through a real database and compares the two verdicts.


class TestNeverContestsARealValue:
    """FR-015's invariant. One failing condition, checked per field."""

    def test_a_real_title_is_never_overwritten(self) -> None:
        out = build_filmot_update(
            REAL_TITLE, None, None, "Archive Title", None, None, True
        )
        assert "title" not in out.updates
        assert "title:stored_value_is_real" in out.refused

    def test_a_present_channel_is_never_overwritten(self) -> None:
        out = build_filmot_update(
            None,
            "UCstored0000000000000001",
            None,
            None,
            "UCnew00000000000000001",
            None,
            True,
        )
        assert "channel_id" not in out.updates

    def test_a_positive_duration_is_never_overwritten(self) -> None:
        out = build_filmot_update(None, None, 300, None, None, 500, True)
        assert "duration" not in out.updates


class TestWritesWhatItShould:
    """The paired positive cases — without these, refusal proves nothing."""

    def test_a_placeholder_title_is_filled(self) -> None:
        out = build_filmot_update(
            URL_PLACEHOLDER, None, None, REAL_TITLE, None, None, True
        )
        assert out.updates["title"] == REAL_TITLE
        assert out.fields_written == ["title"]
        assert out.writes_anything is True

    def test_the_bracket_form_is_also_filled(self) -> None:
        """Both forms, because handling one silently skips half the targets."""
        out = build_filmot_update(
            BRACKET_PLACEHOLDER, None, None, REAL_TITLE, None, None, True
        )
        assert out.updates["title"] == REAL_TITLE

    def test_an_absent_channel_is_filled_when_known(self) -> None:
        out = build_filmot_update(
            None, None, None, None, "UCknown000000000000001", None, True
        )
        assert out.updates["channel_id"] == "UCknown000000000000001"
        assert out.unknown_channel_id is None

    @pytest.mark.parametrize("stored", [None, 0], ids=["null", "zero"])
    def test_an_absent_duration_is_filled(self, stored: int | None) -> None:
        out = build_filmot_update(None, None, stored, None, None, 214, True)
        assert out.updates["duration"] == 214


class TestRefusals:
    """Each rule that discards data the archive supplied, and reports it."""

    def test_an_incoming_placeholder_title_is_refused(self) -> None:
        """FR-004b — writing it satisfies fill-only while leaving the gap."""
        out = build_filmot_update(
            URL_PLACEHOLDER, None, None, BRACKET_PLACEHOLDER, None, None, True
        )
        assert "title" not in out.updates
        assert "title:incoming_is_placeholder" in out.refused

    def test_an_unknown_channel_is_reported_not_written(self) -> None:
        out = build_filmot_update(
            None, None, None, None, "UCunknown00000000000001", None, False
        )
        assert "channel_id" not in out.updates
        assert out.unknown_channel_id == "UCunknown00000000000001"
        assert "channel_id:channel_unknown" in out.refused

    def test_a_zero_incoming_duration_is_ignored(self) -> None:
        """Zero means "unknown" at the source, not "zero seconds"."""
        out = build_filmot_update(None, None, None, None, None, 0, True)
        assert "duration" not in out.updates

    @pytest.mark.parametrize(
        "incoming", [MAX_PLAUSIBLE_DURATION_SECONDS + 1, 77_986_171]
    )
    def test_an_implausible_duration_is_refused(self, incoming: int) -> None:
        """The library already holds a duration of roughly 902 days."""
        out = build_filmot_update(None, None, None, None, None, incoming, True)
        assert "duration" not in out.updates
        assert "duration:incoming_implausible" in out.refused

    def test_the_boundary_value_is_accepted(self) -> None:
        """24h exactly is plausible; the rule is *exceeds*, not *reaches*."""
        out = build_filmot_update(
            None, None, None, None, None, MAX_PLAUSIBLE_DURATION_SECONDS, True
        )
        assert out.updates["duration"] == MAX_PLAUSIBLE_DURATION_SECONDS


class TestNothingToWrite:
    def test_an_empty_outcome_writes_nothing_and_claims_nothing(self) -> None:
        """`updates` empty ⇒ no write AND no contribution record (FR-013)."""
        out = build_filmot_update(
            REAL_TITLE, "UCx0000000000000000001", 300, None, None, None, True
        )

        assert out.updates == {}
        assert out.fields_written == []
        assert out.writes_anything is False

    def test_upload_date_cannot_be_emitted(self) -> None:
        """FR-008 is structural: the value is not a parameter at all.

        Asserting the emitted column set is stronger than asserting one absent
        key — it fails if any future field is added without a decision.
        """
        out = build_filmot_update(
            URL_PLACEHOLDER,
            None,
            None,
            REAL_TITLE,
            "UCk00000000000000000001",
            214,
            True,
        )
        assert set(out.updates) <= {"title", "channel_id", "duration"}
