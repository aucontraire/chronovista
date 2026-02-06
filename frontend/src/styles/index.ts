/**
 * Design System Barrel Export
 *
 * Re-exports all design tokens and styling utilities for convenient importing.
 *
 * @example
 * ```tsx
 * import { colorTokens, cardClasses, INFINITE_SCROLL_CONFIG } from '../styles';
 * ```
 *
 * @module styles
 */

// Token exports
export {
  colorTokens,
  spacingTokens,
  INFINITE_SCROLL_CONFIG,
  VIRTUALIZATION_CONFIG,
  DEBOUNCE_CONFIG,
  RESPONSIVE_CONFIG,
  CONTRAST_SAFE_COLORS,
} from "./tokens";

// Token type exports
export type {
  ColorTokens,
  SpacingTokens,
  InfiniteScrollConfig,
  VirtualizationConfig,
  DebounceConfig,
  ResponsiveConfig,
  ContrastSafeColors,
} from "./tokens";

// Card pattern exports
export {
  cardPatterns,
  cardClasses,
  cardVariants,
} from "./card";

// Card type exports
export type { CardPatternKey, CardVariantKey } from "./card";
