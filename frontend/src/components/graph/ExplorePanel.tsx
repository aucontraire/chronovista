/**
 * ExplorePanel — Explore mode body (Feature 115): the neighborhood of the selected
 * entities, rendered through the shared long-lived {@link ConnectionGraph}.
 *
 * Seeds are the current pair (or single entity) as a union (FR-009). A changed or failed
 * request never discards the view already on screen (FR-022): the hook keeps previous data
 * and the error banner is non-blocking.
 */

import { useEffect, useMemo, useRef, useState } from "react";

import type { EdgeLayer } from "../../api/graph";
import { useExpansions, useNeighborhood } from "../../hooks/useNeighborhood";
import { ConnectionGraph } from "./ConnectionGraph";
import { ConnectionTable } from "./ConnectionTable";
import { NodeTypeLegend } from "./NodeTypeLegend";
import { MaximizeOverlay } from "./MaximizeOverlay";
import { DEFAULT_ENABLED_LAYERS, EDGE_LAYERS, EdgeLayerControls } from "./EdgeLayerControls";
import {
  NO_FILTER,
  buildSubgraphModel,
  computeHiddenIds,
  mergeExpansions,
  withoutHidden,
} from "./connectionModel";
import { RelationshipFilter } from "./RelationshipFilter";

const TABLE_ID = "explore-table";
/** FR-008: total node ceiling for accumulated expansion; also sent to the server. */
export const NODE_CEILING = 250;

interface ExplorePanelProps {
  seeds: string[];
  maxCategorySize?: number | undefined;
  /** Skip the request when the graph is known unservable. */
  enabled?: boolean | undefined;
}

