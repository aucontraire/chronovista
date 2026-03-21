/**
 * TranscriptPanel component displays transcript availability information.
 *
 * Shows a collapsible panel with available transcript languages, quality indicators,
 * and language selection functionality.
 *
 * Implements:
 * - FR-009 through FR-015: Transcript panel requirements
 * - FR-012a-c: Expand/collapse with animation and reduced motion support
 * - FR-014: Session-scoped language persistence
 * - NFR-A01-A02: Focus management
 * - NFR-A04-A10: Accessibility requirements
 * - Feature 048 (T015): Auto-scroll with follow-playback toggle and aria-live region
 *   - FR-015: Auto-scroll to active segment when followPlayback is ON
 *   - FR-016: "Follow playback" toggle button with aria-pressed state
 *   - FR-A02: aria-live="polite" region announces active segment text (debounced 1000ms)
 *   - Edge Case 5: Manual user scroll pauses auto-scroll; re-engages on next segment transition
 *
 * @module components/transcript/TranscriptPanel
 */

import { useCallback, useEffect, useRef, useState, type ChangeEvent, type KeyboardEvent } from "react";

import { usePrefersReducedMotion } from "../../hooks/usePrefersReducedMotion";
import { useTranscriptLanguages } from "../../hooks/useTranscriptLanguages";
import { useTranscriptSearch } from "../../hooks/useTranscriptSearch";
import type { TranscriptLanguage, TranscriptType, TranscriptSegment } from "../../types/transcript";
import { LanguageSelector } from "./LanguageSelector";
import { TranscriptFullText } from "./TranscriptFullText";
import { TranscriptSegments } from "./TranscriptSegments";
import { ViewModeToggle, type ViewMode } from "./ViewModeToggle";

/**
 * Props for the TranscriptPanel component.
 */
interface TranscriptPanelProps {
  /** The YouTube video ID to fetch transcript languages for */
  videoId: string;
  /** BCP-47 language code for deep link auto-selection */
  initialLanguage?: string | undefined;
  /** Segment ID to scroll to */
  targetSegmentId?: number | undefined;
  /** Timestamp fallback for scroll */
  targetTimestamp?: number | undefined;
  /** Callback when deep link navigation completes */
  onDeepLinkComplete?: (() => void) | undefined;
  /**
   * ID of the transcript segment currently active under the playback cursor.
   * Comes from useYouTubePlayer.activeSegmentId. Null when in a gap or before
   * the first segment. Undefined when no player is mounted.
   * Used for auto-scroll (FR-015) and aria-live announcement (FR-A02).
   */
  activeSegmentId?: number | null | undefined;
  /**
   * Seeks the YouTube player to a timestamp in seconds (FR-013).
   * Passed through to TranscriptSegments. Undefined when no player is mounted.
   */
  seekTo?: ((seconds: number) => void) | undefined;
  /**
   * Whether the transcript panel should auto-scroll to the active segment (FR-016).
   * Comes from useYouTubePlayer.followPlayback. Session-scoped state lives in the hook.
   */
  followPlayback?: boolean | undefined;
  /**
   * Toggles the follow-playback mode (FR-016).
   * Comes from useYouTubePlayer.toggleFollowPlayback.
   */
  toggleFollowPlayback?: (() => void) | undefined;
  /**
   * Called whenever the loaded transcript segments change (e.g. on first load
   * or language switch). VideoDetailPage uses this to keep the segments array
   * passed to useYouTubePlayer up-to-date for active-segment binary search.
   */
  onSegmentsChange?: ((segments: TranscriptSegment[]) => void) | undefined;
}

/**
 * Unique ID for the transcript content region.
 */
const TRANSCRIPT_CONTENT_ID = "transcript-content";

/**
 * Gets the language badge display text with full BCP-47 code.
 *
 * Shows full variant codes to distinguish similar languages (e.g., "EN-gb" vs "EN").
 *
 * @param languageCode - BCP-47 language code (e.g., "en-GB", "es")
 * @returns Formatted language code with primary language uppercase
 */
function getLanguageBadgeText(languageCode: string): string {
  const parts = languageCode.split("-");
  const primaryLanguage = (parts[0] ?? languageCode).toUpperCase();

  // If there's a variant (region/script), include it
  if (parts.length > 1) {
    const variant = parts.slice(1).join("-").toLowerCase();
    return `${primaryLanguage}-${variant}`;
  }

  return primaryLanguage;
}

