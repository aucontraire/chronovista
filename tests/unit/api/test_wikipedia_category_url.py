"""Unit tests for the Wikipedia category URL helper (Feature 086).

The category detail page links out to the public Wikipedia category page. The URL must use
MediaWiki's title conventions (spaces -> underscores) and keep the readable punctuation Wikipedia
allows in category titles, while percent-encoding genuinely unsafe characters. Category names are
neutral placeholders (public repo).
"""

from __future__ import annotations

from chronovista.api.routers.wikipedia_categories import _wikipedia_category_url

_BASE = "https://en.wikipedia.org/wiki/Category:"


def test_spaces_become_underscores() -> None:
    assert _wikipedia_category_url("Category A") == f"{_BASE}Category_A"


def test_readable_punctuation_is_preserved() -> None:
    # Parentheses and commas stay literal so the link is human-legible.
    url = _wikipedia_category_url("Place A (Region B), Country C")
    assert url == f"{_BASE}Place_A_(Region_B),_Country_C"


def test_unsafe_characters_are_percent_encoded() -> None:
    # '#', '?', '%' would break the URL path and must be encoded.
    url = _wikipedia_category_url("A # B ? C")
    assert "#" not in url and "?" not in url
    assert url.startswith(_BASE)
