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
    classify_if_determinate,
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
            (["Q198"], EntityType.EVENT),  # war
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


class TestOrganizationDemotionFixClasses:
    """Classes that previously classified to OTHER and so were demoted from the heuristic's
    'organization' guess at approval. All now map to ORGANIZATION, which is both what lets the
    repair re-type the affected entities and what keeps them inside corroboration coverage.
    (Platform/software/app classes are NOT here — they now live in
    INSTANCE_OF_BY_TYPE[PRODUCT], Feature 103.)
    """

    @pytest.mark.parametrize(
        "qid",
        [
            "Q484652",  # international organization
            "Q1127126",  # military alliance
            "Q124964",  # coalition
            "Q52110228",  # geopolitical group
            "Q4120211",  # regional organization
            "Q120121699",  # political economic union
            "Q170156",  # confederation
            "Q155271",  # think tank
            "Q31855",  # research institute
            "Q875538",  # public university
            "Q45400320",  # open-access publisher
            "Q5741069",  # rock band
        ],
    )
    def test_class_maps_to_organization(self, qid: str) -> None:
        assert classify_entity_type([qid]) == EntityType.ORGANIZATION
        assert suggest_entity_type([qid]) == "organization"


class TestClassifyPrecedence:
    @pytest.mark.parametrize(
        ("instance_of", "expected"),
        [
            (["Q5", "Q43229"], EntityType.PERSON),  # person beats organization
            (["Q43229", "Q6256"], EntityType.ORGANIZATION),  # org beats place
            (["Q6256", "Q198"], EntityType.PLACE),  # place beats event
            (["Q198", "Q11424"], EntityType.EVENT),  # event beats work
        ],
    )
    def test_highest_precedence_wins(
        self, instance_of: list[str], expected: EntityType
    ) -> None:
        assert classify_entity_type(instance_of) == expected


class TestEventAnchorWidening:
    """2026-11 event widening: carried-level war/conflict/attack/disaster classes that real
    Wikidata items actually hold as P31 (the superclass `occurrence` anchor is dead under flat
    matching). Members chosen by an offline occurrence-ancestry walk; the time-interval branch
    (e.g. historical period) and the recurring-event branch (holidays/festivals) are excluded.
    Re-types zero stored rows (the 5 matching entities were already typed `event`).
    """

    @pytest.mark.parametrize(
        "qid",
        [
            "Q198",  # war
            "Q103495",  # world war
            "Q8465",  # civil war
            "Q864113",  # proxy war
            "Q154605",  # total war
            "Q350604",  # armed conflict
            "Q11422542",  # international conflict
            "Q108809873",  # political conflict
            "Q766875",  # ethnic conflict
            "Q645883",  # military operation
            "Q2001676",  # offensive
            "Q467011",  # invasion
            "Q476807",  # military raid
            "Q3199915",  # massacre
            "Q173462",  # crime against humanity
            "Q25917186",  # coordinated terrorist attack
            "Q898712",  # aircraft hijacking
            "Q10931",  # revolution
            "Q34439356",  # hurricane
            "Q30111082",  # political event
        ],
    )
    def test_carried_level_class_maps_to_event(self, qid: str) -> None:
        assert classify_entity_type([qid]) == EntityType.EVENT

    def test_conflict_beats_law_by_precedence(self) -> None:
        # A long-running conflict can carry a conflict class and (rarely) a law-ish class; EVENT
        # sits above LAW in _PRECEDENCE, so the happening wins. (Treaty Q131569 -> law.)
        assert classify_entity_type(["Q198", "Q131569"]) == EntityType.EVENT

    def test_event_widening_does_not_corroborate(self) -> None:
        # EVENT stays out of _CORROBORATION_TYPES, so widening cannot regress #271.
        assert classify_entity_type(["Q198"]) == EntityType.EVENT
        assert type_corroboration("event", ["Q198"]) is None


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
        assert type_corroboration(entity_type, ["Q198"]) is None


