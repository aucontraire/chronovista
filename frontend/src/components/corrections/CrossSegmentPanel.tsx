/**
 * CrossSegmentPanel — displays suggested cross-segment ASR correction candidates.
 *
 * Renders a ranked list of adjacent-segment pairs where an ASR error spans the
 * segment boundary. Each candidate card is clickable and calls `prefillForm` to
 * populate the batch find-replace form with the candidate's source pattern,
 * proposed correction, and cross-segment flag.
 *
 * The panel renders immediately with a loading state while the data fetches and
 * does NOT block the rest of BatchCorrectionsPage.
 *
 * Features:
 * - Loading skeleton with aria-live polite announcement
 * - Empty state when no candidates exist
 * - Candidate cards ranked by confidence (highest first)
 * - Partial-correction badge when is_partially_corrected is true
 * - Inline "Form updated" notice that auto-dismisses after 3 seconds
 * - Keyboard accessible: Enter/Space to select a candidate
 */

import { useEffect, useRef, useState } from "react";

import { useCrossSegmentCandidates } from "../../hooks/useCrossSegmentCandidates";
import type { CrossSegmentCandidate } from "../../types/corrections";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface CrossSegmentPanelProps {
  /**
   * Called when the user selects a candidate. The form should be pre-filled
   * with the provided pattern, replacement, and cross-segment values.
   */
  prefillForm: (values: {
    pattern: string;
    replacement: string;
    crossSegment: boolean;
  }) => void;
  /**
   * Controlled open/closed state for the collapsible panel.
   * Defaults to true (open) when not provided.
   */
  isOpen?: boolean;
  /**
   * Called when the user clicks the toggle header to open or close the panel.
   */
  onToggle?: () => void;
}

// ---------------------------------------------------------------------------
// Loading skeleton
// ---------------------------------------------------------------------------

