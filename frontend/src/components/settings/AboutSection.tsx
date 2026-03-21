/**
 * AboutSection — displays application version, database statistics, and
 * last-sync timestamps within the Settings page.
 *
 * Implements Feature 049 requirements:
 * - FR-018: Backend and frontend version display
 * - FR-019: Database entity counts (Videos, Channels, Playlists, Transcripts,
 *            Corrections, Canonical Tags) in a responsive grid
 * - FR-020: Last-sync timestamps per data type, formatted as relative time
 * - FR-021: Loading skeleton while fetching
 * - FR-022: Inline error with retry button on API failure
 * - FR-025: "Never synced" for null sync timestamps
 * - FR-029: ARIA labels for statistic sections, semantic dl/dt/dd markup
 *
 * @module components/settings/AboutSection
 */

import { useCallback } from "react";

import { useAppInfo } from "../../hooks/useAppInfo";
import type { DatabaseStats } from "../../api/settings";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface StatItem {
  label: string;
  value: number;
}

interface SyncItem {
  key: string;
  label: string;
  timestamp: string | null;
}

// ---------------------------------------------------------------------------
// Relative time formatting
// ---------------------------------------------------------------------------

/**
 * Formats a UTC ISO-8601 timestamp string as a relative time string
 * (e.g. "2 hours ago", "3 days ago").
 *
 * Returns null when the input is null (never synced).
 * Falls back to the raw ISO string if the date is unparseable.
 *
 * Parameters
 * ----------
 * isoString : string | null
 *   The UTC timestamp string from the backend, or null.
 *
 * Returns
 * -------
 * string | null
 *   A human-readable relative string, or null for a null input.
 */
function formatRelativeTime(isoString: string | null): string | null {
  if (isoString === null) return null;

  const date = new Date(isoString);
  if (isNaN(date.getTime())) return isoString;

  const nowMs = Date.now();
  const diffMs = nowMs - date.getTime();
  const diffSeconds = Math.floor(diffMs / 1000);

  const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });

  if (Math.abs(diffSeconds) < 60) {
    return rtf.format(-diffSeconds, "second");
  }
  const diffMinutes = Math.floor(diffSeconds / 60);
  if (Math.abs(diffMinutes) < 60) {
    return rtf.format(-diffMinutes, "minute");
  }
  const diffHours = Math.floor(diffMinutes / 60);
  if (Math.abs(diffHours) < 24) {
    return rtf.format(-diffHours, "hour");
  }
  const diffDays = Math.floor(diffHours / 24);
  if (Math.abs(diffDays) < 30) {
    return rtf.format(-diffDays, "day");
  }
  const diffMonths = Math.floor(diffDays / 30);
  if (Math.abs(diffMonths) < 12) {
    return rtf.format(-diffMonths, "month");
  }
  const diffYears = Math.floor(diffMonths / 12);
  return rtf.format(-diffYears, "year");
}

/**
 * Formats a UTC ISO-8601 timestamp string as an absolute locale string for
 * use in the `title` tooltip attribute.
 *
 * Parameters
 * ----------
 * isoString : string | null
 *   The UTC timestamp string from the backend, or null.
 *
 * Returns
 * -------
 * string
 *   A locale-formatted date-time string, or an empty string for null input.
 */
function formatAbsoluteTime(isoString: string | null): string {
  if (isoString === null) return "";
  const date = new Date(isoString);
  if (isNaN(date.getTime())) return isoString;
  return date.toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

// ---------------------------------------------------------------------------
// Icons (inline SVG — no icon library dependency)
// ---------------------------------------------------------------------------

function ExclamationTriangleIcon({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      fill="currentColor"
      viewBox="0 0 24 24"
      className={className}
      aria-hidden="true"
    >
      <path
        fillRule="evenodd"
        d="M9.401 3.003c1.155-2 4.043-2 5.197 0l7.355 12.748c1.154 2-.29 4.5-2.599 4.5H4.645c-2.309 0-3.752-2.5-2.598-4.5L9.4 3.003ZM12 8.25a.75.75 0 0 1 .75.75v3.75a.75.75 0 0 1-1.5 0V9a.75.75 0 0 1 .75-.75Zm0 8.25a.75.75 0 1 0 0-1.5.75.75 0 0 0 0 1.5Z"
        clipRule="evenodd"
      />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Loading skeleton
// ---------------------------------------------------------------------------

function AboutSkeleton() {
  return (
    <div
      role="status"
      aria-label="Loading application information"
      aria-busy="true"
      className="animate-pulse space-y-6"
    >
      {/* Version skeleton */}
      <div>
        <div className="h-4 bg-slate-200 rounded w-32 mb-2" />
        <div className="h-3 bg-slate-100 rounded w-56" />
      </div>

      {/* Database stats skeleton — 6 cards */}
      <div>
        <div className="h-4 bg-slate-200 rounded w-40 mb-3" />
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <div key={i} className="bg-slate-100 rounded-lg p-4">
              <div className="h-6 bg-slate-200 rounded w-12 mb-1" />
              <div className="h-3 bg-slate-100 rounded w-20" />
            </div>
          ))}
        </div>
      </div>

      {/* Sync timestamps skeleton */}
      <div>
        <div className="h-4 bg-slate-200 rounded w-36 mb-3" />
        <div className="space-y-2">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="flex justify-between">
              <div className="h-3 bg-slate-100 rounded w-28" />
              <div className="h-3 bg-slate-100 rounded w-20" />
            </div>
          ))}
        </div>
      </div>

      <span className="sr-only">Loading application information…</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Version display (FR-018)
