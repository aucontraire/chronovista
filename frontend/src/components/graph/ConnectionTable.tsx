/**
 * ConnectionTable — the accessible edge-list equivalent of the graph (Feature 113).
 *
 * Built from the same {@link ConnectionModel} as `ConnectionGraph`, so the two
 * views always show the same nodes and edges (FR-005). This is the primary view
 * for assistive technology and the automatically testable one (FR-026, SC-004).
 */

import { forwardRef } from "react";

import { KIND_LABELS, LAYER_LABELS } from "./connectionModel";
import type { ConnectionModel, ModelNode } from "./connectionModel";

interface ConnectionTableProps {
  model: ConnectionModel;
  /** Screen-reader caption; Explore overrides Connect's two-entity wording. */
  caption?: string;
  /**
   * Explore only (FR-021): the off-canvas, keyboard-operable equivalent of double-clicking a node.
   * Rows offer "Expand" for each neighbor endpoint that has an entity id.
   */
  onExpand?: (entityId: string) => void;
  /** Entities already expanded; their button is disabled. */
  expandedIds?: ReadonlySet<string>;
  /** False once the node ceiling is reached (FR-008). */
  canExpand?: boolean;
}

function NodeCell({ node }: { node: ModelNode | undefined }) {
  if (!node) return <>Unknown</>;
  const marker =
    node.role === "endpoint-a"
      ? " (endpoint A)"
      : node.role === "endpoint-b"
        ? " (endpoint B)"
        : node.role === "category"
          ? " (category)"
          : "";
  return (
    <>
      <span className={node.role.startsWith("endpoint") ? "font-semibold" : ""}>
        {node.name}
      </span>
      {marker && <span className="text-slate-500">{marker}</span>}
    </>
  );
}

export const ConnectionTable = forwardRef<HTMLDivElement, ConnectionTableProps>(
  function ConnectionTable(
    {
      model,
      caption = "Connections between the two entities, one row per relationship",
      onExpand,
      expandedIds,
      canExpand = true,
    },
    ref,
  ) {
    const byId = new Map(model.nodes.map((n) => [n.id, n]));
    return (
      <div
        ref={ref}
        tabIndex={-1}
        className="overflow-x-auto rounded-lg border border-slate-200 bg-white"
      >
        <table className="min-w-full text-left text-sm">
          <caption className="sr-only">{caption}</caption>
          <thead className="bg-slate-50 text-slate-600">
            <tr>
              <th scope="col" className="px-3 py-2 font-medium">Source</th>
              <th scope="col" className="px-3 py-2 font-medium">Relationship</th>
              <th scope="col" className="px-3 py-2 font-medium">Target</th>
              <th scope="col" className="px-3 py-2 font-medium">Kind</th>
              {onExpand && <th scope="col" className="px-3 py-2 font-medium">Expand</th>}
            </tr>
          </thead>
          <tbody>
            {model.edges.map((edge) => (
              <tr key={edge.id} className="border-t border-slate-100">
                <td className="px-3 py-2"><NodeCell node={byId.get(edge.source)} /></td>
                <td className="px-3 py-2">{edge.relationship}</td>
                <td className="px-3 py-2"><NodeCell node={byId.get(edge.target)} /></td>
                <td className="px-3 py-2 text-slate-600">
                  {edge.layer !== undefined ? (
                    LAYER_LABELS[edge.layer]
                  ) : (
                    <>
                      {KIND_LABELS[edge.kind]}
                      {edge.overlay && " — co-occurrence, not a knowledge-base fact"}
                    </>
                  )}
                </td>
                {onExpand && (
                  <td className="px-3 py-2">
                    <div className="flex flex-wrap gap-2">
                      {[byId.get(edge.source), byId.get(edge.target)].map((n) =>
                        // Seeds already show their neighborhood; bridge nodes have no entity id.
                        n?.entityId && !n.role.startsWith("endpoint") ? (
                          <button
                            key={n.id}
                            type="button"
                            onClick={() => onExpand(n.entityId as string)}
                            disabled={!canExpand || expandedIds?.has(n.entityId) === true}
                            className="rounded border border-slate-300 px-2 py-0.5 text-xs text-indigo-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:text-slate-400"
                          >
                            Expand <span className="sr-only">{n.name}</span>
                            <span aria-hidden="true">{n.name}</span>
                          </button>
                        ) : null,
                      )}
                    </div>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  },
);
