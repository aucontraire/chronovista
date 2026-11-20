/**
 * Connection Explorer (Feature 113).
 *
 * Pick two entities and see how — and whether — they connect, as an interactive
 * graph plus an equivalent accessible table. A per-row deep-link from the
 * co-occurring-entities panel prefills both endpoints via `?a=<id>&b=<id>` (FR-023).
 *
 * Result states are deliberately distinct and never conflated (FR-009):
 *  - connected            -> graph + table
 *  - no knowledge-base path -> coverage view (each endpoint's kb_degree)
 *  - graph rebuilding / not loaded -> "not available yet" with the next action
 *  - entity not in the current graph -> older-than-library explanation (FR-003)
 *  - request failure       -> generic error with retry
 */

import { useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { ConnectionGraph } from "../components/graph/ConnectionGraph";
import { ConnectionTable } from "../components/graph/ConnectionTable";
import { EntityPicker } from "../components/graph/EntityPicker";
import { EvidencePanel } from "../components/graph/EvidencePanel";
import { buildConnectionModel, hasKnowledgeBaseConnection } from "../components/graph/connectionModel";
import type { GraphConnection, GraphNode } from "../api/graph";
import { useConnection, useGraphHealth } from "../hooks/useConnection";
import { useEntityDetail } from "../hooks/useEntityDetail";

const TABLE_ID = "connection-table";
const MIN_HOPS = 3;
const MAX_HOPS = 6; // mirror the server cap (/graph/connect max_hops le=6)
const DEFAULT_CATEGORY_SIZE = 500;

function EndpointCoverage({ node, id }: { node: GraphNode; id: string | null }) {
  const { entityDetail } = useEntityDetail(id);
  const externalUrl = entityDetail?.enrichment?.identifiers[0]?.url;
  return (
    <li className="rounded-md border border-slate-200 bg-white p-3 text-sm">
      <p className="font-medium text-slate-800">{node.name}</p>
      <p className="text-slate-600">
        {node.kb_degree === null
          ? "Knowledge-base coverage unknown"
          : `${node.kb_degree} knowledge-base ${node.kb_degree === 1 ? "fact" : "facts"}`}
      </p>
      <p className="mt-1 flex gap-3">
        {externalUrl ? (
          <a
            href={externalUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-indigo-700 hover:underline"
          >
            External record
          </a>
        ) : (
          // FR-012: the gap case is an UN-enriched endpoint — always offer an actionable
          // "look it up" external path (a Wikidata search), not nothing.
          <a
            href={`https://www.wikidata.org/w/index.php?search=${encodeURIComponent(node.name)}`}
            target="_blank"
            rel="noopener noreferrer"
            className="text-indigo-700 hover:underline"
          >
            Look up on Wikidata
          </a>
        )}
        {id && (
          <Link to={`/entities/${id}`} className="text-indigo-700 hover:underline">
            Entity page
          </Link>
        )}
      </p>
    </li>
  );
}

const LOW_KB_DEGREE = 3;

function NoPathView({ connection }: { connection: GraphConnection }) {
  const degrees = [connection.entity_a.kb_degree, connection.entity_b.kb_degree];
  const known = degrees.every((d): d is number => d !== null);
  const sparse = known && Math.min(...(degrees as number[])) < LOW_KB_DEGREE;
  return (
    <div data-testid="no-connection" role="status" className="space-y-3">
      <p className="text-sm text-slate-700">
        {/* "no direct relationship or shared reference-point" — NOT "no knowledge-base path": a
            broad shared category may still be rendered below, and a category IS a knowledge-base
            fact, so the stronger claim would contradict the graph on screen (FR-009). */}
        No direct relationship or shared reference-point was found between these entities within{" "}
        {connection.searched_max_hops} hops.{" "}
        {sparse
          ? "One of them is barely in the knowledge base — likely a coverage or enrichment gap, not a stated non-relationship."
          : `That can mean they are unrelated, or that one is thinly covered by the knowledge base.${
              connection.any_truncated
                ? connection.searched_max_hops < MAX_HOPS
                  ? " The search reached its limit, so a longer path may exist; try a larger reach."
                  : " The search went to the maximum reach, so any remaining path would be longer and more tenuous than this tool follows."
                : ""
            }`}
      </p>
      <ul className="grid gap-2 sm:grid-cols-2" aria-label="Knowledge-base coverage">
        <EndpointCoverage node={connection.entity_a} id={connection.entity_a.entity_id} />
        <EndpointCoverage node={connection.entity_b} id={connection.entity_b.entity_id} />
      </ul>
    </div>
  );
}

function legend() {
  return (
    <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-600" aria-label="Graph legend">
      <li>Solid line: knowledge-base relationship</li>
      <li>Dotted line: shared category</li>
      <li>Dashed curve: co-occurrence overlay (appear together; not a knowledge-base fact)</li>
      <li>Large bordered node: endpoint</li>
      <li>Diamond: category, sized by specificity</li>
    </ul>
  );
}

export function ConnectionExplorerPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const a = searchParams.get("a");
  const b = searchParams.get("b");
  const [names, setNames] = useState<Record<string, string>>({});
  const [maxHops, setMaxHops] = useState(MIN_HOPS);
  const [maxCategorySize, setMaxCategorySize] = useState(DEFAULT_CATEGORY_SIZE);
  const tableRef = useRef<HTMLDivElement>(null);

  const { health } = useGraphHealth();
  const knownUnservable = health !== undefined && !health.servable;
  const ready = Boolean(a && b) && a !== b;

  const { connection, isLoading, failure, refetch } = useConnection(
    ready ? a : null,
    ready ? b : null,
    { maxHops, maxCategorySize, enabled: !knownUnservable },
  );

  const model = useMemo(
    () => (connection ? buildConnectionModel(connection) : null),
    [connection],
  );

  function setEndpoint(key: "a" | "b", id: string | null, name?: string) {
    const next = new URLSearchParams(searchParams);
    if (id) next.set(key, id);
    else next.delete(key);
    setSearchParams(next);
    if (id && name) setNames((prev) => ({ ...prev, [id]: name }));
  }

  const nameFor = (id: string | null): string | undefined => {
    if (!id) return undefined;
    if (connection?.entity_a.entity_id === id) return connection.entity_a.name;
    if (connection?.entity_b.entity_id === id) return connection.entity_b.name;
    return names[id];
  };

  const hasKb = model ? hasKnowledgeBaseConnection(model) : false;
  const unavailable = knownUnservable || failure?.kind === "unavailable";

  return (
    <section
      aria-labelledby="connection-explorer-heading"
      className="mx-auto max-w-5xl space-y-4 px-4 py-6"
    >
      <h1 id="connection-explorer-heading" className="text-xl font-semibold text-slate-900">
        Connection Explorer
      </h1>
      <p className="text-sm text-slate-500">
        Pick two entities to see how — and whether — they connect.
      </p>
      {health?.servable && health.loaded_at && (
        <p className="text-xs text-slate-400" data-testid="graph-as-of">
          Graph as of {new Date(health.loaded_at).toLocaleString()}.
        </p>
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        <EntityPicker
          label="Entity A"
          selectedId={a}
          selectedName={nameFor(a)}
          onSelect={(id, name) => setEndpoint("a", id, name)}
          onClear={() => setEndpoint("a", null)}
        />
        <EntityPicker
          label="Entity B"
          selectedId={b}
          selectedName={nameFor(b)}
          onSelect={(id, name) => setEndpoint("b", id, name)}
          onClear={() => setEndpoint("b", null)}
        />
      </div>

      <div className="flex flex-wrap gap-4 text-sm">
        <label className="flex items-center gap-2">
          Reach (hops, {MIN_HOPS}–{MAX_HOPS})
          <input
            type="number"
            min={MIN_HOPS}
            max={MAX_HOPS}
            value={maxHops}
            onChange={(e) =>
              setMaxHops(
                Math.min(MAX_HOPS, Math.max(MIN_HOPS, Number(e.target.value) || MIN_HOPS)),
              )
            }
            className="w-20 rounded border border-slate-300 px-2 py-1"
          />
        </label>
        <label className="flex items-center gap-2">
          Largest category size
          <input
            type="number"
            min={1}
            value={maxCategorySize}
            onChange={(e) =>
              setMaxCategorySize(Math.max(1, Number(e.target.value) || DEFAULT_CATEGORY_SIZE))
            }
            className="w-24 rounded border border-slate-300 px-2 py-1"
          />
        </label>
      </div>

      {!ready && !unavailable && (
        <p role="status" className="text-sm text-slate-600" data-testid="pick-prompt">
          {a && a === b
            ? "Pick two different entities."
            : "Choose both entities to see how they connect."}
        </p>
      )}

      {unavailable && (
        <div
          role="status"
          data-testid="graph-unavailable"
          className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-700"
        >
          <p className="font-medium">The connection graph isn&apos;t available yet.</p>
          <p className="mt-1">
            {health?.status === "loading"
              ? "It is being rebuilt. Try again in a few minutes."
              : "It hasn't been loaded (or can't be reached). Load the graph with the graph reload script, then retry."}
          </p>
          <button
            type="button"
            onClick={refetch}
            className="mt-2 text-indigo-700 hover:underline"
          >
            Retry
          </button>
        </div>
      )}

      {ready && !unavailable && isLoading && (
        <p role="status" className="text-sm text-slate-500" data-testid="connection-loading">
          Finding connections…
        </p>
      )}

      {ready && !unavailable && failure?.kind === "not_in_graph" && (
        <div
          role="status"
          data-testid="not-in-graph"
          className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-700"
        >
          <p className="font-medium">One of these entities isn&apos;t in the current graph.</p>
          <p className="mt-1">
            The graph may be older than your library, so this is not the same as &quot;no
            connection.&quot; Pick a different entity, or rebuild the graph to include it.
          </p>
          {failure.detail && <p className="mt-1 text-slate-500">{failure.detail}</p>}
        </div>
      )}

      {ready && !unavailable && failure?.kind === "error" && (
        <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          Couldn&apos;t load the connection.{" "}
          <button type="button" onClick={refetch} className="underline">
            Retry
          </button>
        </div>
      )}

      {ready && !unavailable && connection && model && (
        <div className="space-y-4">
          {connection.reviewed_verdict?.verdict === "relationship" && (
            <p role="status" className="rounded-md bg-emerald-50 p-3 text-sm text-emerald-900">
              Reviewed: confirmed relationship
              {connection.reviewed_verdict.relation
                ? ` (${connection.reviewed_verdict.relation.replace(/_/g, " ")})`
                : ""}
              .
            </p>
          )}
          {!hasKb && <NoPathView connection={connection} />}
          {model.edges.length > 0 && (
            <>
              <div>
                <ConnectionGraph
                  model={model}
                  tableId={TABLE_ID}
                  summary={`Graph of ${model.edges.length} relationships between ${connection.entity_a.name} and ${connection.entity_b.name}. The table below lists the same relationships.`}
                />
                {legend()}
                <button
                  type="button"
                  onClick={() => tableRef.current?.focus()}
                  className="mt-2 text-sm text-indigo-700 hover:underline"
                >
                  Skip to table
                </button>
              </div>
              <div id={TABLE_ID}>
                <ConnectionTable ref={tableRef} model={model} />
              </div>
              {hasKb && connection.any_truncated && (
                <p className="text-xs text-slate-500">
                  The knowledge-base search reached its {connection.searched_max_hops}-hop
                  limit; a longer path may exist.
                </p>
              )}
            </>
          )}
          {/* Sibling of the edges block so it also renders in the gap case (no KB edge). */}
          {connection.entity_a.entity_id && connection.entity_b.entity_id && (
            <EvidencePanel
              entityAId={connection.entity_a.entity_id}
              entityBId={connection.entity_b.entity_id}
            />
          )}
        </div>
      )}
    </section>
  );
}
