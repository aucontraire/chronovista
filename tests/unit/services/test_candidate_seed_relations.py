"""Regression test: candidate seeding is governed by an explicit allowlist (Feature 105).

Feature 105 flipped seeding from an opt-out denylist (``RELATIONS − {award_received, position_held}``)
to an explicit ``SEED_ALLOWLIST``. The original intent still holds and is pinned here: the
categorically-untypeable relations never seed, ``part_of`` still does, and fact-mining
(``RELATIONS``) continues to cover everything regardless of seeding. The structural invariants of
the allowlist itself (baseline-containment, subset, no competing denylist) are enforced separately
by the mutation-verified guards in ``tests/unit/architecture/test_seed_allowlist_fitness.py``.
"""

from __future__ import annotations

from chronovista.services.candidate_suggestion_service import (
    SEED_ALLOWLIST,
    _seed_relation_fields,
)
from chronovista.services.wikidata_properties import RELATIONS


def test_untypeable_relations_are_not_seeded() -> None:
    seeded = set(_seed_relation_fields())
    assert "award_received" not in seeded
    assert "position_held" not in seeded


def test_seed_relation_fields_is_exactly_the_allowlist() -> None:
    assert set(_seed_relation_fields()) == set(SEED_ALLOWLIST)


def test_fact_mining_still_covers_the_untypeable_relations() -> None:
    # Seeding is decoupled from capture — the untypeable relations stay in RELATIONS so
    # backfill_entity_relations keeps mining them as facts ("person received X award").
    mined = set(RELATIONS.values())
    assert "award_received" in mined
    assert "position_held" in mined


def test_part_of_is_still_seeded() -> None:
    # part_of is deliberately on the allowlist: its targets are heterogeneous and P31-first types
    # its event targets (v0.110.0), so dropping it would lose real events.
    assert "part_of" in set(_seed_relation_fields())


def test_feature_105_seed_now_set_is_seeded() -> None:
    # The cheap high-signal "seed-now" edges (US2) seed candidates.
    seeded = set(_seed_relation_fields())
    for field in (
        "funder",
        "practiced_by",
        "perpetrator",
        "participant",
        "executive_producer",
    ):
        assert field in seeded, field


def test_feature_105_held_edges_are_captured_but_not_seeded() -> None:
    # The expensive / held edges and place-institution edges are CAPTURED (in RELATIONS) but NOT on
    # the allowlist, so they never mint candidates (capture != seed).
    seeded = set(_seed_relation_fields())
    captured = set(RELATIONS.values())
    for field in (
        "relative",
        "influenced_by",
        "has_part",
        "named_after",
        "significant_event",
        "head_of_government",
        "work_location",
    ):
        assert field in captured, f"{field} should be captured"
        assert field not in seeded, f"{field} is held — must not seed"
