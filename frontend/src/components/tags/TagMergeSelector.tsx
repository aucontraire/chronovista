/**
 * TagMergeSelector Component (Feature 056)
 *
 * Contains-mode tag search for the merge workflow, plus multi-source
 * selection and single-target designation.
 *
 * Implements:
 * - T030: Contains-mode search (useCanonicalTags with matchMode: "contains",
 *   limit: 50), multi-source selection, and target designation
 * - FR-006: One or more source tags may be selected
 * - FR-007: Exactly one target tag, distinct from every source
 * - FR-011: A tag cannot be both a source and the target of the same merge
 * - FR-012: Duplicate source selections are prevented
 * - FR-018: WCAG 2.1 AA — keyboard operability, ARIA roles/labels, visible
 *   focus, screen-reader announcements for state changes
 *
 * Search UX intentionally differs from TagAutocomplete's single-select
 * combobox: each result offers two independent actions ("Add as source" /
 * "Set as target"), which does not fit a single-selection combobox pattern.
 * Results are rendered as a labelled list of buttons instead — fully
 * keyboard operable via Tab, with a live region announcing result counts.
 */

import { useId, useState } from "react";

import { useCanonicalTags } from "../../hooks/useCanonicalTags";
import type { SelectedMergeTag } from "../../types/canonical-tags";
import { isApiError } from "../../api/config";

/** Minimum characters required before a contains-mode search fires (FR-003). */
const MIN_QUERY_LENGTH = 2;

/** Per-surface result limit for the merge search (FR-005, SC-006). */
const MERGE_SEARCH_LIMIT = 50;

export interface TagMergeSelectorProps {
  /** Currently selected source tags (absorbed and marked merged). */
  sources: SelectedMergeTag[];
  /** Currently designated target tag (the surviving canonical tag), or null. */
  target: SelectedMergeTag | null;
  /** Called with a validated tag to add as a new source. */
  onAddSource: (tag: SelectedMergeTag) => void;
  /** Called with a source's normalized_form to remove it from the selection. */
  onRemoveSource: (normalizedForm: string) => void;
  /** Called with a validated tag to designate as the target, or null to clear it. */
  onSetTarget: (tag: SelectedMergeTag | null) => void;
  /** Disables all interactive controls while a merge is in flight. */
  disabled?: boolean;
}

