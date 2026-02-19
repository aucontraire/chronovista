/**
 * Recovery data types for the Chronovista frontend.
 * These types match the backend API recovery response schemas.
 */

/**
 * Result data from a Wayback Machine recovery operation.
 * Contains detailed information about the recovery attempt.
 */
export interface RecoveryResultData {
  /** Whether the recovery operation succeeded */
  success: boolean;
  /** ISO 8601 timestamp of the Wayback snapshot used (null if none) */
  snapshot_used: string | null;
  /** List of field names that were successfully recovered */
  fields_recovered: string[];
  /** List of field names that were skipped (already present) */
  fields_skipped: string[];
  /** Total number of snapshots found in the archive */
  snapshots_available: number;
  /** Number of snapshots attempted during recovery */
  snapshots_tried: number;
  /** Human-readable reason for failure (null if successful) */
  failure_reason: string | null;
  /** Duration of the recovery operation in seconds */
  duration_seconds: number;
}
