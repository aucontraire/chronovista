"""Regression test: candidate seeding excludes categorically-untypeable relations.

This is a **regression test, not a contract guard**: it catches someone *deleting* the exclusion,
not someone adding a 36th `RELATIONS` property whose targets are also unfilable — that's a human
OntoNotes judgement ("does this relation's target have an EntityType slot?"), not a computable
predicate, and one occurrence does not earn the general mechanism (Rule of Three). If a third such
relation ever recurs, the computable form is an integration check that no seeded relation exceeds
~50% `other` — the empty middle of the observed bimodal split (every mapped relation <=1.5%, the
two culprits ~99%).
"""

from __future__ import annotations

from chronovista.services.candidate_suggestion_service import (
    _UNTYPEABLE_SEED_RELATIONS,
    _seed_relation_fields,
)
from chronovista.services.wikidata_properties import RELATIONS


def test_untypeable_relations_are_not_seeded() -> None:
    seeded = set(_seed_relation_fields())
    assert "award_received" not in seeded
    assert "position_held" not in seeded
    assert frozenset({"award_received", "position_held"}) == _UNTYPEABLE_SEED_RELATIONS


def test_fact_mining_still_covers_the_excluded_relations() -> None:
    # The fix narrows candidate SEEDING only — the excluded relations stay in RELATIONS so
    # backfill_entity_relations keeps mining them as facts ("person received X award").
    mined = set(RELATIONS.values())
    assert "award_received" in mined
    assert "position_held" in mined


def test_part_of_is_still_seeded() -> None:
    # part_of is deliberately NOT excluded: its targets are heterogeneous and P31-first types its
    # event targets (v0.110.0), so dropping it would lose real events.
    assert "part_of" in set(_seed_relation_fields())


def test_seed_is_exactly_the_mined_set_minus_the_denylist() -> None:
    assert (
        set(_seed_relation_fields())
        == set(RELATIONS.values()) - _UNTYPEABLE_SEED_RELATIONS
    )
