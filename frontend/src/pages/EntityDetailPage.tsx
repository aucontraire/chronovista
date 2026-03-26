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

import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { ENTITY_TYPE_LABELS, ENTITY_TYPE_COLORS } from "../constants/entityTypes";
import { useEntityVideos, useDeleteManualAssociation, useScanEntity } from "../hooks/useEntityMentions";
import { apiFetch } from "../api/config";
import type { EntityDetail, EntityAliasSummary } from "../api/entityMentions";
import { createEntityAlias } from "../api/entityMentions";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { PhoneticVariantsSection } from "../components/corrections/PhoneticVariantsSection";
import { ExclusionPatternsSection } from "../components/corrections/ExclusionPatternsSection";

/** Default page title to restore on unmount */
const DEFAULT_PAGE_TITLE = "Chronovista";

// ---------------------------------------------------------------------------
// Entity detail type (fetched from the named-entities endpoint)
// ---------------------------------------------------------------------------

/** Re-export alias for clarity within this module. */
type NamedEntityDetail = EntityDetail;

interface NamedEntityDetailResponse {
  data: NamedEntityDetail;
}

// ---------------------------------------------------------------------------
// Helper functions
// ---------------------------------------------------------------------------

function getTypeLabel(entityType: string): string {
  return ENTITY_TYPE_LABELS[entityType] ?? entityType;
}

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

/** Human-readable label for each alias_type value. */
const ALIAS_TYPE_LABELS: Record<string, string> = {
  name_variant: "Name variant",
  abbreviation: "Abbreviation",
  nickname: "Nickname",
  translated_name: "Translation",
  former_name: "Former name",
};

function getAliasTypeLabel(aliasType: string): string {
  return ALIAS_TYPE_LABELS[aliasType] ?? aliasType;
}

/** Badge colour class for each alias type. */
const ALIAS_TYPE_COLORS: Record<string, string> = {
  name_variant: "bg-slate-100 text-slate-600 border-slate-200",
  abbreviation: "bg-blue-50 text-blue-600 border-blue-200",
  nickname: "bg-violet-50 text-violet-600 border-violet-200",
  translated_name: "bg-teal-50 text-teal-600 border-teal-200",
  former_name: "bg-amber-50 text-amber-600 border-amber-200",
};

