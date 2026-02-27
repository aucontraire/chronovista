/**
 * FilterPills Component
 *
 * Implements:
 * - T043: Display active filters as colored pills
 * - T031: Boolean filter pills (Liked, Has transcripts) alongside tag/topic/category pills
 * - T092: WCAG AA color contrast (7.0:1+) across all states
 * - T091: Touch-friendly 44px minimum targets on mobile
 * - T094: 8px minimum spacing between interactive elements
 * - T096: RTL layout support
 * - FR-ACC-001: WCAG 2.1 Level AA compliance
 * - FR-ACC-002: Focus management
 * - FR-ACC-007: Visible focus indicators
 * - FR-021: Screen reader announcements on add/remove/clear
 * - FR-022: Focus management after pill removal
 *
 * Features:
 * - Color-coded pills: blue=tags, green=categories, purple=topics, slate=boolean
 * - canonical_tag pills: blue scheme + variation badge "{N} var." when alias_count > 1
 * - Remove button (x) for each pill
 * - Accessible with proper ARIA labels
 * - Keyboard navigation support
 * - Uses FILTER_COLORS from types/filters.ts with 7.0:1+ contrast
 * - Long tag truncation with tooltip (T050): 20 chars default, 25 chars for canonical_tag
 * - Touch-friendly 44px minimum targets on mobile (T091)
 * - RTL-aware layout with logical properties (T096)
 * - Focus management: after removal moves to next pill → previous → search input (FR-022)
 * - Screen reader live region announces add/remove/clear (FR-021)
 *
 * Color Contrast Ratios (WCAG AA compliant):
 * - Tags: Blue scheme (7.1:1 contrast)
 * - Categories: Green scheme (7.2:1 contrast)
 * - Topics: Purple scheme (7.0:1 contrast)
 * - Boolean: Slate scheme (7.0:1+ contrast)
 * - Canonical Tags: Blue scheme (7.1:1 contrast)
 *
 * @see FR-ACC-001: WCAG 2.1 Level AA Compliance
 * @see FR-ACC-002: Focus Management
 * @see FR-ACC-007: Visible Focus Indicators
 * @see FR-021: Screen Reader Announcements
 * @see FR-022: Focus Management After Removal
 * @see T091-T096: Mobile & accessibility polish
 */

import { useRef, useId, useState, useEffect } from 'react';
import { filterColors } from '../styles/tokens';

/**
 * Maximum characters before truncating filter text for standard types.
 * Raised to 25 to avoid truncating longer but common tag names.
 */
const MAX_FILTER_TEXT_LENGTH = 25;

/**
 * Maximum characters before truncating canonical_tag filter text (FR-022).
 * Same as MAX_FILTER_TEXT_LENGTH (25 chars) per spec.
 */
const MAX_CANONICAL_TAG_TEXT_LENGTH = 25;

/** Supported filter pill types. */
export type FilterPillType = 'tag' | 'category' | 'topic' | 'boolean' | 'canonical_tag';

export interface FilterPill {
  /** Type of filter (determines color scheme) */
  type: FilterPillType;
  /** Value/ID of the filter */
  value: string;
  /** Display label for the filter */
  label: string;
  /** Full display text for tooltip (optional, defaults to label) */
  fullText?: string | undefined;
  /**
   * Number of aliases for canonical_tag type (optional).
   * When alias_count > 1, shows "{alias_count - 1} var." badge.
   * When alias_count = 1 or omitted, no variation badge is shown.
   */
  aliasCount?: number | undefined;
}

export interface FilterPillsProps {
  /** Array of active filters to display */
  filters: FilterPill[];
  /** Callback when a filter is removed */
  onRemove: (type: FilterPillType, value: string) => void;
  /** Optional className for container */
  className?: string;
  /**
   * Ref to the search input element, used for focus management after all pills removed (FR-022).
   * When all pills are cleared and this ref is provided, focus moves to the search input.
   */
  searchInputRef?: React.RefObject<HTMLInputElement | null>;
}

/**
 * Truncates text with ellipsis if it exceeds the maximum length.
 *
 * @param text - Text to truncate
 * @param maxLength - Maximum character length
 * @returns Truncated text with ellipsis if needed
 */
