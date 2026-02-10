"""
Language preference CLI commands.

This module provides a comprehensive CLI interface for managing user language
preferences in chronovista. It enables users to configure their language
settings for intelligent transcript management, including:

- **Fluent languages**: Languages the user reads well (auto-download enabled)
- **Learning languages**: Languages being studied (auto-download enabled, with goals)
- **Curious languages**: Languages of occasional interest (on-demand only)
- **Excluded languages**: Languages to never download

Commands
--------
list
    Display configured language preferences in table, JSON, or YAML format.
set
    Set language preferences interactively or via command-line flags.
add
    Add a single language preference with optional priority and goal.
remove
    Remove a language preference with confirmation.
reset
    Clear all language preferences with optional reconfiguration.

Examples
--------
List all configured preferences::

    $ chronovista languages list

Set preferences interactively::

    $ chronovista languages set

Set preferences via flags::

    $ chronovista languages set --fluent "en,es" --learning "it" --exclude "zh-CN"

Add a learning language with goal::

    $ chronovista languages add it --type learning --goal "B2 by December"

Notes
-----
This module integrates with the sync command framework to provide upgrade
prompts for users who haven't configured language preferences yet.

See Also
--------
chronovista.models.user_language_preference : Language preference data models
chronovista.repositories.user_language_preference_repository : Data access layer
"""

from __future__ import annotations

import asyncio
import json
import locale
import shutil
import sys
from enum import Enum
from typing import Any, Dict, List, Optional

import typer
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ..config.database import db_manager
from ..models.enums import LanguageCode, LanguagePreferenceType
from ..models.user_language_preference import (
    UserLanguagePreference,
    UserLanguagePreferenceCreate,
)
from ..repositories.user_language_preference_repository import (
    UserLanguagePreferenceRepository,
)
from ..utils.fuzzy import find_similar

# -------------------------------------------------------------------------
# Terminal Detection and Configuration (T086-T087)
# -------------------------------------------------------------------------


def _is_tty() -> bool:
    """
    Check if stdout is a terminal (TTY).

    Used to determine whether to use Rich formatting or plain text output.
    When output is piped to a file or another command, TTY detection returns
    False and the module switches to plain text mode.

    Returns
    -------
    bool
        True if stdout is a terminal, False otherwise.

    Examples
    --------
    >>> _is_tty()  # In terminal
    True
    >>> _is_tty()  # When piped to file
    False
    """
    return sys.stdout.isatty()


def _get_terminal_width() -> int:
    """
    Get the current terminal width in columns.

    Falls back to 80 columns if terminal size cannot be determined
    (e.g., when running in non-TTY mode or on systems where terminal
    size detection is not available).

    Returns
    -------
    int
        Terminal width in columns (minimum 40, maximum 200).

    Examples
    --------
    >>> width = _get_terminal_width()
    >>> 40 <= width <= 200
    True
    """
    try:
        width = shutil.get_terminal_size().columns
        # Clamp to reasonable bounds
        return max(40, min(width, 200))
    except Exception:
        return 80  # Default fallback


def _truncate_text(text: str, max_width: int, suffix: str = "...") -> str:
    """
    Truncate text to fit within a maximum width.

    Ensures text does not exceed the specified width by truncating
    and adding a suffix if necessary.

    Parameters
    ----------
    text : str
        The text to truncate.
    max_width : int
        Maximum allowed width in characters.
    suffix : str, optional
        Suffix to append when truncating (default is "...").

    Returns
    -------
    str
        The truncated text with suffix if truncated, or original text.

    Examples
    --------
    >>> _truncate_text("Hello, World!", 10)
    'Hello, ...'
    >>> _truncate_text("Hi", 10)
    'Hi'
    """
    if not text or len(text) <= max_width:
        return text

    if max_width <= len(suffix):
        return suffix[:max_width]

    return text[: max_width - len(suffix)] + suffix


# Initialize CLI components
# Use force_terminal=False when not a TTY to disable Rich formatting
console = Console(force_terminal=_is_tty() if not _is_tty() else None)
language_app = typer.Typer(
    name="languages",
    help="Manage language preferences for transcript downloads",
    no_args_is_help=True,
)

# Constants
DEFAULT_USER_ID = "default_user"
DEFAULT_TERMINAL_WIDTH = 80
MIN_GOAL_COLUMN_WIDTH = 20

# -------------------------------------------------------------------------
# Module-Level Session State (T080 - US8)
# -------------------------------------------------------------------------

# Tracks whether upgrade prompt has been shown this session
_upgrade_prompt_shown: bool = False


class OutputFormat(str, Enum):
    """Output format options for list command."""

    TABLE = "table"
    JSON = "json"
    YAML = "yaml"


# -------------------------------------------------------------------------
# Language Display Name Mapping
# -------------------------------------------------------------------------

LANGUAGE_NAMES: dict[str, str] = {
    # Major English variants
    "en": "English",
    "en-US": "English (United States)",
    "en-GB": "English (United Kingdom)",
    "en-AU": "English (Australia)",
    "en-CA": "English (Canada)",
    # Spanish variants
    "es": "Spanish",
    "es-ES": "Spanish (Spain)",
    "es-MX": "Spanish (Mexico)",
    "es-AR": "Spanish (Argentina)",
    "es-CO": "Spanish (Colombia)",
    "es-419": "Spanish (Latin America)",
    # French variants
    "fr": "French",
    "fr-FR": "French (France)",
    "fr-CA": "French (Canada)",
    # German variants
    "de": "German",
    "de-DE": "German (Germany)",
    "de-AT": "German (Austria)",
    "de-CH": "German (Switzerland)",
    # Italian
    "it": "Italian",
    "it-IT": "Italian (Italy)",
    # Portuguese variants
    "pt": "Portuguese",
    "pt-PT": "Portuguese (Portugal)",
    "pt-BR": "Portuguese (Brazil)",
    # Chinese variants
    "zh-CN": "Chinese (Simplified)",
    "zh-TW": "Chinese (Traditional)",
    "zh-HK": "Chinese (Hong Kong)",
    # Japanese
    "ja": "Japanese",
    "ja-JP": "Japanese (Japan)",
    # Korean
    "ko": "Korean",
    "ko-KR": "Korean (Korea)",
    # Russian
    "ru": "Russian",
    "ru-RU": "Russian (Russia)",
    # Arabic
    "ar": "Arabic",
    "ar-SA": "Arabic (Saudi Arabia)",
    "ar-EG": "Arabic (Egypt)",
    # Hindi
    "hi": "Hindi",
    "hi-IN": "Hindi (India)",
    # Other major languages
    "nl": "Dutch",
    "nl-NL": "Dutch (Netherlands)",
    "sv": "Swedish",
    "no": "Norwegian",
    "da": "Danish",
    "fi": "Finnish",
    "pl": "Polish",
    "cs": "Czech",
    "hu": "Hungarian",
    "ro": "Romanian",
    "el": "Greek",
    "he": "Hebrew",
    "tr": "Turkish",
    "uk": "Ukrainian",
    "th": "Thai",
    "vi": "Vietnamese",
    "id": "Indonesian",
    "ms": "Malay",
    "tl": "Tagalog",
    # Indian languages
    "bn": "Bengali",
    "gu": "Gujarati",
    "kn": "Kannada",
    "ml": "Malayalam",
    "mr": "Marathi",
    "pa": "Punjabi",
    "ta": "Tamil",
    "te": "Telugu",
    "ur": "Urdu",
}


# -------------------------------------------------------------------------
# Helper Functions (T004-T008)
# -------------------------------------------------------------------------


def parse_language_input(input_str: str) -> List[str]:
    """
    Parse comma-separated language codes with whitespace handling.

    Parses a string of comma-separated language codes, normalizing them
    to lowercase and removing empty values.

    Parameters
    ----------
    input_str : str
        Comma-separated language codes (e.g., "en, es, fr").

    Returns
    -------
    List[str]
        List of normalized language codes.

    Examples
    --------
    >>> parse_language_input("en, es, fr")
    ['en', 'es', 'fr']
    >>> parse_language_input(" en , es ")
    ['en', 'es']
    >>> parse_language_input("en,,es")
    ['en', 'es']
    >>> parse_language_input("   ")
    []
    >>> parse_language_input("EN, ES")
    ['en', 'es']
    """
    if not input_str or not input_str.strip():
        return []

    codes = []
    for code in input_str.split(","):
        stripped = code.strip().lower()
        if stripped:
            codes.append(stripped)
    return codes


