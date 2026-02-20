/**
 * VideoFilters Component
 *
 * Implements:
 * - T044: Main video filters panel layout
 * - T045: TagAutocomplete integration
 * - T047: URL state sync using useSearchParams
 * - T048: Filter clear functionality
 * - T042b: Frontend filter limit validation
 * - T058: TopicCombobox integration
 * - T059: Parent context path display in FilterPills
 * - T060: Indented hierarchical display (implemented in TopicCombobox)
 * - T061: Topic search with highlight matching (implemented in TopicCombobox)
 * - T062: URL state sync for topic filter (topic_id params)
 * - T063: No-match topic search (implemented in TopicCombobox)
 * - T071: Combined URL params persist all filters
 * - T072: URL pre-population on page load
 * - T073: Graceful handling of invalid URL filter values
 * - T074: Browser refresh preserves all filter state
 * - T075: Browser back/forward navigation with filter state
 * - T090: Responsive layout with mobile breakpoint
 * - T091: Touch-friendly 44px minimum targets
 * - T096: RTL layout support
 *
 * Features:
 * - Integrated TagAutocomplete, CategoryDropdown, TopicCombobox
 * - FilterPills display for active filters
 * - "Clear All" button to reset all filters
 * - URL state synchronization (tags, category, topic_id params)
 * - Filter limit validation (10 tags, 10 topics, 1 category, 15 total)
 * - Warning messages near limits
 * - Video count display
 * - Shareable URLs with all filter combinations
 * - Graceful handling of invalid filter values
 * - Browser navigation support (back/forward)
 * - Responsive mobile-first design with collapsible filters
 * - RTL (Right-to-Left) language support
 *
 * Layout:
 * ┌────────────────────────────────────────────────────────────────┐
 * │ 🔍 Search tags...    📂 Category ▼    🌐 Topics ▼   Clear All  │
 * ├────────────────────────────────────────────────────────────────┤
 * │ Active: [🏷️ music ×] [📂 Gaming ×] [🌐 Arts > Music ×]         │
 * │ Showing 47 videos                                              │
 * └────────────────────────────────────────────────────────────────┘
 *
 * @see T044: VideoFilters component
 * @see T047: URL state sync
 * @see T071-T075: URL composability
 * @see T090-T096: Mobile & accessibility polish
 * @see FR-034: Filter limits
 */

import { useSearchParams } from 'react-router-dom';
import { useEffect, useState, useId } from 'react';

import { TagAutocomplete } from './TagAutocomplete';
import { CategoryDropdown } from './CategoryDropdown';
import { TopicCombobox } from './TopicCombobox';
import { FilterPills } from './FilterPills';
import type { FilterPillType } from './FilterPills';
import { FilterToggle } from './FilterToggle';
import { useCategories } from '../hooks/useCategories';
import { useTopics } from '../hooks/useTopics';
import { useOnlineStatus } from '../hooks/useOnlineStatus';
import { FILTER_LIMITS } from '../types/filters';

interface VideoFiltersProps {
  /** Total number of videos matching current filters */
  videoCount?: number | null;
  /** Optional className for container */
  className?: string;
  /** API warnings for partial results (T088) */
  warnings?: Array<{ filter: string; message: string }>;
}

/**
 * Calculates the total number of active filters across all types.
 */
function calculateTotalFilters(
  tags: string[],
  category: string | null,
  topicIds: string[]
): number {
  return tags.length + (category ? 1 : 0) + topicIds.length;
}

/**
 * Checks if any filter limit is approaching (80% or more).
 */
function isApproachingLimit(
  tags: string[],
  category: string | null,
  topicIds: string[]
): boolean {
  const total = calculateTotalFilters(tags, category, topicIds);
  return (
    tags.length >= FILTER_LIMITS.MAX_TAGS * 0.8 ||
    topicIds.length >= FILTER_LIMITS.MAX_TOPICS * 0.8 ||
    total >= FILTER_LIMITS.MAX_TOTAL * 0.8
  );
}

