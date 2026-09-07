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

import React, { useEffect, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { CooccurringPanel } from "../components/entity/CooccurringPanel";
import { EntityEnrichmentSection } from "../components/entity/EntityEnrichmentSection";
import { EntityTagSection } from "../components/entity/EntityTagSection";
import { EntityTypeBadge } from "../components/EntityTypeBadge";
import { AssociationBreakdown } from "../components/AssociationBreakdown";
import { ENTITY_TYPE_LABELS } from "../constants/entityTypes";
import {
  useEntityVideos,
  useDeleteManualAssociation,
  useScanEntity,
  useUpdateEntity,
} from "../hooks/useEntityMentions";
import { apiFetch } from "../api/config";
import type {
  EntityDetail,
  EntityAliasSummary,
  UpdateEntityRequest,
  UpdateEntityAliasRequest,
} from "../api/entityMentions";
import { createEntityAlias, updateEntityAlias, deleteEntityAlias } from "../api/entityMentions";
import { useUndoAliasDeletion } from "../hooks/useUndoAliasDeletion";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { PhoneticVariantsSection } from "../components/corrections/PhoneticVariantsSection";
import { ExclusionPatternsSection } from "../components/corrections/ExclusionPatternsSection";
import { foldName } from "../utils/foldName";

/** Default page title to restore on unmount */
const DEFAULT_PAGE_TITLE = "Chronovista";

/**
 * FR-005a: while a just-grounded entity's background-fetched Wikidata
 * properties are still populating, the detail query refetches a few times
 * over a short window so they appear without a manual reload. Bounded by
 * attempt count (via `query.state.dataUpdateCount`) so it can never poll
 * indefinitely — mirrors the scan-job polling pattern in useEntityMentions.ts.
 */
const ENRICH_POLL_MAX_ATTEMPTS = 5;
const ENRICH_POLL_INTERVAL_MS = 1500;

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

function PencilIcon({ className }: { className?: string }) {
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
        d="m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L6.832 19.82a4.5 4.5 0 0 1-1.897 1.13l-2.685.8.8-2.685a4.5 4.5 0 0 1 1.13-1.897L16.863 4.487Zm0 0L19.5 7.125"
      />
    </svg>
  );
}