function getAliasTypeBadgeClass(aliasType: string): string {
  return ALIAS_TYPE_COLORS[aliasType] ?? "bg-slate-100 text-slate-600 border-slate-200";
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
// UnlinkConfirmation (inline, entity detail page)
// ---------------------------------------------------------------------------

interface UnlinkConfirmationProps {
  /** Unique id used for data-testid attributes */
  id: string;
  /** Whether the delete mutation is in progress */
  isPending: boolean;
  /** Called when the user confirms the removal */
  onConfirm: () => void;
  /** Called when the user cancels or presses Escape */
  onCancel: () => void;
}

/**
 * Inline horizontal confirmation row for removing a manual entity–video
 * association from the entity detail page video list.
 *
 * Follows the RevertConfirmation pattern:
 * - Confirm button auto-focuses on mount (WCAG 2.4.3)
 * - Escape key cancels
 * - Amber colour scheme
 * - Message text satisfies FR-027
 */
function UnlinkConfirmation({
  id,
  isPending,
  onConfirm,
  onCancel,
}: UnlinkConfirmationProps) {
  const confirmButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    confirmButtonRef.current?.focus();
  }, []);

  const handleKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    event.stopPropagation();
    if (event.key === "Escape") {
      onCancel();
    }
  };

  return (
    <div
      className="mt-2 flex flex-wrap items-start gap-2 bg-amber-50 border border-amber-200 rounded-md px-3 py-2"
      onKeyDown={handleKeyDown}
    >
      <svg
        className="w-4 h-4 flex-shrink-0 text-amber-600 mt-0.5"
        fill="currentColor"
        viewBox="0 0 24 24"
        aria-hidden="true"
      >
        <path
          fillRule="evenodd"
          d="M9.401 3.003c1.155-2 4.043-2 5.197 0l7.355 12.748c1.154 2-.29 4.5-2.599 4.5H4.645c-2.309 0-3.752-2.5-2.598-4.5L9.4 3.003ZM12 8.25a.75.75 0 0 1 .75.75v3.75a.75.75 0 0 1-1.5 0V9a.75.75 0 0 1 .75-.75Zm0 8.25a.75.75 0 1 0 0-1.5.75.75 0 0 0 0 1.5Z"
          clipRule="evenodd"
        />
      </svg>

      <span className="text-xs text-amber-900 flex-1">
        Only the manual association will be removed. Transcript-derived mentions
        will remain unaffected.
      </span>

      <div className="flex items-center gap-2">
        <button
          ref={confirmButtonRef}
          type="button"
          data-testid={`unlink-confirm-${id}`}
          onClick={onConfirm}
          disabled={isPending}
          aria-busy={isPending ? "true" : undefined}
          aria-label="Confirm removal of manual association"
          className="
            min-h-[44px] min-w-[44px]
            px-3 py-1
            text-sm font-medium text-white
            bg-amber-600 hover:bg-amber-700 disabled:bg-amber-400
            rounded-md
            focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-1
            transition-colors
          "
        >
          {isPending ? "Removing..." : "Remove"}
        </button>

        <button
          type="button"
          data-testid={`unlink-cancel-${id}`}
          onClick={onCancel}
          aria-label="Cancel removal"
          className="
            min-h-[44px] min-w-[44px]
            px-3 py-1
            text-sm font-medium text-slate-700
            bg-white hover:bg-slate-50
            border border-slate-300
            rounded-md
            focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-1
            transition-colors
          "
        >
          Cancel
        </button>
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
  first_mention_time: number | null;
  /** Segment id of the first mention — used for the ?seg= deep link */
  first_segment_id: number;
  /** Detection method categories present, e.g. ["transcript", "manual"]. */
  sources: string[];
  /** Whether a manual association exists for this entity on this video. */
  has_manual: boolean;
  /** Entity ID from route params — needed for the unlink mutation. */
  entityId: string;
  /** Whether this card's unlink confirmation is currently visible. */
  isUnlinking: boolean;
  /** Called when the unlink button is clicked. */
  onUnlinkClick: () => void;
  /** Called when the unlink confirmation is cancelled. */
  onUnlinkCancel: () => void;
  /** Called when the unlink is confirmed. */
  onUnlinkConfirm: () => void;
  /** Whether the delete mutation is pending for this card. */
  isDeletePending: boolean;
}

