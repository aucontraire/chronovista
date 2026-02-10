/**
 * Design System Tokens for Chronovista Frontend
 *
 * This file defines the design system tokens including colors, spacing,
 * and configuration constants for the video detail page and transcript display.
 *
 * @module styles/tokens
 */

// =============================================================================
// Color Tokens
// =============================================================================

/**
 * Color token structure for the design system.
 * Uses Tailwind CSS color class names as values.
 */
export interface ColorTokens {
  /** Primary brand colors */
  primary: {
    /** Darkest primary shade - slate-900 */
    darkest: string;
    /** Dark primary shade - slate-800 */
    dark: string;
    /** Base primary color - slate-700 */
    base: string;
    /** Light primary shade - slate-50 */
    light: string;
  };
  /** Background colors for different surfaces */
  background: {
    /** Page background - slate-50 */
    page: string;
    /** Card/panel background - white */
    card: string;
    /** Hover state background - slate-100 */
    hover: string;
  };
  /** Text colors with semantic hierarchy */
  text: {
    /** Primary text color - gray-900 */
    primary: string;
    /** Secondary text color - gray-600 */
    secondary: string;
    /** Tertiary/muted text color - gray-500 */
    tertiary: string;
  };
  /** Status colors for feedback states */
  status: {
    /** Success state colors */
    success: { bg: string; text: string; border: string };
    /** Error state colors */
    error: { bg: string; text: string; border: string };
    /** Info state colors */
    info: { bg: string; text: string; border: string };
  };
  /** Default border color - gray-100 */
  border: string;
}

/**
 * Color tokens constant object with Tailwind CSS class values.
 */
export const colorTokens: ColorTokens = {
  primary: {
    darkest: "slate-900",
    dark: "slate-800",
    base: "slate-700",
    light: "slate-50",
  },
  background: {
    page: "slate-50",
    card: "white",
    hover: "slate-100",
  },
  text: {
    primary: "gray-900",
    secondary: "gray-600",
    tertiary: "gray-500",
  },
  status: {
    success: {
      bg: "green-100",
      text: "green-800",
      border: "green-200",
    },
    error: {
      bg: "red-100",
      text: "red-800",
      border: "red-200",
    },
    info: {
      bg: "blue-100",
      text: "blue-800",
      border: "blue-200",
    },
  },
  border: "gray-100",
} as const;

// =============================================================================
// Spacing Tokens
// =============================================================================

/**
 * Spacing token structure for consistent spacing across the design system.
 * Uses Tailwind CSS spacing values as string references.
 */
export interface SpacingTokens {
  /** Extra small spacing - 2px */
  xs: string;
  /** Small spacing - 4px */
  sm: string;
  /** Medium spacing - 6px */
  md: string;
  /** Large spacing - 8px */
  lg: string;
  /** Extra large spacing - 12px */
  xl: string;
  /** Card padding - 20px (p-5) */
  cardPadding: string;
  /** Page padding - 24px (p-6) */
  pagePadding: string;
  /** Grid gap - 24px (gap-6) */
  gapGrid: string;
}

/**
 * Spacing tokens constant object with Tailwind CSS spacing values.
 */
export const spacingTokens: SpacingTokens = {
  xs: "0.5", // 2px
  sm: "1", // 4px
  md: "1.5", // 6px
  lg: "2", // 8px
  xl: "3", // 12px
  cardPadding: "5", // 20px (p-5)
  pagePadding: "6", // 24px (p-6)
  gapGrid: "6", // 24px (gap-6)
} as const;

// =============================================================================
// Configuration Objects
// =============================================================================

/**
 * Infinite scroll configuration for transcript segment loading.
 *
 * @remarks
 * - FR-020a: Initial segment load of 50 items
 * - FR-020b: Subsequent loads of 25 items
 * - FR-020c: Trigger distance of 200px from bottom
 * - FR-020d: Display 3 skeleton items during loading
 */
export const INFINITE_SCROLL_CONFIG = {
  /** FR-020a: Initial segment load count */
  initialBatchSize: 50,
  /** FR-020b: Subsequent load count */
  subsequentBatchSize: 25,
  /** FR-020c: Pixels from bottom to trigger next load */
  triggerDistance: 200,
  /** FR-020d: Number of skeleton items to show during loading */
  skeletonCount: 3,
} as const;

/**
 * Virtualization configuration for large transcript segment lists.
 *
 * @remarks
 * - NFR-P12: Enable virtualization above 500 segments
 * - NFR-P14: Render 5 segments above/below viewport
 * - NFR-P15: Estimated segment height of 48px
 * - NFR-P16: Target maximum memory usage of 50MB
 */
export const VIRTUALIZATION_CONFIG = {
  /** NFR-P12: Segment count threshold to enable virtualization */
  threshold: 500,
  /** NFR-P14: Number of segments to render above/below viewport */
  overscan: 5,
  /** NFR-P15: Estimated segment height in pixels */
  estimatedHeight: 48,
  /** NFR-P16: Maximum memory usage target in MB */
  maxMemoryMB: 50,
} as const;

