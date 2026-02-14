/**
 * SearchFilters Component
 *
 * Implements:
 * - FR-008: Language filter dropdown
 * - FR-013: Search type checkboxes (Transcripts enabled, others "Coming Soon")
 * - FR-021: Responsive filter panel (desktop sidebar, tablet drawer, mobile bottom sheet)
 *
 * Features:
 * - Language dropdown with available languages from search results
 * - "All languages" option as default
 * - Human-readable language names for BCP-47 codes
 * - Search type filter panel with checkboxes
 * - Result count display on Transcripts checkbox
 * - "Coming Soon" badges for disabled search types
 * - Responsive behavior: permanent sidebar (desktop), drawer (tablet), bottom sheet (mobile)
 * - ARIA labels for accessibility
 * - Deduplication and alphabetical sorting
 *
 * @see FR-008: Language filter dropdown
 * @see FR-013: Search type checkboxes
 * @see FR-021: Responsive filter panel
 */

import { useEffect } from 'react';
import { SEARCH_CONFIG } from '../config/search';
import { SEARCH_TYPE_OPTIONS, type EnabledSearchTypes, type SearchType } from '../types/search';

interface SearchFiltersProps {
  /** Available language codes from search results (BCP-47) */
  availableLanguages: string[];
  /** Currently selected language (empty string for "All languages") */
  selectedLanguage: string;
  /** Callback when language selection changes */
  onLanguageChange: (language: string) => void;
  /** Total number of transcript search results */
  totalResults: number;
  /** Total number of title search results */
  titleCount?: number;
  /** Total number of description search results */
  descriptionCount?: number;
  /** Whether the user is on a mobile device */
  isMobile?: boolean;
  /** Whether the user is on a tablet device */
  isTablet?: boolean;
  /** Whether the filter panel is open (mobile/tablet only) */
  isOpen?: boolean;
  /** Callback when the filter panel should close (mobile/tablet only) */
  onClose?: () => void;
  /** Which search types are currently enabled */
  enabledTypes: EnabledSearchTypes;
  /** Callback when a search type is toggled */
  onToggleType: (type: keyof EnabledSearchTypes) => void;
  /** Whether to include unavailable content (T031, FR-021) */
  includeUnavailable?: boolean;
  /** Callback when include unavailable is toggled */
  onToggleIncludeUnavailable?: () => void;
}

/**
 * Mapping of language codes to human-readable display names.
 *
 * Includes both base language codes and regional variants.
 * Regional variants are preserved to show users the specific
 * language/dialect context (e.g., lingo, slang, spelling differences).
 */
const LANGUAGE_NAMES: Record<string, string> = {
  // Base codes
  'en': 'English',
  'es': 'Spanish',
  'de': 'German',
  'fr': 'French',
  'pt': 'Portuguese',
  'ja': 'Japanese',
  'ko': 'Korean',
  'zh': 'Chinese',
  'ru': 'Russian',
  'ar': 'Arabic',
  'hi': 'Hindi',
  'it': 'Italian',
  'nl': 'Dutch',
  'pl': 'Polish',
  'tr': 'Turkish',
  'vi': 'Vietnamese',
  // English regional variants
  'en-US': 'English (US)',
  'en-GB': 'English (UK)',
  'en-AU': 'English (Australia)',
  'en-CA': 'English (Canada)',
  'en-IN': 'English (India)',
  // Spanish regional variants
  'es-ES': 'Spanish (Spain)',
  'es-MX': 'Spanish (Mexico)',
  'es-AR': 'Spanish (Argentina)',
  'es-CO': 'Spanish (Colombia)',
  'es-419': 'Spanish (Latin America)',
  // French regional variants
  'fr-FR': 'French (France)',
  'fr-CA': 'French (Canada)',
  // German regional variants
  'de-DE': 'German (Germany)',
  'de-AT': 'German (Austria)',
  'de-CH': 'German (Switzerland)',
  // Portuguese regional variants
  'pt-PT': 'Portuguese (Portugal)',
  'pt-BR': 'Portuguese (Brazil)',
  // Chinese variants
  'zh-CN': 'Chinese (Simplified)',
  'zh-TW': 'Chinese (Traditional)',
  'zh-HK': 'Chinese (Hong Kong)',
  // Other regional variants
  'ja-JP': 'Japanese (Japan)',
  'ko-KR': 'Korean (Korea)',
  'ru-RU': 'Russian (Russia)',
  'ar-SA': 'Arabic (Saudi Arabia)',
  'ar-EG': 'Arabic (Egypt)',
  'hi-IN': 'Hindi (India)',
  'it-IT': 'Italian (Italy)',
  'nl-NL': 'Dutch (Netherlands)',
};

