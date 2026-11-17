"""Architecture fitness test -- the entity match-form TOKEN SET has one home.

Feature 111 makes ASR-error forms matchable: ``_build_entity_pattern`` folds every
admissible ASR form into the regex alternation ``pg_pattern`` AND into
``gap_form_seqs``, so an ASR fold produces a competing/emitted span. The scoped-scan
widening (``_shared_token_neighbour_ids``) and the cross-segment candidate pre-filter
(inside ``_scan_cross_segment``) decide *which entities compete / are searched* from an
entity's token set, and MUST derive that set from the same forms the matcher uses:
names PLUS admissible ASR folds. :func:`_match_form_tokens` is the single home for that
union.

The failure this guards against is the one that actually shipped on the branch: a
consumer derives its per-entity token set from NAMES ONLY (calling ``_tokens`` directly
over ``(canonical_name, *alias_names)``), omitting ``asr_folds``. That is invisible to
``test_token_helper_single_source`` -- which only proves tokenisation goes through
``_tokens``, not that the FORM SET is complete -- and it produces the scoped-widening
shadowing false-positive and the cross-segment false-negative (Deliverable B §0).

This is the MONOPOLY half of the single-source contract: not "the home computes the
right thing" (that is :func:`test_match_form_tokens_unions_asr_folds`) but "nothing
derives a per-entity form-token set except the home." We enforce it as an exact-set
site test: the scopes that call ``_tokens(...)`` directly must equal a sanctioned
allowlist. A consumer that builds tokens locally appears as an extra scope and fails; a
consumer that routes through ``_match_form_tokens`` does not call ``_tokens`` directly
and drops out.

SANCTIONED ``_tokens(...)`` CALLERS -- each exempt for a STATED reason:
  ``_match_form_tokens``   THE home (names via ``_tokens``, folds via ``_TOKEN_RE``).
  ``gap_form_seqs``        ordered multi-token SEQUENCES for gap matching -- a different
                           shape than a flat set, same primitives.
  ``_asr_form_admissible`` admissibility PROPERTY of one form, not a per-entity set.
  ``_any_form_tokenless``  the ``always_run`` predicate for the pre-filters: "is any
                           match form (name OR fold) token-empty?" -- total over the
                           home's form set, a companion to it, not a per-entity set.
  ``<module>``             ``_FILLER_TOKENS_BY_LANG``: disfluency fillers, not entity
                           forms.
Text-side tokenisation (``_TOKEN_RE.findall(folded_text...)`` over transcript text in the
scan loops) is the SEARCH side, never calls ``_tokens``, and is out of scope here. The
``CrossSegmentDiscovery`` alias loading (the spike's 4th site) is a different algorithm
that does not derive this relation and is exempt by not calling ``_tokens`` here.

MUTATION-VERIFIED (Constitution Single-Source Operations, v1.3.0): re-inline
``tokens.update(_tokens(form))`` over an entity's names at any consumer (the
pre-Deliverable-B state of ``_shared_token_neighbour_ids`` / ``_scan_cross_segment``) and
:func:`test_form_token_set_has_one_home` goes RED; route it through
``_match_form_tokens`` and it is green.
"""

from __future__ import annotations

import ast
from pathlib import Path

from chronovista.services.entity_mention_scan_service import _match_form_tokens

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SERVICE = (
    _REPO_ROOT / "src" / "chronovista" / "services" / "entity_mention_scan_service.py"
)

# Scopes allowed to call `_tokens(...)` directly. Everything else that needs an
# entity's match-form token set must call `_match_form_tokens`. See the module
# docstring for the stated exemption reason behind each name.
_SANCTIONED_TOKENS_CALLERS = frozenset(
    {
        "_match_form_tokens",
        "_any_form_tokenless",
        "gap_form_seqs",
        "_asr_form_admissible",
        "<module>",
    }
)

# Scopes allowed to touch the raw tokeniser regex ``_TOKEN_RE`` directly. COMPANION to
# the ``_tokens``-caller guard: a consumer that re-inlines tokenisation as
# ``_TOKEN_RE.findall(_fold_diacritics(f)[0].casefold())`` -- the two-line unpack that is
# house style for the text side (``folded_text, offset_map = _fold_diacritics(...)``) --
# never calls ``_tokens`` and so slips the caller guard AND the older textual
# ``test_token_helper_single_source`` (whose literal spans one line). Keying on
# ``_TOKEN_RE`` by scope catches every NEW scope that tokenises on its own. It stays
# blind to a form-side re-inline INSIDE an already-sanctioned scope (e.g.
# ``_scan_cross_segment``, sanctioned for its text-side ``present_tokens``); the
# behavioural differentials in
# tests/integration/services/test_deliverable_b_asr_token_relation.py cover that
# residual, catching the instance regardless of spelling.
_SANCTIONED_TOKEN_RE_SCOPES = frozenset(
    {
        "_tokens",  # the tokeniser itself
        "_match_form_tokens",  # splits folded ASR forms
        "_any_form_tokenless",  # totality check splits folded forms
        "gap_form_seqs",  # ordered sequences from folded forms
        "_collect_gap_matches",  # TEXT side: tokenises segment text
        "_scan_cross_segment",  # TEXT side: present_tokens from transcript text
    }
)


