/**
 * Formatting utilities for Chronovista frontend.
 *
 * Implements:
 * - FR-017: Format timestamps as "M:SS" for times under 1 hour, "H:MM:SS" for times >= 1 hour
 * - FR-018: Format dates as "MMM D, YYYY" (e.g., "Jan 15, 2024")
 *
 * @module utils/formatters
 */

// Re-export formatTimestamp for convenience
export { formatTimestamp } from "./formatTimestamp";

/**
 * Format ISO date string into human-readable format.
 * Format: "MMM D, YYYY" (e.g., "Jan 15, 2024")
 *
 * @param isoDate - ISO 8601 date string
 * @returns Formatted date string
 *
 * @example
 * ```ts
 * formatDate("2024-01-15T10:30:00Z");  // "Jan 15, 2024"
 * formatDate("2023-12-25");            // "Dec 25, 2023"
 * ```
 */
export function formatDate(isoDate: string): string {
  const date = new Date(isoDate);
  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}
