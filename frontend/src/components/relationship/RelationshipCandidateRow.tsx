/**
 * One read-only novel-relationship candidate row (Feature 107).
 *
 * The row asserts only that the pair is a "candidate". The typed-eligible badge
 * is a trust signal, never a filter.
 */

import { Link } from "react-router-dom";

import type { RelationshipCandidate } from "../../hooks/useRelationshipCandidates";

const LINK_CLASS =
  "font-semibold text-indigo-700 hover:underline focus:outline-none focus:ring-2 focus:ring-indigo-500 rounded";

export function RelationshipCandidateRow({
  candidate,
}: {
  candidate: RelationshipCandidate;
}) {
  const { entity_a: a, entity_b: b } = candidate;
  const detail = candidate.kb_corroboration_detail.join(", ");
  // Target /videos explicitly: the root index route redirects and drops the query.
  // No min_evidence: the queue's title+description channel is not a selectable scope.
  const togetherParams = new URLSearchParams();
  togetherParams.append("entity_id", a.id);
  togetherParams.append("entity_id", b.id);
  const togetherHref = `/videos?${togetherParams.toString()}`;
  return (
    <li className="bg-white rounded-xl shadow-md border border-gray-100 p-4">
      <div className="flex flex-wrap items-center gap-2 mb-2">
        <h3 className="text-base text-gray-900">
          <Link to={`/entities/${a.id}`} className={LINK_CLASS}>
            {a.canonical_name}
          </Link>
          <span aria-hidden="true" className="mx-2 text-gray-400">
            &harr;
          </span>
          <span className="sr-only"> and </span>
          <Link to={`/entities/${b.id}`} className={LINK_CLASS}>
            {b.canonical_name}
          </Link>
        </h3>
        <span className="text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-700">
          candidate
        </span>
        {candidate.both_typed_eligible && (
          <span
            className="text-xs px-2 py-0.5 rounded-full bg-green-50 text-green-800"
            title="Both entities have a type with measured precision"
          >
            typed-eligible
          </span>
        )}
        <span
          className="text-xs px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700"
          title={detail || "No knowledge-base corroboration"}
        >
          {`corroboration ${candidate.kb_corroboration_count}`}
        </span>
      </div>
      <dl className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-gray-500">
        <div className="flex gap-1">
          <dt>Shared videos</dt>
          <dd className="font-semibold text-gray-700">
            {candidate.shared_video_count.toLocaleString()}
          </dd>
        </div>
        <div className="flex gap-1">
          <dt>Lift</dt>
          <dd className="font-semibold text-gray-700">
            {candidate.lift.toFixed(2)}
          </dd>
        </div>
        <div className="flex gap-1">
          <dt>Video universe</dt>
          <dd className="font-semibold text-gray-700">
            {candidate.channel_video_universe.toLocaleString()}
          </dd>
        </div>
      </dl>
      {/* Count-free on purpose: shared_video_count is the generator's number and can
          differ from the association-inclusive /videos total. */}
      <Link
        to={togetherHref}
        aria-label={`View videos where ${a.canonical_name} and ${b.canonical_name} appear together`}
        className="mt-2 inline-block text-xs text-indigo-700 hover:underline focus:outline-none focus:ring-2 focus:ring-indigo-500 rounded"
      >
        View shared videos &rarr;
      </Link>
    </li>
  );
}
