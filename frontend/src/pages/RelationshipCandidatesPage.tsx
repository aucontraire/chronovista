/**
 * RelationshipCandidatesPage — read-only, lift-ranked queue of novel
 * relationship candidates (Feature 107). No verdict UI exists.
 */

import { useEffect, useState } from "react";

import {
  TermsExplainer,
  type TermEntry,
} from "../components/candidates/TermsExplainer";
import {
  RelationshipCandidateRow,
  ReviewStatusBadge,
  VERDICT_BADGES,
} from "../components/relationship/RelationshipCandidateRow";
import { SkipLink } from "../components/SkipLink";
import {
  useRelationshipCandidates,
  type ReviewFilter,
  type SortBy,
  type SortDir,
  type VerdictCategory,
} from "../hooks/useRelationshipCandidates";

const MAIN_CONTENT_ID = "relationship-candidates-main-content";
const PAGE_SIZE = 50;

const PAGE_BUTTON_CLASS =
  "px-4 py-2 text-sm font-medium rounded-lg border border-gray-300 bg-white text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-indigo-500";

const REVIEW_OPTIONS: { value: ReviewFilter; label: string }[] = [
  { value: "reviewed", label: "Reviewed" },
  { value: "unreviewed", label: "Not reviewed" },
  { value: "all", label: "All" },
];

const VERDICT_ORDER: readonly VerdictCategory[] = [
  "associated_with",
  "co_cast",
  "covers",
  "coincidence",
  "artifact",
];

const METRIC_TERMS: readonly TermEntry[] = [
  {
    term: "Lift",
    definition:
      "How much more these two co-occur than chance would predict. High lift means a real association, not just two popular entities.",
  },
  {
    term: "Corroboration",
    definition:
      "How much the knowledge base already partially supports this pair.",
  },
];

const SORT_COLUMNS: { value: Exclude<SortBy, "rank">; label: string }[] = [
  { value: "lift", label: "Lift" },
  { value: "shared_video_count", label: "Shared videos" },
  { value: "kb_corroboration_count", label: "Corroboration" },
  { value: "reviewed_at", label: "Reviewed date" },
];