def validate_language_code(code: str) -> Optional[LanguageCode]:
    """
    Validate and convert a language code string to LanguageCode enum.

    Performs case-insensitive matching against the LanguageCode enum.

    Parameters
    ----------
    code : str
        Language code to validate (e.g., "en", "en-US").

    Returns
    -------
    Optional[LanguageCode]
        LanguageCode enum value if valid, None if invalid.

    Examples
    --------
    >>> validate_language_code("en")
    <LanguageCode.ENGLISH: 'en'>
    >>> validate_language_code("EN-US")
    <LanguageCode.ENGLISH_US: 'en-US'>
    >>> validate_language_code("xyz")
    None
    """
    if not code:
        return None

    normalized = code.strip().lower()

    # Try to match against all LanguageCode values
    for lang_code in LanguageCode:
        if lang_code.value.lower() == normalized:
            return lang_code

    return None


def detect_system_locale() -> LanguageCode:
    """
    Detect the system's default locale and return matching LanguageCode.

    Uses the system's locale settings to determine the preferred language.
    Falls back to English if detection fails or no match is found.

    Returns
    -------
    LanguageCode
        The detected LanguageCode, or ENGLISH as fallback.

    Examples
    --------
    >>> # On a system with locale set to "es_MX.UTF-8"
    >>> detect_system_locale()
    <LanguageCode.SPANISH: 'es'>
    """
    try:
        # Get the system locale using getlocale() which is the recommended approach
        # Note: We need to first call setlocale to get the current LC_ALL setting
        # getlocale() returns (language, encoding) tuple
        current_locale = locale.getlocale(locale.LC_ALL)
        system_locale = current_locale[0] if current_locale else None

        # If getlocale returns None, try environment variables
        if not system_locale:
            import os

            system_locale = (
                os.environ.get("LC_ALL")
                or os.environ.get("LC_MESSAGES")
                or os.environ.get("LANG")
            )

        if not system_locale:
            return LanguageCode.ENGLISH

        # Parse locale string (e.g., "es_MX" -> "es")
        # Handle formats: "en_US", "en_US.UTF-8", "en"
        base_locale = system_locale.split(".")[0]  # Remove encoding suffix

        # Try full locale match first (e.g., "en_US" -> "en-US")
        full_locale = base_locale.replace("_", "-")
        full_match = validate_language_code(full_locale)
        if full_match:
            return full_match

        # Try language-only match (e.g., "en_US" -> "en")
        language_only = base_locale.split("_")[0]
        language_match = validate_language_code(language_only)
        if language_match:
            return language_match

        return LanguageCode.ENGLISH

    except Exception:
        # Fallback to English on any error
        return LanguageCode.ENGLISH


def suggest_similar_codes(invalid_code: str, max_suggestions: int = 3) -> List[str]:
    """
    Find similar language codes using Levenshtein distance.

    Suggests language codes that are similar to the invalid input,
    using a distance threshold of 2.

    Parameters
    ----------
    invalid_code : str
        The invalid language code entered by the user.
    max_suggestions : int, optional
        Maximum number of suggestions to return (default is 3).

    Returns
    -------
    List[str]
        List of similar language code values, sorted by distance.

    Examples
    --------
    >>> suggest_similar_codes("en")
    ['en']
    >>> suggest_similar_codes("englis")
    []
    >>> suggest_similar_codes("es-us")  # Close to "es" or "en-US"
    ['en-US', 'es']
    """
    if not invalid_code:
        return []

    # Use find_similar from utils.fuzzy for Levenshtein-based matching
    candidates = [lang_code.value for lang_code in LanguageCode]
    return find_similar(
        invalid_code.strip(),
        candidates,
        max_distance=2,
        limit=max_suggestions,
        case_sensitive=False,
    )


def get_language_display_name(code: str) -> str:
    """
    Get human-readable name for a language code.

    Parameters
    ----------
    code : str
        Language code (e.g., "en", "en-US", "es-MX").

    Returns
    -------
    str
        Human-readable language name, or the code itself if unknown.

    Examples
    --------
    >>> get_language_display_name("en")
    'English'
    >>> get_language_display_name("es-MX")
    'Spanish (Mexico)'
    >>> get_language_display_name("unknown")
    'unknown'
    """
    if not code:
        return ""

    # Try exact match first
    if code in LANGUAGE_NAMES:
        return LANGUAGE_NAMES[code]

    # Try case-insensitive match
    normalized = code.lower()
    for key, value in LANGUAGE_NAMES.items():
        if key.lower() == normalized:
            return value

    # Return the code itself if no match found
    return code


# -------------------------------------------------------------------------
# Database Access Helper (T009)
# -------------------------------------------------------------------------


async def _get_preferences(user_id: str) -> List[UserLanguagePreference]:
    """
    Get user language preferences from the database.

    Retrieves all language preferences for the specified user,
    sorted by priority order.

    Parameters
    ----------
    user_id : str
        The user identifier.

    Returns
    -------
    List[UserLanguagePreference]
        List of user language preferences sorted by priority.

    Examples
    --------
    >>> prefs = await _get_preferences("default_user")
    >>> len(prefs)
    3
    """
    repo = UserLanguagePreferenceRepository()

    async for session in db_manager.get_session():
        db_prefs = await repo.get_user_preferences(session, user_id)
        return [UserLanguagePreference.model_validate(p) for p in db_prefs]

    return []


# -------------------------------------------------------------------------
# List Command Helper Functions (T017-T020)
# -------------------------------------------------------------------------


async def _list_preferences(
    user_id: str,
    preference_type: Optional[LanguagePreferenceType] = None,
) -> Dict[LanguagePreferenceType, List[UserLanguagePreference]]:
    """
    Fetch and group preferences by type.

    Retrieves all user preferences and groups them by preference type.
    Optionally filters by a specific preference type.

    Parameters
    ----------
    user_id : str
        The user identifier.
    preference_type : Optional[LanguagePreferenceType], optional
        Filter by specific preference type, by default None.

    Returns
    -------
    Dict[LanguagePreferenceType, List[UserLanguagePreference]]
        Dictionary of preferences grouped by type.

    Examples
    --------
    >>> grouped = await _list_preferences("default_user")
    >>> len(grouped[LanguagePreferenceType.FLUENT])
    2
    """
    prefs = await _get_preferences(user_id)

    # Filter by type if specified
    if preference_type:
        prefs = [p for p in prefs if p.preference_type == preference_type.value]

    # Initialize grouped dictionary
    grouped: Dict[LanguagePreferenceType, List[UserLanguagePreference]] = {
        LanguagePreferenceType.FLUENT: [],
        LanguagePreferenceType.LEARNING: [],
        LanguagePreferenceType.CURIOUS: [],
        LanguagePreferenceType.EXCLUDE: [],
    }

    # Group preferences by type
    for pref in prefs:
        ptype = LanguagePreferenceType(pref.preference_type)
        grouped[ptype].append(pref)

    return grouped


