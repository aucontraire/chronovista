/**
 * PlaylistFilterTabs Component
 *
 * Implements:
 * - CHK055: Filter Tab Navigation with keyboard support
 * - CHK063: Focus management on filter activation
 * - Three tabs: "All", "YouTube-Linked", "Local"
 * - URL search param synchronization
 * - WCAG 2.1 AA compliant with proper ARIA attributes
 *
 * Features:
 * - Active tab has distinct styling (selected state)
 * - Keyboard navigation with arrow keys
 * - Screen reader friendly with role="tablist" and aria-selected
 * - Focus indicators per CHK056
 * - Tab/Shift+Tab and Left/Right Arrow navigation
 * - Enter/Space activation
 *
 * @see CHK055: Filter Tab Navigation
 * @see CHK063: Focus Management
 * @see CHK056: Focus Indicators
 */

import { useEffect, useRef } from 'react';
import type { PlaylistFilterType } from '../types/playlist';

interface PlaylistFilterTabsProps {
  /** Current active filter type */
  currentFilter: PlaylistFilterType;
  /** Callback when filter selection changes */
  onFilterChange: (filter: PlaylistFilterType) => void;
  /** Optional className for custom styling */
  className?: string;
  /** Optional counts for each filter type (for badge display) */
  counts?: {
    all?: number;
    linked?: number;
    local?: number;
  };
}

/** Tab configuration for each filter type */
const TABS: Array<{
  id: PlaylistFilterType;
  label: string;
  ariaLabel: string;
}> = [
  {
    id: 'all',
    label: 'All',
    ariaLabel: 'Show all playlists',
  },
  {
    id: 'linked',
    label: 'YouTube-Linked',
    ariaLabel: 'Show YouTube-linked playlists',
  },
  {
    id: 'local',
    label: 'Local',
    ariaLabel: 'Show local playlists',
  },
];

/**
 * PlaylistFilterTabs component for filtering playlists by type.
 *
 * Provides accessible tab navigation with keyboard support and URL synchronization.
 *
 * @example
 * ```tsx
 * // Basic usage
 * <PlaylistFilterTabs
 *   currentFilter="all"
 *   onFilterChange={(filter) => setSearchParams({ filter })}
 * />
 *
 * // With counts
 * <PlaylistFilterTabs
 *   currentFilter="linked"
 *   onFilterChange={handleFilterChange}
 *   counts={{ all: 47, linked: 32, local: 15 }}
 * />
 * ```
 */
export function PlaylistFilterTabs({
  currentFilter,
  onFilterChange,
  className = '',
  counts,
}: PlaylistFilterTabsProps) {
  const tablistRef = useRef<HTMLDivElement>(null);

  // Handle keyboard navigation within tablist
  useEffect(() => {
    const tablist = tablistRef.current;
    if (!tablist) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (!target.matches('[role="tab"]')) return;

      const tabs = Array.from(tablist.querySelectorAll('[role="tab"]'));
      const currentIndex = tabs.indexOf(target);

      let nextIndex: number | null = null;

      switch (e.key) {
        case 'ArrowLeft':
          e.preventDefault();
          nextIndex = currentIndex > 0 ? currentIndex - 1 : tabs.length - 1;
          break;
        case 'ArrowRight':
          e.preventDefault();
          nextIndex = currentIndex < tabs.length - 1 ? currentIndex + 1 : 0;
          break;
        case 'Home':
          e.preventDefault();
          nextIndex = 0;
          break;
        case 'End':
          e.preventDefault();
          nextIndex = tabs.length - 1;
          break;
      }

      if (nextIndex !== null) {
        const nextTab = tabs[nextIndex] as HTMLButtonElement;
        nextTab.focus();
        // Activate the tab on arrow key navigation
        const filterId = nextTab.dataset.filterId as PlaylistFilterType;
        if (filterId) {
          onFilterChange(filterId);
        }
      }
    };

    tablist.addEventListener('keydown', handleKeyDown);
    return () => tablist.removeEventListener('keydown', handleKeyDown);
  }, [onFilterChange]);

  const handleTabClick = (filter: PlaylistFilterType) => {
    // Focus remains on activated tab per CHK063
    onFilterChange(filter);
  };

  return (
    <nav
      ref={tablistRef}
      role="tablist"
      aria-label="Filter playlists by type"
      className={`inline-flex items-center gap-1 border-b border-gray-200 dark:border-gray-700 mb-6 ${className}`}
    >
      {TABS.map((tab) => {
        const isSelected = currentFilter === tab.id;
        const count = counts?.[tab.id];

        return (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={isSelected}
            aria-label={tab.ariaLabel}
            data-filter-id={tab.id}
            onClick={() => handleTabClick(tab.id)}
            tabIndex={isSelected ? 0 : -1}
            className={`
              px-4 py-3 font-medium text-sm transition-colors relative
              border-b-2 -mb-px
              focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1 rounded-t-lg
              ${
                isSelected
                  ? 'text-blue-600 dark:text-blue-400 border-blue-600 dark:border-blue-400 font-semibold'
                  : 'text-gray-600 dark:text-gray-400 border-transparent hover:text-gray-900 dark:hover:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-800'
              }
              active:bg-gray-100 dark:active:bg-gray-700
            `}
          >
            <span className="flex items-center gap-1.5">
              {tab.label}
              {count !== undefined && count > 0 && (
                <span
                  className={`
                    px-1.5 py-0.5 text-xs rounded-full
                    ${
                      isSelected
                        ? 'bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-300'
                        : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300'
                    }
                  `}
                  aria-label={`${count} playlists`}
                >
                  {count}
                </span>
              )}
            </span>
          </button>
        );
      })}
    </nav>
  );
}
