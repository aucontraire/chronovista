/**
 * CooccurringPanel — "appears with" on the entity detail page (Feature 062, US3).
 *
 * Discovery without knowing what to search for: shows which entities share the
 * most videos with the subject, and opens any pairing as an intersection.
 *
 * The count each row shows equals the total of the page it opens (FR-024b), so
 * the panel never promises a number the destination contradicts.
 */

import { useState } from "react";
import { Link } from "react-router-dom";

import { EntityName } from "../EntityName";
import {
  COOCCURRING_PAGE_SIZE,
  useCooccurringEntities,
} from "../../hooks/useCooccurringEntities";

/** Server-enforced ceiling; reveal-more stops here (FR-023a). */
const MAX_COOCCURRING = 50;

interface CooccurringPanelProps {
  /** The subject entity. */
  entityId: string;
  /**
   * Evidence scope of the surrounding view. The panel must compute under the
   * same scope it carries forward, or the count shown and the intersection it
   * opens will disagree (FR-024a).
   */
  minEvidence?: "transcript" | undefined;
  className?: string;
}

export function CooccurringPanel({
  entityId,
  minEvidence,
  className = "",
}: CooccurringPanelProps) {
  const [limit, setLimit] = useState(COOCCURRING_PAGE_SIZE);
  const { partners, isLoading, isError } = useCooccurringEntities(
    entityId,
    limit,
    minEvidence
  );

  /**
   * Address scheme shared with the videos list, not a parallel one (FR-022).
   *
   * Targets `/videos` explicitly, NOT `/`. The root is an index route that
   * redirects with `<Navigate to="/videos" replace />`, and that redirect
   * carries no query string — linking to `/?entity_id=…` silently lands on an
   * unfiltered videos page with every parameter dropped.
   */
  function intersectionHref(partnerId: string): string {
    const params = new URLSearchParams();
    params.append("entity_id", entityId);
    params.append("entity_id", partnerId);
    if (minEvidence) params.set("min_evidence", minEvidence);
    return `/videos?${params.toString()}`;
  }

  return (
    <section
      className={`rounded-lg border border-slate-200 bg-white p-4 ${className}`.trim()}
      aria-labelledby="cooccurring-heading"
      data-testid="cooccurring-panel"
    >
      <h2
        id="cooccurring-heading"
        className="mb-3 text-sm font-semibold text-slate-800"
      >
        Appears with
      </h2>

      {/* Loading state, distinct from empty and from error (FR-036). */}
      {isLoading && (
        <p
          role="status"
          className="text-sm text-slate-500"
          data-testid="cooccurring-loading"
        >
          Finding related entities…
        </p>
      )}

      {/* A panel failure degrades to a panel-level error and leaves the
          surrounding page usable (FR-038). It deliberately does not raise. */}
      {!isLoading && isError && (
        <p
          role="alert"
          className="text-sm text-amber-800"
          data-testid="cooccurring-error"
        >
          Couldn&apos;t load related entities. The rest of this page is
          unaffected.
        </p>
      )}

      {!isLoading && !isError && partners.length === 0 && (
        <div role="status" data-testid="cooccurring-empty">
          <p className="text-sm text-slate-600">
            Nothing else appears alongside this entity yet.
          </p>
          {/* An empty result under a restricted scope is a different fact from
              one empty under every scope, and suggests a different action
              (FR-024d). */}
          {minEvidence === "transcript" && (
            <p className="mt-1 text-xs text-slate-500">
              Transcript-only is active — title and description mentions are
              being excluded. Turning it off may reveal connections.
            </p>
          )}
        </div>
      )}

      {!isLoading && !isError && partners.length > 0 && (
        <>
          <ul className="space-y-1">
            {partners.map((partner) => (
              <li key={partner.entity_id}>
                <Link
                  to={intersectionHref(partner.entity_id)}
                  className="flex items-center justify-between gap-2 rounded px-2 py-1.5 text-sm hover:bg-slate-50"
                >
                  <EntityName
                    name={partner.canonical_name}
                    entityType={partner.entity_type}
                    className="min-w-0 truncate"
                  />
                  <span className="shrink-0 text-slate-500">
                    {partner.shared_video_count}{" "}
                    {partner.shared_video_count === 1 ? "video" : "videos"}
                  </span>
                </Link>
              </li>
            ))}
          </ul>

          {/* Reveal-more requests a further tranche of the same size, bounded
              by the ceiling the endpoint enforces (FR-023, FR-023a). Hidden
              once the list is short of the requested limit, since that means
              there is nothing further to reveal. */}
          {partners.length >= limit && limit < MAX_COOCCURRING && (
            <button
              type="button"
              onClick={() =>
                setLimit((current) =>
                  Math.min(current + COOCCURRING_PAGE_SIZE, MAX_COOCCURRING)
                )
              }
              className="mt-2 text-sm text-indigo-700 hover:underline"
            >
              Show more
            </button>
          )}
        </>
      )}
    </section>
  );
}
