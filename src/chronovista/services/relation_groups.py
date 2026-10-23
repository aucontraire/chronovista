"""Canonical relation grouping for the INVERSE "Referenced by" surface (Feature 087).

This is the backend definition the ``/referenced-by`` endpoint returns — so its labels/attributions
describe the *referencing* entity's relationship to the viewed one (the INVERSE of the stored field).
The forward outgoing-relations display has its own forward-worded grouping in the frontend mirror
(`frontend/src/components/entity/relationGroups.ts`). The two share the **synonym-union principle**
(FR-003 — notably membership = member_of + part_of, identical both directions) and the field
exclusions, but family relations invert to *different* groups (father/mother → "children"; child →
"parents"), so the labels and some groupings are direction-specific, not a single shared literal.

Two load-bearing rules:
- **Synonymous grouping (FR-003):** ``member_of`` (P463) and ``part_of`` (P361) both carry group
  membership, so they are ONE group. Keying an inverse query to a single field under-reports
  *invisibly* (a partial count looks like a working feature).
- **Source attribution (FR-004):** each group names its specific relationship and frames it as
  Wikidata's statement, never a generic "related to" — an inverted vague relation (e.g. P3342, which
  spans founders…opponents…victims) must read as a reported, sourced claim about a real person.

Field names are the human-readable aliases from :data:`chronovista.services.wikidata_properties.WANTED`
(e.g. ``significant_person`` for P3342), NOT the P-numbers. Selection is by **measured value**
(employment, membership, significant-person, founder, family), EXCLUDING attribute/hub fields
(country, place_of_birth/death) whose inverse is a hub list, not a relationship (wayfinder ticket 05).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class RelationGroup(BaseModel):
    """One displayed relationship: the synonymous source fields it unions + its label/attribution."""

    model_config = ConfigDict(frozen=True)

    key: str = Field(
        ...,
        description=(
            "Stable OPAQUE group identifier, e.g. 'membership'. Carries NO directional guarantee — "
            "the key's wording (noun vs verb) is not a contract; the subject/direction live in "
            "`label`/`attribution`. Consumers must treat it as an opaque id."
        ),
    )
    member_fields: tuple[str, ...] = Field(
        ...,
        description="The WANTED field name(s) this group unions (e.g. member_of + part_of)",
    )
    label: str = Field(..., description="Specific relationship name shown to the user")
    attribution: str = Field(
        ...,
        description="Source-attributed framing — Wikidata's statement, never a generic connection",
    )


# These are the INVERSE groups — this list is what the "Referenced by" endpoint returns, so each
# label/attribution describes the REFERENCING entity's relationship to the viewed one (the inverse of
# the stored field). Inverting a family relation changes the GROUPING, not just the wording: an entity
# whose `father` OR `mother` names the viewed entity IS a child of it (→ "children"); an entity whose
# `child` names it IS a parent (→ "parents"). (The forward display's grouping/labels live in the
# frontend mirror; only the synonym-union principle and the field exclusions are shared.)
# Each `member_fields` entry MUST be a key in WANTED. Excluded: country (P27/P17), place_of_birth
# (P19), place_of_death (P20) — their inverse is a hub list, not a relationship.
RELATION_GROUPS: tuple[RelationGroup, ...] = (
    RelationGroup(
        key="employment",
        member_fields=("employer",),
        label="Employee",
        attribution="Listed by Wikidata as an employee of this entity",
    ),
    RelationGroup(
        key="membership",
        member_fields=("member_of", "part_of"),
        label="Member",
        attribution="Listed by Wikidata as a member or part of this entity",
    ),
    RelationGroup(
        # X.founder == T  →  T founded X  →  X is an entity founded by the viewed one.
        key="founded",
        member_fields=("founder",),
        label="Founded by this entity",
        attribution="Listed by Wikidata as founded by this entity",
    ),
    RelationGroup(
        # X.significant_person == T  →  T is a significant person of X.
        key="significant_person_of",
        member_fields=("significant_person",),
        label="Has this entity as a significant person",
        attribution="Listed by Wikidata as having this entity as a significant person",
    ),
    RelationGroup(
        # X.father == T  or  X.mother == T  →  T is X's parent  →  X is a child of the viewed entity.
        key="children",
        member_fields=("father", "mother"),
        label="Child",
        attribution="Listed by Wikidata as a child of this entity",
    ),
    RelationGroup(
        # X.child == T  →  T is X's child  →  X is a parent of the viewed entity.
        key="parents",
        member_fields=("child",),
        label="Parent",
        attribution="Listed by Wikidata as a parent of this entity",
    ),
    RelationGroup(
        key="spouse",
        member_fields=("spouse",),
        label="Spouse",
        attribution="Listed by Wikidata as a spouse of this entity",
    ),
    RelationGroup(
        key="sibling",
        member_fields=("sibling",),
        label="Sibling",
        attribution="Listed by Wikidata as a sibling of this entity",
    ),
    # Feature 088 — creative-work credits. The field is stored on the WORK and names a person, so the
    # referencing entity X is the work and the viewed entity T is the person: X is directed/produced/
    # written/scored BY T, or HAS T in its cast. Labels are X-centric ("… by this entity"), mirroring
    # `founded` — never "Director of" etc., which attached to the work would read backwards.
    RelationGroup(
        # X.cast_member == T  →  the work X has person T in its cast.
        key="cast_of",
        member_fields=("cast_member",),
        label="Has this entity in its cast",
        attribution="Listed by Wikidata with this entity in its cast",
    ),
    RelationGroup(
        # X.director == T  →  the work X is directed by person T.
        key="directed",
        member_fields=("director",),
        label="Directed by this entity",
        attribution="Listed by Wikidata as directed by this entity",
    ),
    RelationGroup(
        key="produced",
        member_fields=("producer",),
        label="Produced by this entity",
        attribution="Listed by Wikidata as produced by this entity",
    ),
    RelationGroup(
        key="wrote",
        member_fields=("screenwriter",),
        label="Written by this entity",
        attribution="Listed by Wikidata as written by this entity",
    ),
    RelationGroup(
        key="scored",
        member_fields=("composer",),
        label="Scored by this entity",
        attribution="Listed by Wikidata as having its score composed by this entity",
    ),
)

# Flat set of every field the reverse query searches (de-duplicated), for the repository's WHERE.
INBOUND_FIELDS: tuple[str, ...] = tuple(
    dict.fromkeys(f for g in RELATION_GROUPS for f in g.member_fields)
)
