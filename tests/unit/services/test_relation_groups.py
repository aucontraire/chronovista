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


def test_credit_groups_present_with_their_fields() -> None:
    # Feature 088 — one group per credit kind, each over its single WANTED field.
    expected = {
        "cast_of": "cast_member",
        "directed": "director",
        "produced": "producer",
        "wrote": "screenwriter",
        "scored": "composer",
    }
    for key, field in expected.items():
        assert _group(key).member_fields == (field,), key
        assert field in INBOUND_FIELDS


def test_credit_labels_are_inverse_directional_not_forward() -> None:
    # The field is stored on the WORK; the label describes the work relative to the viewed person
    # (X-centric, "… by this entity" / "in its cast"), never the forward word that would read as if
    # the work were the director/cast-member (the 087 directional trap).
    credit_keys = {"cast_of", "directed", "produced", "wrote", "scored"}
    labels = {g.label for g in RELATION_GROUPS if g.key in credit_keys}
    # no forward-worded credit label leaks onto the inverse surface
    forward_words = (
        "Director of",
        "Producer of",
        "Writer of",
        "Screenwriter of",
        "Cast member of",
    )
    for fw in forward_words:
        assert not any(fw in lab for lab in labels), fw
    # each credit label frames the work as the subject ("by this entity" or "in its cast")
    for lab in labels:
        assert ("by this entity" in lab) or ("in its cast" in lab), lab


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


def test_feature_095_inverse_groups_present() -> None:
    # Each new relationship edge has an inverse ("Referenced by") group over its single field.
    expected = {
        "award_recipient": "award_received",
        "noted_work": "notable_work",
        "event_participant": "participant_in",
        "child_org": "parent_organization",
        "parent_org": "child_organization",
        "owned_entity": "owned_by",
        "chaired_org": "chairperson",
        "led_org": "ceo",
        "affiliated_entity": "affiliation",
        "created_work": "creator",
        "produced_work": "production_company",
        "broadcast_work": "original_broadcaster",
    }
    for key, field in expected.items():
        assert _group(key).member_fields == (field,), key
        assert field in INBOUND_FIELDS


def test_owned_by_has_inverse_group_but_owner_of_is_absent() -> None:
    # Feature 095 Q3: the owner side is the INVERSE of owned_by; owner_of is never captured.
    assert "owned_by" in INBOUND_FIELDS
    assert "owner_of" not in INBOUND_FIELDS
    assert "owner_of" not in WANTED.values()


def test_feature_095_attributes_excluded_from_relation_groups() -> None:
    # The 8 new node attributes are NOT relationships — they must never enter the inverse surface.
    for attr in (
        "religion_or_worldview",
        "residence",
        "ethnic_group",
        "legal_form",
        "industry",
        "political_ideology",
        "political_alignment",
        "head_position",
    ):
        assert attr not in INBOUND_FIELDS
