"""ASR-match provenance contract guard (Feature 111, Constitution v1.4.0 committed contract).

Feature 111 adds ``DetectionMethod.ASR_MATCH`` for mentions recovered from a
registered ASR-error form. Two cross-feature data contracts (spec FR-014) must
hold for every reader of ``entity_mentions``, and this guards them as data (no
DB, no network):

1. **asr_match is transcript-derived.** ``EntityMentionRepository._TRANSCRIPT_METHODS``
   is the single committed home for "which detection methods count as a
   transcript appearance" (used by ``get_entity_video_list`` for per-video
   mention counts). It must name EXACTLY the non-manual ``DetectionMethod``
   values. Dropping ``asr_match`` (undercounting recovered mentions) or adding a
   new non-manual method to the enum without counting it both fail here — that is
   the mutation check.

2. **asr_match provenance lives on ``detection_method``, never on ``alias_id``.**
   An asr_match row carries ``alias_id IS NULL`` (enforced by the EntityMention
   model validator: ``alias_id`` is only valid for ``rule_match``). So any reader
   that equated ``alias_id IS NULL`` with "curated / non-recovered" would now
   wrongly fold recovered mentions into the curated bucket. The audit at the time
   this landed found every ``alias_id IS NULL`` reader already scoped to
   ``detection_method == 'rule_match'`` (alias backfill-linking and
   alias-coverage deletion), so none conflates asr_match with curated. This guard
   pins the enabling invariant — asr_match is NOT rule_match — so a future change
   that made them equal (collapsing the distinction those readers rely on) fails.
"""

from __future__ import annotations

from pathlib import Path

import chronovista.repositories.entity_mention_repository as _mention_repo_module
from chronovista.models.entity_mention import SPANNING_DETECTION_METHODS
from chronovista.models.enums import (
    ALIAS_LINKABLE_DETECTION_METHODS,
    SCAN_DETECTION_METHODS,
    DetectionMethod,
)
from chronovista.repositories.entity_mention_repository import EntityMentionRepository


def test_transcript_methods_are_exactly_the_non_manual_detection_methods() -> None:
    expected = {
        method.value
        for method in DetectionMethod
        if method is not DetectionMethod.MANUAL
    }
    assert expected == EntityMentionRepository._TRANSCRIPT_METHODS, (
        "_TRANSCRIPT_METHODS must name exactly the non-manual DetectionMethod "
        "values. A transcript-derived method missing from the set undercounts "
        "those mentions in get_entity_video_list; a manual value present would "
        "count hand-linked associations as transcript appearances. Update the "
        "set (and decide the counting semantics) when the enum changes."
    )


def test_asr_match_is_counted_as_transcript_derived() -> None:
    """The specific drift this release fixes: recovered ASR mentions are
    transcript appearances, so the per-video count must include them. Removing
    asr_match from _TRANSCRIPT_METHODS (reverting Feature 111 FR-014) fails this.
    """
    assert (
        DetectionMethod.ASR_MATCH.value in EntityMentionRepository._TRANSCRIPT_METHODS
    )


def test_asr_match_is_distinct_from_rule_match() -> None:
    """asr_match provenance must stay separable from rule_match: the backfill is
    reverted by ``DELETE WHERE detection_method='asr_match'`` (SC-009) and the
    precision audit samples asr_match rows (SC-001). Collapsing the two values
    would make recovered mentions indistinguishable from curated rule matches and
    silently break both — and the alias_id-IS-NULL readers that scope to
    rule_match would start matching recovered rows.
    """
    assert DetectionMethod.ASR_MATCH is not DetectionMethod.RULE_MATCH


def test_spanning_detection_methods_are_the_transcript_writers() -> None:
    """A cross-segment span is valid only for a transcript writer (never
    title/description/manual). SPANNING_DETECTION_METHODS is the single home the
    EntityMention validator reads; asr_match is a transcript writer, so a
    boundary-crossing ASR recovery keeps its asr_match provenance instead of being
    downgraded to rule_match (which would violate FR-014/SC-009). Dropping
    asr_match (reintroducing the spanning-write crash) or admitting manual (a
    non-transcript span) fails here.
    """
    assert {
        DetectionMethod.RULE_MATCH,
        DetectionMethod.USER_CORRECTION,
        DetectionMethod.ASR_MATCH,
    } == SPANNING_DETECTION_METHODS
    assert DetectionMethod.MANUAL not in SPANNING_DETECTION_METHODS


