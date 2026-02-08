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
} as const;

// Type for the config
export type SearchConfig = typeof SEARCH_CONFIG;
