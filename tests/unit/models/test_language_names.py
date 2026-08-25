"""Unit tests for the canonical language-name single source of truth."""

from __future__ import annotations

import pytest

from chronovista.models.language_names import LANGUAGE_NAMES, get_language_name


class TestGetLanguageName:
    """Behaviour of get_language_name()."""

    def test_base_code(self) -> None:
        assert get_language_name("en") == "English"

    def test_region_qualified_code(self) -> None:
        assert get_language_name("en-US") == "English (United States)"

    def test_case_insensitive(self) -> None:
        assert get_language_name("EN-us") == "English (United States)"

    def test_unknown_code_returns_itself(self) -> None:
        assert get_language_name("xyz") == "xyz"

    def test_empty_returns_empty(self) -> None:
        assert get_language_name("") == ""


class TestCorrectedLabels:
    """Regression: these codes were previously mislabeled with wrong countries."""

    @pytest.mark.parametrize(
        ("code", "expected"),
        [
            ("es-MX", "Spanish (Mexico)"),  # was "Spanish (Peru)"
            ("es-ES", "Spanish (Spain)"),  # was "Spanish (Portugal)"
            ("ru-RU", "Russian (Russia)"),  # was "Russian (Norway)"
            ("hi-IN", "Hindi (India)"),  # was "Hindi (Finland)"
            ("en-IN", "English (India)"),
        ],
    )
    def test_country_names_are_correct(self, code: str, expected: str) -> None:
        assert LANGUAGE_NAMES[code] == expected

    def test_no_scrambled_country_survives(self) -> None:
        # Guard against the specific wrong labels reappearing anywhere in the map.
        wrong = {
            "Spanish (Peru)",
            "Spanish (Portugal)",
            "Russian (Norway)",
            "Hindi (Finland)",
            "English (Finland)",
        }
        assert wrong.isdisjoint(set(LANGUAGE_NAMES.values()))
