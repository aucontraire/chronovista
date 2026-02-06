/**
 * LanguageSelector component for transcript language selection.
 *
 * Implements WAI-ARIA tabs pattern (NFR-A03) with keyboard navigation
 * and quality indicators for transcript types.
 *
 * @module components/transcript/LanguageSelector
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { DEBOUNCE_CONFIG } from "../../styles/tokens";
import type { TranscriptLanguage, TranscriptType } from "../../types/transcript";

/**
 * Props for the LanguageSelector component.
 */
export interface LanguageSelectorProps {
  /** Array of available transcript languages */
  languages: TranscriptLanguage[];
  /** Currently selected language code */
  selectedLanguage: string;
  /** Callback when language selection changes */
  onLanguageChange: (code: string) => void;
  /** Optional ID for aria-controls reference */
  contentId?: string;
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
 * Gets the display label for a language code.
 *
 * Shows full BCP-47 code to distinguish variants (e.g., "en-GB" vs "en").
 * Displays with the variant in lowercase for readability (e.g., "EN-gb").
 *
 * @param languageCode - BCP-47 language code (e.g., "en", "en-GB", "pt-BR")
 * @returns Formatted language code with primary language uppercase
 */
function getLanguageLabel(languageCode: string): string {
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
 * LanguageSelector component displays pill tabs for transcript language selection.
 *
 * Features:
 * - WAI-ARIA tabs pattern with proper roles and attributes (NFR-A03)
 * - Arrow key navigation: Left/Right to move, Home/End for first/last
 * - Quality indicator (checkmark) for manual/CC transcripts
 * - Debounced language switch (NFR-P05)
 * - Aria-live announcements for language changes (NFR-A04)
 *
 * @example
 * ```tsx
 * <LanguageSelector
 *   languages={languages}
 *   selectedLanguage="en"
 *   onLanguageChange={(code) => setSelectedLanguage(code)}
 * />
 * ```
 */
export function LanguageSelector({
  languages,
  selectedLanguage,
  onLanguageChange,
  contentId = "transcript-content",
}: LanguageSelectorProps) {
  // Ref for debounce timeout
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Ref for tab elements for focus management
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);

  // State for aria-live announcement
  const [announcement, setAnnouncement] = useState<string>("");

  // Track the focused tab index for keyboard navigation
  const [focusedIndex, setFocusedIndex] = useState<number>(() => {
    const index = languages.findIndex(
      (lang) => lang.language_code === selectedLanguage
    );
    return index >= 0 ? index : 0;
  });

  // Update focusedIndex when selectedLanguage changes externally
  useEffect(() => {
    const index = languages.findIndex(
      (lang) => lang.language_code === selectedLanguage
    );
    if (index >= 0) {
      setFocusedIndex(index);
    }
  }, [selectedLanguage, languages]);

  // Cleanup debounce on unmount
  useEffect(() => {
    return () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }
    };
  }, []);

  /**
   * Handles language selection with debouncing (NFR-P05).
   */
  const handleLanguageSelect = useCallback(
    (languageCode: string, languageName: string) => {
      if (languageCode === selectedLanguage) {
        return;
      }

      // Clear any pending debounce
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }

      // Debounce the language change (NFR-P05)
      debounceRef.current = setTimeout(() => {
        onLanguageChange(languageCode);

        // Announce the language change for screen readers (NFR-A04)
        setAnnouncement(`Transcript language changed to ${languageName}`);

        // Clear announcement after it's been read
        setTimeout(() => setAnnouncement(""), 1000);
      }, DEBOUNCE_CONFIG.languageSwitch);
    },
    [selectedLanguage, onLanguageChange]
  );

  /**
   * Handles keyboard navigation for tabs (NFR-A03).
   * - Left/Right arrows: Navigate between tabs
   * - Home/End: Jump to first/last tab
   * - Enter/Space: Select the focused tab
   */
  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLButtonElement>, index: number) => {
      const tabCount = languages.length;
      let newIndex = index;
      let shouldPreventDefault = true;

      switch (event.key) {
        case "ArrowLeft":
          newIndex = index > 0 ? index - 1 : tabCount - 1;
          break;
        case "ArrowRight":
          newIndex = index < tabCount - 1 ? index + 1 : 0;
          break;
        case "Home":
          newIndex = 0;
          break;
        case "End":
          newIndex = tabCount - 1;
          break;
        default:
          shouldPreventDefault = false;
      }

      if (shouldPreventDefault) {
        event.preventDefault();
        setFocusedIndex(newIndex);
        tabRefs.current[newIndex]?.focus();

        // Select the tab when navigating with arrow keys
        const language = languages[newIndex];
        if (language) {
          handleLanguageSelect(language.language_code, language.language_name);
        }
      }
    },
    [languages, handleLanguageSelect]
  );

  if (languages.length === 0) {
    return null;
  }

  return (
    <div className="relative">
      {/* Tab list container with horizontal scroll for many languages (NFR-R05) */}
      <div
        role="tablist"
        aria-label="Transcript languages"
        className="flex gap-2 overflow-x-auto pb-1"
      >
        {languages.map((language, index) => {
          const isSelected = language.language_code === selectedLanguage;
          const highQuality = isHighQuality(language.transcript_type);

          return (
            <button
              key={language.language_code}
              ref={(el) => {
                tabRefs.current[index] = el;
              }}
              role="tab"
              id={`tab-${language.language_code}`}
              aria-selected={isSelected}
              aria-controls={contentId}
              tabIndex={index === focusedIndex ? 0 : -1}
              onClick={() =>
                handleLanguageSelect(
                  language.language_code,
                  language.language_name
                )
              }
              onKeyDown={(e) => handleKeyDown(e, index)}
              className={`
                inline-flex items-center gap-1 px-3 py-1.5 rounded-full text-sm font-medium
                whitespace-nowrap transition-colors duration-150
                focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2
                ${
                  isSelected
                    ? "bg-blue-600 text-white"
                    : "bg-gray-100 text-gray-700 hover:bg-gray-200"
                }
              `}
              title={`${language.language_name} (${highQuality ? "Manual/CC" : "Auto-generated"})`}
            >
              {getLanguageLabel(language.language_code)}
              {highQuality && (
                <span
                  aria-hidden="true"
                  className={isSelected ? "text-white" : "text-green-600"}
                >
                  &#10003;
                </span>
              )}
              <span className="sr-only">
                {language.language_name}
                {highQuality ? ", high quality transcript" : ""}
              </span>
            </button>
          );
        })}
      </div>

      {/* Aria-live region for language change announcements (NFR-A04) */}
      <div
        role="status"
        aria-live="polite"
        aria-atomic="true"
        className="sr-only"
      >
        {announcement}
      </div>
    </div>
  );
}