export function RelationshipCandidatesPage() {
  const [eligibleOnly, setEligibleOnly] = useState(false);
  const [review, setReview] = useState<ReviewFilter>("all");
  const [verdicts, setVerdicts] = useState<VerdictCategory[]>([]);
  const [sortBy, setSortBy] = useState<SortBy>("rank");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [offset, setOffset] = useState(0);

  const handleSort = (column: Exclude<SortBy, "rank">) => {
    if (sortBy === column) {
      setSortDir(sortDir === "desc" ? "asc" : "desc");
    } else {
      setSortBy(column);
      setSortDir("desc");
    }
    setOffset(0);
  };

  const { data, isLoading, isError, error, refetch } = useRelationshipCandidates({
    limit: PAGE_SIZE,
    offset,
    eligible_only: eligibleOnly,
    review,
    verdict: verdicts,
    sort_by: sortBy,
    sort_dir: sortDir,
  });

  useEffect(() => {
    document.title = "Relationship Candidates - ChronoVista";
    return () => {
      document.title = "ChronoVista";
    };
  }, []);

  const total = data?.total ?? 0;
  const totalBeforeScoping = data?.total_before_scoping ?? total;
  const headCutoff = data?.head_cutoff ?? 0;
  const isScoped = totalBeforeScoping > total && total >= headCutoff;
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
        <TermsExplainer
          heading={
            <h1 className="text-3xl font-bold text-gray-900">
              Relationship Candidates
            </h1>
          }
          terms={METRIC_TERMS}
          panelLabel="Relationship candidate key"
          intro="How to read the verdict badges and the numbers on each pair."
        >
          <dl
            aria-label="Verdict categories"
            className="grid grid-cols-1 sm:grid-cols-[11rem_1fr] gap-x-4 gap-y-2 text-sm mb-4 pb-4 border-b border-gray-100"
          >
            {VERDICT_ORDER.map((v) => (
              <div key={v} className="contents">
                <dt>
                  <ReviewStatusBadge status={v} />
                </dt>
                <dd className="text-gray-600 mb-2 sm:mb-0">
                  {VERDICT_BADGES[v]?.meaning}
                </dd>
              </div>
            ))}
            <div className="contents">
              <dt>
                <ReviewStatusBadge status={null} />
              </dt>
              <dd className="text-gray-600">
                Not yet reviewed; still a candidate awaiting judgment.
              </dd>
            </div>
          </dl>
        </TermsExplainer>
        <p className="-mt-4 mb-4 text-sm text-gray-600">
          Entity pairs that appear together in videos more often than chance,
          ranked by lift. Pairs you&apos;ve reviewed show their verdict (see the
          &ldquo;i&rdquo; key above); the rest are still candidates awaiting judgment.
        </p>
        {data?.generated_at && (
          <p className="mb-4 text-xs text-gray-500">
            Last generated{" "}
            <time dateTime={data.generated_at}>
              {new Date(data.generated_at).toLocaleString()}
            </time>
          </p>
        )}

        <fieldset className="mb-4">
          <legend className="text-sm font-medium text-gray-700 mb-1">
            Review status
          </legend>
          <div className="inline-flex rounded-lg border border-gray-300 overflow-hidden">
            {REVIEW_OPTIONS.map((o) => (
              <label
                key={o.value}
                className={`px-4 py-2 text-sm font-medium cursor-pointer focus-within:ring-2 focus-within:ring-inset focus-within:ring-indigo-500 ${
                  review === o.value
                    ? "bg-indigo-600 text-white"
                    : "bg-white text-gray-700 hover:bg-gray-50"
                }`}
              >
                <input
                  type="radio"
                  name="review-filter"
                  value={o.value}
                  checked={review === o.value}
                  onChange={() => {
                    setReview(o.value);
                    setOffset(0);
                  }}
                  className="sr-only"
                />
                {o.label}
              </label>
            ))}
          </div>
        </fieldset>

        <fieldset className="mb-4">
          <legend className="text-sm font-medium text-gray-700 mb-1">
            Verdict category (none selected = all)
          </legend>
          <div className="flex flex-wrap items-center gap-2">
            {VERDICT_ORDER.map((v) => {
              const badge = VERDICT_BADGES[v];
              const checked = verdicts.includes(v);
              return (
                <label
                  key={v}
                  className={`text-sm px-3 py-1 rounded-full border cursor-pointer focus-within:ring-2 focus-within:ring-indigo-500 ${
                    badge?.cls ?? ""
                  } ${checked ? "ring-2 ring-gray-900 font-semibold" : "opacity-70 hover:opacity-100"}`}
                >
                  <input
                    type="checkbox"
                    name="verdict-filter"
                    value={v}
                    checked={checked}
                    onChange={() => {
                      setVerdicts(
                        checked ? verdicts.filter((x) => x !== v) : [...verdicts, v]
                      );
                      setOffset(0);
                    }}
                    className="sr-only"
                  />
                  <span aria-hidden="true">{`${badge?.glyph ?? ""} `}</span>
                  {v}
                </label>
              );
            })}
            {verdicts.length > 0 && (
              <button
                type="button"
                onClick={() => {
                  setVerdicts([]);
                  setOffset(0);
                }}
                className="px-3 py-1.5 text-sm text-indigo-700 hover:underline focus:outline-none focus:ring-2 focus:ring-indigo-500 rounded"
              >
                Clear categories
              </button>
            )}
          </div>
        </fieldset>

        <div
          role="group"
          aria-label="Sort by"
          className="mb-4 flex flex-wrap items-center gap-2"
        >
          <span className="text-sm font-medium text-gray-700">Sort by</span>
          {SORT_COLUMNS.map((c) => {
            const active = sortBy === c.value;
            const dirWord = sortDir === "desc" ? "descending" : "ascending";
            return (
              <button
                key={c.value}
                type="button"
                aria-pressed={active}
                aria-label={
                  active ? `${c.label}, sorted ${dirWord}` : `${c.label}, not sorted`
                }
                data-sort-dir={active ? sortDir : undefined}
                onClick={() => handleSort(c.value)}
                className={`px-3 py-1.5 text-sm rounded-lg border focus:outline-none focus:ring-2 focus:ring-indigo-500 ${
                  active
                    ? "border-indigo-600 bg-indigo-50 text-indigo-900 font-semibold"
                    : "border-gray-300 bg-white text-gray-700 hover:bg-gray-50"
                }`}
              >
                {c.label}
                {active && (
                  <span aria-hidden="true">
                    {sortDir === "desc" ? " \u2193" : " \u2191"}
                  </span>
                )}
              </button>
            );
          })}
          {sortBy !== "rank" && (
            <button
              type="button"
              onClick={() => {
                setSortBy("rank");
                setSortDir("desc");
                setOffset(0);
              }}
              className="px-3 py-1.5 text-sm text-indigo-700 hover:underline focus:outline-none focus:ring-2 focus:ring-indigo-500 rounded"
            >
              Reset to rank
            </button>
          )}
        </div>

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
              {review !== "all" || verdicts.length > 0
                ? "No candidates match the review filter. Switch to All to see every candidate."
                : eligibleOnly
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
                {isScoped &&
                  ` — top ${headCutoff.toLocaleString()} of ${totalBeforeScoping.toLocaleString()}`}
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