/**
 * VideoFilters provides a comprehensive filtering UI for videos.
 *
 * Integrates tag autocomplete, category dropdown, and topic combobox with
 * URL state synchronization. Displays active filters as pills and enforces
 * filter limits to maintain performance.
 *
 * @example
 * ```tsx
 * <VideoFilters videoCount={47} />
 * ```
 */
export function VideoFilters({
  videoCount = null,
  className = '',
  warnings = [],
}: VideoFiltersProps) {
  const [searchParams, setSearchParams] = useSearchParams();
  const [warningMessage, setWarningMessage] = useState<string>('');

  // Unique ID for ARIA relationships
  const filterId = useId();

  // Check online status for offline indicator (T084)
  const isOnline = useOnlineStatus();

  // Read filter state from URL with sanitization (T073)
  // Filter out empty/whitespace-only values for robust URL handling
  const rawTags = searchParams.getAll('tag');
  const tags = rawTags.filter((tag) => tag && tag.trim().length > 0);

  const rawCategory = searchParams.get('category');
  const category = rawCategory && rawCategory.trim().length > 0 ? rawCategory : null;

  const rawTopicIds = searchParams.getAll('topic_id');
  const topicIds = rawTopicIds.filter((id) => id && id.trim().length > 0);

  // Read boolean filter params from URL (Feature 027)
  const likedOnly = searchParams.get('liked_only') === 'true';
  const hasTranscript = searchParams.get('has_transcript') === 'true';

  // Fetch categories and topics for display names
  const { categories } = useCategories();
  const { topics } = useTopics();

  // Calculate filter counts (include boolean filters in active count)
  const totalFilters = calculateTotalFilters(tags, category, topicIds);
  const booleanFilterCount = (likedOnly ? 1 : 0) + (hasTranscript ? 1 : 0);
  const hasActiveFilters = totalFilters > 0 || booleanFilterCount > 0;
  const approachingLimit = isApproachingLimit(tags, category, topicIds);

  // Log warnings for invalid filter values (T073)
  useEffect(() => {
    if (category && !categories.find((c) => c.category_id === category)) {
      console.warn(`[VideoFilters] Invalid category ID in URL: "${category}"`);
    }

    topicIds.forEach((topicId) => {
      if (!topics.find((t) => t.topic_id === topicId)) {
        console.warn(`[VideoFilters] Invalid topic ID in URL: "${topicId}"`);
      }
    });
  }, [category, topicIds, categories, topics]);

  // Update warning message when approaching limits
  useEffect(() => {
    if (totalFilters >= FILTER_LIMITS.MAX_TOTAL) {
      setWarningMessage(
        `Maximum filter limit reached (${FILTER_LIMITS.MAX_TOTAL}). Remove filters to add more.`
      );
    } else if (tags.length >= FILTER_LIMITS.MAX_TAGS) {
      setWarningMessage(
        `Maximum tag limit reached (${FILTER_LIMITS.MAX_TAGS}). Remove tags to add more.`
      );
    } else if (topicIds.length >= FILTER_LIMITS.MAX_TOPICS) {
      setWarningMessage(
        `Maximum topic limit reached (${FILTER_LIMITS.MAX_TOPICS}). Remove topics to add more.`
      );
    } else if (approachingLimit) {
      setWarningMessage(
        `Approaching filter limits (${totalFilters}/${FILTER_LIMITS.MAX_TOTAL} total).`
      );
    } else {
      setWarningMessage('');
    }
  }, [tags.length, topicIds.length, totalFilters, approachingLimit]);

  /**
   * Adds a tag to the URL parameters.
   */
  const handleTagAdd = (tag: string) => {
    if (tags.includes(tag)) return;
    if (tags.length >= FILTER_LIMITS.MAX_TAGS) return;
    if (totalFilters >= FILTER_LIMITS.MAX_TOTAL) return;

    const newParams = new URLSearchParams(searchParams);
    newParams.append('tag', tag);
    setSearchParams(newParams);
  };

  /**
   * Removes a tag from the URL parameters.
   */
  const handleTagRemove = (tag: string) => {
    const newParams = new URLSearchParams(searchParams);
    // Remove all instances of this tag
    newParams.delete('tag');
    tags.filter((t) => t !== tag).forEach((t) => newParams.append('tag', t));
    setSearchParams(newParams);
  };

  /**
   * Updates the category in URL parameters.
   */
  const handleCategoryChange = (categoryId: string | null) => {
    const newParams = new URLSearchParams(searchParams);
    if (categoryId) {
      newParams.set('category', categoryId);
    } else {
      newParams.delete('category');
    }
    setSearchParams(newParams);
  };

  /**
   * Adds a topic to the URL parameters.
   */
  const handleTopicAdd = (topicId: string) => {
    if (topicIds.includes(topicId)) return;
    if (topicIds.length >= FILTER_LIMITS.MAX_TOPICS) return;
    if (totalFilters >= FILTER_LIMITS.MAX_TOTAL) return;

    const newParams = new URLSearchParams(searchParams);
    newParams.append('topic_id', topicId);
    setSearchParams(newParams);
  };

  /**
   * Removes a topic from the URL parameters.
   */
  const handleTopicRemove = (topicId: string) => {
    const newParams = new URLSearchParams(searchParams);
    // Remove all instances of this topic
    newParams.delete('topic_id');
    topicIds
      .filter((id) => id !== topicId)
      .forEach((id) => newParams.append('topic_id', id));
    setSearchParams(newParams);
  };

  /**
   * Clears all filters from URL parameters.
   */
  const handleClearAll = () => {
    const newParams = new URLSearchParams();
    // Preserve non-filter parameters if any
    const filterKeys = ['tag', 'category', 'topic_id', 'include_unavailable', 'liked_only', 'has_transcript'];
    searchParams.forEach((value, key) => {
      if (!filterKeys.includes(key)) {
        newParams.append(key, value);
      }
    });
    setSearchParams(newParams);
  };

  /**
   * Handles filter removal from FilterPills.
   * Supports tag, category, topic, and boolean pill types.
   */
  const handleFilterRemove = (
    type: FilterPillType,
    value: string
  ) => {
    switch (type) {
      case 'tag':
        handleTagRemove(value);
        break;
      case 'category':
        handleCategoryChange(null);
        break;
      case 'topic':
        handleTopicRemove(value);
        break;
      case 'boolean': {
        // Remove the boolean URL param (e.g., liked_only, has_transcript)
        const newParams = new URLSearchParams(searchParams);
        newParams.delete(value);
        setSearchParams(newParams);
        break;
      }
    }
  };

  // Build filter pills data (including boolean pills for Feature 027)
  const filterPills = [
    ...tags.map((tag) => ({
      type: 'tag' as const,
      value: tag,
      label: tag,
    })),
    ...(category
      ? [
          {
            type: 'category' as const,
            value: category,
            label:
              categories.find((c) => c.category_id === category)?.name ||
              'Unknown',
          },
        ]
      : []),
    ...topicIds.map((topicId) => {
      const topic = topics.find((t) => t.topic_id === topicId);
      const topicLabel = topic?.name || 'Unknown';
      return {
        type: 'topic' as const,
        value: topicId,
        label: topicLabel,
        fullText: topic?.parent_path
          ? `${topic.parent_path} > ${topic.name}`
          : undefined,
      };
    }),
    // Boolean filter pills (Feature 027, T031)
    ...(likedOnly
      ? [{ type: 'boolean' as const, value: 'liked_only', label: 'Liked' }]
      : []),
    ...(hasTranscript
      ? [{ type: 'boolean' as const, value: 'has_transcript', label: 'Has transcripts' }]
      : []),
  ];

  return (
    <div
      id={filterId}
      className={`space-y-4 p-4 sm:p-6 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-sm ${className}`}
      role="region"
      aria-label="Video filter panel"
    >
      {/* Filter Controls Row - Stack vertically on mobile, grid on desktop */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Tag Autocomplete */}
        <div className="w-full">
          <TagAutocomplete
            selectedTags={tags}
            onTagSelect={handleTagAdd}
            onTagRemove={handleTagRemove}
            maxTags={FILTER_LIMITS.MAX_TAGS}
          />
        </div>

        {/* Category Dropdown */}
        <div className="w-full">
          <CategoryDropdown
            selectedCategory={category}
            onCategoryChange={handleCategoryChange}
          />
        </div>

        {/* Topic Combobox */}
        <div className="w-full">
          <TopicCombobox
            selectedTopics={topicIds}
            onTopicSelect={handleTopicAdd}
            onTopicRemove={handleTopicRemove}
            maxTopics={FILTER_LIMITS.MAX_TOPICS}
          />
        </div>
      </div>

      {/* T010: Include Unavailable Content Toggle - Migrated to FilterToggle (FR-021, NFR-003) */}
      <div className="pt-3 border-t border-gray-200 dark:border-gray-700">
        <FilterToggle
          paramKey="include_unavailable"
          label="Show unavailable content"
        />
      </div>

      {/* Offline Indicator (T084) */}
      {!isOnline && (
        <div
          className="px-3 py-2 bg-gray-50 dark:bg-gray-900/40 border border-gray-300 dark:border-gray-600 rounded text-sm text-gray-800 dark:text-gray-200"
          role="alert"
          aria-live="assertive"
        >
          <span className="font-medium">📡 Offline:</span> You are currently offline. Some features may not work.
        </div>
      )}

      {/* Partial Results Warning (T088) */}
      {warnings.length > 0 && (
        <div
          className="px-3 py-2 bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-700 rounded"
          role="alert"
          aria-live="polite"
        >
          <p className="text-sm font-medium text-yellow-800 dark:text-yellow-200 mb-1">
            ⚠️ Some filters could not be applied:
          </p>
          <ul className="text-xs text-yellow-700 dark:text-yellow-300 list-disc list-inside space-y-0.5">
            {warnings.map((warning, index) => (
              <li key={index}>
                <span className="font-medium">{warning.filter}:</span> {warning.message}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Warning Message */}
      {warningMessage && (
        <div
          className="px-3 py-2 bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-700 rounded text-sm text-yellow-800 dark:text-yellow-200"
          role="alert"
          aria-live="polite"
        >
          <span className="font-medium">⚠️ Warning:</span> {warningMessage}
        </div>
      )}

      {/* Active Filters Section */}
      {hasActiveFilters && (
        <div className="space-y-3 pt-3 border-t border-gray-200 dark:border-gray-700">
          {/* Active Filters Header */}
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
            <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300">
              Active Filters ({totalFilters + booleanFilterCount})
            </h3>
            <button
              type="button"
              onClick={handleClearAll}
              className="text-sm font-medium text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 rounded px-3 py-2 sm:px-2 sm:py-1 transition-colors w-full sm:w-auto min-h-[44px] sm:min-h-0"
            >
              Clear All
            </button>
          </div>

          {/* Filter Pills */}
          <FilterPills filters={filterPills} onRemove={handleFilterRemove} />

          {/* Video Count */}
          {videoCount !== null && (
            <p
              className="text-sm text-gray-600 dark:text-gray-400"
              role="status"
              aria-live="polite"
            >
              Showing {videoCount} video{videoCount !== 1 ? 's' : ''}
            </p>
          )}
        </div>
      )}

      {/* No Filters Message */}
      {!hasActiveFilters && (
        <p className="text-sm text-gray-500 dark:text-gray-400 text-center py-2">
          No active filters. Select tags, categories, or topics to filter
          videos.
        </p>
      )}
    </div>
  );
}
