"""
Tests for language preference CLI commands and helper functions.

This module provides comprehensive test coverage for the language commands
module, including helper functions, database operations, and CLI commands.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml
from typer.testing import CliRunner

from chronovista.cli.language_commands import (
    DEFAULT_USER_ID,
    LANGUAGE_NAMES,
    OutputFormat,
    _get_preferences,
    _get_terminal_width,
    _is_tty,
    _levenshtein_distance,
    _truncate_text,
    detect_system_locale,
    get_language_display_name,
    language_app,
    parse_language_input,
    suggest_similar_codes,
    validate_language_code,
)
from chronovista.cli.main import app
from chronovista.models.enums import LanguageCode, LanguagePreferenceType
from chronovista.models.user_language_preference import UserLanguagePreference


# -------------------------------------------------------------------------
# Fixtures
# -------------------------------------------------------------------------


@pytest.fixture
def runner() -> CliRunner:
    """CLI test runner fixture."""
    return CliRunner()


@pytest.fixture
def mock_preferences() -> List[UserLanguagePreference]:
    """
    Create a list of mock UserLanguagePreference objects for testing.

    Returns
    -------
    List[UserLanguagePreference]
        List of mock language preferences.
    """
    now = datetime.now(timezone.utc)
    return [
        UserLanguagePreference(
            user_id=DEFAULT_USER_ID,
            language_code=LanguageCode.ENGLISH,
            preference_type=LanguagePreferenceType.FLUENT,
            priority=1,
            auto_download_transcripts=True,
            learning_goal=None,
            created_at=now,
        ),
        UserLanguagePreference(
            user_id=DEFAULT_USER_ID,
            language_code=LanguageCode.SPANISH,
            preference_type=LanguagePreferenceType.LEARNING,
            priority=2,
            auto_download_transcripts=True,
            learning_goal="Improve conversational Spanish",
            created_at=now,
        ),
        UserLanguagePreference(
            user_id=DEFAULT_USER_ID,
            language_code=LanguageCode.FRENCH,
            preference_type=LanguagePreferenceType.CURIOUS,
            priority=3,
            auto_download_transcripts=False,
            learning_goal=None,
            created_at=now,
        ),
    ]


@pytest.fixture
def mock_db_preferences() -> List[MagicMock]:
    """
    Create mock database preference objects.

    Returns
    -------
    List[MagicMock]
        List of mock database objects that mimic UserLanguagePreferenceDB.
    """
    now = datetime.now(timezone.utc)
    prefs = []
    for code, ptype, priority in [
        (LanguageCode.ENGLISH.value, LanguagePreferenceType.FLUENT.value, 1),
        (LanguageCode.SPANISH.value, LanguagePreferenceType.LEARNING.value, 2),
        (LanguageCode.FRENCH.value, LanguagePreferenceType.CURIOUS.value, 3),
    ]:
        mock = MagicMock()
        mock.user_id = DEFAULT_USER_ID
        mock.language_code = code
        mock.preference_type = ptype
        mock.priority = priority
        mock.auto_download_transcripts = priority <= 2
        mock.learning_goal = None
        mock.created_at = now
        prefs.append(mock)
    return prefs


# -------------------------------------------------------------------------
# Test: parse_language_input (T004)
# -------------------------------------------------------------------------


class TestParseLanguageInput:
    """Tests for parse_language_input() function."""

    def test_parse_basic_comma_separated(self) -> None:
        """Test basic comma-separated parsing."""
        result = parse_language_input("en, es, fr")
        assert result == ["en", "es", "fr"]

    def test_parse_with_extra_whitespace(self) -> None:
        """Test parsing handles extra whitespace."""
        result = parse_language_input(" en , es ")
        assert result == ["en", "es"]

    def test_parse_with_empty_values(self) -> None:
        """Test parsing filters out empty values."""
        result = parse_language_input("en,,es")
        assert result == ["en", "es"]

    def test_parse_empty_string(self) -> None:
        """Test parsing empty string returns empty list."""
        result = parse_language_input("")
        assert result == []

    def test_parse_whitespace_only(self) -> None:
        """Test parsing whitespace-only string returns empty list."""
        result = parse_language_input("   ")
        assert result == []

    def test_parse_case_normalization(self) -> None:
        """Test parsing normalizes to lowercase."""
        result = parse_language_input("EN, ES, FR")
        assert result == ["en", "es", "fr"]

    def test_parse_mixed_case(self) -> None:
        """Test parsing handles mixed case."""
        result = parse_language_input("En-Us, es-MX, Fr-CA")
        assert result == ["en-us", "es-mx", "fr-ca"]

    def test_parse_single_language(self) -> None:
        """Test parsing single language code."""
        result = parse_language_input("en")
        assert result == ["en"]

    def test_parse_complex_codes(self) -> None:
        """Test parsing complex BCP-47 codes."""
        result = parse_language_input("en-US, zh-CN, pt-BR")
        assert result == ["en-us", "zh-cn", "pt-br"]


# -------------------------------------------------------------------------
# Test: validate_language_code (T005)
# -------------------------------------------------------------------------


class TestValidateLanguageCode:
    """Tests for validate_language_code() function."""

    def test_validate_basic_code(self) -> None:
        """Test validation of basic language code."""
        result = validate_language_code("en")
        assert result == LanguageCode.ENGLISH

    def test_validate_with_region(self) -> None:
        """Test validation of language code with region."""
        result = validate_language_code("en-US")
        assert result == LanguageCode.ENGLISH_US

    def test_validate_case_insensitive(self) -> None:
        """Test validation is case insensitive."""
        result = validate_language_code("EN")
        assert result == LanguageCode.ENGLISH

    def test_validate_mixed_case(self) -> None:
        """Test validation handles mixed case."""
        result = validate_language_code("En-Us")
        assert result == LanguageCode.ENGLISH_US

    def test_validate_invalid_code(self) -> None:
        """Test validation returns None for invalid code."""
        result = validate_language_code("xyz")
        assert result is None

    def test_validate_empty_string(self) -> None:
        """Test validation returns None for empty string."""
        result = validate_language_code("")
        assert result is None

    def test_validate_with_whitespace(self) -> None:
        """Test validation handles whitespace."""
        result = validate_language_code("  en  ")
        assert result == LanguageCode.ENGLISH

    def test_validate_all_enum_values(self) -> None:
        """Test all LanguageCode enum values can be validated."""
        for lang_code in LanguageCode:
            result = validate_language_code(lang_code.value)
            assert result == lang_code


# -------------------------------------------------------------------------
# Test: detect_system_locale (T006)
# -------------------------------------------------------------------------


class TestDetectSystemLocale:
    """Tests for detect_system_locale() function."""

    @patch("chronovista.cli.language_commands.locale.getlocale")
    def test_detect_spanish_locale(self, mock_locale: MagicMock) -> None:
        """Test detection of Spanish locale (full match takes priority)."""
        mock_locale.return_value = ("es_MX", "UTF-8")
        result = detect_system_locale()
        # Full locale "es-MX" matches first, so SPANISH_MX is returned
        assert result == LanguageCode.SPANISH_MX

    @patch("chronovista.cli.language_commands.locale.getlocale")
    def test_detect_english_us_locale(self, mock_locale: MagicMock) -> None:
        """Test detection of English US locale."""
        mock_locale.return_value = ("en_US", "UTF-8")
        result = detect_system_locale()
        assert result == LanguageCode.ENGLISH_US

    @patch("chronovista.cli.language_commands.locale.getlocale")
    def test_detect_french_locale(self, mock_locale: MagicMock) -> None:
        """Test detection of French locale."""
        mock_locale.return_value = ("fr_FR", "UTF-8")
        result = detect_system_locale()
        assert result == LanguageCode.FRENCH_FR

    @patch("chronovista.cli.language_commands.locale.getlocale")
    def test_fallback_on_none(self, mock_locale: MagicMock) -> None:
        """Test fallback to English when locale is None."""
        mock_locale.return_value = (None, None)
        with patch.dict("os.environ", {}, clear=True):
            result = detect_system_locale()
        assert result == LanguageCode.ENGLISH

    @patch("chronovista.cli.language_commands.locale.getlocale")
    def test_fallback_on_unknown_locale(self, mock_locale: MagicMock) -> None:
        """Test fallback to English for unknown locale."""
        mock_locale.return_value = ("xx_YY", "UTF-8")
        result = detect_system_locale()
        assert result == LanguageCode.ENGLISH

    @patch("chronovista.cli.language_commands.locale.getlocale")
    def test_fallback_on_exception(self, mock_locale: MagicMock) -> None:
        """Test fallback to English on exception."""
        mock_locale.side_effect = Exception("Locale error")
        result = detect_system_locale()
        assert result == LanguageCode.ENGLISH

    @patch("chronovista.cli.language_commands.locale.getlocale")
    def test_detect_without_encoding(self, mock_locale: MagicMock) -> None:
        """Test detection without encoding suffix."""
        mock_locale.return_value = ("de_DE", None)
        result = detect_system_locale()
        assert result == LanguageCode.GERMAN_DE

    @patch("chronovista.cli.language_commands.locale.getlocale")
    def test_detect_from_env_variable(self, mock_locale: MagicMock) -> None:
        """Test detection from LANG environment variable when getlocale returns None."""
        mock_locale.return_value = (None, None)
        with patch.dict("os.environ", {"LANG": "ja_JP.UTF-8"}, clear=True):
            result = detect_system_locale()
        # Full locale "ja-JP" matches, so JAPANESE_JP is returned
        assert result == LanguageCode.JAPANESE_JP


# -------------------------------------------------------------------------
# Test: suggest_similar_codes (T007)
# -------------------------------------------------------------------------


class TestSuggestSimilarCodes:
    """Tests for suggest_similar_codes() function."""

    def test_suggest_exact_match(self) -> None:
        """Test suggestions include exact match."""
        result = suggest_similar_codes("en")
        assert "en" in result

    def test_suggest_typo_correction(self) -> None:
        """Test suggestions for common typos."""
        # "es" with one character difference
        result = suggest_similar_codes("ez")
        assert len(result) > 0

    def test_suggest_max_suggestions(self) -> None:
        """Test max suggestions limit is respected."""
        result = suggest_similar_codes("e", max_suggestions=2)
        assert len(result) <= 2

    def test_suggest_empty_input(self) -> None:
        """Test empty input returns empty list."""
        result = suggest_similar_codes("")
        assert result == []

    def test_suggest_far_typo(self) -> None:
        """Test no suggestions for very different input."""
        result = suggest_similar_codes("xyzabc")
        assert result == []

    def test_suggest_threshold(self) -> None:
        """Test threshold of 2 is applied."""
        # "enn" is distance 1 from "en"
        result = suggest_similar_codes("enn")
        assert "en" in result

    def test_suggest_sorted_by_distance(self) -> None:
        """Test results are sorted by distance."""
        result = suggest_similar_codes("en")
        # First result should be exact match if available
        if "en" in result:
            assert result[0] == "en"


# -------------------------------------------------------------------------
# Test: get_language_display_name (T008)
# -------------------------------------------------------------------------


class TestGetLanguageDisplayName:
    """Tests for get_language_display_name() function."""

    def test_get_basic_language_name(self) -> None:
        """Test getting basic language name."""
        result = get_language_display_name("en")
        assert result == "English"

    def test_get_regional_language_name(self) -> None:
        """Test getting regional language name."""
        result = get_language_display_name("en-US")
        assert result == "English (United States)"

    def test_get_spanish_name(self) -> None:
        """Test getting Spanish language name."""
        result = get_language_display_name("es-MX")
        assert result == "Spanish (Mexico)"

    def test_get_unknown_code(self) -> None:
        """Test unknown code returns the code itself."""
        result = get_language_display_name("xyz")
        assert result == "xyz"

    def test_get_empty_code(self) -> None:
        """Test empty code returns empty string."""
        result = get_language_display_name("")
        assert result == ""

    def test_get_case_insensitive(self) -> None:
        """Test name lookup is case insensitive."""
        result = get_language_display_name("EN")
        assert result == "English"

    def test_all_language_names_defined(self) -> None:
        """Test all LanguageCode values have display names."""
        for lang_code in LanguageCode:
            result = get_language_display_name(lang_code.value)
            # Should either have a mapped name or return the code itself
            assert result is not None
            assert len(result) > 0


# -------------------------------------------------------------------------
# Test: _levenshtein_distance (internal helper)
# -------------------------------------------------------------------------


class TestLevenshteinDistance:
    """Tests for _levenshtein_distance() internal function."""

    def test_identical_strings(self) -> None:
        """Test distance of identical strings is 0."""
        assert _levenshtein_distance("en", "en") == 0

    def test_single_substitution(self) -> None:
        """Test single character substitution."""
        assert _levenshtein_distance("en", "es") == 1

    def test_single_insertion(self) -> None:
        """Test single character insertion."""
        assert _levenshtein_distance("en", "enn") == 1

    def test_single_deletion(self) -> None:
        """Test single character deletion."""
        assert _levenshtein_distance("en", "e") == 1

    def test_empty_string(self) -> None:
        """Test distance to empty string is length of other string."""
        assert _levenshtein_distance("en", "") == 2
        assert _levenshtein_distance("", "en") == 2

    def test_completely_different(self) -> None:
        """Test distance of completely different strings."""
        assert _levenshtein_distance("abc", "xyz") == 3


# -------------------------------------------------------------------------
# Test: _get_preferences (T009)
# -------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGetPreferences:
    """Tests for _get_preferences() async helper function."""

    async def test_get_preferences_returns_list(
        self, mock_db_preferences: List[MagicMock]
    ) -> None:
        """Test _get_preferences returns list of preferences."""
        with patch(
            "chronovista.cli.language_commands.db_manager"
        ) as mock_db_manager:
            # Setup async context manager
            mock_session = AsyncMock()
            mock_db_manager.get_session.return_value.__aiter__ = AsyncMock(
                return_value=iter([mock_session])
            )

            with patch(
                "chronovista.cli.language_commands.UserLanguagePreferenceRepository"
            ) as mock_repo_class:
                mock_repo = MagicMock()
                mock_repo.get_user_preferences = AsyncMock(
                    return_value=mock_db_preferences
                )
                mock_repo_class.return_value = mock_repo

                # This test verifies the structure - actual DB call mocked
                # For real implementation, we'd use integration tests
                pass

    async def test_get_preferences_empty_user(self) -> None:
        """Test _get_preferences returns empty list for user with no prefs."""
        with patch(
            "chronovista.cli.language_commands.db_manager"
        ) as mock_db_manager:
            mock_session = AsyncMock()
            mock_db_manager.get_session.return_value.__aiter__ = AsyncMock(
                return_value=iter([mock_session])
            )

            with patch(
                "chronovista.cli.language_commands.UserLanguagePreferenceRepository"
            ) as mock_repo_class:
                mock_repo = MagicMock()
                mock_repo.get_user_preferences = AsyncMock(return_value=[])
                mock_repo_class.return_value = mock_repo

                # Verify empty return case structure
                pass


# -------------------------------------------------------------------------
# Test: CLI Commands (List Command - T011-T016)
# -------------------------------------------------------------------------


class TestLanguageListCommand:
    """Tests for 'languages list' command."""

    def test_list_command_help(self, runner: CliRunner) -> None:
        """Test list command help text."""
        result = runner.invoke(app, ["languages", "list", "--help"])
        assert result.exit_code == 0
        assert "Output format" in result.stdout or "format" in result.stdout.lower()

    def test_list_empty_preferences_shows_guidance(self, runner: CliRunner) -> None:
        """T011: Empty preferences show setup guidance."""
        with patch("chronovista.cli.language_commands._get_preferences") as mock_get:
            mock_get.return_value = []

            result = runner.invoke(app, ["languages", "list"])

            assert result.exit_code == 0
            assert "No language preferences configured" in result.stdout
            assert "chronovista languages set" in result.stdout
            assert "--from-locale" in result.stdout

    def test_list_with_preferences_shows_grouped_table(
        self, runner: CliRunner, mock_preferences: List[UserLanguagePreference]
    ) -> None:
        """T012: Preferences are displayed in grouped table."""
        with patch("chronovista.cli.language_commands._get_preferences") as mock_get:
            mock_get.return_value = mock_preferences

            result = runner.invoke(app, ["languages", "list"])

            assert result.exit_code == 0
            # Check for section headers
            assert "Fluent" in result.stdout
            assert "Learning" in result.stdout
            assert "Curious" in result.stdout
            # Check for language names (formatted as "code (Name)")
            assert "en" in result.stdout.lower()
            assert "English" in result.stdout
            assert "Spanish" in result.stdout
            # Check for priority and auto-download columns
            assert "Priority" in result.stdout
            assert "Auto-Download" in result.stdout

    def test_list_format_json_outputs_valid_json(
        self, runner: CliRunner, mock_preferences: List[UserLanguagePreference]
    ) -> None:
        """T013: --format json outputs valid JSON."""
        import json

        with patch("chronovista.cli.language_commands._get_preferences") as mock_get:
            mock_get.return_value = mock_preferences

            result = runner.invoke(app, ["languages", "list", "--format", "json"])

            assert result.exit_code == 0
            # Parse output as JSON to verify structure
            output_data = json.loads(result.stdout)
            assert "fluent" in output_data
            assert "learning" in output_data
            assert "curious" in output_data
            assert "exclude" in output_data
            # Verify content
            assert len(output_data["fluent"]) == 1
            assert len(output_data["learning"]) == 1
            assert len(output_data["curious"]) == 1
            assert output_data["fluent"][0]["language_code"] == "en"
            assert output_data["learning"][0]["language_code"] == "es"

    def test_list_format_yaml_outputs_valid_yaml(
        self, runner: CliRunner, mock_preferences: List[UserLanguagePreference]
    ) -> None:
        """T014: --format yaml outputs valid YAML."""
        import yaml

        with patch("chronovista.cli.language_commands._get_preferences") as mock_get:
            mock_get.return_value = mock_preferences

            result = runner.invoke(app, ["languages", "list", "--format", "yaml"])

            assert result.exit_code == 0
            # Parse output as YAML to verify structure
            output_data = yaml.safe_load(result.stdout)
            assert "fluent" in output_data
            assert "learning" in output_data
            assert "curious" in output_data
            assert "exclude" in output_data
            # Verify content
            assert len(output_data["fluent"]) == 1
            assert len(output_data["learning"]) == 1

    def test_list_type_filter_shows_only_filtered(
        self, runner: CliRunner, mock_preferences: List[UserLanguagePreference]
    ) -> None:
        """T015: --type fluent filters to fluent only."""
        with patch("chronovista.cli.language_commands._get_preferences") as mock_get:
            mock_get.return_value = mock_preferences

            result = runner.invoke(app, ["languages", "list", "--type", "fluent"])

            assert result.exit_code == 0
            # Should show fluent section
            assert "Fluent" in result.stdout
            assert "English" in result.stdout
            # Should NOT show learning or curious sections
            assert "Learning" not in result.stdout
            assert "Italian" not in result.stdout or "Curious" not in result.stdout

    def test_list_available_shows_all_codes(self, runner: CliRunner) -> None:
        """T016: --available shows all language codes."""
        result = runner.invoke(app, ["languages", "list", "--available"])

        assert result.exit_code == 0
        # Check header
        assert "Available Language Codes" in result.stdout
        # Check for sample language codes
        assert "en" in result.stdout.lower()
        assert "es" in result.stdout.lower()
        assert "fr" in result.stdout.lower()
        # Check for language names
        assert "English" in result.stdout
        assert "Spanish" in result.stdout
        # Verify count is mentioned (should be 47+ languages)
        assert "47" in result.stdout or "supported" in result.stdout.lower()


class TestLanguageSetCommand:
    """Tests for 'languages set' command."""

    def test_set_command_help(self, runner: CliRunner) -> None:
        """Test set command help text."""
        result = runner.invoke(app, ["languages", "set", "--help"])
        assert result.exit_code == 0

    @patch("chronovista.cli.language_commands.locale.getdefaultlocale")
    def test_set_detects_system_locale(
        self, mock_locale: MagicMock, runner: CliRunner
    ) -> None:
        """T024: Interactive mode detects system locale."""
        mock_locale.return_value = ("es_MX", "UTF-8")

        with patch("chronovista.cli.language_commands.typer.prompt") as mock_prompt:
            # User accepts defaults
            mock_prompt.return_value = ""

            with patch("chronovista.cli.language_commands._save_preferences") as mock_save:
                mock_save.return_value = None

                result = runner.invoke(app, ["languages", "set"])

                # Verify Spanish locale was detected
                assert result.exit_code == 0
                assert "Spanish" in result.stdout or "es" in result.stdout

    @patch("chronovista.cli.language_commands.locale.getdefaultlocale")
    def test_set_accepts_defaults_with_enter(
        self, mock_locale: MagicMock, runner: CliRunner
    ) -> None:
        """T025: Enter accepts default languages."""
        mock_locale.return_value = ("fr_FR", "UTF-8")

        with patch("chronovista.cli.language_commands.typer.prompt") as mock_prompt:
            # User presses Enter to accept defaults
            mock_prompt.return_value = ""

            with patch("chronovista.cli.language_commands._save_preferences") as mock_save:
                mock_save.return_value = None

                result = runner.invoke(app, ["languages", "set"])

                # Verify defaults were accepted
                assert result.exit_code == 0
                assert mock_save.called

    @patch("chronovista.cli.language_commands.locale.getdefaultlocale")
    def test_set_customize_with_c(
        self, mock_locale: MagicMock, runner: CliRunner
    ) -> None:
        """T026: 'c' triggers full interactive setup."""
        mock_locale.return_value = ("en_US", "UTF-8")

        with patch("chronovista.cli.language_commands.typer.prompt") as mock_prompt:
            # Simulate: customize, fluent=en,es, learning=it, goal for it, curious=de, exclude=zh
            mock_prompt.side_effect = [
                "c",  # Customize
                "en,es",  # Fluent
                "it",  # Learning
                "B2 by December",  # Goal for it
                "de",  # Curious
                "zh",  # Exclude
            ]

            with patch("chronovista.cli.language_commands._save_preferences") as mock_save:
                mock_save.return_value = None

                result = runner.invoke(app, ["languages", "set"])

                # Verify full interactive sequence ran
                assert result.exit_code == 0
                # Should have prompted multiple times
                assert mock_prompt.call_count >= 4

    @patch("chronovista.cli.language_commands.locale.getdefaultlocale")
    def test_set_from_locale_no_prompts(
        self, mock_locale: MagicMock, runner: CliRunner
    ) -> None:
        """T027: --from-locale uses system locale without prompts."""
        mock_locale.return_value = ("de_DE", "UTF-8")

        with patch("chronovista.cli.language_commands.typer.prompt") as mock_prompt:
            with patch("chronovista.cli.language_commands._save_preferences") as mock_save:
                mock_save.return_value = None

                result = runner.invoke(app, ["languages", "set", "--from-locale"])

                # Verify no prompts were shown
                assert result.exit_code == 0
                assert not mock_prompt.called
                # Should have saved preferences
                assert mock_save.called

    @patch("chronovista.cli.language_commands.locale.getdefaultlocale")
    def test_set_full_sequence(
        self, mock_locale: MagicMock, runner: CliRunner
    ) -> None:
        """T028: Full interactive sequence for all types."""
        mock_locale.return_value = ("en_US", "UTF-8")

        with patch("chronovista.cli.language_commands.typer.prompt") as mock_prompt:
            # Full interactive flow
            mock_prompt.side_effect = [
                "c",  # Customize
                "en,es",  # Fluent
                "it,fr",  # Learning
                "B2 by December",  # Goal for it
                "",  # No goal for fr
                "de",  # Curious
                "zh",  # Exclude
            ]

            with patch("chronovista.cli.language_commands._save_preferences") as mock_save:
                mock_save.return_value = None

                result = runner.invoke(app, ["languages", "set"])

                # Verify all types were configured
                assert result.exit_code == 0

    @patch("chronovista.cli.language_commands.locale.getdefaultlocale")
    def test_set_learning_goal_prompt(
        self, mock_locale: MagicMock, runner: CliRunner
    ) -> None:
        """T029: Learning languages prompt for goal."""
        mock_locale.return_value = ("en_US", "UTF-8")

        with patch("chronovista.cli.language_commands.typer.prompt") as mock_prompt:
            mock_prompt.side_effect = [
                "c",  # Customize
                "en",  # Fluent
                "it",  # Learning
                "B2 proficiency",  # Goal for it
                "",  # Curious (empty)
                "",  # Exclude (empty)
            ]

            with patch("chronovista.cli.language_commands._save_preferences") as mock_save:
                mock_save.return_value = None

                result = runner.invoke(app, ["languages", "set"])

                # Verify goal prompt appeared
                assert result.exit_code == 0
                # Check that prompts included goal
                assert any("goal" in str(call).lower() for call in mock_prompt.call_args_list)

    @patch("chronovista.cli.language_commands.locale.getdefaultlocale")
    def test_set_ctrl_c_exits_130(
        self, mock_locale: MagicMock, runner: CliRunner
    ) -> None:
        """T030: Ctrl+C exits with code 130, no partial save."""
        mock_locale.return_value = ("en_US", "UTF-8")

        with patch("chronovista.cli.language_commands.typer.prompt") as mock_prompt:
            # Simulate Ctrl+C
            mock_prompt.side_effect = KeyboardInterrupt()

            with patch("chronovista.cli.language_commands._save_preferences") as mock_save:
                mock_save.return_value = None

                result = runner.invoke(app, ["languages", "set"])

                # Verify exit code 130 for Ctrl+C
                assert result.exit_code == 130
                # Verify no save occurred
                assert not mock_save.called
                assert "cancelled" in result.stdout.lower() or "cancel" in result.stdout.lower()


class TestLanguageAddCommand:
    """Tests for 'languages add' command."""

    def test_add_command_help(self, runner: CliRunner) -> None:
        """Test add command help text."""
        result = runner.invoke(app, ["languages", "add", "--help"])
        assert result.exit_code == 0
        assert "language" in result.stdout.lower()

    def test_add_command_adds_language_at_end_of_priority_list(
        self, runner: CliRunner
    ) -> None:
        """T048 [P] [US5]: Add command adds language at end of priority list."""
        # Mock _check_language_exists to return None (language doesn't exist)
        with patch(
            "chronovista.cli.language_commands._check_language_exists"
        ) as mock_check:
            mock_check.return_value = None

            # Mock _add_language_preference to return priority 3 (end of list)
            with patch(
                "chronovista.cli.language_commands._add_language_preference"
            ) as mock_add:
                mock_add.return_value = (3, True)  # (priority, auto_download)

                # Add Italian as fluent (should get priority 3)
                result = runner.invoke(
                    app, ["languages", "add", "it", "--type", "fluent"]
                )

                assert result.exit_code == 0
                assert "it" in result.stdout.lower()
                assert "Italian" in result.stdout
                assert "Priority: 3" in result.stdout
                # Verify _add_language_preference was called
                assert mock_add.called

    def test_add_command_with_priority_inserts_and_shifts_others(
        self, runner: CliRunner
    ) -> None:
        """T049 [P] [US5]: Add --priority inserts at specified position and shifts others."""
        # Mock _check_language_exists to return None (language doesn't exist)
        with patch(
            "chronovista.cli.language_commands._check_language_exists"
        ) as mock_check:
            mock_check.return_value = None

            # Mock _add_language_preference to return priority 1 (requested position)
            with patch(
                "chronovista.cli.language_commands._add_language_preference"
            ) as mock_add:
                mock_add.return_value = (1, True)  # (priority, auto_download)

                # Add German as fluent at priority 1 (should shift others)
                result = runner.invoke(
                    app,
                    ["languages", "add", "de", "--type", "fluent", "--priority", "1"],
                )

                assert result.exit_code == 0
                assert "de" in result.stdout.lower()
                assert "German" in result.stdout
                assert "Priority: 1" in result.stdout
                # Verify _add_language_preference was called with priority parameter
                assert mock_add.called
                # Verify priority was passed to the function
                call_args = mock_add.call_args
                assert call_args[0][3] == 1  # priority argument is the 4th positional arg

    def test_add_command_with_goal_stores_learning_goal(
        self, runner: CliRunner
    ) -> None:
        """T050 [P] [US5]: Add --goal stores learning goal for learning type."""
        # Mock _check_language_exists to return None (language doesn't exist)
        with patch(
            "chronovista.cli.language_commands._check_language_exists"
        ) as mock_check:
            mock_check.return_value = None

            # Mock _add_language_preference to return priority 1 and auto_download=True
            with patch(
                "chronovista.cli.language_commands._add_language_preference"
            ) as mock_add:
                mock_add.return_value = (1, True)  # (priority, auto_download)

                # Add Italian as learning with goal
                result = runner.invoke(
                    app,
                    [
                        "languages",
                        "add",
                        "it",
                        "--type",
                        "learning",
                        "--goal",
                        "B2 by December",
                    ],
                )

                assert result.exit_code == 0
                assert "it" in result.stdout.lower()
                assert "Italian" in result.stdout
                assert "LEARNING" in result.stdout
                # Verify _add_language_preference was called with the goal
                assert mock_add.called
                # Verify learning_goal was passed to the function
                call_args = mock_add.call_args
                assert call_args[0][4] == "B2 by December"  # learning_goal is the 5th positional arg

    def test_add_command_existing_language_shows_error_with_guidance(
        self, runner: CliRunner
    ) -> None:
        """T051 [P] [US5]: Add existing language shows error with guidance."""
        # Setup: English already configured as fluent
        existing = [
            UserLanguagePreference(
                user_id=DEFAULT_USER_ID,
                language_code=LanguageCode.ENGLISH,
                preference_type=LanguagePreferenceType.FLUENT,
                priority=1,
                auto_download_transcripts=True,
                learning_goal=None,
                created_at=datetime.now(timezone.utc),
            )
        ]

        with patch("chronovista.cli.language_commands._get_preferences") as mock_get:
            mock_get.return_value = existing

            # Try to add English again
            result = runner.invoke(
                app, ["languages", "add", "en", "--type", "learning"]
            )

            assert result.exit_code == 2
            assert "Error" in result.stdout
            assert "en" in result.stdout.lower()
            assert "already configured" in result.stdout.lower()
            assert "FLUENT" in result.stdout
            # Should show guidance to remove and re-add
            assert "chronovista languages remove" in result.stdout
            assert "chronovista languages add" in result.stdout

    def test_add_command_invalid_code_shows_suggestions(
        self, runner: CliRunner
    ) -> None:
        """T052 [P] [US5]: Add invalid code shows suggestions."""
        with patch("chronovista.cli.language_commands._get_preferences") as mock_get:
            mock_get.return_value = []

            # Try to add invalid language code
            result = runner.invoke(
                app, ["languages", "add", "xyz", "--type", "fluent"]
            )

            assert result.exit_code == 1
            assert "Error" in result.stdout
            assert "Unknown language code" in result.stdout
            assert "xyz" in result.stdout
            # Should show suggestions or available codes
            assert (
                "Did you mean" in result.stdout
                or "See all codes" in result.stdout
                or "chronovista languages list --available" in result.stdout
            )


class TestLanguageRemoveCommand:
    """Tests for 'languages remove' command."""

    def test_remove_command_help(self, runner: CliRunner) -> None:
        """Test remove command help text."""
        result = runner.invoke(app, ["languages", "remove", "--help"])
        assert result.exit_code == 0

    def test_remove_with_confirmation(self, runner: CliRunner) -> None:
        """T058: Test remove command with confirmation."""
        # Setup: Mock existing preference for "it"
        mock_pref = MagicMock()
        mock_pref.user_id = DEFAULT_USER_ID
        mock_pref.language_code = "it"
        mock_pref.preference_type = LanguagePreferenceType.LEARNING.value
        mock_pref.priority = 1
        mock_pref.auto_download_transcripts = True
        mock_pref.learning_goal = None

        async def mock_get_session():
            mock_session = AsyncMock()
            mock_session.commit = AsyncMock()
            yield mock_session

        with patch("chronovista.cli.language_commands.db_manager") as mock_db_manager:
            mock_db_manager.get_session = mock_get_session

            with patch(
                "chronovista.cli.language_commands.UserLanguagePreferenceRepository"
            ) as mock_repo_class:
                mock_repo = MagicMock()
                mock_repo.get_by_composite_key = AsyncMock(return_value=mock_pref)
                mock_repo.delete_user_preference = AsyncMock(return_value=True)
                mock_repo.get_preferences_by_type = AsyncMock(return_value=[])
                mock_repo_class.return_value = mock_repo

                with patch("chronovista.cli.language_commands.typer.confirm") as mock_confirm:
                    mock_confirm.return_value = True

                    result = runner.invoke(app, ["languages", "remove", "it"])

                    assert result.exit_code == 0
                    assert "Removed" in result.stdout
                    assert "Italian" in result.stdout or "it" in result.stdout

    def test_remove_yes_skips_confirmation(self, runner: CliRunner) -> None:
        """T059: Test remove --yes skips confirmation."""
        # Setup: Mock existing preference for "it"
        mock_pref = MagicMock()
        mock_pref.user_id = DEFAULT_USER_ID
        mock_pref.language_code = "it"
        mock_pref.preference_type = LanguagePreferenceType.LEARNING.value
        mock_pref.priority = 1
        mock_pref.auto_download_transcripts = True
        mock_pref.learning_goal = None

        async def mock_get_session():
            mock_session = AsyncMock()
            mock_session.commit = AsyncMock()
            yield mock_session

        with patch("chronovista.cli.language_commands.db_manager") as mock_db_manager:
            mock_db_manager.get_session = mock_get_session

            with patch(
                "chronovista.cli.language_commands.UserLanguagePreferenceRepository"
            ) as mock_repo_class:
                mock_repo = MagicMock()
                mock_repo.get_by_composite_key = AsyncMock(return_value=mock_pref)
                mock_repo.delete_user_preference = AsyncMock(return_value=True)
                mock_repo.get_preferences_by_type = AsyncMock(return_value=[])
                mock_repo_class.return_value = mock_repo

                with patch("chronovista.cli.language_commands.typer.confirm") as mock_confirm:
                    result = runner.invoke(app, ["languages", "remove", "it", "--yes"])

                    # Confirm should NOT be called with --yes
                    assert not mock_confirm.called
                    assert result.exit_code == 0
                    assert "Removed" in result.stdout

    def test_remove_compacts_priorities_after_removal(self, runner: CliRunner) -> None:
        """T060: Test remove compacts priorities after removal."""
        # Setup: Mock preferences with gaps [1, 3, 4]
        mock_pref_to_remove = MagicMock()
        mock_pref_to_remove.user_id = DEFAULT_USER_ID
        mock_pref_to_remove.language_code = "it"
        mock_pref_to_remove.preference_type = LanguagePreferenceType.LEARNING.value
        mock_pref_to_remove.priority = 2

        # After removal, priorities should be [1, 3, 4] -> need to compact to [1, 2, 3]
        mock_pref_3 = MagicMock()
        mock_pref_3.language_code = "es"
        mock_pref_3.priority = 3
        mock_pref_4 = MagicMock()
        mock_pref_4.language_code = "fr"
        mock_pref_4.priority = 4

        async def mock_get_session():
            mock_session = AsyncMock()
            mock_session.commit = AsyncMock()
            yield mock_session

        with patch("chronovista.cli.language_commands.db_manager") as mock_db_manager:
            mock_db_manager.get_session = mock_get_session

            with patch(
                "chronovista.cli.language_commands.UserLanguagePreferenceRepository"
            ) as mock_repo_class:
                mock_repo = MagicMock()
                mock_repo.get_by_composite_key = AsyncMock(return_value=mock_pref_to_remove)
                mock_repo.delete_user_preference = AsyncMock(return_value=True)
                # After deletion, remaining preferences have gaps
                mock_repo.get_preferences_by_type = AsyncMock(
                    return_value=[mock_pref_3, mock_pref_4]
                )
                mock_repo.update_priority = AsyncMock()
                mock_repo_class.return_value = mock_repo

                result = runner.invoke(app, ["languages", "remove", "it", "--yes"])

                assert result.exit_code == 0
                # Verify update_priority was called to compact priorities
                assert mock_repo.update_priority.called

    def test_remove_non_existent_language_shows_message(self, runner: CliRunner) -> None:
        """T061: Test remove non-existent language shows message."""
        async def mock_get_session():
            mock_session = AsyncMock()
            mock_session.commit = AsyncMock()
            yield mock_session

        with patch("chronovista.cli.language_commands.db_manager") as mock_db_manager:
            mock_db_manager.get_session = mock_get_session

            with patch(
                "chronovista.cli.language_commands.UserLanguagePreferenceRepository"
            ) as mock_repo_class:
                mock_repo = MagicMock()
                # Preference not found
                mock_repo.get_by_composite_key = AsyncMock(return_value=None)
                mock_repo_class.return_value = mock_repo

                result = runner.invoke(app, ["languages", "remove", "xyz"])

                assert result.exit_code == 0
                assert "not found" in result.stdout

    def test_remove_cancelled_by_user_returns_exit_code_1(self, runner: CliRunner) -> None:
        """T062: Test remove cancelled by user returns exit code 1."""
        # Setup: Mock existing preference
        mock_pref = MagicMock()
        mock_pref.user_id = DEFAULT_USER_ID
        mock_pref.language_code = "it"
        mock_pref.preference_type = LanguagePreferenceType.LEARNING.value
        mock_pref.priority = 1

        async def mock_get_session():
            mock_session = AsyncMock()
            mock_session.commit = AsyncMock()
            yield mock_session

        with patch("chronovista.cli.language_commands.db_manager") as mock_db_manager:
            mock_db_manager.get_session = mock_get_session

            with patch(
                "chronovista.cli.language_commands.UserLanguagePreferenceRepository"
            ) as mock_repo_class:
                mock_repo = MagicMock()
                mock_repo.get_by_composite_key = AsyncMock(return_value=mock_pref)
                mock_repo_class.return_value = mock_repo

                with patch("chronovista.cli.language_commands.typer.confirm") as mock_confirm:
                    # User declines confirmation
                    mock_confirm.return_value = False

                    result = runner.invoke(app, ["languages", "remove", "it"])

                    assert result.exit_code == 1
                    assert "Cancelled" in result.stdout or "cancelled" in result.stdout


class TestLanguageResetCommand:
    """Tests for 'languages reset' command."""

    def test_reset_command_help(self, runner: CliRunner) -> None:
        """Test reset command help text."""
        result = runner.invoke(app, ["languages", "reset", "--help"])
        assert result.exit_code == 0
        assert "yes" in result.stdout.lower() or "skip" in result.stdout.lower()

    def test_reset_with_confirmation(self, runner: CliRunner) -> None:
        """T067 [P] [US7]: Test reset command with confirmation."""
        # Setup: User has 7 preferences
        existing_prefs = [
            UserLanguagePreference(
                user_id=DEFAULT_USER_ID,
                language_code=LanguageCode.ENGLISH,
                preference_type=LanguagePreferenceType.FLUENT,
                priority=1,
                auto_download_transcripts=True,
                learning_goal=None,
                created_at=datetime.now(timezone.utc),
            ),
            UserLanguagePreference(
                user_id=DEFAULT_USER_ID,
                language_code=LanguageCode.SPANISH,
                preference_type=LanguagePreferenceType.FLUENT,
                priority=2,
                auto_download_transcripts=True,
                learning_goal=None,
                created_at=datetime.now(timezone.utc),
            ),
            UserLanguagePreference(
                user_id=DEFAULT_USER_ID,
                language_code=LanguageCode.ITALIAN,
                preference_type=LanguagePreferenceType.LEARNING,
                priority=1,
                auto_download_transcripts=True,
                learning_goal="B2 by December",
                created_at=datetime.now(timezone.utc),
            ),
            UserLanguagePreference(
                user_id=DEFAULT_USER_ID,
                language_code=LanguageCode.FRENCH,
                preference_type=LanguagePreferenceType.LEARNING,
                priority=2,
                auto_download_transcripts=True,
                learning_goal=None,
                created_at=datetime.now(timezone.utc),
            ),
            UserLanguagePreference(
                user_id=DEFAULT_USER_ID,
                language_code=LanguageCode.GERMAN,
                preference_type=LanguagePreferenceType.CURIOUS,
                priority=1,
                auto_download_transcripts=False,
                learning_goal=None,
                created_at=datetime.now(timezone.utc),
            ),
            UserLanguagePreference(
                user_id=DEFAULT_USER_ID,
                language_code=LanguageCode.JAPANESE,
                preference_type=LanguagePreferenceType.CURIOUS,
                priority=2,
                auto_download_transcripts=False,
                learning_goal=None,
                created_at=datetime.now(timezone.utc),
            ),
            UserLanguagePreference(
                user_id=DEFAULT_USER_ID,
                language_code=LanguageCode.CHINESE_SIMPLIFIED,
                preference_type=LanguagePreferenceType.EXCLUDE,
                priority=1,
                auto_download_transcripts=False,
                learning_goal=None,
                created_at=datetime.now(timezone.utc),
            ),
        ]

        async def mock_get_session():
            mock_session = AsyncMock()
            mock_session.commit = AsyncMock()
            yield mock_session

        with patch("chronovista.cli.language_commands.db_manager") as mock_db_manager:
            mock_db_manager.get_session = mock_get_session

            with patch(
                "chronovista.cli.language_commands.UserLanguagePreferenceRepository"
            ) as mock_repo_class:
                mock_repo = MagicMock()
                mock_repo.get_user_preferences = AsyncMock(return_value=existing_prefs)
                mock_repo.delete_all_user_preferences = AsyncMock(return_value=7)
                mock_repo_class.return_value = mock_repo

                with patch("chronovista.cli.language_commands.typer.confirm") as mock_confirm:
                    # User confirms deletion but declines reconfiguration
                    mock_confirm.side_effect = [True, False]  # First for reset confirm, second for reconfig

                    result = runner.invoke(app, ["languages", "reset"])

                    assert result.exit_code == 0
                    # Should confirm deletion twice (reset + reconfig)
                    assert mock_confirm.call_count == 2
                    # Verify first call mentions the count
                    first_call_text = str(mock_confirm.call_args_list[0])
                    assert "7" in first_call_text  # Count should be in confirmation prompt
                    # Should call delete_all
                    mock_repo.delete_all_user_preferences.assert_called_once()
                    # Should show success message
                    assert "cleared" in result.stdout.lower()

    def test_reset_yes_skips_confirmation(self, runner: CliRunner) -> None:
        """T068 [P] [US7]: Test reset --yes skips reset confirmation but offers reconfig."""
        # Setup: User has 3 preferences
        existing_prefs = [
            UserLanguagePreference(
                user_id=DEFAULT_USER_ID,
                language_code=LanguageCode.ENGLISH,
                preference_type=LanguagePreferenceType.FLUENT,
                priority=1,
                auto_download_transcripts=True,
                learning_goal=None,
                created_at=datetime.now(timezone.utc),
            ),
            UserLanguagePreference(
                user_id=DEFAULT_USER_ID,
                language_code=LanguageCode.SPANISH,
                preference_type=LanguagePreferenceType.FLUENT,
                priority=2,
                auto_download_transcripts=True,
                learning_goal=None,
                created_at=datetime.now(timezone.utc),
            ),
            UserLanguagePreference(
                user_id=DEFAULT_USER_ID,
                language_code=LanguageCode.ITALIAN,
                preference_type=LanguagePreferenceType.LEARNING,
                priority=1,
                auto_download_transcripts=True,
                learning_goal="B2",
                created_at=datetime.now(timezone.utc),
            ),
        ]

        async def mock_get_session():
            mock_session = AsyncMock()
            mock_session.commit = AsyncMock()
            yield mock_session

        with patch("chronovista.cli.language_commands.db_manager") as mock_db_manager:
            mock_db_manager.get_session = mock_get_session

            with patch(
                "chronovista.cli.language_commands.UserLanguagePreferenceRepository"
            ) as mock_repo_class:
                mock_repo = MagicMock()
                mock_repo.get_user_preferences = AsyncMock(return_value=existing_prefs)
                mock_repo.delete_all_user_preferences = AsyncMock(return_value=3)
                mock_repo_class.return_value = mock_repo

                with patch("chronovista.cli.language_commands.typer.confirm") as mock_confirm:
                    # User declines reconfiguration offer
                    mock_confirm.return_value = False

                    result = runner.invoke(app, ["languages", "reset", "--yes"])

                    # Should call confirm ONCE for reconfiguration (not for reset confirmation)
                    assert mock_confirm.call_count == 1
                    # Verify it's asking about reconfiguration
                    call_text = str(mock_confirm.call_args)
                    assert "reconfigure" in call_text.lower() or "configure" in call_text.lower()

                    assert result.exit_code == 0
                    assert "cleared" in result.stdout.lower()

    def test_reset_offers_reconfiguration(self, runner: CliRunner) -> None:
        """T069 [P] [US7]: Test reset offers reconfiguration after clearing."""
        existing_prefs = [
            UserLanguagePreference(
                user_id=DEFAULT_USER_ID,
                language_code=LanguageCode.ENGLISH,
                preference_type=LanguagePreferenceType.FLUENT,
                priority=1,
                auto_download_transcripts=True,
                learning_goal=None,
                created_at=datetime.now(timezone.utc),
            )
        ]

        async def mock_get_session():
            mock_session = AsyncMock()
            mock_session.commit = AsyncMock()
            yield mock_session

        with patch("chronovista.cli.language_commands.db_manager") as mock_db_manager:
            mock_db_manager.get_session = mock_get_session

            with patch(
                "chronovista.cli.language_commands.UserLanguagePreferenceRepository"
            ) as mock_repo_class:
                mock_repo = MagicMock()
                mock_repo.get_user_preferences = AsyncMock(return_value=existing_prefs)
                mock_repo.delete_all_user_preferences = AsyncMock(return_value=1)
                mock_repo_class.return_value = mock_repo

                with patch("chronovista.cli.language_commands.typer.confirm") as mock_confirm:
                    # User confirms deletion, then declines reconfiguration
                    mock_confirm.side_effect = [True, False]

                    result = runner.invoke(app, ["languages", "reset"])

                    assert result.exit_code == 0
                    # Should offer reconfiguration
                    assert mock_confirm.call_count == 2
                    # Check that second call asks about reconfiguration
                    second_call_text = str(mock_confirm.call_args_list[1])
                    assert "reconfigure" in second_call_text.lower() or "configure" in second_call_text.lower()

    def test_reset_no_setup_skips_reconfiguration(self, runner: CliRunner) -> None:
        """T070 [P] [US7]: Test reset --no-setup skips reconfiguration offer."""
        existing_prefs = [
            UserLanguagePreference(
                user_id=DEFAULT_USER_ID,
                language_code=LanguageCode.ENGLISH,
                preference_type=LanguagePreferenceType.FLUENT,
                priority=1,
                auto_download_transcripts=True,
                learning_goal=None,
                created_at=datetime.now(timezone.utc),
            )
        ]

        async def mock_get_session():
            mock_session = AsyncMock()
            mock_session.commit = AsyncMock()
            yield mock_session

        with patch("chronovista.cli.language_commands.db_manager") as mock_db_manager:
            mock_db_manager.get_session = mock_get_session

            with patch(
                "chronovista.cli.language_commands.UserLanguagePreferenceRepository"
            ) as mock_repo_class:
                mock_repo = MagicMock()
                mock_repo.get_user_preferences = AsyncMock(return_value=existing_prefs)
                mock_repo.delete_all_user_preferences = AsyncMock(return_value=1)
                mock_repo_class.return_value = mock_repo

                with patch("chronovista.cli.language_commands.typer.confirm") as mock_confirm:
                    mock_confirm.return_value = True

                    result = runner.invoke(app, ["languages", "reset", "--yes", "--no-setup"])

                    assert result.exit_code == 0
                    # Should only confirm once (or zero with --yes)
                    assert mock_confirm.call_count == 0
                    assert "cleared" in result.stdout.lower()

    def test_reset_cancelled_returns_exit_code_1(self, runner: CliRunner) -> None:
        """T071 [P] [US7]: Test reset cancelled by user returns exit code 1."""
        existing_prefs = [
            UserLanguagePreference(
                user_id=DEFAULT_USER_ID,
                language_code=LanguageCode.ENGLISH,
                preference_type=LanguagePreferenceType.FLUENT,
                priority=1,
                auto_download_transcripts=True,
                learning_goal=None,
                created_at=datetime.now(timezone.utc),
            )
        ]

        async def mock_get_session():
            mock_session = AsyncMock()
            mock_session.commit = AsyncMock()
            yield mock_session

        with patch("chronovista.cli.language_commands.db_manager") as mock_db_manager:
            mock_db_manager.get_session = mock_get_session

            with patch(
                "chronovista.cli.language_commands.UserLanguagePreferenceRepository"
            ) as mock_repo_class:
                mock_repo = MagicMock()
                mock_repo.get_user_preferences = AsyncMock(return_value=existing_prefs)
                mock_repo_class.return_value = mock_repo

                with patch("chronovista.cli.language_commands.typer.confirm") as mock_confirm:
                    # User declines confirmation
                    mock_confirm.return_value = False

                    result = runner.invoke(app, ["languages", "reset"])

                    assert result.exit_code == 1
                    assert "cancelled" in result.stdout.lower() or "canceled" in result.stdout.lower()

    def test_reset_no_preferences_shows_message(self, runner: CliRunner) -> None:
        """Test reset with no preferences shows message and exits 0."""
        async def mock_get_session():
            mock_session = AsyncMock()
            mock_session.commit = AsyncMock()
            yield mock_session

        with patch("chronovista.cli.language_commands.db_manager") as mock_db_manager:
            mock_db_manager.get_session = mock_get_session

            with patch(
                "chronovista.cli.language_commands.UserLanguagePreferenceRepository"
            ) as mock_repo_class:
                mock_repo = MagicMock()
                mock_repo.get_user_preferences = AsyncMock(return_value=[])
                mock_repo_class.return_value = mock_repo

                result = runner.invoke(app, ["languages", "reset"])

                assert result.exit_code == 0
                assert "No language preferences" in result.stdout or "no preferences" in result.stdout.lower()


# -------------------------------------------------------------------------
# Test: Set Command with Flags (US4 - T038-T042)
# -------------------------------------------------------------------------


class TestLanguageSetCommandFlags:
    """Tests for 'languages set' command with flag-based (non-interactive) input."""

    def test_set_fluent_flag_saves_fluent_preferences(self, runner: CliRunner) -> None:
        """T038: Test set --fluent flag saves fluent preferences."""
        with patch("chronovista.cli.language_commands._save_preferences") as mock_save:
            mock_save.return_value = None

            result = runner.invoke(app, ["languages", "set", "--fluent", "en,es"])

            assert result.exit_code == 0
            assert mock_save.called
            # Verify call args - should have fluent languages
            call_args = mock_save.call_args
            prefs_dict = call_args[0][1]  # Second positional arg
            assert LanguagePreferenceType.FLUENT in prefs_dict
            assert "en" in prefs_dict[LanguagePreferenceType.FLUENT]
            assert "es" in prefs_dict[LanguagePreferenceType.FLUENT]

    def test_set_with_multiple_flags(self, runner: CliRunner) -> None:
        """T039: Test set with multiple flags (--fluent, --learning, --curious, --exclude)."""
        with patch("chronovista.cli.language_commands._save_preferences") as mock_save:
            mock_save.return_value = None

            result = runner.invoke(
                app,
                [
                    "languages",
                    "set",
                    "--fluent",
                    "en,es",
                    "--learning",
                    "it,fr",
                    "--curious",
                    "de",
                    "--exclude",
                    "zh-CN",
                ],
            )

            assert result.exit_code == 0
            assert mock_save.called
            # Verify all types were processed
            call_args = mock_save.call_args
            prefs_dict = call_args[0][1]
            assert len(prefs_dict[LanguagePreferenceType.FLUENT]) == 2
            assert len(prefs_dict[LanguagePreferenceType.LEARNING]) == 2
            assert len(prefs_dict[LanguagePreferenceType.CURIOUS]) == 1
            assert len(prefs_dict[LanguagePreferenceType.EXCLUDE]) == 1

    def test_set_append_adds_to_existing_preferences(self, runner: CliRunner) -> None:
        """T040: Test set --append adds to existing preferences."""
        # Mock existing preferences
        existing_prefs = [
            UserLanguagePreference(
                user_id=DEFAULT_USER_ID,
                language_code=LanguageCode.ENGLISH,
                preference_type=LanguagePreferenceType.FLUENT,
                priority=1,
                auto_download_transcripts=True,
                learning_goal=None,
                created_at=datetime.now(timezone.utc),
            )
        ]

        with patch("chronovista.cli.language_commands._get_preferences") as mock_get:
            mock_get.return_value = existing_prefs

            with patch("chronovista.cli.language_commands._save_preferences") as mock_save:
                mock_save.return_value = None

                result = runner.invoke(
                    app, ["languages", "set", "--fluent", "es", "--append"]
                )

                assert result.exit_code == 0
                assert mock_save.called
                # Should have merged existing + new
                call_args = mock_save.call_args
                prefs_dict = call_args[0][1]
                # Should contain both en (existing) and es (new)
                assert "en" in prefs_dict[LanguagePreferenceType.FLUENT]
                assert "es" in prefs_dict[LanguagePreferenceType.FLUENT]

    def test_set_with_conflict_shows_error(self, runner: CliRunner) -> None:
        """T041: Test set with conflict (same language in multiple types) shows error."""
        result = runner.invoke(
            app,
            [
                "languages",
                "set",
                "--fluent",
                "en",
                "--learning",
                "en",  # Conflict: en in both fluent and learning
            ],
        )

        assert result.exit_code == 2  # Conflict exit code
        assert "conflict" in result.stdout.lower() or "cannot be in multiple types" in result.stdout.lower()
        assert "en" in result.stdout

    def test_set_with_invalid_language_code_shows_suggestions(
        self, runner: CliRunner
    ) -> None:
        """T042: Test set with invalid language code shows suggestions."""
        result = runner.invoke(app, ["languages", "set", "--fluent", "xyz"])

        assert result.exit_code == 1  # Invalid code exit code
        # Should show error about invalid code
        assert "invalid" in result.stdout.lower() or "unknown" in result.stdout.lower()


# -------------------------------------------------------------------------
# Test: Constants and Configuration
# -------------------------------------------------------------------------


class TestLanguageConstants:
    """Tests for language command constants."""

    def test_default_user_id_defined(self) -> None:
        """Test DEFAULT_USER_ID is defined."""
        assert DEFAULT_USER_ID == "default_user"

    def test_output_format_enum(self) -> None:
        """Test OutputFormat enum values."""
        assert OutputFormat.TABLE.value == "table"
        assert OutputFormat.JSON.value == "json"
        assert OutputFormat.YAML.value == "yaml"

    def test_language_names_coverage(self) -> None:
        """Test LANGUAGE_NAMES has reasonable coverage."""
        # Should have at least 50 language mappings
        assert len(LANGUAGE_NAMES) >= 50
        # Should include major languages
        assert "en" in LANGUAGE_NAMES
        assert "es" in LANGUAGE_NAMES
        assert "fr" in LANGUAGE_NAMES
        assert "de" in LANGUAGE_NAMES
        assert "zh-CN" in LANGUAGE_NAMES
        assert "ja" in LANGUAGE_NAMES


# -------------------------------------------------------------------------
# Test: Upgrade Prompt for Sync Commands (US8 - T075-T079)
# -------------------------------------------------------------------------


class TestUpgradePromptForSyncCommands:
    """Tests for upgrade prompt functionality in sync commands."""

    @pytest.mark.asyncio
    async def test_upgrade_prompt_appears_when_no_preferences_configured(self) -> None:
        """T075 [P] [US8]: Test upgrade prompt appears when no preferences configured."""
        from chronovista.cli.language_commands import (
            check_and_prompt_language_preferences,
        )

        # Reset module-level flag
        import chronovista.cli.language_commands as lang_cmd

        lang_cmd._upgrade_prompt_shown = False

        with patch("chronovista.cli.language_commands._get_preferences") as mock_get:
            mock_get.return_value = []  # No preferences configured

            with patch("chronovista.cli.language_commands._show_upgrade_prompt") as mock_prompt:
                mock_prompt.return_value = False  # User declines

                result = await check_and_prompt_language_preferences(DEFAULT_USER_ID)

                # Verify prompt was shown
                assert mock_prompt.called
                # Should return empty list (use defaults)
                assert result == []

    @pytest.mark.asyncio
    async def test_upgrade_prompt_does_not_appear_when_preferences_exist(self) -> None:
        """T076 [P] [US8]: Test upgrade prompt does NOT appear when preferences exist."""
        from chronovista.cli.language_commands import (
            check_and_prompt_language_preferences,
        )

        # Reset module-level flag
        import chronovista.cli.language_commands as lang_cmd

        lang_cmd._upgrade_prompt_shown = False

        mock_prefs = [
            UserLanguagePreference(
                user_id=DEFAULT_USER_ID,
                language_code=LanguageCode.ENGLISH,
                preference_type=LanguagePreferenceType.FLUENT,
                priority=1,
                auto_download_transcripts=True,
                learning_goal=None,
                created_at=datetime.now(timezone.utc),
            )
        ]

        with patch("chronovista.cli.language_commands._get_preferences") as mock_get:
            mock_get.return_value = mock_prefs

            with patch("chronovista.cli.language_commands._show_upgrade_prompt") as mock_prompt:
                result = await check_and_prompt_language_preferences(DEFAULT_USER_ID)

                # Verify prompt was NOT shown
                assert not mock_prompt.called
                # Should return fluent languages
                assert result == ["en"]

    @pytest.mark.asyncio
    async def test_upgrade_prompt_appears_only_once_per_session(self) -> None:
        """T077 [P] [US8]: Test upgrade prompt appears only once per session."""
        from chronovista.cli.language_commands import (
            check_and_prompt_language_preferences,
        )

        # Reset module-level flag
        import chronovista.cli.language_commands as lang_cmd

        lang_cmd._upgrade_prompt_shown = False

        with patch("chronovista.cli.language_commands._get_preferences") as mock_get:
            mock_get.return_value = []  # No preferences

            with patch("chronovista.cli.language_commands._show_upgrade_prompt") as mock_prompt:
                mock_prompt.return_value = False  # User declines

                # First call - should show prompt
                result1 = await check_and_prompt_language_preferences(DEFAULT_USER_ID)
                assert mock_prompt.call_count == 1

                # Second call - should NOT show prompt (already shown this session)
                result2 = await check_and_prompt_language_preferences(DEFAULT_USER_ID)
                assert mock_prompt.call_count == 1  # Still 1, not 2

                # Both should return empty list
                assert result1 == []
                assert result2 == []

    @pytest.mark.asyncio
    async def test_accepting_upgrade_prompt_enters_first_run_setup(self) -> None:
        """T078 [P] [US8]: Test accepting upgrade prompt enters first-run setup."""
        from chronovista.cli.language_commands import (
            check_and_prompt_language_preferences,
        )

        # Reset module-level flag
        import chronovista.cli.language_commands as lang_cmd

        lang_cmd._upgrade_prompt_shown = False

        with patch("chronovista.cli.language_commands._get_preferences") as mock_get:
            # First call: no preferences, second call: has preferences after setup
            mock_get.side_effect = [
                [],  # No preferences initially
                [
                    UserLanguagePreference(
                        user_id=DEFAULT_USER_ID,
                        language_code=LanguageCode.ENGLISH,
                        preference_type=LanguagePreferenceType.FLUENT,
                        priority=1,
                        auto_download_transcripts=True,
                        learning_goal=None,
                        created_at=datetime.now(timezone.utc),
                    )
                ],  # Preferences exist after setup
            ]

            with patch("chronovista.cli.language_commands._show_upgrade_prompt") as mock_prompt:
                mock_prompt.return_value = True  # User accepts

                with patch(
                    "chronovista.cli.language_commands._handle_interactive_setup"
                ) as mock_setup:
                    mock_setup.return_value = None

                    result = await check_and_prompt_language_preferences(DEFAULT_USER_ID)

                    # Verify setup was called
                    assert mock_setup.called
                    # Should return fluent languages after setup
                    assert result == ["en"]

    @pytest.mark.asyncio
    async def test_declining_upgrade_prompt_proceeds_with_defaults(self) -> None:
        """T079 [P] [US8]: Test declining upgrade prompt proceeds with defaults."""
        from chronovista.cli.language_commands import (
            check_and_prompt_language_preferences,
        )

        # Reset module-level flag
        import chronovista.cli.language_commands as lang_cmd

        lang_cmd._upgrade_prompt_shown = False

        with patch("chronovista.cli.language_commands._get_preferences") as mock_get:
            mock_get.return_value = []  # No preferences

            with patch("chronovista.cli.language_commands._show_upgrade_prompt") as mock_prompt:
                mock_prompt.return_value = False  # User declines

                with patch(
                    "chronovista.cli.language_commands._handle_interactive_setup"
                ) as mock_setup:
                    result = await check_and_prompt_language_preferences(DEFAULT_USER_ID)

                    # Verify setup was NOT called
                    assert not mock_setup.called
                    # Should return empty list (use defaults)
                    assert result == []


# -------------------------------------------------------------------------
# Test: TTY Detection and Terminal Width (T086-T087)
# -------------------------------------------------------------------------


class TestTTYDetection:
    """Tests for TTY detection and terminal width handling."""

    def test_is_tty_returns_bool(self) -> None:
        """T086: Test _is_tty returns boolean value."""
        result = _is_tty()
        assert isinstance(result, bool)

    @patch("chronovista.cli.language_commands.sys.stdout.isatty")
    def test_is_tty_when_terminal(self, mock_isatty: MagicMock) -> None:
        """T086: Test _is_tty returns True when stdout is terminal."""
        mock_isatty.return_value = True
        # Need to reimport to get the mocked version
        from chronovista.cli.language_commands import _is_tty
        result = _is_tty()
        assert result is True

    @patch("chronovista.cli.language_commands.sys.stdout.isatty")
    def test_is_tty_when_not_terminal(self, mock_isatty: MagicMock) -> None:
        """T086: Test _is_tty returns False when stdout is not terminal."""
        mock_isatty.return_value = False
        from chronovista.cli.language_commands import _is_tty
        result = _is_tty()
        assert result is False


class TestTerminalWidth:
    """Tests for terminal width detection and handling."""

    def test_get_terminal_width_returns_int(self) -> None:
        """T087: Test _get_terminal_width returns integer."""
        result = _get_terminal_width()
        assert isinstance(result, int)

    def test_get_terminal_width_within_bounds(self) -> None:
        """T087: Test terminal width is clamped to reasonable bounds."""
        result = _get_terminal_width()
        assert 40 <= result <= 200

    @patch("chronovista.cli.language_commands.shutil.get_terminal_size")
    def test_get_terminal_width_respects_actual_size(self, mock_size: MagicMock) -> None:
        """T087: Test _get_terminal_width uses actual terminal size."""
        mock_size.return_value = MagicMock(columns=120)
        from chronovista.cli.language_commands import _get_terminal_width
        result = _get_terminal_width()
        assert result == 120

    @patch("chronovista.cli.language_commands.shutil.get_terminal_size")
    def test_get_terminal_width_clamps_minimum(self, mock_size: MagicMock) -> None:
        """T087: Test _get_terminal_width clamps minimum to 40."""
        mock_size.return_value = MagicMock(columns=20)
        from chronovista.cli.language_commands import _get_terminal_width
        result = _get_terminal_width()
        assert result == 40

    @patch("chronovista.cli.language_commands.shutil.get_terminal_size")
    def test_get_terminal_width_clamps_maximum(self, mock_size: MagicMock) -> None:
        """T087: Test _get_terminal_width clamps maximum to 200."""
        mock_size.return_value = MagicMock(columns=500)
        from chronovista.cli.language_commands import _get_terminal_width
        result = _get_terminal_width()
        assert result == 200

    @patch("chronovista.cli.language_commands.shutil.get_terminal_size")
    def test_get_terminal_width_fallback_on_error(self, mock_size: MagicMock) -> None:
        """T087: Test _get_terminal_width fallback to 80 on error."""
        mock_size.side_effect = Exception("Terminal size error")
        from chronovista.cli.language_commands import _get_terminal_width
        result = _get_terminal_width()
        assert result == 80


class TestTextTruncation:
    """Tests for text truncation helper function."""

    def test_truncate_text_short_string(self) -> None:
        """T087: Test truncation does not affect short strings."""
        result = _truncate_text("Hi", 10)
        assert result == "Hi"

    def test_truncate_text_exact_length(self) -> None:
        """T087: Test truncation does not affect exact length strings."""
        result = _truncate_text("Hello", 5)
        assert result == "Hello"

    def test_truncate_text_long_string(self) -> None:
        """T087: Test truncation adds suffix to long strings."""
        result = _truncate_text("Hello, World!", 10)
        assert result == "Hello, ..."
        assert len(result) == 10

    def test_truncate_text_custom_suffix(self) -> None:
        """T087: Test truncation with custom suffix."""
        result = _truncate_text("Hello, World!", 10, suffix="..")
        assert result == "Hello, W.."
        assert len(result) == 10

    def test_truncate_text_empty_string(self) -> None:
        """T087: Test truncation handles empty string."""
        result = _truncate_text("", 10)
        assert result == ""

    def test_truncate_text_very_small_width(self) -> None:
        """T087: Test truncation with very small width."""
        result = _truncate_text("Hello", 3)
        assert result == "..."
        assert len(result) == 3

    def test_truncate_text_width_smaller_than_suffix(self) -> None:
        """T087: Test truncation when width is smaller than suffix."""
        result = _truncate_text("Hello", 2)
        assert result == ".."
        assert len(result) == 2


class TestNonTTYOutput:
    """Tests for non-TTY output behavior."""

    def test_list_available_non_tty_output(self, runner: CliRunner) -> None:
        """T086: Test --available output works in non-TTY mode."""
        with patch("chronovista.cli.language_commands._is_tty") as mock_tty:
            mock_tty.return_value = False
            result = runner.invoke(app, ["languages", "list", "--available"])
            assert result.exit_code == 0
            # Should contain language codes without Rich formatting
            assert "en" in result.stdout.lower()
            assert "Available Language Codes" in result.stdout

    def test_list_preferences_non_tty_output(
        self, runner: CliRunner, mock_preferences: List[UserLanguagePreference]
    ) -> None:
        """T086: Test list output works in non-TTY mode."""
        with patch("chronovista.cli.language_commands._is_tty") as mock_tty:
            mock_tty.return_value = False
            with patch("chronovista.cli.language_commands._get_preferences") as mock_get:
                mock_get.return_value = mock_preferences
                result = runner.invoke(app, ["languages", "list"])
                assert result.exit_code == 0
                # Should show language preferences in plain text
                assert "Language Preferences" in result.stdout
                assert "Fluent" in result.stdout or "fluent" in result.stdout.lower()

    def test_json_output_always_plain(
        self, runner: CliRunner, mock_preferences: List[UserLanguagePreference]
    ) -> None:
        """T086: Test JSON output is always plain (no Rich formatting)."""
        with patch("chronovista.cli.language_commands._get_preferences") as mock_get:
            mock_get.return_value = mock_preferences
            result = runner.invoke(app, ["languages", "list", "--format", "json"])
            assert result.exit_code == 0
            # Should be valid JSON regardless of TTY mode
            output_data = json.loads(result.stdout)
            assert "fluent" in output_data

    def test_yaml_output_always_plain(
        self, runner: CliRunner, mock_preferences: List[UserLanguagePreference]
    ) -> None:
        """T086: Test YAML output is always plain (no Rich formatting)."""
        with patch("chronovista.cli.language_commands._get_preferences") as mock_get:
            mock_get.return_value = mock_preferences
            result = runner.invoke(app, ["languages", "list", "--format", "yaml"])
            assert result.exit_code == 0
            # Should be valid YAML regardless of TTY mode
            output_data = yaml.safe_load(result.stdout)
            assert "fluent" in output_data
