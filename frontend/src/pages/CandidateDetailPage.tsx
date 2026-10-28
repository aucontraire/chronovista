/**
 * CandidateDetailPage — one candidate with signals and provenance (Feature 097).
 */

import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import {
  TermsExplainer,
  triageLabel,
  type TermKey,
} from "../components/candidates/TermsExplainer";
import {
  LinkConsequenceInfo,
  TagInspectLink,
} from "../components/entity/TagInspectControls";
import { SkipLink } from "../components/SkipLink";
import {
  useApproveCandidate,
  useCandidateDetail,
  useCandidateTagFootprint,
  useRejectCandidate,
} from "../hooks/useCandidates";
import type { CandidateVerdictResponse } from "../api/candidates";
import { linkEntityTag } from "../api/candidates";
import { invalidateAfterTagLink } from "../hooks/useEntityTags";
import { useEntityDetail } from "../hooks/useEntityDetail";

/** Stable ID used by SkipLink and main content container. */
const MAIN_CONTENT_ID = "candidate-detail-main-content";

const DETAIL_TERMS: readonly TermKey[] = [
  "worth_review",
  "likely_eliminable",
  "grounds_nowhere",
  "score",
  "corroboration",
  "salience",
  "dangling_edges",
  "token_count",
  "possible_duplicate",
];

/**
 * Cap on seed entities resolved to names. Each seed is one
 * GET /entities/{id} request (N+1) because no batch entities-by-ids endpoint
 * exists; seeds beyond the cap are summarised as a count.
 */
const MAX_RESOLVED_SEEDS = 10;

function readStringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((v): v is string => typeof v === "string")
    : [];
}

function SeedLink({ seedId }: { seedId: string }) {
  const { entityDetail, isLoading } = useEntityDetail(seedId);
  const name = entityDetail?.canonical_name ?? (isLoading ? "Loading..." : seedId);
  return (
    <Link to={`/entities/${seedId}`} className="text-indigo-700 hover:underline">
      {name}
    </Link>
  );
}

const VERDICT_MESSAGES: Record<string, string> = {
  approved: "Entity created.",
  superseded: "Already existed \u2014 linked, not duplicated.",
  rejected: "Candidate rejected.",
  failed: "Already decided.",
};

function verdictErrorMessage(error: unknown): string {
  const status = (error as { status?: number } | null)?.status;
  if (status === 404) return "This candidate no longer exists.";
  if (status === 409)
    return "A canonical identity must be established first.";
  return "The verdict could not be recorded. Please try again.";
}

