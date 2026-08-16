"""Domain models for entity↔video associations (Feature 066).

An **association** links a named entity to a video through one of five sources.
These are domain models returned by the canonical association resolver in the
repository layer and consumed by the API; they live here (not in ``api/schemas``)
so the repository can return them without depending on the API layer.

``mention`` is the text-anchored subset (transcript / title / description);
``tag`` and ``manual`` are associations that are not mentions. Reliability
descends manual > transcript > title > description > tag.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class AssociationSourceBreakdown(BaseModel):
    """Per-source distinct-video counts behind an entity's association total.

    Each field is the number of distinct videos associated with the entity
    through that source. ``tag`` is a derived association (from ``video_tags``);
    the other four are stored ``mention_source`` values, with ``manual``
    distinguished by detection method.

    Attributes
    ----------
    manual : int
        Videos associated by a manual/asserted link (may have no text anchor).
    transcript : int
        Videos where the entity was spoken in the transcript.
    title : int
        Videos with the entity in the title.
    description : int
        Videos with the entity in the description.
    tag : int
        Videos associated through an uploader tag.
    """

    manual: int = Field(ge=0)
    transcript: int = Field(ge=0)
    title: int = Field(ge=0)
    description: int = Field(ge=0)
    tag: int = Field(ge=0)

    model_config = ConfigDict(strict=True)


class AssociationCount(BaseModel):
    """An entity's association video count with its per-source breakdown.

    Computed once by the canonical association resolver and surfaced identically
    by the entity list and the entity detail, so the two can never disagree
    (FR-001/FR-002).

    Attributes
    ----------
    total : int
        Distinct videos associated with the entity through ANY source. Repetition
        of a name within one field never inflates it (FR-003).
    by_source : AssociationSourceBreakdown
        The inline five-source breakdown (FR-004). The parts do NOT necessarily
        sum to ``total``: a video reached through two sources counts once in
        ``total`` but in each contributing source.
    """

    total: int = Field(ge=0)
    by_source: AssociationSourceBreakdown

    model_config = ConfigDict(strict=True)
