"""
Factories for Feature 067 entity-enrichment models and ledger fixtures.

All values are NEUTRAL placeholders — never real library names, QIDs, or IRIs (Constitution
VI). These build the tracked ``EntityEnrichmentRecord`` contract and raw ledger-shaped dicts
for the load seam tests (ST-001/002/006).
"""

from __future__ import annotations

import uuid
from typing import Any

import factory
from factory import LazyFunction
from uuid_utils import uuid7

from chronovista.models.entity_enrichment import (
    EntityEnrichmentRecord,
    ExternalIdentifier,
    LedgerDBpedia,
    LedgerWikidata,
)


def _uuid7() -> uuid.UUID:
    return uuid.UUID(str(uuid7()))


class EntityEnrichmentRecordFactory(factory.Factory[EntityEnrichmentRecord]):
    """Factory for the tracked load-input record (neutral placeholders)."""

    class Meta:
        model = EntityEnrichmentRecord

    entity_id = LazyFunction(_uuid7)
    canonical_name = factory.Sequence(lambda n: f"Example Entity {n}")
    properties = factory.LazyFunction(
        lambda: {
            "occupation": {"values": ["placeholder occupation"], "qids": ["Q000001"]},
            "country": {"values": ["Placeholderland"], "qids": ["Q000002"]},
        }
    )
    wikidata = factory.LazyFunction(
        lambda: LedgerWikidata(qid="Q000009", status="found", verified=False)
    )
    dbpedia = factory.LazyFunction(
        lambda: LedgerDBpedia(
            resource="http://dbpedia.org/resource/Example_Entity",
            source="owl:sameAs from wikidata",
        )
    )


def build_external_identifier(**kwargs: Any) -> ExternalIdentifier:
    """Build a structured ExternalIdentifier with neutral defaults."""
    defaults: dict[str, Any] = {
        "id": "Q000009",
        "verified": False,
        "status": "confirmed",
    }
    defaults.update(kwargs)
    return ExternalIdentifier(**defaults)


def build_ledger_record(**kwargs: Any) -> dict[str, Any]:
    """Build a raw ledger-shaped record dict (as it appears in the export JSON).

    Includes extra fields the real ledger carries (mention_count, aliases, …) so tests
    exercise the ``extra='ignore'`` path.
    """
    entity_id = str(kwargs.pop("entity_id", _uuid7()))
    record: dict[str, Any] = {
        "entity_id": entity_id,
        "canonical_name": kwargs.pop("canonical_name", "Example Entity"),
        "canonical_name_normalized": "example entity",
        "entity_type": "person",
        "mention_count": 3,
        "video_count": 2,
        "aliases": [],
        "properties": {
            "occupation": {"values": ["placeholder occupation"], "qids": ["Q000001"]},
        },
        "wikidata": {"qid": "Q000009", "status": "found", "verified": False},
        "dbpedia": {
            "resource": "http://dbpedia.org/resource/Example_Entity",
            "page": "https://en.wikipedia.org/wiki/Example_Entity",
            "source": "owl:sameAs from wikidata",
            "outgoing_links": 12,
        },
    }
    record.update(kwargs)
    return record


def build_ledger_export(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Wrap raw records in a ledger export envelope (as written to entities.json)."""
    return {
        "schema_version": 3,
        "generated_at": "2026-08-16T00:00:00Z",
        "source": "test",
        "entity_count": len(records),
        "passes": [],
        "entities": records,
    }