/** A small removable pill for a selected source or target tag. */
function SelectedTagPill({
  tag,
  variant,
  onRemove,
  disabled,
}: {
  tag: SelectedMergeTag;
  variant: "source" | "target";
  onRemove: () => void;
  disabled: boolean;
}) {
  const colorClasses =
    variant === "target"
      ? "bg-green-100 text-green-800 border-green-300"
      : "bg-blue-100 text-blue-800 border-blue-300";

  return (
    <li
      className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium border ${colorClasses}`}
    >
      <span>{tag.canonical_form}</span>
      <button
        type="button"
        onClick={onRemove}
        disabled={disabled}
        aria-label={`Remove ${tag.canonical_form} as ${variant}`}
        className="inline-flex items-center justify-center min-w-[24px] min-h-[24px] -me-1 rounded-full hover:bg-black/10 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1 disabled:opacity-50 disabled:cursor-not-allowed"
      >
        <svg
          className="w-3 h-3"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          aria-hidden="true"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M6 18L18 6M6 6l12 12"
          />
        </svg>
      </button>
    </li>
  );
}

export function TagMergeSelector({
  sources,
  target,
  onAddSource,
  onRemoveSource,
  onSetTarget,
  disabled = false,
}: TagMergeSelectorProps) {
  const [query, setQuery] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);

  const inputId = useId();
  const descriptionId = useId();
  const resultsId = useId();
  const announcementId = useId();
  const errorId = useId();

  const { tags, suggestions, isLoading, isError, error } = useCanonicalTags(
    query,
    { matchMode: "contains", limit: MERGE_SEARCH_LIMIT }
  );

  const trimmedQuery = query.trim();
  const hasValidQuery = trimmedQuery.length >= MIN_QUERY_LENGTH;
  const showResults = hasValidQuery && !isLoading && !isError;
  const showNoMatches =
    showResults && tags.length === 0 && (suggestions ?? []).length === 0;

  const sourceNormalizedForms = new Set(sources.map((s) => s.normalized_form));
  const isSource = (tag: SelectedMergeTag) =>
    sourceNormalizedForms.has(tag.normalized_form);
  const isTarget = (tag: SelectedMergeTag) =>
    target !== null && target.normalized_form === tag.normalized_form;

  function toMergeTag(tag: {
    canonical_form: string;
    normalized_form: string;
    alias_count: number;
    video_count?: number;
  }): SelectedMergeTag {
    return {
      canonical_form: tag.canonical_form,
      normalized_form: tag.normalized_form,
      alias_count: tag.alias_count,
      video_count: tag.video_count ?? 0,
    };
  }

  function handleAddSource(tag: SelectedMergeTag) {
    if (isTarget(tag)) {
      // FR-011: a tag cannot be both a source and the target.
      setValidationError(
        `"${tag.canonical_form}" is already the target — a tag cannot be both a source and the target.`
      );
      return;
    }
    if (isSource(tag)) {
      // FR-012: prevent duplicate source selections.
      setValidationError(`"${tag.canonical_form}" is already selected as a source.`);
      return;
    }
    setValidationError(null);
    onAddSource(tag);
  }

  function handleSetTarget(tag: SelectedMergeTag) {
    if (isSource(tag)) {
      // FR-011: a tag cannot be both a source and the target.
      setValidationError(
        `"${tag.canonical_form}" is already a source — remove it as a source before setting it as the target.`
      );
      return;
    }
    setValidationError(null);
    onSetTarget(tag);
  }

  let announcementText = "";
  if (hasValidQuery && !isLoading) {
    if (tags.length > 0) {
      announcementText = `${tags.length} tag${tags.length === 1 ? "" : "s"} found`;
    } else if ((suggestions ?? []).length > 0) {
      announcementText = "No exact matches. Suggestions available.";
    } else {
      announcementText = `No tags found matching "${trimmedQuery}"`;
    }
  }

  return (
    <div className="space-y-4">
      {/* Search input */}
      <div>
        <label htmlFor={inputId} className="block text-sm font-medium text-slate-900">
          Search tags to merge
        </label>
        <div className="relative mt-1">
          <input
            id={inputId}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            disabled={disabled}
            aria-describedby={descriptionId}
            aria-controls={showResults ? resultsId : undefined}
            placeholder="Type at least 2 characters..."
            className="w-full px-4 py-2.5 text-base border rounded-lg text-slate-900 placeholder-slate-500 border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:bg-slate-100 disabled:cursor-not-allowed"
          />
          {isLoading && hasValidQuery && (
            <div className="absolute right-3 top-1/2 -translate-y-1/2">
              <div
                className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin"
                aria-hidden="true"
              />
            </div>
          )}
        </div>
        <p id={descriptionId} className="mt-1 text-xs text-slate-500">
          Searches canonical form, variations, and aliases at any position (min. 2
          characters).
        </p>
      </div>

      {/* Screen reader announcement region */}
      <div
        id={announcementId}
        role="status"
        aria-live="polite"
        aria-atomic="true"
        className="sr-only"
      >
        {announcementText}
      </div>

      {/* Error state */}
      {hasValidQuery && isError && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-lg" role="alert">
          <p className="text-sm text-red-800">
            {isApiError(error) && error.type === "timeout"
              ? "Request timed out. Please try again."
              : "Error loading tags. Please try again."}
          </p>
        </div>
      )}

      {/* No matches (edge case) */}
      {showNoMatches && (
        <p className="text-sm text-slate-500">
          No tags found matching &ldquo;{trimmedQuery}&rdquo;.
        </p>
      )}

      {/* Results list */}
      {showResults && tags.length > 0 && (
        <ul
          id={resultsId}
          role="list"
          aria-label="Tag search results"
          className="divide-y divide-slate-100 border border-slate-200 rounded-lg max-h-72 overflow-auto"
        >
          {tags.map((tag) => {
            const mergeTag = toMergeTag(tag);
            const alreadySource = isSource(mergeTag);
            const alreadyTarget = isTarget(mergeTag);
            return (
              <li
                key={tag.normalized_form}
                className="flex items-center justify-between gap-3 px-4 py-2.5"
              >
                <div className="min-w-0">
                  <p className="text-sm font-medium text-slate-900 truncate">
                    {tag.canonical_form}
                  </p>
                  <p className="text-xs text-slate-500">
                    {tag.video_count} videos · {tag.alias_count} alias
                    {tag.alias_count === 1 ? "" : "es"}
                  </p>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  <button
                    type="button"
                    onClick={() => handleAddSource(mergeTag)}
                    disabled={disabled || alreadySource || alreadyTarget}
                    aria-label={`Add ${tag.canonical_form} as a source tag`}
                    className="px-2.5 py-1.5 min-h-[36px] text-xs font-medium rounded-md border border-blue-300 text-blue-700 bg-blue-50 hover:bg-blue-100 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {alreadySource ? "Added" : "+ Source"}
                  </button>
                  <button
                    type="button"
                    onClick={() => handleSetTarget(mergeTag)}
                    disabled={disabled || alreadyTarget || alreadySource}
                    aria-label={`Set ${tag.canonical_form} as the merge target`}
                    className="px-2.5 py-1.5 min-h-[36px] text-xs font-medium rounded-md border border-green-300 text-green-700 bg-green-50 hover:bg-green-100 focus:outline-none focus:ring-2 focus:ring-green-500 focus:ring-offset-1 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {alreadyTarget ? "Target" : "Set target"}
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      )}

      {/* Fuzzy suggestions fallback when contains-mode finds no matches */}
      {showResults && tags.length === 0 && (suggestions ?? []).length > 0 && (
        <div role="group" aria-label="Fuzzy suggestions" className="text-sm">
          <span className="font-medium text-slate-700">Did you mean: </span>
          {(suggestions ?? []).map((s, index) => (
            <span key={s.normalized_form}>
              <button
                type="button"
                onClick={() =>
                  handleAddSource({
                    canonical_form: s.canonical_form,
                    normalized_form: s.normalized_form,
                    alias_count: 1,
                    video_count: 0,
                  })
                }
                className="text-blue-600 hover:text-blue-800 hover:underline focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1 rounded px-0.5"
              >
                {s.canonical_form}
              </button>
              {index < (suggestions ?? []).length - 1 && <span>, </span>}
            </span>
          ))}
          <span>?</span>
        </div>
      )}

      {/* Validation error (FR-011, FR-012) */}
      {validationError && (
        <p id={errorId} role="alert" className="text-sm text-red-700">
          {validationError}
        </p>
      )}

      {/* Target tag */}
      <div>
        <h3 className="text-sm font-semibold text-slate-900">Target tag</h3>
        <p className="text-xs text-slate-500 mb-1.5">
          The canonical tag that survives — all sources fold into it.
        </p>
        {target === null ? (
          <p className="text-sm text-slate-400">No target selected yet.</p>
        ) : (
          <ul role="list" className="flex flex-wrap gap-2">
            <SelectedTagPill
              tag={target}
              variant="target"
              onRemove={() => onSetTarget(null)}
              disabled={disabled}
            />
          </ul>
        )}
      </div>

      {/* Source tags */}
      <div>
        <h3 className="text-sm font-semibold text-slate-900">
          Source tags
          <span className="ml-1.5 text-xs font-normal text-slate-500">
            ({sources.length})
          </span>
        </h3>
        <p className="text-xs text-slate-500 mb-1.5">
          Tags absorbed into the target and marked merged.
        </p>
        {sources.length === 0 ? (
          <p className="text-sm text-slate-400">No source tags selected yet.</p>
        ) : (
          <ul role="list" className="flex flex-wrap gap-2">
            {sources.map((tag) => (
              <SelectedTagPill
                key={tag.normalized_form}
                tag={tag}
                variant="source"
                onRemove={() => onRemoveSource(tag.normalized_form)}
                disabled={disabled}
              />
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