function truncateText(text: string, maxLength: number): string {
  if (text.length <= maxLength) {
    return text;
  }
  return `${text.slice(0, maxLength)}...`;
}

/**
 * Gets the appropriate emoji icon for a filter type.
 */
function getFilterIcon(type: FilterPillType): string {
  switch (type) {
    case 'tag':
      return '\u{1F3F7}\uFE0F';
    case 'category':
      return '\u{1F4C2}';
    case 'topic':
      return '\u{1F310}';
    case 'boolean':
      return '\u{2705}';
    case 'canonical_tag':
      return '\u{1F3F7}\uFE0F';
  }
}

/**
 * FilterPills displays active filters as colored pills with remove buttons.
 *
 * Each filter type has a distinct color scheme for easy visual differentiation:
 * - Tags: Blue (7.1:1 contrast)
 * - Categories: Green (7.2:1 contrast)
 * - Topics: Purple (7.0:1 contrast)
 * - Boolean: Slate (7.0:1+ contrast) — for Liked, Has transcripts, etc.
 * - Canonical Tags: Blue (7.1:1 contrast) — with optional variation badge
 *
 * Focus management (FR-022): after pill removal, focus moves to:
 * 1. Next pill's remove button (if exists)
 * 2. Previous pill's remove button (if exists)
 * 3. Search input (via searchInputRef) if no pills remain
 *
 * Screen reader announcements (FR-021): aria-live region announces:
 * - Pill added: "{label} filter added. {N} active filters." + variation info
 * - Pill removed: "{label} filter removed. {N} active filters remaining."
 * - Clear All: "All filters cleared."
 *
 * @example
 * ```tsx
 * <FilterPills
 *   filters={[
 *     { type: 'tag', value: 'music', label: 'music' },
 *     { type: 'category', value: '10', label: 'Gaming' },
 *     { type: 'topic', value: '/m/04rlf', label: 'Music', fullText: 'Arts > Music' },
 *     { type: 'boolean', value: 'liked_only', label: 'Liked' },
 *     { type: 'canonical_tag', value: 'javascript', label: 'JavaScript', aliasCount: 4 },
 *   ]}
 *   onRemove={(type, value) => handleFilterRemove(type, value)}
 *   searchInputRef={searchInputRef}
 * />
 * ```
 */