export function ExplorePanel({ seeds, maxCategorySize, enabled = true }: ExplorePanelProps) {
  // Toggling a layer re-queries with the new `edge_types`. The graph is updated in place
  // (incremental mode pins surviving nodes), so the view is not reset (FR-020), and
  // co-occurrence is not fetched until enabled (FR-007).
  const [layers, setLayers] = useState<ReadonlySet<EdgeLayer>>(DEFAULT_ENABLED_LAYERS);
  const edgeTypes = EDGE_LAYERS.filter((l) => layers.has(l));
  const noLayers = edgeTypes.length === 0;
  const queryOptions = {
    edgeTypes,
    maxCategorySize,
    ceiling: NODE_CEILING,
    // An empty `edge_types` means "server default", not "nothing": never send it.
    enabled: enabled && !noLayers,
  };
  const {
    subgraph: base,
    isLoading,
    failure,
    refetch,
  } = useNeighborhood(seeds, queryOptions);

  // Expanded entities accumulate client-side, scoped to the current seeds. Each one is a
  // neighborhood query (so it honours the enabled layers) merged into the base view.
  const seedKey = [...seeds].sort().join("|");
  const [expansion, setExpansion] = useState<{ seedKey: string; ids: string[] }>({
    seedKey,
    ids: [],
  });
  const expandedIds = expansion.seedKey === seedKey ? expansion.ids : [];
  const expansions = useExpansions(expandedIds, queryOptions);
  const merged = useMemo(
    () => (base ? mergeExpansions(base, expansions.results, NODE_CEILING) : null),
    [base, expansions.results],
  );
  const subgraph = merged?.subgraph;
  const atCeiling = merged?.atCeiling ?? false;
  const expandedSet = useMemo(() => new Set(expandedIds), [expandedIds]);

  // The single expand handler, shared by canvas double-click and the table's Expand buttons.
  function expandNode(entityId: string) {
    if (atCeiling || expandedSet.has(entityId)) return;
    setExpansion({ seedKey, ids: [...expandedIds, entityId] });
  }

  function toggleLayer(layer: EdgeLayer) {
    setLayers((prev) => {
      const next = new Set(prev);
      if (next.has(layer)) next.delete(layer);
      else next.add(layer);
      return next;
    });
  }
  const tableRef = useRef<HTMLDivElement>(null);
  const model = useMemo(() => (subgraph ? buildSubgraphModel(subgraph) : null), [subgraph]);

  // Focus filters. One computation decides what is hidden; the canvas hides exactly those ids in
  // place, and the table is built from the model minus the same ids — one model, two views.
  const [hiddenKinds, setHiddenKinds] = useState<ReadonlySet<string>>(NO_FILTER.hiddenNodeKinds);
  const [hiddenRels, setHiddenRels] = useState<ReadonlySet<string>>(NO_FILTER.hiddenRelationships);
  const hiddenIds = useMemo(
    () =>
      model
        ? computeHiddenIds(model, { hiddenNodeKinds: hiddenKinds, hiddenRelationships: hiddenRels })
        : new Set<string>(),
    [model, hiddenKinds, hiddenRels],
  );
  const visibleModel = useMemo(() => (model ? withoutHidden(model, hiddenIds) : null), [model, hiddenIds]);
  const hiddenNodeCount = model && visibleModel ? model.nodes.length - visibleModel.nodes.length : 0;

  function toggleIn(set: ReadonlySet<string>, key: string): ReadonlySet<string> {
    const next = new Set(set);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    return next;
  }
  function setAllRelationships(hide: boolean) {
    setHiddenRels(hide ? new Set((model?.edges ?? []).map((e) => e.edgeType)) : new Set());
  }

  const relationshipFilter = model && (
    <RelationshipFilter
      model={model}
      hidden={hiddenRels}
      onToggle={(edgeType) => setHiddenRels((prev) => toggleIn(prev, edgeType))}
      onSetAll={setAllRelationships}
    />
  );

  // Maximize (FR-017): same graph instance, same cap/ceiling/layers (FR-019); only the size changes.
  const graphVisible = !noLayers && model !== null;
  const [maximized, setMaximized] = useState(false);
  const [fitToken, setFitToken] = useState(0);
  const maximizeButtonRef = useRef<HTMLButtonElement>(null);
  const returnFocusRef = useRef<HTMLElement | null>(null);
  useEffect(() => {
    // The dialog cannot outlive its graph (e.g. the last layer was switched off).
    if (!graphVisible) setMaximized(false);
  }, [graphVisible]);

  function enterMaximize() {
    returnFocusRef.current = maximizeButtonRef.current;
    setMaximized(true);
  }
  function exitMaximize() {
    returnFocusRef.current = maximizeButtonRef.current;
    setMaximized(false);
  }
  function viewTable() {
    // The table is page content, so reaching it leaves the dialog and lands focus on it.
    returnFocusRef.current = tableRef.current;
    setMaximized(false);
  }

  const countText = subgraph
    ? subgraph.total_available > subgraph.nodes.length
      ? `Showing ${subgraph.nodes.length} of ${subgraph.total_available} nodes`
      : `Showing all ${subgraph.nodes.length} ${subgraph.nodes.length === 1 ? "node" : "nodes"}`
    : "";

  if (seeds.length === 0) {
    return (
      <p role="status" className="text-sm text-slate-600" data-testid="explore-pick-prompt">
        Choose an entity to explore its neighborhood.
      </p>
    );
  }

  return (
    <div className="space-y-3" data-testid="explore-panel">
      {/* While maximized the same controls live in the floating toolbar instead (FR-018). */}
      {!maximized && <EdgeLayerControls enabled={layers} onToggle={toggleLayer} />}
      {noLayers && (
        <p role="status" data-testid="explore-no-layers" className="text-sm text-slate-600">
          Turn on at least one edge layer to see the neighborhood.
        </p>
      )}
      {isLoading && (
        <p role="status" className="text-sm text-slate-500" data-testid="explore-loading">
          Loading the neighborhood…
        </p>
      )}

      {failure?.kind === "unavailable" && (
        <p role="status" data-testid="explore-unavailable" className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700">
          The connection graph isn&apos;t available yet.{" "}
          <button type="button" onClick={refetch} className="text-indigo-700 hover:underline">
            Retry
          </button>
        </p>
      )}
      {failure?.kind === "not_in_graph" && (
        <p role="status" data-testid="explore-not-in-graph" className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700">
          An entity here isn&apos;t in the current graph — it may be newer than the graph, which is
          not the same as having no neighbors.
        </p>
      )}
      {failure?.kind === "error" && (
        <p role="alert" data-testid="explore-error" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
          Couldn&apos;t load the neighborhood.{" "}
          <button type="button" onClick={refetch} className="underline">
            Retry
          </button>
        </p>
      )}

      {!noLayers && subgraph && model && (
        <>
          <p className="text-sm text-slate-700" data-testid="explore-count">
            {countText}
            {hiddenNodeCount > 0 && ` (${hiddenNodeCount} hidden by filters)`}
          </p>
          {expansions.pending > 0 && (
            <p role="status" className="text-sm text-slate-500" data-testid="explore-expanding">
              Expanding…
            </p>
          )}
          {expansions.failed > 0 && (
            <p role="alert" data-testid="explore-expand-error" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
              Couldn&apos;t expand {expansions.failed === 1 ? "a node" : `${expansions.failed} nodes`}.
              The current view is unchanged.
            </p>
          )}
          {atCeiling && (
            <p role="status" data-testid="explore-ceiling" className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
              Reached the {NODE_CEILING}-node ceiling, so further expansion is unavailable. Nothing
              already shown was removed
              {merged && merged.refused > 0 ? `; ${merged.refused} expansion${merged.refused === 1 ? " was" : "s were"} not added` : ""}.
            </p>
          )}
          <NodeTypeLegend
            model={model}
            hiddenKinds={hiddenKinds}
            onToggleKind={(kind) => setHiddenKinds((prev) => toggleIn(prev, kind))}
          />
          <button
            ref={maximizeButtonRef}
            type="button"
            onClick={enterMaximize}
            className="text-sm text-indigo-700 hover:underline"
          >
            Maximize graph
          </button>
          <MaximizeOverlay
            maximized={maximized}
            onExit={exitMaximize}
            label="Neighborhood graph, maximized"
            returnFocusRef={returnFocusRef}
            toolbar={
              <div
                role="toolbar"
                aria-label="Graph controls"
                className="absolute right-4 top-4 z-10 max-h-[calc(100vh-2rem)] w-80 max-w-[calc(100vw-2rem)] space-y-2 overflow-y-auto rounded-lg border border-slate-300 bg-white/95 p-3 shadow-lg"
              >
                <p className="text-xs text-slate-600" data-testid="maximized-count">
                  {countText}
                </p>
                {/* Actions first: the panel scrolls when many types are listed. */}
                <div className="flex flex-wrap gap-2 text-sm">
                  <button type="button" onClick={() => setFitToken((n) => n + 1)} className="rounded border border-slate-300 px-2 py-1">
                    Fit to view
                  </button>
                  <button type="button" onClick={viewTable} className="rounded border border-slate-300 px-2 py-1">
                    View table
                  </button>
                  <button
                    type="button"
                    onClick={exitMaximize}
                    className="rounded border border-slate-300 px-2 py-1"
                  >
                    Exit full screen
                  </button>
                </div>
                <EdgeLayerControls enabled={layers} onToggle={toggleLayer} />
                <NodeTypeLegend
                  model={model}
                  hiddenKinds={hiddenKinds}
                  onToggleKind={(kind) => setHiddenKinds((prev) => toggleIn(prev, kind))}
                />
                {relationshipFilter}
              </div>
            }
          >
            <ConnectionGraph
              model={model}
              tableId={TABLE_ID}
              updateMode="incremental"
              onNodeExpand={expandNode}
              maximized={maximized}
              fitToken={fitToken}
              maxRenderedNodes={NODE_CEILING}
              hiddenIds={hiddenIds}
              summary={`Neighborhood graph of ${visibleModel?.nodes.length ?? model.nodes.length} entities and ${visibleModel?.edges.length ?? model.edges.length} relationships. The table below lists the same relationships.`}
            />
          </MaximizeOverlay>
          <button
            type="button"
            onClick={() => tableRef.current?.focus()}
            className="text-sm text-indigo-700 hover:underline"
          >
            Skip to table
          </button>
          {/* Rendered in one slot at a time (this one, or the toolbar while maximized); both read
              the same state above, so a toggle in either shows in the other. */}
          {!maximized && relationshipFilter}
          <div id={TABLE_ID}>
            <ConnectionTable
              ref={tableRef}
              model={visibleModel ?? model}
              caption="Relationships in the neighborhood, one row per edge, with its trust layer"
              onExpand={expandNode}
              expandedIds={expandedSet}
              canExpand={!atCeiling}
            />
          </div>
        </>
      )}
    </div>
  );
}
