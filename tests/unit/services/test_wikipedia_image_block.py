"""Storage-boundary unit test for the Wikipedia image block writer (Feature 093, FR-003).

The crux of the cross-feature data contract: a Wikipedia-sourced image MUST be written by a
dedicated helper tagged ``source == "wikipedia"`` — NOT by :func:`assemble_block`, which forces
``source == "wikidata"`` (a value the refetch merge treats as replaceable). These tests pin the
block shape and prove the two writers are distinct, so a future change cannot silently route a
Wikipedia image through the Wikidata assembler and make it clobberable. Synthetic filenames only.
"""

from __future__ import annotations

from chronovista.services.wikidata_properties import (
    SOURCE,
    WIKIPEDIA_SOURCE,
    assemble_block,
    merge_wikidata_blocks,
    wikipedia_image_block,
)

_SET_AT = "2026-10-24T00:00:00Z"


class TestBlockShape:
    def test_shape_and_source(self) -> None:
        block = wikipedia_image_block("Placeholder_Portrait.jpg", _SET_AT)
        assert block == {
            "values": ["Placeholder_Portrait.jpg"],
            "qids": [],
            "source": "wikipedia",
            "set_at": _SET_AT,
        }

    def test_source_is_wikipedia_not_wikidata(self) -> None:
        block = wikipedia_image_block("Placeholder_Portrait.jpg", _SET_AT)
        assert block["source"] == WIKIPEDIA_SOURCE == "wikipedia"
        assert block["source"] != SOURCE  # SOURCE == "wikidata"

    def test_first_value_is_the_bare_commons_filename(self) -> None:
        # The resolver serves values[0] as a bare Commons File name (no File: prefix, no URL).
        block = wikipedia_image_block("Some_Free_File.jpg", _SET_AT)
        assert block["values"][0] == "Some_Free_File.jpg"


class TestNotTheWikidataAssembler:
    def test_distinct_source_from_assemble_block(self) -> None:
        # assemble_block hard-codes source "wikidata"; the Wikipedia helper must differ.
        wd = assemble_block([], ["Some_Free_File.jpg"], {}, _SET_AT)
        wiki = wikipedia_image_block("Some_Free_File.jpg", _SET_AT)
        assert wd["source"] == "wikidata"
        assert wiki["source"] == "wikipedia"
        assert wd["source"] != wiki["source"]


class TestLifecycleAgainstMerge:
    """The block's reason-for-being: it survives a Wikidata refetch and is overridden by P18."""

    def test_survives_refetch_with_no_p18(self) -> None:
        # A property refetch that finds no P18 adds no "image" key; the merge preserves ours (FR-005).
        current = {"image": wikipedia_image_block("Placeholder_Portrait.jpg", _SET_AT)}
        fresh: dict[str, object] = {
            "occupation": assemble_block([], ["analyst"], {}, _SET_AT)
        }
        merged = merge_wikidata_blocks(current, fresh)
        assert merged["image"] == current["image"]

    def test_overridden_by_a_later_p18(self) -> None:
        # A refetch that DOES find P18 overlays a fresh source:"wikidata" image → Wikidata wins.
        current = {"image": wikipedia_image_block("Placeholder_Portrait.jpg", _SET_AT)}
        p18 = assemble_block(
            [], ["Real_Wikidata_Portrait.jpg"], {}, "2026-10-25T00:00:00Z"
        )
        merged = merge_wikidata_blocks(current, {"image": p18})
        assert merged["image"]["source"] == "wikidata"
        assert merged["image"]["values"] == ["Real_Wikidata_Portrait.jpg"]