function TrashIcon({ className }: { className?: string }) {
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
        d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0"
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
  /**
   * Context snippet (~150 chars) surrounding the description match.
   * Only present when "description" is in sources; null otherwise.
   */
  description_context: string | null;
  /**
   * Canonical name of the entity — used to highlight the entity text within
   * the description context snippet (FR-034).
   */
  entityName: string;
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

/**
 * Highlights all case-insensitive occurrences of `query` within `text` by
 * wrapping them in `<mark>` elements.  Returns an array of React nodes.
 */
function highlightEntityInContext(text: string, query: string): React.ReactNode[] {
  if (!query.trim()) return [text];
  const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const regex = new RegExp(`(${escaped})`, "gi");
  const parts = text.split(regex);
  return parts.map((part, i) =>
    regex.test(part) ? (
      <mark key={i} className="bg-yellow-100 font-bold not-italic">
        {part}
      </mark>
    ) : (
      part
    )
  );
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
  description_context,
  entityName,
  isUnlinking,
  onUnlinkClick,
  onUnlinkCancel,
  onUnlinkConfirm,
  isDeletePending,
}: EntityVideoCardProps) {
  const isManualOnly = mention_count === 0 && has_manual;
  const hasTranscript = sources.includes("transcript") && mention_count > 0;
  const hasTag = sources.includes("tag");
  const hasTitle = sources.includes("title");
  const hasDescription = sources.includes("description");

  // T026: tag-only videos (no transcript mention and no manual association)
  // link to the video page without segment/timestamp params since there is no
  // transcript timestamp to seek to.
  const isTagOnly = !sources.includes("transcript") && !has_manual;

  const to = isTagOnly || isManualOnly || first_mention_time == null
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
          {/* Source badges — quality hierarchy: TITLE → TRANSCRIPT → TAG → DESC → MANUAL */}
          <div className="flex flex-wrap items-center gap-2 mb-2">
            {/* T050: TITLE badge — amber, non-clickable (FR-011) */}
            {hasTitle && (
              <span
                className="inline-flex items-center px-2 py-0.5 text-xs font-medium rounded bg-amber-100 text-amber-700"
                data-testid="title-badge"
                title="Entity found in video title"
              >
                TITLE
              </span>
            )}
            {hasTranscript && (
              <span
                className="inline-flex items-center px-2 py-0.5 text-xs font-medium rounded bg-indigo-100 text-indigo-700 border border-indigo-200"
                data-testid="transcript-badge"
              >
                TRANSCRIPT &times;{mention_count}
              </span>
            )}
            {/* T025: TAG badge — teal pill shown when video is associated via tag */}
            {hasTag && (
              <span
                className="inline-flex items-center bg-teal-100 text-teal-700 rounded-full px-2 py-0.5 text-xs font-medium"
                data-testid="tag-badge"
              >
                TAG
              </span>
            )}
            {/* T051: DESC badge — slate, non-clickable (FR-012) */}
            {hasDescription && (
              <span
                className="inline-flex items-center px-2 py-0.5 text-xs font-medium rounded bg-slate-200 text-slate-700"
                data-testid="desc-badge"
                title="Entity found in video description"
              >
                DESC
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
          {/* T052: Description context snippet — italic, truncated, entity highlighted */}
          {hasDescription && description_context && (
            <p
              className="text-xs text-slate-500 italic mb-2"
              data-testid="description-context"
            >
              {highlightEntityInContext(
                description_context.length > 150
                  ? description_context.slice(0, 150) + "..."
                  : description_context,
                entityName
              )}
            </p>
          )}
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

interface AliasRowProps {
  alias: EntityAliasSummary;
  entityId: string;
  /**
   * True when this alias is the entity's own name (its case/accent-folded name
   * equals the entity's folded canonical name — the "self-alias"). Derived at
   * render time (Feature 075 / #301); it drives the Primary badge and the
   * reinforced delete confirmation. Deleting it stays allowed and undoable.
   */
  isPrimary: boolean;
  /**
   * Called after a mutation that changes what text matches — the
   * case-sensitivity flag, or a rename — so the caller can rebuild mentions.
   */
  onMatchingChanged: () => void;
  /**
   * Called after a mutation that doesn't change what text matches or which
   * videos are associated (an edit that only changed the alias type) — just
   * refreshes the list.
   */
  onAliasListChanged: () => void;
  /**
   * Called after a successful delete with the info needed to offer Undo.
   * The backend also retracts the alias's auto-detected mentions, which
   * changes entity↔video associations — so the caller must refresh the same
   * query families a mention-changing scan does, not just the alias list.
   * This row unmounts as soon as that refresh resolves (the alias leaves
   * `entity.aliases`), so the Undo affordance itself must live at the page
   * level, not here.
   */
  onAliasDeleted: (deleted: { operationId: string; aliasName: string }) => void;
}

function AliasRow({
  alias,
  entityId,
  isPrimary,
  onMatchingChanged,
  onAliasListChanged,
  onAliasDeleted,
}: AliasRowProps) {
  const [caseSensitive, setCaseSensitive] = useState(alias.case_sensitive);
  const [isSavingCase, setIsSavingCase] = useState(false);
  const [caseError, setCaseError] = useState<string | null>(null);
  const toggleId = `alias-case-${alias.id}`;

  // ---------------------------------------------------------------------------
  // Edit (name + type) — Feature #289
  // ---------------------------------------------------------------------------

  const [isEditing, setIsEditing] = useState(false);
  const [nameInput, setNameInput] = useState(alias.alias_name);
  const [typeInput, setTypeInput] = useState(alias.alias_type);
  const [editError, setEditError] = useState<string | null>(null);
  const [isSavingEdit, setIsSavingEdit] = useState(false);
  const editButtonRef = useRef<HTMLButtonElement>(null);
  const nameInputRef = useRef<HTMLInputElement>(null);

  // ---------------------------------------------------------------------------
  // Delete — Feature #289
  // ---------------------------------------------------------------------------

  const [isConfirmingDelete, setIsConfirmingDelete] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const deleteButtonRef = useRef<HTMLButtonElement>(null);
  const deleteConfirmButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (isEditing) {
      nameInputRef.current?.focus();
    }
  }, [isEditing]);

  useEffect(() => {
    if (isConfirmingDelete) {
      deleteConfirmButtonRef.current?.focus();
    }
  }, [isConfirmingDelete]);

  async function handleToggle(next: boolean) {
    // Optimistic, because the switch is the feedback — a checkbox that lags
    // behind the click reads as broken.
    setCaseSensitive(next);
    setIsSavingCase(true);
    setCaseError(null);
    try {
      await updateEntityAlias(entityId, alias.id, { case_sensitive: next });
      onMatchingChanged();
    } catch {
      setCaseSensitive(!next);
      setCaseError("Could not save. Try again.");
    } finally {
      setIsSavingCase(false);
    }
  }

  function enterEditMode() {
    setNameInput(alias.alias_name);
    setTypeInput(alias.alias_type);
    setEditError(null);
    setIsEditing(true);
  }

  function exitEditMode() {
    setIsEditing(false);
    // Return focus to the trigger for keyboard users (WCAG 2.4.3).
    requestAnimationFrame(() => editButtonRef.current?.focus());
  }

  function handleEditCancel() {
    setEditError(null);
    exitEditMode();
  }

  function handleEditKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    event.stopPropagation();
    if (event.key === "Escape") {
      handleEditCancel();
    }
  }

  const trimmedNameInput = nameInput.trim();
  const editHasChanges =
    trimmedNameInput !== alias.alias_name || typeInput !== alias.alias_type;

  async function handleEditSave() {
    // Belt-and-suspenders: the Save button is already disabled for both of
    // these, so this only guards a race (e.g. a stray Enter keypress).
    if (isSavingEdit || trimmedNameInput === "" || !editHasChanges) return;

    const nameChanged = trimmedNameInput !== alias.alias_name;
    const patch: UpdateEntityAliasRequest = {};
    if (nameChanged) patch.alias_name = trimmedNameInput;
    if (typeInput !== alias.alias_type) patch.alias_type = typeInput;

    setIsSavingEdit(true);
    setEditError(null);
    try {
      await updateEntityAlias(entityId, alias.id, patch);
      exitEditMode();
      // A rename changes what text matches, so it needs the same rescan the
      // case-sensitivity flag does. A type-only change doesn't affect
      // matching — just refresh the list.
      if (nameChanged) {
        onMatchingChanged();
      } else {
        onAliasListChanged();
      }
    } catch (err: unknown) {
      const status = (err as { status?: number } | null)?.status;
      if (status === 409) {
        setEditError(
          "This name is already covered by an existing alias — accents and case " +
            "are ignored when matching, so this spelling counts as the same."
        );
      } else if (status === 404) {
        setEditError("Alias not found. Please refresh the page.");
      } else {
        setEditError("Failed to save changes. Please try again.");
      }
      // Editor stays open and the user's input is preserved.
    } finally {
      setIsSavingEdit(false);
    }
  }

  function handleDeleteCancel() {
    setIsConfirmingDelete(false);
    setDeleteError(null);
    requestAnimationFrame(() => deleteButtonRef.current?.focus());
  }

  function handleDeleteKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    event.stopPropagation();
    if (event.key === "Escape") {
      handleDeleteCancel();
    }
  }

  async function handleDeleteConfirm() {
    if (isDeleting) return;
    setIsDeleting(true);
    setDeleteError(null);
    try {
      const deleted = await deleteEntityAlias(entityId, alias.id);
      setIsConfirmingDelete(false);
      // The backend also retracted this alias's auto-detected mentions —
      // an association-level change, not just a list refresh — so the
      // caller must invalidate the same query families a mention-changing
      // scan does (see refreshEntityAssociations). It must NOT trigger an
      // actual rescan: the server already removed the mentions and
      // recomputed counts, so re-scanning would just be redundant work.
      // Also hands up `operation_id` so the page can offer Undo (#298) —
      // this row is about to unmount once that refresh resolves.
      onAliasDeleted({
        operationId: deleted.operation_id,
        aliasName: deleted.alias_name,
      });
    } catch (err: unknown) {
      const status = (err as { status?: number } | null)?.status;
      setDeleteError(
        status === 404
          ? "Alias not found. Please refresh the page."
          : "Failed to delete alias. Please try again."
      );
    } finally {
      setIsDeleting(false);
    }
  }

  if (isEditing) {
    return (
      <div
        className="py-2 px-3 space-y-2"
        onKeyDown={handleEditKeyDown}
        role="group"
        aria-label={`Edit alias "${alias.alias_name}"`}
      >
        <div className="flex items-center gap-2">
          <input
            ref={nameInputRef}
            type="text"
            value={nameInput}
            onChange={(e) => {
              setNameInput(e.target.value);
              if (editError) setEditError(null);
            }}
            disabled={isSavingEdit}
            aria-label={`Alias name for "${alias.alias_name}"`}
            maxLength={200}
            className="flex-1 min-w-0 rounded-md border border-slate-300 px-3 py-1.5 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 disabled:bg-slate-100 disabled:text-slate-500"
          />
          <select
            value={typeInput}
            onChange={(e) => setTypeInput(e.target.value)}
            disabled={isSavingEdit}
            aria-label={`Alias type for "${alias.alias_name}"`}
            className="rounded-md border border-slate-300 px-2 py-1.5 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 disabled:bg-slate-100 disabled:text-slate-500"
          >
            {ALIAS_TYPE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>

        {isSavingEdit && (
          <p role="status" aria-live="polite" className="text-xs text-slate-500">
            Saving…
          </p>
        )}
        {editError !== null && (
          <p role="alert" className="text-xs text-red-600">
            {editError}
          </p>
        )}

        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => void handleEditSave()}
            disabled={isSavingEdit || trimmedNameInput === "" || !editHasChanges}
            aria-busy={isSavingEdit ? "true" : undefined}
            className="inline-flex items-center px-3 py-1.5 text-sm font-medium text-white bg-indigo-600 rounded-md hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {isSavingEdit ? "Saving…" : "Save"}
          </button>
          <button
            type="button"
            onClick={handleEditCancel}
            disabled={isSavingEdit}
            className="inline-flex items-center px-3 py-1.5 text-sm font-medium text-slate-700 bg-white border border-slate-300 rounded-md hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            Cancel
          </button>
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between py-2 px-3 rounded-lg hover:bg-slate-50 transition-colors">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-gray-800">{alias.alias_name}</span>
          {isPrimary && (
            <span
              className="inline-flex items-center px-2 py-0.5 text-xs font-semibold rounded border border-indigo-300 bg-indigo-50 text-indigo-700"
              title="This alias is the entity's own name (its canonical name)."
            >
              Primary
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          <label
            htmlFor={toggleId}
            className="flex items-center gap-1.5 text-xs text-slate-600 cursor-pointer"
            title={
              `Match "${alias.alias_name}" only with this exact capitalisation. ` +
              "Use when the alias is also an ordinary word and casing tells them " +
              "apart — check the mentions first, since automatic transcripts " +
              "often drop capitals from names."
            }
          >
            <input
              id={toggleId}
              type="checkbox"
              checked={caseSensitive}
              disabled={isSavingCase}
              onChange={(e) => void handleToggle(e.target.checked)}
              className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500 disabled:opacity-50"
            />
            Match case
          </label>
          {caseError !== null && (
            <span role="alert" className="text-xs text-red-600">
              {caseError}
            </span>
          )}
          <span
            className={`inline-flex items-center px-2 py-0.5 text-xs font-medium rounded border ${getAliasTypeBadgeClass(alias.alias_type)}`}
          >
            {getAliasTypeLabel(alias.alias_type)}
          </span>
          <span className="text-xs text-gray-400 tabular-nums w-16 text-right">
            {alias.occurrence_count.toLocaleString()}{" "}
            {alias.occurrence_count === 1 ? "occurrence" : "occurrences"}
          </span>
          <button
            ref={editButtonRef}
            type="button"
            onClick={enterEditMode}
            aria-label={`Edit alias "${alias.alias_name}"`}
            className="inline-flex items-center justify-center w-7 h-7 rounded-full text-slate-400 hover:text-slate-600 hover:bg-slate-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-1 transition-colors"
          >
            <PencilIcon className="w-3.5 h-3.5" />
          </button>
          <button
            ref={deleteButtonRef}
            type="button"
            onClick={() => setIsConfirmingDelete(true)}
            aria-label={`Delete alias "${alias.alias_name}"`}
            className="inline-flex items-center justify-center w-7 h-7 rounded-full text-slate-400 hover:text-red-600 hover:bg-red-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-400 focus-visible:ring-offset-1 transition-colors"
          >
            <TrashIcon className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {isConfirmingDelete && (
        <div
          className={
            isPrimary
              ? "mt-1 mb-2 flex flex-wrap items-start gap-2 bg-red-50 border border-red-300 rounded-md px-3 py-2"
              : "mt-1 mb-2 flex flex-wrap items-start gap-2 bg-amber-50 border border-amber-200 rounded-md px-3 py-2"
          }
          onKeyDown={handleDeleteKeyDown}
        >
          <WarningIcon
            className={`w-4 h-4 flex-shrink-0 mt-0.5 ${isPrimary ? "text-red-600" : "text-amber-600"}`}
          />
          <span className={`text-xs flex-1 ${isPrimary ? "text-red-900" : "text-amber-900"}`}>
            {isPrimary ? (
              <>
                <strong className="font-semibold">
                  {"This alias is the entity's own name."}
                </strong>{" "}
                {"Deleting it removes the alias, but the mentions it matched stay, because they also match the entity's canonical name. You can undo this."}
              </>
            ) : (
              `Deleting this alias will remove about ${alias.occurrence_count.toLocaleString()} auto-detected ${alias.occurrence_count === 1 ? "mention" : "mentions"} it produced. Mentions you added manually, or that came from a correction, will be kept.`
            )}
          </span>
          {deleteError !== null && (
            <span role="alert" className="text-xs text-red-700 w-full">
              {deleteError}
            </span>
          )}
          <div className="flex items-center gap-2">
            <button
              ref={deleteConfirmButtonRef}
              type="button"
              onClick={() => void handleDeleteConfirm()}
              disabled={isDeleting}
              aria-busy={isDeleting ? "true" : undefined}
              aria-label={`Confirm deletion of alias "${alias.alias_name}"`}
              className={
                isPrimary
                  ? "min-h-[36px] px-3 py-1 text-sm font-medium text-white bg-red-600 hover:bg-red-700 disabled:bg-red-400 rounded-md focus:outline-none focus-visible:ring-2 focus-visible:ring-red-500 focus-visible:ring-offset-1 transition-colors"
                  : "min-h-[36px] px-3 py-1 text-sm font-medium text-white bg-amber-600 hover:bg-amber-700 disabled:bg-amber-400 rounded-md focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-500 focus-visible:ring-offset-1 transition-colors"
              }
            >
              {isDeleting ? "Deleting…" : "Delete"}
            </button>
            <button
              type="button"
              onClick={handleDeleteCancel}
              disabled={isDeleting}
              aria-label={`Cancel deletion of alias "${alias.alias_name}"`}
              className="min-h-[36px] px-3 py-1 text-sm font-medium text-slate-700 bg-white hover:bg-slate-50 border border-slate-300 rounded-md focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-500 focus-visible:ring-offset-1 transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
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
        setErrorMsg(
          "This name is already covered by an existing alias — accents and case " +
            "are ignored when matching, so this spelling counts as the same."
        );
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
// Entity name & description editor (Feature 057)
// ---------------------------------------------------------------------------

/** Maximum length for an entity's canonical_name, matching backend validation. */
const ENTITY_NAME_MAX_LENGTH = 500;

interface EntityNameEditorProps {
  entityId: string;
  canonicalName: string;
  description: string | null;
  entityType: string;
  /** Rendered next to the name in read mode (the existing entity-type badge). */
  typeBadge: React.ReactNode;
}

/**
 * Inline editor for an entity's display name and description (Feature 057,
 * FR-001/FR-002). Editing here never touches the tag(s) the entity is linked
 * to (FR-003).
 *
 * Mirrors the `AddAliasForm` / `TranscriptSegments` `isEditing` toggle
 * pattern: a read view with a keyboard-operable Edit button, and an edit
 * view with labeled Name/Description inputs and Save/Cancel.
 *
 * Accessibility (FR-021/FR-022/FR-023):
 * - The edit trigger is a native `<button>`, so Enter/Space activate it
 *   without any custom key handling.
 * - Escape (while editing) cancels and restores the read view.
 * - Name/description inputs are labeled.
 * - A `role="status" aria-live="polite"` region announces "Saving…" / a
 *   success message; errors are announced via `role="alert"`.
 * - Save is disabled (and shows a pending label) while the mutation is in
 *   flight, preventing duplicate submissions.
 * - On a 400/404/409 error the editor stays open and the user's edited
 *   values are left untouched, so nothing is lost.
 */
function EntityNameEditor({
  entityId,
  canonicalName,
  description,
  entityType,
  typeBadge,
}: EntityNameEditorProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [nameInput, setNameInput] = useState(canonicalName);
  const [descriptionInput, setDescriptionInput] = useState(description ?? "");
  const [typeInput, setTypeInput] = useState(entityType);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const nameInputRef = useRef<HTMLInputElement>(null);
  const editButtonRef = useRef<HTMLButtonElement>(null);
  const successTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const updateMutation = useUpdateEntity();

  useEffect(() => {
    return () => {
      if (successTimerRef.current !== null) {
        clearTimeout(successTimerRef.current);
      }
    };
  }, []);

  useEffect(() => {
    if (isEditing) {
      nameInputRef.current?.focus();
    }
  }, [isEditing]);

  function enterEditMode() {
    setNameInput(canonicalName);
    setDescriptionInput(description ?? "");
    setTypeInput(entityType);
    setErrorMsg(null);
    setSuccessMsg(null);
    setIsEditing(true);
  }

  function exitEditMode() {
    setIsEditing(false);
    // Return focus to the trigger for keyboard users (WCAG 2.4.3).
    requestAnimationFrame(() => editButtonRef.current?.focus());
  }

  function handleCancel() {
    setErrorMsg(null);
    setSuccessMsg(null);
    exitEditMode();
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    event.stopPropagation();
    if (event.key === "Escape") {
      handleCancel();
    }
  }

  function handleSave() {
    if (updateMutation.isPending) return; // FR-023: no double-submit

    const trimmedName = nameInput.trim();
    if (trimmedName.length === 0) {
      setErrorMsg("Name cannot be empty.");
      return;
    }
    if (trimmedName.length > ENTITY_NAME_MAX_LENGTH) {
      setErrorMsg(`Name must be ${ENTITY_NAME_MAX_LENGTH} characters or fewer.`);
      return;
    }

    const payload: UpdateEntityRequest = {};
    if (trimmedName !== canonicalName) {
      payload.canonical_name = trimmedName;
    }
    if (descriptionInput !== (description ?? "")) {
      payload.description = descriptionInput;
    }
    if (typeInput !== entityType) {
      payload.entity_type = typeInput;
    }

    if (Object.keys(payload).length === 0) {
      // Edge case: no-op save — nothing changed, just return to read view.
      exitEditMode();
      return;
    }

    setErrorMsg(null);
    setSuccessMsg(null);

    updateMutation.mutate(
      { entityId, data: payload },
      {
        onSuccess: () => {
          setSuccessMsg("Saved.");
          exitEditMode();
          successTimerRef.current = setTimeout(() => setSuccessMsg(null), 3000);
        },
        onError: (err) => {
          const status = (err as { status?: number } | null)?.status;
          if (status === 409) {
            setErrorMsg(
              "Another entity of that type already has this name. Choose a different name or type."
            );
          } else if (status === 400) {
            setErrorMsg(err.message || "Invalid name or description.");
          } else if (status === 404) {
            setErrorMsg("Entity not found. Please refresh the page.");
          } else {
            setErrorMsg("Failed to save changes. Please try again.");
          }
          // FR-022: editor stays open (isEditing untouched) and the user's
          // input is preserved (nameInput/descriptionInput untouched).
        },
      }
    );
  }

  if (!isEditing) {
    return (
      <>
        <div className="flex flex-wrap items-start gap-3 mb-4">
          <h1 className="text-2xl lg:text-3xl font-bold text-gray-900">
            {canonicalName}
          </h1>
          {typeBadge}
          <button
            ref={editButtonRef}
            type="button"
            onClick={enterEditMode}
            aria-label={`Edit name and description for ${canonicalName}`}
            className="
              inline-flex items-center gap-1
              min-h-[32px]
              px-2.5 py-1
              text-xs font-medium text-slate-600
              bg-slate-100 hover:bg-slate-200
              border border-slate-200
              rounded-full
              focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-1
              transition-colors
            "
          >
            <PencilIcon className="w-3.5 h-3.5" />
            Edit
          </button>
        </div>

        {description ? (
          <p className="text-gray-600 mb-4 max-w-3xl">{description}</p>
        ) : (
          <p className="text-gray-400 italic mb-4">No description available.</p>
        )}

        {successMsg && (
          <p
            role="status"
            aria-live="polite"
            className="text-sm text-green-700 bg-green-50 border border-green-200 rounded-md px-3 py-1.5 mb-4 inline-block"
          >
            {successMsg}
          </p>
        )}
      </>
    );
  }

  return (
    <div
      className="mb-4 p-4 bg-slate-50 border border-slate-200 rounded-lg space-y-3"
      onKeyDown={handleKeyDown}
    >
      <div>
        <label
          htmlFor="entity-name-input"
          className="block text-sm font-medium text-gray-700 mb-1"
        >
          Name
        </label>
        <input
          ref={nameInputRef}
          id="entity-name-input"
          type="text"
          value={nameInput}
          onChange={(e) => {
            setNameInput(e.target.value);
            if (errorMsg) setErrorMsg(null);
          }}
          disabled={updateMutation.isPending}
          maxLength={ENTITY_NAME_MAX_LENGTH}
          aria-invalid={errorMsg !== null ? "true" : "false"}
          aria-describedby={errorMsg !== null ? "entity-name-error" : undefined}
          className="
            w-full px-3 py-2
            text-sm text-gray-900
            border border-slate-300 rounded-md
            focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500
            disabled:bg-slate-100 disabled:text-slate-500
          "
        />
      </div>

      <div>
        <label
          htmlFor="entity-type-select"
          className="block text-sm font-medium text-gray-700 mb-1"
        >
          Type
        </label>
        <select
          id="entity-type-select"
          value={typeInput}
          onChange={(e) => {
            setTypeInput(e.target.value);
            if (errorMsg) setErrorMsg(null);
          }}
          disabled={updateMutation.isPending}
          className="
            w-full px-3 py-2
            text-sm text-gray-900
            border border-slate-300 rounded-md
            focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500
            disabled:bg-slate-100 disabled:text-slate-500
          "
        >
          {/* Driven from the shared label map so the options can never drift
              from the types the database actually accepts. */}
          {Object.entries(ENTITY_TYPE_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label
          htmlFor="entity-description-input"
          className="block text-sm font-medium text-gray-700 mb-1"
        >
          Description
        </label>
        <textarea
          id="entity-description-input"
          value={descriptionInput}
          onChange={(e) => {
            setDescriptionInput(e.target.value);
            if (errorMsg) setErrorMsg(null);
          }}
          disabled={updateMutation.isPending}
          rows={3}
          className="
            w-full px-3 py-2
            text-sm text-gray-900
            border border-slate-300 rounded-md
            resize-none
            focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500
            disabled:bg-slate-100 disabled:text-slate-500
          "
        />
      </div>

      {/* Pending status — announced to screen readers (FR-021) */}
      {updateMutation.isPending && (
        <p
          role="status"
          aria-live="polite"
          className="text-sm text-slate-600 bg-slate-100 border border-slate-200 rounded-md px-3 py-1.5"
        >
          Saving…
        </p>
      )}

      {/* Inline error — preserved with the editor open (FR-022) */}
      {errorMsg && (
        <p
          id="entity-name-error"
          role="alert"
          className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-md px-3 py-1.5"
        >
          {errorMsg}
        </p>
      )}

      <div className="flex gap-2">
        <button
          type="button"
          onClick={handleSave}
          disabled={updateMutation.isPending}
          aria-busy={updateMutation.isPending ? "true" : undefined}
          className="
            min-h-[44px] min-w-[44px]
            px-4 py-2
            text-sm font-medium text-white
            bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400
            rounded-md
            focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-1
            disabled:cursor-not-allowed
            transition-colors
          "
        >
          {updateMutation.isPending ? "Saving…" : "Save"}
        </button>
        <button
          type="button"
          onClick={handleCancel}
          className="
            min-h-[44px] min-w-[44px]
            px-4 py-2
            text-sm font-medium text-slate-700
            bg-white hover:bg-slate-50
            border border-slate-300
            rounded-md
            focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-1
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
// Main page component
// ---------------------------------------------------------------------------

/**
 * EntityDetailPage — profile page for a single named entity.
 *
 * Route: /entities/:entityId
 */
/** Association source values for the multi-select filter, in display order. */
const SOURCE_FILTER_VALUES = [
  "tag",
  "transcript",
  "title",
  "description",
  "manual",
] as const;

type SourceFilterValue = (typeof SOURCE_FILTER_VALUES)[number];

/** Human-readable labels for each association source. */
const SOURCE_FILTER_LABELS: Record<SourceFilterValue, string> = {
  tag: "Tag",
  transcript: "Transcript",
  title: "Title",
  description: "Description",
  manual: "Manual",
};

function isSourceFilterValue(value: string): value is SourceFilterValue {
  return (SOURCE_FILTER_VALUES as readonly string[]).includes(value);
}

export function EntityDetailPage() {
  const { entityId } = useParams<{ entityId: string }>();
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();

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
      {
        entityId,
        options: {
          sources: ["transcript", "title", "description"],
          // Always a full rebuild, never incremental. An incremental scan only
          // ADDS, so any subtractive edit — removing an alias, adding an
          // exclusion pattern — leaves the mentions it should have retracted
          // in place, and the user sees a scan "succeed" while the wrong
          // matches survive. The delete is scoped to detection_method
          // 'rule_match', so manual and correction-derived mentions are
          // untouched, and the whole delete-and-rebuild is one transaction.
          full_rescan: true,
        },
      },
      {
        onSuccess: (data) => {
          const { mentions_found, unique_videos } = data.data;
          const msg =
            mentions_found === 0
              ? "No mentions found for this entity."
              : `Rebuilt ${mentions_found.toLocaleString()} mention${mentions_found === 1 ? "" : "s"} across ${unique_videos.toLocaleString()} video${unique_videos === 1 ? "" : "s"}.`;
          setScanMessage(msg);
          setScanMessageType("success");
          scanTimerRef.current = setTimeout(() => {
            setScanMessage(null);
            setScanMessageType(null);
          }, 3000);
        },
        onError: (err) => {
          const status = (err as { status?: number } | null)?.status;
          let msg: string;
          if (status === 404) {
            msg = "Entity not found. Please refresh the page.";
          } else if (status === 409) {
            msg = "A scan is already running for this entity.";
          } else if (status === 503 || status === 500) {
            msg = "Scan service unavailable. Please try again later.";
          } else {
            // The scan launched but failed while running — surface the
            // backend's actual failure reason instead of a generic message.
            msg = err.message || "Scan failed. Please try again.";
          }
          setScanMessage(msg);
          setScanMessageType("error");
          // Error messages persist until the user retries — no auto-dismiss.
        },
      }
    );
  }

  // Refreshes the entity-detail cache (and therefore the alias list, which
  // is read straight off `entity.aliases`) without a rescan — for mutations
  // that don't change what text matches or which videos are associated,
  // e.g. adding an alias or editing only its type.
  function refreshEntityDetail() {
    void queryClient.invalidateQueries({
      queryKey: ["entity-detail", entityId],
    });
  }

  // Deleting an alias now also retracts that alias's auto-detected
  // (rule_match) mentions on the backend, which changes entity↔video
  // associations and recomputed counts — the same shape of change a scan
  // makes. So it must invalidate the same query families `useScanEntity`
  // does (see its `getInvalidationKeys` in useEntityMentions.ts), just
  // without actually re-running a scan (the server already did the removal
  // and recompute — a rescan would be redundant work, not a correctness fix).
  function refreshEntityAssociations() {
    void queryClient.invalidateQueries({
      queryKey: ["entity-detail", entityId],
    });
    void queryClient.invalidateQueries({
      queryKey: ["entity-videos", entityId],
    });
    void queryClient.invalidateQueries({ queryKey: ["video-entities"] });
    void queryClient.invalidateQueries({ queryKey: ["entities"] });
    void queryClient.invalidateQueries({ queryKey: ["entitySearch"] });
  }

  // ---------------------------------------------------------------------------
  // Alias deletion — Undo banner (Feature #298)
  //
  // The deleted AliasRow unmounts as soon as refreshEntityAssociations's
  // refetch resolves (the alias leaves `entity.aliases`), so the Undo
  // affordance can't live in the row itself — it's lifted to the page.
  // ---------------------------------------------------------------------------

  interface DeletedAliasBanner {
    operationId: string;
    aliasName: string;
  }

  const [deletedAliasBanner, setDeletedAliasBanner] =
    useState<DeletedAliasBanner | null>(null);
  const [undoError, setUndoError] = useState<string | null>(null);
  const undoButtonRef = useRef<HTMLButtonElement>(null);
  const undoAliasDeletionMutation = useUndoAliasDeletion();

  // Move focus to Undo when the banner appears — the row the user just
  // interacted with (the delete confirm button) no longer exists.
  useEffect(() => {
    if (deletedAliasBanner) {
      undoButtonRef.current?.focus();
    }
  }, [deletedAliasBanner]);

  function handleAliasDeleted(deleted: DeletedAliasBanner) {
    refreshEntityAssociations();
    setUndoError(null);
    setDeletedAliasBanner(deleted);
  }

  function handleUndoAliasDeletion() {
    if (!deletedAliasBanner || !entityId || undoAliasDeletionMutation.isPending) {
      return;
    }
    setUndoError(null);
    undoAliasDeletionMutation.mutate(
      { operationId: deletedAliasBanner.operationId, entityId },
      {
        onSuccess: () => {
          // The association refetch above repaints the alias list — nothing
          // further to do here besides dismissing the banner.
          setDeletedAliasBanner(null);
        },
        onError: (err) => {
          const status = (err as { status?: number } | null)?.status;
          setUndoError(
            status === 409
              ? "Couldn't undo — it may already be undone, or a new alias with that name was created since."
              : status === 404
                ? "Couldn't undo — the entity or operation could no longer be found."
                : "Couldn't undo. Please try again."
          );
        },
      }
    );
  }

  function handleDismissDeletedAliasBanner() {
    setDeletedAliasBanner(null);
    setUndoError(null);
  }

  function handleDeletedAliasBannerKeyDown(
    event: React.KeyboardEvent<HTMLDivElement>
  ) {
    event.stopPropagation();
    if (event.key === "Escape") {
      handleDismissDeletedAliasBanner();
    }
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
    // FR-005a: bounded auto-refetch — poll only while grounded and properties
    // are still empty, and only for a capped number of attempts. Stops the
    // moment properties are present, the entity isn't grounded, or the cap
    // is reached; never polls indefinitely.
    refetchInterval: (query) => {
      const enrichment = query.state.data?.enrichment;
      if (!enrichment?.grounded) return false;
      if (Object.keys(enrichment.properties).length > 0) return false;
      if (query.state.dataUpdateCount >= ENRICH_POLL_MAX_ATTEMPTS) return false;
      return ENRICH_POLL_INTERVAL_MS;
    },
  });

  // T065/T019: Source filter — read the selected set from repeated ?source=
  // URL query params, ignoring any values outside the known five sources.
  const selectedSources = searchParams
    .getAll("source")
    .filter(isSourceFilterValue);

  function handleSourceToggle(value: SourceFilterValue, checked: boolean) {
    const nextSelected = checked
      ? [...selectedSources, value]
      : selectedSources.filter((s) => s !== value);

    const next = new URLSearchParams(searchParams);
    next.delete("source");
    for (const s of nextSelected) {
      next.append("source", s);
    }
    setSearchParams(next, { replace: true });
  }

  function handleClearSourceFilter() {
    const next = new URLSearchParams(searchParams);
    next.delete("source");
    setSearchParams(next, { replace: true });
  }

  // Infinite-scroll video list (union across selected sources; empty = all)
  const entityVideoParams = selectedSources.length
    ? { source: selectedSources }
    : {};
  const {
    videos,
    isLoading: videosLoading,
    hasNextPage,
    isFetchingNextPage,
    loadMoreRef,
  } = useEntityVideos(entityId ?? "", entityVideoParams);

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
        {/* Name + type badge + description — inline editable (Feature 057) */}
        <EntityNameEditor
          entityId={entityId ?? ""}
          canonicalName={entity.canonical_name}
          description={entity.description}
          entityType={entity.entity_type}
          typeBadge={
            <EntityTypeBadge entityType={entity.entity_type} size="md" />
          }
        />

        {/* Stats row */}
        <div className="flex flex-wrap items-center gap-6 text-sm text-gray-500">
          <span>
            <strong className="text-gray-900 font-semibold">
              {entity.mention_count.toLocaleString()}
            </strong>{" "}
            mention{entity.mention_count === 1 ? "" : "s"}
          </span>
          <span>
            <strong className="text-gray-900 font-semibold">
              {entity.video_count.toLocaleString()}
            </strong>{" "}
            association{entity.video_count === 1 ? "" : "s"}
          </span>
          <AssociationBreakdown bySource={entity.by_source} />
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
                Rescanning...
                <span className="sr-only">Rebuilding mentions for this entity...</span>
              </>
            ) : (
              "Rescan Mentions"
            )}
          </button>

          {!scanMutation.isPending && (
            <p className="text-sm text-slate-500">
              Rebuilds every detected mention from the entity's current aliases
              and exclusion patterns. Mentions you added or corrected by hand
              are kept.
            </p>
          )}

          {scanMutation.isPending && (
            <p
              role="status"
              aria-live="polite"
              className="text-sm text-slate-600 bg-slate-50 border border-slate-200 rounded-md px-3 py-1.5"
            >
              Scanning… (this can take a few minutes)
            </p>
          )}

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

      {/* Alias-deletion Undo banner (Feature #298) — page-level because the
          deleted AliasRow has already unmounted by the time this shows. */}
      {deletedAliasBanner && (
        <div
          role="status"
          aria-live="polite"
          onKeyDown={handleDeletedAliasBannerKeyDown}
          className="mb-4 flex flex-wrap items-center gap-3 bg-slate-100 border border-slate-200 rounded-md px-4 py-2.5"
        >
          <span className="text-sm text-slate-700 flex-1">
            {`Alias "${deletedAliasBanner.aliasName}" deleted.`}
          </span>
          {undoError !== null && (
            <span role="alert" className="text-sm text-red-600">
              {undoError}
            </span>
          )}
          <button
            ref={undoButtonRef}
            type="button"
            onClick={handleUndoAliasDeletion}
            disabled={undoAliasDeletionMutation.isPending}
            aria-busy={undoAliasDeletionMutation.isPending ? "true" : undefined}
            className="text-sm font-medium text-indigo-600 hover:text-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-1 rounded"
          >
            {undoAliasDeletionMutation.isPending ? "Undoing…" : "Undo"}
          </button>
          <button
            type="button"
            onClick={handleDismissDeletedAliasBanner}
            aria-label={`Dismiss "${deletedAliasBanner.aliasName}" deleted notification`}
            className="inline-flex items-center justify-center w-6 h-6 rounded-full text-slate-400 hover:text-slate-600 hover:bg-slate-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-1"
          >
            <svg
              className="w-3.5 h-3.5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        </div>
      )}

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
                <AliasRow
                  key={alias.id}
                  alias={alias}
                  entityId={entityId ?? ""}
                  // Primary = the entity's own name: this alias folds (case/accent-
                  // insensitive) to the entity's canonical name. Derived at render
                  // time — no stored flag (Feature 075 / #301).
                  isPrimary={
                    foldName(alias.alias_name) === foldName(entity.canonical_name)
                  }
                  // Changing the flag, or renaming the alias text, changes
                  // nothing until mentions are rebuilt: an incremental scan
                  // only adds, so it would never retract what the previous
                  // rule matched. Firing the rescan here is what makes either
                  // change mean something.
                  onMatchingChanged={handleScanClick}
                  // Editing only the alias's type doesn't change what text
                  // matches — just refresh the list.
                  onAliasListChanged={refreshEntityDetail}
                  // Deleting an alias now also retracts its auto-detected
                  // mentions on the backend — an association-level change,
                  // not just a list refresh — and offers Undo (#298).
                  onAliasDeleted={handleAliasDeleted}
                />
              ))}
            </div>
          ) : (
            <p className="text-sm text-gray-400 italic">No aliases registered.</p>
          )}
          {entityId && (
            <AddAliasForm entityId={entityId} onCreated={refreshEntityDetail} />
          )}
        </div>
      </section>

      {/* Tags section (Feature 064) */}
      {entityId && (
        <EntityTagSection entityId={entityId} entityName={entity.canonical_name} />
      )}

      {/* Enrichment section (Feature 067, US2; "Change link" — Feature 073, US1) */}
      {entityId && (
        <EntityEnrichmentSection
          entityId={entityId}
          entityType={entity.entity_type}
          canonicalName={entity.canonical_name}
          {...(entity.enrichment !== undefined
            ? { enrichment: entity.enrichment }
            : {})}
        />
      )}

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
        {/* Section header + source filter dropdown */}
        <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
          <h2
            id="entity-videos-heading"
            className="text-lg font-semibold text-gray-900"
          >
            Videos
          </h2>

          {/* T065/T019: Source filter — multi-select checkboxes (union) */}
          <fieldset className="flex flex-wrap items-center gap-x-4 gap-y-1">
            <legend className="text-sm text-gray-600 whitespace-nowrap mb-1 sm:mb-0">
              Filter videos by source:
            </legend>
            {SOURCE_FILTER_VALUES.map((value) => {
              const inputId = `source-filter-${value}`;
              return (
                <span key={value} className="flex items-center gap-1.5">
                  <input
                    id={inputId}
                    type="checkbox"
                    checked={selectedSources.includes(value)}
                    onChange={(e) => handleSourceToggle(value, e.target.checked)}
                    className="h-4 w-4 rounded border-slate-300 text-indigo-600 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
                  />
                  <label
                    htmlFor={inputId}
                    className="text-sm text-gray-700 whitespace-nowrap"
                  >
                    {SOURCE_FILTER_LABELS[value]}
                  </label>
                </span>
              );
            })}
          </fieldset>
        </div>

        {/* Appears-with panel (Feature 062, US3).

            Rendered unconditionally rather than gated on the video list's
            loading state, and fetching through its own query — it must not
            block this page's initial render (FR-037). It is the feature's
            slowest query, so making the page wait on it would penalise
            exactly the entities users open most. A failure inside it degrades
            to a panel-level message and leaves this page usable (FR-038). */}
        {entityId && (
          <div className="mb-6">
            <CooccurringPanel entityId={entityId} />
          </div>
        )}

        {/* Loading skeleton for video list — T067: dropdown stays interactive */}
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
                  description_context={v.description_context ?? null}
                  entityName={entity.canonical_name}
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

        {/* Empty state — T066/T019: source-filtered empty state */}
        {!videosLoading && videos.length === 0 && (
          <div className="bg-white rounded-xl border border-gray-100 p-8 text-center">
            {selectedSources.length > 0 ? (
              <>
                <p className="text-gray-500 mb-2">
                  No videos found for the selected source(s).
                </p>
                <button
                  type="button"
                  onClick={handleClearSourceFilter}
                  className="text-sm text-indigo-600 hover:text-indigo-800 underline focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
                >
                  Try all sources
                </button>
              </>
            ) : (
              <p className="text-gray-500">No videos found for this entity.</p>
            )}
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
