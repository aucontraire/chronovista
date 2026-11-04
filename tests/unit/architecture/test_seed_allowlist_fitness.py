"""Fitness guards for the candidate seed ALLOWLIST (Feature 105, ADR 014).

Seeding was flipped from an opt-out denylist (``RELATIONS − {award_received, position_held}``) to
an explicit ``SEED_ALLOWLIST``. Because the candidate upsert refreshes pending rows only and never
deletes, a relation that silently drops out of the allowlist would strand its existing candidates,
un-refreshed and indistinguishable from live ones — a permanent risk, not a one-time migration
concern. These two guards are therefore **permanent** and **mutation-verified**:

- Guard A (baseline-containment): the relations that seeded at the moment of the flip MUST all
  remain in ``SEED_ALLOWLIST``. Written as containment (not equality) so it survives future
  seed-promotions (US2+ append new relations) while still catching a silent drop-out.
- Guard B (subset + single source): ``SEED_ALLOWLIST`` MUST be a subset of the captured relations
  (``<=``, not strict — "every mined relation seeds" is a legitimate state, not a ceiling), and no
  competing denylist source may govern seeding.

Neither guard reads any gitignored tree. Mutation-verify (recorded, per Constitution v1.3.0):
- Guard A: remove any ``_BASELINE`` member from ``SEED_ALLOWLIST`` → RED (and the assertion message
  names the missing relation); restore → green.
- Guard B: add a non-member string to ``SEED_ALLOWLIST`` → RED; re-introduce a module-level
  ``_UNTYPEABLE_SEED_RELATIONS`` that governs ``_seed_relation_fields`` → the "single source" test
  RED.
"""

from __future__ import annotations

from chronovista.services import candidate_suggestion_service as css
from chronovista.services.candidate_suggestion_service import (
    SEED_ALLOWLIST,
    _seed_relation_fields,
)
from chronovista.services.wikidata_properties import RELATIONS

# The relations that seeded at the opt-out→allowlist flip: every RELATIONS value then present
# except the two categorically-untypeable ones. Frozen here as the committed baseline — this is a
# snapshot, deliberately independent of the current RELATIONS so a later removal is caught.
_BASELINE: frozenset[str] = frozenset(
    {
        "employer",
        "educated_at",
        "member_of",
        "place_of_birth",
        "place_of_death",
        "father",
        "mother",
        "spouse",
        "child",
        "sibling",
        "political_party",
        "part_of",
        "subclass_of",
        "founder",
        "cast_member",
        "director",
        "producer",
        "screenwriter",
        "composer",
        "significant_person",
        "unmarried_partner",
        "field_of_work",
        "notable_work",
        "participant_in",
        "parent_organization",
        "child_organization",
        "owned_by",
        "chairperson",
        "ceo",
        "affiliation",
        "creator",
        "production_company",
        "original_broadcaster",
    }
)


def test_guard_a_baseline_relations_still_seed() -> None:
    """Every relation that seeded at the flip is still on the allowlist (containment)."""
    missing = _BASELINE - SEED_ALLOWLIST
    assert (
        not missing
    ), f"baseline seed relations silently dropped from SEED_ALLOWLIST: {sorted(missing)}"


def test_guard_b_allowlist_is_subset_of_captured_relations() -> None:
    """Every allowlisted relation is a real captured RELATIONS value (``<=``, not strict)."""
    unknown = SEED_ALLOWLIST - set(RELATIONS.values())
    assert (
        not unknown
    ), f"SEED_ALLOWLIST names relations absent from RELATIONS: {sorted(unknown)}"


def test_guard_b_allowlist_is_the_single_seeding_source() -> None:
    """Seeding derives from the allowlist alone — no competing denylist source remains."""
    assert set(_seed_relation_fields()) == set(SEED_ALLOWLIST)
    assert not hasattr(css, "_UNTYPEABLE_SEED_RELATIONS"), (
        "a denylist constant reappeared in the seeding module; seeding must be governed by "
        "SEED_ALLOWLIST alone (Feature 105)"
    )