function CrossSegmentSkeleton() {
  return (
    <div
      className="animate-pulse space-y-3"
      role="status"
      aria-label="Loading cross-segment candidates"
    >
      {[1, 2, 3].map((i) => (
        <div
          key={i}
          className="rounded-lg border border-slate-200 bg-white p-4 space-y-2"
        >
          <div className="h-3 w-3/4 rounded bg-slate-200" />
          <div className="h-3 w-1/2 rounded bg-slate-200" />
          <div className="h-3 w-2/3 rounded bg-slate-200" />
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Inline notice
// ---------------------------------------------------------------------------

interface PrefillNoticeProps {
  onDismiss: () => void;
}

function PrefillNotice({ onDismiss }: PrefillNoticeProps) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="flex items-center justify-between rounded bg-blue-50 border border-blue-200 px-3 py-2 text-sm text-blue-700 mb-3"
    >
      <span>Form updated with cross-segment pattern</span>
      <button
        type="button"
        onClick={onDismiss}
        aria-label="Dismiss notice"
        className="ml-3 text-blue-500 hover:text-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1 rounded"
      >
        &times;
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Candidate card
// ---------------------------------------------------------------------------

interface CandidateCardProps {
  candidate: CrossSegmentCandidate;
  onSelect: (candidate: CrossSegmentCandidate) => void;
}

function CandidateCard({ candidate, onSelect }: CandidateCardProps) {
  const confidencePct = Math.round(candidate.confidence * 100);

  function handleKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onSelect(candidate);
    }
  }

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => onSelect(candidate)}
      onKeyDown={handleKeyDown}
      aria-label={`Apply cross-segment correction: ${candidate.source_pattern} → ${candidate.proposed_correction}, confidence ${confidencePct}%`}
      className="cursor-pointer rounded-lg border border-slate-200 bg-white p-4 hover:border-blue-300 hover:bg-blue-50 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1 transition-colors space-y-3"
    >
      {/* Segment texts */}
      <div className="space-y-1">
        <div>
          <span className="text-xs font-medium text-slate-500 uppercase tracking-wide">
            Segment 1:
          </span>
          <code className="ml-2 font-mono text-sm text-slate-800">
            {candidate.segment_n_text}
          </code>
        </div>
        <div>
          <span className="text-xs font-medium text-slate-500 uppercase tracking-wide">
            Segment 2:
          </span>
          <code className="ml-2 font-mono text-sm text-slate-800">
            {candidate.segment_n1_text}
          </code>
        </div>
      </div>

      {/* Correction details */}
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <div>
          <span className="text-slate-500">Pattern: </span>
          <code className="font-mono text-slate-800">{candidate.source_pattern}</code>
        </div>
        <span className="text-slate-300" aria-hidden="true">→</span>
        <div>
          <span className="text-slate-500">Correction: </span>
          <code className="font-mono text-slate-800">{candidate.proposed_correction}</code>
        </div>
      </div>

      {/* Metadata row: confidence + source badge + partial badge */}
      <div className="flex items-center gap-2">
        <span className="inline-flex items-center rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-700">
          {confidencePct}% confidence
        </span>
        {candidate.discovery_source === "entity_alias" && (
          <span
            className="inline-flex items-center rounded-full bg-violet-100 px-2.5 py-0.5 text-xs font-medium text-violet-700"
            title="Discovered via entity alias"
          >
            Entity
          </span>
        )}
        {candidate.is_partially_corrected && (
          <span className="inline-flex items-center rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-medium text-amber-700">
            Partial
          </span>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

/**
 * CrossSegmentPanel renders a section of suggested cross-segment correction
 * candidates. Clicking a candidate pre-fills the batch find-replace form via
 * the `prefillForm` prop and shows a brief inline notice.
 *
 * The panel is collapsible: the `isOpen` prop controls its expanded state and
 * `onToggle` notifies the parent when the user clicks the header toggle button.
 */
export function CrossSegmentPanel({ prefillForm, isOpen = true, onToggle }: CrossSegmentPanelProps) {
  const { data, isLoading, isError } = useCrossSegmentCandidates();

  // Sort candidates by confidence descending (highest confidence first).
  const candidates: CrossSegmentCandidate[] = data
    ? [...data].sort((a, b) => b.confidence - a.confidence)
    : [];

  // -------------------------------------------------------------------------
  // Inline notice state
  // -------------------------------------------------------------------------

  const [showNotice, setShowNotice] = useState(false);
  const noticeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Clear the auto-dismiss timer when the component unmounts.
  useEffect(() => {
    return () => {
      if (noticeTimerRef.current !== null) {
        clearTimeout(noticeTimerRef.current);
      }
    };
  }, []);

  function showPrefillNotice() {
    // Cancel any existing timer before starting a new one.
    if (noticeTimerRef.current !== null) {
      clearTimeout(noticeTimerRef.current);
    }
    setShowNotice(true);
    noticeTimerRef.current = setTimeout(() => {
      setShowNotice(false);
      noticeTimerRef.current = null;
    }, 3000);
  }

  function handleDismissNotice() {
    if (noticeTimerRef.current !== null) {
      clearTimeout(noticeTimerRef.current);
      noticeTimerRef.current = null;
    }
    setShowNotice(false);
  }

  // -------------------------------------------------------------------------
  // Candidate selection
  // -------------------------------------------------------------------------

  function handleSelectCandidate(candidate: CrossSegmentCandidate) {
    prefillForm({
      pattern: candidate.source_pattern,
      replacement: candidate.proposed_correction,
      crossSegment: true,
    });
    showPrefillNotice();
  }

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  return (
    <section aria-label="Suggested Cross-Segment Candidates">
      {/* Toggle header */}
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={isOpen}
        aria-controls="cross-segment-panel"
        className="flex w-full items-center justify-between text-left focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1 rounded"
      >
        <h2 className="text-lg font-semibold text-slate-900">
          Suggested Cross-Segment Candidates
        </h2>
        <svg
          aria-hidden="true"
          className={`h-5 w-5 text-slate-500 transition-transform duration-300 ${isOpen ? "rotate-180" : "rotate-0"}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          strokeWidth={2}
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {/* Collapsible content */}
      <div
        className={`grid transition-[grid-template-rows] duration-300 ease-in-out ${isOpen ? "grid-rows-[1fr]" : "grid-rows-[0fr]"}`}
      >
        <div id="cross-segment-panel" className="overflow-hidden">
          <div className="space-y-4 pt-3">
            {/* Subtitle */}
            <p className="text-sm text-slate-500">
              Adjacent segment pairs where an ASR error may span the boundary.
              Click a candidate to pre-fill the form above.
            </p>

            {/* Inline prefill notice */}
            {showNotice && <PrefillNotice onDismiss={handleDismissNotice} />}

            {/* aria-live region for loading → loaded announcement */}
            <div aria-live="polite" aria-atomic="true" className="sr-only">
              {isLoading
                ? "Loading cross-segment candidates"
                : `${candidates.length} cross-segment candidate${candidates.length === 1 ? "" : "s"} loaded`}
            </div>

            {/* Loading state */}
            {isLoading && <CrossSegmentSkeleton />}

            {/* Error state */}
            {isError && !isLoading && (
              <div
                role="alert"
                className="rounded-lg bg-red-50 border border-red-200 p-4 text-sm text-red-700"
              >
                Failed to load cross-segment candidates. Please try refreshing the page.
              </div>
            )}

            {/* Empty state */}
            {!isLoading && !isError && candidates.length === 0 && (
              <div className="rounded-lg bg-white border border-slate-200 p-8 text-center">
                <p className="text-slate-600 font-medium">No cross-segment candidates found.</p>
                <p className="mt-1 text-sm text-slate-400">
                  Candidates appear once enough corrections have been applied to
                  identify cross-boundary patterns.
                </p>
              </div>
            )}

            {/* Candidate list */}
            {!isLoading && !isError && candidates.length > 0 && (
              <div className="space-y-3">
                {candidates.map((candidate) => (
                  <CandidateCard
                    key={`${candidate.segment_n_id}-${candidate.segment_n1_id}`}
                    candidate={candidate}
                    onSelect={handleSelectCandidate}
                  />
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
