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

from chronovista.models.enums import DetectionMethod
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