def _format_table_output(
    grouped: Dict[LanguagePreferenceType, List[UserLanguagePreference]]
) -> None:
    """
    Format preferences as grouped Rich table or plain text.

    Displays preferences grouped by type with appropriate columns
    for each preference type. Automatically detects TTY mode and
    uses plain text formatting when output is piped.

    Parameters
    ----------
    grouped : Dict[LanguagePreferenceType, List[UserLanguagePreference]]
        Preferences grouped by type.

    Notes
    -----
    - In TTY mode: Uses Rich panels and tables with colors
    - In non-TTY mode: Uses plain text output suitable for piping
    - Terminal width is respected for text truncation in Goal column

    Examples
    --------
    >>> _format_table_output(grouped_prefs)
    # Displays formatted table to console
    """
    is_tty = _is_tty()
    terminal_width = _get_terminal_width()

    # Calculate available width for goal column (after other columns)
    # Priority (8) + Language (~25) + Auto-Download (15) + padding (~12) = ~60
    goal_column_width = max(MIN_GOAL_COLUMN_WIDTH, terminal_width - 60)

    # Check if any preferences exist
    total_prefs = sum(len(prefs) for prefs in grouped.values())

    if is_tty:
        # Rich formatted output
        console.print(
            Panel(
                "Language Preferences",
                title_align="center",
                border_style="blue",
            )
        )
        console.print()
    else:
        # Plain text output
        print("=" * min(40, terminal_width))
        print("Language Preferences")
        print("=" * min(40, terminal_width))
        print()

    if total_prefs == 0:
        if is_tty:
            console.print("No language preferences configured.")
            console.print()
            console.print("To set up your preferences, run:")
            console.print("  chronovista languages set")
            console.print()
            console.print("Or initialize from your system locale:")
            console.print("  chronovista languages set --from-locale")
        else:
            print("No language preferences configured.")
            print()
            print("To set up your preferences, run:")
            print("  chronovista languages set")
            print()
            print("Or initialize from your system locale:")
            print("  chronovista languages set --from-locale")
        return

    # Display each preference type group
    for pref_type in LanguagePreferenceType:
        prefs = grouped[pref_type]
        if not prefs:
            continue

        # Section header
        if is_tty:
            console.print(f"[bold]{pref_type.value.title()} Languages[/bold]")
        else:
            print(f"{pref_type.value.title()} Languages")
            print("-" * len(f"{pref_type.value.title()} Languages"))

        # Create table based on preference type
        if pref_type == LanguagePreferenceType.LEARNING:
            if is_tty:
                table = Table(show_header=True, header_style="bold cyan")
                table.add_column("Priority", style="dim", width=8)
                table.add_column("Language", style="cyan")
                table.add_column("Auto-Download", justify="center")
                table.add_column("Goal", style="yellow", max_width=goal_column_width)

                for pref in prefs:
                    lang_code = pref.language_code if isinstance(pref.language_code, str) else pref.language_code.value
                    lang_display = f"{lang_code} ({get_language_display_name(lang_code)})"
                    auto_download = "Yes" if pref.auto_download_transcripts else "No"
                    goal = pref.learning_goal if pref.learning_goal else "-"
                    # Truncate goal for display
                    goal_display = _truncate_text(goal, goal_column_width)
                    table.add_row(
                        str(pref.priority),
                        lang_display,
                        auto_download,
                        goal_display,
                    )
                console.print(table)
            else:
                # Plain text output
                print(f"{'Priority':<10}{'Language':<30}{'Auto-Download':<15}{'Goal'}")
                for pref in prefs:
                    lang_code = pref.language_code if isinstance(pref.language_code, str) else pref.language_code.value
                    lang_display = f"{lang_code} ({get_language_display_name(lang_code)})"
                    auto_download = "Yes" if pref.auto_download_transcripts else "No"
                    goal = pref.learning_goal if pref.learning_goal else "-"
                    goal_display = _truncate_text(goal, goal_column_width)
                    print(f"{pref.priority:<10}{lang_display:<30}{auto_download:<15}{goal_display}")
        else:
            if is_tty:
                table = Table(show_header=True, header_style="bold cyan")
                table.add_column("Priority", style="dim", width=8)
                table.add_column("Language", style="cyan")
                table.add_column("Auto-Download", justify="center")

                for pref in prefs:
                    lang_code = pref.language_code if isinstance(pref.language_code, str) else pref.language_code.value
                    lang_display = f"{lang_code} ({get_language_display_name(lang_code)})"
                    auto_download = "Yes" if pref.auto_download_transcripts else "No"
                    table.add_row(
                        str(pref.priority),
                        lang_display,
                        auto_download,
                    )
                console.print(table)
            else:
                # Plain text output
                print(f"{'Priority':<10}{'Language':<30}{'Auto-Download'}")
                for pref in prefs:
                    lang_code = pref.language_code if isinstance(pref.language_code, str) else pref.language_code.value
                    lang_display = f"{lang_code} ({get_language_display_name(lang_code)})"
                    auto_download = "Yes" if pref.auto_download_transcripts else "No"
                    print(f"{pref.priority:<10}{lang_display:<30}{auto_download}")

        if is_tty:
            console.print()
        else:
            print()


def _format_json_output(
    grouped: Dict[LanguagePreferenceType, List[UserLanguagePreference]]
) -> None:
    """
    Format preferences as JSON.

    Outputs preferences in JSON format grouped by type. Uses plain print()
    to ensure output is suitable for piping and programmatic consumption.

    Parameters
    ----------
    grouped : Dict[LanguagePreferenceType, List[UserLanguagePreference]]
        Preferences grouped by type.

    Notes
    -----
    JSON output is always plain text (no Rich formatting) to ensure
    compatibility with tools like `jq` and programmatic parsing.

    Examples
    --------
    >>> _format_json_output(grouped_prefs)
    # Outputs JSON to stdout
    """
    output: Dict[str, List[Dict[str, Any]]] = {
        "fluent": [],
        "learning": [],
        "curious": [],
        "exclude": [],
    }

    for pref_type, prefs in grouped.items():
        type_key = pref_type.value
        for pref in prefs:
            # language_code is already a string due to use_enum_values=True
            lang_code = pref.language_code if isinstance(pref.language_code, str) else pref.language_code.value
            pref_dict: Dict[str, Any] = {
                "language_code": lang_code,
                "priority": pref.priority,
                "auto_download": pref.auto_download_transcripts,
            }
            if pref.learning_goal:
                pref_dict["goal"] = pref.learning_goal
            output[type_key].append(pref_dict)

    # Use print() for machine-readable output (no Rich formatting)
    print(json.dumps(output, indent=2))


def _format_yaml_output(
    grouped: Dict[LanguagePreferenceType, List[UserLanguagePreference]]
) -> None:
    """
    Format preferences as YAML.

    Outputs preferences in YAML format grouped by type. Uses plain print()
    to ensure output is suitable for piping and programmatic consumption.

    Parameters
    ----------
    grouped : Dict[LanguagePreferenceType, List[UserLanguagePreference]]
        Preferences grouped by type.

    Notes
    -----
    YAML output is always plain text (no Rich formatting) to ensure
    compatibility with YAML parsers and programmatic processing.

    Examples
    --------
    >>> _format_yaml_output(grouped_prefs)
    # Outputs YAML to stdout
    """
    output: Dict[str, List[Dict[str, Any]]] = {
        "fluent": [],
        "learning": [],
        "curious": [],
        "exclude": [],
    }

    for pref_type, prefs in grouped.items():
        type_key = pref_type.value
        for pref in prefs:
            # language_code is already a string due to use_enum_values=True
            lang_code = pref.language_code if isinstance(pref.language_code, str) else pref.language_code.value
            pref_dict: Dict[str, Any] = {
                "language_code": lang_code,
                "priority": pref.priority,
                "auto_download": pref.auto_download_transcripts,
            }
            if pref.learning_goal:
                pref_dict["goal"] = pref.learning_goal
            output[type_key].append(pref_dict)

    # Use print() for machine-readable output (no Rich formatting)
    print(yaml.dump(output, default_flow_style=False, sort_keys=False))


def _show_available_languages() -> None:
    """
    Display all available language codes.

    Shows all supported language codes from LanguageCode enum
    in a formatted table or plain text list depending on TTY mode.

    Notes
    -----
    - In TTY mode: Uses Rich table with colors
    - In non-TTY mode: Uses plain text format suitable for piping

    Examples
    --------
    >>> _show_available_languages()
    # Displays all language codes
    """
    is_tty = _is_tty()
    total_langs = len(LanguageCode)

    # Sort language codes alphabetically by their value
    sorted_codes = sorted(LanguageCode, key=lambda x: x.value)

    if is_tty:
        console.print(f"Available Language Codes ({total_langs} supported):")
        console.print()

        # Create table
        table = Table(show_header=True, header_style="bold cyan", show_lines=False)
        table.add_column("Code", style="cyan", width=12)
        table.add_column("Language", style="white")

        for lang_code in sorted_codes:
            display_name = get_language_display_name(lang_code.value)
            table.add_row(lang_code.value, display_name)

        console.print(table)
    else:
        # Plain text output
        print(f"Available Language Codes ({total_langs} supported):")
        print()
        print(f"{'Code':<12}{'Language'}")
        print("-" * 40)
        for lang_code in sorted_codes:
            display_name = get_language_display_name(lang_code.value)
            print(f"{lang_code.value:<12}{display_name}")


