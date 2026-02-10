/**
 * FilterPills Component
 *
 * Implements:
 * - T043: Display active filters as colored pills
 * - T092: WCAG AA color contrast (7.0:1+) across all states
 * - T091: Touch-friendly 44px minimum targets on mobile
 * - T094: 8px minimum spacing between interactive elements
 * - T096: RTL layout support
 * - FR-ACC-001: WCAG 2.1 Level AA compliance
 * - FR-ACC-002: Focus management
 * - FR-ACC-007: Visible focus indicators
 *
 * Features:
 * - Color-coded pills: blue=tags, green=categories, purple=topics
 * - Remove button (×) for each pill
 * - Accessible with proper ARIA labels
 * - Keyboard navigation support
 * - Uses FILTER_COLORS from types/filters.ts with 7.0:1+ contrast
 * - Long tag truncation with tooltip (T050)
 * - Touch-friendly 44px minimum targets on mobile (T091)
 * - RTL-aware layout with logical properties (T096)
 *
 * Color Contrast Ratios (WCAG AA compliant):
 * - Tags: Blue scheme (7.1:1 contrast)
 * - Categories: Green scheme (7.2:1 contrast)
 * - Topics: Purple scheme (7.0:1 contrast)
 *
 * @see FR-ACC-001: WCAG 2.1 Level AA Compliance
 * @see FR-ACC-002: Focus Management
 * @see FR-ACC-007: Visible Focus Indicators
 * @see T091-T096: Mobile & accessibility polish
 */

import { filterColors } from '../styles/tokens';

/**
 * Maximum characters before truncating filter text.
 */
const MAX_FILTER_TEXT_LENGTH = 20;

interface FilterPill {
  /** Type of filter (determines color scheme) */
  type: 'tag' | 'category' | 'topic';
  /** Value/ID of the filter */
  value: string;
  /** Display label for the filter */
  label: string;
  /** Full display text for tooltip (optional, defaults to label) */
  fullText?: string | undefined;
}

interface FilterPillsProps {
  /** Array of active filters to display */
  filters: FilterPill[];
  /** Callback when a filter is removed */
  onRemove: (type: 'tag' | 'category' | 'topic', value: string) => void;
  /** Optional className for container */
  className?: string;
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
function getFilterIcon(type: 'tag' | 'category' | 'topic'): string {
  switch (type) {
    case 'tag':
      return '🏷️';
    case 'category':
      return '📂';
    case 'topic':
      return '🌐';
  }
}

/**
 * FilterPills displays active filters as colored pills with remove buttons.
 *
 * Each filter type has a distinct color scheme for easy visual differentiation:
 * - Tags: Blue (7.1:1 contrast)
 * - Categories: Green (7.2:1 contrast)
 * - Topics: Purple (7.0:1 contrast)
 *
 * @example
 * ```tsx
 * <FilterPills
 *   filters={[
 *     { type: 'tag', value: 'music', label: 'music' },
 *     { type: 'category', value: '10', label: 'Gaming' },
 *     { type: 'topic', value: '/m/04rlf', label: 'Music', fullText: 'Arts > Music' },
 *   ]}
 *   onRemove={(type, value) => handleFilterRemove(type, value)}
 * />
 * ```
 */
export function FilterPills({
  filters,
  onRemove,
  className = '',
}: FilterPillsProps) {
  if (filters.length === 0) {
    return null;
  }

  return (
    <div
      className={`flex flex-wrap gap-2 ${className}`}
      role="list"
      aria-label="Active filters"
    >
      {/* gap-2 = 8px minimum spacing between interactive elements (T094) */}
      {filters.map((filter) => {
        const colorScheme = filterColors[filter.type];
        const displayText = truncateText(filter.label, MAX_FILTER_TEXT_LENGTH);
        const isTruncated = displayText !== filter.label;
        const tooltipText = filter.fullText || filter.label;
        const icon = getFilterIcon(filter.type);

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
              {displayText}
            </span>

            {/* Remove button - 44px minimum touch target on mobile */}
            <button
              type="button"
              onClick={() => onRemove(filter.type, filter.value)}
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
  );
}
