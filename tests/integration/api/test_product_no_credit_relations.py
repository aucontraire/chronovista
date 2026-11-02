"""Credit relation groups are gated on the Wikidata property, never on entity_type
(Feature 103, FR-007 / SC-003 / research Decision 9).

This is the backend half of the SC-003 proof: it pins the *definition* — the credit relation
groups (cast/director/producer/screenwriter/composer) are keyed solely on their Wikidata property
member fields, so nothing can offer a credit affordance on the basis of ``entity_type``.

The *behavioral* forward-affordance proof — a ``product`` with no credit properties renders no
credit group, while a ``work`` that HAS one does — lives on the surface where relations are
actually offered: the frontend test
``frontend/src/components/entity/__tests__/EntityEnrichmentSection.test.tsx``. (The backend
``referenced-by`` endpoint is the *reverse* relation and requires a Wikidata QID, so it is not the
surface FR-007's "offered" refers to.)
"""

from __future__ import annotations

from chronovista.services.relation_groups import RELATION_GROUPS

_CREDIT_KEYS = {"cast_of", "directed", "produced", "wrote", "scored"}
_CREDIT_FIELDS = {"cast_member", "director", "producer", "screenwriter", "composer"}


def test_credit_groups_are_property_gated_not_type_gated() -> None:
    groups_by_key = {g.key: g for g in RELATION_GROUPS}
    for key in _CREDIT_KEYS:
        assert key in groups_by_key, f"missing credit group {key}"
        group = groups_by_key[key]
        # Gated on credit property member fields only — never on entity_type.
        assert (
            set(group.member_fields) <= _CREDIT_FIELDS
        ), f"{key} member_fields {group.member_fields} are not credit properties"
        assert not hasattr(
            group, "entity_type"
        ), f"{key} must not gate on entity_type (property-driven only)"