# -------------------------------------------------------------------------
# List Command (T021-T023)
# -------------------------------------------------------------------------


@language_app.command(name="list")
def list_preferences(
    format: OutputFormat = typer.Option(
        OutputFormat.TABLE, "--format", "-f", help="Output format (table, json, yaml)"
    ),
    preference_type: Optional[LanguagePreferenceType] = typer.Option(
        None, "--type", "-t", help="Filter by preference type"
    ),
    available: bool = typer.Option(
        False, "--available", help="Show all available language codes"
    ),
) -> None:
    """
    List configured language preferences.

    Displays user's language preferences grouped by type (fluent, learning,
    curious, exclude). Supports multiple output formats and filtering.

    Parameters
    ----------
    format : OutputFormat
        Output format (table, json, yaml), default is table.
    preference_type : Optional[LanguagePreferenceType]
        Filter by specific preference type.
    available : bool
        Show all available language codes instead of user preferences.

    Examples
    --------
    List all preferences in table format:
        $ chronovista languages list

    List preferences in JSON format:
        $ chronovista languages list --format json

    List only fluent languages:
        $ chronovista languages list --type fluent

    Show all available language codes:
        $ chronovista languages list --available
    """
    # Handle --available flag
    if available:
        _show_available_languages()
        return

    # Fetch and group preferences
    try:
        grouped = asyncio.run(_list_preferences(DEFAULT_USER_ID, preference_type))

        # Format output based on selected format
        if format == OutputFormat.TABLE:
            _format_table_output(grouped)
        elif format == OutputFormat.JSON:
            _format_json_output(grouped)
        elif format == OutputFormat.YAML:
            _format_yaml_output(grouped)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


# -------------------------------------------------------------------------
# Set Command Helper Functions (T031-T036, T043-T047)
# -------------------------------------------------------------------------


def _show_first_run_defaults(detected_locale: LanguageCode) -> tuple[bool, List[str]]:
    """
    Show first-run defaults with detected locale and English fallback.

    Displays detected locale and offers quick setup with confirmation.

    Parameters
    ----------
    detected_locale : LanguageCode
        The detected system locale.

    Returns
    -------
    tuple[bool, List[str]]
        Tuple of (accepted: bool, languages: List[str]).
        If accepted is True, languages contains the default codes.
        If accepted is False, user chose to customize.

    Examples
    --------
    >>> accepted, langs = _show_first_run_defaults(LanguageCode.SPANISH)
    >>> if accepted:
    ...     print(f"Using defaults: {langs}")
    """
    # Display setup header
    console.print(
        Panel(
            "Language Preferences Setup",
            title_align="center",
            border_style="blue",
        )
    )
    console.print()

    # Show detected locale
    detected_display = get_language_display_name(detected_locale.value)
    console.print(f"We detected your system language: {detected_display} ({detected_locale.value})")
    console.print()

    # Show defaults
    console.print("Quick setup - which languages can you read?")
    console.print(f"  [x] {detected_display} ({detected_locale.value}) - detected")

    # Add English if different from detected
    if detected_locale != LanguageCode.ENGLISH:
        console.print(f"  [x] English (en) - recommended fallback")
    console.print()

    # Prompt for confirmation
    response = typer.prompt(
        "Press Enter to continue with these defaults, or 'c' to customize",
        default="",
        show_default=False,
    )

    # Build default language list
    if detected_locale != LanguageCode.ENGLISH:
        default_langs = [detected_locale.value, LanguageCode.ENGLISH.value]
    else:
        default_langs = [LanguageCode.ENGLISH.value]

    # Check if user wants to customize
    if response.strip().lower() == "c":
        return (False, [])
    else:
        return (True, default_langs)


def _run_full_interactive_setup() -> Dict[LanguagePreferenceType, List[str]]:
    """
    Run full interactive setup prompting for all preference types.

    Prompts user for each preference type in order: fluent, learning,
    curious, exclude. Validates language codes and shows suggestions
    for invalid codes.

    Returns
    -------
    Dict[LanguagePreferenceType, List[str]]
        Dictionary mapping preference type to list of language codes.

    Examples
    --------
    >>> prefs = _run_full_interactive_setup()
    >>> print(prefs[LanguagePreferenceType.FLUENT])
    ['en', 'es']
    """
    result: Dict[LanguagePreferenceType, List[str]] = {
        LanguagePreferenceType.FLUENT: [],
        LanguagePreferenceType.LEARNING: [],
        LanguagePreferenceType.CURIOUS: [],
        LanguagePreferenceType.EXCLUDE: [],
    }

    console.print()
    console.print("[bold]Configure your language preferences:[/bold]")
    console.print()

    # Fluent languages
    fluent_input = typer.prompt(
        "Fluent languages (comma-separated, e.g., 'en, es')",
        default="",
    )
    fluent_codes = parse_language_input(fluent_input)
    for code in fluent_codes:
        validated = validate_language_code(code)
        if validated:
            result[LanguagePreferenceType.FLUENT].append(validated.value)
        else:
            console.print(f"[yellow]Warning: Unknown language code '{code}'[/yellow]")
            suggestions = suggest_similar_codes(code)
            if suggestions:
                console.print(f"  Did you mean: {', '.join(suggestions)}?")

    # Learning languages
    learning_input = typer.prompt(
        "Learning languages (optional, comma-separated)",
        default="",
    )
    learning_codes = parse_language_input(learning_input)
    for code in learning_codes:
        validated = validate_language_code(code)
        if validated:
            result[LanguagePreferenceType.LEARNING].append(validated.value)
        else:
            console.print(f"[yellow]Warning: Unknown language code '{code}'[/yellow]")
            suggestions = suggest_similar_codes(code)
            if suggestions:
                console.print(f"  Did you mean: {', '.join(suggestions)}?")

    # Curious languages
    curious_input = typer.prompt(
        "Curious languages (on-demand only, optional)",
        default="",
    )
    curious_codes = parse_language_input(curious_input)
    for code in curious_codes:
        validated = validate_language_code(code)
        if validated:
            result[LanguagePreferenceType.CURIOUS].append(validated.value)
        else:
            console.print(f"[yellow]Warning: Unknown language code '{code}'[/yellow]")
            suggestions = suggest_similar_codes(code)
            if suggestions:
                console.print(f"  Did you mean: {', '.join(suggestions)}?")

    # Excluded languages
    exclude_input = typer.prompt(
        "Excluded languages (never download, optional)",
        default="",
    )
    exclude_codes = parse_language_input(exclude_input)
    for code in exclude_codes:
        validated = validate_language_code(code)
        if validated:
            result[LanguagePreferenceType.EXCLUDE].append(validated.value)
        else:
            console.print(f"[yellow]Warning: Unknown language code '{code}'[/yellow]")
            suggestions = suggest_similar_codes(code)
            if suggestions:
                console.print(f"  Did you mean: {', '.join(suggestions)}?")

    return result


def _prompt_learning_goals(languages: List[str]) -> Dict[str, str]:
    """
    Prompt for learning goals for each learning language.

    For each language in the list, prompts user for an optional
    learning goal (e.g., "B2 by December").

    Parameters
    ----------
    languages : List[str]
        List of language codes to prompt for goals.

    Returns
    -------
    Dict[str, str]
        Dictionary mapping language_code to goal (empty string if no goal).

    Examples
    --------
    >>> goals = _prompt_learning_goals(["it", "fr"])
    >>> print(goals["it"])
    'B2 by December'
    """
    goals: Dict[str, str] = {}

    if not languages:
        return goals

    console.print()
    for lang_code in languages:
        display_name = get_language_display_name(lang_code)
        goal = typer.prompt(
            f"Enter learning goal for {display_name} ({lang_code}) [optional]",
            default="",
        )
        goals[lang_code] = goal.strip()

    return goals


