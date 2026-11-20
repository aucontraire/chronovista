/**
 * NodeTypeLegend — the colour/shape key for the types and kinds actually on screen. Every swatch
 * is paired with its text name, so the key does not rely on colour alone. Entity types are
 * coloured circles; the structural kinds repeat their on-canvas shape (diamond / dashed
 * round-rectangle).
 *
 * With `onToggleKind` the key doubles as a filter: each row is a checkbox (checked = shown).
 * A type present only as an endpoint is disabled, since endpoints are never hidden.
 */

import {
  ENTITY_TYPE_FALLBACK_LABEL,
  ENTITY_TYPE_LABELS,
  GRAPH_STRUCTURAL_COLORS,
  entityTypeGraphColor,
} from "../../constants/entityTypes";
import { isEndpoint, nodeKind } from "./connectionModel";
import type { ConnectionModel } from "./connectionModel";
import { ToggleRow } from "./ToggleRow";

const LIST = "flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-600";
const SWATCH = "inline-block h-3 w-3 border border-slate-700";

interface NodeTypeLegendProps {
  model: ConnectionModel;
  /** Kinds currently hidden (Explore filter). */
  hiddenKinds?: ReadonlySet<string>;
  /** Present → rows become filter checkboxes. */
  onToggleKind?: (kind: string) => void;
}

export function NodeTypeLegend({ model, hiddenKinds, onToggleKind }: NodeTypeLegendProps) {
  const labels = new Map<string, string>();
  const filterable = new Set<string>();
  for (const n of model.nodes) {
    if (n.role === "category" || n.role === "bridge") continue;
    const key = nodeKind(n);
    if (!labels.has(key)) labels.set(key, ENTITY_TYPE_LABELS[key] ?? (key === "" ? ENTITY_TYPE_FALLBACK_LABEL : n.label));
    if (!isEndpoint(n)) filterable.add(key);
  }
  const hasCategory = model.nodes.some((n) => n.role === "category");
  const hasBridge = model.nodes.some((n) => n.role === "bridge");
  if (labels.size === 0 && !hasCategory && !hasBridge) return null;

  const row = (kind: string, swatch: React.ReactNode, text: string, canToggle: boolean) =>
    onToggleKind ? (
      <li key={kind}>
        <ToggleRow
          checked={!hiddenKinds?.has(kind)}
          onChange={() => onToggleKind(kind)}
          disabled={!canToggle}
          className="text-xs"
        >
          {swatch}
          {text}
          {!canToggle && <span className="sr-only"> (endpoint, always shown)</span>}
        </ToggleRow>
      </li>
    ) : (
      <li key={kind} className="flex items-center gap-1">
        {swatch}
        {text}
      </li>
    );

  return (
    <div className="space-y-1">
      {labels.size > 0 && (
        <ul className={LIST} aria-label="Node colour by entity type">
          {[...labels].map(([key, text]) =>
            row(
              key,
              <span
                aria-hidden="true"
                className={`${SWATCH} rounded-full`}
                style={{ backgroundColor: entityTypeGraphColor(key) }}
              />,
              text,
              filterable.has(key),
            ),
          )}
        </ul>
      )}
      {(hasCategory || hasBridge) && (
        <ul className={LIST} aria-label="Other node kinds">
          {hasCategory &&
            row(
              "category",
              <span
                aria-hidden="true"
                className={`${SWATCH} rotate-45 scale-90`}
                style={{ backgroundColor: GRAPH_STRUCTURAL_COLORS.category }}
              />,
              "Shared category",
              true,
            )}
          {hasBridge &&
            row(
              "bridge",
              <span
                aria-hidden="true"
                className={`${SWATCH} rounded-sm border-dashed`}
                style={{ backgroundColor: GRAPH_STRUCTURAL_COLORS.bridge }}
              />,
              "Reference value (not in your library)",
              true,
            )}
        </ul>
      )}
    </div>
  );
}
