/**
 * EntitiesPage component displays the list of named entities with filters
 * and infinite scroll.
 *
 * Features (Feature 038):
 * - Filter by entity type (tabs: All, Person, Organization, Place, Event, Work, Other)
 * - "Has mentions" toggle filter
 * - Search by name
 * - Sort: Name (A-Z) or Mentions (desc)
 * - Card grid with type badge, mention count, video count, and description
 * - Click navigates to /entities/:entityId
 * - Infinite scroll pagination
 * - Loading skeleton, empty state, error state
 */

import { useEffect, useCallback } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { useEntities } from "../hooks/useEntityMentions";
import type { EntityListItem } from "../api/entityMentions";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const ENTITY_TYPE_TABS: Array<{ value: string; label: string }> = [
  { value: "all", label: "All" },
  { value: "person", label: "Person" },
  { value: "organization", label: "Organization" },
  { value: "place", label: "Place" },
  { value: "event", label: "Event" },
  { value: "work", label: "Work" },
  { value: "other", label: "Other" },
];

const VALID_TYPES = ENTITY_TYPE_TABS.map((t) => t.value);

const SORT_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "mentions", label: "Mentions" },
  { value: "name", label: "Name (A-Z)" },
];

/** Badge colour classes by entity type — matches EntityDetailPage */
const ENTITY_TYPE_COLORS: Record<string, string> = {
  person: "bg-indigo-100 text-indigo-700 border-indigo-200",
  organization: "bg-violet-100 text-violet-700 border-violet-200",
  place: "bg-emerald-100 text-emerald-700 border-emerald-200",
  event: "bg-amber-100 text-amber-700 border-amber-200",
  work: "bg-sky-100 text-sky-700 border-sky-200",
  concept: "bg-rose-100 text-rose-700 border-rose-200",
  other: "bg-slate-100 text-slate-700 border-slate-200",
};

const ENTITY_TYPE_LABELS: Record<string, string> = {
  person: "Person",
  organization: "Organization",
  place: "Place",
  event: "Event",
  work: "Work",
  concept: "Concept",
  other: "Other",
};

function getTypeBadgeClass(entityType: string): string {
  return (
    ENTITY_TYPE_COLORS[entityType] ?? "bg-slate-100 text-slate-700 border-slate-200"
  );
}

