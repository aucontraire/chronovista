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
    INSTANCE_OF_BY_TYPE,
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

    @pytest.mark.parametrize(
        "qid,expected",
        [
            ("Q47913", "organization"),  # intelligence agency
            ("Q35657", "place"),  # U.S. state
            ("Q5398426", "work"),  # television series
            ("Q12909644", "concept"),  # political ideology
            ("Q934744", "event"),  # political scandal
        ],
    )
    def test_feature_099_classes_suggested(self, qid: str, expected: str) -> None:
        # US2 forward path: a newly-recognized class now yields a confident suggestion for the
        # create-entity modal / candidate generation, where before it was undeterminable (None).
        assert suggest_entity_type([qid]) == expected


class TestExpectedInstanceOfDriftGuard:
    """Re-export integrity (invariant #3, revised by Feature 099): the corroboration view covers
    person/place/organization only — NO new corroborating TYPES — and for those three types its
    expected QID sets TRACK the classification table (they grow in sync with Feature 099+ so the
    create-modal suggestion and the "type may differ" badge can never disagree, FR-007 as revised).
    Guards against (a) a new corroborating type sneaking in, and (b) corroboration drifting out of
    step with classification for the three types.
    """

    def test_keys_are_only_the_three_corroboration_types(self) -> None:
        assert set(EXPECTED_INSTANCE_OF) == {"person", "place", "organization"}

    def test_tracks_classification_for_corroboration_types(self) -> None:
        # Each corroborating type's expected set equals that type's classification anchors, so the
        # suggestion (from classify) and the badge (from corroboration) cannot disagree.
        assert EXPECTED_INSTANCE_OF["person"] == set(
            INSTANCE_OF_BY_TYPE[EntityType.PERSON]
        )
        assert EXPECTED_INSTANCE_OF["place"] == set(
            INSTANCE_OF_BY_TYPE[EntityType.PLACE]
        )
        assert EXPECTED_INSTANCE_OF["organization"] == set(
            INSTANCE_OF_BY_TYPE[EntityType.ORGANIZATION]
        )


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


class TestClassifyFeature099Classes:
    """FR-001 / FR-012: the Feature 099 anchor additions classify to their intended type."""

    @pytest.mark.parametrize(
        "qid,expected",
        [
            # place
            ("Q35657", EntityType.PLACE),  # U.S. state
            ("Q15149663", EntityType.PLACE),  # state of Mexico
            ("Q1549591", EntityType.PLACE),  # big city
            # organization
            ("Q7210356", EntityType.ORGANIZATION),  # political organization
            ("Q47913", EntityType.ORGANIZATION),  # intelligence agency
            ("Q17127659", EntityType.ORGANIZATION),  # terrorist organization
            ("Q207320", EntityType.ORGANIZATION),  # paramilitary organization
            ("Q17149090", EntityType.ORGANIZATION),  # armed organization
            ("Q20858006", EntityType.ORGANIZATION),  # federal law enforcement agency
            ("Q910252", EntityType.ORGANIZATION),  # federal executive department
            ("Q62078547", EntityType.ORGANIZATION),  # public research university
            ("Q902104", EntityType.ORGANIZATION),  # private university
            ("Q15936437", EntityType.ORGANIZATION),  # research university
            ("Q1188663", EntityType.ORGANIZATION),  # colonial college
            (
                "Q23002054",
                EntityType.ORGANIZATION,
            ),  # private not-for-profit educational institution
            ("Q11032", EntityType.ORGANIZATION),  # newspaper
            ("Q1110794", EntityType.ORGANIZATION),  # daily newspaper
            ("Q1153191", EntityType.ORGANIZATION),  # online newspaper
            ("Q35127", EntityType.ORGANIZATION),  # website
            ("Q561068", EntityType.ORGANIZATION),  # specialty channel
            # work
            ("Q5398426", EntityType.WORK),  # television series
            # concept
            ("Q12909644", EntityType.CONCEPT),  # political ideology
            ("Q49773", EntityType.CONCEPT),  # social movement
            ("Q2738074", EntityType.CONCEPT),  # political movement
            # event
            ("Q934744", EntityType.EVENT),  # political scandal
        ],
    )
    def test_new_class_classifies(self, qid: str, expected: EntityType) -> None:
        assert classify_entity_type([qid]) == expected


class TestClassifyFeature099Precedence:
    """FR-003: a new place/work class co-occurring with a new org class resolves by the fixed
    precedence (organization > place > ... > work), order-independently."""

    def test_new_org_outranks_new_place(self) -> None:
        assert classify_entity_type(["Q35657", "Q47913"]) == EntityType.ORGANIZATION
        assert classify_entity_type(["Q47913", "Q35657"]) == EntityType.ORGANIZATION

    def test_new_org_outranks_new_work(self) -> None:
        assert classify_entity_type(["Q5398426", "Q11032"]) == EntityType.ORGANIZATION


class TestCorroborationNotWidenedFeature099:
    """FR-007 (#271-safe): extending classification MUST NOT widen corroboration. An entity of a
    work/concept/event class corroborates as neutral (None), never True/False."""

    @pytest.mark.parametrize(
        "entity_type,qid",
        [
            ("work", "Q5398426"),  # television series
            ("concept", "Q12909644"),  # political ideology
            ("event", "Q934744"),  # political scandal
        ],
    )
    def test_non_corroboration_types_stay_neutral(
        self, entity_type: str, qid: str
    ) -> None:
        assert type_corroboration(entity_type, [qid]) is None

    def test_new_place_class_corroborates_place(self) -> None:
        # Suggestion↔badge agreement (FR-007 revised): a U.S. state suggests AND corroborates place.
        assert suggest_entity_type(["Q35657"]) == "place"
        assert type_corroboration("place", ["Q35657"]) is True

    def test_new_org_class_corroborates_org(self) -> None:
        assert suggest_entity_type(["Q47913"]) == "organization"
        assert type_corroboration("organization", ["Q47913"]) is True


class TestExtensionZeroRegression:
    """SC-003: the Feature 099 extension must not change any already-determinate classification.

    Full-population validation (all 1,931 grounded entities, 0 regressions) is recorded in
    research.md Phase-0. These unit guards pin the two mechanisms a careless future edit could
    break it by: (1) a frozen set of pre-existing determinate results must stay unchanged;
    (2) no QID may be assigned to more than one type (which precedence would then resolve silently).
    """

    @pytest.mark.parametrize(
        "instance_of,expected",
        [
            (["Q5"], EntityType.PERSON),  # human
            (["Q6256"], EntityType.PLACE),  # country
            (["Q43229"], EntityType.ORGANIZATION),  # organization
            (["Q1656682"], EntityType.EVENT),  # event
            (["Q11424"], EntityType.WORK),  # film
            (["Q151885"], EntityType.CONCEPT),  # concept
            (
                ["Q11424", "Q6256"],
                EntityType.PLACE,
            ),  # work+place -> place (place > work)
            (["Q43229", "Q5"], EntityType.PERSON),  # org+person -> person
        ],
    )
    def test_preexisting_determinate_unchanged(
        self, instance_of: list[str], expected: EntityType
    ) -> None:
        assert classify_entity_type(instance_of) == expected

    def test_no_qid_assigned_to_two_types(self) -> None:
        seen: dict[str, EntityType] = {}
        for etype, qids in INSTANCE_OF_BY_TYPE.items():
            for q in qids:
                assert q not in seen, f"{q} assigned to both {seen.get(q)} and {etype}"
                seen[q] = etype