def _show_confirmation_summary(
    grouped: Dict[LanguagePreferenceType, List[str]],
    goals: Optional[Dict[str, str]] = None,
) -> None:
    """
    Show confirmation summary with Rich Panel.

    Displays saved preferences grouped by type with auto-download
    status and learning goals.

    Parameters
    ----------
    grouped : Dict[LanguagePreferenceType, List[str]]
        Dictionary of preference type to language codes.
    goals : Optional[Dict[str, str]], optional
        Dictionary of language_code to learning goal, by default None.

    Examples
    --------
    >>> _show_confirmation_summary(grouped_prefs, {"it": "B2 by December"})
    # Displays formatted panel
    """
    console.print()
    console.print(
        Panel(
            "Preferences Saved Successfully",
            title_align="center",
            border_style="green",
        )
    )
    console.print()

    goals_map = goals or {}

    # Fluent
    fluent_langs = grouped.get(LanguagePreferenceType.FLUENT, [])
    if fluent_langs:
        langs_str = ", ".join(fluent_langs)
        console.print(f"Fluent:   {langs_str} (auto-download enabled)")

    # Learning
    learning_langs = grouped.get(LanguagePreferenceType.LEARNING, [])
    if learning_langs:
        learning_parts = []
        for lang in learning_langs:
            if lang in goals_map and goals_map[lang]:
                learning_parts.append(f"{lang} ({goals_map[lang]})")
            else:
                learning_parts.append(lang)
        langs_str = ", ".join(learning_parts)
        console.print(f"Learning: {langs_str} (auto-download enabled)")

    # Curious
    curious_langs = grouped.get(LanguagePreferenceType.CURIOUS, [])
    if curious_langs:
        langs_str = ", ".join(curious_langs)
        console.print(f"Curious:  {langs_str} (on-demand only)")

    # Excluded
    exclude_langs = grouped.get(LanguagePreferenceType.EXCLUDE, [])
    if exclude_langs:
        langs_str = ", ".join(exclude_langs)
        console.print(f"Excluded: {langs_str} (never download)")

    console.print()
    console.print("Tip: Use 'chronovista languages list' to review")


async def _save_preferences(
    user_id: str,
    prefs_dict: Dict[LanguagePreferenceType, List[str]],
    goals_dict: Optional[Dict[str, str]] = None,
) -> None:
    """
    Save language preferences atomically.

    Builds UserLanguagePreferenceCreate objects and saves them
    using the repository's atomic save operation.

    Parameters
    ----------
    user_id : str
        The user identifier.
    prefs_dict : Dict[LanguagePreferenceType, List[str]]
        Dictionary of preference type to language codes.
    goals_dict : Optional[Dict[str, str]], optional
        Dictionary of language_code to learning goal, by default None.

    Examples
    --------
    >>> await _save_preferences("default_user", grouped_prefs, {"it": "B2"})
    """
    goals_map = goals_dict or {}
    preferences_to_save: List[UserLanguagePreferenceCreate] = []

    # Build preference objects with priorities
    for pref_type, lang_codes in prefs_dict.items():
        # Determine auto_download based on type
        auto_download = pref_type in (
            LanguagePreferenceType.FLUENT,
            LanguagePreferenceType.LEARNING,
        )

        for priority, lang_code in enumerate(lang_codes, start=1):
            # Validate language code
            validated_code = validate_language_code(lang_code)
            if not validated_code:
                continue

            # Get learning goal if applicable
            learning_goal = None
            if pref_type == LanguagePreferenceType.LEARNING:
                learning_goal = goals_map.get(lang_code, None)
                # Convert empty string to None
                if learning_goal == "":
                    learning_goal = None

            # Create preference object
            pref = UserLanguagePreferenceCreate(
                user_id=user_id,
                language_code=validated_code,
                preference_type=pref_type,
                priority=priority,
                auto_download_transcripts=auto_download,
                learning_goal=learning_goal,
            )
            preferences_to_save.append(pref)

    # Save all preferences atomically
    repo = UserLanguagePreferenceRepository()
    async for session in db_manager.get_session():
        await repo.save_preferences(session, user_id, preferences_to_save)
        await session.commit()


# -------------------------------------------------------------------------
# Upgrade Prompt Functions (T081-T082 - US8)
# -------------------------------------------------------------------------


def _show_upgrade_prompt() -> bool:
    """
    Show upgrade prompt and return True if user wants to configure (T082 - US8).

    Displays a [Y/n] format prompt asking if user wants to configure language
    preferences. Default is "Y" (yes).

    Returns
    -------
    bool
        True if user wants to configure, False otherwise.

    Examples
    --------
    >>> if _show_upgrade_prompt():
    ...     # User wants to configure
    ...     pass
    """
    console.print()
    console.print(
        Panel(
            "[blue]chronovista now supports intelligent transcript management.[/blue]\n\n"
            "Would you like to configure your language preferences now?",
            title="Language Preferences Not Configured",
            border_style="yellow",
        )
    )
    console.print()

    # Use [Y/n] format (Y is default)
    return typer.confirm("Configure languages now?", default=True)


def _handle_interactive_setup() -> None:
    """
    Run interactive language preference setup.

    This is a wrapper around the existing interactive setup logic used
    in the 'set' command. It runs the full interactive flow.

    Examples
    --------
    >>> _handle_interactive_setup()
    # Runs full interactive setup
    """
    # Detect system locale
    detected = detect_system_locale()

    # Show first-run defaults
    accepted, default_langs = _show_first_run_defaults(detected)

    if accepted:
        # User accepted defaults
        interactive_prefs_dict: Dict[LanguagePreferenceType, List[str]] = {
            LanguagePreferenceType.FLUENT: default_langs,
            LanguagePreferenceType.LEARNING: [],
            LanguagePreferenceType.CURIOUS: [],
            LanguagePreferenceType.EXCLUDE: [],
        }
        interactive_goals_dict: Dict[str, str] = {}
    else:
        # User chose to customize - run full interactive setup
        interactive_prefs_dict = _run_full_interactive_setup()

        # Prompt for learning goals if any learning languages
        learning_langs = interactive_prefs_dict.get(LanguagePreferenceType.LEARNING, [])
        interactive_goals_dict = _prompt_learning_goals(learning_langs)

    # Save preferences synchronously using asyncio.run
    asyncio.run(_save_preferences(DEFAULT_USER_ID, interactive_prefs_dict, interactive_goals_dict))

    # Show confirmation
    _show_confirmation_summary(interactive_prefs_dict, interactive_goals_dict)


async def check_and_prompt_language_preferences(user_id: str) -> List[str]:
    """
    Check for preferences and show upgrade prompt if needed (T081 - US8).

    This function is called from sync commands before sync operations.
    It checks if the user has language preferences configured:
    - If preferences exist: return fluent languages
    - If no preferences AND not yet prompted this session:
      - Show upgrade prompt
      - If user accepts: run interactive setup
      - If user declines: return empty list (use defaults)
    - If already prompted this session: return empty list (use defaults)

    Parameters
    ----------
    user_id : str
        The user identifier.

    Returns
    -------
    List[str]
        List of language codes to use for sync (empty list = use defaults).

    Examples
    --------
    >>> languages = await check_and_prompt_language_preferences("default_user")
    >>> if not languages:
    ...     # Use system locale or English fallback
    ...     languages = [detect_system_locale().value]
    """
    global _upgrade_prompt_shown

    # Get current preferences
    prefs = await _get_preferences(user_id)

    if prefs:
        # Has preferences - return fluent languages
        return [
            p.language_code if isinstance(p.language_code, str) else p.language_code.value
            for p in prefs
            if p.preference_type == LanguagePreferenceType.FLUENT.value
        ]

    # No preferences exist
    if _upgrade_prompt_shown:
        # Already prompted this session - use defaults
        return []

    # Mark as prompted
    _upgrade_prompt_shown = True

    # Show prompt and handle response
    if _show_upgrade_prompt():
        # User wants to configure - run setup
        _handle_interactive_setup()

        # Re-fetch preferences after setup
        prefs = await _get_preferences(user_id)
        return [
            p.language_code if isinstance(p.language_code, str) else p.language_code.value
            for p in prefs
            if p.preference_type == LanguagePreferenceType.FLUENT.value
        ]
    else:
        # User declined - use defaults
        console.print()
        detected = detect_system_locale()
        detected_display = get_language_display_name(detected.value)
        console.print(f"[yellow]Using default: {detected_display} ({detected.value}) based on system locale[/yellow]")
        console.print("[dim]Tip: Configure later with 'chronovista languages set'[/dim]")
        console.print()
        return []


