"""Single-source fitness guard for the positioned qualification rule (Feature 117).

The evidence panel and the proximity record computation must count the SAME
mentions, or a reviewer opens passages that the proximity numbers did not count
(and vice versa). They share one rule, ``positioned_transcript_mention_qualifies``,
called once by the panel and once PER ENDPOINT by the proximity self-join. A
surface that hand-rolls its own copy, or an endpoint that stops being qualified,
changes the exact count below and fails here (Constitution: single-source guard).
The behavioral proof lives in ``tests/integration/test_proximity_service.py``
(``TestSharedQualificationRule`` and ``TestPanelEquivalence``).
"""

from __future__ import annotations

import inspect
from pathlib import Path

import chronovista
from chronovista.repositories import entity_mention_repository

_RULE = "positioned_transcript_mention_qualifies"
_SRC = Path(chronovista.__file__).parent

# One call in the panel (co_occurrence_evidence), two in _instance_select (ma, mb).
_EXPECTED_CALL_SITES = {
    "repositories/entity_mention_repository.py": 1,
    "repositories/entity_pair_proximity_repository.py": 2,
}


def _call_sites() -> dict[str, int]:
    counts: dict[str, int] = {}
    for path in _SRC.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        n = source.count(f"{_RULE}(") - source.count(f"def {_RULE}(")
        if n:
            counts[path.relative_to(_SRC).as_posix()] = n
    return counts


def test_the_positioned_rule_has_exactly_its_three_call_sites() -> None:
    assert _call_sites() == _EXPECTED_CALL_SITES, (
        "positioned_transcript_mention_qualifies call sites changed. The panel calls "
        "it once and the proximity self-join once per endpoint. If a surface was added "
        "or one stopped calling the shared rule, the panel and proximity can now "
        "disagree about which mentions count."
    )


def test_the_panel_call_is_inside_co_occurrence_evidence() -> None:
    method = inspect.getsource(
        entity_mention_repository.EntityMentionRepository.co_occurrence_evidence
    )
    assert f"{_RULE}(" in method


def test_the_rule_states_its_contract_at_the_point_of_definition() -> None:
    doc = inspect.getdoc(
        entity_mention_repository.positioned_transcript_mention_qualifies
    )
    assert doc is not None
    for clause in (
        "transcript-sourced",
        "not a ``manual`` assertion",
        "visible names",
        "asr_match",
        "abs(start(A) - start(B)) <= w",
        "inclusive",
    ):
        assert clause in doc, f"contract clause missing from the docstring: {clause!r}"


# ----- producer guard (Feature 117, T029) -----------------------------------------
#
# Every path that changes positioned qualifying mentions, their timing, their
# exclusions, or an entity's visible names must invalidate the affected proximity
# scopes in its own transaction. The behavioral proof, one mutation-verified test per
# producer, is tests/integration/services/test_proximity_producers.py. This guard pins
# WHERE the calls are, so adding or removing a producer is a deliberate, reviewed edit.
#
# Audited NOT to be producers (no positioned mention, timing, exclusion, or visible
# name changes): CLI find_and_replace, rebuild_text, ASR-error registration (writes
# entity_asr_errors, not a visible name), entity_creation._register_aliases (new
# entities only), the metadata scan (title/description), and manual associations
# (no segment).
_INVALIDATE = "invalidate_proximity_scopes("
_EXPECTED_PRODUCER_CALL_SITES = {
    "api/routers/entity_mentions.py": 4,  # alias create + rename; exclude + restore
    "cli/entity_commands.py": 3,  # add-alias, remove-alias, edit-alias rename
    "repositories/video_transcript_repository.py": 1,  # segment (re)creation
    # apply_to_segments; the cross-segment chunk commit; 2 revert branches
    "services/batch_correction_service.py": 4,
    "services/entity_curation_service.py": 5,  # rename + undo; alias delete + undo; undo exclusion
    "services/entity_mention_scan_service.py": 2,  # per-segment + cross-segment scan
    "services/tag_management.py": 1,  # link a tag to an existing entity's name
    "services/transcript_whitespace_service.py": 1,  # whitespace normalization
    # Not a library change: `rebuild --video-id/--entity-id` explicitly invalidates
    # the scopes the operator asked for (video branch, entity branch).
    "services/proximity_service.py": 2,
}


def _producer_call_sites() -> dict[str, int]:
    counts: dict[str, int] = {}
    for path in _SRC.rglob("*.py"):
        if "docs" in path.relative_to(_SRC).parts:
            continue
        source = path.read_text(encoding="utf-8")
        n = source.count(_INVALIDATE) - source.count(f"def {_INVALIDATE}")
        if n:
            counts[path.relative_to(_SRC).as_posix()] = n
    return counts


def test_the_proximity_producers_are_exactly_the_audited_call_sites() -> None:
    assert _producer_call_sites() == _EXPECTED_PRODUCER_CALL_SITES, (
        "invalidate_proximity_scopes call sites changed. If you added a path that "
        "changes positioned mentions, exclusions, or visible names, it must "
        "invalidate (and get a behavioral test in test_proximity_producers.py); if you "
        "removed one, proximity can silently go stale. Update the map deliberately."
    )
    assert sum(_EXPECTED_PRODUCER_CALL_SITES.values()) == 23


def test_the_current_predicate_has_one_home() -> None:
    """Freshness is decided in one place (``_is_current``): the claim, the counts,
    ``status`` and pair completeness must never disagree about the same row."""
    source = (_SRC / "repositories/entity_pair_proximity_repository.py").read_text(
        encoding="utf-8"
    )
    assert source.count("computed_revision.is_not_distinct_from(") == 1
    assert source.count("computed_revision.is_distinct_from(") == 0
    assert source.count("def _is_current(") == 1
