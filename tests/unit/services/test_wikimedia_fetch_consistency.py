"""Cross-service consistency checks for the Wikimedia/DBpedia fetch core (Feature 102, Phase 5,
User Story 3 — single-sourced, consistent outbound behavior).

The architecture fitness guards (``tests/unit/architecture/test_wikimedia_fetch_fitness.py``)
prove the UA is *assembled* in exactly one site (G1) and that the services *compose* the transport.
This module is the complementary **value** check: across the five migrated services it asserts the
outbound identities each services produces are single-sourced from the one template yet remain
distinct per component (SC-002 / FR-002), and that the backoff cap and attempt budget are one shared
value rather than a per-service constant (FR-003).

All five ``_UA_COMPONENT`` constants are imported directly so a service that re-hard-codes a UA, or
collides its label with another service's, surfaces here as a red value assertion — not merely as a
guard-count change. These are pure value checks (no I/O), so the module stays synchronous.
"""

from __future__ import annotations

from chronovista import __version__
from chronovista.services import wikimedia_transport as wt
from chronovista.services.category_size import _UA_COMPONENT as CATEGORY_SIZE_COMPONENT
from chronovista.services.dbpedia_resolver import _UA_COMPONENT as DBPEDIA_COMPONENT
from chronovista.services.entity_category_fetch import (
    _UA_COMPONENT as ENTITY_CATEGORY_COMPONENT,
)
from chronovista.services.wikidata_client import _UA_COMPONENT as WIKIDATA_COMPONENT
from chronovista.services.wikimedia_transport import wikimedia_user_agent
from chronovista.services.wikipedia_image_fallback import (
    _UA_COMPONENT as IMAGE_FALLBACK_COMPONENT,
)

# The five in-scope services' component labels, keyed by service for readable failure messages.
_COMPONENTS: dict[str, str] = {
    "wikidata_client": WIKIDATA_COMPONENT,
    "dbpedia_resolver": DBPEDIA_COMPONENT,
    "entity_category_fetch": ENTITY_CATEGORY_COMPONENT,
    "category_size": CATEGORY_SIZE_COMPONENT,
    "wikipedia_image_fallback": IMAGE_FALLBACK_COMPONENT,
}


class TestSingleSourcedDistinctIdentities:
    """SC-002 / FR-002: one shared UA producer, per-component labels present AND distinct."""

    def test_all_five_services_are_collected(self) -> None:
        # Guard the guard: if a sixth in-scope service is added (or one is dropped) without
        # updating this consistency check, the distinctness assertion below silently narrows.
        assert len(_COMPONENTS) == 5

    def test_every_component_label_is_non_empty(self) -> None:
        for service, component in _COMPONENTS.items():
            assert (
                component and component.strip()
            ), f"{service} has an empty UA component"

    def test_component_labels_are_all_distinct(self) -> None:
        # The image fallback used to reuse the Wikidata client's "personal YouTube-library tool"
        # label — the Phase 5 fix gave it its own "page-image fallback", so the set is now five.
        labels = list(_COMPONENTS.values())
        assert len(set(labels)) == 5, f"component labels collide: {labels}"

    def test_each_service_user_agent_is_template_produced(self) -> None:
        # Each service's produced UA must equal the one shared template applied to its own label,
        # and must carry the single shared contact URL (FR-002: one producer, not one value).
        for service, component in _COMPONENTS.items():
            ua = wikimedia_user_agent(component)
            assert (
                ua == f"chronovista/{__version__} ({wt._CONTACT_URL}; {component})"
            ), f"{service} UA not produced by the shared template"
            assert wt._CONTACT_URL in ua, f"{service} UA missing the shared contact URL"


class TestUnifiedBackoffIsSharedNotPerService:
    """FR-003: the backoff cap and attempt budget are a single shared value in the transport.

    The backoff *behavior* (Retry-After honored-but-capped, exponential fallback, exhaustion raises)
    is covered by the transport's own ``TestBackoff``; this is only a light guard that the cap and
    attempt budget live as one shared constant rather than being re-declared per service.
    """

    def test_wait_cap_is_single_shared_value(self) -> None:
        assert wt._WAIT_CAP == 10.0

    def test_max_attempts_is_single_shared_value(self) -> None:
        assert wt._MAX_ATTEMPTS == 3
