"""Unit tests for the derived Wikipedia identifier on the entity enrichment block.

A DBpedia resource IRI encodes the English-Wikipedia article title, so the detail
page can offer a Wikipedia article link next to the Wikidata/DBpedia chips without a
second lookup. ``_build_enrichment`` derives it by reusing the canonical
``title_from_dbpedia_iri`` (the tested inverse of the resolver's ``_resource_iri``,
which URL-unquotes), and renders it through ``_identifier_url``. These tests pin that
behaviour. Neutral placeholder titles only (Constitution VI).
"""

from __future__ import annotations

from typing import Any

from chronovista.api.routers.entity_mentions import (
    _build_enrichment,
    _identifier_url,
)

RESOURCE = "http://dbpedia.org/resource/"


class TestIdentifierUrl:
    def test_wikipedia_url_from_title(self) -> None:
        assert (
            _identifier_url("wikipedia", "Placeholder_Person")
            == "https://en.wikipedia.org/wiki/Placeholder_Person"
        )

    def test_unknown_source_passes_through(self) -> None:
        # An unrecognised source is rendered as-is (the pre-existing fallback).
        assert _identifier_url("freebase", "/m/0abc") == "/m/0abc"


def _wikipedia(enrichment: Any) -> Any:
    return next(
        (view for view in enrichment.identifiers if view.source == "wikipedia"), None
    )


class TestBuildEnrichmentDerivesWikipedia:
    def test_derives_from_dbpedia_iri_next_to_the_others(self) -> None:
        enrichment = _build_enrichment(
            external_ids={
                "wikidata": {"id": "Q000001", "verified": True},
                "dbpedia": {"id": f"{RESOURCE}Placeholder_Person", "verified": False},
            },
            properties=None,
        )
        wiki = _wikipedia(enrichment)
        assert wiki is not None
        assert wiki.url == "https://en.wikipedia.org/wiki/Placeholder_Person"
        assert wiki.id == "Placeholder_Person"
        # Appears alongside the stored chips, after them.
        sources = [view.source for view in enrichment.identifiers]
        assert sources[-1] == "wikipedia"
        assert {"wikidata", "dbpedia"}.issubset(set(sources))

    def test_percent_encoded_title_is_decoded_for_display(self) -> None:
        # The DBpedia IRI percent-encodes characters outside the resolver's safe set.
        # Reusing title_from_dbpedia_iri unquotes them, so the rendered `id` reads
        # cleanly rather than showing "%26"/"%C3%A9" gunk (api-contract-guardian finding 1).
        enrichment = _build_enrichment(
            external_ids={"dbpedia": {"id": f"{RESOURCE}Plac%C3%A9_%26_Co"}},
            properties=None,
        )
        wiki = _wikipedia(enrichment)
        assert wiki is not None
        assert wiki.id == "Placé_&_Co"
        assert wiki.url == "https://en.wikipedia.org/wiki/Placé_&_Co"

    def test_derives_from_legacy_bare_string_iri(self) -> None:
        # The legacy string shape stores the id as a bare string that is still a full
        # IRI (``{"dbpedia": "http://.../resource/Title"}``) — it must derive too.
        enrichment = _build_enrichment(
            external_ids={"dbpedia": f"{RESOURCE}Placeholder_Person"}, properties=None
        )
        wiki = _wikipedia(enrichment)
        assert wiki is not None
        assert wiki.url == "https://en.wikipedia.org/wiki/Placeholder_Person"

    def test_derived_wikipedia_is_not_human_verified(self) -> None:
        # Even when the DBpedia chip is verified, the DERIVED Wikipedia link is not:
        # nobody confirmed a string-manipulated link, and the badge means human-confirmed
        # (FR-014). So it stays False regardless of the DBpedia flag.
        enrichment = _build_enrichment(
            external_ids={
                "dbpedia": {"id": f"{RESOURCE}Placeholder_Person", "verified": True}
            },
            properties=None,
        )
        wiki = _wikipedia(enrichment)
        assert wiki is not None
        assert wiki.verified is False

    def test_no_wikipedia_without_a_dbpedia_id(self) -> None:
        # A bare Wikidata QID cannot yield an article title without a fetch, so no chip.
        enrichment = _build_enrichment(
            external_ids={"wikidata": {"id": "Q000001", "verified": True}},
            properties=None,
        )
        assert _wikipedia(enrichment) is None

    def test_stored_canonical_wikipedia_wins_over_derivation(self) -> None:
        # A pipeline-stored `wikipedia` identifier must be used verbatim, not duplicated
        # by a derived one.
        enrichment = _build_enrichment(
            external_ids={
                "dbpedia": {"id": f"{RESOURCE}Placeholder_Person", "verified": False},
                "wikipedia": {"id": "Canonical_Title", "verified": True},
            },
            properties=None,
        )
        wikis = [v for v in enrichment.identifiers if v.source == "wikipedia"]
        assert len(wikis) == 1
        assert wikis[0].id == "Canonical_Title"
        assert wikis[0].url == "https://en.wikipedia.org/wiki/Canonical_Title"
        assert wikis[0].verified is True

    def test_absent_dbpedia_negative_yields_no_wikipedia(self) -> None:
        # A recorded DBpedia negative (id is None) is not a link, so nothing to derive.
        enrichment = _build_enrichment(
            external_ids={"dbpedia": {"id": None, "status": "absent"}},
            properties=None,
        )
        assert _wikipedia(enrichment) is None