// ---------------------------------------------------------------------------

interface VersionDisplayProps {
  backendVersion: string;
  frontendVersion: string;
}

function VersionDisplay({ backendVersion, frontendVersion }: VersionDisplayProps) {
  return (
    <div>
      <h4
        id="about-version-heading"
        className="text-sm font-semibold text-slate-700 mb-1"
      >
        Version
      </h4>
      <dl
        aria-labelledby="about-version-heading"
        className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-slate-600"
      >
        <div className="flex items-center gap-1.5">
          <dt className="font-medium text-slate-800">Backend:</dt>
          <dd className="font-mono">{backendVersion}</dd>
        </div>
        <div className="flex items-center gap-1.5">
          <dt className="font-medium text-slate-800">Frontend:</dt>
          <dd className="font-mono">{frontendVersion}</dd>
        </div>
      </dl>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Database statistics grid (FR-019)
// ---------------------------------------------------------------------------

const DB_STAT_LABELS: { key: keyof DatabaseStats; label: string }[] = [
  { key: "videos", label: "Videos" },
  { key: "channels", label: "Channels" },
  { key: "playlists", label: "Playlists" },
  { key: "transcripts", label: "Transcripts" },
  { key: "corrections", label: "Corrections" },
  { key: "canonical_tags", label: "Canonical Tags" },
];

interface DatabaseStatsGridProps {
  stats: DatabaseStats;
}

function DatabaseStatsGrid({ stats }: DatabaseStatsGridProps) {
  const items: StatItem[] = DB_STAT_LABELS.map(({ key, label }) => ({
    label,
    value: stats[key],
  }));

  return (
    <div>
      <h4
        id="about-db-stats-heading"
        className="text-sm font-semibold text-slate-700 mb-3"
      >
        Database Statistics
      </h4>

      <dl
        aria-labelledby="about-db-stats-heading"
        className="grid grid-cols-2 sm:grid-cols-3 gap-3"
      >
        {items.map(({ label, value }) => (
          <div
            key={label}
            className="bg-slate-50 border border-slate-100 rounded-lg px-4 py-3"
          >
            <dt className="text-xs font-medium text-slate-500 mb-0.5">
              {label}
            </dt>
            <dd className="text-xl font-semibold text-slate-900 tabular-nums">
              {value.toLocaleString()}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sync timestamps (FR-020, FR-025)
// ---------------------------------------------------------------------------

/** Maps backend sync_timestamps keys to human-readable labels. */
const SYNC_KEY_LABELS: Record<string, string> = {
  subscriptions: "Subscriptions",
  videos: "Videos",
  transcripts: "Transcripts",
  playlists: "Playlists",
  topics: "Topics",
};

/** Preferred display order for sync keys. */
const SYNC_KEY_ORDER = [
  "subscriptions",
  "videos",
  "transcripts",
  "playlists",
  "topics",
];

interface SyncTimestampsProps {
  syncTimestamps: Record<string, string | null>;
}

function SyncTimestamps({ syncTimestamps }: SyncTimestampsProps) {
  // Build ordered list: known keys first (in SYNC_KEY_ORDER), then any extras
  const knownKeys = SYNC_KEY_ORDER.filter((k) => k in syncTimestamps);
  const extraKeys = Object.keys(syncTimestamps).filter(
    (k) => !SYNC_KEY_ORDER.includes(k)
  );
  const orderedKeys = [...knownKeys, ...extraKeys];

  const items: SyncItem[] = orderedKeys.map((key) => ({
    key,
    label: SYNC_KEY_LABELS[key] ?? key,
    timestamp: syncTimestamps[key] ?? null,
  }));

  return (
    <div>
      <h4
        id="about-sync-heading"
        className="text-sm font-semibold text-slate-700 mb-3"
      >
        Last Synced
      </h4>

      <dl
        aria-labelledby="about-sync-heading"
        className="divide-y divide-slate-100"
      >
        {items.map(({ key, label, timestamp }) => {
          const relative = formatRelativeTime(timestamp);
          const absolute = formatAbsoluteTime(timestamp);

          return (
            <div
              key={key}
              className="flex items-center justify-between py-2 first:pt-0 last:pb-0"
            >
              <dt className="text-sm text-slate-600">{label}</dt>
              <dd
                className="text-sm font-medium text-slate-800 text-right"
                title={absolute !== "" ? absolute : undefined}
              >
                {relative !== null ? (
                  <time dateTime={timestamp ?? undefined}>{relative}</time>
                ) : (
                  <span className="text-slate-400 font-normal italic">
                    Never synced
                  </span>
                )}
              </dd>
            </div>
          );
        })}
      </dl>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

/**
 * AboutSection renders the application info card within the Settings page.
 * It is fully self-contained — all data comes from the `useAppInfo` hook.
 *
 * Displays:
 * - Backend and frontend version strings (FR-018)
 * - Database entity counts in a responsive grid (FR-019)
 * - Per-data-type last-sync timestamps with relative formatting (FR-020, FR-025)
 * - Loading skeleton (FR-021) and inline error with retry (FR-022)
 *
 * @example
 * ```tsx
 * <AboutSection />
 * ```
 */
export function AboutSection() {
  const { appInfo, isLoading, error } = useAppInfo();

  const handleRetry = useCallback(() => {
    window.location.reload();
  }, []);

  return (
    <section aria-labelledby="about-heading">
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6">
        {/* ---------------------------------------------------------------- */}
        {/* Section header                                                   */}
        {/* ---------------------------------------------------------------- */}
        <div className="mb-6">
          <h3
            id="about-heading"
            className="text-lg font-semibold text-slate-900"
          >
            About
          </h3>
          <p className="text-sm text-slate-500 mt-1">
            Application version, database statistics, and last sync times.
          </p>
        </div>

        {/* ---------------------------------------------------------------- */}
        {/* Loading state (FR-021)                                           */}
        {/* ---------------------------------------------------------------- */}
        {isLoading && <AboutSkeleton />}

        {/* ---------------------------------------------------------------- */}
        {/* Error state (FR-022)                                             */}
        {/* ---------------------------------------------------------------- */}
        {!isLoading && error !== null && (
          <div
            role="alert"
            className="flex items-start gap-3 bg-rose-50 border border-rose-200 rounded-lg px-4 py-3"
          >
            <ExclamationTriangleIcon className="w-5 h-5 text-rose-600 flex-shrink-0 mt-0.5" />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-rose-800">
                Failed to load application information
              </p>
              <p className="text-xs text-rose-700 mt-1">{error.message}</p>
            </div>
            <button
              type="button"
              onClick={handleRetry}
              className="flex-shrink-0 text-sm font-medium text-rose-700 hover:text-rose-900 underline focus:outline-none focus-visible:ring-2 focus-visible:ring-rose-500 focus-visible:ring-offset-2 transition-colors"
            >
              Retry
            </button>
          </div>
        )}

        {/* ---------------------------------------------------------------- */}
        {/* Main content (once loaded and no error)                         */}
        {/* ---------------------------------------------------------------- */}
        {!isLoading && error === null && appInfo !== undefined && (
          <div className="space-y-6">
            {/* Version (FR-018) */}
            <VersionDisplay
              backendVersion={appInfo.backend_version}
              frontendVersion={appInfo.frontend_version}
            />

            <hr className="border-slate-100" aria-hidden="true" />

            {/* Database statistics (FR-019) */}
            <DatabaseStatsGrid stats={appInfo.database_stats} />

            <hr className="border-slate-100" aria-hidden="true" />

            {/* Sync timestamps (FR-020, FR-025) */}
            <SyncTimestamps syncTimestamps={appInfo.sync_timestamps} />
          </div>
        )}
      </div>
    </section>
  );
}
