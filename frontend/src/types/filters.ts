/**
 * Video classification filter types for the Chronovista frontend.
 * Supports filtering by tags, categories, and topics with hierarchical navigation.
 *
 * @module types/filters
 */

/**
 * Active video filters state.
 */
export interface VideoFilters {
  /** Selected tags (OR logic) */
  tags: string[];
  /** Selected category ID (single) */
  category: string | null;
  /** Selected topic IDs (OR logic) */
  topicIds: string[];
}

/**
 * Topic with hierarchy for combobox.
 * Includes parent path and depth for hierarchical display.
 */
export interface TopicHierarchyItem {
  /** YouTube topic ID */
  topic_id: string;
  /** Display name for the topic */
  name: string;
  /** Parent topic ID (null for top-level) */
  parent_topic_id: string | null;
  /** Full path of parent names (null for top-level) */
  parent_path: string | null;
  /** Depth in hierarchy (0 for top-level) */
  depth: number;
  /** Number of videos with this topic */
  video_count: number;
}

/**
 * Sidebar category navigation item.
 */
export interface SidebarCategory {
  /** YouTube category ID */
  category_id: string;
  /** Category display name */
  name: string;
  /** Number of videos in this category */
  video_count: number;
  /** Navigation URL for this category */
  href: string;
}

/**
 * Filter color scheme by type.
 * Used for visual differentiation of filter pills.
 */
export type FilterType = 'tag' | 'category' | 'topic';

/**
 * Color schemes for filter pills with WCAG AA contrast compliance.
 * All text colors have 7.0:1+ contrast ratio on their background.
 */
export const FILTER_COLORS: Record<FilterType, { bg: string; text: string; border: string }> = {
  tag: { bg: 'bg-blue-100', text: 'text-blue-800', border: 'border-blue-200' },
  category: { bg: 'bg-green-100', text: 'text-green-800', border: 'border-green-200' },
  topic: { bg: 'bg-purple-100', text: 'text-purple-800', border: 'border-purple-200' },
};

/**
 * RFC 7807 Problem Details for standardized error responses.
 * Used for API error responses (FR-052).
 */
export interface ProblemDetails {
  /** URI reference identifying the problem type */
  type: string;
  /** Human-readable summary of the problem type */
  title: string;
  /** HTTP status code */
  status: number;
  /** Human-readable explanation specific to this occurrence */
  detail: string;
  /** URI reference identifying the specific occurrence */
  instance: string;
}

/**
 * Filter warning codes for partial failures (FR-050).
 * Used when filters partially fail but the operation can continue.
 */
export type FilterWarningCode =
  | 'FILTER_PARTIAL_FAILURE'
  | 'FILTER_INVALID_VALUE'
  | 'FILTER_TIMEOUT';

/**
 * Warning for partial filter failures.
 * Allows graceful degradation when some filters fail (FR-050).
 */
export interface FilterWarning {
  /** Warning code identifying the failure type */
  code: FilterWarningCode;
  /** Type of filter that failed */
  filter_type: FilterType;
  /** Human-readable warning message */
  message: string;
}

/**
 * Filter validation limits (FR-034).
 * Prevents excessive filter combinations that could degrade performance.
 */
export const FILTER_LIMITS = {
  /** Maximum number of tags that can be selected simultaneously */
  MAX_TAGS: 10,
  /** Maximum number of topics that can be selected simultaneously */
  MAX_TOPICS: 10,
  /** Maximum number of categories (always 1 - single selection) */
  MAX_CATEGORIES: 1,
  /** Maximum total number of filters across all types */
  MAX_TOTAL: 15,
} as const;

/**
 * API timeout configuration (FR-036).
 * Defines timeout and retry behavior for filter API requests.
 */
export const TIMEOUT_CONFIG = {
  /** Maximum wait time for API response in milliseconds */
  API_TIMEOUT_MS: 10000,
  /** Retry delay sequence in milliseconds (exponential backoff) */
  RETRY_DELAYS_MS: [1000, 2000, 4000],
  /** Maximum number of retry attempts */
  MAX_RETRIES: 3,
} as const;