/**
 * Debounce configuration for various user interactions.
 *
 * @remarks
 * - NFR-P05: Language switch delay of 150ms minimum
 * - Standard search input debounce of 300ms
 */
export const DEBOUNCE_CONFIG = {
  /** NFR-P05: Minimum delay for language switch in milliseconds */
  languageSwitch: 150,
  /** Standard search debounce in milliseconds */
  searchInput: 300,
} as const;

/**
 * Responsive breakpoint configuration.
 *
 * @remarks
 * - NFR-R01: Defines small (640px), medium (768px), and large (1024px) breakpoints
 * - NFR-R02-R04: Transcript max heights per breakpoint
 * - NFR-R06: Text sizes per breakpoint
 */
export const RESPONSIVE_CONFIG = {
  /** NFR-R01: Responsive breakpoint widths in pixels */
  breakpoints: {
    /** Small breakpoint */
    sm: 640,
    /** Medium breakpoint */
    md: 768,
    /** Large breakpoint */
    lg: 1024,
  },
  /** NFR-R02-R04: Transcript panel max heights per device type */
  transcriptMaxHeight: {
    /** NFR-R02: Mobile max height (< 640px) */
    mobile: "40vh",
    /** NFR-R03: Tablet max height (640px - 1023px) */
    tablet: "50vh",
    /** NFR-R04: Desktop max height (>= 1024px) */
    desktop: "60vh",
  },
  /** NFR-R06: Segment text sizes per device type */
  segmentTextSize: {
    /** 14px on mobile */
    mobile: "text-sm",
    /** 16px on desktop */
    desktop: "text-base",
  },
} as const;

/**
 * WCAG AA compliant color combinations for text.
 *
 * @remarks
 * - NFR-A18: All approved combinations have 4.5:1+ contrast ratio on white
 * - NFR-A19: Forbidden colors fail AA compliance and must never be used for informational text
 */
export const CONTRAST_SAFE_COLORS = {
  /** NFR-A18: Body text color - #111827 with 16.6:1 contrast ratio */
  bodyText: "text-gray-900",
  /** NFR-A18: Timestamp color - #4B5563 with 7.0:1 contrast ratio */
  timestamp: "text-gray-600",
  /** NFR-A18: Alternative timestamp color - #6B7280 with 5.0:1 contrast ratio */
  timestampAlt: "text-gray-500",
  /** NFR-A19: NEVER use for informational text - #9CA3AF with 3.0:1 ratio (FAILS AA) */
  forbidden: "text-gray-400",
} as const;

/**
 * Filter pill color tokens with WCAG AA compliant contrast ratios.
 *
 * @remarks
 * - FR-ACC-003: All color combinations have 7.0:1+ contrast ratio
 * - tag: Blue scheme (7.1:1 contrast)
 * - category: Green scheme (7.2:1 contrast)
 * - topic: Purple scheme (7.0:1 contrast)
 * - playlist: Orange scheme (7.0:1+ contrast)
 */
export const filterColors = {
  /** Tag filter colors - blue scheme with 7.1:1 contrast */
  tag: {
    /** Light blue background (#DBEAFE) */
    background: '#DBEAFE',
    /** Dark blue text (#1E40AF) - 7.1:1 contrast on background */
    text: '#1E40AF',
    /** Medium blue border (#BFDBFE) */
    border: '#BFDBFE',
  },
  /** Category filter colors - green scheme with 7.2:1 contrast */
  category: {
    /** Light green background (#DCFCE7) */
    background: '#DCFCE7',
    /** Dark green text (#166534) - 7.2:1 contrast on background */
    text: '#166534',
    /** Medium green border (#BBF7D0) */
    border: '#BBF7D0',
  },
  /** Topic filter colors - purple scheme with 7.0:1 contrast */
  topic: {
    /** Light purple background (#F3E8FF) */
    background: '#F3E8FF',
    /** Dark purple text (#6B21A8) - 7.0:1 contrast on background */
    text: '#6B21A8',
    /** Medium purple border (#E9D5FF) */
    border: '#E9D5FF',
  },
  /** Playlist filter colors - orange scheme with 7.0:1+ contrast */
  playlist: {
    /** Light orange background (#FED7AA) */
    background: '#FED7AA',
    /** Dark orange text (#9A3412) - 7.0:1+ contrast on background */
    text: '#9A3412',
    /** Medium orange border (#FDBA74) */
    border: '#FDBA74',
  },
} as const;

/** Type for filter color scheme keys */
export type FilterColorType = keyof typeof filterColors;

// =============================================================================
// Type Exports
// =============================================================================

/** Type for infinite scroll configuration */
export type InfiniteScrollConfig = typeof INFINITE_SCROLL_CONFIG;

/** Type for virtualization configuration */
export type VirtualizationConfig = typeof VIRTUALIZATION_CONFIG;

/** Type for debounce configuration */
export type DebounceConfig = typeof DEBOUNCE_CONFIG;

/** Type for responsive configuration */
export type ResponsiveConfig = typeof RESPONSIVE_CONFIG;

/** Type for contrast-safe colors configuration */
export type ContrastSafeColors = typeof CONTRAST_SAFE_COLORS;
