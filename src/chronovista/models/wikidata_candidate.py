"""
Wikidata candidate model (Feature 067, US3).

The transient shortlist item shown for human approval when creating an entity. Not persisted.
Carries the signals ADR-010 D5 found necessary to reject look-alike stubs — a label,
description and type alone are insufficient against machine-generated author items.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class WikidataCandidate(BaseModel):
    """One ranked Wikidata match offered for approval during entity creation."""

    model_config = ConfigDict(validate_assignment=True)

    qid: str = Field(..., description="Wikidata item id, e.g. 'Q42'")
    label: str = Field(
        ...,
        description="Display label, resolved BCP-47-aware (en → mul/en-gb, FR-016)",
    )
    description: str | None = Field(
        default=None, description="Item description, if any"
    )
    instance_of: list[str] = Field(
        default_factory=list,
        description="P31 values, for the type cross-check (FR-013)",
    )
    statement_count: int = Field(
        default=0, description="Total statements — a stub signal (FR-013)"
    )
    sitelink_count: int = Field(
        default=0, description="Linked reference pages — a stub signal (FR-013)"
    )
    is_stub: bool = Field(
        default=False,
        description=(
            "True when the item looks machine-generated: few statements and no sitelinks, "
            "or the author-stub signal (an ORCID with little else) — ADR-010 D5."
        ),
    )
    type_matches: bool = Field(
        default=False,
        description="Whether instance_of corroborates the entity type being assigned (FR-013)",
    )
