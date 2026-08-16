"""Unit tests for the provenance filter builder (Feature 066, US3 / T016).

``parse_provenance_filter`` is the single place the multi-select ``source``
query param is normalised and validated. These tests pin FR-007/008/009:

- one value selects that source only;
- several values union (order-independent, deduplicated);
- empty/absent means "all sources" (``None``);
- detection method (rule_match, spacy_ner, ...) is NEVER a valid filter input —
  provenance and detection method are separate axes.
"""

from __future__ import annotations

import pytest

from chronovista.api.routers.entity_mentions import parse_provenance_filter
from chronovista.exceptions import APIValidationError


class TestEmptyMeansAll:
    def test_none_returns_none(self) -> None:
        assert parse_provenance_filter(None) is None

    def test_empty_list_returns_none(self) -> None:
        assert parse_provenance_filter([]) is None

    def test_blank_and_whitespace_only_returns_none(self) -> None:
        assert parse_provenance_filter(["", "  ", ","]) is None


class TestSingleSourceOnly:
    @pytest.mark.parametrize(
        "value", ["manual", "transcript", "title", "description", "tag"]
    )
    def test_single_value_returns_just_that_source(self, value: str) -> None:
        assert parse_provenance_filter([value]) == [value]


class TestMultiSelectUnion:
    def test_repeated_params_union_sorted(self) -> None:
        assert parse_provenance_filter(["transcript", "title"]) == [
            "title",
            "transcript",
        ]

    def test_comma_separated_is_split(self) -> None:
        assert parse_provenance_filter(["tag,title"]) == ["tag", "title"]

    def test_mixed_repeated_and_comma_forms(self) -> None:
        assert parse_provenance_filter(["tag,title", "manual"]) == [
            "manual",
            "tag",
            "title",
        ]

    def test_duplicates_collapse(self) -> None:
        assert parse_provenance_filter(["tag", "tag", "tag,tag"]) == ["tag"]

    def test_order_independent(self) -> None:
        assert parse_provenance_filter(["title", "tag"]) == parse_provenance_filter(
            ["tag", "title"]
        )


class TestDetectionMethodIsNeverAFilterInput:
    @pytest.mark.parametrize(
        "value", ["rule_match", "spacy_ner", "llm_extraction", "user_correction"]
    )
    def test_detection_methods_are_rejected(self, value: str) -> None:
        # FR-009: detection method is a separate axis, not accepted here.
        with pytest.raises(APIValidationError):
            parse_provenance_filter([value])

    def test_unknown_value_is_rejected(self) -> None:
        with pytest.raises(APIValidationError):
            parse_provenance_filter(["banana"])

    def test_one_bad_value_among_good_rejects_the_whole_request(self) -> None:
        with pytest.raises(APIValidationError):
            parse_provenance_filter(["tag", "rule_match"])