class TestCorroborationDecoupledFromClassification:
    def test_event_classifies_but_does_not_corroborate(self) -> None:
        # The crux of Feature 098: classification widened to cover event, but corroboration
        # for event remains neutral so sparsely-anchored types cannot flash "type may differ".
        assert classify_entity_type(["Q198"]) == EntityType.EVENT
        assert type_corroboration("event", ["Q198"]) is None


class TestTypeVerificationDelegates:
    """T007 — the create-time corroboration (_type_verification) is unchanged after re-pointing."""

    def test_person_true(self) -> None:
        assert _type_verification("person", ["Q5"]) is True

    def test_person_false(self) -> None:
        assert _type_verification("person", ["Q6256"]) is False

    def test_event_neutral(self) -> None:
        assert _type_verification("event", ["Q198"]) is None


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


class TestClassifyIfDeterminate:
    """The typed 'classify, or None if undeterminable' predicate — the single home shared by the
    re-typing backfills and (as a string) by the create-modal suggestion. A determinate P31 yields
    its EntityType; the catch-all OTHER yields None (Direction A: absence of evidence never
    overrides a stored type)."""

    @pytest.mark.parametrize(
        ("instance_of", "expected"),
        [
            (["Q5"], EntityType.PERSON),  # human
            (["Q6256"], EntityType.PLACE),  # country
            (["Q43229"], EntityType.ORGANIZATION),  # organization
            (["Q198"], EntityType.EVENT),  # war
            (["Q11424"], EntityType.WORK),  # film
            (["Q151885"], EntityType.CONCEPT),  # concept
        ],
    )
    def test_determinate_returns_type(
        self, instance_of: list[str], expected: EntityType
    ) -> None:
        assert classify_if_determinate(instance_of) == expected

    def test_empty_is_none(self) -> None:
        assert classify_if_determinate([]) is None

    def test_unknown_qid_is_none(self) -> None:
        assert classify_if_determinate(["Q999999999"]) is None

    def test_other_classification_is_none_not_other(self) -> None:
        # The catch-all OTHER is reported as None, never EntityType.OTHER — that is the whole
        # point of the predicate (the backfills skip None; they must never write 'other').
        assert classify_entity_type(["Q999999999"]) is EntityType.OTHER
        assert classify_if_determinate(["Q999999999"]) is None

    @pytest.mark.parametrize(
        "instance_of",
        [[], ["Q999999999"], ["Q5"], ["Q6256"], ["Q43229"], ["Q198"]],
    )
    def test_suggest_entity_type_is_the_string_view(
        self, instance_of: list[str]
    ) -> None:
        # Single source: suggest_entity_type is exactly classify_if_determinate rendered to a
        # string, so the two cannot drift.
        determinate = classify_if_determinate(instance_of)
        expected = determinate.value if determinate is not None else None
        assert suggest_entity_type(instance_of) == expected


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
            (["Q198"], EntityType.EVENT),  # war
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


