/**
 * Centralized entity type constants for named entity UI.
 *
 * These constants are shared across EntitiesPage, EntityDetailPage, and any
 * future component that renders entity type badges, filter tabs, or tooltips.
 * Import from here instead of redefining per-file.
 *
 * @module constants/entityTypes
 */

// ---------------------------------------------------------------------------
// Labels
// ---------------------------------------------------------------------------

/**
 * Human-readable display label for each entity_type value from the backend.
 * Covers all 8 entity-producing types.
 */
export const ENTITY_TYPE_LABELS: Record<string, string> = {
  person: "Person",
  organization: "Organization",
  place: "Place",
  event: "Event",
  work: "Work",
  technical_term: "Technical Term",
  concept: "Concept",
  other: "Other",
};

// ---------------------------------------------------------------------------
// Colors
// ---------------------------------------------------------------------------

/**
 * Tailwind CSS badge colour classes for each entity_type value.
 *
 * Each value is a space-joined set of bg-, text-, and border- utility classes
 * suitable for use inside an `<span className={...}>` badge element.
 * Falls back to slate neutral when the type is unrecognised.
 */
export const ENTITY_TYPE_COLORS: Record<string, string> = {
  person: "bg-indigo-100 text-indigo-700 border-indigo-200",
  organization: "bg-violet-100 text-violet-700 border-violet-200",
  place: "bg-emerald-100 text-emerald-700 border-emerald-200",
  event: "bg-amber-100 text-amber-700 border-amber-200",
  work: "bg-sky-100 text-sky-700 border-sky-200",
  technical_term: "bg-teal-100 text-teal-700 border-teal-200",
  concept: "bg-rose-100 text-rose-700 border-rose-200",
  other: "bg-slate-100 text-slate-700 border-slate-200",
};

// ---------------------------------------------------------------------------
// Tabs
// ---------------------------------------------------------------------------

/**
 * Filter tab definitions for the entity list page.
 *
 * The first entry ("all") is the unfiltered default; the remaining entries
 * correspond 1-to-1 with ENTITY_PRODUCING_TYPES.
 *
 * `value` is the URL query-param / API filter value.
 * `label` is the human-readable tab label.
 */
export const ENTITY_TYPE_TABS: Array<{ value: string; label: string }> = [
  { value: "all", label: "All" },
  { value: "person", label: "Person" },
  { value: "organization", label: "Organization" },
  { value: "place", label: "Place" },
  { value: "event", label: "Event" },
  { value: "work", label: "Work" },
  { value: "technical_term", label: "Technical Term" },
  { value: "concept", label: "Concept" },
  { value: "other", label: "Other" },
];

// ---------------------------------------------------------------------------
// Tooltips
// ---------------------------------------------------------------------------

/**
 * Tooltip definition strings for each entity_type value.
 *
 * Each value provides a short definition followed by representative examples
 * drawn from the types of content chronovista transcripts typically cover
 * (politics, economics, technology, history).
 */
export const ENTITY_TYPE_TOOLTIPS: Record<string, string> = {
  person:
    "A named human being. Examples: Alexandria Ocasio-Cortez, Edward Snowden, Adam Smith",
  organization:
    "A company, institution, government body, or formal group. Examples: Federal Reserve, NATO, OpenAI",
  place:
    "A named geographic location or region. Examples: Gaza Strip, Silicon Valley, European Union",
  event:
    "A named historical, political, or cultural event. Examples: January 6th, Bretton Woods Conference, Arab Spring",
  work:
    "A created artifact: book, film, law, treaty, software, or named project. Examples: The Wealth of Nations, Citizens United, GPT-4",
  technical_term:
    "A specific named method, technique, or mechanism from a specialized domain. Examples: GraphRAG, quantitative easing, filibuster",
  concept:
    "A broader idea, framework, principle, or abstraction. Examples: regulatory capture, neoliberalism, separation of powers",
  other:
    "An entity that doesn't fit the categories above. Review periodically for new type patterns.",
};

// ---------------------------------------------------------------------------
// Producing-types list
// ---------------------------------------------------------------------------

/**
 * The 8 entity_type keys that can appear as the `entity_type` field on a
 * NamedEntity record returned from the backend.
 *
 * Use this array in selectors, validators, and any component that needs to
 * enumerate only the concrete entity-producing types (i.e. excluding generic
 * topic/descriptor meta-types that are not surfaced in the UI).
 */
export const ENTITY_PRODUCING_TYPES: string[] = [
  "person",
  "organization",
  "place",
  "event",
  "work",
  "technical_term",
  "concept",
  "other",
];
