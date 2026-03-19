/**
 * PhoneticVariantsSection — collapsible section that shows suspected ASR
 * phonetic variants of a named entity's name.
 *
 * The section is collapsed by default and only fetches data when expanded
 * (lazy loading). Each row lets the user:
 * - Register the original_text as an entity alias (name_variant type).
 * - Navigate to the batch find-replace page pre-filled with the suggestion.
 *
 * Confidence threshold slider (aria-valuetext, step 0.05) filters results
 * client-side without triggering a refetch.
 *
 * Features (Feature 046, US4):
 * - Collapsible disclosure with aria-expanded on the toggle button
 * - Lazy fetch: query enabled only when expanded
 * - Confidence range input with ARIA value announcement
 * - Register as Alias: POST to /entities/{id}/aliases, then invalidate cache
 * - Find & Replace: navigate to /corrections/batch with pre-filled state
 * - Loading, empty, and error states
 */

import { useState, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import { usePhoneticMatches } from "../../hooks/usePhoneticMatches";
import { createEntityAlias } from "../../api/entityMentions";
import type { PhoneticMatch } from "../../types/corrections";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface PhoneticVariantsSectionProps {
  /** UUID of the named entity to fetch phonetic variants for. */
  entityId: string;
}

// ---------------------------------------------------------------------------
// Icons (inline SVG — no icon library dependency)
// ---------------------------------------------------------------------------

function ChevronDownIcon({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      strokeWidth={1.5}
      stroke="currentColor"
      className={className}
      aria-hidden="true"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="m19.5 8.25-7.5 7.5-7.5-7.5"
      />
    </svg>
  );
}

function ChevronUpIcon({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      strokeWidth={1.5}
      stroke="currentColor"
      className={className}
      aria-hidden="true"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="m4.5 15.75 7.5-7.5 7.5 7.5"
      />
    </svg>
  );
}

function CheckIcon({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      strokeWidth={2}
      stroke="currentColor"
      className={className}
      aria-hidden="true"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="m4.5 12.75 6 6 9-13.5"
      />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Loading skeleton
// ---------------------------------------------------------------------------

function PhoneticSkeleton() {
  return (
    <div
      className="animate-pulse space-y-3 mt-4"
      role="status"
      aria-label="Loading phonetic variants"
    >
      {[1, 2, 3].map((i) => (
        <div
          key={i}
          className="rounded-lg border border-slate-200 bg-white p-4 space-y-2"
        >
          <div className="h-3 w-1/2 rounded bg-slate-200" />
          <div className="h-3 w-3/4 rounded bg-slate-200" />
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Row action state
// ---------------------------------------------------------------------------

type RowActionState =
  | { kind: "idle" }
  | { kind: "pending" }
  | { kind: "registered" }
  | { kind: "error"; message: string };

// ---------------------------------------------------------------------------
// Match row
// ---------------------------------------------------------------------------

interface MatchRowProps {
  match: PhoneticMatch;
  entityId: string;
  onAliasRegistered: () => void;
}

function MatchRow({ match, entityId, onAliasRegistered }: MatchRowProps) {
  const navigate = useNavigate();
  const [actionState, setActionState] = useState<RowActionState>({
    kind: "idle",
  });
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Clean up error auto-dismiss timer on unmount.
  useEffect(() => {
    return () => {
      if (timerRef.current !== null) {
        clearTimeout(timerRef.current);
      }
    };
  }, []);

  const confidencePct = Math.round(match.confidence * 100);

  async function handleRegisterAlias() {
    if (actionState.kind === "pending" || actionState.kind === "registered") {
      return;
    }
    setActionState({ kind: "pending" });
    try {
      await createEntityAlias(entityId, match.original_text, "name_variant");
      setActionState({ kind: "registered" });
      onAliasRegistered();
    } catch (err: unknown) {
      const status = (err as { status?: number } | null)?.status;
      let message = "Failed to register alias. Please try again.";
      if (status === 409) {
        message = "This alias already exists.";
      } else if (status === 404) {
        message = "Entity not found.";
      }
      setActionState({ kind: "error", message });
      // Auto-dismiss error after 4 seconds.
      timerRef.current = setTimeout(() => {
        setActionState({ kind: "idle" });
        timerRef.current = null;
      }, 4000);
    }
  }

  function handleFindAndReplace() {
    navigate("/corrections/batch", {
      state: {
        pattern: match.original_text,
        replacement: match.proposed_correction,
      },
    });
  }

  const isRegistered = actionState.kind === "registered";
  const isPending = actionState.kind === "pending";

  return (
    <tr className="hover:bg-slate-50 transition-colors">
      {/* Original text */}
      <td className="px-4 py-3 text-sm text-gray-900 font-mono">
        {match.original_text}
      </td>

      {/* Proposed correction */}
      <td className="px-4 py-3 text-sm text-gray-900 font-mono">
        {match.proposed_correction}
      </td>

      {/* Confidence */}
      <td className="px-4 py-3 text-sm text-gray-500 tabular-nums whitespace-nowrap">
        <span
          className="inline-flex items-center rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-700"
          aria-label={`${confidencePct}% confidence`}
        >
          {confidencePct}%
        </span>
      </td>

      {/* Evidence */}
      <td className="px-4 py-3 text-sm text-gray-500">
        {match.evidence_description}
      </td>

      {/* Video title */}
      <td className="px-4 py-3 text-sm text-gray-500">
        {match.video_title ?? (
          <span className="italic text-gray-400">Unknown video</span>
        )}
      </td>

      {/* Actions */}
      <td className="px-4 py-3 whitespace-nowrap">
        <div className="flex items-center gap-2">
          {/* Register as Alias button */}
          {isRegistered ? (
            <span
              className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-green-700 bg-green-50 border border-green-200 rounded-md"
              aria-label="Alias registered"
            >
              <CheckIcon className="w-3.5 h-3.5" />
              Registered
            </span>
          ) : (
            <button
              type="button"
              onClick={handleRegisterAlias}
              disabled={isPending}
              aria-label={`Register "${match.original_text}" as alias`}
              className="inline-flex items-center px-3 py-1.5 text-xs font-medium text-indigo-700 bg-indigo-50 border border-indigo-200 rounded-md hover:bg-indigo-100 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-1 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {isPending ? "Registering…" : "Register as Alias"}
            </button>
          )}

          {/* Find & Replace button */}
          <button
            type="button"
            onClick={handleFindAndReplace}
            aria-label={`Find and replace "${match.original_text}" with "${match.proposed_correction}"`}
            className="inline-flex items-center px-3 py-1.5 text-xs font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-1 transition-colors"
          >
            Find &amp; Replace
          </button>
        </div>

        {/* Inline error feedback */}
        {actionState.kind === "error" && (
          <p className="mt-1 text-xs text-red-600" role="alert">
            {actionState.message}
          </p>
        )}
      </td>
    </tr>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

/**
 * PhoneticVariantsSection renders a collapsible card showing suspected ASR
 * phonetic variants of the entity name.
 *
 * Data is only fetched when the user expands the section (lazy loading).
 * A confidence slider lets the user filter results client-side without
 * triggering additional network requests.
 */
export function PhoneticVariantsSection({
  entityId,
}: PhoneticVariantsSectionProps) {
  const queryClient = useQueryClient();
  const [isExpanded, setIsExpanded] = useState(false);
  const [displayThreshold, setDisplayThreshold] = useState(0.5);

  const { data: matches, isLoading, isError } = usePhoneticMatches({
    entityId,
    serverFloor: 0.3,
    displayThreshold,
    enabled: isExpanded,
  });

  const contentId = `phonetic-variants-content-${entityId}`;

  function handleAliasRegistered() {
    // Invalidate all relevant query caches.
    void queryClient.invalidateQueries({
      queryKey: ["entity-detail", entityId],
    });
    void queryClient.invalidateQueries({ queryKey: ["entity-mentions"] });
    void queryClient.invalidateQueries({ queryKey: ["phonetic-matches"] });
    void queryClient.invalidateQueries({ queryKey: ["diff-analysis"] });
  }

  const thresholdPct = Math.round(displayThreshold * 100);

  return (
    <section aria-labelledby="phonetic-variants-heading" className="mb-6">
      {/* Collapsible header */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
        <button
          type="button"
          id="phonetic-variants-heading"
          aria-expanded={isExpanded}
          aria-controls={contentId}
          onClick={() => setIsExpanded((prev) => !prev)}
          className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-inset focus:ring-indigo-500 transition-colors"
        >
          <div>
            <h2 className="text-base font-semibold text-gray-900">
              Suspected ASR Variants
            </h2>
            <p className="text-xs text-gray-500 mt-0.5">
              Phonetic matches that may represent misrecognised versions of this
              entity name in transcripts.
            </p>
          </div>
          {isExpanded ? (
            <ChevronUpIcon className="w-5 h-5 text-gray-400 flex-shrink-0 ml-3" />
          ) : (
            <ChevronDownIcon className="w-5 h-5 text-gray-400 flex-shrink-0 ml-3" />
          )}
        </button>

        {/* Collapsible body */}
        {isExpanded && (
          <div id={contentId} className="px-4 pb-4 border-t border-slate-100">
            {/* Confidence threshold slider */}
            <div className="flex items-center gap-3 py-3">
              <label
                htmlFor="phonetic-confidence-slider"
                className="text-xs font-medium text-gray-600 whitespace-nowrap"
              >
                Min confidence:
              </label>
              <input
                id="phonetic-confidence-slider"
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={displayThreshold}
                onChange={(e) =>
                  setDisplayThreshold(parseFloat(e.target.value))
                }
                aria-label="Confidence threshold"
                aria-valuemin={0}
                aria-valuemax={1}
                aria-valuenow={displayThreshold}
                aria-valuetext={`Confidence threshold: ${thresholdPct}%`}
                className="flex-1 h-2 accent-indigo-600 cursor-pointer"
              />
              <span className="text-xs font-medium text-gray-700 tabular-nums w-10 text-right">
                {thresholdPct}%
              </span>
            </div>

            {/* aria-live region for loading → loaded announcement */}
            <div aria-live="polite" aria-atomic="true" className="sr-only">
              {isLoading
                ? "Loading phonetic variants"
                : `${matches?.length ?? 0} phonetic variant${(matches?.length ?? 0) === 1 ? "" : "s"} loaded`}
            </div>

            {/* Loading state */}
            {isLoading && <PhoneticSkeleton />}

            {/* Error state */}
            {isError && !isLoading && (
              <div
                role="alert"
                className="mt-3 rounded-lg bg-red-50 border border-red-200 p-4 text-sm text-red-700"
              >
                Failed to load phonetic variants. Please try refreshing the
                page.
              </div>
            )}

            {/* Empty state */}
            {!isLoading && !isError && matches !== undefined && matches.length === 0 && (
              <div className="mt-3 rounded-lg bg-white border border-slate-200 p-6 text-center">
                <p className="text-sm text-gray-500">
                  No suspected ASR variants found above the{" "}
                  {thresholdPct}% confidence threshold.
                </p>
              </div>
            )}

            {/* Results table */}
            {!isLoading && !isError && matches !== undefined && matches.length > 0 && (
              <div className="mt-3 overflow-x-auto rounded-lg border border-slate-200">
                <table className="min-w-full divide-y divide-slate-200 text-sm">
                  <thead className="bg-slate-50">
                    <tr>
                      <th
                        scope="col"
                        className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide"
                      >
                        Original Text
                      </th>
                      <th
                        scope="col"
                        className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide"
                      >
                        Proposed Correction
                      </th>
                      <th
                        scope="col"
                        className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide"
                      >
                        Confidence
                      </th>
                      <th
                        scope="col"
                        className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide"
                      >
                        Evidence
                      </th>
                      <th
                        scope="col"
                        className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide"
                      >
                        Video Title
                      </th>
                      <th
                        scope="col"
                        className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide"
                      >
                        Actions
                      </th>
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-slate-100">
                    {matches.map((match, idx) => (
                      <MatchRow
                        key={`${match.video_id}-${match.segment_id}-${idx}`}
                        match={match}
                        entityId={entityId}
                        onAliasRegistered={handleAliasRegistered}
                      />
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
