/**
 * EntityMentionsPanel component displays named entity chips grouped by type.
 *
 * Features:
 * - T028: Entity chips grouped by entity_type (People, Organizations, Places, …)
 * - T033: Each entity name links to /entities/{entity_id} (US8)
 * - Count badges (e.g., "Noam Chomsky (12)")
 * - Click handler scrolls the transcript to the first mention segment
 * - T009: [MANUAL] badge (emerald) for entities with manual associations
 * - T011: Always rendered (even when empty) so the search/link UI can appear
 * - T025: Entity search autocomplete with manual association (Feature 050, US1)
 * - Loading skeleton during fetch
 *
 * Accessibility:
 * - WCAG 2.1 AA: semantic sections with labeled headings
 * - Keyboard-navigable chip links
 * - Screen-reader-friendly role structure
 * - sr-only text for [MANUAL] badge
 * - Search input: role="searchbox", aria-label
 * - Results list: role="listbox", role="option" per result
 * - Disabled results: aria-disabled="true"
 */

import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import type { VideoEntitySummary } from "../api/entityMentions";
import { useEntitySearch } from "../hooks/useEntitySearch";
import {
  useCreateManualAssociation,
  useDeleteManualAssociation,
  useScanVideoEntities,
} from "../hooks/useEntityMentions";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface EntityMentionsPanelProps {
  /** Entity summaries to display (sorted by mention_count DESC). */
  entities: VideoEntitySummary[];
  /** Whether the data is still loading (shows skeleton). */
  isLoading: boolean;
  /**
   * The YouTube video ID — used to scope entity search `is_linked` context
   * and to create manual associations via `useCreateManualAssociation`.
   * Required for the search/link UI (T025, FR-024).
   */
  videoId: string;
  /**
   * Whether the video has at least one transcript. Controls visibility of
   * the "Scan for Entity Mentions" button (T012). When false the button is
   * not rendered because scanning requires transcript data.
   */
  hasTranscript?: boolean;
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
// UnlinkConfirmation (internal)
// ---------------------------------------------------------------------------

interface UnlinkConfirmationProps {
  /** Unique id used for data-testid attributes */
  id: string;
  /** Whether the delete mutation is in progress */
  isPending: boolean;
  /** Called when the user confirms the removal */
  onConfirm: () => void;
  /** Called when the user cancels or presses Escape */
  onCancel: () => void;
}

/**
 * Inline horizontal confirmation row for removing a manual entity association.
 *
 * Follows the RevertConfirmation pattern:
 * - Confirm button auto-focuses on mount (WCAG 2.4.3)
 * - Escape key cancels
 * - Amber colour scheme to signal a destructive action
 * - The message text satisfies FR-027
 */
function UnlinkConfirmation({
  id,
  isPending,
  onConfirm,
  onCancel,
}: UnlinkConfirmationProps) {
  const confirmButtonRef = useRef<HTMLButtonElement>(null);

  // WCAG 2.4.3: auto-focus Confirm button on mount.
  useEffect(() => {
    confirmButtonRef.current?.focus();
  }, []);

  // Allow Escape to cancel from anywhere (document-level listener).
  useEffect(() => {
    const handleDocKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onCancel();
      }
    };
    document.addEventListener("keydown", handleDocKeyDown);
    return () => document.removeEventListener("keydown", handleDocKeyDown);
  }, [onCancel]);

  const handleKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    event.stopPropagation();
    if (event.key === "Escape") {
      onCancel();
    }
  };

  return (
    <div
      className="mt-2 flex flex-wrap items-start gap-2 bg-amber-50 border border-amber-200 rounded-md px-3 py-2"
      onKeyDown={handleKeyDown}
    >
      {/* Warning icon */}
      <svg
        className="w-4 h-4 flex-shrink-0 text-amber-600 mt-0.5"
        fill="currentColor"
        viewBox="0 0 24 24"
        aria-hidden="true"
      >
        <path
          fillRule="evenodd"
          d="M9.401 3.003c1.155-2 4.043-2 5.197 0l7.355 12.748c1.154 2-.29 4.5-2.599 4.5H4.645c-2.309 0-3.752-2.5-2.598-4.5L9.4 3.003ZM12 8.25a.75.75 0 0 1 .75.75v3.75a.75.75 0 0 1-1.5 0V9a.75.75 0 0 1 .75-.75Zm0 8.25a.75.75 0 1 0 0-1.5.75.75 0 0 0 0 1.5Z"
          clipRule="evenodd"
        />
      </svg>

      {/* FR-027 confirmation message */}
      <span className="text-xs text-amber-900 flex-1">
        Only the manual association will be removed. Transcript-derived mentions
        will remain unaffected.
      </span>

      <div className="flex items-center gap-2">
        {/* Confirm button */}
        <button
          ref={confirmButtonRef}
          type="button"
          data-testid={`unlink-confirm-${id}`}
          onClick={onConfirm}
          disabled={isPending}
          aria-busy={isPending ? "true" : undefined}
          aria-label="Confirm removal of manual association"
          className="
            min-h-[44px] min-w-[44px]
            px-3 py-1
            text-sm font-medium text-white
            bg-amber-600 hover:bg-amber-700 disabled:bg-amber-400
            rounded-md
            focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-1
            transition-colors
          "
        >
          {isPending ? "Removing..." : "Remove"}
        </button>

        {/* Cancel button — always enabled */}
        <button
          type="button"
          data-testid={`unlink-cancel-${id}`}
          onClick={onCancel}
          aria-label="Cancel removal"
          className="
            min-h-[44px] min-w-[44px]
            px-3 py-1
            text-sm font-medium text-slate-700
            bg-white hover:bg-slate-50
            border border-slate-300
            rounded-md
            focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-1
            transition-colors
          "
        >
          Cancel
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// EntitySearchAutocomplete (internal)
// ---------------------------------------------------------------------------

interface EntitySearchAutocompleteProps {
  videoId: string;
}

/**
 * Inline entity search autocomplete widget.
 *
 * Renders a search input that queries the /entities/search endpoint via
 * useEntitySearch.  Results show the entity name, type, and (when present)
 * the matched alias.  Selecting an active, non-linked result calls
 * useCreateManualAssociation to create the association.
 *
 * Accessibility:
 * - role="searchbox" on the input
 * - role="listbox" on the results container
 * - role="option" on each result row
 * - aria-disabled="true" for already-linked and deprecated results
 * - role="status" loading indicator
 */
function EntitySearchAutocomplete({ videoId }: EntitySearchAutocompleteProps) {
  const [searchQuery, setSearchQuery] = useState("");
  // Tracks focus state so user.clear() (which fires focus) triggers a re-render
  // that picks up the updated hook return value (e.g., isBelowMinChars: true).
  const [, setFocusTick] = useState(0);

  // Debounce and API call handled inside the hook (NFR-004, 300 ms).
  const {
    entities: searchResults,
    isLoading: isSearching,
    isFetched,
    isBelowMinChars,
  } = useEntitySearch(searchQuery, videoId);

  const createMutation = useCreateManualAssociation();

  const showResults = !isBelowMinChars;
  const showEmpty =
    showResults && isFetched && !isSearching && searchResults.length === 0;
  const showList = showResults && searchResults.length > 0;

  return (
    <div className="space-y-2">
      {/* Label — visually styled as a small section header */}
      <p className="text-sm font-medium text-gray-700">Link an entity</p>

      {/* Search input */}
      <div className="relative">
        <input
          type="text"
          role="searchbox"
          aria-label="Search entities to link"
          placeholder="Search entities..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          onFocus={() => setFocusTick((t) => t + 1)}
          className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 placeholder-gray-400"
          autoComplete="off"
        />

        {/* Loading spinner */}
        {isSearching && (
          <div
            role="status"
            data-testid="entity-search-loading"
            className="absolute right-3 top-1/2 -translate-y-1/2"
          >
            <span className="sr-only">Searching entities…</span>
            <svg
              className="w-4 h-4 text-indigo-500 animate-spin"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
              />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8v8H4z"
              />
            </svg>
          </div>
        )}
      </div>

      {/* Empty results message */}
      {showEmpty && (
        <p className="text-sm text-gray-500 px-1">No matching entities</p>
      )}

      {/* Mutation error message */}
      {createMutation.isError && (
        <p className="text-sm text-red-600 px-1" role="alert">
          {(createMutation.error as { status?: number }).status === 409
            ? "This entity is already linked to the video."
            : (createMutation.error as { status?: number }).status === 422
              ? "This entity is deprecated and cannot be linked."
              : "Failed to link entity. Please try again."}
        </p>
      )}

      {/* Results dropdown */}
      {showList && (
        <ul
          role="listbox"
          aria-label="Search results"
          className="bg-white border border-gray-200 rounded-lg shadow-lg overflow-hidden divide-y divide-gray-100"
        >
          {searchResults.map((result) => {
            const hasManualLink = (result.link_sources ?? []).includes("manual");
            const isDeprecated = result.status === "deprecated";
            const isSelectable = !hasManualLink && !isDeprecated;

            return (
              <li
                key={result.entity_id}
                role="option"
                aria-selected={false}
                {...(!isSelectable ? { "aria-disabled": "true" } : {})}
              >
                {isSelectable ? (
                  /* Active, non-linked result — clickable button */
                  <button
                    type="button"
                    aria-label={result.canonical_name}
                    onClick={() => {
                      createMutation.mutate({
                        videoId,
                        entityId: result.entity_id,
                      });
                    }}
                    disabled={createMutation.isPending}
                    className="w-full flex items-center justify-between gap-2 px-3 py-2.5 text-left text-sm hover:bg-indigo-50 focus:outline-none focus:bg-indigo-50 transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
                  >
                    <span className="flex-1 min-w-0">
                      <span className="font-medium text-gray-900 truncate block">
                        {result.canonical_name}
                      </span>
                      {result.matched_alias && (
                        <span className="text-xs text-gray-500">
                          via &ldquo;{result.matched_alias}&rdquo;
                        </span>
                      )}
                    </span>
                    <span className="shrink-0 text-xs text-gray-400 capitalize">
                      {getTypeLabel(result.entity_type)}
                    </span>
                  </button>
                ) : (
                  /* Already-linked or deprecated — non-interactive display row */
                  <div
                    className="w-full flex items-center justify-between gap-2 px-3 py-2.5 text-sm cursor-default opacity-70"
                  >
                    <span className="flex-1 min-w-0">
                      <span className="font-medium text-gray-500 truncate block">
                        {result.canonical_name}
                      </span>
                      {result.matched_alias && (
                        <span className="text-xs text-gray-400">
                          via &ldquo;{result.matched_alias}&rdquo;
                        </span>
                      )}
                    </span>
                    <span className="shrink-0 flex items-center gap-1.5">
                      {isDeprecated && (
                        <span className="text-xs font-medium text-amber-600">
                          Deprecated
                        </span>
                      )}
                      {hasManualLink && !isDeprecated && (
                        <span className="text-xs text-gray-400">
                          Already linked
                        </span>
                      )}
                      <span className="text-xs text-gray-400 capitalize">
                        {getTypeLabel(result.entity_type)}
                      </span>
                    </span>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Spinner icon (used by the scan button)
// ---------------------------------------------------------------------------

function SpinnerIcon({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      className={className}
      aria-hidden="true"
    >
      <circle
        className="opacity-25"
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="4"
      />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
      />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

/**
 * EntityMentionsPanel renders entity chips grouped by type, plus an entity
 * search autocomplete widget for creating manual associations.
 *
 * Always renders the panel container so the search/link UI is consistently
 * visible even when no mentions exist. Shows an empty-state message when there
 * are no mentions and loading has finished. Shows skeleton while `isLoading`
 * is true.
 *
 * @example
 * ```tsx
 * <EntityMentionsPanel
 *   videoId={videoId}
 *   entities={entities}
 *   isLoading={isLoading}
 *   onEntityClick={(segId, ts) => scrollTranscriptTo(segId, ts)}
 * />
 * ```
 */
export function EntityMentionsPanel({
  entities,
  isLoading,
  videoId,
  hasTranscript = false,
  onEntityClick,
}: EntityMentionsPanelProps) {
  // T043: Track which entity's unlink confirmation is currently visible.
  const [unlinkingEntityId, setUnlinkingEntityId] = useState<string | null>(null);

  const deleteMutation = useDeleteManualAssociation();

  // T012: Scan for entity mentions in this video's transcripts.
  const scanMutation = useScanVideoEntities();

  const [scanMessage, setScanMessage] = useState<{
    text: string;
    kind: "success" | "error";
  } | null>(null);

  // Auto-dismiss the success message after 3 seconds.
  useEffect(() => {
    if (scanMessage?.kind !== "success") return;
    const timer = setTimeout(() => setScanMessage(null), 3000);
    return () => clearTimeout(timer);
  }, [scanMessage]);

  // Show skeleton while loading
  if (isLoading) {
    return <EntityMentionsSkeleton />;
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

      {/* T011: empty-state message when no mentions exist */}
      {entities.length === 0 && (
        <p className="text-sm text-gray-500">No entity mentions yet.</p>
      )}

      {/* Entity chip groups */}
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
                    videoId={videoId}
                    isUnlinking={unlinkingEntityId === entity.entity_id}
                    isDeletePending={
                      deleteMutation.isPending &&
                      unlinkingEntityId === entity.entity_id
                    }
                    onUnlinkClick={() =>
                      setUnlinkingEntityId(entity.entity_id)
                    }
                    onUnlinkCancel={() => setUnlinkingEntityId(null)}
                    onUnlinkConfirm={() => {
                      deleteMutation.mutate(
                        {
                          videoId,
                          entityId: entity.entity_id,
                        },
                        {
                          onSuccess: () => setUnlinkingEntityId(null),
                        },
                      );
                    }}
                    {...(onEntityClick !== undefined && { onEntityClick })}
                  />
                </div>
              ))}
            </div>
          </div>
        );
      })}

      {/* T025/FR-024: search/link UI — always rendered below chip groups */}
      <div className="border-t border-gray-100 pt-4">
        <EntitySearchAutocomplete videoId={videoId} />
      </div>

      {/* T012: Scan for Entity Mentions — only shown when transcripts exist */}
      {hasTranscript && (
        <div className="border-t border-gray-100 pt-4 flex flex-wrap items-center gap-3">
          <span
            title={scanMutation.isPending ? "A scan is already running" : undefined}
            className="inline-block"
          >
            <button
              type="button"
              disabled={scanMutation.isPending}
              aria-disabled={scanMutation.isPending}
              aria-busy={scanMutation.isPending ? "true" : undefined}
              onClick={() => {
                setScanMessage(null);
                scanMutation.reset();
                scanMutation.mutate(
                  { videoId, options: { sources: ["transcript", "title", "description"] } },
                  {
                    onSuccess: (result) => {
                      const { unique_entities, mentions_found } = result.data;
                      if (unique_entities === 0 && mentions_found === 0) {
                        setScanMessage({ text: "No entity mentions found", kind: "success" });
                      } else {
                        setScanMessage({
                          text: `Found ${unique_entities} ${unique_entities === 1 ? "entity" : "entities"} with ${mentions_found} ${mentions_found === 1 ? "mention" : "mentions"}`,
                          kind: "success",
                        });
                      }
                    },
                    onError: (err) => {
                      setScanMessage({
                        text: (err as { message?: string }).message ?? "Scan failed. Please try again.",
                        kind: "error",
                      });
                    },
                  }
                );
              }}
              className={`inline-flex items-center px-4 py-2 text-sm font-medium rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 transition-colors ${
                scanMutation.isPending
                  ? "bg-indigo-400 text-white cursor-not-allowed"
                  : "bg-indigo-600 hover:bg-indigo-700 text-white"
              }`}
            >
              {scanMutation.isPending ? (
                <>
                  <SpinnerIcon className="w-4 h-4 mr-2 animate-spin" />
                  Scanning...
                  <span className="sr-only">Scanning for mentions...</span>
                </>
              ) : (
                "Scan for Entity Mentions"
              )}
            </button>
          </span>

          {/* Inline result message */}
          {scanMessage !== null && (
            <p
              role={scanMessage.kind === "error" ? "alert" : "status"}
              aria-live={scanMessage.kind === "error" ? undefined : "polite"}
              className={`text-sm font-medium ${
                scanMessage.kind === "success"
                  ? "text-green-700"
                  : "text-red-700"
              }`}
            >
              {scanMessage.text}
            </p>
          )}
        </div>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// EntityChip (internal)
// ---------------------------------------------------------------------------

interface EntityChipProps {
  entity: VideoEntitySummary;
  onEntityClick?: (segmentId: number, timestamp: number) => void;
  /** The video ID this chip belongs to — needed for the unlink mutation. */
  videoId: string;
  /** Whether this chip's unlink confirmation is currently visible. */
  isUnlinking: boolean;
  /** Called when the unlink (X) button is clicked. */
  onUnlinkClick: () => void;
  /** Called when the unlink confirmation is cancelled. */
  onUnlinkCancel: () => void;
  /** Called when the unlink is confirmed. */
  onUnlinkConfirm: () => void;
  /** Whether the delete mutation is pending for this chip. */
  isDeletePending: boolean;
}

/**
 * Builds the aria-label for an entity chip, including mention count and manual
 * association status per WCAG 2.1 AA.
 */
function buildAriaLabel(entity: VideoEntitySummary): string {
  const hasTranscript = entity.mention_count > 0;
  const parts: string[] = [entity.canonical_name];

  if (hasTranscript) {
    parts.push(
      `${entity.mention_count} mention${entity.mention_count === 1 ? "" : "s"}`
    );
  }
  if (entity.has_manual) {
    parts.push("manually linked");
  }
  parts.push("View entity details.");
  return parts.join(", ");
}

/**
 * A single entity chip that:
 * 1. Links to the entity detail page (/entities/{entity_id}) (T033)
 * 2. Has a click handler that scrolls the transcript to the first mention
 *    (skipped when first_mention_time is null — manual-only association)
 * 3. Shows a [MANUAL] badge (emerald) when has_manual is true (T009)
 * 4. Shows an X unlink button when has_manual is true (T044)
 */
function EntityChip({
  entity,
  onEntityClick,
  isUnlinking,
  onUnlinkClick,
  onUnlinkCancel,
  onUnlinkConfirm,
  isDeletePending,
}: EntityChipProps) {
  const handleClick = () => {
    // T009: only scroll the transcript when a transcript mention exists.
    // Manual-only entities have first_mention_time === null — skip the callback
    // so the Link simply navigates to the entity detail page.
    if (onEntityClick && entity.first_mention_time !== null) {
      // segment_id is not available in VideoEntitySummary; pass 0 as sentinel.
      // The caller (VideoDetailPage) uses the timestamp to scroll via the
      // deep-link mechanism.
      onEntityClick(0, entity.first_mention_time);
    }
  };

  return (
    <div>
      <div className="inline-flex items-center gap-1">
        <Link
          to={`/entities/${entity.entity_id}`}
          onClick={handleClick}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-indigo-700 bg-indigo-50 border border-indigo-200 rounded-full hover:bg-indigo-100 hover:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 transition-colors"
          aria-label={buildAriaLabel(entity)}
        >
          <span>{entity.canonical_name}</span>

          {/* Transcript mention tally — hidden when mention_count is 0 */}
          {entity.mention_count > 0 && (
            <span
              className="text-xs font-normal text-indigo-500"
              aria-hidden="true"
            >
              ({entity.mention_count})
            </span>
          )}

          {/* T009: [MANUAL] badge — shown when a manual association exists */}
          {entity.has_manual && (
            <span
              className="inline-flex items-center px-1.5 py-0.5 text-xs font-medium text-emerald-700 bg-emerald-50 border border-emerald-200 rounded"
              aria-hidden="true"
            >
              MANUAL
            </span>
          )}

          {/* Screen-reader-only text for the manual badge */}
          {entity.has_manual && (
            <span className="sr-only">, manually linked</span>
          )}
        </Link>

        {/* T044: Unlink button — only shown when has_manual is true */}
        {entity.has_manual && (
          <button
            type="button"
            data-testid={`unlink-button-${entity.entity_id}`}
            aria-label={`Remove manual association for ${entity.canonical_name}`}
            onClick={(e) => {
              e.stopPropagation();
              e.preventDefault();
              onUnlinkClick();
            }}
            className="
              inline-flex items-center justify-center
              w-5 h-5
              text-slate-400 hover:text-amber-600
              rounded-full
              focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-500 focus-visible:ring-offset-1
              transition-colors
            "
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 20 20"
              fill="currentColor"
              className="w-3.5 h-3.5"
              aria-hidden="true"
            >
              <path d="M6.28 5.22a.75.75 0 0 0-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 1 0 1.06 1.06L10 11.06l3.72 3.72a.75.75 0 1 0 1.06-1.06L11.06 10l3.72-3.72a.75.75 0 0 0-1.06-1.06L10 8.94 6.28 5.22Z" />
            </svg>
          </button>
        )}
      </div>

      {/* Inline unlink confirmation — shown below the chip */}
      {isUnlinking && (
        <UnlinkConfirmation
          id={entity.entity_id}
          isPending={isDeletePending}
          onConfirm={onUnlinkConfirm}
          onCancel={onUnlinkCancel}
        />
      )}
    </div>
  );
}