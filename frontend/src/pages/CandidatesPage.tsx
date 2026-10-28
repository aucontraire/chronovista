/**
 * CandidatesPage — the ranked pending candidate review queue (Feature 097).
 *
 * Phase 2 renders a basic list; filters, sort and the summary panel arrive in
 * a later phase.
 */

import { useCallback, useEffect } from "react";
import { Link, useSearchParams } from "react-router-dom";

import type { CandidateDetail } from "../api/candidates";
import {
  TermsExplainer,
  triageLabel,
  type TermKey,
} from "../components/candidates/TermsExplainer";
import { ProgressBar } from "../components/onboarding/ProgressBar";
import { SkipLink } from "../components/SkipLink";
import { ENTITY_TYPE_TABS } from "../constants/entityTypes";
import {
  useCandidateSummary,
  useCandidatesList,
  useGenerationStatus,
  useStartGeneration,
} from "../hooks/useCandidates";

/** Stable ID used by SkipLink and main content container. */
const MAIN_CONTENT_ID = "candidates-main-content";

const TRIAGE_OPTIONS = [
  { value: "all", label: "All triage" },
  { value: "worth_review", label: "Worth review" },
  { value: "likely_eliminable", label: "Likely eliminable" },
  { value: "grounds_nowhere", label: triageLabel("grounds_nowhere") },
];
const SORT_OPTIONS = [
  { value: "score", label: "Score" },
  { value: "corroboration", label: "Corroboration" },
  { value: "salience", label: "Salience" },
];
const VALID_TRIAGE = TRIAGE_OPTIONS.map((o) => o.value);
const VALID_SORT = SORT_OPTIONS.map((o) => o.value);
const VALID_TYPES = ENTITY_TYPE_TABS.map((t) => t.value);

/** Token count at or above which a name is no longer "single-token". */
const MULTI_TOKEN_MIN = 2;

const SELECT_CLASS =
  "text-sm border border-gray-300 rounded-lg bg-white text-gray-900 py-2 pl-3 pr-8 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500";

const LIST_TERMS: readonly TermKey[] = [
  "worth_review",
  "likely_eliminable",
  "grounds_nowhere",
  "score",
  "corroboration",
  "salience",
  "single_token",
  "possible_duplicate",
];

function SummaryPanel() {
  const { data, isError } = useCandidateSummary();
  if (isError) return null;
  if (!data) {
    return (
      <section aria-label="Queue summary" className="mb-6 text-sm text-gray-500">
        Loading summary...
      </section>
    );
  }
  const stat = (label: string, value: number) => (
    <div key={label} className="flex gap-1">
      <dt>{label}</dt>
      <dd className="font-semibold text-gray-900">{value.toLocaleString()}</dd>
    </div>
  );
  return (
    <section
      aria-label="Queue summary"
      className="mb-6 bg-white rounded-xl shadow-md border border-gray-100 p-4 space-y-2"
    >
      <h2 className="sr-only">Queue summary</h2>
      <dl
        aria-label="Review status counts"
        className="flex flex-wrap gap-x-6 gap-y-1 text-sm text-gray-600"
      >
        {stat("Pending", data.pending)}
        {stat("Approved", data.approved)}
        {stat("Rejected", data.rejected)}
        {stat("Superseded", data.superseded)}
      </dl>
      <dl
        aria-label="Pending triage counts"
        className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-gray-500"
      >
        {stat("Worth review", data.worth_review)}
        {stat("Likely eliminable", data.likely_eliminable)}
        {stat(triageLabel("grounds_nowhere"), data.grounds_nowhere)}
      </dl>
    </section>
  );
}

function Toggle({
  label,
  checked,
  onClick,
}: {
  label: string;
  checked: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={onClick}
      className={`inline-flex items-center gap-2 min-h-[44px] px-4 py-2 text-sm font-medium rounded-lg border transition-colors whitespace-nowrap focus:outline-none focus:ring-2 focus:ring-indigo-500 ${
        checked
          ? "bg-indigo-50 border-indigo-300 text-indigo-700"
          : "bg-white border-gray-300 text-gray-600 hover:bg-gray-50"
      }`}
    >
      <span
        aria-hidden="true"
        className={`inline-block w-4 h-4 rounded-full border-2 flex-shrink-0 ${
          checked ? "bg-indigo-600 border-indigo-600" : "bg-white border-gray-400"
        }`}
      />
      {label}
    </button>
  );
}

