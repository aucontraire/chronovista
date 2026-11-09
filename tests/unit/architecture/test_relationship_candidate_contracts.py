"""Contract guards for the novel-relationship generator (Feature 107).

Mutation-verified fitness tests that fail if a *measured* decision silently drifts
out of the generator. Each guards a decision whose quiet reversal would change the
queue's precision — the exact failure this feature was built to avoid. See
specs/107 research (R2 no floor, R3 three-arm filter incl. headquarters) and the
gitignored notes 016/018.
"""

from __future__ import annotations

import uuid

import pytest

import chronovista.repositories.relationship_candidate_repository as repo_mod
from chronovista.db.models import RelationshipCandidate as RelationshipCandidateDB
from chronovista.services import relationship_candidate_service as svc
from chronovista.services.wikidata_properties import RELATIONS


def test_attribute_arm_is_exactly_country_pob_headquarters() -> None:
    # R3: the attribute arm of the novelty filter is the calibrated set. Dropping
    # headquarters (the org analogue of place_of_birth) or any member diverges the
    # filter from what the precision was measured against.
    assert set(svc.ATTR_FIELDS) == {"country", "place_of_birth", "headquarters"}


def test_direct_edge_arm_is_derived_from_relations_single_source() -> None:
    # R3 / single-source: the direct-edge arm must enumerate from RELATIONS, not a
    # hand-maintained subset, so newly-captured relations are covered automatically.
    assert frozenset(RELATIONS.values()) == svc._RELATION_FIELDS
    # A hand list would almost certainly be smaller than the full captured set.
    assert len(svc._RELATION_FIELDS) > 50


def test_no_support_floor_beyond_the_qualifying_minimum() -> None:
    # R2: the qualifying support minimum is exactly 5 and the lift minimum exactly 5.
    # A higher support floor would delete the measured highest-precision cell
    # (support 5-6, high lift ~93.8% real). This guard fails if either drifts up.
    assert svc.SUPPORT_MIN == 5
    assert svc.LIFT_MIN == 5.0


def test_no_support_floor_keeps_a_minimum_support_high_lift_pair() -> None:
    # Behavioural companion to the constant guard: two rare entities sharing exactly
    # 5 videos out of a large universe produce a very high lift and MUST survive.
    a_id, b_id = sorted((uuid.uuid4(), uuid.uuid4()))
    entity_rows = [
        (a_id, {}, {}),
        (b_id, {}, {}),
    ]
    # e_a and e_b co-occur in exactly 5 videos; 95 filler single-entity videos make
    # N = 100 so lift = 5 * 100 / (5 * 5) = 20 (>= 5), support = 5 (the floor).
    filler = uuid.uuid4()
    entity_rows.append((filler, {}, {}))
    mention_rows: list[tuple[uuid.UUID, str]] = []
    for i in range(5):
        mention_rows.append((a_id, f"v{i}"))
        mention_rows.append((b_id, f"v{i}"))
    for i in range(5, 100):
        mention_rows.append((filler, f"v{i}"))

    candidates, universe = svc.compute_candidates(
        mention_rows=mention_rows, entity_rows=entity_rows, run_id=uuid.uuid4()
    )
    assert universe == 100
    pair = [c for c in candidates if {c.entity_a_id, c.entity_b_id} == {a_id, b_id}]
    assert len(pair) == 1
    assert pair[0].shared_video_count == 5
    assert pair[0].lift == 20.0


def test_corroboration_field_set_and_exclusion_mechanism() -> None:
    # Mutation-verified contract guard (Constitution v1.4.0): asserts the EFFECT of the
    # exclusion mechanism, not a constant's contents. The prior pin
    # (`{"P5008","P1343"} <= CORROBORATION_EXCLUDE`) passed under four broken
    # constructions (NOTE 018 §18-§21); this fails under every one of them.
    universe = frozenset(RELATIONS.values()) | frozenset(svc.ATTR_FIELDS)

    # Universe = the documented 106-of-118 captured field names. The exact count is a
    # deliberate-review pin: changing RELATIONS/ATTR_FIELDS changes what counts as
    # corroboration and MUST be a conscious update here. (106/118 since P1327
    # "professional_partner" was added to RELATIONS, 2026-11-08.)
    assert universe == svc._CORROBORATION_FIELDS
    assert len(svc._CORROBORATION_FIELDS) == 106
    # Node attributes are omitted by construction (co-classification, not a relation).
    assert "instance_of" not in svc._CORROBORATION_FIELDS
    # Ships empty: nothing is excluded today.
    assert frozenset() == svc.CORROBORATION_EXCLUDE_FIELDS

    # The mechanism is LIVE despite shipping empty — two mutations prove reachability.
    # Single-source field:
    excl_employer = svc._compute_corroboration_fields(frozenset({"employer"}))
    assert len(excl_employer) == 105 and "employer" not in excl_employer
    # Multi-source field (country <- P17 + P27): the case a P-number-space exclusion
    # silently fails (P27 keeps producing `country`). Only a field-name-space exclusion
    # removes it — this assertion is what distinguishes the correct construction.
    excl_country = svc._compute_corroboration_fields(frozenset({"country"}))
    assert len(excl_country) == 105 and "country" not in excl_country
    # Non-resolution raises, never silently no-ops.
    with pytest.raises(ValueError):
        svc._compute_corroboration_fields(frozenset({"not_a_captured_field"}))


