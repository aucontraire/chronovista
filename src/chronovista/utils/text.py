"""Text processing utilities for correction and analysis pipelines.

Provides helper functions for normalising text tokens extracted from
word-level diffs and cross-segment candidates.
"""

from __future__ import annotations

import re

# Characters to strip from the boundaries of tokens.  Internal punctuation
# (hyphens in "Teapot-Dome", apostrophes in "Khashoggi's") is preserved.
_BOUNDARY_PUNCT_RE = re.compile(
    r"^[.,;:!?\"'`()\[\]{}<>…—–\-/\\|@#$%^&*~]+|"
    r"[.,;:!?\"'`()\[\]{}<>…—–\-/\\|@#$%^&*~]+$"
)


def strip_boundary_punctuation(text: str) -> str:
    """Strip leading and trailing punctuation from text, preserving internal punctuation.

    Characters such as ``.``, ``,``, ``;``, ``:``, ``!``, ``?``, ``"``,
    ``'``, ``(``, ``)`` and similar are removed from the boundaries only.
    Internal punctuation (e.g., hyphens in "Teapot-Dome" or apostrophes
    in "Khashoggi's") is preserved.

    Parameters
    ----------
    text : str
        The input text to clean.

    Returns
    -------
    str
        The text with boundary punctuation removed.

    Examples
    --------
    >>> strip_boundary_punctuation('"Sheinbaum"')
    'Sheinbaum'
    >>> strip_boundary_punctuation("Teapot-Dome")
    'Teapot-Dome'
    >>> strip_boundary_punctuation("Khashoggi's")
    "Khashoggi's"
    >>> strip_boundary_punctuation("...hello...")
    'hello'
    """
    return _BOUNDARY_PUNCT_RE.sub("", text)
