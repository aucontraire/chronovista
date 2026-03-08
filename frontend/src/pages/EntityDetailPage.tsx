/**
 * EntityDetailPage — displays a named entity's profile and all videos it
 * appears in.
 *
 * Route: /entities/:entityId
 *
 * Features (Feature 038, US8):
 * - T031: Header with canonical name, type badge, description, mention count,
 *   and video count
 * - T031: Infinite-scroll video list using useEntityVideos
 * - T031: Each video card shows title, channel name, mention count, first
 *   mention timestamp, and navigates to the video with a deep-link
 * - T031: 404 state for non-existent entities
 * - T031: Loading skeleton
 */

import { useEffect } from "react";
import { Link, useParams } from "react-router-dom";

import { useEntityVideos } from "../hooks/useEntityMentions";
import { apiFetch } from "../api/config";
import { useQuery } from "@tanstack/react-query";
import type { VideoEntitySummary } from "../api/entityMentions";

/** Default page title to restore on unmount */
const DEFAULT_PAGE_TITLE = "Chronovista";

// ---------------------------------------------------------------------------
// Entity detail type (fetched from the named-entities endpoint)
// ---------------------------------------------------------------------------

/** Minimal named entity detail fetched from /api/v1/entities/{entity_id} */
interface NamedEntityDetail {
  entity_id: string;
  canonical_name: string;
  entity_type: string;
  description: string | null;
  status: string;
  mention_count: number;
}

interface NamedEntityDetailResponse {
  data: NamedEntityDetail;
}

// ---------------------------------------------------------------------------
// Helper functions
// ---------------------------------------------------------------------------

/** Human-readable label for each entity_type value from the backend. */
const ENTITY_TYPE_LABELS: Record<string, string> = {
  person: "Person",
  organization: "Organization",
  place: "Place",
  event: "Event",
  work: "Work",
  concept: "Concept",
  other: "Other",
};

function getTypeLabel(entityType: string): string {
  return ENTITY_TYPE_LABELS[entityType] ?? entityType;
}

/** Badge colour by entity type */
const ENTITY_TYPE_COLORS: Record<string, string> = {
  person: "bg-indigo-100 text-indigo-700 border-indigo-200",
  organization: "bg-violet-100 text-violet-700 border-violet-200",
  place: "bg-emerald-100 text-emerald-700 border-emerald-200",
  event: "bg-amber-100 text-amber-700 border-amber-200",
  work: "bg-sky-100 text-sky-700 border-sky-200",
  concept: "bg-rose-100 text-rose-700 border-rose-200",
  other: "bg-slate-100 text-slate-700 border-slate-200",
};

function getTypeBadgeClass(entityType: string): string {
  return (
    ENTITY_TYPE_COLORS[entityType] ?? "bg-slate-100 text-slate-700 border-slate-200"
  );
}

