"""Unit tests for the canonical relation grouping (Feature 087)."""

from __future__ import annotations

from chronovista.services.relation_groups import (
    INBOUND_FIELDS,
    RELATION_GROUPS,
)
from chronovista.services.wikidata_properties import WANTED


def _group(key: str):
    return next(g for g in RELATION_GROUPS if g.key == key)


def test_membership_unions_synonymous_fields() -> None:
    # The 19-not-2 trap: membership MUST union member_of + part_of, not key one field.
    assert set(_group("membership").member_fields) == {"member_of", "part_of"}


def test_family_groups_are_inverse_correct() -> None:
    # INVERSE semantics: an entity whose father/mother names the viewed one is its CHILD; an entity
    # whose child names it is its PARENT. (Keying 'father' as "Father" on the reverse surface would
    # caption the viewed entity's children as its father — the FR-004 directional harm.)
    children = _group("children")
    assert set(children.member_fields) == {"father", "mother"}
    assert children.label == "Child"
    parents = _group("parents")
    assert set(parents.member_fields) == {"child"}
    assert parents.label == "Parent"
    # founder inverts to "founded by this entity"; significant_person to "has this entity as …".
    assert _group("founded").member_fields == ("founder",)
    assert "founded" in _group("founded").attribution.lower()
    # no forward-worded family labels leak onto the inverse surface
    labels = {g.label for g in RELATION_GROUPS}
    assert "Father" not in labels and "Mother" not in labels and "Founder" not in labels


def test_every_inbound_field_is_a_wanted_alias() -> None:
    aliases = set(WANTED.values())
    assert set(INBOUND_FIELDS) <= aliases, set(INBOUND_FIELDS) - aliases


def test_founder_is_captured() -> None:
    # Feature 087 added P112 -> founder to the curated set.
    assert "founder" in WANTED.values()
    assert "founder" in INBOUND_FIELDS


def test_attribute_hub_fields_excluded() -> None:
    # country/place fields are the largest supply but weakest signal — excluded by design.
    for excluded in (
        "country",
        "place_of_birth",
        "place_of_death",
        "instance_of",
        "occupation",
    ):
        assert excluded not in INBOUND_FIELDS


def test_every_group_is_specifically_attributed() -> None:
    # No generic "related to"/"connected with"; each group names its relationship + attributes it.
    for g in RELATION_GROUPS:
        low = f"{g.label} {g.attribution}".lower()
        assert "wikidata" in g.attribution.lower()
        assert "related to" not in low and "connected with" not in low
