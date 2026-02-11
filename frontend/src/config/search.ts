// src/config/search.ts
export const SEARCH_CONFIG = {
  // Debounce delay for search input (milliseconds)
  DEBOUNCE_DELAY: 300,

  // Number of results per API request
  PAGE_SIZE: 20,

  // Intersection Observer configuration for infinite scroll
  SCROLL_TRIGGER_MARGIN: '400px',
  SCROLL_TRIGGER_THRESHOLD: 0.0,

  // Virtualization threshold (enable after this many results)
  VIRTUALIZATION_THRESHOLD: 200,

  // Hard cap on accumulated results
  MAX_ACCUMULATED_RESULTS: 1000,

  // Query constraints
  MIN_QUERY_LENGTH: 2,
  MAX_QUERY_LENGTH: 500,

  // Loading skeleton configuration
  SKELETON_COUNT: 8,

  // Mobile filter panel auto-close delay (milliseconds)
  FILTER_PANEL_AUTO_CLOSE_DELAY: 500,

  // Title/Description search configuration (Feature 021)
  TITLE_SEARCH_LIMIT: 50,
  DESCRIPTION_SEARCH_LIMIT: 50,
  SNIPPET_ELLIPSIS: '...',

  // API endpoint paths for new search types
  TITLE_SEARCH_ENDPOINT: '/search/titles',
  DESCRIPTION_SEARCH_ENDPOINT: '/search/descriptions',

  // Stale time for title/description queries (2 minutes, consistent with segments)
  SEARCH_STALE_TIME: 2 * 60 * 1000,
} as const;

// Type for the config
export type SearchConfig = typeof SEARCH_CONFIG;
