"""Contract guards for the novel-relationship generator (Feature 107).

Mutation-verified fitness tests that fail if a *measured* decision silently drifts
out of the generator. Each guards a decision whose quiet reversal would change the
queue's precision — the exact failure this feature was built to avoid. See
specs/107 research (R2 no floor, R3 three-arm filter incl. headquarters) and the
gitignored notes 016/018.
"""

from __future__ import annotations

import uuid

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


def test_corroboration_exclusions_are_pinned() -> None:
    # Forward-defensive pin (NOT a live filter): P5008/P1343 are issue-10 live-probe
    # negatives and are not in the captured RELATIONS set, so excluding them in the
    # captured-property corroboration is currently a no-op. The guard pins the
    # constant so any change to it is a deliberate, reviewed decision.
    assert {"P5008", "P1343"} <= svc.CORROBORATION_EXCLUDE
