/**
 * EvidencePanel — "Where they're discussed together" (Features 114/118).
 *
 * Discussion passages where both entities are mentioned, one row per video (FR-009), closest-first,
 * streamed in by infinite scroll (FR-016 — a dense pair is never collapsed away). This is co-mention
 * evidence, not a statement that the entities are related. A failure degrades to a panel-level alert.
 */

import { useEffect, useId, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { DEFAULT_PROXIMITY_WINDOW, PROXIMITY_WINDOWS } from "../../api/graph";
import type {
  FailedScope,
  PairPassages,
  ProximityWindow,
} from "../../api/graph";
import { useFartherVideos, usePairPassages } from "../../hooks/usePairPassages";
import { formatTimestamp } from "../../utils/formatTimestamp";
import { buildVideoDeepLink } from "../../utils/videoDeepLink";
import { EvidenceItem } from "./EvidenceItem";

interface EvidencePanelProps {
  entityAId: string;
  entityBId: string;
  /** Proximity window in seconds; defaults to the server default. */
  window?: ProximityWindow;
  /** Called with the chosen window; the page writes it to the URL. */
  onWindowChange?: (window: ProximityWindow) => void;
  className?: string;
}

function plural(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`;
}

/** Co-mention totals over every video in the window — never a claim of relationship. */
function summarySentence(first: PairPassages): string {
  const base = `${plural(first.passage_count, "discussion passage", "discussion passages")} across ${plural(first.video_count, "video", "videos")}, ${plural(first.channel_count, "channel", "channels")}`;
  return first.closest_gap_seconds === null
    ? `${base}.`
    : `${base}; closest mentions ${Math.round(first.closest_gap_seconds)} s apart.`;
}

function emptyMessage(first: PairPassages, window: ProximityWindow): string {
  switch (first.state) {
    case "no_passage_in_window":
      return `No passage within ${window} s.`;
    case "not_computed":
      return "Not computed yet; this updates automatically.";
    case "no_transcript":
      return first.basis_when_empty
        ? `Not spoken together in any transcript. These entities co-occur through ${first.basis_when_empty} mentions, but no readable transcript passage mentions both.`
        : "Not spoken together in any transcript.";
    default:
      return "There are no more transcript passages to show.";
  }
}

const toggleClass =
  "rounded text-xs text-indigo-700 hover:underline focus:outline-none focus:ring-2 focus:ring-indigo-500";

function FailedScopes({ scopes }: { scopes: FailedScope[] }) {
  const [open, setOpen] = useState(false);
  const listId = useId();
  return (
    <div role="status" className="mb-2" data-testid="evidence-failed">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={listId}
        onClick={() => setOpen((v) => !v)}
        className={toggleClass}
      >
        {plural(scopes.length, "transcript", "transcripts")} could not be
        computed; counts may be incomplete
      </button>
      {open && (
        <ul id={listId} className="mt-1 space-y-1 text-xs text-slate-600">
          {scopes.map((scope) => (
            <li key={`${scope.video_id}-${scope.language_code}`}>
              {scope.video_title ?? "Untitled video"}
              {scope.channel_title ? ` · ${scope.channel_title}` : ""} ·{" "}
              {scope.language_code}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Videos where both are spoken but never within the window; fetched only once expanded. */
function FartherVideosSection({
  entityAId,
  entityBId,
  window,
  count,
}: {
  entityAId: string;
  entityBId: string;
  window: ProximityWindow;
  count: number;
}) {
  const [open, setOpen] = useState(false);
  const listId = useId();
  const farther = useFartherVideos(entityAId, entityBId, window, open);
  return (
    <div className="mb-3" data-testid="evidence-farther">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={listId}
        onClick={() => setOpen((v) => !v)}
        className={toggleClass}
      >
        Plus {plural(count, "video", "videos")} where both are spoken farther
        apart
      </button>
      <div id={listId}>
        {open && farther.isLoading && (
          <p role="status" className="mt-1 text-xs text-slate-500">
            Loading…
          </p>
        )}
        {open && farther.isError && (
          <p role="alert" className="mt-1 text-xs text-amber-800">
            Couldn&apos;t load these videos.
          </p>
        )}
        {open && farther.items.length > 0 && (
          <ul className="mt-1 space-y-1 text-xs text-slate-600">
            {farther.items.map((video) => {
              const title = video.video_title ?? "Untitled video";
              const stamp = formatTimestamp(video.nearest_start_time);
              return (
                <li key={`${video.video_id}-${video.language_code}`}>
                  {title}
                  {video.channel_title ? ` · ${video.channel_title}` : ""} ·{" "}
                  {video.language_code} ·{" "}
                  {Math.round(video.nearest_gap_seconds)}s apart ·{" "}
                  <Link
                    to={buildVideoDeepLink(video.video_id, {
                      lang: video.language_code,
                      t: video.nearest_start_time,
                    })}
                    aria-label={`Open at ${stamp} – ${title} (${video.language_code})`}
                    className="font-mono text-indigo-700 hover:underline focus:outline-none focus:ring-2 focus:ring-indigo-500 rounded"
                  >
                    Open at {stamp}
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
        {open && farther.hasNextPage && (
          <button
            type="button"
            onClick={farther.fetchNextPage}
            aria-disabled={farther.isFetchingNextPage}
            className={`mt-1 ${toggleClass}`}
          >
            {farther.isFetchingNextPage ? "Loading more…" : "Show more"}
          </button>
        )}
      </div>
    </div>
  );
}

export function EvidencePanel({
  entityAId,
  entityBId,
  window = DEFAULT_PROXIMITY_WINDOW,
  onWindowChange,
  className = "",
}: EvidencePanelProps) {
  const {
    items,
    first,
    isLoading,
    isError,
    hasNextPage,
    isFetchingNextPage,
    isFetchNextPageError,
    fetchNextPage,
    refetch,
  } = usePairPassages(entityAId, entityBId, window);

  // Infinite scroll: load the next page when a sentinel near the end scrolls into view. The visible
  // "Load more" button below is the keyboard-accessible fallback (and the path tests exercise).
  const sentinelRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const el = sentinelRef.current;
    if (!el || !hasNextPage || isFetchNextPageError) return;
    const io = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting && !isFetchingNextPage) fetchNextPage();
      },
      { rootMargin: "200px" },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [hasNextPage, isFetchingNextPage, isFetchNextPageError, fetchNextPage]);

  return (
    <section
      className={`rounded-lg border border-slate-200 bg-white p-4 ${className}`.trim()}
      aria-labelledby="evidence-heading"
      data-testid="evidence-panel"
    >
      <h2
        id="evidence-heading"
        className="mb-3 text-sm font-semibold text-slate-800"
      >
        Where they&apos;re discussed together
      </h2>

      <fieldset className="mb-3 flex flex-wrap items-center gap-2">
        <legend className="sr-only">Mentioned within</legend>
        <span aria-hidden="true" className="text-xs text-slate-500">
          Mentioned within
        </span>
        {PROXIMITY_WINDOWS.map((value) => (
          <label
            key={value}
            className={`cursor-pointer rounded-md border px-3 py-1 text-sm focus-within:ring-2 focus-within:ring-indigo-600 ${
              window === value
                ? "border-indigo-700 bg-indigo-50 font-semibold text-indigo-900"
                : "border-slate-300 text-slate-700"
            }`}
          >
            <input
              type="radio"
              name="proximity-window"
              value={value}
              checked={window === value}
              onChange={() => onWindowChange?.(value)}
              className="sr-only"
            />
            {value} s
          </label>
        ))}
      </fieldset>

      {isLoading && (
        <p
          role="status"
          className="text-sm text-slate-500"
          data-testid="evidence-loading"
        >
          Finding passages…
        </p>
      )}

      {!isLoading && isError && items.length === 0 && (
        <div className="flex flex-wrap items-center gap-3">
          <p
            role="alert"
            className="text-sm text-amber-800"
            data-testid="evidence-error"
          >
            Couldn&apos;t load transcript passages. The rest of this page is
            unaffected.
          </p>
          <button
            type="button"
            onClick={refetch}
            className="rounded border border-slate-300 px-2 py-1 text-xs text-indigo-700 hover:underline focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            Retry
          </button>
        </div>
      )}

      {!isLoading && !(isError && items.length === 0) && first && (
        <>
          {items.length > 0 ? (
            <p
              className="mb-3 text-xs text-slate-500"
              data-testid="evidence-counts"
              aria-live="polite"
              aria-atomic="true"
            >
              {summarySentence(first)}
            </p>
          ) : (
            <div
              role="status"
              data-testid="evidence-empty"
              className="mb-3 text-sm text-slate-600"
            >
              {emptyMessage(first, window)}
            </div>
          )}

          {first.pending_scopes > 0 && (
            <p
              role="status"
              className="mb-2 text-xs text-slate-600"
              data-testid="evidence-pending"
            >
              Updating: {first.pending_scopes}{" "}
              {first.pending_scopes === 1 ? "transcript is" : "transcripts are"}{" "}
              being recomputed; counts may change.
            </p>
          )}

          {first.failed_scopes.length > 0 && (
            <FailedScopes scopes={first.failed_scopes} />
          )}

          {first.farther_video_count > 0 && (
            <FartherVideosSection
              key={window}
              entityAId={entityAId}
              entityBId={entityBId}
              window={window}
              count={first.farther_video_count}
            />
          )}

          {items.length > 0 && (
            <ul className="space-y-2" aria-label="Transcript passages">
              {items.map((item) => (
                <EvidenceItem key={`${item.video_id}-${window}`} item={item} />
              ))}
            </ul>
          )}

          {items.length > 0 && hasNextPage && (
            <div
              ref={sentinelRef}
              className="mt-2 flex items-center gap-3 text-xs text-slate-500"
            >
              <button
                type="button"
                onClick={() => {
                  if (!isFetchingNextPage) fetchNextPage();
                }}
                aria-disabled={isFetchingNextPage}
                aria-label="Show more co-mention videos"
                className="rounded text-indigo-700 hover:underline focus:outline-none focus:ring-2 focus:ring-indigo-500 aria-disabled:text-slate-400"
              >
                {isFetchingNextPage ? "Loading more…" : "Show more"}
              </button>
              {isFetchNextPageError && (
                <span role="alert" className="text-amber-800">
                  Couldn&apos;t load more. Try again.
                </span>
              )}
            </div>
          )}
        </>
      )}
    </section>
  );
}
