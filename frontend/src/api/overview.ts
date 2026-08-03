/**
 * API client for the Overview Dashboard endpoint (Feature 061).
 *
 * Covers:
 * - GET /api/v1/overview — library aggregates in a single request
 *
 * Hand-written, like every other module here. `orval.config.ts` and
 * `make generate-api` exist and make the repo look like it has a generated
 * client, but `contracts/openapi.json` does not exist and orval's `clean: true`
 * would delete the hand-written modules in this directory. See GitHub #158.
 */

import { apiFetch } from "./config";

// ---------------------------------------------------------------------------
// Response types (match backend api/schemas/overview.py)
// ---------------------------------------------------------------------------

export interface PlaylistTypeCount {
  playlist_type: string;
  playlist_count: number;
  /**
   * True for every type except `regular`.
   *
   * Derived by the backend as "not regular", never from a named set — so a
   * `liked` or `favorites` playlist is correctly flagged rather than being
   * shown as user curation.
   */
  is_system: boolean;
}

export interface WatchLaterDepth {
  total: number;
  unwatched: number;
  /**
   * Target for the unwatched deep link (FR-025, FR-025a).
   *
   * Null when more than one Watch Later playlist exists: the depth spans all of
   * them, so no single playlist matches the figure clicked, and the figure is
   * rendered non-interactively instead.
   */
  playlist_id: string | null;
}

export interface LibraryRollup {
  watched_videos: number;
  saved_curated_videos: number;
  /** A video attribute, not a playlist type — belongs with the video rollups. */
  liked_videos: number;
}

export interface Overview {
  saved_and_forgotten: number;
  /**
   * Null when no Watch Later playlist exists.
   *
   * Distinct from a present-but-empty queue, which is `{total: 0, unwatched: 0}`.
   * Rendering both as zeros would tell someone with no Watch Later that their
   * queue is empty.
   */
  watch_later: WatchLaterDepth | null;
  playlist_inventory: PlaylistTypeCount[];
  rollup: LibraryRollup;
}

interface OverviewResponse {
  data: Overview;
  pagination: null;
}

/**
 * Fetch the library overview aggregates.
 *
 * @param signal - Optional AbortSignal, combined with the internal timeout.
 */
export async function fetchOverview(signal?: AbortSignal): Promise<Overview> {
  const response = await apiFetch<OverviewResponse>("/overview", {
    ...(signal !== undefined ? { externalSignal: signal } : {}),
  });
  return response.data;
}