def _scopes_calling_tokens() -> set[str]:
    """Names of the scopes (function/method, or ``<module>``) that call ``_tokens``."""
    tree = ast.parse(_SERVICE.read_text(encoding="utf-8"))
    callers: set[str] = set()

    class _Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self._scope: list[str] = ["<module>"]

        def _enter(self, node: ast.AST, name: str) -> None:
            self._scope.append(name)
            self.generic_visit(node)
            self._scope.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self._enter(node, node.name)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self._enter(node, node.name)

        def visit_Call(self, node: ast.Call) -> None:
            if isinstance(node.func, ast.Name) and node.func.id == "_tokens":
                callers.add(self._scope[-1])
            self.generic_visit(node)

    _Visitor().visit(tree)
    callers.discard("_tokens")  # the def itself does not call _tokens; defensive
    return callers


def test_form_token_set_has_one_home() -> None:
    callers = _scopes_calling_tokens()
    extra = callers - _SANCTIONED_TOKENS_CALLERS
    missing = _SANCTIONED_TOKENS_CALLERS - callers
    assert not extra, (
        f"{sorted(extra)} call `_tokens(...)` directly to build a per-entity token "
        "set. Route through `_match_form_tokens(names, asr_folds)` so ASR forms are "
        "never dropped (Deliverable B: scoped-widening shadowing / cross-segment "
        "false-negative). If a new site is a genuine exception, add it to "
        "_SANCTIONED_TOKENS_CALLERS with a stated reason in this module's docstring."
    )
    assert not missing, (
        f"expected sanctioned `_tokens` callers are gone: {sorted(missing)}. The "
        "single home may have moved or been renamed; update this guard to the new home."
    )


def _scopes_using_token_re() -> set[str]:
    """Names of the scopes that touch ``_TOKEN_RE`` directly (any attribute access)."""
    tree = ast.parse(_SERVICE.read_text(encoding="utf-8"))
    scopes: set[str] = set()

    class _Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self._scope: list[str] = ["<module>"]

        def _enter(self, node: ast.AST, name: str) -> None:
            self._scope.append(name)
            self.generic_visit(node)
            self._scope.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self._enter(node, node.name)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self._enter(node, node.name)

        def visit_Attribute(self, node: ast.Attribute) -> None:
            if isinstance(node.value, ast.Name) and node.value.id == "_TOKEN_RE":
                scopes.add(self._scope[-1])
            self.generic_visit(node)

    _Visitor().visit(tree)
    return scopes


def test_raw_tokenisation_has_one_home() -> None:
    """COMPANION guard (Finding A): catch a re-inline that evades the ``_tokens`` guard.

    The two-line ``_TOKEN_RE.findall(_fold_diacritics(f)[0].casefold())`` spelling calls
    no ``_tokens`` AND splits ``test_token_helper_single_source``'s one-line literal, so
    both pass while the names-only bug is re-introduced. Keying on ``_TOKEN_RE`` by scope
    catches a new tokenising scope. Completeness of the single-source contract depends on
    the CONJUNCTION of this test, ``test_form_token_set_has_one_home``, and
    ``test_token_helper_single_source``; do not relax one without the others.
    """
    scopes = _scopes_using_token_re()
    extra = scopes - _SANCTIONED_TOKEN_RE_SCOPES
    missing = _SANCTIONED_TOKEN_RE_SCOPES - scopes
    assert not extra, (
        f"{sorted(extra)} tokenise with `_TOKEN_RE` directly. Derive an entity's token "
        "set via `_match_form_tokens` (and its always_run flag via `_any_form_tokenless`)"
        " rather than re-inlining tokenisation. If a new site is a genuine text-side or "
        "primitive use, add it to _SANCTIONED_TOKEN_RE_SCOPES with a stated reason."
    )
    assert not missing, (
        f"expected `_TOKEN_RE` scopes are gone: {sorted(missing)}; update the allowlist "
        "to the moved home(s)."
    )


def test_match_form_tokens_unions_asr_folds() -> None:
    """The home actually includes ASR-fold tokens (the CONTENT half of the contract).

    MUTATION: drop the ``asr_folds`` loop from ``_match_form_tokens`` and this goes RED.
    """
    got = _match_form_tokens(["Alfa"], ["bravo charlie"])
    assert {"bravo", "charlie"} <= got, got
    # A fold coinciding with a name contributes nothing new (coverage, not provenance).
    assert _match_form_tokens(["Delta"], ["delta"]) == {"delta"}
    # Names still fold + split as before.
    assert _match_form_tokens(["Perú, Café"], []) == {"peru", "cafe"}
