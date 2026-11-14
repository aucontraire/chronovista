"""Architecture fitness test -- the name-token fold+split has one inline home.

The entity-mention scanner tokenises a name *form* the same way in several places:
fold diacritics / whitespace / invisibles, casefold, then split on word-char runs
(``_TOKEN_RE.findall(_fold_diacritics(form)[0].casefold())``). Feature 111 extracts
that into one module-level helper, :func:`_tokens`, so the candidate pre-filter, the
scope-token set, and the neighbour-token set all agree by construction.

The failure this guards against: a future edit re-inlines the raw expression at a new
call site. Two copies can drift (one adds ``.strip()``, one forgets ``.casefold()``)
and the shared-token arbitration invariant silently weakens. The guard keys on the
**raw inline expression** ``_TOKEN_RE.findall(_fold_diacritics(`` and asserts it
appears nowhere outside the body of ``_tokens`` itself -- the sole legitimate home.

MUTATION-VERIFIED (Constitution Single-Source Operations): re-inline the expression at
any other site (e.g. ``toks = _TOKEN_RE.findall(_fold_diacritics(form)[0].casefold())``
in place of ``toks = _tokens(form)``) and
``test_token_fold_split_has_one_inline_home`` goes RED; revert, green. The docstring
reference was rewritten to ``_tokens(form)`` precisely so the guard counts code, not
prose. Confirmed on 2026-11-13.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from chronovista.services.entity_mention_scan_service import _tokens

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SERVICE = (
    _REPO_ROOT / "src" / "chronovista" / "services" / "entity_mention_scan_service.py"
)

# The raw inline expression the helper replaces. One occurrence is legitimate --
# the return statement inside _tokens; every other occurrence is a re-inline.
_INLINE = "_TOKEN_RE.findall(_fold_diacritics("


def _tokens_body_line_span() -> tuple[int, int]:
    """Return the ``(start, end)`` 1-based line span of the ``_tokens`` def."""
    tree = ast.parse(_SERVICE.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "_tokens":
            assert node.end_lineno is not None
            return node.lineno, node.end_lineno
    raise AssertionError("module-level `_tokens` helper not found")


def test_token_fold_split_has_one_inline_home() -> None:
    start, end = _tokens_body_line_span()
    offenders: list[int] = []
    for lineno, line in enumerate(
        _SERVICE.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if _INLINE in line and not (start <= lineno <= end):
            offenders.append(lineno)
    assert not offenders, (
        "the name-token fold+split expression "
        f"`{_INLINE}...)` is inlined outside the `_tokens` helper at "
        f"lines {offenders}. Call `_tokens(form)` instead so every tokenisation "
        "stays identical by construction; a divergent copy weakens the "
        "shared-token arbitration invariant (NOTE 020)."
    )


def test_tokens_helper_actually_holds_the_expression() -> None:
    """The guard is meaningful only if the helper really contains the expression --
    else a rename leaves the guard green while the home moved. The other mutation
    direction.
    """
    start, end = _tokens_body_line_span()
    lines = _SERVICE.read_text(encoding="utf-8").splitlines()
    body = "\n".join(lines[start - 1 : end])
    assert _INLINE in body, (
        "`_tokens` no longer contains the fold+split expression; the single home "
        "moved. Update this guard to the new home."
    )


@pytest.mark.parametrize(
    ("form", "expected"),
    [
        ("Bravo, Charlie", ["bravo", "charlie"]),
        ("", []),
        ("   ", []),
        (",.;", []),
    ],
)
def test_tokens_behaviour(form: str, expected: list[str]) -> None:
    assert _tokens(form) == expected


def test_tokens_folds_accents() -> None:
    # An accented form folds to its unaccented, casefolded tokens; a plain split
    # would keep the accent and the comma-attached word intact.
    assert _tokens("Perú, Café") == ["peru", "cafe"]