/**
 * Get human-readable display name for a language code.
 * Preserves regional variants to show users the specific language context.
 *
 * @param code - BCP-47 language code (can be base or regional variant)
 * @returns Display name or the code itself if no mapping exists
 */
function getLanguageDisplayName(code: string): string {
  // First try exact match (including regional variants)
  if (LANGUAGE_NAMES[code]) {
    return LANGUAGE_NAMES[code];
  }
  // Fall back to base language name if regional variant not in map
  const parts = code.split('-');
  const baseCode = parts[0] || code;
  if (LANGUAGE_NAMES[baseCode]) {
    // Return with region suffix for unknown regional variants
    const region = parts.length > 1 && parts[1] ? ` (${parts[1]})` : '';
    return `${LANGUAGE_NAMES[baseCode]}${region}`;
  }
  // Return the code itself if completely unknown
  return code;
}

/**
 * SearchFilters component for filtering search results.
 *
 * Supports language filtering and search type selection.
 * Responsive design adapts panel display based on screen size.
 *
 * @example
 * ```tsx
 * // Desktop (permanent sidebar)
 * <SearchFilters
 *   availableLanguages={['en', 'es', 'de']}
 *   selectedLanguage="en"
 *   onLanguageChange={(lang) => setLanguage(lang)}
 *   totalResults={47}
 * />
 *
 * // Mobile (bottom sheet)
 * <SearchFilters
 *   availableLanguages={['en', 'es', 'de']}
 *   selectedLanguage="en"
 *   onLanguageChange={(lang) => setLanguage(lang)}
 *   totalResults={47}
 *   isMobile={true}
 *   isOpen={isFiltersOpen}
 *   onClose={() => setIsFiltersOpen(false)}
 * />
 * ```
 */
// Helper to map SearchType to EnabledSearchTypes key
const TYPE_KEY_MAP: Partial<Record<SearchType, keyof EnabledSearchTypes>> = {
  'transcripts': 'transcripts',
  'video_titles': 'titles',
  'video_descriptions': 'descriptions',
};