export function FilterPills({
  filters,
  onRemove,
  className = '',
  searchInputRef,
}: FilterPillsProps) {
  const announcementId = useId();
  const [announcement, setAnnouncement] = useState('');

  // Track previous filter count to detect add vs remove for announcements
  const prevFiltersRef = useRef<FilterPill[]>([]);

  // Refs to all pill remove buttons for focus management (FR-022)
  const removeButtonRefs = useRef<(HTMLButtonElement | null)[]>([]);

  // Announce changes to screen readers (FR-021)
  useEffect(() => {
    const prev = prevFiltersRef.current;
    const curr = filters;

    if (prev.length === 0 && curr.length === 0) {
      prevFiltersRef.current = curr;
      return;
    }

    if (prev.length > 0 && curr.length === 0) {
      // All filters cleared
      setAnnouncement('All filters cleared.');
    } else if (curr.length > prev.length) {
      // Filter added
      const added = curr.find(
        (f) => !prev.some((p) => p.type === f.type && p.value === f.value)
      );
      if (added) {
        let msg = `${added.label} filter added. ${curr.length} active filter${curr.length !== 1 ? 's' : ''}.`;
        if (added.type === 'canonical_tag' && added.aliasCount && added.aliasCount > 1) {
          const varCount = added.aliasCount - 1;
          msg += ` Covers ${varCount} variation${varCount !== 1 ? 's' : ''}.`;
        }
        setAnnouncement(msg);
      }
    } else if (curr.length < prev.length) {
      // Filter removed
      const removed = prev.find(
        (p) => !curr.some((f) => f.type === p.type && f.value === p.value)
      );
      if (removed) {
        setAnnouncement(
          `${removed.label} filter removed. ${curr.length} active filter${curr.length !== 1 ? 's' : ''} remaining.`
        );
      }
    }

    prevFiltersRef.current = curr;
  }, [filters]);

  if (filters.length === 0) {
    return (
      // Keep the live region in the DOM even when no pills, so announcements still fire
      <div
        id={announcementId}
        role="status"
        aria-live="polite"
        aria-atomic="true"
        className="sr-only"
        data-testid="filter-pills-announcement"
      >
        {announcement}
      </div>
    );
  }

  /**
   * Handles pill removal with focus management (FR-022).
   * After removing a pill at `index`:
   * 1. Focus the next pill's remove button (if exists)
   * 2. Otherwise focus the previous pill's remove button
   * 3. Otherwise focus the search input via searchInputRef
   */
  const handleRemoveWithFocus = (
    type: FilterPillType,
    value: string,
    index: number
  ) => {
    onRemove(type, value);

    // Schedule focus after React re-renders (filters array changes)
    requestAnimationFrame(() => {
      const nextIndex = index < filters.length - 1 ? index : index - 1;
      const targetButton = removeButtonRefs.current[nextIndex];
      if (targetButton) {
        targetButton.focus();
      } else if (searchInputRef?.current) {
        searchInputRef.current.focus();
      }
    });
  };

  return (
    <>
      {/* Screen reader announcement region (FR-021) */}
      <div
        id={announcementId}
        role="status"
        aria-live="polite"
        aria-atomic="true"
        className="sr-only"
        data-testid="filter-pills-announcement"
      >
        {announcement}
      </div>

      <div
        className={`flex flex-wrap gap-2 ${className}`}
        role="list"
        aria-label="Active filters"
      >
        {/* gap-2 = 8px minimum spacing between interactive elements (T094) */}
        {filters.map((filter, index) => {
          const colorScheme = filterColors[filter.type];
          const maxLength =
            filter.type === 'canonical_tag'
              ? MAX_CANONICAL_TAG_TEXT_LENGTH
              : MAX_FILTER_TEXT_LENGTH;
          const displayText = truncateText(filter.label, maxLength);
          const isTruncated = displayText !== filter.label;
          const tooltipText = filter.fullText || filter.label;
          const icon = getFilterIcon(filter.type);

          // Variation badge for canonical_tag (alias_count - 1)
          const showVariationBadge =
            filter.type === 'canonical_tag' &&
            filter.aliasCount !== undefined &&
            filter.aliasCount > 1;
          const variationCount = showVariationBadge
            ? (filter.aliasCount as number) - 1
            : 0;

          return (
            <div
              key={`${filter.type}-${filter.value}`}
              role="listitem"
              className="inline-flex items-center gap-1.5 px-3 py-2 sm:py-1.5 min-h-[44px] sm:min-h-0 rounded-full text-sm font-medium border transition-colors"
              style={{
                backgroundColor: colorScheme.background,
                color: colorScheme.text,
                borderColor: colorScheme.border,
              }}
              title={isTruncated ? tooltipText : undefined}
            >
              {/* Filter icon */}
              <span aria-hidden="true">{icon}</span>

              {/* Filter label */}
              <span className="inline-flex items-baseline gap-1">
                <span className="sr-only">{filter.type}: </span>
                <span>{displayText}</span>
                {/* Variation badge: "{N} var." shown only when alias_count > 1 */}
                {showVariationBadge && (
                  <span
                    className="text-xs font-normal opacity-75"
                    aria-hidden="true"
                  >
                    {variationCount} var.
                  </span>
                )}
              </span>

              {/* Remove button - 44px minimum touch target on mobile */}
              <button
                ref={(el) => {
                  removeButtonRefs.current[index] = el;
                }}
                type="button"
                onClick={() => handleRemoveWithFocus(filter.type, filter.value, index)}
                aria-label={`Remove ${filter.type} filter: ${filter.label}`}
                className="inline-flex items-center justify-center min-w-[44px] min-h-[44px] sm:min-w-[24px] sm:min-h-[24px] -my-2 sm:my-0 -me-2 sm:me-0 rounded-full hover:bg-black/10 dark:hover:bg-white/10 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 transition-colors"
                style={{ color: colorScheme.text }}
              >
                <svg
                  className="w-4 h-4 sm:w-3 sm:h-3"
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
            </div>
          );
        })}
      </div>
    </>
  );
}
