/**
 * RelationshipCandidatesPage — read-only, lift-ranked queue of novel
 * relationship candidates (Feature 107). No verdict UI exists.
 */

import { useEffect, useState } from "react";

import { RelationshipCandidateRow } from "../components/relationship/RelationshipCandidateRow";
import { SkipLink } from "../components/SkipLink";
import { useRelationshipCandidates } from "../hooks/useRelationshipCandidates";

const MAIN_CONTENT_ID = "relationship-candidates-main-content";
const PAGE_SIZE = 50;

const PAGE_BUTTON_CLASS =
  "px-4 py-2 text-sm font-medium rounded-lg border border-gray-300 bg-white text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-indigo-500";

export function RelationshipCandidatesPage() {
  const [eligibleOnly, setEligibleOnly] = useState(false);
  const [offset, setOffset] = useState(0);

  const { data, isLoading, isError, error, refetch } = useRelationshipCandidates({
    limit: PAGE_SIZE,
    offset,
    eligible_only: eligibleOnly,
  });

  useEffect(() => {
    document.title = "Relationship Candidates - ChronoVista";
    return () => {
      document.title = "ChronoVista";
    };
  }, []);

  const total = data?.total ?? 0;
  const items = data?.items ?? [];
  const from = total === 0 ? 0 : offset + 1;
  const to = offset + items.length;

  return (
    <>
      <SkipLink targetId={MAIN_CONTENT_ID} label="Skip to content" />
      <main
        id={MAIN_CONTENT_ID}
        tabIndex={-1}
        className="container mx-auto px-4 py-8"
      >
        <h1 className="text-3xl font-bold text-gray-900">
          Relationship Candidates
        </h1>
        <p className="mt-2 mb-4 text-sm text-gray-600">
          Entity pairs that appear together in videos more often than chance,
          ranked by lift. Each is only a candidate; nothing here is a verdict.
        </p>
        {data?.generated_at && (
          <p className="mb-4 text-xs text-gray-500">
            Last generated{" "}
            <time dateTime={data.generated_at}>
              {new Date(data.generated_at).toLocaleString()}
            </time>
          </p>
        )}

        <div className="mb-6">
          <label className="inline-flex items-center gap-2 text-sm font-medium text-gray-700">
            <input
              type="checkbox"
              checked={eligibleOnly}
              onChange={(e) => {
                setEligibleOnly(e.target.checked);
                setOffset(0);
              }}
              className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
            />
            Measured-precision only
          </label>
        </div>

        {isLoading && (
          <p role="status" className="text-sm text-gray-500">
            Loading relationship candidates...
          </p>
        )}

        {isError && (
          <div
            role="alert"
            className="bg-red-50 border border-red-200 rounded-lg p-4"
          >
            <p className="text-red-800 font-medium mb-2">
              {error instanceof Error && error.message
                ? error.message
                : "Failed to load relationship candidates."}
            </p>
            <button
              type="button"
              onClick={() => void refetch()}
              className="px-4 py-2 bg-red-600 text-white font-medium rounded-md hover:bg-red-700"
            >
              Retry
            </button>
          </div>
        )}

        {!isLoading && !isError && data && total === 0 && (
          <div
            role="status"
            className="bg-white rounded-xl border border-gray-100 shadow-md p-8 text-center"
          >
            <p className="text-gray-900 font-medium">
              No relationship candidates yet.
            </p>
            <p className="mt-1 text-sm text-gray-600">
              {eligibleOnly
                ? "No candidates have measured precision. Turn off the filter to see all."
                : "Run the relationship candidate generator to populate this list."}
            </p>
          </div>
        )}

        {!isError && items.length > 0 && (
          <>
            <ul aria-label="Relationship candidates" className="space-y-3">
              {items.map((c) => (
                <RelationshipCandidateRow key={c.id} candidate={c} />
              ))}
            </ul>
            <nav
              aria-label="Pagination"
              className="mt-6 flex items-center justify-between"
            >
              <button
                type="button"
                className={PAGE_BUTTON_CLASS}
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              >
                Previous
              </button>
              <p className="text-sm text-gray-600">
                {`Showing ${from}-${to} of ${total.toLocaleString()}`}
              </p>
              <button
                type="button"
                className={PAGE_BUTTON_CLASS}
                disabled={offset + PAGE_SIZE >= total}
                onClick={() => setOffset(offset + PAGE_SIZE)}
              >
                Next
              </button>
            </nav>
          </>
        )}
      </main>
    </>
  );
}