export function SearchFilters({
  availableLanguages,
  selectedLanguage,
  onLanguageChange,
  totalResults,
  titleCount = 0,
  descriptionCount = 0,
  isMobile = false,
  isTablet = false,
  isOpen = true,
  onClose,
  enabledTypes,
  onToggleType,
  includeUnavailable = false,
  onToggleIncludeUnavailable,
}: SearchFiltersProps) {
  // Preserve regional variants (e.g., "en-US", "en-GB") as separate options
  // This shows users the specific language context (lingo, slang, spelling)
  // and ensures filters match the exact codes stored in transcript segments
  const uniqueLanguages = Array.from(new Set(availableLanguages));
  const sortedLanguages = uniqueLanguages.sort((a, b) => {
    const nameA = getLanguageDisplayName(a);
    const nameB = getLanguageDisplayName(b);
    return nameA.localeCompare(nameB);
  });

  const isResponsiveMode = isMobile || isTablet;

  // Handle Escape key to close panel
  useEffect(() => {
    if (!isResponsiveMode || !isOpen || !onClose) return;

    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };

    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [isResponsiveMode, isOpen, onClose]);

  const handleLanguageChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
    onLanguageChange(event.target.value);

    // Auto-close after filter change on mobile/tablet
    if (isResponsiveMode && onClose) {
      setTimeout(() => {
        onClose();
      }, SEARCH_CONFIG.FILTER_PANEL_AUTO_CLOSE_DELAY);
    }
  };

  // Don't render if closed on mobile/tablet
  if (isResponsiveMode && !isOpen) {
    return null;
  }

  const filterContent = (
    <>
      {/* Header with close button for mobile/tablet */}
      {isResponsiveMode && (
        <div className="flex items-center justify-between mb-6 pb-4 border-b border-gray-200 dark:border-gray-700">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
            Filters
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close filters"
            className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
          >
            <svg
              className="w-5 h-5 text-gray-500 dark:text-gray-400"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        </div>
      )}

      {/* Search Type Filter Section */}
      <div className="mb-6">
        <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">
          Search Type
        </h3>
        <div className="space-y-2">
          {SEARCH_TYPE_OPTIONS.map((option) => {
            const typeKey = TYPE_KEY_MAP[option.type];
            const isChecked = typeKey ? enabledTypes[typeKey] : false;
            // FR-011: At-least-one enforcement
            // If this is the only enabled type, disable the checkbox to prevent unchecking
            const isOnlyEnabled = typeKey && isChecked &&
              Object.values(enabledTypes).filter(Boolean).length === 1;

            // Show result count for all enabled & checked types
            const countMap: Record<string, number> = {
              'transcripts': totalResults,
              'video_titles': titleCount,
              'video_descriptions': descriptionCount,
            };
            const count = countMap[option.type];
            const displayLabel = isChecked && count !== undefined && count > 0
              ? `${option.label} (${count})`
              : option.label;

            return (
              <label
                key={option.type}
                className={`flex items-center gap-3 p-2 rounded-lg transition-colors ${
                  option.enabled && !isOnlyEnabled
                    ? 'hover:bg-gray-50 dark:hover:bg-gray-800 cursor-pointer'
                    : 'opacity-50 cursor-not-allowed'
                }`}
              >
                <input
                  type="checkbox"
                  id={`search-type-${option.type}`}
                  checked={isChecked}
                  disabled={!option.enabled || isOnlyEnabled}
                  aria-label={`${option.label} search type`}
                  className="w-4 h-4 text-blue-600 border-gray-300 dark:border-gray-600 rounded focus:ring-2 focus:ring-blue-500 disabled:cursor-not-allowed"
                  onChange={() => {
                    if (typeKey && option.enabled) {
                      onToggleType(typeKey);
                    }
                  }}
                />
                <span className="flex-1 text-sm text-gray-900 dark:text-gray-100">
                  {displayLabel}
                </span>
              </label>
            );
          })}
        </div>
      </div>

      {/* Language Filter Section - FR-014: Only show when transcripts enabled */}
      {enabledTypes.transcripts && availableLanguages.length > 0 && (
        <div>
          <label
            htmlFor="language-filter"
            className="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3"
          >
            Language
          </label>
          <select
            id="language-filter"
            value={selectedLanguage}
            onChange={handleLanguageChange}
            aria-label="Language filter"
            className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors"
          >
            <option value="">All languages</option>
            {sortedLanguages.map((code) => (
              <option key={code} value={code}>
                {getLanguageDisplayName(code)}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* T031: Include Unavailable Content Toggle (FR-021, NFR-003) */}
      {onToggleIncludeUnavailable && (
        <div className="pt-4 border-t border-gray-200 dark:border-gray-700">
          <label className="flex items-center gap-3 p-2 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 cursor-pointer transition-colors">
            <input
              type="checkbox"
              checked={includeUnavailable}
              onChange={onToggleIncludeUnavailable}
              className="w-4 h-4 text-blue-600 border-gray-300 dark:border-gray-600 rounded focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
              aria-label="Include unavailable content"
            />
            <span className="text-sm text-gray-700 dark:text-gray-300">
              Show unavailable content
            </span>
          </label>
        </div>
      )}
    </>
  );

  // Desktop: permanent sidebar
  if (!isResponsiveMode) {
    return (
      <aside
        role="complementary"
        aria-label="Search filters"
        className="w-full lg:w-64 p-4 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700"
      >
        {filterContent}
      </aside>
    );
  }

  // Mobile: bottom sheet
  if (isMobile) {
    return (
      <>
        {/* Backdrop */}
        <div
          className="fixed inset-0 bg-black/50 z-40"
          onClick={onClose}
          aria-hidden="true"
        />
        {/* Bottom Sheet */}
        <aside
          role="dialog"
          aria-modal="true"
          aria-label="Search filters"
          className="fixed bottom-0 left-0 right-0 z-50 bg-white dark:bg-gray-900 rounded-t-2xl shadow-2xl p-6 max-h-[80vh] overflow-y-auto"
        >
          {filterContent}
        </aside>
      </>
    );
  }

  // Tablet: slide-in drawer
  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/50 z-40"
        onClick={onClose}
        aria-hidden="true"
      />
      {/* Drawer */}
      <aside
        role="dialog"
        aria-modal="true"
        aria-label="Search filters"
        className="fixed right-0 top-0 bottom-0 z-50 w-80 bg-white dark:bg-gray-900 shadow-2xl p-6 overflow-y-auto"
      >
        {filterContent}
      </aside>
    </>
  );
}
