"""Unit tests for the candidate-suggestion pure functions (Feature 096, T010).

Scorer (Decision 2b) ordering properties, triage boundaries, and the authored
predicate -> type-hint derivation. Pure functions — no DB, no network.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from chronovista.models.enums import EntityType, TriageCategory
from chronovista.services.candidate_suggestion_service import (
    _derive_type_hint,
    _score,
    _triage,
)


class TestDeriveTypeHint:
    def test_single_consistent_type(self) -> None:
        assert _derive_type_hint(["spouse", "child", "father"]) == EntityType.PERSON
        assert _derive_type_hint(["member_of", "employer"]) == EntityType.ORGANIZATION
        assert _derive_type_hint(["place_of_birth"]) == EntityType.PLACE
        assert _derive_type_hint(["participant_in"]) == EntityType.EVENT

    def test_conflicting_types_fall_back_to_other(self) -> None:
        # person (cast_member) vs organization (member_of) → OTHER (spec Assumption)
        assert _derive_type_hint(["cast_member", "member_of"]) == EntityType.OTHER

    def test_unmapped_or_empty_is_other(self) -> None:
        assert _derive_type_hint([]) == EntityType.OTHER
        assert _derive_type_hint(["position_held", "part_of"]) == EntityType.OTHER

    def test_never_returns_tag_only_types(self) -> None:
        # type_hint flows into entity_type, which forbids topic/descriptor.
        for relations in (
            ["spouse"],
            ["member_of"],
            ["notable_work"],
            ["field_of_work"],
        ):
            assert _derive_type_hint(relations) not in (
                EntityType.TOPIC,
                EntityType.DESCRIPTOR,
            )


class TestScore:
    def test_zero_salience_scores_zero(self) -> None:
        assert _score(0, 5.0, 2, 3) == 0.0

    @settings(max_examples=100, deadline=None)
    @given(
        salience_a=st.integers(min_value=0, max_value=1000),
        bump=st.integers(min_value=1, max_value=1000),
        specificity=st.floats(min_value=0.01, max_value=30.0),
        tokens=st.integers(min_value=1, max_value=6),
        corroboration=st.integers(min_value=1, max_value=50),
    )
    def test_monotonic_non_decreasing_in_salience(
        self,
        salience_a: int,
        bump: int,
        specificity: float,
        tokens: int,
        corroboration: int,
    ) -> None:
        lower = _score(salience_a, specificity, tokens, corroboration)
        higher = _score(salience_a + bump, specificity, tokens, corroboration)
        assert higher >= lower

    @settings(max_examples=100, deadline=None)
    @given(
        salience=st.integers(min_value=1, max_value=1000),
        specificity=st.floats(min_value=0.01, max_value=30.0),
        tokens=st.integers(min_value=1, max_value=6),
        corroboration=st.integers(min_value=1, max_value=50),
    )
    def test_monotonic_non_decreasing_in_corroboration(
        self, salience: int, specificity: float, tokens: int, corroboration: int
    ) -> None:
        lower = _score(salience, specificity, tokens, corroboration)
        higher = _score(salience, specificity, tokens, corroboration + 1)
        assert higher >= lower

    def test_more_specific_name_outranks_common_at_equal_salience(self) -> None:
        specific = _score(5, 12.0, 2, 1)  # high specificity
        common = _score(5, 1.0, 2, 1)  # low specificity
        assert specific > common


class TestTriage:
    def test_zero_salience_is_grounds_nowhere(self) -> None:
        assert _triage(0, 2, 5.0) == TriageCategory.GROUNDS_NOWHERE

    def test_frequent_single_token_is_likely_eliminable(self) -> None:
        assert _triage(50, 1, 5.0) == TriageCategory.LIKELY_ELIMINABLE

    def test_high_salience_low_specificity_is_likely_eliminable(self) -> None:
        assert _triage(40, 3, 2.0) == TriageCategory.LIKELY_ELIMINABLE

    def test_specific_present_is_worth_review(self) -> None:
        assert _triage(3, 2, 10.0) == TriageCategory.WORTH_REVIEW

    @settings(max_examples=50, deadline=None)
    @given(
        salience=st.integers(min_value=0, max_value=1000),
        tokens=st.integers(min_value=1, max_value=6),
        specificity=st.floats(min_value=0.0, max_value=30.0),
    )
    def test_triage_is_total_and_valid(
        self, salience: int, tokens: int, specificity: float
    ) -> None:
        # Always returns exactly one valid category; zero salience always grounds-nowhere.
        result = _triage(salience, tokens, specificity)
        assert result in set(TriageCategory)
        if salience == 0:
            assert result == TriageCategory.GROUNDS_NOWHERE


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
