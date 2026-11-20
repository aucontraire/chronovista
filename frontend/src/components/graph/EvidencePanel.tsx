/**
 * EvidencePanel — "Where they're discussed together" (Feature 114, US1).
 *
 * Transcript passages where both entities are mentioned, one row per video (FR-009), closest-first,
 * streamed in by infinite scroll (FR-016 — a dense pair is never collapsed away). This is co-mention
 * evidence, not a statement that the entities are related. A failure degrades to a panel-level alert.
 */

import { useEffect, useRef } from "react";

import { useConnectionEvidence } from "../../hooks/useConnectionEvidence";
import { EvidenceItem } from "./EvidenceItem";

interface EvidencePanelProps {
  entityAId: string;
  entityBId: string;
  className?: string;
}

export function EvidencePanel({
  entityAId,
  entityBId,
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
  } = useConnectionEvidence(entityAId, entityBId);

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
        <p
          role="alert"
          className="text-sm text-amber-800"
          data-testid="evidence-error"
        >
          Couldn&apos;t load transcript passages. The rest of this page is
          unaffected.
        </p>
      )}

      {!isLoading && !isError && first && items.length === 0 && (
        <div role="status" data-testid="evidence-empty">
          {first.basis_when_empty ? (
            <p className="text-sm text-slate-600">
              These entities co-occur through {first.basis_when_empty} mentions,
              but no readable transcript passage mentions both.
            </p>
          ) : first.total_available > 0 ? (
            <p className="text-sm text-slate-600">
              There are no more transcript passages to show.
            </p>
          ) : (
            <p className="text-sm text-slate-600">
              No transcript passage mentions both of these entities.
            </p>
          )}
        </div>
      )}

      {!isLoading && first && items.length > 0 && (
        <>
          <p
            className="mb-3 text-xs text-slate-500"
            data-testid="evidence-counts"
            aria-live="polite"
            aria-atomic="true"
          >
            Spoken together in {first.total_available}{" "}
            {first.total_available === 1 ? "video" : "videos"} (
            {first.raw_cooccurrence_count}{" "}
            {first.raw_cooccurrence_count === 1 ? "transcript" : "transcripts"}
            ).
          </p>
          <ul className="space-y-2" aria-label="Transcript passages">
            {items.map((item) => (
              <EvidenceItem key={item.video_id} item={item} />
            ))}
          </ul>

          {hasNextPage && (
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