def test_scan_detection_methods_cover_asr_but_not_corrections() -> None:
    """SCAN_DETECTION_METHODS is the single home for the methods the rule-scan
    writes, deletes (every --full delete + the US4 compete delete), and counts
    (the counter-recompute helpers). asr_match MUST be included or recovered rows
    are never refreshed and accumulate as stale duplicates across rescans (the
    re-insert is ON CONFLICT DO NOTHING, so it fails silently). user_correction
    and manual MUST be excluded or a rescan would clobber human-authored mentions
    the scan does not re-create.
    """
    assert {
        DetectionMethod.RULE_MATCH,
        DetectionMethod.ASR_MATCH,
    } == SCAN_DETECTION_METHODS
    assert DetectionMethod.USER_CORRECTION not in SCAN_DETECTION_METHODS
    assert DetectionMethod.MANUAL not in SCAN_DETECTION_METHODS


def test_alias_linkable_methods_are_rule_match_only() -> None:
    """ALIAS_LINKABLE_DETECTION_METHODS is the single home for methods that may
    carry an alias_id — only rule_match. It overlaps SCAN_DETECTION_METHODS on
    rule_match but MUST NOT include asr_match: an ASR-error form is not a name, so
    it links to no alias, and the EntityMention validator rejects alias_id on any
    non-rule_match method. Widening this set (a careless sweep of every rule_match
    literal into one constant) would make the alias backfill-linking and
    alias-coverage-deletion queries target rows the model forbids — the two-set
    distinction this guard protects.
    """
    assert {DetectionMethod.RULE_MATCH} == ALIAS_LINKABLE_DETECTION_METHODS
    assert DetectionMethod.ASR_MATCH not in ALIAS_LINKABLE_DETECTION_METHODS
    # The two sets are distinct (overlap only on rule_match).
    assert SCAN_DETECTION_METHODS != ALIAS_LINKABLE_DETECTION_METHODS
    assert ALIAS_LINKABLE_DETECTION_METHODS < SCAN_DETECTION_METHODS


# Every association-MEMBERSHIP query reads the ONE shared qualification helper, so a
# mention counts on all surfaces or none (#262). This pins that count. NOTE:
# ``update_entity_counters`` is deliberately NOT in this set — it computes the
# detected-mention TALLY (visible-name OR asr_match, never a manual method arm), a
# different question from association membership; conflating the two is what the
# v0.122.0 counter bug was. Its behaviour is pinned by
# test_delete_removes_auto_keeps_manual_and_correction + the asr recovery gating
# test, not by this count.
# 8th site added by Feature 118: EntityMentionRepository._pair_qualifying_mentions, the one
# qualifying-mention CTE behind the passage panel (interval ends, highlights, farther-apart
# list). It reaches the shared predicate through ``positioned_transcript_mention_qualifies``.
# (Feature 114's co_occurrence_evidence was also a site until its endpoint was retired, #422.)
_EXPECTED_QUALIFICATION_CALL_SITES = 8
# The evidence panel reaches the shared predicate through
# ``positioned_transcript_mention_qualifies`` (the rule it shares with proximity), so
# it is counted there rather than as a direct call.
_EXPECTED_POSITIONED_SURFACES_IN_MODULE = 1


def test_all_association_surfaces_use_the_shared_qualification() -> None:
    """Exact-count guard: pin the number of surfaces that gate on the shared
    qualification predicate ``_mention_qualifies_as_association``.

    The #262 class of bug is a surface that counts a mention on a DIFFERENT rule
    than its peers. A shared constant pins "which names count"; it is blind to a
    surface added on a new axis (which detection methods count). An exact-count
    guard is not: adding an association-membership query that hand-rolls
    ``visible-name OR manual`` instead of calling the helper — or dropping an
    existing call — changes the count and fails here, forcing a conscious review
    that the new/removed site admits ``asr_match`` via the shared predicate.
    """
    source = Path(_mention_repo_module.__file__).read_text(encoding="utf-8")
    direct = source.count("_mention_qualifies_as_association(visible_names)")
    # Calls of the positioned rule in THIS module (its definition is excluded).
    positioned = source.count(
        "positioned_transcript_mention_qualifies("
    ) - source.count("def positioned_transcript_mention_qualifies(")
    assert positioned == _EXPECTED_POSITIONED_SURFACES_IN_MODULE
    # The positioned rule must itself delegate to the shared predicate, or the
    # surfaces counted through it would not admit asr_match.
    assert "_mention_qualifies_as_association(visible_names, mention)" in source
    call_sites = direct + positioned
    assert call_sites == _EXPECTED_QUALIFICATION_CALL_SITES, (
        f"expected {_EXPECTED_QUALIFICATION_CALL_SITES} association surfaces to call "
        f"the shared qualification helper, found {call_sites}. If you added or "
        f"removed an association-membership query, update this count AND confirm the "
        f"site admits asr_match via the shared predicate (not a hand-rolled "
        f"visible-name-only filter) — the surface-by-surface drift that reintroduces "
        f"the #262 bug."
    )
