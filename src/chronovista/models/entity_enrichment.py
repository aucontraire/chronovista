"""
Entity enrichment models (Feature 067).

Pydantic V2 models for the knowledge-base enrichment persisted on ``named_entities``:
the structured ``external_ids`` identifier records, the entity-detail enrichment block,
and the tracked contract for one ledger record the loader consumes.

The property bag itself (``named_entities.properties``) is stored and mirrored **verbatim**
as an open ``dict[str, Any]`` — the entity-resolution pipeline accumulates heterogeneous
property entries across versions (``qids`` / ``literals`` / ``values`` / ``source``), and a
rigid sub-schema would reject real records. This mirrors the established precedent of the
existing ``external_ids: dict[str, Any]`` JSONB field. The ``Any`` here is a deliberate,
documented boundary type for open external data (Constitution II).
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# The persisted identifier state. Distinct from the ledger's richer ResolutionStatus:
#   confirmed = an identifier is present; verified = a human confirmed it;
#   absent    = the source was searched and holds nothing (id is None).
IdentifierStatus = Literal["confirmed", "verified", "absent"]


class ExternalIdentifier(BaseModel):
    """One external knowledge-base identifier and its meta-facts (FR-002).

    Stored as a value in ``named_entities.external_ids``, keyed by source
    (``"wikidata"`` / ``"dbpedia"``).
    """

    model_config = ConfigDict(validate_assignment=True)

    id: str | None = Field(
        default=None,
        description="QID or DBpedia IRI; None for a recorded negative result",
    )
    verified: bool = Field(
        default=False, description="A human confirmed this identifier (FR-014)"
    )
    status: IdentifierStatus = Field(default="confirmed")
    link_provenance: str | None = Field(
        default=None,
        description=(
            "For DBpedia: how the resource was reached (sameAs vs sitelink fallback). "
            "Backend-only — never rendered on the detail page (US2 clarification)."
        ),
    )

    @model_validator(mode="after")
    def _status_id_invariant(self) -> ExternalIdentifier:
        """FR-002: an 'absent' identifier has no id; a confirmed/verified one has an id."""
        if self.status == "absent" and self.id is not None:
            raise ValueError("an 'absent' identifier must carry no id")
        if self.status != "absent" and self.id is None:
            raise ValueError("a 'confirmed' or 'verified' identifier must carry an id")
        return self


class EntityIdentifierView(BaseModel):
    """Viewer-facing identifier for the entity detail page (US2).

    Deliberately omits ``status`` and ``link_provenance`` — those stay backend-only
    (US2 clarification, FR-010).
    """

    model_config = ConfigDict(validate_assignment=True)

    source: str = Field(..., description="Knowledge base, e.g. 'wikidata' / 'dbpedia'")
    id: str = Field(..., description="The identifier value")
    url: str = Field(
        ..., description="Link to the identifier on the public knowledge base"
    )
    verified: bool = Field(
        default=False, description="Drives the 'human-verified' indicator (FR-010)"
    )


class EntityEnrichment(BaseModel):
    """The enrichment block returned on the entity detail response (US2, FR-009/010/011)."""

    model_config = ConfigDict(validate_assignment=True)

    grounded: bool = Field(
        ..., description="False → the detail page renders 'not grounded' (FR-011)"
    )
    properties: dict[str, Any] = Field(
        default_factory=dict,
        description="Populated property bag, mirrored verbatim from storage (FR-009)",
    )
    identifiers: list[EntityIdentifierView] = Field(
        default_factory=list, description="External identifiers as links (FR-010)"
    )


class LedgerWikidata(BaseModel):
    """The subset of the ledger's Wikidata block the loader reads. Extra fields ignored."""

    model_config = ConfigDict(extra="ignore")

    qid: str | None = None
    # Ledger ResolutionStatus: unknown | no_article | absent | found (a superset of ours).
    status: str = "unknown"
    verified: bool = False


class LedgerDBpedia(BaseModel):
    """The subset of the ledger's DBpedia block the loader reads. Extra fields ignored."""

    model_config = ConfigDict(extra="ignore")

    resource: str = Field(..., description="The RDF resource IRI — the identifier")
    source: str | None = Field(
        default=None, description="How the resource was reached (link provenance)"
    )


class EntityEnrichmentRecord(BaseModel):
    """Tracked contract for one ledger record the loader consumes (research D2).

    The untracked ``scripts/entity_resolution/`` pipeline exports JSON matching this shape;
    it lives in a gitignored file, so this tracked model IS the contract boundary. Unknown
    fields are ignored so a richer ledger record does not break the load.
    """

    model_config = ConfigDict(extra="ignore")

    entity_id: uuid.UUID
    # Read for the post-load reconciliation sample only; NEVER written (FR-006).
    canonical_name: str
    properties: dict[str, Any] = Field(default_factory=dict)
    wikidata: LedgerWikidata | None = None
    dbpedia: LedgerDBpedia | None = None

    def to_external_ids(self) -> dict[str, ExternalIdentifier]:
        """Transform the ledger's blocks into the DB's ``external_ids`` shape (FR-002).

        A present QID becomes a confirmed (or verified) Wikidata identifier; a searched-
        and-absent Wikidata result becomes an ``absent`` record; ``unknown`` / ``no_article``
        (nothing decided yet) persists no Wikidata entry. A DBpedia resource becomes a
        confirmed identifier carrying its link provenance.
        """
        out: dict[str, ExternalIdentifier] = {}
        wd = self.wikidata
        if wd is not None:
            if wd.qid:
                out["wikidata"] = ExternalIdentifier(
                    id=wd.qid,
                    verified=wd.verified,
                    status="verified" if wd.verified else "confirmed",
                )
            elif wd.status == "absent":
                out["wikidata"] = ExternalIdentifier(
                    id=None, verified=False, status="absent"
                )
        db = self.dbpedia
        if db is not None and db.resource:
            out["dbpedia"] = ExternalIdentifier(
                id=db.resource,
                verified=False,
                status="confirmed",
                link_provenance=db.source,
            )
        return out