function getTypeLabel(entityType: string): string {
  return ENTITY_TYPE_LABELS[entityType] ?? entityType;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/**
 * Skeleton card for the entity loading state.
 */
function EntitySkeletonCard() {
  return (
    <div
      className="bg-white rounded-xl shadow-md border border-gray-100 p-5 animate-pulse"
      aria-hidden="true"
    >
      {/* Type badge skeleton */}
      <div className="h-5 w-24 bg-gray-200 rounded-full mb-3" />
      {/* Name skeleton */}
      <div className="h-5 bg-gray-200 rounded-md w-3/4 mb-3" />
      {/* Description skeleton */}
      <div className="h-4 bg-gray-200 rounded-md w-full mb-1" />
      <div className="h-4 bg-gray-200 rounded-md w-5/6 mb-4" />
      {/* Stats skeleton */}
      <div className="flex gap-4">
        <div className="h-4 bg-gray-200 rounded-md w-20" />
        <div className="h-4 bg-gray-200 rounded-md w-16" />
      </div>
    </div>
  );
}

function EntityLoadingState({ count = 8 }: { count?: number }) {
  return (
    <div
      className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6"
      role="status"
      aria-label="Loading entities"
      aria-live="polite"
      aria-busy="true"
    >
      {Array.from({ length: count }, (_, i) => (
        <EntitySkeletonCard key={i} />
      ))}
      <span className="sr-only">Loading entities...</span>
    </div>
  );
}

/**
 * Entity card — navigates to the entity detail page on click.
 */
function EntityCard({ entity }: { entity: EntityListItem }) {
  return (
    <Link
      to={`/entities/${entity.entity_id}`}
      className="block bg-white rounded-xl shadow-md border border-gray-100 p-5 hover:shadow-lg hover:border-gray-200 transition-all focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2"
      aria-label={`${entity.canonical_name} — ${entity.mention_count} mention${entity.mention_count === 1 ? "" : "s"} in ${entity.video_count} video${entity.video_count === 1 ? "" : "s"}`}
    >
      {/* Type badge */}
      <span
        className={`inline-flex items-center px-2.5 py-0.5 text-xs font-medium rounded-full border mb-3 ${getTypeBadgeClass(entity.entity_type)}`}
      >
        {getTypeLabel(entity.entity_type)}
      </span>

      {/* Entity name */}
      <h3 className="text-base font-semibold text-gray-900 mb-2 line-clamp-2">
        {entity.canonical_name}
      </h3>

      {/* Description snippet */}
      {entity.description ? (
        <p className="text-sm text-gray-500 mb-4 line-clamp-2">
          {entity.description}
        </p>
      ) : (
        <p className="text-sm text-gray-400 italic mb-4 line-clamp-1">
          No description available.
        </p>
      )}

      {/* Stats row */}
      <div className="flex items-center gap-4 text-xs text-gray-500">
        <span>
          <strong className="font-semibold text-gray-700">
            {entity.mention_count.toLocaleString()}
          </strong>{" "}
          mention{entity.mention_count === 1 ? "" : "s"}
        </span>
        <span>
          <strong className="font-semibold text-gray-700">
            {entity.video_count.toLocaleString()}
          </strong>{" "}
          video{entity.video_count === 1 ? "" : "s"}
        </span>
      </div>
    </Link>
  );
}

/**
 * Type filter tabs.
 */
interface TypeFilterTabsProps {
  currentType: string;
  onTypeChange: (type: string) => void;
}

function TypeFilterTabs({ currentType, onTypeChange }: TypeFilterTabsProps) {
  return (
    <nav aria-label="Entity type filter" role="tablist">
      <div className="flex flex-wrap gap-1 rounded-lg bg-gray-100 p-1">
        {ENTITY_TYPE_TABS.map((tab) => {
          const isActive = currentType === tab.value;
          return (
            <button
              key={tab.value}
              type="button"
              role="tab"
              aria-selected={isActive}
              onClick={() => onTypeChange(tab.value)}
              className={`min-h-[44px] px-3 py-2 rounded-md text-sm font-medium transition-colors whitespace-nowrap ${
                isActive
                  ? "bg-white text-gray-900 shadow-sm"
                  : "text-gray-600 hover:text-gray-900 hover:bg-gray-50"
              }`}
            >
              {tab.label}
            </button>
          );
        })}
      </div>
    </nav>
  );
}

/**
 * Pagination status: "Showing X of Y entities"
 */
function PaginationStatus({
  loadedCount,
  total,
}: {
  loadedCount: number;
  total: number | null;
}) {
  if (total === null) {
    return (
      <p className="text-sm text-gray-500 text-center py-2">
        Showing {loadedCount} entit{loadedCount !== 1 ? "ies" : "y"}
      </p>
    );
  }
  return (
    <p className="text-sm text-gray-500 text-center py-2">
      Showing {loadedCount} of {total} entit{total !== 1 ? "ies" : "y"}
    </p>
  );
}

/**
 * All-loaded message shown once the last page is fetched.
 */
function AllLoadedMessage({ total }: { total: number }) {
  return (
    <p className="text-sm text-gray-500 text-center py-4 border-t border-gray-200">
      All {total} entit{total !== 1 ? "ies" : "y"} loaded
    </p>
  );
}

/**
 * Empty state when no entities match the current filters.
 */
function EntitiesEmptyState({
  typeFilter,
  hasMentions,
  search,
}: {
  typeFilter: string;
  hasMentions: boolean;
  search: string;
}) {
  const hasActiveFilters = typeFilter !== "all" || hasMentions || search !== "";

  return (
    <div
      className="bg-white border border-gray-200 rounded-xl shadow-lg p-12 text-center flex flex-col items-center justify-center min-h-[400px]"
      role="status"
      aria-label="No entities found"
    >
      <div className="mx-auto w-20 h-20 mb-6 text-gray-400 bg-gray-100 rounded-full p-4">
        <svg
          xmlns="http://www.w3.org/2000/svg"
          fill="none"
          viewBox="0 0 24 24"
          strokeWidth={1.5}
          stroke="currentColor"
          aria-hidden="true"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M18 18.72a9.094 9.094 0 0 0 3.741-.479 3 3 0 0 0-4.682-2.72m.94 3.198.001.031c0 .225-.012.447-.037.666A11.944 11.944 0 0 1 12 21c-2.17 0-4.207-.576-5.963-1.584A6.062 6.062 0 0 1 6 18.719m12 0a5.971 5.971 0 0 0-.941-3.197m0 0A5.995 5.995 0 0 0 12 12.75a5.995 5.995 0 0 0-5.058 2.772m0 0a3 3 0 0 0-4.681 2.72 8.986 8.986 0 0 0 3.74.477m.94-3.197a5.971 5.971 0 0 0-.94 3.197M15 6.75a3 3 0 1 1-6 0 3 3 0 0 1 6 0Zm6 3a2.25 2.25 0 1 1-4.5 0 2.25 2.25 0 0 1 4.5 0Zm-13.5 0a2.25 2.25 0 1 1-4.5 0 2.25 2.25 0 0 1 4.5 0Z"
          />
        </svg>
      </div>

      <h3 className="text-xl font-semibold text-gray-900 mb-3">
        {hasActiveFilters ? "No entities match your filters" : "No entities yet"}
      </h3>

      <p className="text-gray-600 mb-6 max-w-sm">
        {hasActiveFilters
          ? "Try adjusting your filters or search term."
          : "Run the entity scan to detect named entities in your transcripts."}
      </p>

      {!hasActiveFilters && (
        <>
          <div className="inline-block mb-6">
            <code className="bg-gray-900 text-green-400 px-5 py-3 rounded-lg font-mono text-sm shadow-md block">
              $ chronovista entities scan
            </code>
          </div>
          <p className="text-sm text-gray-500 max-w-xs">
            This will scan your transcripts for people, organizations, places, and more.
          </p>
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page component
// ---------------------------------------------------------------------------

/**
 * EntitiesPage displays named entities with loading, error, and empty states.
 * Includes type filter tabs, has-mentions toggle, search input, sort dropdown,
 * and infinite scroll.
 */
export function EntitiesPage() {
  const [searchParams, setSearchParams] = useSearchParams();

  // Parse type filter from URL
  const typeParam = searchParams.get("type") ?? "all";
  const typeFilter = VALID_TYPES.includes(typeParam) ? typeParam : "all";

  // Parse has_mentions toggle
  const hasMentionsParam = searchParams.get("has_mentions");
  const hasMentions = hasMentionsParam === "true";

  // Parse search query
  const search = searchParams.get("search") ?? "";

  // Parse sort
  const sortParam = searchParams.get("sort") ?? "mentions";
  const sort = ["mentions", "name"].includes(sortParam) ? sortParam : "mentions";

  // Build hook params — only include optional fields when they have values so
  // that exactOptionalPropertyTypes is satisfied (undefined must be absent, not set).
  const hookParams: Parameters<typeof useEntities>[0] = {
    sort,
    ...(typeFilter !== "all" ? { type: typeFilter } : {}),
    ...(hasMentions ? { has_mentions: true as const } : {}),
    ...(search ? { search } : {}),
  };

  const {
    entities,
    total,
    loadedCount,
    isLoading,
    isError,
    error,
    hasNextPage,
    isFetchingNextPage,
    retry,
    loadMoreRef,
  } = useEntities(hookParams);

  // Set page title
  useEffect(() => {
    document.title = "Entities - ChronoVista";
    return () => {
      document.title = "ChronoVista";
    };
  }, []);

  // Scroll to top when filters change
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, [typeFilter, hasMentions, search, sort]);

  // Handlers
  const handleTypeChange = useCallback(
    (newType: string) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        if (newType === "all") {
          next.delete("type");
        } else {
          next.set("type", newType);
        }
        return next;
      });
    },
    [setSearchParams]
  );

  const handleHasMentionsToggle = useCallback(() => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      if (hasMentions) {
        next.delete("has_mentions");
      } else {
        next.set("has_mentions", "true");
      }
      return next;
    });
  }, [hasMentions, setSearchParams]);

  const handleSearchChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const value = e.target.value;
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        if (value) {
          next.set("search", value);
        } else {
          next.delete("search");
        }
        return next;
      });
    },
    [setSearchParams]
  );

  const handleSortChange = useCallback(
    (e: React.ChangeEvent<HTMLSelectElement>) => {
      const value = e.target.value;
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        if (value === "mentions") {
          next.delete("sort");
        } else {
          next.set("sort", value);
        }
        return next;
      });
    },
    [setSearchParams]
  );

  // Entity count header text
  const countText =
    total !== null
      ? `${total} entit${total !== 1 ? "ies" : "y"}`
      : null;

  // Error message extraction helper
  const extractErrorMessage = (err: unknown): string => {
    if (typeof err === "object" && err !== null && "message" in err) {
      return (err as { message: string }).message;
    }
    return "An error occurred while loading entities";
  };

  // Toolbar (shown in all states)
  const toolbar = (
    <div className="space-y-4 mb-6">
      {/* Type filter tabs */}
      <TypeFilterTabs
        currentType={typeFilter}
        onTypeChange={handleTypeChange}
      />

      {/* Search, has-mentions toggle, and sort */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-3">
        {/* Search input */}
        <div className="flex-1 relative">
          <label htmlFor="entity-search" className="sr-only">
            Search entities
          </label>
          <div className="pointer-events-none absolute inset-y-0 left-3 flex items-center">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 20 20"
              fill="currentColor"
              className="w-4 h-4 text-gray-400"
              aria-hidden="true"
            >
              <path
                fillRule="evenodd"
                d="M9 3.5a5.5 5.5 0 1 0 0 11 5.5 5.5 0 0 0 0-11ZM2 9a7 7 0 1 1 12.452 4.391l3.328 3.329a.75.75 0 1 1-1.06 1.06l-3.329-3.328A7 7 0 0 1 2 9Z"
                clipRule="evenodd"
              />
            </svg>
          </div>
          <input
            id="entity-search"
            type="search"
            placeholder="Search entities..."
            value={search}
            onChange={handleSearchChange}
            className="w-full pl-9 pr-4 py-2.5 text-sm border border-gray-300 rounded-lg bg-white text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition-colors"
          />
        </div>

        {/* Has mentions toggle */}
        <button
          type="button"
          role="switch"
          aria-checked={hasMentions}
          onClick={handleHasMentionsToggle}
          className={`inline-flex items-center gap-2 min-h-[44px] px-4 py-2 text-sm font-medium rounded-lg border transition-colors whitespace-nowrap ${
            hasMentions
              ? "bg-indigo-50 border-indigo-300 text-indigo-700"
              : "bg-white border-gray-300 text-gray-600 hover:bg-gray-50 hover:text-gray-900"
          }`}
        >
          <span
            className={`inline-block w-4 h-4 rounded-full border-2 flex-shrink-0 ${
              hasMentions
                ? "bg-indigo-600 border-indigo-600"
                : "bg-white border-gray-400"
            }`}
            aria-hidden="true"
          />
          Has mentions
        </button>

        {/* Sort dropdown */}
        <div className="flex items-center gap-2">
          <label
            htmlFor="entity-sort"
            className="text-sm font-medium text-gray-700 whitespace-nowrap"
          >
            Sort by
          </label>
          <select
            id="entity-sort"
            value={sort}
            onChange={handleSortChange}
            className="text-sm border border-gray-300 rounded-lg bg-white text-gray-900 py-2.5 pl-3 pr-8 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition-colors"
          >
            {SORT_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
      </div>
    </div>
  );

  // Initial loading state
  if (isLoading) {
    return (
      <main className="container mx-auto px-4 py-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-6">Entities</h1>
        {toolbar}
        <EntityLoadingState count={8} />
      </main>
    );
  }

  // Error state (only if no entities loaded)
  if (isError && entities.length === 0) {
    return (
      <main className="container mx-auto px-4 py-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-6">Entities</h1>
        {toolbar}
        <div
          className="bg-gradient-to-br from-red-50 to-amber-50 border border-red-200 rounded-xl shadow-lg p-8 text-center"
          role="alert"
          aria-live="polite"
        >
          <div className="mx-auto w-16 h-16 mb-5 text-red-500 bg-red-100 rounded-full p-3">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth={1.5}
              stroke="currentColor"
              aria-hidden="true"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z"
              />
            </svg>
          </div>

          <p className="text-sm font-semibold text-red-800 uppercase tracking-wider mb-2">
            Could not load entities
          </p>

          <p className="text-red-700 mb-8 max-w-md mx-auto">
            {extractErrorMessage(error)}
          </p>

          <button
            type="button"
            onClick={retry}
            className="inline-flex items-center px-6 py-3 bg-red-600 text-white font-semibold rounded-lg shadow-md hover:bg-red-700 hover:shadow-lg focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2 transition-all duration-200"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth={1.5}
              stroke="currentColor"
              className="w-5 h-5 mr-2"
              aria-hidden="true"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182m0-4.991v4.99"
              />
            </svg>
            Retry
          </button>
        </div>
      </main>
    );
  }

  // Empty state
  if (entities.length === 0) {
    return (
      <main className="container mx-auto px-4 py-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-6">Entities</h1>
        {toolbar}
        <EntitiesEmptyState
          typeFilter={typeFilter}
          hasMentions={hasMentions}
          search={search}
        />
      </main>
    );
  }

  // Entities list with pagination
  return (
    <main className="container mx-auto px-4 py-8">
      <div className="flex items-baseline justify-between mb-6">
        <h1 className="text-3xl font-bold text-gray-900">Entities</h1>
        {countText && (
          <span className="text-sm text-gray-500 ml-3" aria-hidden="true">
            {countText}
          </span>
        )}
      </div>

      {toolbar}

      {/* ARIA live region for count announcement */}
      {total !== null && (
        <div role="status" aria-live="polite" className="sr-only">
          Showing {total} entit{total !== 1 ? "ies" : "y"}
        </div>
      )}

      <div className="space-y-4">
        {/* Pagination status — top (only if more to load) */}
        {hasNextPage && (
          <PaginationStatus loadedCount={loadedCount} total={total} />
        )}

        {/* Entity cards grid */}
        <div
          className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6"
          role="list"
          aria-label="Entity list"
        >
          {entities.map((entity) => (
            <div key={entity.entity_id} role="listitem">
              <EntityCard entity={entity} />
            </div>
          ))}
        </div>

        {/* Loading more indicator */}
        {isFetchingNextPage && (
          <div aria-live="polite">
            <p className="text-sm text-gray-500 text-center py-2">
              Loading more entities...
            </p>
            <EntityLoadingState count={4} />
          </div>
        )}

        {/* Inline error when entities are loaded but next page fails */}
        {isError && entities.length > 0 && (
          <div
            className="bg-red-50 border border-red-200 rounded-lg p-4 text-center"
            role="alert"
          >
            <p className="text-red-800 font-medium mb-2">
              {extractErrorMessage(error)}
            </p>
            <button
              type="button"
              onClick={retry}
              className="inline-flex items-center px-4 py-2 bg-red-600 text-white font-medium rounded-md hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2 transition-colors"
            >
              Retry
            </button>
          </div>
        )}

        {/* Intersection Observer sentinel */}
        {!isError && (
          <div ref={loadMoreRef} className="h-4" aria-hidden="true" />
        )}

        {/* All loaded message */}
        {!hasNextPage && !isError && total !== null && total > 0 && (
          <AllLoadedMessage total={total} />
        )}
      </div>
    </main>
  );
}
