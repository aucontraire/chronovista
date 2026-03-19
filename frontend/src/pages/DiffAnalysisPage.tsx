/**
 * DiffAnalysisPage — ASR Error Patterns dashboard.
 *
 * Route: /corrections/diff-analysis
 *
 * Features (Feature 046, T013):
 * - Sortable table of DiffErrorPattern items (frequency sort only — FR-008)
 * - Client-side error token text filter (instant, no API call)
 * - Server-side entity name filter (debounced 300ms, sent as entityName param)
 * - "Show completed" toggle (server-side, default false) to include/exclude
 *   patterns where remaining_matches === 0
 * - Hidden live region announces sort direction changes (FR-028)
 * - Entity column: linked to /entities/{id} when entity_id is present
 * - "Find & Replace" action pre-fills BatchCorrectionsPage via router state (US2)
 * - Completed rows show a disabled "Completed" badge instead of "Find & Replace"
 * - Empty / loading / error states
 */

import { useState, useMemo, useCallback, useEffect, useRef } from "react";
import { Link, useNavigate } from "react-router-dom";

import { useDiffAnalysis } from "../hooks/useDiffAnalysis";
import type { DiffErrorPattern } from "../types/corrections";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type SortDirection = "asc" | "desc";

// ---------------------------------------------------------------------------
// Custom hook: debounce a value by `delay` ms
// ---------------------------------------------------------------------------

function useDebounce<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState<T>(value);

  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(id);
  }, [value, delay]);

  return debounced;
}

// ---------------------------------------------------------------------------
// Loading skeleton
// ---------------------------------------------------------------------------

