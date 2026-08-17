"""Unit tests for the pure Wikidata property extractors (Feature 068, T002).

This module is the **parity anchor** (spec FR-002): it pins the extracted/assembled shape to the
persisted per-field block ``{"values", "qids", "source", "set_at"}`` the batch load mirrors. Inputs
are neutral placeholder QIDs/labels (Constitution VI).
"""

from __future__ import annotations

from typing import Any

from chronovista.services.wikidata_properties import (
    assemble_block,
    assemble_properties,
    extract_claims,
    format_time,
    pick_label,
    snak_value,
    value_qids,
)


def _item_snak(qid: str) -> dict[str, Any]:
    return {
        "mainsnak": {
            "snaktype": "value",
            "datavalue": {"type": "wikibase-entityid", "value": {"id": qid}},
        }
    }


def _time_snak(stamp: str, precision: int) -> dict[str, Any]:
    return {
        "mainsnak": {
            "snaktype": "value",
            "datavalue": {
                "type": "time",
                "value": {"time": stamp, "precision": precision},
            },
        }
    }


def _string_snak(text: str) -> dict[str, Any]:
    return {
        "mainsnak": {
            "snaktype": "value",
            "datavalue": {"type": "string", "value": text},
        }
    }


class TestFormatTime:
    def test_day_precision(self) -> None:
        assert (
            format_time({"time": "+1959-04-02T00:00:00Z", "precision": 11})
            == "1959-04-02"
        )

    def test_month_precision_drops_day(self) -> None:
        assert (
            format_time({"time": "+1959-04-01T00:00:00Z", "precision": 10}) == "1959-04"
        )

    def test_year_precision_drops_month_day(self) -> None:
        # The padded day/month must NOT be emitted — that would invent a birthday.
        assert format_time({"time": "+1959-01-01T00:00:00Z", "precision": 9}) == "1959"

    def test_decade_or_coarser_is_unrenderable(self) -> None:
        assert format_time({"time": "+1950-01-01T00:00:00Z", "precision": 8}) is None

    def test_bce(self) -> None:
        assert (
            format_time({"time": "-0044-03-15T00:00:00Z", "precision": 11})
            == "0044-03-15 BCE"
        )

    def test_garbage_returns_none(self) -> None:
        assert format_time({"time": "not-a-date", "precision": 11}) is None


class TestSnakValue:
    def test_item_reference(self) -> None:
        assert snak_value(_item_snak("Q000042")["mainsnak"]) == ("Q000042", None)

    def test_time_literal(self) -> None:
        assert snak_value(_time_snak("+2000-01-01T00:00:00Z", 9)["mainsnak"]) == (
            None,
            "2000",
        )

    def test_string_literal(self) -> None:
        assert snak_value(_string_snak("example_handle")["mainsnak"]) == (
            None,
            "example_handle",
        )

    def test_monolingual_text(self) -> None:
        snak = {
            "snaktype": "value",
            "datavalue": {"type": "monolingualtext", "value": {"text": "Placeholder"}},
        }
        assert snak_value(snak) == (None, "Placeholder")

    def test_unknown_datatype_dropped(self) -> None:
        snak = {
            "snaktype": "value",
            "datavalue": {"type": "quantity", "value": {"amount": "+5"}},
        }
        assert snak_value(snak) == (None, None)


class TestExtractClaims:
    def test_item_and_literal_fields(self) -> None:
        claims = {
            "P106": [_item_snak("Q1"), _item_snak("Q2")],  # occupation (items)
            "P569": [_time_snak("+1970-05-06T00:00:00Z", 11)],  # birth_date (literal)
            "P2002": [_string_snak("example_handle")],  # x_username (literal)
        }
        out = extract_claims(claims)
        assert out["occupation"] == {"qids": ["Q1", "Q2"], "literals": []}
        assert out["birth_date"] == {"qids": [], "literals": ["1970-05-06"]}
        assert out["x_username"] == {"qids": [], "literals": ["example_handle"]}

    def test_deprecated_statement_skipped(self) -> None:
        good = _item_snak("Q1")
        deprecated = {**_item_snak("Q2"), "rank": "deprecated"}
        out = extract_claims({"P106": [good, deprecated]})
        assert out["occupation"]["qids"] == ["Q1"]

    def test_novalue_and_somevalue_dropped(self) -> None:
        novalue = {"mainsnak": {"snaktype": "novalue"}}
        somevalue = {"mainsnak": {"snaktype": "somevalue"}}
        # A field that only has novalue/somevalue must not appear at all.
        out = extract_claims({"P569": [novalue, somevalue]})
        assert "birth_date" not in out

    def test_p27_and_p17_both_fold_into_country(self) -> None:
        out = extract_claims({"P27": [_item_snak("Q1")], "P17": [_item_snak("Q2")]})
        assert out["country"] == {"qids": ["Q1", "Q2"], "literals": []}

    def test_duplicate_qid_deduped(self) -> None:
        out = extract_claims({"P106": [_item_snak("Q1"), _item_snak("Q1")]})
        assert out["occupation"]["qids"] == ["Q1"]

    def test_unwanted_property_ignored(self) -> None:
        out = extract_claims({"P9999": [_item_snak("Q1")]})
        assert out == {}


class TestPickLabel:
    def test_prefers_mul_then_en(self) -> None:
        labels = {"en": {"value": "English"}, "mul": {"value": "Mul"}}
        assert pick_label(labels) == "Mul"  # mul is first in LABEL_ORDER

    def test_falls_back_when_mul_absent(self) -> None:
        assert pick_label({"en": {"value": "English"}}) == "English"

    def test_none_when_no_known_lang(self) -> None:
        assert pick_label({"zz": {"value": "x"}}) is None

    def test_first_present_lang_wins_even_if_empty(self) -> None:
        # Parity: mirror the pipeline — the first PRESENT language is selected and returned verbatim
        # (empty string here). The caller drops a falsy label, keeping the value-QID unresolved.
        assert pick_label({"mul": {"value": ""}, "en": {"value": "English"}}) == ""


class TestAssembleBlock:
    def test_persisted_shape_exact_keys(self) -> None:
        block = assemble_block(
            ["Q1"], ["2000"], {"Q1": "Politician"}, "2026-08-17T00:00:00+00:00"
        )
        assert set(block.keys()) == {"values", "qids", "source", "set_at"}
        assert block["source"] == "wikidata"

    def test_labels_resolved_then_literals_appended(self) -> None:
        block = assemble_block(["Q1", "Q2"], ["lit"], {"Q1": "A", "Q2": "B"}, "t")
        assert block["values"] == ["A", "B", "lit"]
        assert block["qids"] == ["Q1", "Q2"]

    def test_unresolved_qid_stays_as_qid(self) -> None:
        # FR-007 partial: a value-QID whose label did not resolve is kept as its QID, never dropped.
        block = assemble_block(["Q1", "Q2"], [], {"Q1": "A"}, "t")
        assert block["values"] == ["A", "Q2"]


class TestAssembleProperties:
    def test_end_to_end_shape(self) -> None:
        claims = {
            "P106": [_item_snak("Q1")],
            "P569": [_time_snak("+1970-01-01T00:00:00Z", 9)],
        }
        extracted = extract_claims(claims)
        assert value_qids(extracted) == ["Q1"]
        props = assemble_properties(
            extracted, {"Q1": "Economist"}, "2026-08-17T00:00:00+00:00"
        )
        assert props["occupation"]["values"] == ["Economist"]
        assert props["birth_date"]["values"] == ["1970"]
        for block in props.values():
            assert set(block.keys()) == {"values", "qids", "source", "set_at"}
