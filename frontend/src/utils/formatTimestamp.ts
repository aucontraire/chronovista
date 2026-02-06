/**
 * Timestamp formatting utilities for transcript display.
 *
 * Implements FR-018: Format timestamps as MM:SS or H:MM:SS based on duration.
 *
 * @module utils/formatTimestamp
 */

/**
 * Formats a timestamp in seconds to a human-readable string.
 *
 * For times under 1 hour: MM:SS format (e.g., "3:45", "12:08")
 * For times >= 1 hour: H:MM:SS format (e.g., "1:23:45", "2:00:00")
 *
 * @param seconds - Time in seconds (can be decimal)
 * @returns Formatted timestamp string
 *
 * @example
 * ```ts
 * formatTimestamp(0);      // "0:00"
 * formatTimestamp(65);     // "1:05"
 * formatTimestamp(3661);   // "1:01:01"
 * formatTimestamp(3600);   // "1:00:00"
 * formatTimestamp(125.5);  // "2:05" (decimal truncated)
 * ```
 */
export function formatTimestamp(seconds: number): string {
  // Handle negative numbers (shouldn't happen, but be safe)
  const totalSeconds = Math.max(0, Math.floor(seconds));

  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const secs = totalSeconds % 60;

  // Pad seconds to always be 2 digits
  const paddedSeconds = secs.toString().padStart(2, "0");

  if (hours > 0) {
    // H:MM:SS format for times >= 1 hour
    const paddedMinutes = minutes.toString().padStart(2, "0");
    return `${hours}:${paddedMinutes}:${paddedSeconds}`;
  }

  // MM:SS format for times < 1 hour (minutes not padded)
  return `${minutes}:${paddedSeconds}`;
}
