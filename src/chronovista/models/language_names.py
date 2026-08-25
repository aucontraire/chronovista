"""Canonical BCP-47 language-code → display-name mapping.

Single source of truth for language display names across the backend (CLI,
the ``/settings/supported-languages`` endpoint, and transcript routes). The
frontend keeps a mirror of this data in ``frontend/src/constants/languageNames.ts``;
the two must stay in agreement (there is no cross-language codegen, so a change
here should be reflected there).

Region-qualified codes carry their region name (``es-MX`` → "Spanish
(Mexico)"). Lookup is case-insensitive per RFC 5646; an unknown code is
returned unchanged rather than guessed.
"""

from __future__ import annotations

LANGUAGE_NAMES: dict[str, str] = {
    # Major English variants
    "en": "English",
    "en-US": "English (United States)",
    "en-GB": "English (United Kingdom)",
    "en-AU": "English (Australia)",
    "en-CA": "English (Canada)",
    "en-IN": "English (India)",
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
    "zh": "Chinese",
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


def get_language_name(code: str) -> str:
    """Return the human-readable name for a BCP-47 language code.

    Lookup is case-insensitive (``EN-us`` resolves the same as ``en-US``). An
    unknown code is returned unchanged rather than guessed.

    Parameters
    ----------
    code : str
        A BCP-47 language code (e.g. ``"en"``, ``"en-US"``, ``"es-MX"``).

    Returns
    -------
    str
        The display name, or ``code`` itself if there is no mapping.

    Examples
    --------
    >>> get_language_name("en")
    'English'
    >>> get_language_name("es-MX")
    'Spanish (Mexico)'
    >>> get_language_name("unknown")
    'unknown'
    """
    if not code:
        return code

    if code in LANGUAGE_NAMES:
        return LANGUAGE_NAMES[code]

    normalized = code.lower()
    for key, value in LANGUAGE_NAMES.items():
        if key.lower() == normalized:
            return value

    return code
