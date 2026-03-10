"""
Tests for translate_python_regex_to_posix() — Feature 040.

Covers:
- T004: Contract-table translation cases for Python → POSIX regex word-boundary
  conversion used when executing pattern searches against PostgreSQL.
- T006: Malformed regex validation (FR-015) — ensures invalid patterns raise
  ValueError with a user-friendly message rather than propagating a raw
  re.error to the caller.

The function under test does NOT yet exist; these tests are intentionally
written to FAIL until the implementation is added to
src/chronovista/repositories/transcript_segment_repository.py.

Note: No pytestmark = pytest.mark.asyncio is needed here because
translate_python_regex_to_posix() is a synchronous, pure function.
"""

from __future__ import annotations

import pytest

from chronovista.repositories.transcript_segment_repository import (
    translate_python_regex_to_posix,
)


class TestTranslatePythonRegexToPosix:
    """T004 — Contract-table cases for Python → POSIX word-boundary translation.

    Python regex uses ``\\b`` / ``\\B`` for word boundaries; PostgreSQL's
    ``~`` operator uses ``\\y`` / ``\\Y``.  The function must rewrite
    boundary assertions while leaving ``\\b`` inside character classes
    (where it means backspace) and escaped literal backslashes (``\\\\b``)
    untouched.
    """

    def test_start_boundary_only(self) -> None:
        """\\b at the start of a pattern becomes \\y."""
        result = translate_python_regex_to_posix(r"\bamlo\w*")
        assert result == r"\yamlo\w*"

    def test_end_boundary_only(self) -> None:
        """\\b at the end of a pattern becomes \\y."""
        result = translate_python_regex_to_posix(r"amlo\b")
        assert result == r"amlo\y"

    def test_both_boundaries(self) -> None:
        """\\b on both sides of a word are both converted to \\y."""
        result = translate_python_regex_to_posix(r"\bamlo\b")
        assert result == r"\yamlo\y"

    def test_non_word_boundary(self) -> None:
        """\\B (non-word boundary) becomes \\Y."""
        result = translate_python_regex_to_posix(r"\Bamlo")
        assert result == r"\Yamlo"

    def test_boundary_inside_character_class_unchanged(self) -> None:
        r"""\\b inside [...] is a backspace assertion; it must not be rewritten."""
        result = translate_python_regex_to_posix(r"[\b]amlo")
        assert result == r"[\b]amlo"

    def test_no_boundaries_unchanged(self) -> None:
        """Patterns without any boundary assertion pass through unchanged."""
        result = translate_python_regex_to_posix(r"amlo\w*")
        assert result == r"amlo\w*"

    def test_escaped_backslash_before_b_unchanged(self) -> None:
        r"""\\\\b is a literal backslash followed by 'b', not a boundary — unchanged."""
        result = translate_python_regex_to_posix(r"\\b")
        assert result == r"\\b"

    def test_mixed_boundary_inside_and_outside_class(self) -> None:
        r"""\\b outside and \\B outside are translated; \\b inside [...] is not."""
        result = translate_python_regex_to_posix(r"\b[\b]\B")
        assert result == r"\y[\b]\Y"


class TestMalformedRegexValidation:
    """T006 — Malformed regex detection (FR-015).

    translate_python_regex_to_posix() must validate the pattern with Python's
    ``re`` module before attempting translation.  Invalid patterns should raise
    ``ValueError`` with a message suitable for display to the user (not a raw
    ``re.error`` traceback).

    Valid patterns must never raise.
    """

    def test_unbalanced_bracket_raises_value_error(self) -> None:
        """An unclosed character class bracket is invalid and raises ValueError."""
        with pytest.raises(ValueError, match=r"[Ii]nvalid|[Rr]egex|[Pp]attern"):
            translate_python_regex_to_posix("[abc")

    def test_unbalanced_parenthesis_raises_value_error(self) -> None:
        """An unclosed group parenthesis is invalid and raises ValueError."""
        with pytest.raises(ValueError, match=r"[Ii]nvalid|[Rr]egex|[Pp]attern"):
            translate_python_regex_to_posix("(abc")

    def test_valid_literal_pattern_does_not_raise(self) -> None:
        """A plain literal pattern is valid and must not raise."""
        result = translate_python_regex_to_posix("hello world")
        assert isinstance(result, str)

    def test_valid_boundary_pattern_does_not_raise(self) -> None:
        r"""A pattern containing \\b is valid and must not raise."""
        result = translate_python_regex_to_posix(r"\bhello\b")
        assert isinstance(result, str)

    def test_valid_complex_pattern_does_not_raise(self) -> None:
        """A complex but syntactically valid pattern must not raise."""
        result = translate_python_regex_to_posix(r"\b\w+\s+\w+\b")
        assert isinstance(result, str)
