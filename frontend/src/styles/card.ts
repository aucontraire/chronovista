/**
 * Card styling utilities for Chronovista design system.
 *
 * Provides consistent patterns for card components including base styles,
 * interactive states, and accessibility-focused focus indicators.
 *
 * @example
 * ```tsx
 * import { cardClasses, cardPatterns } from '../styles/card';
 *
 * // Use the complete card class string
 * <div className={cardClasses}>Card content</div>
 *
 * // Or compose individual patterns
 * <div className={`${cardPatterns.base} ${cardPatterns.hover}`}>Card content</div>
 * ```
 */

/**
 * Individual card styling patterns that can be composed together.
 *
 * @property base - Core card appearance (background, corners, shadow, border)
 * @property hover - Hover state enhancements for interactive cards
 * @property focus - Focus state for keyboard navigation accessibility
 * @property transition - Animation timing for smooth state changes
 */
export const cardPatterns = {
  /** Base card appearance with white background, rounded corners, shadow, and subtle border */
  base: "bg-white rounded-xl shadow-md border border-gray-100",

  /** Hover state with enhanced shadow and slightly darker border */
  hover: "hover:shadow-xl hover:border-gray-200",

  /** Focus state for accessibility with visible focus ring */
  focus: "focus-within:ring-2 focus-within:ring-blue-500 focus-within:ring-offset-2",

  /** Smooth transition for all state changes */
  transition: "transition-all duration-200",
} as const;

/**
 * Type representing valid card pattern keys.
 */
export type CardPatternKey = keyof typeof cardPatterns;

/**
 * Pre-composed card class string combining all patterns.
 *
 * Use this for standard interactive cards that need all styling applied.
 *
 * @example
 * ```tsx
 * <article className={cardClasses}>
 *   <h2>Card Title</h2>
 *   <p>Card content goes here</p>
 * </article>
 * ```
 */
export const cardClasses = `${cardPatterns.base} ${cardPatterns.hover} ${cardPatterns.focus} ${cardPatterns.transition}`;

/**
 * Card variant classes for different use cases.
 */
export const cardVariants = {
  /** Default interactive card with all states */
  default: cardClasses,

  /** Static card without hover effects (for non-interactive content) */
  static: `${cardPatterns.base} ${cardPatterns.transition}`,

  /** Focusable card without hover effects (for keyboard-only interaction) */
  focusable: `${cardPatterns.base} ${cardPatterns.focus} ${cardPatterns.transition}`,
} as const;

/**
 * Type representing valid card variant keys.
 */
export type CardVariantKey = keyof typeof cardVariants;
