"""
Wikipedia free-Commons image fallback — per-entity fetch outcome models (Feature 093).

The backfill asks, for each grounded entity with no image, whether its English Wikipedia page
carries a *free* Wikimedia Commons lead image. The answer is a :class:`FallbackResult` whose
:class:`FallbackOutcome` is one of a **closed, distinct** set — so the run summary can count a
*proven absence* (no page, no lead image) separately from a *failure* (an exhausted retry or a
transport error) rather than conflating the two (spec FR-007, Constitution VIII).

Only ``STORED`` carries a filename; every other outcome stores nothing. These are pure value
objects (no I/O) assembled by :mod:`chronovista.services.wikipedia_image_fallback`.
"""

from __future__ import annotations

from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class FallbackOutcome(str, Enum):
    """The single recorded result of evaluating one entity's English Wikipedia lead image.

    A closed set, keyed to the observable facts the fetch can establish (spec FR-007):

    - ``STORED`` — a free Commons lead image was found and its bare filename stored.
    - ``DECLINED_NON_FREE`` — the file is flagged non-free, **or** its hosting metadata could
      not be obtained and is declined conservatively (an unverifiable file is never stored).
    - ``DECLINED_NOT_COMMONS`` — the lead image is a local English-Wikipedia upload, not hosted
      on Wikimedia Commons (so it is neither free-by-Commons-policy nor resolvable by the
      Commons-only serving path).
    - ``NO_PAGE`` — the entity's Wikidata item has no English-Wikipedia sitelink.
    - ``NO_LEAD_IMAGE`` — the English-Wikipedia page has no free lead image.
    - ``ERROR`` — an external call failed or its rate-limit retries were exhausted. A *failure*,
      counted apart from the proven absences above.
    """

    STORED = "stored"
    DECLINED_NON_FREE = "declined_non_free"
    DECLINED_NOT_COMMONS = "declined_not_commons"
    NO_PAGE = "no_page"
    NO_LEAD_IMAGE = "no_lead_image"
    ERROR = "error"


class FallbackResult(BaseModel):
    """The outcome of evaluating one entity, plus the filename when (and only when) stored.

    ``filename`` is set exactly when ``outcome is FallbackOutcome.STORED`` and is ``None`` for
    every decline/absence/error. ``detail`` carries a short human-readable note (e.g. the QID with
    no sitelink, or the error text) for the per-entity summary — never library content in tests.
    """

    model_config = ConfigDict(frozen=True)

    entity_id: UUID
    outcome: FallbackOutcome
    filename: str | None = None
    detail: str | None = None