function CandidateRow({ candidate }: { candidate: CandidateDetail }) {
  return (
    <li>
      <Link
        to={`/candidates/${candidate.id}`}
        className="block bg-white rounded-xl shadow-md border border-gray-100 p-4 hover:shadow-lg hover:border-gray-200 transition-all focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2"
      >
        <div className="flex flex-wrap items-center gap-2 mb-2">
          <h3 className="text-base font-semibold text-gray-900">
            {candidate.label}
          </h3>
          <span className="text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-700">
            {candidate.type_hint}
          </span>
          <span className="text-xs px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700">
            {triageLabel(candidate.triage)}
          </span>
        </div>
        <dl className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-gray-500">
          <div className="flex gap-1">
            <dt>Score</dt>
            <dd className="font-semibold text-gray-700">
              {candidate.score.toFixed(2)}
            </dd>
          </div>
          <div className="flex gap-1">
            <dt>Corroboration</dt>
            <dd className="font-semibold text-gray-700">
              {candidate.corroboration_count}
            </dd>
          </div>
          <div className="flex gap-1">
            <dt>Salience</dt>
            <dd className="font-semibold text-gray-700">
              {candidate.salience.toFixed(2)}
            </dd>
          </div>
        </dl>
      </Link>
    </li>
  );
}

const GENERATE_BUTTON_CLASS =
  "inline-flex items-center px-4 py-2 bg-indigo-600 text-white font-medium rounded-md hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 transition-colors disabled:opacity-50 disabled:cursor-not-allowed";

/**
 * Generate button + progress/result panel. Running-ness comes from the polled
 * server status, never from local state, so a reload mid-run still shows it.
 */
function GenerationPanel() {
  const { data } = useGenerationStatus();
  const start = useStartGeneration();
  const run = data?.run ?? null;
  const isRunning = run?.status === "running";
  const alreadyRunning = start.data?.alreadyRunning === true;
  const percent = run?.progress_percent ?? 0;

  return (
    <section aria-label="Candidate generation" className="mb-6">
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={() => start.mutate()}
          disabled={isRunning || start.isPending}
          className={GENERATE_BUTTON_CLASS}
        >
          {isRunning ? "Generating..." : "Generate candidates"}
        </button>
        {alreadyRunning && (
          <p role="status" className="text-sm text-amber-700">
            Generation is already running.
          </p>
        )}
      </div>

      {start.isError && (
        <p role="alert" className="mt-3 text-sm text-red-800">
          {start.error?.message || "Failed to start generation."}
        </p>
      )}

      {isRunning && (
        <div
          role="group"
          aria-label="Candidate generation progress"
          className="mt-3 max-w-xl"
        >
          <p className="text-sm text-gray-600 mb-1">Generating candidates...</p>
          <ProgressBar progress={percent} />
        </div>
      )}

      {run?.status === "completed" && (
        <p role="status" className="mt-3 text-sm text-green-800">
          {run.empty_reason
            ? `Generation finished with no candidates: ${run.empty_reason}`
            : `Generation complete: ${run.candidates_discovered.toLocaleString()} discovered, ${run.pending_total.toLocaleString()} pending.`}
        </p>
      )}

      {run?.status === "failed" && (
        <div
          role="alert"
          className="mt-3 bg-red-50 border border-red-200 rounded-lg p-4"
        >
          <p className="text-red-800 font-medium mb-2">
            Generation failed{run.error ? `: ${run.error}` : "."}
          </p>
          <button
            type="button"
            onClick={() => start.mutate()}
            disabled={start.isPending}
            className="px-4 py-2 bg-red-600 text-white font-medium rounded-md hover:bg-red-700 disabled:opacity-50"
          >
            Retry
          </button>
        </div>
      )}
    </section>
  );
}

function LoadingState() {
  return (
    <div
      role="status"
      aria-label="Loading candidates"
      aria-live="polite"
      aria-busy="true"
      className="space-y-3"
    >
      {Array.from({ length: 6 }, (_, i) => (
        <div
          key={i}
          aria-hidden="true"
          className="bg-white rounded-xl shadow-md border border-gray-100 p-4 animate-pulse"
        >
          <div className="h-5 w-1/3 bg-gray-200 rounded-md mb-3" />
          <div className="h-4 w-1/2 bg-gray-200 rounded-md" />
        </div>
      ))}
      <span className="sr-only">Loading candidates...</span>
    </div>
  );
}

