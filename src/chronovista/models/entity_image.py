"""Pydantic V2 models for the manual entity image (Feature 092).

An entity's displayed portrait is resolved from two independent sources: an
operator-uploaded image (dedicated ``named_entities`` columns + a file on disk)
and the automated Wikidata/Commons image (``properties.image``). These models
carry the resolved state to the API surface and shape the mutation requests.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ImageSource = Literal["manual", "wikidata"]


class EntityImageState(BaseModel):
    """The resolved image state for an entity (returned on the detail response).

    ``source`` is the stored preference; the resolver falls back when the
    preferred source has no usable image. ``version`` drives the portrait
    ``?v=`` cache-buster and is ``None`` when only the placeholder applies.
    """

    model_config = ConfigDict(strict=True)

    has_manual: bool = Field(
        ...,
        description="An uploaded manual image exists (manual_image_ext IS NOT NULL)",
    )
    has_wikidata: bool = Field(
        ..., description="A usable automated Wikidata/Commons image exists"
    )
    source: ImageSource = Field(
        ..., description="Stored source preference: 'manual' or 'wikidata'"
    )
    version: str | None = Field(
        default=None,
        description=(
            "Cache-buster: the effective image's timestamp (ISO-8601), or None "
            "when neither a manual nor an automated image applies"
        ),
    )


class SetImageSourceRequest(BaseModel):
    """Request body for ``PATCH /entities/{id}/image/source``."""

    model_config = ConfigDict(strict=True)

    source: ImageSource = Field(
        ..., description="Which source to display: 'manual' or 'wikidata'"
    )