def _validate_no_conflicts(
    prefs_dict: Dict[LanguagePreferenceType, List[str]]
) -> Optional[tuple[str, str, str]]:
    """
    Validate that no language appears in multiple preference types.

    Parameters
    ----------
    prefs_dict : Dict[LanguagePreferenceType, List[str]]
        Dictionary of preference type to language codes.

    Returns
    -------
    Optional[tuple[str, str, str]]
        If conflict found: (language_code, type1, type2).
        If no conflict: None.

    Examples
    --------
    >>> prefs = {
    ...     LanguagePreferenceType.FLUENT: ["en"],
    ...     LanguagePreferenceType.LEARNING: ["en"],
    ... }
    >>> _validate_no_conflicts(prefs)
    ('en', 'fluent', 'learning')
    """
    # Build a map of language_code -> list of types it appears in
    lang_to_types: Dict[str, List[str]] = {}

    for pref_type, lang_codes in prefs_dict.items():
        for lang_code in lang_codes:
            if lang_code not in lang_to_types:
                lang_to_types[lang_code] = []
            lang_to_types[lang_code].append(pref_type.value)

    # Check for conflicts
    for lang_code, types in lang_to_types.items():
        if len(types) > 1:
            # Return first conflict found
            return (lang_code, types[0], types[1])

    return None


def _process_flag_input(
    flag_value: str, pref_type: LanguagePreferenceType
) -> tuple[List[str], List[str]]:
    """
    Process and validate comma-separated language codes from flag input.

    Parameters
    ----------
    flag_value : str
        Comma-separated language codes from command flag.
    pref_type : LanguagePreferenceType
        The preference type for context in error messages.

    Returns
    -------
    tuple[List[str], List[str]]
        Tuple of (valid_codes, invalid_codes).
        valid_codes: List of validated language codes.
        invalid_codes: List of codes that failed validation.

    Examples
    --------
    >>> _process_flag_input("en,es,xyz", LanguagePreferenceType.FLUENT)
    (['en', 'es'], ['xyz'])
    """
    # Parse input
    codes = parse_language_input(flag_value)

    valid_codes: List[str] = []
    invalid_codes: List[str] = []

    # Validate each code
    for code in codes:
        validated = validate_language_code(code)
        if validated:
            valid_codes.append(validated.value)
        else:
            invalid_codes.append(code)

    return (valid_codes, invalid_codes)


# -------------------------------------------------------------------------
# Set Command (T037)
# -------------------------------------------------------------------------


@language_app.command()
def set(
    fluent: Optional[str] = typer.Option(
        None, "--fluent", help="Comma-separated fluent language codes"
    ),
    learning: Optional[str] = typer.Option(
        None, "--learning", help="Comma-separated learning language codes"
    ),
    curious: Optional[str] = typer.Option(
        None, "--curious", help="Comma-separated curious language codes"
    ),
    exclude: Optional[str] = typer.Option(
        None, "--exclude", help="Comma-separated excluded language codes"
    ),
    from_locale: bool = typer.Option(
        False, "--from-locale", help="Initialize from system locale without prompts"
    ),
    append: bool = typer.Option(
        False, "--append", help="Add to existing preferences (don't replace)"
    ),
) -> None:
    """
    Set language preferences interactively or via flags.

    Interactive mode (no flags): Detects system locale, offers defaults,
    and allows customization.

    --from-locale mode: Automatically sets detected locale + English as
    fluent languages without prompts.

    Flag mode: Set specific preference types via command-line flags.

    Examples
    --------
    Interactive setup:
        $ chronovista languages set

    Quick setup from locale:
        $ chronovista languages set --from-locale

    Set via flags:
        $ chronovista languages set --fluent "en,es" --learning "it"
    """
    try:
        # Handle --from-locale mode
        if from_locale:
            detected = detect_system_locale()
            detected_display = get_language_display_name(detected.value)

            # Build default language list
            if detected != LanguageCode.ENGLISH:
                lang_codes = [detected.value, LanguageCode.ENGLISH.value]
            else:
                lang_codes = [LanguageCode.ENGLISH.value]

            # Build preferences dict
            prefs_dict: Dict[LanguagePreferenceType, List[str]] = {
                LanguagePreferenceType.FLUENT: lang_codes,
                LanguagePreferenceType.LEARNING: [],
                LanguagePreferenceType.CURIOUS: [],
                LanguagePreferenceType.EXCLUDE: [],
            }

            # Save preferences
            asyncio.run(_save_preferences(DEFAULT_USER_ID, prefs_dict))

            # Show confirmation
            _show_confirmation_summary(prefs_dict)

        # Handle flag-based mode (T043-T047)
        elif any([fluent, learning, curious, exclude]):
            # Process all flag inputs
            all_invalid_codes: List[str] = []
            flag_prefs_dict: Dict[LanguagePreferenceType, List[str]] = {
                LanguagePreferenceType.FLUENT: [],
                LanguagePreferenceType.LEARNING: [],
                LanguagePreferenceType.CURIOUS: [],
                LanguagePreferenceType.EXCLUDE: [],
            }

            # Process each flag if provided
            if fluent:
                valid, invalid = _process_flag_input(fluent, LanguagePreferenceType.FLUENT)
                flag_prefs_dict[LanguagePreferenceType.FLUENT] = valid
                all_invalid_codes.extend(invalid)

            if learning:
                valid, invalid = _process_flag_input(learning, LanguagePreferenceType.LEARNING)
                flag_prefs_dict[LanguagePreferenceType.LEARNING] = valid
                all_invalid_codes.extend(invalid)

            if curious:
                valid, invalid = _process_flag_input(curious, LanguagePreferenceType.CURIOUS)
                flag_prefs_dict[LanguagePreferenceType.CURIOUS] = valid
                all_invalid_codes.extend(invalid)

            if exclude:
                valid, invalid = _process_flag_input(exclude, LanguagePreferenceType.EXCLUDE)
                flag_prefs_dict[LanguagePreferenceType.EXCLUDE] = valid
                all_invalid_codes.extend(invalid)

            # Check for invalid codes (T042)
            if all_invalid_codes:
                console.print("[red]Error: Invalid language codes detected:[/red]")
                for code in all_invalid_codes:
                    console.print(f"  [red]- {code}[/red]")
                    suggestions = suggest_similar_codes(code)
                    if suggestions:
                        console.print(f"    Did you mean: {', '.join(suggestions)}?")
                console.print()
                console.print("Use 'chronovista languages list --available' to see all valid codes.")
                raise typer.Exit(1)

            # Check for conflicts (T041)
            conflict = _validate_no_conflicts(flag_prefs_dict)
            if conflict:
                lang_code, type1, type2 = conflict
                console.print(f"[red]Error: Language '{lang_code}' cannot be in multiple types.[/red]")
                console.print(f"Found in: --{type1} and --{type2}")
                console.print()
                console.print("Remove from one type and try again.")
                raise typer.Exit(2)

            # Handle --append mode (T040, T046)
            if append:
                # Get existing preferences
                existing_prefs = asyncio.run(_get_preferences(DEFAULT_USER_ID))

                # Build existing preferences dict
                existing_dict: Dict[LanguagePreferenceType, List[str]] = {
                    LanguagePreferenceType.FLUENT: [],
                    LanguagePreferenceType.LEARNING: [],
                    LanguagePreferenceType.CURIOUS: [],
                    LanguagePreferenceType.EXCLUDE: [],
                }

                for pref in existing_prefs:
                    ptype = LanguagePreferenceType(pref.preference_type)
                    # language_code is already a string due to use_enum_values=True
                    lang_code = pref.language_code if isinstance(pref.language_code, str) else pref.language_code.value
                    if lang_code not in existing_dict[ptype]:
                        existing_dict[ptype].append(lang_code)

                # Merge with new preferences (preserve order: existing first, then new)
                for pref_type in LanguagePreferenceType:
                    # Start with existing
                    merged = existing_dict[pref_type].copy()
                    # Add new codes that aren't already present
                    for new_code in flag_prefs_dict[pref_type]:
                        if new_code not in merged:
                            merged.append(new_code)
                    flag_prefs_dict[pref_type] = merged

            # Save preferences
            asyncio.run(_save_preferences(DEFAULT_USER_ID, flag_prefs_dict))

            # Show confirmation
            _show_confirmation_summary(flag_prefs_dict)

        # Handle interactive mode
        else:
            # Detect system locale
            detected = detect_system_locale()

            # Show first-run defaults
            accepted, default_langs = _show_first_run_defaults(detected)

            if accepted:
                # User accepted defaults
                interactive_prefs_dict: Dict[LanguagePreferenceType, List[str]] = {
                    LanguagePreferenceType.FLUENT: default_langs,
                    LanguagePreferenceType.LEARNING: [],
                    LanguagePreferenceType.CURIOUS: [],
                    LanguagePreferenceType.EXCLUDE: [],
                }
                interactive_goals_dict: Dict[str, str] = {}
            else:
                # User chose to customize - run full interactive setup
                interactive_prefs_dict = _run_full_interactive_setup()

                # Prompt for learning goals if any learning languages
                learning_langs = interactive_prefs_dict.get(LanguagePreferenceType.LEARNING, [])
                interactive_goals_dict = _prompt_learning_goals(learning_langs)

            # Save preferences
            asyncio.run(_save_preferences(DEFAULT_USER_ID, interactive_prefs_dict, interactive_goals_dict))

            # Show confirmation
            _show_confirmation_summary(interactive_prefs_dict, interactive_goals_dict)

    except KeyboardInterrupt:
        console.print("\n[yellow]Setup cancelled. No changes saved.[/yellow]")
        raise typer.Exit(130)


