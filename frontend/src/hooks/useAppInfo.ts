/**
 * useAppInfo hook for fetching application version and database statistics.
 *
 * Implements:
 * - GET /api/v1/settings/app-info — backend version, frontend version,
 *   database entity counts, and last-sync timestamps
 *
 * This is a read-only hook; no mutations are needed for app info.
 *
 * @module hooks/useAppInfo
 */

import { useQuery } from "@tanstack/react-query";

import { fetchAppInfo, type AppInfo } from "../api/settings";

// ---------------------------------------------------------------------------
// Query key constant
// ---------------------------------------------------------------------------

export const APP_INFO_KEY = ["app-info"] as const;

// ---------------------------------------------------------------------------
// Public hook return type
// ---------------------------------------------------------------------------

export interface UseAppInfoReturn {
  /** Application version and database statistics, or undefined while loading. */
  appInfo: AppInfo | undefined;
  /** True while the query is fetching for the first time. */
  isLoading: boolean;
  /** Any error thrown during the fetch, or null. */
  error: Error | null;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

/**
 * Fetches application info from the backend with a 30-second stale time.
 *
 * App info changes rarely (deploys, sync operations) so a moderate stale
 * window avoids unnecessary round-trips while keeping data reasonably fresh.
 *
 * @example
 * ```tsx
 * const { appInfo, isLoading, error } = useAppInfo();
 *
 * if (isLoading) return <Spinner />;
 * if (error) return <ErrorMessage error={error} />;
 *
 * return <p>Backend v{appInfo?.backend_version}</p>;
 * ```
 */
export function useAppInfo(): UseAppInfoReturn {
  const query = useQuery<
    Awaited<ReturnType<typeof fetchAppInfo>>,
    Error
  >({
    queryKey: APP_INFO_KEY,
    queryFn: ({ signal }) => fetchAppInfo(signal),
    staleTime: 30 * 1000, // 30 seconds — app info changes only on deploy/sync
  });

  return {
    appInfo: query.data?.data,
    isLoading: query.isLoading,
    error: query.error,
  };
}