export function CandidatesPage() {
  const [searchParams, setSearchParams] = useSearchParams();

  const triageParam = searchParams.get("triage") ?? "all";
  const triage = VALID_TRIAGE.includes(triageParam) ? triageParam : "all";
  const typeParam = searchParams.get("type") ?? "all";
  const typeHint = VALID_TYPES.includes(typeParam) ? typeParam : "all";
  const sortParam = searchParams.get("sort") ?? "score";
  const sort = VALID_SORT.includes(sortParam) ? sortParam : "score";
  const hideSingleToken = searchParams.get("multi_token") === "true";
  const duplicatesOnly = searchParams.get("duplicates") === "true";

  // Optional fields are only present when set (exactOptionalPropertyTypes).
  const hookParams: Parameters<typeof useCandidatesList>[0] = {
    sort,
    ...(triage !== "all" ? { triage } : {}),
    ...(typeHint !== "all" ? { type_hint: typeHint } : {}),
    ...(hideSingleToken ? { min_token_count: MULTI_TOKEN_MIN } : {}),
    ...(duplicatesOnly ? { possible_duplicate: true } : {}),
  };

  /** Set a URL param, deleting it when it equals its default. */
  const setParam = useCallback(
    (key: string, value: string, defaultValue: string) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        if (value === defaultValue) next.delete(key);
        else next.set(key, value);
        return next;
      });
    },
    [setSearchParams]
  );

  const {
    candidates,
    total,
    isLoading,
    isError,
    error,
    hasNextPage,
    isFetchingNextPage,
    retry,
    loadMoreRef,
  } = useCandidatesList(hookParams);

  useEffect(() => {
    document.title = "Candidates - ChronoVista";
    return () => {
      document.title = "ChronoVista";
    };
  }, []);

  const errorMessage =
    error && typeof error.message === "string" && error.message
      ? error.message
      : "Failed to load candidates.";

  return (
    <>
      <SkipLink targetId={MAIN_CONTENT_ID} label="Skip to content" />
      <main
        id={MAIN_CONTENT_ID}
        tabIndex={-1}
        className="container mx-auto px-4 py-8"
      >
        <TermsExplainer
          terms={LIST_TERMS}
          heading={
            <h1 className="text-3xl font-bold text-gray-900">Candidate Review</h1>
          }
        />

        <GenerationPanel />

        <SummaryPanel />

        <div
          role="group"
          aria-label="Candidate filters"
          className="flex flex-col sm:flex-row sm:flex-wrap sm:items-center gap-3 mb-6"
        >
          <div className="flex items-center gap-2">
            <label htmlFor="candidate-triage" className="text-sm font-medium text-gray-700">
              Triage
            </label>
            <select
              id="candidate-triage"
              value={triage}
              onChange={(e) => setParam("triage", e.target.value, "all")}
              className={SELECT_CLASS}
            >
              {TRIAGE_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>
          <div className="flex items-center gap-2">
            <label htmlFor="candidate-type" className="text-sm font-medium text-gray-700">
              Type
            </label>
            <select
              id="candidate-type"
              value={typeHint}
              onChange={(e) => setParam("type", e.target.value, "all")}
              className={SELECT_CLASS}
            >
              {ENTITY_TYPE_TABS.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>
          </div>
          <div className="flex items-center gap-2">
            <label htmlFor="candidate-sort" className="text-sm font-medium text-gray-700">
              Sort by
            </label>
            <select
              id="candidate-sort"
              value={sort}
              onChange={(e) => setParam("sort", e.target.value, "score")}
              className={SELECT_CLASS}
            >
              {SORT_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>
          <Toggle
            label="Hide single-token names"
            checked={hideSingleToken}
            onClick={() =>
              setParam("multi_token", hideSingleToken ? "false" : "true", "false")
            }
          />
          <Toggle
            label="Possible duplicates only"
            checked={duplicatesOnly}
            onClick={() =>
              setParam("duplicates", duplicatesOnly ? "false" : "true", "false")
            }
          />
        </div>

        {isLoading ? (
          <LoadingState />
        ) : isError && candidates.length === 0 ? (
          <div
            className="bg-red-50 border border-red-200 rounded-lg p-6 text-center"
            role="alert"
          >
            <p className="text-red-800 font-medium mb-3">{errorMessage}</p>
            <button
              type="button"
              onClick={retry}
              className="inline-flex items-center px-4 py-2 bg-red-600 text-white font-medium rounded-md hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2 transition-colors"
            >
              Retry
            </button>
          </div>
        ) : candidates.length === 0 ? (
          <div
            className="bg-white border border-gray-200 rounded-xl p-12 text-center"
            role="status"
            aria-label="No candidates"
          >
            <h2 className="text-xl font-semibold text-gray-900 mb-2">
              No pending candidates
            </h2>
            <p className="text-gray-600">
              The review queue is empty. Use Generate candidates above to
              populate it.
            </p>
          </div>
        ) : (
          <>
            {total !== null && (
              <p className="text-sm text-gray-600 mb-3">
                {total.toLocaleString()} pending candidate
                {total === 1 ? "" : "s"}
              </p>
            )}
            <ul className="space-y-3" aria-label="Pending candidates">
              {candidates.map((c) => (
                <CandidateRow key={c.id} candidate={c} />
              ))}
            </ul>
            {isError && (
              <div
                className="mt-4 bg-red-50 border border-red-200 rounded-lg p-4 text-center"
                role="alert"
              >
                <p className="text-red-800 font-medium mb-2">{errorMessage}</p>
                <button
                  type="button"
                  onClick={retry}
                  className="px-4 py-2 bg-red-600 text-white font-medium rounded-md hover:bg-red-700"
                >
                  Retry
                </button>
              </div>
            )}
            {!isError && <div ref={loadMoreRef} className="h-4" aria-hidden="true" />}
            {isFetchingNextPage && (
              <p className="text-sm text-gray-500 text-center mt-2" role="status">
                Loading more...
              </p>
            )}
            {!hasNextPage && !isError && (
              <p className="text-sm text-gray-500 text-center mt-4">
                All candidates loaded.
              </p>
            )}
          </>
        )}
      </main>
    </>
  );
}
