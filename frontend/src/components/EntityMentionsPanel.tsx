/**
 * EntityMentionsPanel component displays named entity chips grouped by type.
 *
 * Features:
 * - T028: Entity chips grouped by entity_type (People, Organizations, Places, …)
 * - T033: Each entity name links to /entities/{entity_id} (US8)
 * - Count badges (e.g., "Noam Chomsky (12)")
 * - Click handler scrolls the transcript to the first mention segment
 * - Hidden when no mentions exist
 * - Loading skeleton during fetch
 *
 * Accessibility:
 * - WCAG 2.1 AA: semantic sections with labeled headings
 * - Keyboard-navigable chip links
 * - Screen-reader-friendly role structure
 */

import { Link } from "react-router-dom";

import type { VideoEntitySummary } from "../api/entityMentions";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface EntityMentionsPanelProps {
  /** Entity summaries to display (sorted by mention_count DESC). */
  entities: VideoEntitySummary[];
  /** Whether the data is still loading (shows skeleton). */
  isLoading: boolean;
  /**
   * Callback invoked when the user clicks an entity chip.
   * Receives the first-mention segment_id and timestamp so the caller can
   * scroll the transcript panel to that position.
   */
  onEntityClick?: (segmentId: number, timestamp: number) => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Human-readable label for each entity_type value from the backend. */
const ENTITY_TYPE_LABELS: Record<string, string> = {
  person: "People",
  organization: "Organizations",
  place: "Places",
  event: "Events",
  work: "Works",
  concept: "Concepts",
  other: "Other",
};

/** Priority order for rendering sections (most important first). */
const ENTITY_TYPE_ORDER = [
  "person",
  "organization",
  "place",
  "event",
  "work",
  "concept",
  "other",
];

function getTypeLabel(entityType: string): string {
  return ENTITY_TYPE_LABELS[entityType] ?? entityType;
}

/** Group entity summaries by entity_type. */
function groupByType(
  entities: VideoEntitySummary[]
): Map<string, VideoEntitySummary[]> {
  const groups = new Map<string, VideoEntitySummary[]>();
  for (const entity of entities) {
    const key = entity.entity_type;
    const existing = groups.get(key);
    if (existing) {
      existing.push(entity);
    } else {
      groups.set(key, [entity]);
    }
  }
  return groups;
}

/** Sort the group keys by the canonical order defined in ENTITY_TYPE_ORDER. */
function sortGroupKeys(keys: string[]): string[] {
  return [...keys].sort((a, b) => {
    const ai = ENTITY_TYPE_ORDER.indexOf(a);
    const bi = ENTITY_TYPE_ORDER.indexOf(b);
    const aIdx = ai === -1 ? ENTITY_TYPE_ORDER.length : ai;
    const bIdx = bi === -1 ? ENTITY_TYPE_ORDER.length : bi;
    return aIdx - bIdx;
  });
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/** A single skeleton chip placeholder. */
function ChipSkeleton() {
  return (
    <div
      data-testid="entity-chip-skeleton"
      className="h-8 w-28 rounded-full bg-slate-200 animate-pulse"
      aria-hidden="true"
    />
  );
}

/** Loading state: skeleton chips with a placeholder heading. */
function EntityMentionsSkeleton() {
  return (
    <section
      aria-label="Entity mentions loading"
      className="bg-white rounded-xl shadow-md border border-gray-100 p-6 lg:p-8 space-y-4"
    >
      <div className="h-5 w-40 rounded bg-slate-200 animate-pulse" aria-hidden="true" />
      <div className="flex flex-wrap gap-2">
        {Array.from({ length: 6 }).map((_, i) => (
          <ChipSkeleton key={i} />
        ))}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

/**
 * EntityMentionsPanel renders entity chips grouped by type.
 *
 * Hidden when `entities` is empty AND `isLoading` is false.
 * Shows skeleton while `isLoading` is true.
 *
 * @example
 * ```tsx
 * <EntityMentionsPanel
 *   entities={entities}
 *   isLoading={isLoading}
 *   onEntityClick={(segId, ts) => scrollTranscriptTo(segId, ts)}
 * />
 * ```
 */
export function EntityMentionsPanel({
  entities,
  isLoading,
  onEntityClick,
}: EntityMentionsPanelProps) {
  // Show skeleton while loading
  if (isLoading) {
    return <EntityMentionsSkeleton />;
  }

  // Hidden when there are no mentions
  if (entities.length === 0) {
    return null;
  }

  const groups = groupByType(entities);
  const orderedKeys = sortGroupKeys(Array.from(groups.keys()));

  return (
    <section
      aria-labelledby="entity-mentions-heading"
      className="bg-white rounded-xl shadow-md border border-gray-100 p-6 lg:p-8 space-y-6"
    >
      {/* Section heading */}
      <h3
        id="entity-mentions-heading"
        className="text-lg font-semibold text-gray-900"
      >
        Entity Mentions
      </h3>

      {orderedKeys.map((entityType) => {
        const group = groups.get(entityType);
        if (!group || group.length === 0) return null;
        const sectionId = `entity-type-${entityType}`;

        return (
          <div key={entityType}>
            {/* Type group heading */}
            <h4
              id={sectionId}
              className="text-sm font-medium text-gray-700 mb-2"
            >
              {getTypeLabel(entityType)}
            </h4>

            {/* Entity chips */}
            <div
              role="list"
              aria-labelledby={sectionId}
              className="flex flex-wrap gap-2"
            >
              {group.map((entity) => (
                <div key={entity.entity_id} role="listitem">
                  <EntityChip
                    entity={entity}
                    onEntityClick={onEntityClick}
                  />
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </section>
  );
}

// ---------------------------------------------------------------------------
// EntityChip (internal)
// ---------------------------------------------------------------------------

interface EntityChipProps {
  entity: VideoEntitySummary;
  onEntityClick?: (segmentId: number, timestamp: number) => void;
}

/**
 * A single entity chip that:
 * 1. Links to the entity detail page (/entities/{entity_id}) (T033)
 * 2. Has a click handler that scrolls the transcript to the first mention
 */
function EntityChip({ entity, onEntityClick }: EntityChipProps) {
  const handleClick = () => {
    if (onEntityClick) {
      // Use first_mention_time as timestamp; segment_id is not available in
      // VideoEntitySummary, so pass 0 as sentinel — the caller (VideoDetailPage)
      // will use the timestamp to scroll via the deep-link mechanism.
      onEntityClick(0, entity.first_mention_time);
    }
  };

  return (
    <Link
      to={`/entities/${entity.entity_id}`}
      onClick={handleClick}
      className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-indigo-700 bg-indigo-50 border border-indigo-200 rounded-full hover:bg-indigo-100 hover:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 transition-colors"
      aria-label={`${entity.canonical_name}, ${entity.mention_count} mention${entity.mention_count === 1 ? "" : "s"}. View entity details.`}
    >
      <span>{entity.canonical_name}</span>
      <span
        className="text-xs font-normal text-indigo-500"
        aria-hidden="true"
      >
        ({entity.mention_count})
      </span>
    </Link>
  );
}