/** Format a timestamp in seconds to MM:SS display. */
function formatTimestamp(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

// ---------------------------------------------------------------------------
// Icons
// ---------------------------------------------------------------------------

function ArrowLeftIcon({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      strokeWidth={1.5}
      stroke="currentColor"
      className={className}
      aria-hidden="true"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M10.5 19.5 3 12m0 0 7.5-7.5M3 12h18"
      />
    </svg>
  );
}

function WarningIcon({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      strokeWidth={1.5}
      stroke="currentColor"
      className={className}
      aria-hidden="true"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M12 9v3.75m9-.75a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 3.75h.008v.008H12v-.008Z"
      />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Skeleton
// ---------------------------------------------------------------------------

function EntityDetailSkeleton() {
  return (
    <div className="p-6 lg:p-8 animate-pulse" aria-label="Loading entity details">
      {/* Header skeleton */}
      <div className="bg-white rounded-xl shadow-md border border-gray-100 p-6 mb-6 space-y-4">
        <div className="h-8 w-64 rounded bg-slate-200" />
        <div className="h-5 w-24 rounded-full bg-slate-200" />
        <div className="h-4 w-full max-w-lg rounded bg-slate-200" />
        <div className="flex gap-6">
          <div className="h-4 w-32 rounded bg-slate-200" />
          <div className="h-4 w-24 rounded bg-slate-200" />
        </div>
      </div>
      {/* Video list skeleton */}
      <div className="space-y-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="bg-white rounded-xl shadow-sm border border-gray-100 p-4 space-y-2">
            <div className="h-5 w-3/4 rounded bg-slate-200" />
            <div className="h-4 w-1/2 rounded bg-slate-200" />
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Video card
// ---------------------------------------------------------------------------

interface EntityVideoCardProps {
  video_id: string;
  video_title: string;
  channel_name: string;
  mention_count: number;
  /** Start time (seconds) of the first mention — used for the deep link */
  first_mention_time: number;
  /** Segment id of the first mention — used for the ?seg= deep link */
  first_segment_id: number;
}

function EntityVideoCard({
  video_id,
  video_title,
  channel_name,
  mention_count,
  first_mention_time,
  first_segment_id,
}: EntityVideoCardProps) {
  const to =
    first_segment_id > 0
      ? `/videos/${video_id}?seg=${first_segment_id}&t=${Math.floor(first_mention_time)}`
      : `/videos/${video_id}?t=${Math.floor(first_mention_time)}`;

  return (
    <Link
      to={to}
      className="block bg-white rounded-xl shadow-sm border border-gray-100 p-4 hover:shadow-md hover:border-gray-200 transition-all focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2"
      aria-label={`${video_title} — ${mention_count} mention${mention_count === 1 ? "" : "s"}, first at ${formatTimestamp(first_mention_time)}`}
    >
      <h4 className="text-base font-semibold text-gray-900 mb-1 line-clamp-2">
        {video_title}
      </h4>
      <p className="text-sm text-gray-500 mb-2">{channel_name}</p>
      <div className="flex items-center gap-4 text-xs text-gray-500">
        <span>
          {mention_count} mention{mention_count === 1 ? "" : "s"}
        </span>
        <span>First at {formatTimestamp(first_mention_time)}</span>
      </div>
    </Link>
  );
}

// ---------------------------------------------------------------------------
// Main page component
// ---------------------------------------------------------------------------

/**
 * EntityDetailPage — profile page for a single named entity.
 *
 * Route: /entities/:entityId
 */
export function EntityDetailPage() {
  const { entityId } = useParams<{ entityId: string }>();

  // Fetch entity detail — we reuse the video-entity summary shape to get
  // the canonical_name, entity_type, and description.  The backend exposes
  // GET /api/v1/entities/{entity_id} which returns the NamedEntity record.
  const {
    data: entity,
    isLoading: entityLoading,
    isError: entityError,
    error: entityFetchError,
  } = useQuery<NamedEntityDetail | null>({
    queryKey: ["entity-detail", entityId],
    queryFn: async () => {
      if (!entityId) return null;
      try {
        const res = await apiFetch<NamedEntityDetailResponse>(
          `/entities/${entityId}`
        );
        return res.data;
      } catch (err: unknown) {
        // Re-throw so TanStack Query registers an error
        throw err;
      }
    },
    enabled: Boolean(entityId),
    staleTime: 5 * 60 * 1000,
    gcTime: 10 * 60 * 1000,
    retry: (failureCount, err) => {
      const status = (err as { status?: number } | null)?.status;
      if (status === 404) return false;
      return failureCount < 3;
    },
  });

  // Infinite-scroll video list
  const {
    videos,
    total,
    isLoading: videosLoading,
    hasNextPage,
    isFetchingNextPage,
    loadMoreRef,
  } = useEntityVideos(entityId ?? "");

  // Browser tab title
  useEffect(() => {
    if (entity) {
      document.title = `${entity.canonical_name} — Chronovista`;
    }
    return () => {
      document.title = DEFAULT_PAGE_TITLE;
    };
  }, [entity]);

  // Loading state
  if (entityLoading) {
    return <EntityDetailSkeleton />;
  }

  // 404 — entity not found
  const notFound =
    (!entity && !entityLoading) ||
    (entityError &&
      ((entityFetchError as { status?: number } | null)?.status === 404 ||
        entity === null));

  if (notFound) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[calc(100vh-4rem)] p-8">
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-12 text-center max-w-md">
          <div className="mx-auto w-16 h-16 mb-6 text-slate-400 bg-slate-100 rounded-full p-4">
            <WarningIcon className="w-full h-full" />
          </div>
          <h2 className="text-2xl font-bold text-slate-900 mb-3">
            Entity Not Found
          </h2>
          <p className="text-slate-600">
            The entity you're looking for doesn't exist or has been removed.
          </p>
          <Link
            to="/videos"
            className="inline-flex items-center mt-6 px-6 py-3 bg-slate-900 text-white font-semibold rounded-lg hover:bg-slate-800 transition-colors focus:outline-none focus:ring-2 focus:ring-slate-900 focus:ring-offset-2"
          >
            <ArrowLeftIcon className="w-5 h-5 mr-2" />
            Back to Videos
          </Link>
        </div>
      </div>
    );
  }

  if (!entity) {
    return null;
  }

  return (
    <div className="p-6 lg:p-8">
      {/* Back navigation */}
      <div className="mb-6">
        <Link
          to="/videos"
          className="inline-flex items-center text-slate-600 hover:text-slate-900 transition-colors"
        >
          <ArrowLeftIcon className="w-5 h-5 mr-2" />
          Back to Videos
        </Link>
      </div>

      {/* Entity header card */}
      <article className="bg-white rounded-xl shadow-md border border-gray-100 p-6 lg:p-8 mb-6">
        {/* Name + type badge */}
        <div className="flex flex-wrap items-start gap-3 mb-4">
          <h1 className="text-2xl lg:text-3xl font-bold text-gray-900">
            {entity.canonical_name}
          </h1>
          <span
            className={`inline-flex items-center px-3 py-1 text-sm font-medium rounded-full border ${getTypeBadgeClass(entity.entity_type)}`}
            aria-label={`Entity type: ${getTypeLabel(entity.entity_type)}`}
          >
            {getTypeLabel(entity.entity_type)}
          </span>
        </div>

        {/* Description */}
        {entity.description ? (
          <p className="text-gray-600 mb-4 max-w-3xl">{entity.description}</p>
        ) : (
          <p className="text-gray-400 italic mb-4">No description available.</p>
        )}

        {/* Stats row */}
        <div className="flex flex-wrap items-center gap-6 text-sm text-gray-500">
          <span>
            <strong className="text-gray-900 font-semibold">
              {entity.mention_count.toLocaleString()}
            </strong>{" "}
            mention{entity.mention_count === 1 ? "" : "s"}
          </span>
          {total !== null && (
            <span>
              <strong className="text-gray-900 font-semibold">
                {total.toLocaleString()}
              </strong>{" "}
              video{total === 1 ? "" : "s"}
            </span>
          )}
        </div>
      </article>

      {/* Video list section */}
      <section aria-labelledby="entity-videos-heading">
        <h2
          id="entity-videos-heading"
          className="text-lg font-semibold text-gray-900 mb-4"
        >
          Videos
        </h2>

        {/* Loading skeleton for video list */}
        {videosLoading && (
          <div className="space-y-4 animate-pulse">
            {[1, 2, 3].map((i) => (
              <div
                key={i}
                className="bg-white rounded-xl border border-gray-100 p-4 space-y-2"
              >
                <div className="h-5 w-3/4 rounded bg-slate-200" />
                <div className="h-4 w-1/2 rounded bg-slate-200" />
              </div>
            ))}
          </div>
        )}

        {/* Video cards */}
        {!videosLoading && videos.length > 0 && (
          <div className="space-y-4">
            {videos.map((v) => {
              const firstMention = v.mentions[0];
              return (
                <EntityVideoCard
                  key={v.video_id}
                  video_id={v.video_id}
                  video_title={v.video_title}
                  channel_name={v.channel_name}
                  mention_count={v.mention_count}
                  first_mention_time={firstMention?.start_time ?? 0}
                  first_segment_id={firstMention?.segment_id ?? 0}
                />
              );
            })}
          </div>
        )}

        {/* Empty state */}
        {!videosLoading && videos.length === 0 && (
          <div className="bg-white rounded-xl border border-gray-100 p-8 text-center">
            <p className="text-gray-500">No videos found for this entity.</p>
          </div>
        )}

        {/* Infinite scroll sentinel */}
        <div ref={loadMoreRef} className="py-2" aria-hidden="true" />

        {/* Loading more indicator */}
        {isFetchingNextPage && (
          <div className="text-center py-4 text-sm text-gray-500">
            Loading more videos…
          </div>
        )}

        {/* End of list */}
        {!hasNextPage && videos.length > 0 && (
          <p className="text-center text-sm text-gray-400 py-4">
            All {videos.length} video{videos.length === 1 ? "" : "s"} loaded.
          </p>
        )}
      </section>
    </div>
  );
}