function DiffAnalysisSkeleton() {
  return (
    <div
      className="animate-pulse"
      aria-label="Loading ASR error patterns"
      role="status"
    >
      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <div className="bg-slate-100 px-6 py-3 flex gap-6">
          {[100, 120, 80, 100, 90].map((w, i) => (
            <div
              key={i}
              className="h-4 rounded bg-slate-300"
              style={{ width: w }}
            />
          ))}
        </div>
        {[1, 2, 3, 4, 5].map((i) => (
          <div
            key={i}
            className="border-t border-slate-100 px-6 py-4 flex gap-6 items-center"
          >
            <div className="h-4 rounded bg-slate-200" style={{ width: 120 }} />
            <div className="h-4 rounded bg-slate-200" style={{ width: 140 }} />
            <div className="h-4 rounded bg-slate-200" style={{ width: 50 }} />
            <div className="h-4 rounded bg-slate-200" style={{ width: 110 }} />
            <div className="h-8 rounded bg-slate-200" style={{ width: 110 }} />
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sort icon (ascending / descending / neutral)
// ---------------------------------------------------------------------------

function SortIcon({ direction }: { direction: SortDirection | null }) {
  if (direction === "asc") {
    return (
      <svg
        aria-hidden="true"
        className="inline-block w-3.5 h-3.5 ml-1 flex-shrink-0"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
        strokeWidth={2.5}
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M5 15l7-7 7 7" />
      </svg>
    );
  }
  if (direction === "desc") {
    return (
      <svg
        aria-hidden="true"
        className="inline-block w-3.5 h-3.5 ml-1 flex-shrink-0"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
        strokeWidth={2.5}
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M19 9l-7 7-7-7" />
      </svg>
    );
  }
  // Neutral — no active sort
  return (
    <svg
      aria-hidden="true"
      className="inline-block w-3.5 h-3.5 ml-1 flex-shrink-0 opacity-40"
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M8 9l4-4 4 4M8 15l4 4 4-4" />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Table row
// ---------------------------------------------------------------------------

interface PatternRowProps {
  pattern: DiffErrorPattern;
  onFindAndReplace: (pattern: DiffErrorPattern) => void;
}

function PatternRow({ pattern, onFindAndReplace }: PatternRowProps) {
  const completed = pattern.remaining_matches === 0;

  return (
    <tr className={`hover:bg-slate-50 transition-colors${completed ? " opacity-60" : ""}`}>
      <td className="px-4 py-3 text-sm">
        <code className={`font-mono break-all${completed ? " text-slate-400" : " text-rose-700"}`}>
          {pattern.error_token}
        </code>
      </td>
      <td className="px-4 py-3 text-sm">
        <code className={`font-mono break-all${completed ? " text-slate-400" : " text-emerald-700"}`}>
          {pattern.canonical_form}
        </code>
      </td>
      <td className={`px-4 py-3 text-sm tabular-nums${completed ? " text-slate-400" : " text-slate-700"}`}>
        {pattern.frequency.toLocaleString()}
      </td>
      <td className="px-4 py-3 text-sm text-slate-600">
        {pattern.entity_id !== null && pattern.entity_name !== null ? (
          <Link
            to={`/entities/${pattern.entity_id}`}
            className="text-blue-600 hover:underline focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1 rounded"
          >
            {pattern.entity_name}
          </Link>
        ) : null}
      </td>
      <td className="px-4 py-3 text-right">
        {completed ? (
          <span
            className="inline-flex items-center px-3 py-1.5 text-xs font-medium text-slate-400 bg-slate-100 border border-slate-200 rounded-md cursor-default select-none"
            title="All instances corrected"
            aria-label={`Completed: ${pattern.error_token} → ${pattern.canonical_form}`}
          >
            Completed
          </span>
        ) : (
          <button
            type="button"
            onClick={() => onFindAndReplace(pattern)}
            className="inline-flex items-center px-3 py-1.5 text-xs font-medium text-blue-700 bg-blue-50 border border-blue-200 rounded-md hover:bg-blue-100 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 transition-colors"
            aria-label={`Find and replace: ${pattern.error_token} → ${pattern.canonical_form}`}
          >
            Find &amp; Replace
          </button>
        )}
      </td>
    </tr>
  );
}

// ---------------------------------------------------------------------------
// Main page component
// ---------------------------------------------------------------------------

/**
 * DiffAnalysisPage — sortable table of recurring ASR error patterns.
 *
 * Route: /corrections/diff-analysis
 */
export function DiffAnalysisPage() {
  const navigate = useNavigate();

  // -------------------------------------------------------------------------
  // Filter state
  // -------------------------------------------------------------------------

  /** Client-side text filter applied to error_token. Instant, no API call. */
  const [errorTokenSearch, setErrorTokenSearch] = useState("");

  /** Server-side entity name filter. Debounced before being sent to API. */
  const [entityNameInput, setEntityNameInput] = useState("");
  const debouncedEntityName = useDebounce(entityNameInput, 300);

  /**
   * Server-side toggle: when false (default), the API excludes patterns where
   * remaining_matches === 0. When true, completed patterns are included so the
   * user can see the full history.
   */
  const [showCompleted, setShowCompleted] = useState(false);

  // -------------------------------------------------------------------------
  // Sort state (frequency-only, FR-008)
  // -------------------------------------------------------------------------

  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");

  // -------------------------------------------------------------------------
  // Live region ref for sort announcements (FR-028)
  // -------------------------------------------------------------------------

  const liveRegionRef = useRef<HTMLDivElement>(null);

  const announceSortChange = useCallback((direction: SortDirection) => {
    if (liveRegionRef.current) {
      liveRegionRef.current.textContent = `Sorted by frequency, ${direction === "desc" ? "descending" : "ascending"}`;
    }
  }, []);

  const handleToggleSort = useCallback(() => {
    setSortDirection((prev) => {
      const next: SortDirection = prev === "desc" ? "asc" : "desc";
      announceSortChange(next);
      return next;
    });
  }, [announceSortChange]);

  // -------------------------------------------------------------------------
  // Data fetching
  // -------------------------------------------------------------------------

  const { data, isLoading, isError, error: queryError } = useDiffAnalysis({
    ...(debouncedEntityName ? { entityName: debouncedEntityName } : {}),
    showCompleted,
  });

  // -------------------------------------------------------------------------
  // Page title
  // -------------------------------------------------------------------------

  useEffect(() => {
    document.title = "ASR Error Patterns - ChronoVista";
    return () => {
      document.title = "ChronoVista";
    };
  }, []);

  // -------------------------------------------------------------------------
  // Derived: filtered + sorted patterns
  // -------------------------------------------------------------------------

  const filteredAndSortedPatterns = useMemo<DiffErrorPattern[]>(() => {
    const raw = data ?? [];

    // Client-side error token filter
    const filtered =
      errorTokenSearch.trim() === ""
        ? raw
        : raw.filter((p) =>
            p.error_token
              .toLowerCase()
              .includes(errorTokenSearch.trim().toLowerCase())
          );

    // Sort by frequency
    return [...filtered].sort((a, b) =>
      sortDirection === "desc"
        ? b.frequency - a.frequency
        : a.frequency - b.frequency
    );
  }, [data, errorTokenSearch, sortDirection]);

  const isEmpty =
    !isLoading && !isError && filteredAndSortedPatterns.length === 0;

  // -------------------------------------------------------------------------
  // Handlers
  // -------------------------------------------------------------------------

  /**
   * Navigate to BatchCorrectionsPage with pre-filled pattern and replacement.
   * Uses router state so the target page can consume and then clear it
   * (T014 / US2 cross-page pre-fill).
   */
  const handleFindAndReplace = useCallback(
    (pattern: DiffErrorPattern) => {
      // Wrap in \b word boundaries and enable regex mode so short tokens
      // like "Pari" don't match inside longer words like "Paris".
      const escaped = pattern.error_token.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      navigate("/corrections/batch", {
        state: {
          pattern: `\\b${escaped}\\b`,
          replacement: pattern.canonical_form,
          isRegex: true,
        },
      });
    },
    [navigate]
  );

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  return (
    <main className="container mx-auto px-4 py-8">
      {/* Hidden live region for sort announcements (FR-028) */}
      <div
        ref={liveRegionRef}
        role="status"
        aria-live="polite"
        aria-atomic="true"
        className="sr-only"
      />

      {/* Page header */}
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-gray-900">ASR Error Patterns</h1>
        <p className="mt-1 text-sm text-slate-500">
          Recurring ASR misrecognition patterns identified by word-level diff
          analysis. Use "Find &amp; Replace" to batch-correct any pattern across
          all transcripts.
        </p>
      </div>

      {/* Filters */}
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-start">
        {/* Error token search (client-side, instant) */}
        <div className="flex-1 space-y-1">
          <label
            htmlFor="error-token-filter"
            className="block text-sm font-medium text-slate-700"
          >
            Filter by error token
          </label>
          <input
            id="error-token-filter"
            type="search"
            value={errorTokenSearch}
            onChange={(e) => setErrorTokenSearch(e.target.value)}
            placeholder="e.g. barak, hussain…"
            className="w-full px-3 py-2 rounded-md border border-slate-300 bg-white text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors"
            aria-label="Filter patterns by error token"
          />
        </div>

        {/* Entity name filter (server-side, debounced) */}
        <div className="flex-1 space-y-1">
          <label
            htmlFor="entity-name-filter"
            className="block text-sm font-medium text-slate-700"
          >
            Filter by entity name
          </label>
          <input
            id="entity-name-filter"
            type="search"
            value={entityNameInput}
            onChange={(e) => setEntityNameInput(e.target.value)}
            placeholder="e.g. Barack Obama…"
            className="w-full px-3 py-2 rounded-md border border-slate-300 bg-white text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors"
            aria-label="Filter patterns by entity name"
            aria-describedby="entity-filter-hint"
          />
          <p id="entity-filter-hint" className="text-xs text-slate-400">
            Filters by associated named entity (server-side, ~300 ms delay)
          </p>
        </div>

        {/* Show completed toggle (server-side) */}
        <div className="flex items-center sm:mt-6 sm:pt-1">
          <label
            htmlFor="show-completed-toggle"
            className="flex items-center gap-2 text-sm font-medium text-slate-700 cursor-pointer select-none"
          >
            <input
              id="show-completed-toggle"
              type="checkbox"
              checked={showCompleted}
              onChange={(e) => setShowCompleted(e.target.checked)}
              className="h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-2 focus:ring-blue-500 focus:ring-offset-1 cursor-pointer"
            />
            Show completed
          </label>
        </div>
      </div>

      {/* Loading state */}
      {isLoading && <DiffAnalysisSkeleton />}

      {/* Query error state */}
      {isError && !isLoading && (
        <div
          className="rounded-xl bg-red-50 border border-red-200 p-6 text-sm text-red-700"
          role="alert"
        >
          Failed to load ASR error patterns.{" "}
          {queryError instanceof Error
            ? queryError.message
            : "Please try refreshing the page."}
        </div>
      )}

      {/* Empty state */}
      {isEmpty && (
        <div className="rounded-xl bg-white border border-slate-200 p-12 text-center shadow-sm">
          <div className="mx-auto mb-4 w-12 h-12 rounded-full bg-slate-100 flex items-center justify-center">
            <svg
              aria-hidden="true"
              className="w-6 h-6 text-slate-400"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              strokeWidth={1.5}
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M9 12h3.75M9 15h3.75M9 18h3.75m3 .75H18a2.25 2.25 0 0 0 2.25-2.25V6.108c0-1.135-.845-2.098-1.976-2.192a48.424 48.424 0 0 0-1.123-.08m-5.801 0c-.065.21-.1.433-.1.664 0 .414.336.75.75.75h4.5a.75.75 0 0 0 .75-.75 2.25 2.25 0 0 0-.1-.664m-5.8 0A2.251 2.251 0 0 1 13.5 2.25H15c1.012 0 1.867.668 2.15 1.586m-5.8 0c-.376.023-.75.05-1.124.08C9.095 4.01 8.25 4.973 8.25 6.108V8.25m0 0H4.875c-.621 0-1.125.504-1.125 1.125v11.25c0 .621.504 1.125 1.125 1.125h9.75c.621 0 1.125-.504 1.125-1.125V9.375c0-.621-.504-1.125-1.125-1.125H8.25Z" />
            </svg>
          </div>
          <p className="text-slate-600 font-medium">
            {errorTokenSearch.trim() !== "" || entityNameInput.trim() !== ""
              ? "No patterns match the current filters."
              : "No ASR error patterns found."}
          </p>
          <p className="mt-1 text-sm text-slate-400">
            {errorTokenSearch.trim() !== "" || entityNameInput.trim() !== ""
              ? "Try clearing the filters to see all patterns."
              : "Apply batch corrections to generate diff analysis data."}
          </p>
        </div>
      )}

      {/* Patterns table */}
      {filteredAndSortedPatterns.length > 0 && (
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200">
              <thead className="bg-slate-100">
                <tr>
                  <th
                    scope="col"
                    className="px-4 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider"
                  >
                    Error Token
                  </th>
                  <th
                    scope="col"
                    className="px-4 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider"
                  >
                    Canonical Form
                  </th>
                  {/* Sortable frequency column (FR-008) */}
                  <th
                    scope="col"
                    aria-sort={
                      sortDirection === "asc" ? "ascending" : "descending"
                    }
                    className="px-4 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider"
                  >
                    <button
                      type="button"
                      onClick={handleToggleSort}
                      className="inline-flex items-center gap-1 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1 rounded"
                      aria-label={`Sort by frequency, currently ${sortDirection === "desc" ? "descending" : "ascending"}. Click to sort ${sortDirection === "desc" ? "ascending" : "descending"}.`}
                    >
                      Frequency
                      <SortIcon direction={sortDirection} />
                    </button>
                  </th>
                  <th
                    scope="col"
                    className="px-4 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider"
                  >
                    Entity
                  </th>
                  <th scope="col" className="relative px-4 py-3">
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 bg-white">
                {filteredAndSortedPatterns.map((pattern) => (
                  <PatternRow
                    key={`${pattern.error_token}:${pattern.canonical_form}`}
                    pattern={pattern}
                    onFindAndReplace={handleFindAndReplace}
                  />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </main>
  );
}