class TestClassifyProductFeature103:
    """Feature 103: the narrow `product` anchor set classifies to PRODUCT; organization still
    outranks product (dual-classed companies stay organization); product does NOT corroborate
    (#271-safe — its anchor set is a deliberate floor); website/news-site stay organization.
    """

    _PRODUCT_ANCHORS = [
        "Q620615",  # mobile app
        "Q3220391",  # social networking service
        "Q19967801",  # online service
        "Q559856",  # online video platform
        "Q118140435",  # very large online platform
        "Q122759350",  # user-generated content platform
        "Q59152282",  # video streaming service
        "Q723685",  # video on demand
        "Q870780",  # chatbot
        "Q133284163",  # generative artificial intelligence chatbot
        "Q116961403",  # conversational AI
        "Q115305900",  # large language model
        "Q124629760",  # family of large language models
        "Q116777014",  # generative pre-trained transformer
        "Q117246174",  # generative artificial intelligence
        "Q7397",  # software
        "Q40056",  # computer program
        "Q189053",  # command-line interface
        "Q56277524",  # personal knowledge base
        "Q14644",  # spyware
        "Q1344897",  # whistleblower platform
        "Q351764",  # e-commerce payment system
    ]

    @pytest.mark.parametrize("qid", _PRODUCT_ANCHORS)
    def test_anchor_classifies_to_product(self, qid: str) -> None:
        assert classify_entity_type([qid]) == EntityType.PRODUCT
        assert suggest_entity_type([qid]) == "product"

    def test_anchor_set_is_the_reviewed_22(self) -> None:
        # Pins the reviewed set (data-model §3): 17 core + 5 resolved-IN borderline.
        assert INSTANCE_OF_BY_TYPE[EntityType.PRODUCT] == frozenset(
            self._PRODUCT_ANCHORS
        )
        assert len(self._PRODUCT_ANCHORS) == 22

    def test_organization_outranks_product(self) -> None:
        # A company that also carries a product class stays organization (FR-004).
        assert classify_entity_type(["Q4830453", "Q620615"]) == EntityType.ORGANIZATION
        assert classify_entity_type(["Q620615", "Q4830453"]) == EntityType.ORGANIZATION

    def test_product_outranks_lower_types(self) -> None:
        # product sits directly below organization, above place/event/work/concept.
        assert classify_entity_type(["Q620615", "Q6256"]) == EntityType.PRODUCT
        assert classify_entity_type(["Q620615", "Q11424"]) == EntityType.PRODUCT

    def test_website_and_news_site_are_not_product(self) -> None:
        # website stays organization; news website is no anchor → OTHER (never product), so
        # Direction A keeps a news-site entity's stored type. SC-001: neither is re-typed.
        assert classify_entity_type(["Q35127"]) == EntityType.ORGANIZATION
        assert classify_entity_type(["Q17232649"]) == EntityType.OTHER

    def test_product_corroboration_is_neutral(self) -> None:
        # Deliberate floor → product must NOT corroborate, or it would flash "type may differ".
        assert type_corroboration("product", ["Q620615"]) is None
        assert "product" not in EXPECTED_INSTANCE_OF


class TestClassifyLawFeature104:
    """Feature 104: the narrow `law` anchor set classifies to LAW; law outranks work (a treaty/
    statute that also carries a work class resolves to law); law does NOT corroborate; broad
    document/agreement and the Supreme-Court-decision class are NOT law."""

    _LAW_ANCHORS = ["Q7748", "Q476068", "Q131569", "Q134083781"]

    @pytest.mark.parametrize("qid", _LAW_ANCHORS)
    def test_anchor_classifies_to_law(self, qid: str) -> None:
        assert classify_entity_type([qid]) == EntityType.LAW
        assert suggest_entity_type([qid]) == "law"

    def test_anchor_set_is_the_reviewed_four(self) -> None:
        assert INSTANCE_OF_BY_TYPE[EntityType.LAW] == frozenset(self._LAW_ANCHORS)

    @pytest.mark.parametrize("qid", _LAW_ANCHORS)
    def test_law_outranks_work(self, qid: str) -> None:
        # Any law anchor co-occurring with a work-of-art class (Q386724 = work) resolves to law,
        # in both argument orders (FR-004 — a statute/treaty is never left as a creative work).
        assert classify_entity_type([qid, "Q386724"]) == EntityType.LAW
        assert classify_entity_type(["Q386724", qid]) == EntityType.LAW

    def test_broad_and_scotus_classes_are_not_law(self) -> None:
        # Narrow scope (FR-003/FR-010): broad document/agreement and a court decision are excluded.
        assert classify_entity_type(["Q2006324"]) == EntityType.OTHER  # agreement
        assert classify_entity_type(["Q49848"]) == EntityType.OTHER  # document
        assert (
            classify_entity_type(["Q19692072"]) == EntityType.OTHER
        )  # decision of SCOTUS (resolved OUT)

    def test_law_corroboration_is_neutral(self) -> None:
        assert type_corroboration("law", ["Q7748"]) is None
        assert "law" not in EXPECTED_INSTANCE_OF
