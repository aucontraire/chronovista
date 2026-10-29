"""Unit tests for the shared Wikidata type classifier (Feature 098).

Covers classification (mapping, precedence, catch-all, order-independent determinism) and the
corroboration view, including the decoupling that keeps #271 from regressing as classification
coverage grows.
"""

from __future__ import annotations

import pytest

from chronovista.models.enums import EntityType
from chronovista.services.wikidata_client import (
    EXPECTED_INSTANCE_OF,
    WikidataClient,
    _type_verification,
)
from chronovista.services.wikidata_taxonomy import (
    classify_entity_type,
    suggest_entity_type,
    type_corroboration,
)


class TestClassifySingleType:
    @pytest.mark.parametrize(
        ("instance_of", "expected"),
        [
            (["Q5"], EntityType.PERSON),  # human
            (["Q6256"], EntityType.PLACE),  # country
            (["Q3624078"], EntityType.PLACE),  # sovereign state
            (["Q515"], EntityType.PLACE),  # city
            (["Q43229"], EntityType.ORGANIZATION),  # organization
            (["Q1656682"], EntityType.EVENT),  # event
            (["Q11424"], EntityType.WORK),  # film
            (["Q151885"], EntityType.CONCEPT),  # concept
        ],
    )
    def test_single_anchor_maps_to_type(
        self, instance_of: list[str], expected: EntityType
    ) -> None:
        assert classify_entity_type(instance_of) == expected


class TestClassifyCatchAll:
    def test_empty_is_other(self) -> None:
        assert classify_entity_type([]) == EntityType.OTHER

    def test_unknown_qid_is_other(self) -> None:
        assert classify_entity_type(["Q999999999"]) == EntityType.OTHER

    def test_mixed_unknown_and_known_uses_known(self) -> None:
        assert classify_entity_type(["Q999999999", "Q5"]) == EntityType.PERSON


class TestClassifyPrecedence:
    @pytest.mark.parametrize(
        ("instance_of", "expected"),
        [
            (["Q5", "Q43229"], EntityType.PERSON),  # person beats organization
            (["Q43229", "Q6256"], EntityType.ORGANIZATION),  # org beats place
            (["Q6256", "Q1656682"], EntityType.PLACE),  # place beats event
            (["Q1656682", "Q11424"], EntityType.EVENT),  # event beats work
        ],
    )
    def test_highest_precedence_wins(
        self, instance_of: list[str], expected: EntityType
    ) -> None:
        assert classify_entity_type(instance_of) == expected


class TestClassifyDeterminism:
    def test_order_independent(self) -> None:
        assert classify_entity_type(["Q5", "Q6256"]) == classify_entity_type(
            ["Q6256", "Q5"]
        )

    def test_order_independent_resolves_by_precedence_not_order(self) -> None:
        # Organization listed first, but place/person precedence must still decide.
        assert classify_entity_type(["Q43229", "Q5"]) == EntityType.PERSON
        assert classify_entity_type(["Q5", "Q43229"]) == EntityType.PERSON

    def test_repeated_calls_stable(self) -> None:
        first = classify_entity_type(["Q11424", "Q6256"])
        assert first == classify_entity_type(["Q11424", "Q6256"]) == EntityType.PLACE


class TestCorroboration:
    @pytest.mark.parametrize(
        ("entity_type", "instance_of", "expected"),
        [
            ("person", ["Q5"], True),
            (
                "person",
                ["Q6256"],
                False,
            ),  # has an expected set, does not match → may differ
            (
                "person",
                [],
                False,
            ),  # unchanged legacy behavior (expected set, empty P31)
            ("place", ["Q6256"], True),
            ("organization", ["Q43229"], True),
        ],
    )
    def test_reliable_types_are_tri_state(
        self, entity_type: str, instance_of: list[str], expected: bool
    ) -> None:
        assert type_corroboration(entity_type, instance_of) is expected

    @pytest.mark.parametrize(
        "entity_type", ["event", "work", "concept", "technical_term"]
    )
    def test_non_corroboration_types_are_neutral(self, entity_type: str) -> None:
        # Even though classification KNOWS these anchors, corroboration stays neutral (None),
        # never "may differ" — this is what keeps the create badge from regressing #271.
        assert type_corroboration(entity_type, ["Q1656682"]) is None


class TestCorroborationDecoupledFromClassification:
    def test_event_classifies_but_does_not_corroborate(self) -> None:
        # The crux of Feature 098: classification widened to cover event, but corroboration
        # for event remains neutral so sparsely-anchored types cannot flash "type may differ".
        assert classify_entity_type(["Q1656682"]) == EntityType.EVENT
        assert type_corroboration("event", ["Q1656682"]) is None


class TestTypeVerificationDelegates:
    """T007 — the create-time corroboration (_type_verification) is unchanged after re-pointing."""

    def test_person_true(self) -> None:
        assert _type_verification("person", ["Q5"]) is True

    def test_person_false(self) -> None:
        assert _type_verification("person", ["Q6256"]) is False

    def test_event_neutral(self) -> None:
        assert _type_verification("event", ["Q1656682"]) is None


class TestSuggestEntityType:
    """Create-modal suggestion (FR-008 / Q2): a confident type string, or None (unset) for OTHER."""

    def test_person_suggested(self) -> None:
        assert suggest_entity_type(["Q5"]) == "person"

    def test_place_suggested(self) -> None:
        assert suggest_entity_type(["Q6256"]) == "place"

    def test_empty_is_none_not_other(self) -> None:
        # Undeterminable → None (modal leaves selector unset), never the string "other".
        assert suggest_entity_type([]) is None

    def test_unmapped_is_none_not_other(self) -> None:
        assert suggest_entity_type(["Q999999999"]) is None


class TestExpectedInstanceOfDriftGuard:
    """Re-export integrity (invariant #3): the corroboration view is person/place/organization
    only, with the exact legacy QID sets. Guards against silent drift when the table grows.
    """

    def test_keys_are_only_the_three_corroboration_types(self) -> None:
        assert set(EXPECTED_INSTANCE_OF) == {"person", "place", "organization"}

    def test_exact_qid_sets_unchanged(self) -> None:
        assert EXPECTED_INSTANCE_OF["person"] == {"Q5"}
        assert EXPECTED_INSTANCE_OF["place"] == {
            "Q6256",
            "Q3624078",
            "Q515",
            "Q15284",
            "Q7275",
            "Q82794",
            "Q23442",
        }
        assert EXPECTED_INSTANCE_OF["organization"] == {
            "Q4830453",
            "Q43229",
            "Q783794",
            "Q7278",
            "Q1616075",
            "Q11033",
            "Q163740",
            "Q3918",
            "Q1002697",
        }


class TestFetchInstanceOf:
    """Public batch wrapper (invariant #5): empty-input shortcut and dict-shaping/omission."""

    @pytest.mark.asyncio
    async def test_empty_input_returns_empty_without_fetch(self) -> None:
        assert await WikidataClient().fetch_instance_of([]) == {}

    @pytest.mark.asyncio
    async def test_shapes_and_omits_unknown(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = WikidataClient()

        async def _fake_item_details(http: object, qids: list[str]) -> dict[str, dict]:
            # Q-unknown deliberately absent → must be omitted from the result.
            return {
                "Q5": {"instance_of": ["Q5"]},
                "Q6256": {"instance_of": ["Q6256", "Q3624078"]},
            }

        monkeypatch.setattr(client, "_item_details", _fake_item_details)
        result = await client.fetch_instance_of(["Q5", "Q6256", "Q-unknown"])
        assert result == {"Q5": ["Q5"], "Q6256": ["Q6256", "Q3624078"]}