/**
 * Determines if a transcript type is high quality (manual or auto_synced).
 *
 * @param transcriptType - The transcript type to check
 * @returns true if the transcript is manual/CC quality (FR-011)
 */
function isHighQuality(transcriptType: TranscriptType): boolean {
  return transcriptType === "manual" || transcriptType === "auto_synced";
}

/**
 * LanguageBadge component displays a single language with quality indicator.
 *
 * Shows a checkmark for manual/CC transcripts per FR-011.
 */
function LanguageBadge({ language }: { language: TranscriptLanguage }) {
  const highQuality = isHighQuality(language.transcript_type);

  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium ${
        highQuality
          ? "bg-green-100 text-green-800"
          : "bg-blue-100 text-blue-800"
      }`}
      title={`${language.language_name} (${highQuality ? "Manual/CC" : "Auto-generated"})`}
    >
      {getLanguageBadgeText(language.language_code)}
      {highQuality && (
        <span aria-label="High quality transcript">&#10003;</span>
      )}
    </span>
  );
}

/**
 * ChevronIcon component for the expand/collapse button.
 *
 * Renders as decorative (aria-hidden="true") per NFR-A09.
 */
function ChevronIcon({ isExpanded }: { isExpanded: boolean }) {
  return (
    <svg
      aria-hidden="true"
      className={`w-5 h-5 text-gray-500 transform transition-transform duration-200 ${
        isExpanded ? "rotate-180" : ""
      }`}
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
      xmlns="http://www.w3.org/2000/svg"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M19 9l-7 7-7-7"
      />
    </svg>
  );
}

/**
 * TranscriptPanel displays transcript availability and language options.
 *
 * Features:
 * - Collapsed by default with 48px min-height (FR-010a)
 * - Shows "Transcript Available" text when collapsed
 * - Displays language badges with quality indicators (FR-011)
 * - Expand/collapse toggle with 200ms ease-out animation (FR-012b)
 * - Max-height 60vh when expanded (FR-012a)
 * - Respects prefers-reduced-motion (FR-012c)
 * - Focus management on expand/collapse (NFR-A01, NFR-A02)
 * - Session-scoped language persistence (FR-014)
 * - Shows "No transcript available" when no transcripts exist (FR-015)
 * - Includes aria-live region for accessibility (NFR-A04)
 *
 * @example
 * ```tsx
 * <TranscriptPanel videoId="dQw4w9WgXcQ" />
 * ```
 */
export function TranscriptPanel({
  videoId,
  initialLanguage,
  targetSegmentId,
  targetTimestamp,
  onDeepLinkComplete,
  activeSegmentId,
  seekTo,
  followPlayback,
  toggleFollowPlayback,
  onSegmentsChange,
}: TranscriptPanelProps) {
  const {
    data: languages,
    isLoading,
    isError,
    error,
  } = useTranscriptLanguages(videoId);

  // Auto-expand when deep link parameters are present (FR-003)
  const hasDeepLinkParams = initialLanguage !== undefined || targetSegmentId !== undefined || targetTimestamp !== undefined;
  const [isExpanded, setIsExpanded] = useState(hasDeepLinkParams);

  // Session-scoped language persistence (FR-014)
  const [selectedLanguage, setSelectedLanguage] = useState<string>("");

  // View mode state for segments vs full text display (FR-016a-c)
  const [viewMode, setViewMode] = useState<ViewMode>("segments");

  // Language fallback notice when deep link language is unavailable (FR-012)
  const [languageFallbackNotice, setLanguageFallbackNotice] = useState<string>("");

  // Loaded segments from TranscriptSegments (for client-side search, Feature 042 US4)
  const [loadedSegments, setLoadedSegments] = useState<TranscriptSegment[]>([]);

  // Raw (un-debounced) search input value for the controlled input
  const [searchInputValue, setSearchInputValue] = useState<string>("");

  // Saved scroll position — restored when search is cleared (T025)
  const savedScrollTopRef = useRef<number>(0);

  // Whether search was active (used to detect clear event for scroll restore)
  const wasSearchActiveRef = useRef<boolean>(false);

  // Ref for the active match container — used for scrollIntoView (T025)
  const activeMatchContainerRef = useRef<HTMLDivElement>(null);

  // --- Follow-playback / auto-scroll state (T015) ---

  /**
   * Tracks whether the user has manually scrolled the transcript panel since
   * the last segment transition (Edge Case 5). When true, auto-scroll is
   * suppressed for the current segment; it re-engages on the next transition.
   */
  const userScrolledRef = useRef<boolean>(false);

  /**
   * Debounced aria-live text for the active segment (FR-A02, 1000ms debounce).
   */
  const [activeSegmentAnnouncement, setActiveSegmentAnnouncement] = useState<string>("");
  const activeSegmentAnnouncementTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  /**
   * Previous activeSegmentId — used to detect actual segment transitions in the
   * auto-scroll effect and to determine which segment's text to announce.
   * Initialised as undefined so the first real value always triggers the effect.
   */
  const prevActiveSegmentIdRef = useRef<number | null | undefined>(undefined);

  // Debounced search announcement (FR-021: 500ms debounce on aria-live)
  const [searchAnnouncement, setSearchAnnouncement] = useState<string>("");
  const searchAnnouncementTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Search input ref for keyboard navigation focus detection (T026)
  const searchInputRef = useRef<HTMLInputElement>(null);

  // Refs for focus management (NFR-A01, NFR-A02)
  const toggleButtonRef = useRef<HTMLButtonElement>(null);
  const languageSelectorRef = useRef<HTMLDivElement>(null);
  const transcriptContentRef = useRef<HTMLDivElement>(null);

  // Check for reduced motion preference (FR-012c)
  const prefersReducedMotion = usePrefersReducedMotion();

  // State for aria-live announcements
  const [announcement, setAnnouncement] = useState<string>("");

  // Client-side transcript search (Feature 042 US4, FR-011, FR-020)
  const {
    matches: searchMatches,
    currentIndex: searchCurrentIndex,
    total: searchTotal,
    next: searchNext,
    prev: searchPrev,
    query: searchQuery,
    setQuery: setSearchQuery,
    reset: resetSearch,
  } = useTranscriptSearch(loadedSegments, "");

  // Initialize selected language when languages load
  useEffect(() => {
    if (languages && languages.length > 0 && !selectedLanguage) {
      if (initialLanguage && languages.some(l => l.language_code === initialLanguage)) {
        // Deep link language available — use it (FR-004)
        setSelectedLanguage(initialLanguage);
      } else {
        // Default to first language
        const firstLanguage = languages[0];
        if (firstLanguage) {
          setSelectedLanguage(firstLanguage.language_code);

          // Show fallback notice if initialLanguage was requested but unavailable (FR-012)
          if (initialLanguage) {
            setLanguageFallbackNotice(
              `Requested language '${initialLanguage}' is not available. Showing ${firstLanguage.language_name} instead.`
            );
          }
        }
      }
    }
  }, [languages, selectedLanguage, initialLanguage]);

  // Force segments view mode when deep link navigation targets are present (FR-016)
  useEffect(() => {
    if (targetSegmentId !== undefined || targetTimestamp !== undefined) {
      setViewMode("segments");
    }
  }, [targetSegmentId, targetTimestamp]);

  // Save scroll position when search first activates (for restore on clear — T025).
  // Actual scroll-to-match is handled by TranscriptSegments via activeSegmentIndex,
  // which avoids re-scrolling on every page load during eager-fetch and correctly
  // handles off-screen virtual segments that aren't in the DOM yet.
  useEffect(() => {
    if (searchMatches.length > 0 && !wasSearchActiveRef.current) {
      wasSearchActiveRef.current = true;
      if (transcriptContentRef.current) {
        savedScrollTopRef.current = transcriptContentRef.current.scrollTop;
      }
    }
  }, [searchMatches]);

  // Restore scroll when search is cleared (T025)
  useEffect(() => {
    if (searchQuery === "" && wasSearchActiveRef.current) {
      wasSearchActiveRef.current = false;
      if (transcriptContentRef.current) {
        transcriptContentRef.current.scrollTop = savedScrollTopRef.current;
      }
    }
  }, [searchQuery]);

  // Reset scroll position and clear active search when language or view mode changes (T027, T028).
  // FR-015: Reset scroll to top on language/view mode switch.
  // FR-025: Clear search highlights and search text on language/view mode switch.
  //
  // Scroll reset is immediate (no animation) per FR-015.
  // The effect skips the very first value of selectedLanguage ("" → first language) by
  // checking that selectedLanguage is non-empty before acting, which means the reset only
  // fires on user-initiated language changes, not the initial auto-selection on mount.
  // Deep-link scroll (FR-016) is preserved because TranscriptSegments performs its own
  // scrollIntoView after data loads, which runs after this effect and takes precedence.
  useEffect(() => {
    // Do not act on the initial empty-string placeholder for selectedLanguage.
    if (!selectedLanguage) return;

    // Reset scroll container to top immediately (FR-015).
    if (transcriptContentRef.current) {
      transcriptContentRef.current.scrollTop = 0;
    }

    // Also reset the saved scroll position ref so a subsequent search-clear
    // does not restore a stale pre-language-switch position (T027).
    savedScrollTopRef.current = 0;
    wasSearchActiveRef.current = false;

    // Clear active search state (FR-025, T028).
    setSearchInputValue("");
    resetSearch();
  }, [selectedLanguage, viewMode, resetSearch]);

  // Update debounced aria-live search announcement (T024, FR-021: 500ms debounce)
  useEffect(() => {
    if (searchAnnouncementTimeoutRef.current !== null) {
      clearTimeout(searchAnnouncementTimeoutRef.current);
    }

    if (searchQuery && searchTotal > 0) {
      searchAnnouncementTimeoutRef.current = setTimeout(() => {
        setSearchAnnouncement(
          `${searchTotal} match${searchTotal !== 1 ? "es" : ""} found. Showing ${searchCurrentIndex + 1} of ${searchTotal}.`
        );
      }, 500);
    } else if (searchQuery && searchTotal === 0) {
      searchAnnouncementTimeoutRef.current = setTimeout(() => {
        setSearchAnnouncement("No matches found.");
      }, 500);
    } else {
      setSearchAnnouncement("");
    }

    return () => {
      if (searchAnnouncementTimeoutRef.current !== null) {
        clearTimeout(searchAnnouncementTimeoutRef.current);
      }
    };
  }, [searchQuery, searchTotal, searchCurrentIndex]);

  // --- Auto-scroll to active segment when followPlayback is ON (T015, FR-015) ---
  //
  // This effect fires only when activeSegmentId changes (segment transition), NOT on
  // every currentTime update, keeping scroll events coarse-grained.
  //
  // Scroll strategy:
  //   1. If userScrolledRef is true the user just manually scrolled — skip this
  //      transition but clear the flag so the NEXT transition auto-scrolls again.
  //   2. Query for the segment row using data-segment-id within transcriptContentRef
  //      (which wraps the inner virtualized/non-virtualized scroll container).
  //   3. scrollIntoView({ behavior: 'smooth', block: 'nearest' }) — uses 'nearest'
  //      so a segment that's already partially visible isn't over-scrolled.
  //
  // Virtualization note: scrollIntoView only works for segments that are in the DOM.
  // Segments far from the viewport are outside the virtual window and won't be rendered.
  // For the common case (video playing sequentially, next segment is adjacent), the
  // segment is always rendered because the virtualizer has an overscan of 5 rows.
  useEffect(() => {
    // Only run when the segment ID actually changes (skip initial undefined baseline).
    if (prevActiveSegmentIdRef.current === activeSegmentId) return;
    prevActiveSegmentIdRef.current = activeSegmentId;

    // Re-enable auto-scroll for the new segment even if the user had scrolled away.
    // Edge Case 5: clear the flag on segment transition so auto-scroll re-engages.
    if (userScrolledRef.current) {
      userScrolledRef.current = false;
      // Still skip THIS scroll (the user's intent was to read a different position).
      return;
    }

    // Guard: only scroll when follow is ON, a segment is active, and segment view is shown.
    if (!followPlayback || activeSegmentId == null || viewMode !== "segments") return;

    // The scrollable region is transcriptContentRef; the segment rows with
    // data-segment-id live inside it (either directly or inside the virtualizer div).
    const container = transcriptContentRef.current;
    if (!container) return;

    const segmentEl = container.querySelector<HTMLElement>(
      `[data-segment-id="${activeSegmentId}"]`
    );
    segmentEl?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [activeSegmentId, followPlayback, viewMode]);

  // --- aria-live announcement for active segment text (T015, FR-A02, 1000ms debounce) ---
  //
  // When the active segment changes and a player is present, announce the new
  // segment's text to screen readers after a 1000ms debounce. Rapid segment changes
  // (e.g. quick seeking) cancel and restart the timer so the reader isn't overwhelmed.
  //
  // The segment text is sourced from loadedSegments (already maintained for search).
  useEffect(() => {
    if (activeSegmentAnnouncementTimeoutRef.current !== null) {
      clearTimeout(activeSegmentAnnouncementTimeoutRef.current);
    }

    // Only announce when there is an active segment and a player is present.
    if (activeSegmentId == null || seekTo === undefined) {
      setActiveSegmentAnnouncement("");
      return;
    }

    const segment = loadedSegments.find((s) => s.id === activeSegmentId);
    if (!segment) {
      setActiveSegmentAnnouncement("");
      return;
    }

    activeSegmentAnnouncementTimeoutRef.current = setTimeout(() => {
      setActiveSegmentAnnouncement(segment.text);
    }, 1000);

    return () => {
      if (activeSegmentAnnouncementTimeoutRef.current !== null) {
        clearTimeout(activeSegmentAnnouncementTimeoutRef.current);
      }
    };
  }, [activeSegmentId, loadedSegments, seekTo]);

  /**
   * Handles manual scroll of the transcript content area (Edge Case 5).
   * Sets userScrolledRef so the current segment's auto-scroll is suppressed;
   * auto-scroll re-engages on the next segment transition.
   */
  const handleTranscriptScroll = useCallback(() => {
    // Only track user scroll when follow is ON and a player is active.
    // When follow is already OFF, the flag has no effect, so we still set it
    // cheaply — it'll be cleared on the next segment transition harmlessly.
    userScrolledRef.current = true;
  }, []);

  /**
   * Handles search input change.
   * Updates raw input state and forwards to debounced hook setter.
   */
  const handleSearchInput = useCallback(
    (e: ChangeEvent<HTMLInputElement>) => {
      const value = e.target.value;
      setSearchInputValue(value);
      setSearchQuery(value);
    },
    [setSearchQuery]
  );

  /**
   * Handles keyboard navigation from the search input (T026).
   * Enter → next match, Shift+Enter → previous match.
   */
  const handleSearchKeyDown = useCallback(
    (e: KeyboardEvent<HTMLInputElement>) => {
      if (e.key === "Enter") {
        e.preventDefault();
        if (e.shiftKey) {
          searchPrev();
        } else {
          searchNext();
        }
      }
    },
    [searchNext, searchPrev]
  );

  /**
   * Resets the search field and restores scroll position.
   */
  const handleSearchReset = useCallback(() => {
    setSearchInputValue("");
    resetSearch();
    // Restore scroll handled by effect watching searchQuery
  }, [resetSearch]);

  /**
   * Handles segments loaded from TranscriptSegments (used for search indexing
   * and for surfacing loaded segments to the parent via onSegmentsChange so
   * that VideoDetailPage can update useYouTubePlayer's binary-search data).
   */
  const handleSegmentsChange = useCallback((segments: TranscriptSegment[]) => {
    setLoadedSegments(segments);
    onSegmentsChange?.(segments);
  }, [onSegmentsChange]);

  /**
   * Handles expand/collapse toggle.
   * Manages focus per NFR-A01 (focus first tab on expand) and NFR-A02 (focus toggle on collapse).
   */
  const handleToggle = useCallback(() => {
    setIsExpanded((prev) => {
      const newState = !prev;

      // Announce state change (NFR-A04)
      setAnnouncement(
        newState ? "Transcript panel expanded" : "Transcript panel collapsed"
      );

      // Clear announcement after it's been read
      setTimeout(() => setAnnouncement(""), 1000);

      // Focus management
      if (newState) {
        // NFR-A01: Focus first language tab on expand
        // Use setTimeout to wait for the panel to be visible
        setTimeout(() => {
          const firstTab = languageSelectorRef.current?.querySelector(
            'button[role="tab"]'
          ) as HTMLButtonElement | null;
          firstTab?.focus();
        }, prefersReducedMotion ? 0 : 200);
      } else {
        // NFR-A02: Return focus to toggle on collapse
        setTimeout(() => {
          toggleButtonRef.current?.focus();
        }, prefersReducedMotion ? 0 : 200);
      }

      return newState;
    });
  }, [prefersReducedMotion]);

  /**
   * Handles language selection change.
   */
  const handleLanguageChange = useCallback((code: string) => {
    setSelectedLanguage(code);
    // Auto-dismiss language fallback notice on manual language change (FR-012)
    setLanguageFallbackNotice("");
  }, []);

  /**
   * Handles view mode change (FR-016a-c).
   * Resets scroll position to top when switching between segments and full text views.
   */
  const handleViewModeChange = useCallback((mode: ViewMode) => {
    setViewMode(mode);

    // Reset scroll position to top when view mode changes (FR-016a-c)
    if (transcriptContentRef.current) {
      transcriptContentRef.current.scrollTop = 0;
    }
  }, []);

  /**
   * Handles scroll position reset callback from TranscriptSegments.
   * Called when segments reset their internal scroll position.
   */
  const handleScrollReset = useCallback(() => {
    // Additional scroll reset handling if needed
    if (transcriptContentRef.current) {
      transcriptContentRef.current.scrollTop = 0;
    }
  }, []);

  // Handle loading state
  if (isLoading) {
    return (
      <div
        className="bg-white rounded-lg border border-gray-100 min-h-[48px] px-4 py-3 animate-pulse"
        role="status"
        aria-label="Loading transcript information"
      >
        <div className="flex items-center gap-3">
          <div className="h-4 bg-gray-200 rounded w-32" />
          <div className="flex gap-2">
            <div className="h-6 bg-gray-200 rounded-full w-10" />
            <div className="h-6 bg-gray-200 rounded-full w-10" />
          </div>
        </div>
        <span className="sr-only">Loading transcript information...</span>
      </div>
    );
  }

  // Handle error state
  if (isError) {
    return (
      <div
        className="bg-white rounded-lg border border-red-200 min-h-[48px] px-4 py-3"
        role="alert"
        aria-live="polite"
      >
        <p className="text-sm text-red-800">
          Could not load transcript information.
          {error?.message && (
            <span className="block text-red-600 text-xs mt-1">
              {error.message}
            </span>
          )}
        </p>
      </div>
    );
  }

  // Handle no transcripts available (FR-015)
  if (!languages || languages.length === 0) {
    return (
      <div
        className="bg-white rounded-lg border border-gray-100 min-h-[48px] px-4 py-3"
        role="region"
        aria-label="Transcript information"
        aria-live="polite"
      >
        <p className="text-sm text-gray-500">
          No transcript available for this video
        </p>
      </div>
    );
  }

  // Animation classes based on reduced motion preference (FR-012c)
  const animationClasses = prefersReducedMotion
    ? ""
    : "transition-all duration-200 ease-out";

  // Button text based on state (NFR-A08)
  const buttonText = isExpanded ? "Hide transcript" : "Show transcript";

  return (
    <div
      className="bg-white rounded-lg border border-gray-100 overflow-hidden"
      role="region"
      aria-label="Transcript information"
    >
      {/* Expand/collapse toggle button (NFR-A06, NFR-A07) */}
      <button
        ref={toggleButtonRef}
        type="button"
        onClick={handleToggle}
        aria-expanded={isExpanded}
        aria-controls={TRANSCRIPT_CONTENT_ID}
        className={`
          w-full min-h-[48px] px-4 py-3
          flex items-center justify-between
          text-left
          hover:bg-gray-50
          focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-blue-500
          ${animationClasses}
        `}
      >
        <div className="flex flex-wrap items-center gap-3">
          {/* Transcript Available text */}
          <span className="text-sm font-medium text-gray-900">
            Transcript Available
          </span>

          {/* Language badges (shown in collapsed state) */}
          {!isExpanded && (
            <div
              className="flex flex-wrap gap-2"
              role="list"
              aria-label="Available languages"
            >
              {languages.map((language) => (
                <div key={language.language_code} role="listitem">
                  <LanguageBadge language={language} />
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Toggle indicator with button text and chevron */}
        <div className="flex items-center gap-2 ml-4 flex-shrink-0">
          <span className="text-sm text-gray-600">{buttonText}</span>
          <ChevronIcon isExpanded={isExpanded} />
        </div>
      </button>

      {/* Expandable content area */}
      <div
        id={TRANSCRIPT_CONTENT_ID}
        role="tabpanel"
        aria-hidden={!isExpanded}
        className={`
          overflow-hidden
          ${animationClasses}
          ${
            isExpanded
              ? "max-h-[60vh] sm:max-h-[50vh] lg:max-h-[60vh] opacity-100"
              : "max-h-0 opacity-0"
          }
        `}
        style={{
          // Ensure smooth height transition (NFR-P08)
          visibility: isExpanded ? "visible" : "hidden",
        }}
      >
        <div className="px-4 pb-4 border-t border-gray-100">
          {/* Language selector tabs */}
          <div ref={languageSelectorRef} className="pt-3 pb-3">
            <LanguageSelector
              languages={languages}
              selectedLanguage={selectedLanguage}
              onLanguageChange={handleLanguageChange}
              contentId={TRANSCRIPT_CONTENT_ID}
            />
          </div>

          {/* Language fallback notice (FR-012) */}
          {languageFallbackNotice && (
            <div
              className="mb-3 px-3 py-2 text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded"
              role="status"
              aria-live="polite"
            >
              {languageFallbackNotice}
            </div>
          )}

          {/* Transcript content with view mode toggle */}
          {selectedLanguage && (
            <>
              {/* View Mode Toggle (FR-016a-c) */}
              <div className="pb-3">
                <ViewModeToggle
                  mode={viewMode}
                  onModeChange={handleViewModeChange}
                />
              </div>

              {/* Search field — visible only in expanded segments view (FR-011, T023) */}
              {viewMode === "segments" && (
                <div className="pb-3">
                  <div className="flex items-center gap-2">
                    {/* Follow playback toggle — only shown when a player is available (T015, FR-016) */}
                    {toggleFollowPlayback !== undefined && followPlayback !== undefined && (
                      <button
                        type="button"
                        onClick={toggleFollowPlayback}
                        aria-pressed={followPlayback}
                        title={followPlayback ? "Auto-scrolling to active segment" : "Click to follow playback"}
                        className={`
                          flex-shrink-0 inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded text-xs font-medium
                          border transition-colors duration-150
                          focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500
                          ${
                            followPlayback
                              ? "bg-blue-50 border-blue-300 text-blue-700 hover:bg-blue-100"
                              : "bg-white border-gray-300 text-gray-600 hover:bg-gray-50"
                          }
                        `}
                      >
                        {/* Play/scroll icon */}
                        <svg
                          aria-hidden="true"
                          className="w-3.5 h-3.5 flex-shrink-0"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                          xmlns="http://www.w3.org/2000/svg"
                        >
                          {followPlayback ? (
                            /* Play triangle — "actively following" */
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth={2}
                              d="M5 3l14 9-14 9V3z"
                            />
                          ) : (
                            /* Pause bars — "not following" */
                            <>
                              <line x1="10" y1="5" x2="10" y2="19" strokeWidth={2} strokeLinecap="round" />
                              <line x1="14" y1="5" x2="14" y2="19" strokeWidth={2} strokeLinecap="round" />
                            </>
                          )}
                        </svg>
                        <span>{followPlayback ? "Following" : "Follow playback"}</span>
                      </button>
                    )}
                    {/* Search input (NFR-002: accessible label) */}
                    <label
                      htmlFor="transcript-search-input"
                      className="sr-only"
                    >
                      Search transcript
                    </label>
                    <input
                      ref={searchInputRef}
                      id="transcript-search-input"
                      type="search"
                      value={searchInputValue}
                      onChange={handleSearchInput}
                      onKeyDown={handleSearchKeyDown}
                      placeholder="Search transcript…"
                      aria-label="Search transcript"
                      aria-controls="transcript-content"
                      className="
                        flex-1 min-w-0 px-3 py-1.5 text-sm
                        border border-gray-300 rounded-md
                        bg-white text-gray-900
                        placeholder:text-gray-400
                        focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:border-blue-500
                      "
                    />

                    {/* Match counter "N of M" (FR-013) */}
                    {searchQuery && (
                      <span
                        className="flex-shrink-0 text-xs text-gray-500 tabular-nums"
                        aria-live="off"
                      >
                        {searchTotal === 0
                          ? "0 of 0"
                          : `${searchCurrentIndex + 1} of ${searchTotal}`}
                      </span>
                    )}

                    {/* Previous button — NFR-001: min 44×44px touch target */}
                    {searchTotal > 0 && (
                      <button
                        type="button"
                        onClick={searchPrev}
                        aria-label="Previous match"
                        title="Previous match (Shift+Enter)"
                        disabled={searchTotal === 0}
                        className="
                          flex-shrink-0 min-w-[44px] min-h-[44px] flex items-center justify-center rounded
                          text-gray-600 hover:text-gray-900 hover:bg-gray-100
                          focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500
                          disabled:opacity-40 disabled:cursor-not-allowed
                        "
                      >
                        {/* Up chevron */}
                        <svg
                          className="w-4 h-4"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                          aria-hidden="true"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M5 15l7-7 7 7"
                          />
                        </svg>
                      </button>
                    )}

                    {/* Next button — NFR-001: min 44×44px touch target */}
                    {searchTotal > 0 && (
                      <button
                        type="button"
                        onClick={searchNext}
                        aria-label="Next match"
                        title="Next match (Enter)"
                        disabled={searchTotal === 0}
                        className="
                          flex-shrink-0 min-w-[44px] min-h-[44px] flex items-center justify-center rounded
                          text-gray-600 hover:text-gray-900 hover:bg-gray-100
                          focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500
                          disabled:opacity-40 disabled:cursor-not-allowed
                        "
                      >
                        {/* Down chevron */}
                        <svg
                          className="w-4 h-4"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                          aria-hidden="true"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M19 9l-7 7-7-7"
                          />
                        </svg>
                      </button>
                    )}

                    {/* Clear/reset button — NFR-001: min 44×44px touch target */}
                    {searchInputValue && (
                      <button
                        type="button"
                        onClick={handleSearchReset}
                        aria-label="Clear search"
                        className="
                          flex-shrink-0 min-w-[44px] min-h-[44px] flex items-center justify-center rounded
                          text-gray-500 hover:text-gray-700 hover:bg-gray-100
                          focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500
                        "
                      >
                        {/* X icon */}
                        <svg
                          className="w-4 h-4"
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
                    )}
                  </div>

                  {/* "No matches" hint (shown when query exists but nothing found) */}
                  {searchQuery && searchTotal === 0 && (
                    <p className="mt-1 text-xs text-gray-500" role="status">
                      No matches found
                    </p>
                  )}
                </div>
              )}

              {/* Transcript Content */}
              <div
                ref={transcriptContentRef}
                className="overflow-y-auto max-h-[calc(60vh-150px)] sm:max-h-[calc(50vh-150px)] lg:max-h-[calc(60vh-150px)]"
                role="region"
                aria-label="Transcript content"
                onScroll={handleTranscriptScroll}
              >
                {viewMode === "segments" ? (
                  <TranscriptSegments
                    videoId={videoId}
                    languageCode={selectedLanguage}
                    onScrollPositionReset={handleScrollReset}
                    targetSegmentId={targetSegmentId}
                    targetTimestamp={targetTimestamp}
                    onDeepLinkComplete={onDeepLinkComplete}
                    isExpanded={isExpanded}
                    seekTo={seekTo}
                    activeSegmentId={activeSegmentId}
                    searchProps={{
                      matches: searchMatches,
                      activeMatchIndex: searchCurrentIndex,
                      onSegmentsChange: handleSegmentsChange,
                      activeMatchContainerRef,
                      searchQuery,
                      // Segment-level index for the active match — used by
                      // TranscriptSegments to scroll the virtual container
                      // without relying on DOM refs that fail for off-screen
                      // segments (bug fix: T025 scroll-to-match).
                      activeSegmentIndex:
                        searchMatches[searchCurrentIndex]?.segmentIndex,
                    }}
                  />
                ) : (
                  <TranscriptFullText
                    videoId={videoId}
                    languageCode={selectedLanguage}
                  />
                )}
              </div>
            </>
          )}
        </div>
      </div>

      {/* Screen reader announcement for state changes (NFR-A04) */}
      <div
        role="status"
        aria-live="polite"
        aria-atomic="true"
        className="sr-only"
        data-testid="panel-announcement"
      >
        {announcement}
      </div>

      {/* Screen reader announcement for search match count (T024, FR-021: 500ms debounce) */}
      <div
        role="status"
        aria-live="polite"
        aria-atomic="true"
        className="sr-only"
        data-testid="search-announcement"
      >
        {searchAnnouncement}
      </div>

      {/* aria-live region for active segment text (T015, FR-A02, 1000ms debounce).
          Announces the current playback segment to screen readers without
          visual output. Only populated when a player is present (seekTo defined). */}
      <div
        role="status"
        aria-live="polite"
        aria-atomic="true"
        className="sr-only"
        data-testid="active-segment-announcement"
      >
        {activeSegmentAnnouncement}
      </div>

      {/* Screen reader summary when collapsed */}
      {!isExpanded && (
        <div className="sr-only" aria-live="polite">
          {languages.length} transcript{languages.length !== 1 ? "s" : ""}{" "}
          available in {languages.map((l) => l.language_name).join(", ")}
        </div>
      )}
    </div>
  );
}