export function CandidateDetailPage() {
  const { candidateId } = useParams<{ candidateId: string }>();
  const { data: candidate, isLoading, isError, error, refetch } =
    useCandidateDetail(candidateId);

  const { data: footprint } = useCandidateTagFootprint(candidateId);
  const footprintMatches = footprint?.matches ?? [];

  const queryClient = useQueryClient();
  const [linkOnApprove, setLinkOnApprove] = useState(false);
  const [linkFailed, setLinkFailed] = useState(false);
  // Opt-in is offered only for exactly one unowned match; anything else is ambiguous or unavailable.
  const safeMatch =
    footprintMatches.length === 1 && footprintMatches[0]?.owned_by_entity_id === null
      ? footprintMatches[0]
      : undefined;
  const approve = useApproveCandidate();
  const reject = useRejectCandidate();
  const [verdict, setVerdict] = useState<CandidateVerdictResponse | null>(null);
  const [verdictError, setVerdictError] = useState<unknown>(null);
  const outcomeRef = useRef<HTMLParagraphElement>(null);
  const isPending = approve.isPending || reject.isPending;
  const identityMissing =
    (verdictError as { status?: number } | null)?.status === 409;
  const hasOutcome = verdict !== null || verdictError !== null;

  const submit = (action: typeof approve) => {
    if (!candidateId || isPending) return;
    setVerdict(null);
    setVerdictError(null);
    setLinkFailed(false);
    const wantsLink = action === approve && linkOnApprove && safeMatch !== undefined;
    action.mutate(
      { candidateId },
      {
        onSuccess: (result) => {
          setVerdict(result);
          // Only a freshly created entity can be linked; superseded/failed skip silently.
          if (wantsLink && result.outcome === "approved" && result.created_entity_id) {
            const entityId = result.created_entity_id;
            void linkEntityTag(entityId, {
              normalized_form: safeMatch.normalized_form,
              entity_type: candidate?.type_hint ?? "",
            })
              .then(() => invalidateAfterTagLink(queryClient, entityId))
              .catch(() => setLinkFailed(true));
          }
        },
        onError: (err) => setVerdictError(err),
      }
    );
  };

  // Keep keyboard focus on a stable element after the verdict: the acting
  // button is disabled/removed, which would otherwise drop focus to <body>.
  useEffect(() => {
    if (hasOutcome) outcomeRef.current?.focus();
  }, [hasOutcome, verdict, verdictError]);

  useEffect(() => {
    document.title = "Candidate Detail - ChronoVista";
    return () => {
      document.title = "ChronoVista";
    };
  }, []);

  const seedIds = readStringArray(candidate?.provenance["seed_entity_ids"]);
  const relations = readStringArray(candidate?.provenance["relations"]);
  const notFound = (error as { status?: number } | null)?.status === 404;

  return (
    <>
      <SkipLink targetId={MAIN_CONTENT_ID} label="Skip to content" />
      <main
        id={MAIN_CONTENT_ID}
        tabIndex={-1}
        className="container mx-auto px-4 py-8"
      >
        <nav aria-label="Breadcrumb" className="mb-4 text-sm">
          <Link to="/candidates" className="text-indigo-700 hover:underline">
            Back to candidates
          </Link>
        </nav>

        {isLoading ? (
          <div
            role="status"
            aria-busy="true"
            aria-label="Loading candidate"
            className="animate-pulse"
          >
            <div className="h-8 w-1/3 bg-gray-200 rounded-md mb-4" />
            <div className="h-4 w-1/2 bg-gray-200 rounded-md" />
            <span className="sr-only">Loading candidate...</span>
          </div>
        ) : isError || !candidate ? (
          <div
            className="bg-red-50 border border-red-200 rounded-lg p-6 text-center"
            role="alert"
          >
            <p className="text-red-800 font-medium mb-3">
              {notFound ? "Candidate not found." : "Failed to load candidate."}
            </p>
            {!notFound && (
              <button
                type="button"
                onClick={() => void refetch()}
                className="px-4 py-2 bg-red-600 text-white font-medium rounded-md hover:bg-red-700"
              >
                Retry
              </button>
            )}
          </div>
        ) : (
          <>
            <TermsExplainer
              terms={DETAIL_TERMS}
              heading={
                <h1 className="text-3xl font-bold text-gray-900">
                  {candidate.label}
                </h1>
              }
            />
            <div className="flex flex-wrap items-center gap-3 mb-2 -mt-4">
              <span className="text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-700">
                {candidate.type_hint}
              </span>
              <span className="text-xs px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700">
                {triageLabel(candidate.triage)}
              </span>
            </div>

            <div className="flex flex-wrap items-center gap-3 mb-6">
              <a
                href={`https://www.wikidata.org/wiki/${candidate.wikidata_qid}`}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center px-3 py-1 rounded-full bg-indigo-50 text-indigo-700 text-sm hover:bg-indigo-100"
              >
                View on Wikidata
              </a>
              {candidate.possible_duplicate_of_id && (
                <Link
                  to={`/entities/${candidate.possible_duplicate_of_id}`}
                  className="inline-flex items-center px-3 py-1 rounded-full bg-amber-50 text-amber-800 text-sm hover:bg-amber-100"
                >
                  Possible duplicate of an existing entity
                </Link>
              )}
            </div>

            <section
              aria-labelledby="verdict-heading"
              className="bg-white rounded-xl shadow-md border border-gray-100 p-5 mb-6"
            >
              <h2 id="verdict-heading" className="text-lg font-semibold text-gray-900 mb-3">
                Review
              </h2>
              {candidate.review_status === "pending" && verdict === null && !identityMissing && (
                <div className="flex flex-wrap gap-3 mb-3">
                  <button
                    type="button"
                    disabled={isPending}
                    onClick={() => submit(approve)}
                    className="px-4 py-2 bg-green-700 text-white font-medium rounded-md hover:bg-green-800 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {approve.isPending ? "Approving..." : "Approve"}
                  </button>
                  <button
                    type="button"
                    disabled={isPending}
                    onClick={() => submit(reject)}
                    className="px-4 py-2 bg-gray-700 text-white font-medium rounded-md hover:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {reject.isPending ? "Rejecting..." : "Reject"}
                  </button>
                </div>
              )}
              {candidate.review_status === "pending" &&
                verdict === null &&
                !identityMissing &&
                safeMatch && (
                  <div className="flex items-center gap-1 mb-3 text-sm text-gray-800">
                    <input
                      id="link-on-approve"
                      type="checkbox"
                      checked={linkOnApprove}
                      disabled={isPending}
                      onChange={(e) => setLinkOnApprove(e.target.checked)}
                      className="h-4 w-4 rounded border-gray-300 focus:ring-2 focus:ring-indigo-500"
                    />
                    <label htmlFor="link-on-approve" className="ml-1">
                      Link this tag when I approve
                    </label>
                    <LinkConsequenceInfo />
                  </div>
                )}
              {candidate.review_status !== "pending" && verdict === null && (
                <p className="text-sm text-gray-700 mb-3">
                  Status: {candidate.review_status}
                </p>
              )}
              <div aria-live="polite" aria-atomic="true">
                {(verdict !== null || verdictError !== null) && (
                  <p
                    ref={outcomeRef}
                    tabIndex={-1}
                    className="text-sm font-medium text-gray-900"
                  >
                    {verdict !== null
                      ? (VERDICT_MESSAGES[verdict.outcome] ?? verdict.outcome)
                      : verdictErrorMessage(verdictError)}
                  </p>
                )}
              </div>
              {candidate.review_status === "pending" &&
                footprintMatches.length > 0 && (
                  <ul className="text-sm text-gray-700 mb-3 space-y-1">
                    {footprintMatches.map((m) => (
                      <li key={m.normalized_form}>
                        {m.would_newly_associate > 0 ? (
                          <>
                            If approved, linking the tag «
                            <TagInspectLink normalizedForm={m.normalized_form} />»
                            would also associate {m.would_newly_associate} more
                            video{m.would_newly_associate === 1 ? "" : "s"}.
                          </>
                        ) : (
                          <>
                            Matches tag «<TagInspectLink normalizedForm={m.normalized_form} />» — its videos
                            already reference this name (they will associate on
                            approval).
                          </>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              {linkFailed && (
                <p role="alert" className="text-sm text-red-700 mb-2">
                  The entity was created, but the tag could not be linked. Link it from the entity page.
                </p>
              )}
              {verdict?.created_entity_id && (
                <Link
                  to={`/entities/${verdict.created_entity_id}`}
                  className="text-sm text-indigo-700 hover:underline"
                >
                  View entity
                </Link>
              )}
            </section>

            <section
              aria-labelledby="corroboration-heading"
              className="bg-white rounded-xl shadow-md border border-gray-100 p-5 mb-6"
            >
              <h2 id="corroboration-heading" className="text-lg font-semibold text-gray-900">
                Corroboration
              </h2>
              <p className="text-2xl font-bold text-gray-900">
                {candidate.corroboration_count}
                <span className="text-sm font-normal text-gray-600 ml-2">
                  distinct seed{candidate.corroboration_count === 1 ? "" : "s"} point here
                </span>
              </p>
            </section>

            <section
              aria-labelledby="signals-heading"
              className="bg-white rounded-xl shadow-md border border-gray-100 p-5 mb-6"
            >
              <h2 id="signals-heading" className="text-lg font-semibold text-gray-900 mb-3">
                Signals
              </h2>
              <dl className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                <div>
                  <dt className="text-gray-500">Score</dt>
                  <dd className="font-semibold">{candidate.score.toFixed(2)}</dd>
                </div>
                <div>
                  <dt className="text-gray-500">Salience</dt>
                  <dd className="font-semibold">{candidate.salience.toFixed(2)}</dd>
                </div>
                <div>
                  <dt className="text-gray-500">Dangling edges</dt>
                  <dd className="font-semibold">{candidate.dangling_edge_count}</dd>
                </div>
                <div>
                  <dt className="text-gray-500">Tokens</dt>
                  <dd className="font-semibold">{candidate.token_count}</dd>
                </div>
              </dl>
            </section>

            <section
              aria-labelledby="provenance-heading"
              className="bg-white rounded-xl shadow-md border border-gray-100 p-5"
            >
              <h2 id="provenance-heading" className="text-lg font-semibold text-gray-900 mb-3">
                Provenance
              </h2>
              {seedIds.length === 0 ? (
                <p className="text-sm text-gray-500">No provenance recorded.</p>
              ) : (
                <>
                  {/*
                    The backend stores `relations` as the distinct set of
                    relation names across all seeds, not one per seed, so a
                    relation cannot be paired with a specific seed.
                  */}
                  <p className="text-sm text-gray-700 mb-3">
                    via{" "}
                    {relations.length > 0
                      ? relations.map((r, i) => (
                          <span key={r}>
                            {i > 0 && ", "}«{r}»
                          </span>
                        ))
                      : "«unknown relation»"}{" "}
                    of:
                  </p>
                  <ul className="list-disc pl-5 text-sm space-y-1">
                    {seedIds.slice(0, MAX_RESOLVED_SEEDS).map((id) => (
                      <li key={id}>
                        <SeedLink seedId={id} />
                      </li>
                    ))}
                  </ul>
                  {seedIds.length > MAX_RESOLVED_SEEDS && (
                    <p className="text-sm text-gray-500 mt-2">
                      and {seedIds.length - MAX_RESOLVED_SEEDS} more seeds
                    </p>
                  )}
                </>
              )}
            </section>
          </>
        )}
      </main>
    </>
  );
}