# -------------------------------------------------------------------------
# Add Command Helper Functions (T053-T055)
# -------------------------------------------------------------------------


async def _check_language_exists(
    user_id: str, language_code: str
) -> Optional[LanguagePreferenceType]:
    """
    Check if language preference already exists for user.

    Parameters
    ----------
    user_id : str
        The user identifier.
    language_code : str
        BCP-47 language code to check.

    Returns
    -------
    Optional[LanguagePreferenceType]
        Existing preference type if found, None otherwise.

    Examples
    --------
    >>> existing_type = await _check_language_exists("user1", "en")
    >>> if existing_type:
    ...     print(f"Already configured as {existing_type}")
    """
    prefs = await _get_preferences(user_id)

    for pref in prefs:
        # language_code is already a string due to use_enum_values=True
        pref_code = (
            pref.language_code
            if isinstance(pref.language_code, str)
            else pref.language_code.value
        )
        if pref_code.lower() == language_code.lower():
            return LanguagePreferenceType(pref.preference_type)

    return None


def _calculate_priority(
    existing_prefs: List[UserLanguagePreference],
    pref_type: LanguagePreferenceType,
    requested_priority: Optional[int] = None,
) -> int:
    """
    Calculate priority for new language preference.

    If no priority specified, appends to end (max + 1).
    If priority specified, returns that value.

    Parameters
    ----------
    existing_prefs : List[UserLanguagePreference]
        Existing preferences of the same type.
    pref_type : LanguagePreferenceType
        Type of preference being added.
    requested_priority : Optional[int]
        Requested priority position, None to append.

    Returns
    -------
    int
        Calculated priority value.

    Examples
    --------
    >>> prefs = [pref1, pref2]  # priorities 1, 2
    >>> _calculate_priority(prefs, LanguagePreferenceType.FLUENT)
    3
    >>> _calculate_priority(prefs, LanguagePreferenceType.FLUENT, 1)
    1
    """
    if requested_priority is not None:
        return requested_priority

    # Filter to same type
    same_type = [p for p in existing_prefs if p.preference_type == pref_type.value]

    if not same_type:
        return 1

    # Find max priority and add 1
    max_priority = max(p.priority for p in same_type)
    return max_priority + 1


async def _shift_priorities(
    user_id: str, pref_type: LanguagePreferenceType, insert_at: int
) -> None:
    """
    Shift priorities for existing preferences when inserting at specific position.

    All preferences of the same type with priority >= insert_at are incremented by 1.

    Parameters
    ----------
    user_id : str
        The user identifier.
    pref_type : LanguagePreferenceType
        Type of preference to shift.
    insert_at : int
        Priority position where new preference will be inserted.

    Examples
    --------
    >>> # Shift fluent languages with priority >= 1 up by 1
    >>> await _shift_priorities("user1", LanguagePreferenceType.FLUENT, 1)
    """
    repo = UserLanguagePreferenceRepository()

    async for session in db_manager.get_session():
        # Get all preferences of this type
        prefs = await repo.get_preferences_by_type(session, user_id, pref_type)

        # Shift priorities >= insert_at
        for pref in prefs:
            if pref.priority >= insert_at:
                await repo.update_priority(
                    session, user_id, pref.language_code, pref.priority + 1
                )

        await session.commit()


# -------------------------------------------------------------------------
# Add Command (T056-T057)
# -------------------------------------------------------------------------


async def _add_language_preference(
    user_id: str,
    validated_code: LanguageCode,
    preference_type: LanguagePreferenceType,
    priority: Optional[int],
    learning_goal: Optional[str],
) -> tuple[int, bool]:
    """
    Add a language preference with proper priority handling.

    This consolidated async function handles all database operations in a single
    event loop to avoid asyncio loop conflicts when shifting priorities.

    Parameters
    ----------
    user_id : str
        The user identifier.
    validated_code : LanguageCode
        Validated language code enum.
    preference_type : LanguagePreferenceType
        Type of preference to add.
    priority : Optional[int]
        Requested priority position, None to append.
    learning_goal : Optional[str]
        Learning goal for learning type preferences.

    Returns
    -------
    tuple[int, bool]
        Tuple of (calculated_priority, auto_download).
    """
    repo = UserLanguagePreferenceRepository()

    async for session in db_manager.get_session():
        # Get existing preferences
        all_prefs = await repo.get_user_preferences(session, user_id)

        # Calculate priority
        same_type = [p for p in all_prefs if p.preference_type == preference_type.value]
        if priority is not None:
            calculated_priority = priority
        elif not same_type:
            calculated_priority = 1
        else:
            calculated_priority = max(p.priority for p in same_type) + 1

        # Shift existing priorities if inserting at specific position
        if priority is not None:
            prefs_of_type = await repo.get_preferences_by_type(
                session, user_id, preference_type
            )
            for pref in prefs_of_type:
                if pref.priority >= priority:
                    await repo.update_priority(
                        session, user_id, pref.language_code, pref.priority + 1
                    )

        # Determine auto-download based on type
        auto_download = preference_type in (
            LanguagePreferenceType.FLUENT,
            LanguagePreferenceType.LEARNING,
        )

        # Create the new preference
        new_pref = UserLanguagePreferenceCreate(
            user_id=user_id,
            language_code=validated_code,
            preference_type=preference_type,
            priority=calculated_priority,
            auto_download_transcripts=auto_download,
            learning_goal=learning_goal,
        )

        # Save the new preference
        await repo.save_preferences(session, user_id, [new_pref])
        await session.commit()

        return (calculated_priority, auto_download)

    # Fallback return (should not reach here)
    return (1, False)


