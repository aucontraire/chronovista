/**
 * SkipLink Component
 *
 * Implements:
 * - T036: Skip link to filter panel for jumping directly to results
 * - FR-ACC-001: WCAG 2.1 Level AA compliance
 * - FR-ACC-007: Visible focus indicators
 *
 * Features:
 * - Visually hidden by default
 * - Becomes visible when focused via keyboard
 * - Allows keyboard users to skip navigation and filters to go directly to content
 * - High contrast focus indicator
 *
 * @see FR-ACC-001: WCAG 2.1 Level AA Compliance
 * @see FR-ACC-007: Visible Focus Indicators
 */

import { useEffect } from 'react';

interface SkipLinkProps {
  /** Target element ID to skip to (e.g., "video-results") */
  targetId: string;
  /** Label for the skip link (default: "Skip to results") */
  label?: string;
  /** Optional className for custom styling */
  className?: string;
}

/**
 * SkipLink component for keyboard accessibility.
 *
 * Provides a skip link that is visually hidden by default but becomes visible
 * when focused. This allows keyboard users to bypass navigation and filter controls
 * to jump directly to the main content.
 *
 * @example
 * ```tsx
 * // At the top of the page
 * <SkipLink targetId="video-results" label="Skip to video results" />
 *
 * // Target element
 * <main id="video-results" tabIndex={-1}>
 *   <VideoGrid videos={videos} />
 * </main>
 * ```
 */
export function SkipLink({
  targetId,
  label = 'Skip to results',
  className = '',
}: SkipLinkProps) {
  useEffect(() => {
    // Ensure target element can receive focus (required for smooth scrolling focus)
    const targetElement = document.getElementById(targetId);
    if (targetElement && !targetElement.hasAttribute('tabindex')) {
      targetElement.setAttribute('tabindex', '-1');
    }
  }, [targetId]);

  const handleClick = (e: React.MouseEvent<HTMLAnchorElement>) => {
    e.preventDefault();
    const targetElement = document.getElementById(targetId);

    if (targetElement) {
      // Scroll to target element
      targetElement.scrollIntoView({ behavior: 'smooth', block: 'start' });

      // Set focus to target element after scrolling
      // Use setTimeout to allow smooth scroll to complete
      setTimeout(() => {
        targetElement.focus();
      }, 100);
    }
  };

  return (
    <a
      href={`#${targetId}`}
      onClick={handleClick}
      className={`
        skip-link
        absolute left-0 top-0 z-50
        px-4 py-3
        bg-blue-600 text-white
        font-medium text-base
        rounded-br-lg
        transition-transform
        -translate-y-full
        focus:translate-y-0
        focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2
        ${className}
      `}
      style={{
        // Ensure it's not completely hidden from assistive tech
        // but is visually off-screen until focused
        clipPath: 'inset(50%)',
        height: '1px',
        overflow: 'hidden',
        position: 'absolute',
        whiteSpace: 'nowrap',
        width: '1px',
      }}
      onFocus={(e) => {
        // Remove clip path when focused to make visible
        e.currentTarget.style.clipPath = 'none';
        e.currentTarget.style.height = 'auto';
        e.currentTarget.style.overflow = 'visible';
        e.currentTarget.style.width = 'auto';
      }}
      onBlur={(e) => {
        // Restore clip path when focus is lost
        e.currentTarget.style.clipPath = 'inset(50%)';
        e.currentTarget.style.height = '1px';
        e.currentTarget.style.overflow = 'hidden';
        e.currentTarget.style.width = '1px';
      }}
    >
      {label}
    </a>
  );
}
