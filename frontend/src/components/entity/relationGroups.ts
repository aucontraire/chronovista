/**
 * Frontend mirror of the canonical relation grouping (Feature 087, US2).
 *
 * Source of truth: backend `src/chronovista/services/relation_groups.py`. This file mirrors its
 * grouping (which Wikidata fields are synonyms) but words label/attribution for the FORWARD
 * direction ("this entity is a member of X"), whereas the backend words them for the inverse
 * ("Referenced by"). True cross-language drift detection would need a shared JSON artifact — out
 * of scope for now; `__tests__/relationGroups.parity.test.ts` pins the load-bearing invariants.
 *
 * Attribute fields (country, place_of_birth, place_of_death) are deliberately absent: they are
 * not relationships between entities.
 */

export interface RelationGroupDef {
  key: string;
  /** Wikidata field names (property keys) this group unions. */
  fields: readonly string[];
  /** Specific relationship name. */
  label: string;
  /** Wikidata-attributed phrasing — a sourced claim, never a generic connection. */
  attribution: string;
}

export const RELATION_GROUPS: readonly RelationGroupDef[] = [
  {
    key: "employment",
    fields: ["employer"],
    label: "Employer",
    attribution: "Listed by Wikidata as an employer of this entity",
  },
  {
    key: "membership",
    fields: ["member_of", "part_of"],
    label: "Member of",
    attribution: "Listed by Wikidata as a group this entity is a member or part of",
  },
  {
    key: "significant_person",
    fields: ["significant_person"],
    label: "Significant person",
    attribution: "Listed by Wikidata as a significant person of this entity",
  },
  {
    key: "founder",
    fields: ["founder"],
    label: "Founder",
    attribution: "Listed by Wikidata as a founder of this entity",
  },
  {
    key: "spouse",
    fields: ["spouse"],
    label: "Spouse",
    attribution: "Listed by Wikidata as a spouse of this entity",
  },
  {
    key: "child",
    fields: ["child"],
    label: "Child",
    attribution: "Listed by Wikidata as a child of this entity",
  },
  {
    key: "father",
    fields: ["father"],
    label: "Father",
    attribution: "Listed by Wikidata as the father of this entity",
  },
  {
    key: "mother",
    fields: ["mother"],
    label: "Mother",
    attribution: "Listed by Wikidata as the mother of this entity",
  },
  {
    key: "sibling",
    fields: ["sibling"],
    label: "Sibling",
    attribution: "Listed by Wikidata as a sibling of this entity",
  },
  // Feature 088: creative-work credits. FORWARD wording — the work's own page lists its people.
  {
    key: "cast",
    fields: ["cast_member"],
    label: "Cast",
    attribution: "Listed by Wikidata as a cast member of this work",
  },
  {
    key: "director",
    fields: ["director"],
    label: "Director",
    attribution: "Listed by Wikidata as a director of this work",
  },
  {
    key: "producer",
    fields: ["producer"],
    label: "Producer",
    attribution: "Listed by Wikidata as a producer of this work",
  },
  {
    key: "screenwriter",
    fields: ["screenwriter"],
    label: "Writer",
    attribution: "Listed by Wikidata as a screenwriter of this work",
  },
  {
    key: "composer",
    fields: ["composer"],
    label: "Composer",
    attribution: "Listed by Wikidata as a composer of this work",
  },
  // Feature 095: additional forward relationships; each is its own group (none are synonyms).
  {
    key: "award_received",
    fields: ["award_received"],
    label: "Award received",
    attribution: "Listed by Wikidata as an award received by this entity",
  },
  {
    key: "notable_work",
    fields: ["notable_work"],
    label: "Notable work",
    attribution: "Listed by Wikidata as a notable work of this entity",
  },
  {
    key: "participant_in",
    fields: ["participant_in"],
    label: "Participant in",
    attribution: "Listed by Wikidata as something this entity participated in",
  },
  {
    key: "parent_organization",
    fields: ["parent_organization"],
    label: "Parent organization",
    attribution: "Listed by Wikidata as this entity's parent organization",
  },
  {
    key: "child_organization",
    fields: ["child_organization"],
    label: "Child organization",
    attribution: "Listed by Wikidata as a child organization or unit of this entity",
  },
  {
    key: "owned_by",
    fields: ["owned_by"],
    label: "Owned by",
    attribution: "Listed by Wikidata as an owner of this entity",
  },
  {
    key: "chairperson",
    fields: ["chairperson"],
    label: "Chairperson",
    attribution: "Listed by Wikidata as this entity's chairperson",
  },
  {
    key: "ceo",
    fields: ["ceo"],
    label: "Chief executive officer",
    attribution: "Listed by Wikidata as this entity's chief executive officer",
  },
  {
    key: "affiliation",
    fields: ["affiliation"],
    label: "Affiliation",
    attribution: "Listed by Wikidata as an affiliation of this entity",
  },
  {
    key: "creator",
    fields: ["creator"],
    label: "Creator",
    attribution: "Listed by Wikidata as the creator of this entity",
  },
  {
    key: "production_company",
    fields: ["production_company"],
    label: "Production company",
    attribution: "Listed by Wikidata as the production company of this entity",
  },
  {
    key: "original_broadcaster",
    fields: ["original_broadcaster"],
    label: "Original broadcaster",
    attribution: "Listed by Wikidata as the original broadcaster of this entity",
  },
];

const GROUP_BY_FIELD: ReadonlyMap<string, RelationGroupDef> = new Map(
  RELATION_GROUPS.flatMap((group) => group.fields.map((f) => [f, group] as const))
);

/** The group a property key belongs to, or undefined for ungrouped relation keys. */
export function relationGroupForField(field: string): RelationGroupDef | undefined {
  return GROUP_BY_FIELD.get(field);
}
