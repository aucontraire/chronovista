/**
 * usePrefersReducedMotion hook for accessibility support.
 *
 * Detects if the user has requested reduced motion via their operating system
 * preferences. This hook enables components to disable or reduce animations
 * for users who may experience discomfort from motion.
 *
 * Implements FR-012c accessibility requirement.
 *
 * @example
 * ```tsx
 * import { usePrefersReducedMotion } from '../hooks/usePrefersReducedMotion';
 *
 * function AnimatedComponent() {
 *   const prefersReducedMotion = usePrefersReducedMotion();
 *
 *   return (
 *     <div
 *       className={prefersReducedMotion ? 'static' : 'animate-bounce'}
 *     >
 *       Content
 *     </div>
 *   );
 * }
 * ```
 */

import { useEffect, useState } from "react";

/**
 * Media query for detecting reduced motion preference.
 */
const REDUCED_MOTION_QUERY = "(prefers-reduced-motion: reduce)";

/**
 * Hook that detects if the user prefers reduced motion.
 *
 * Returns true if the user has enabled reduced motion in their operating
 * system settings. The hook listens for changes to the preference and
 * updates automatically if the user changes their setting while the
 * application is running.
 *
 * @returns True if the user prefers reduced motion, false otherwise.
 *
 * @example
 * ```tsx
 * const prefersReducedMotion = usePrefersReducedMotion();
 *
 * // Conditionally apply animation classes
 * const animationClass = prefersReducedMotion
 *   ? ''
 *   : 'transition-transform duration-300';
 *
 * // Or use for imperative animations
 * useEffect(() => {
 *   if (!prefersReducedMotion) {
 *     startAnimation();
 *   }
 * }, [prefersReducedMotion]);
 * ```
 */
export function usePrefersReducedMotion(): boolean {
  // Default to false for SSR safety (assume animations are okay until we can check)
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(false);

  useEffect(() => {
    // Check if matchMedia is available (browser environment)
    if (typeof window === "undefined" || !window.matchMedia) {
      return;
    }

    const mediaQuery = window.matchMedia(REDUCED_MOTION_QUERY);

    // Set initial value
    setPrefersReducedMotion(mediaQuery.matches);

    /**
     * Handler for media query changes.
     * Updates state when user changes their reduced motion preference.
     */
    const handleChange = (event: MediaQueryListEvent): void => {
      setPrefersReducedMotion(event.matches);
    };

    // Modern browsers support addEventListener on MediaQueryList
    // Older browsers only support addListener (deprecated)
    if (mediaQuery.addEventListener) {
      mediaQuery.addEventListener("change", handleChange);
    } else {
      // Fallback for older browsers
      mediaQuery.addListener(handleChange);
    }

    // Cleanup listener on unmount
    return () => {
      if (mediaQuery.removeEventListener) {
        mediaQuery.removeEventListener("change", handleChange);
      } else {
        // Fallback for older browsers
        mediaQuery.removeListener(handleChange);
      }
    };
  }, []);

  return prefersReducedMotion;
}
