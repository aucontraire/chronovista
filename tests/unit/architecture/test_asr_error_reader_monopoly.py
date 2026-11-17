"""Architecture fitness test -- the UNGATED asr-error reader has exactly ONE consumer.

FR-011 suppresses a flagged ASR-error form from *matching* via
``entity_asr_errors.usable_as_match_pattern``, enforced in one place: the scan match
reader ``EntityAsrErrorRepository.get_multiword_forms_for_matching`` applies
``usable_as_match_pattern.is_(True)``. The repository deliberately exposes a SECOND,
**ungated** multiword reader, ``get_all_multiword_forms_for_discovery`` -- a suppressed form must stay
visible to corrections discovery (``cross_segment_discovery``), and that visibility is
exactly what bounds the downside of flagging (a wrong flag costs matching, never
discovery). The two readers are correct as a pair, but neither NAME encodes the gate.

**Monopoly, not instance.** An earlier version of this guard watched a single file (the
scan service) and asserted it never calls the ungated reader. That pins code already
audited; it does nothing for the consumer nobody has written yet -- which is the whole
hazard for a "a flagged form can never match again" contract. The companion
``test_match_form_tokens_single_source`` module in this directory draws the same line:
*"not 'the home computes the right thing' ... but 'nothing derives [it] except the
home.'"* So this guard is the monopoly version: it asserts, over all of
``src/chronovista/``, that the ungated reader is referenced ONLY by the one sanctioned
discovery consumer. A fourth consumer -- or a read added to the writer-only
``asr_alias_registry`` -- that reaches for the plausible-sounding ungated sibling would
bypass FR-011 suppression entirely, and the failure is **silent by construction**: the
ungated result is a strict SUPERSET of the gated one, so nothing errors and the extra
(un-suppressed) matches merely look like better recall.

AST attribute-access, not text: a docstring/comment mention -- the migration
``d4b1f8a3c6e5``'s design note, the repository's own ``:meth:`` cross-references -- is not
an attribute access and is correctly ignored.

CONTRACT GUARD. Three consumer files of ``EntityAsrErrorRepository`` already exist
(discovery/ungated, scan/gated, registry/writer), crossing the Constitution's v1.3.0
>=3-call-site threshold for an exact-count single-source test; and v1.4.0 extends
single-sourcing to contract guards regardless of count. "FR-011 suppression holds only if
every scan-side read goes through the gated reader" is that contract. Precedent: the
OntoNotes -> ``EntityType.__doc__`` guard (#370).

MUTATION-VERIFIED (on a relocated copy; real tree untouched):
  * add ``<anything>.get_all_multiword_forms_for_discovery`` in any non-allowlisted file under
    ``src/chronovista/`` -> :func:`test_ungated_reader_has_exactly_one_consumer` RED;
  * break the gated reader's name out of the scan service ->
    :func:`test_gated_reader_is_wired_into_the_scan` RED.
"""

from __future__ import annotations

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SRC = _REPO_ROOT / "src" / "chronovista"

_GATED_READER = "get_multiword_forms_for_matching"
_UNGATED_READER = "get_all_multiword_forms_for_discovery"
_SCAN_SERVICE = "services/entity_mention_scan_service.py"

# The ONLY sanctioned consumer of the ungated reader. Corrections discovery must see
# suppressed forms; that is the deliberate, bounded exception to FR-011 suppression.
_UNGATED_ALLOWLIST = frozenset({"services/cross_segment_discovery.py"})


def _files_accessing(attr: str) -> set[str]:
    """``src/chronovista``-relative paths of files with an ``ast.Attribute`` ``.attr``.

    AST, not text, so a docstring or comment mention is not counted -- only a real
    ``<expr>.attr`` access.
    """
    hits: set[str] = set()
    for py in sorted(_SRC.rglob("*.py")):
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover - defensive; src is importable
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == attr:
                hits.add(str(py.relative_to(_SRC)))
                break
    return hits


def test_ungated_reader_has_exactly_one_consumer() -> None:
    """``get_all_multiword_forms_for_discovery`` is read ONLY by the sanctioned discovery consumer."""
    consumers = _files_accessing(_UNGATED_READER)
    extra = consumers - _UNGATED_ALLOWLIST
    missing = _UNGATED_ALLOWLIST - consumers
    assert not extra, (
        f"{sorted(extra)} reference the UNGATED asr-error reader `{_UNGATED_READER}`. On "
        "any scan/matching path it bypasses `usable_as_match_pattern` and silently "
        "un-suppresses every FR-011-flagged form (the ungated result is a strict superset "
        f"-- nothing errors). Use the gated `{_GATED_READER}` for matching. If this is a "
        "genuine new discovery-side consumer, add it to _UNGATED_ALLOWLIST with a reason."
    )
    assert not missing, (
        f"the sanctioned ungated consumer(s) {sorted(missing)} no longer read "
        f"`{_UNGATED_READER}` -- it may have moved or been renamed; update the allowlist."
    )


def test_gated_reader_is_wired_into_the_scan() -> None:
    """Positive companion: the suppression gate is actually ON the scan path.

    The monopoly test forbids the ungated reader everywhere but discovery; this asserts
    the scan still routes through the GATED reader, so FR-011 is wired in rather than the
    scan quietly reading nothing (or a future, un-gated replacement).
    """
    assert _SCAN_SERVICE in _files_accessing(_GATED_READER), (
        f"the scan service no longer references the gated reader `{_GATED_READER}`. FR-011 "
        "suppression is enforced only through it; if the scan matcher's reader moved, "
        "update _SCAN_SERVICE / _GATED_READER and confirm the new reader is gated."
    )