def test_head_ordering_ends_in_regen_stable_id() -> None:
    # SC-003a / §22 CONTRACT GUARD: the head ordering MUST end in the regen-stable `id`
    # tiebreak, or the boundary flickers when lift AND corroboration tie. A DB-order test
    # cannot catch a dropped tiebreak (verified during adversarial validation: Postgres
    # returned id order by chance), so the ordering is a single named tuple and this guard
    # asserts its shape structurally — it fails if the terminal id key is dropped.
    order = repo_mod._HEAD_ORDER_BY
    assert len(order) == 4  # lift, corroboration, shared_video_count, id
    assert order[-1] is RelationshipCandidateDB.id  # terminal regen-stable tiebreak
    # corroboration is the secondary key (immediately after lift).
    assert "kb_corroboration_count" in str(order[1])
    assert "lift" in str(order[0])


def test_inbound_holder_arm_field_set_is_pinned() -> None:
    # The 4th (inbound-holder) arm reads person-targeted holder fields. The set is a
    # deliberate-review calibration (measured 2026-11-09: cast_member dominates 52/64 head
    # removals; the "ambiguous" leadership/board fields contribute zero; person-held org<->org
    # fields excluded for cross-field type-coherence). A silent edit changes what the queue
    # treats as 2-hop-derivable, so pin it like the attribute arm.
    expected = frozenset(
        {
            "cast_member",
            "director",
            "producer",
            "screenwriter",
            "composer",
            "executive_producer",
            "director_of_photography",
            "film_editor",
            "film_crew_member",
            "creator",
            "author",
            "narrator",
            "presenter",
            "founder",
            "significant_person",
            "participant",
            "perpetrator",
            "signatory",
        }
    )
    assert expected == svc._INBOUND_HELD_FIELDS
    # Invariants that outlive the exact membership: every inbound-held field must be a real
    # RELATIONS field (a typo would silently remove nothing), and NONE may be a person-held
    # tie field (that would make the cross-field union type-incoherent / org<->org).
    relation_fields = frozenset(RELATIONS.values())
    assert relation_fields >= svc._INBOUND_HELD_FIELDS
    assert svc._INBOUND_HELD_FIELDS.isdisjoint(set(svc.TIE_FIELDS))


def test_inbound_holder_arm_removes_a_coheld_pair() -> None:
    # Two entities co-occur strongly with NO typed tie between them -> normally a candidate.
    # But a third entity (a work) names BOTH via cast_member, so the pair is 2-hop-derivable
    # and the inbound-holder arm MUST remove it. No other arm catches (a,b): the direct-edge
    # arm records (work,a)/(work,b), not (a,b); a and b share no tie/attr referent.
    a_id, b_id = sorted((uuid.uuid4(), uuid.uuid4()))
    work_id = uuid.uuid4()
    filler = uuid.uuid4()
    qa, qb = "Q900001", "Q900002"  # synthetic QIDs (not library content)
    entity_rows = [
        (a_id, {"wikidata": {"id": qa}}, {}),
        (b_id, {"wikidata": {"id": qb}}, {}),
        (work_id, {"wikidata": {"id": "Q900003"}}, {"cast_member": {"qids": [qa, qb]}}),
        (filler, {}, {}),
    ]
    # a and b co-occur in 5 of 100 videos -> high lift, clears support/lift floors.
    mention_rows: list[tuple[uuid.UUID, str]] = []
    for i in range(5):
        mention_rows.append((a_id, f"v{i}"))
        mention_rows.append((b_id, f"v{i}"))
    for i in range(5, 100):
        mention_rows.append((filler, f"v{i}"))

    candidates, universe = svc.compute_candidates(
        mention_rows=mention_rows, entity_rows=entity_rows, run_id=uuid.uuid4()
    )
    assert universe == 100
    assert not [
        c for c in candidates if {c.entity_a_id, c.entity_b_id} == {a_id, b_id}
    ], "inbound-holder arm should remove the co-cast pair"
