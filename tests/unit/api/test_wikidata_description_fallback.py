"""Unit tests for ``_wikidata_description_fallback`` (entities list description fallback).

The entities list surfaces the Wikidata reference-block description when an entity has no
hand-set ``description`` column, so the list matches what the detail page shows. These cover the
pure extraction's edge cases; the end-to-end wiring is covered by the cross-view integration test.
"""

from __future__ import annotations

from chronovista.api.routers.entity_mentions import _wikidata_description_fallback


def _block(values: object) -> dict[str, object]:
    return {"wikidata_description": {"values": values, "source": "wikidata"}}


class TestWikidataDescriptionFallback:
    def test_returns_first_value(self) -> None:
        props = _block(["British politician (placeholder)", "second"])
        assert (
            _wikidata_description_fallback(props) == "British politician (placeholder)"
        )

    def test_none_properties(self) -> None:
        assert _wikidata_description_fallback(None) is None

    def test_missing_block(self) -> None:
        assert _wikidata_description_fallback({"other_key": {"values": ["x"]}}) is None

    def test_empty_values_list(self) -> None:
        assert _wikidata_description_fallback(_block([])) is None

    def test_empty_string_value_is_none(self) -> None:
        assert _wikidata_description_fallback(_block([""])) is None

    def test_non_string_first_value_is_none(self) -> None:
        assert _wikidata_description_fallback(_block([123])) is None

    def test_block_not_a_dict(self) -> None:
        assert _wikidata_description_fallback({"wikidata_description": "oops"}) is None

    def test_values_not_a_list(self) -> None:
        assert (
            _wikidata_description_fallback({"wikidata_description": {"values": "oops"}})
            is None
        )