@language_app.command()
def add(
    language: str = typer.Argument(..., help="BCP-47 language code"),
    preference_type: LanguagePreferenceType = typer.Option(
        ..., "--type", "-t", help="Preference type (fluent, learning, curious, exclude)"
    ),
    priority: Optional[int] = typer.Option(
        None, "--priority", "-p", help="Priority position (1 = highest)"
    ),
    goal: Optional[str] = typer.Option(
        None, "--goal", "-g", help="Learning goal (for learning type only)"
    ),
) -> None:
    """
    Add a single language preference.

    Adds a new language to your preferences with the specified type.
    By default, new languages are added at the end of the priority list.
    Use --priority to insert at a specific position.

    Examples
    --------
    Add Italian as a learning language:
        $ chronovista languages add it --type learning --goal "B2 by December"

    Add German as curious at highest priority:
        $ chronovista languages add de --type curious --priority 1

    Add Spanish as fluent (appended to end):
        $ chronovista languages add es --type fluent
    """
    try:
        # 1. Validate language code
        validated_code = validate_language_code(language)
        if not validated_code:
            console.print(f"[red]Error: Unknown language code '{language}'[/red]")
            console.print()
            suggestions = suggest_similar_codes(language)
            if suggestions:
                console.print("Did you mean one of these?")
                for suggestion in suggestions:
                    display_name = get_language_display_name(suggestion)
                    console.print(f"  - {suggestion} ({display_name})")
            console.print()
            console.print("See all codes: chronovista languages list --available")
            raise typer.Exit(1)

        # 2. Check if language already exists
        existing_type = asyncio.run(
            _check_language_exists(DEFAULT_USER_ID, validated_code.value)
        )
        if existing_type:
            display_name = get_language_display_name(validated_code.value)
            console.print(
                f"[red]Error: '{validated_code.value}' ({display_name}) is already configured as {existing_type.value.upper()}.[/red]"
            )
            console.print()
            console.print("To change its type:")
            console.print(f"  chronovista languages remove {validated_code.value}")
            console.print(
                f"  chronovista languages add {validated_code.value} --type {preference_type.value}"
            )
            raise typer.Exit(2)

        # 3. Validate goal is only for learning type
        learning_goal = None
        if goal:
            if preference_type == LanguagePreferenceType.LEARNING:
                learning_goal = goal.strip() if goal.strip() else None
            else:
                console.print(
                    "[yellow]Warning: --goal is only applicable for learning type. Ignoring.[/yellow]"
                )

        # 4. Add the preference with all operations in a single async call
        calculated_priority, auto_download = asyncio.run(
            _add_language_preference(
                DEFAULT_USER_ID,
                validated_code,
                preference_type,
                priority,
                learning_goal,
            )
        )

        # 5. Show success message
        display_name = get_language_display_name(validated_code.value)
        console.print()
        console.print(
            f"Added '{validated_code.value}' ({display_name}) as {preference_type.value.upper()} language"
        )
        console.print(f"Priority: {calculated_priority}")
        auto_status = "enabled" if auto_download else "disabled"
        console.print(f"Auto-download: {auto_status}")
        if learning_goal:
            console.print(f"Goal: {learning_goal}")
        console.print()

    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(3)




async def _compact_priorities(
    user_id: str, pref_type: LanguagePreferenceType
) -> None:
    """
    Compact priorities after removal to ensure sequential numbering.

    After removing a language, priorities may have gaps (e.g., [1, 3, 4]).
    This function renumbers them to be sequential (e.g., [1, 2, 3]).

    Parameters
    ----------
    user_id : str
        The user identifier.
    pref_type : LanguagePreferenceType
        The preference type to compact priorities for.

    Examples
    --------
    >>> await _compact_priorities("default_user", LanguagePreferenceType.LEARNING)
    # Priorities [1, 3, 5] become [1, 2, 3]
    """
    repo = UserLanguagePreferenceRepository()

    async for session in db_manager.get_session():
        # Get all preferences of this type, sorted by priority
        prefs = await repo.get_preferences_by_type(session, user_id, pref_type)

        # Renumber priorities to be sequential
        for new_priority, pref in enumerate(prefs, start=1):
            if pref.priority != new_priority:
                await repo.update_priority(
                    session, user_id, pref.language_code, new_priority
                )

        await session.commit()


@language_app.command()
def remove(
    language: str = typer.Argument(..., help="Language code to remove"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """
    Remove a language preference.

    Removes a language from your preferences and renumbers priorities
    to maintain sequential ordering.

    Parameters
    ----------
    language : str
        Language code to remove (e.g., "it", "es-MX").
    yes : bool
        Skip confirmation prompt if True.

    Examples
    --------
    Remove with confirmation:
        $ chronovista languages remove it

    Remove without confirmation:
        $ chronovista languages remove it --yes
    """
    # Normalize language code
    lang_code = language.strip().lower()

    # Check if preference exists
    repo = UserLanguagePreferenceRepository()

    async def _remove_preference() -> tuple[bool, Optional[str], Optional[LanguagePreferenceType]]:
        """Helper to check and remove preference."""
        async for session in db_manager.get_session():
            # Get existing preference
            existing = await repo.get_by_composite_key(
                session, DEFAULT_USER_ID, lang_code
            )

            if not existing:
                return (False, None, None)

            # Get preference type for compacting priorities later
            pref_type = LanguagePreferenceType(existing.preference_type)
            display_name = get_language_display_name(existing.language_code)

            # If not --yes, prompt for confirmation
            if not yes:
                pref_type_str = pref_type.value.upper()
                confirmed = typer.confirm(
                    f"Remove '{existing.language_code}' ({display_name}) from {pref_type_str} languages?",
                    default=False,
                )
                if not confirmed:
                    return (True, None, None)  # Found but cancelled

            # Delete the preference
            deleted = await repo.delete_user_preference(
                session, DEFAULT_USER_ID, lang_code
            )

            if not deleted:
                return (False, None, None)

            await session.commit()
            return (True, display_name, pref_type)

        return (False, None, None)

    # Execute removal
    found, display_name, pref_type = asyncio.run(_remove_preference())

    if not found:
        console.print(f"Language '{lang_code}' not found in your preferences.")
        raise typer.Exit(0)

    # If cancelled by user
    if display_name is None:
        console.print("Cancelled.")
        raise typer.Exit(1)

    # Compact priorities for the affected preference type
    if pref_type:
        asyncio.run(_compact_priorities(DEFAULT_USER_ID, pref_type))

    # Show success message
    console.print(f"Removed '{lang_code}' ({display_name})")


@language_app.command()
def reset(
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
    no_setup: bool = typer.Option(False, "--no-setup", help="Skip reconfiguration offer"),
) -> None:
    """
    Reset all language preferences.

    Removes all configured language preferences from the database.
    By default, prompts for confirmation and offers to reconfigure after reset.

    Parameters
    ----------
    yes : bool
        Skip confirmation prompt if True.
    no_setup : bool
        Skip reconfiguration offer after reset if True.

    Examples
    --------
    Reset with confirmation and reconfiguration offer:
        $ chronovista languages reset

    Reset without confirmation:
        $ chronovista languages reset --yes

    Reset without confirmation or reconfiguration:
        $ chronovista languages reset --yes --no-setup
    """
    try:
        async def _reset_preferences() -> tuple[int, bool]:
            """Helper to count and reset preferences."""
            repo = UserLanguagePreferenceRepository()
            async for session in db_manager.get_session():
                # Get count of existing preferences
                existing = await repo.get_user_preferences(session, DEFAULT_USER_ID)
                count = len(existing)

                # If no preferences, show message and exit
                if count == 0:
                    return (0, False)

                # If --yes not provided, show confirmation with count
                if not yes:
                    confirmed = typer.confirm(
                        f"This will remove all {count} configured language preferences.\nAre you sure?",
                        default=False,
                    )
                    if not confirmed:
                        return (count, False)  # Count available but cancelled

                # Delete all preferences
                deleted_count = await repo.delete_all_user_preferences(
                    session, DEFAULT_USER_ID
                )
                await session.commit()
                return (deleted_count, True)

            return (0, False)

        # Execute reset
        count, success = asyncio.run(_reset_preferences())

        # Handle no preferences case
        if count == 0:
            console.print("No language preferences to reset.")
            raise typer.Exit(0)

        # Handle cancellation
        if not success:
            console.print("Cancelled.")
            raise typer.Exit(1)

        # Show success message
        console.print()
        console.print("All language preferences cleared.")
        console.print()

        # Offer reconfiguration if --no-setup not provided
        if not no_setup:
            reconfig = typer.confirm(
                "Would you like to reconfigure now?",
                default=True,
            )
            if reconfig:
                # Run interactive setup
                detected = detect_system_locale()
                accepted, default_langs = _show_first_run_defaults(detected)

                if accepted:
                    # User accepted defaults
                    prefs_dict: Dict[LanguagePreferenceType, List[str]] = {
                        LanguagePreferenceType.FLUENT: default_langs,
                        LanguagePreferenceType.LEARNING: [],
                        LanguagePreferenceType.CURIOUS: [],
                        LanguagePreferenceType.EXCLUDE: [],
                    }
                    goals_dict: Dict[str, str] = {}
                else:
                    # User chose to customize
                    prefs_dict = _run_full_interactive_setup()
                    learning_langs = prefs_dict.get(LanguagePreferenceType.LEARNING, [])
                    goals_dict = _prompt_learning_goals(learning_langs)

                # Save new preferences
                asyncio.run(_save_preferences(DEFAULT_USER_ID, prefs_dict, goals_dict))
                _show_confirmation_summary(prefs_dict, goals_dict)

    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(2)
