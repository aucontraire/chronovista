"""Single source of truth for mapping a Wikidata entity's ``instance_of`` (P31) to our ``EntityType``.

Feature 098. Consolidates the P31→type knowledge that was previously duplicated
(``wikidata_client.EXPECTED_INSTANCE_OF`` and a verbatim copy in the entity-resolution
sweep tooling) and widens it from three types to the full surfaced taxonomy, so candidate
typing, approval, the create-modal suggestion, and the create-time corroboration badge all
answer "what type is this Wikidata entity?" the same way.

Two views of one source, deliberately decoupled:

- :data:`INSTANCE_OF_BY_TYPE` — the **classification** table (broad). :func:`classify_entity_type`
  picks the best ``EntityType`` for a set of P31 QIDs. Growable: add a QID to a set.
- :data:`EXPECTED_INSTANCE_OF` / :func:`type_corroboration` — the **corroboration** view (narrow:
  only the types with a reliable, reasonably complete expected set). This preserves the tri-state
  "agrees / may differ / neutral" semantics the create badge relies on (#271): a type without a
  reliable expected set returns ``None`` (neutral), never a false "may differ". Widening
  *classification* must NOT widen *corroboration*, or sparsely-anchored types would regress #271.

All QIDs here are universal Wikidata **class** identifiers (public ontology, e.g. ``Q5`` = human),
never library entities — nothing here is library content.
"""

from __future__ import annotations

from chronovista.models.enums import EntityType

# Classification table — which P31 class QIDs imply each EntityType. Seeded from the former
# wikidata_client.EXPECTED_INSTANCE_OF (person/place/organization) and extended with conservative,
# well-known anchors for event/work/concept. Grow as coverage gaps surface (see spec FR-002);
# types without a dependable anchor (e.g. technical_term) stay empty and fall through to OTHER.
INSTANCE_OF_BY_TYPE: dict[EntityType, frozenset[str]] = {
    EntityType.PERSON: frozenset({"Q5"}),  # human
    EntityType.PLACE: frozenset(
        {
            "Q6256",  # country
            "Q3624078",  # sovereign state
            "Q515",  # city
            "Q15284",  # municipality
            "Q7275",  # state
            "Q82794",  # geographic region
            "Q23442",  # island
        }
    ),
    EntityType.ORGANIZATION: frozenset(
        {
            "Q4830453",  # business
            "Q43229",  # organization
            "Q783794",  # company
            "Q7278",  # political party
            "Q1616075",  # television station
            "Q11033",  # mass media
            "Q163740",  # nonprofit organization
            "Q3918",  # university
            "Q1002697",  # periodical
        }
    ),
    EntityType.EVENT: frozenset(
        {
            "Q1656682",  # event
            "Q1190554",  # occurrence
            "Q13418847",  # historical event
        }
    ),
    EntityType.WORK: frozenset(
        {
            "Q386724",  # work
            "Q47461344",  # written work
            "Q7725634",  # literary work
            "Q571",  # book
            "Q11424",  # film
            "Q2188189",  # musical work
            "Q7889",  # video game
        }
    ),
    EntityType.CONCEPT: frozenset(
        {
            "Q151885",  # concept
        }
    ),
    # TECHNICAL_TERM: no dependable P31 anchor yet → resolves to OTHER until grown.
}

# Resolution order for multi-type inputs (clarification Q1 / FR-010), highest first.
_PRECEDENCE: tuple[EntityType, ...] = (
    EntityType.PERSON,
    EntityType.ORGANIZATION,
    EntityType.PLACE,
    EntityType.EVENT,
    EntityType.WORK,
    EntityType.CONCEPT,
    EntityType.TECHNICAL_TERM,
    EntityType.OTHER,
)

# Types for which we assert corroboration (a reliable, reasonably complete expected set). Anything
# outside this set corroborates as neutral (None), never "may differ" — this is what keeps the
# create badge from regressing #271 as the classification table grows.
_CORROBORATION_TYPES: frozenset[EntityType] = frozenset(
    {EntityType.PERSON, EntityType.PLACE, EntityType.ORGANIZATION}
)

# String-keyed corroboration view, re-exported for callers that key by the entity_type string
# (the former wikidata_client.EXPECTED_INSTANCE_OF shape). Identical content to before.
EXPECTED_INSTANCE_OF: dict[str, set[str]] = {
    t.value: set(INSTANCE_OF_BY_TYPE[t]) for t in _CORROBORATION_TYPES
}


def classify_entity_type(instance_of: list[str]) -> EntityType:
    """Pick the best ``EntityType`` for a Wikidata entity's P31 (``instance_of``) QIDs.

    Pure (no I/O): takes already-fetched P31 QIDs. Deterministic and order-independent — it
    collects every EntityType whose anchor set intersects ``instance_of`` and returns the
    highest by :data:`_PRECEDENCE`. Empty input, unknown QIDs, or no anchor match → ``OTHER``.

    Parameters
    ----------
    instance_of : list[str]
        The entity's P31 class QIDs (e.g. ``["Q6256", "Q3624078"]``). May be empty.

    Returns
    -------
    EntityType
        The classified type; ``EntityType.OTHER`` when undeterminable.
    """
    qids = set(instance_of)
    matched = {t for t, anchors in INSTANCE_OF_BY_TYPE.items() if anchors & qids}
    for candidate in _PRECEDENCE:
        if candidate in matched:
            return candidate
    return EntityType.OTHER


def type_corroboration(entity_type: str | None, instance_of: list[str]) -> bool | None:
    """Tri-state: does a *chosen* entity type agree with the entity's P31 (#271 semantics)?

    - ``True``  — the type has a reliable expected set and ``instance_of`` corroborates it.
    - ``False`` — the type has a reliable expected set but ``instance_of`` does not match it.
    - ``None``  — the type has no reliable expected set (neutral; render as absent, NOT as
      "type may differ"). This is the #271-safe default and does not widen as the
      classification table grows.
    """
    expected = EXPECTED_INSTANCE_OF.get(entity_type or "", set())
    if not expected:
        return None
    return bool(expected & set(instance_of))


def suggest_entity_type(instance_of: list[str]) -> str | None:
    """Suggested entity type for the create-entity modal (Feature 098, FR-008).

    The classifier's result as a string, or ``None`` when it is the catch-all OTHER — i.e. no
    confident suggestion (undeterminable). The modal pre-selects a non-``None`` suggestion and
    leaves the type selector unset for ``None`` (clarification Q2), rather than nudging the user
    toward "other". Derives from the same classifier as the corroboration badge, so suggestion
    and badge cannot drift (FR-009).
    """
    classified = classify_entity_type(instance_of)
    return classified.value if classified is not EntityType.OTHER else None