function EntityVideoCard({
  video_id,
  video_title,
  channel_name,
  mention_count,
  first_mention_time,
  first_segment_id,
  sources,
  has_manual,
  isUnlinking,
  onUnlinkClick,
  onUnlinkCancel,
  onUnlinkConfirm,
  isDeletePending,
}: EntityVideoCardProps) {
  const isManualOnly = mention_count === 0 && has_manual;
  const hasTranscript = sources.includes("transcript") && mention_count > 0;

  const to = isManualOnly || first_mention_time == null
    ? `/videos/${video_id}`
    : first_segment_id > 0
      ? `/videos/${video_id}?seg=${first_segment_id}&t=${Math.floor(first_mention_time)}`
      : `/videos/${video_id}?t=${Math.floor(first_mention_time)}`;

  const ariaLabel = isManualOnly
    ? `${video_title} — Manually linked`
    : `${video_title} — ${mention_count} mention${mention_count === 1 ? "" : "s"}${first_mention_time != null ? `, first at ${formatTimestamp(first_mention_time)}` : ""}`;

  return (
    <div>
      <div className="relative">
        <Link
          to={to}
          className="block bg-white rounded-xl shadow-sm border border-gray-100 p-4 hover:shadow-md hover:border-gray-200 transition-all focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2"
          aria-label={ariaLabel}
        >
          <h4 className="text-base font-semibold text-gray-900 mb-1 line-clamp-2">
            {video_title}
          </h4>
          <p className="text-sm text-gray-500 mb-2">{channel_name}</p>
          {/* Source badges */}
          <div className="flex items-center gap-2 mb-2">
            {hasTranscript && (
              <span
                className="inline-flex items-center px-2 py-0.5 text-xs font-medium rounded bg-indigo-100 text-indigo-700 border border-indigo-200"
                data-testid="transcript-badge"
              >
                TRANSCRIPT &times;{mention_count}
              </span>
            )}
            {has_manual && (
              <span
                className="inline-flex items-center px-2 py-0.5 text-xs font-medium rounded bg-emerald-100 text-emerald-700 border border-emerald-200"
                data-testid="manual-badge"
              >
                MANUAL
              </span>
            )}
          </div>
          <div className="flex items-center gap-4 text-xs text-gray-500">
            {isManualOnly ? (
              <span>Manually linked</span>
            ) : (
              <>
                <span>
                  {mention_count} mention{mention_count === 1 ? "" : "s"}
                </span>
                {first_mention_time != null && (
                  <span>First at {formatTimestamp(first_mention_time)}</span>
                )}
              </>
            )}
          </div>
        </Link>

        {/* T045: Unlink button — only shown when has_manual is true */}
        {has_manual && (
          <button
            type="button"
            data-testid={`unlink-button-${video_id}`}
            aria-label={`Remove manual association for ${video_title}`}
            onClick={(e) => {
              e.stopPropagation();
              e.preventDefault();
              onUnlinkClick();
            }}
            className="
              absolute top-3 right-3
              inline-flex items-center justify-center
              w-7 h-7
              text-slate-400 hover:text-amber-600
              bg-white hover:bg-amber-50
              border border-slate-200 hover:border-amber-300
              rounded-full
              focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-500 focus-visible:ring-offset-1
              transition-colors
            "
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 20 20"
              fill="currentColor"
              className="w-4 h-4"
              aria-hidden="true"
            >
              <path d="M6.28 5.22a.75.75 0 0 0-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 1 0 1.06 1.06L10 11.06l3.72 3.72a.75.75 0 1 0 1.06-1.06L11.06 10l3.72-3.72a.75.75 0 0 0-1.06-1.06L10 8.94 6.28 5.22Z" />
            </svg>
          </button>
        )}
      </div>

      {/* Inline unlink confirmation — shown below the card */}
      {isUnlinking && (
        <UnlinkConfirmation
          id={video_id}
          isPending={isDeletePending}
          onConfirm={onUnlinkConfirm}
          onCancel={onUnlinkCancel}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Alias row
// ---------------------------------------------------------------------------

function AliasRow({ alias }: { alias: EntityAliasSummary }) {
  return (
    <div className="flex items-center justify-between py-2 px-3 rounded-lg hover:bg-slate-50 transition-colors">
      <span className="text-sm font-medium text-gray-800">{alias.alias_name}</span>
      <div className="flex items-center gap-3">
        <span
          className={`inline-flex items-center px-2 py-0.5 text-xs font-medium rounded border ${getAliasTypeBadgeClass(alias.alias_type)}`}
        >
          {getAliasTypeLabel(alias.alias_type)}
        </span>
        <span className="text-xs text-gray-400 tabular-nums w-16 text-right">
          {alias.occurrence_count.toLocaleString()}{" "}
          {alias.occurrence_count === 1 ? "occurrence" : "occurrences"}
        </span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Add alias form
// ---------------------------------------------------------------------------

/** Valid alias type values accepted by the backend. */
const ALIAS_TYPE_OPTIONS: { value: string; label: string }[] = [
  { value: "name_variant", label: "Name variant" },
  { value: "abbreviation", label: "Abbreviation" },
  { value: "nickname", label: "Nickname" },
  { value: "translated_name", label: "Translation" },
  { value: "former_name", label: "Former name" },
];

interface AddAliasFormProps {
  entityId: string;
  /** Called after a successful creation so the parent can refetch. */
  onCreated: () => void;
}

/**
 * Compact single-row form for adding a new alias to a named entity.
 * Shows a brief green confirmation on success, and inline red error on failure.
 */
function AddAliasForm({ entityId, onCreated }: AddAliasFormProps) {
  const [aliasName, setAliasName] = useState("");
  const [aliasType, setAliasType] = useState("name_variant");
  const [isPending, setIsPending] = useState(false);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const successTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Clear the success fade-out timer on unmount to avoid memory leaks.
  useEffect(() => {
    return () => {
      if (successTimerRef.current !== null) {
        clearTimeout(successTimerRef.current);
      }
    };
  }, []);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const trimmed = aliasName.trim();
    if (!trimmed) return;

    setIsPending(true);
    setSuccessMsg(null);
    setErrorMsg(null);

    try {
      await createEntityAlias(entityId, trimmed, aliasType);
      setAliasName("");
      setSuccessMsg(`"${trimmed}" added successfully.`);
      onCreated();

      // Auto-clear success message after 3 seconds.
      successTimerRef.current = setTimeout(() => {
        setSuccessMsg(null);
      }, 3000);

      // Return focus to the input so the user can add another alias.
      inputRef.current?.focus();
    } catch (err: unknown) {
      const status = (err as { status?: number } | null)?.status;
      if (status === 409) {
        setErrorMsg("This alias already exists for the entity.");
      } else if (status === 404) {
        setErrorMsg("Entity not found. Please refresh the page.");
      } else {
        setErrorMsg("Failed to add alias. Please try again.");
      }
    } finally {
      setIsPending(false);
    }
  }

  return (
    <div className="pt-3 mt-3 border-t border-slate-100">
      <form
        onSubmit={handleSubmit}
        className="flex items-center gap-2"
        aria-label="Add new alias"
      >
        <input
          ref={inputRef}
          type="text"
          value={aliasName}
          onChange={(e) => {
            setAliasName(e.target.value);
            // Clear error when the user starts typing again.
            if (errorMsg) setErrorMsg(null);
          }}
          placeholder="Add new alias…"
          className="flex-1 min-w-0 rounded-md border border-slate-300 px-3 py-1.5 text-sm text-gray-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
          disabled={isPending}
          aria-label="Alias name"
          maxLength={200}
        />
        <select
          value={aliasType}
          onChange={(e) => setAliasType(e.target.value)}
          className="rounded-md border border-slate-300 px-2 py-1.5 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
          disabled={isPending}
          aria-label="Alias type"
        >
          {ALIAS_TYPE_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        <button
          type="submit"
          disabled={isPending || !aliasName.trim()}
          className="inline-flex items-center px-3 py-1.5 text-sm font-medium text-white bg-indigo-600 rounded-md hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {isPending ? "Adding…" : "Add"}
        </button>
      </form>

      {/* Inline feedback */}
      {successMsg && (
        <p className="mt-1.5 text-xs text-green-600" role="status" aria-live="polite">
          {successMsg}
        </p>
      )}
      {errorMsg && (
        <p className="mt-1.5 text-xs text-red-600" role="alert">
          {errorMsg}
        </p>
      )}
    </div>
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
  const queryClient = useQueryClient();

  // T045: Track which video's unlink confirmation is currently visible.
  const [unlinkingVideoId, setUnlinkingVideoId] = useState<string | null>(null);
  const deleteMutation = useDeleteManualAssociation();

  // Auto-hide confirmation after a successful deletion.
  useEffect(() => {
    if (deleteMutation.isSuccess) {
      setUnlinkingVideoId(null);
    }
  }, [deleteMutation.isSuccess]);

  // T008: Scan for mentions button state.
  type ScanMessageType = "success" | "error" | null;
  const [scanMessage, setScanMessage] = useState<string | null>(null);
  const [scanMessageType, setScanMessageType] = useState<ScanMessageType>(null);
  const scanTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const scanMutation = useScanEntity();

  // Clear scan auto-dismiss timer on unmount.
  useEffect(() => {
    return () => {
      if (scanTimerRef.current !== null) {
        clearTimeout(scanTimerRef.current);
      }
    };
  }, []);

  function handleScanClick() {
    if (!entityId) return;
    setScanMessage(null);
    setScanMessageType(null);
    if (scanTimerRef.current !== null) {
      clearTimeout(scanTimerRef.current);
      scanTimerRef.current = null;
    }
    scanMutation.mutate(
      { entityId },
      {
        onSuccess: (data) => {
          const { mentions_found, unique_videos } = data.data;
          const msg =
            mentions_found === 0
              ? "No new mentions found."
              : `Found ${mentions_found.toLocaleString()} new mention${mentions_found === 1 ? "" : "s"} across ${unique_videos.toLocaleString()} video${unique_videos === 1 ? "" : "s"}.`;
          setScanMessage(msg);
          setScanMessageType("success");
          scanTimerRef.current = setTimeout(() => {
            setScanMessage(null);
            setScanMessageType(null);
          }, 3000);
        },
        onError: (err) => {
          const status = (err as { status?: number } | null)?.status;
          let msg = "Scan failed. Please try again.";
          if (status === 404) {
            msg = "Entity not found. Please refresh the page.";
          } else if (status === 503 || status === 500) {
            msg = "Scan service unavailable. Please try again later.";
          }
          setScanMessage(msg);
          setScanMessageType("error");
          // Error messages persist until the user retries — no auto-dismiss.
        },
      }
    );
  }

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

        {/* T008: Scan for mentions button + inline feedback */}
        <div className="mt-5 flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={handleScanClick}
            disabled={scanMutation.isPending}
            aria-busy={scanMutation.isPending ? "true" : undefined}
            title={scanMutation.isPending ? "A scan is already running" : undefined}
            className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 disabled:cursor-not-allowed rounded-md focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 transition-colors"
          >
            {scanMutation.isPending ? (
              <>
                <svg
                  className="w-4 h-4 animate-spin"
                  xmlns="http://www.w3.org/2000/svg"
                  fill="none"
                  viewBox="0 0 24 24"
                  aria-hidden="true"
                >
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                  />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                  />
                </svg>
                Scanning...
                <span className="sr-only">Scanning for mentions...</span>
              </>
            ) : (
              "Scan for Mentions"
            )}
          </button>

          {scanMessage !== null && scanMessageType === "success" && (
            <p
              role="status"
              aria-live="polite"
              className="text-sm text-green-700 bg-green-50 border border-green-200 rounded-md px-3 py-1.5"
            >
              {scanMessage}
            </p>
          )}
          {scanMessage !== null && scanMessageType === "error" && (
            <p
              role="alert"
              className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-md px-3 py-1.5"
            >
              {scanMessage}
            </p>
          )}
        </div>
      </article>

      {/* Aliases section */}
      <section aria-labelledby="entity-aliases-heading" className="mb-6">
        <h2
          id="entity-aliases-heading"
          className="text-lg font-semibold text-gray-900 mb-3"
        >
          Aliases
        </h2>
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
          {entity.aliases.length > 0 ? (
            <div className="divide-y divide-slate-100">
              {entity.aliases.map((alias) => (
                <AliasRow key={alias.alias_name} alias={alias} />
              ))}
            </div>
          ) : (
            <p className="text-sm text-gray-400 italic">No aliases registered.</p>
          )}
          {entityId && (
            <AddAliasForm
              entityId={entityId}
              onCreated={() => {
                void queryClient.invalidateQueries({
                  queryKey: ["entity-detail", entityId],
                });
              }}
            />
          )}
        </div>
      </section>

      {/* Exclusion Patterns section */}
      {entityId && (
        <ExclusionPatternsSection
          entityId={entityId}
          patterns={entity.exclusion_patterns ?? []}
        />
      )}

      {/* Suspected ASR Variants section */}
      {entityId && <PhoneticVariantsSection entityId={entityId} />}

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
                  first_mention_time={v.first_mention_time ?? firstMention?.start_time ?? null}
                  first_segment_id={firstMention?.segment_id ?? 0}
                  sources={v.sources ?? []}
                  has_manual={v.has_manual ?? false}
                  entityId={entityId ?? ""}
                  isUnlinking={unlinkingVideoId === v.video_id}
                  isDeletePending={
                    deleteMutation.isPending && unlinkingVideoId === v.video_id
                  }
                  onUnlinkClick={() => setUnlinkingVideoId(v.video_id)}
                  onUnlinkCancel={() => setUnlinkingVideoId(null)}
                  onUnlinkConfirm={() => {
                    if (entityId) {
                      deleteMutation.mutate({
                        videoId: v.video_id,
                        entityId,
                      });
                    }
                  }}
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
