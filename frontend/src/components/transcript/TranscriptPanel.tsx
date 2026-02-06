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
 *
 * @module components/transcript/TranscriptPanel
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { usePrefersReducedMotion } from "../../hooks/usePrefersReducedMotion";
import { useTranscriptLanguages } from "../../hooks/useTranscriptLanguages";
import type { TranscriptLanguage, TranscriptType } from "../../types/transcript";
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
export function TranscriptPanel({ videoId }: TranscriptPanelProps) {
  const {
    data: languages,
    isLoading,
    isError,
    error,
  } = useTranscriptLanguages(videoId);

  // Expand/collapse state
  const [isExpanded, setIsExpanded] = useState(false);

  // Session-scoped language persistence (FR-014)
  const [selectedLanguage, setSelectedLanguage] = useState<string>("");

  // View mode state for segments vs full text display (FR-016a-c)
  const [viewMode, setViewMode] = useState<ViewMode>("segments");

  // Refs for focus management (NFR-A01, NFR-A02)
  const toggleButtonRef = useRef<HTMLButtonElement>(null);
  const languageSelectorRef = useRef<HTMLDivElement>(null);
  const transcriptContentRef = useRef<HTMLDivElement>(null);

  // Check for reduced motion preference (FR-012c)
  const prefersReducedMotion = usePrefersReducedMotion();

  // State for aria-live announcements
  const [announcement, setAnnouncement] = useState<string>("");

  // Initialize selected language when languages load
  useEffect(() => {
    if (languages && languages.length > 0 && !selectedLanguage) {
      // Default to first language
      const firstLanguage = languages[0];
      if (firstLanguage) {
        setSelectedLanguage(firstLanguage.language_code);
      }
    }
  }, [languages, selectedLanguage]);

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

              {/* Transcript Content */}
              <div
                ref={transcriptContentRef}
                className="overflow-y-auto max-h-[calc(60vh-150px)] sm:max-h-[calc(50vh-150px)] lg:max-h-[calc(60vh-150px)]"
                role="region"
                aria-label="Transcript content"
              >
                {viewMode === "segments" ? (
                  <TranscriptSegments
                    videoId={videoId}
                    languageCode={selectedLanguage}
                    onScrollPositionReset={handleScrollReset}
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
      >
        {announcement}
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
