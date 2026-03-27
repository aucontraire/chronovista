/**
 * API client functions for the settings endpoints (Feature 049).
 *
 * Covers:
 * - GET /api/v1/settings/supported-languages — full list of supported language codes
 * - GET /api/v1/settings/cache — image cache statistics
 * - DELETE /api/v1/settings/cache — purge all cached images
 * - GET /api/v1/settings/app-info — application version and database stats
 */

import { apiFetch } from "./config";

// ---------------------------------------------------------------------------
// Response types (match backend settings schemas)
// ---------------------------------------------------------------------------

export interface SupportedLanguage {
  code: string;
  display_name: string;
}

export interface SupportedLanguagesResponse {
  data: SupportedLanguage[];
  pagination: null;
}

export interface CacheStatus {
  channel_count: number;
  video_count: number;
  total_count: number;
  total_size_bytes: number;
  total_size_display: string;
  oldest_file: string | null;
  newest_file: string | null;
}

export interface CacheStatusResponse {
  data: CacheStatus;
  pagination: null;
}

export interface CachePurgeResult {
  purged: boolean;
  message: string;
}

export interface CachePurgeResponse {
  data: CachePurgeResult;
  pagination: null;
}

export interface DatabaseStats {
  videos: number;
  channels: number;
  playlists: number;
  transcripts: number;
  corrections: number;
  canonical_tags: number;
}

export interface AppInfo {
  backend_version: string;
  frontend_version: string;
  database_stats: DatabaseStats;
  sync_timestamps: Record<string, string | null>;
}

export interface AppInfoResponse {
  data: AppInfo;
  pagination: null;
}

// ---------------------------------------------------------------------------
// API client functions
// ---------------------------------------------------------------------------

export async function fetchSupportedLanguages(
  signal?: AbortSignal
): Promise<SupportedLanguagesResponse> {
  return apiFetch<SupportedLanguagesResponse>("/settings/supported-languages", {
    ...(signal !== undefined ? { externalSignal: signal } : {}),
  });
}

export async function fetchCacheStatus(
  signal?: AbortSignal
): Promise<CacheStatusResponse> {
  return apiFetch<CacheStatusResponse>("/settings/cache", {
    ...(signal !== undefined ? { externalSignal: signal } : {}),
  });
}

export async function purgeCache(): Promise<CachePurgeResponse> {
  return apiFetch<CachePurgeResponse>("/settings/cache", {
    method: "DELETE",
  });
}

export async function fetchAppInfo(
  signal?: AbortSignal
): Promise<AppInfoResponse> {
  return apiFetch<AppInfoResponse>("/settings/app-info", {
    ...(signal !== undefined ? { externalSignal: signal } : {}),
  });
}
