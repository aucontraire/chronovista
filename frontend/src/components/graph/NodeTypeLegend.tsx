/**
 * NodeTypeLegend — the colour/shape key for the types and kinds actually on screen. Every swatch
 * is paired with its text name, so the key does not rely on colour alone. Entity types are
 * coloured circles; the structural kinds repeat their on-canvas shape (diamond / dashed
 * round-rectangle).
 */

import {
  ENTITY_TYPE_FALLBACK_LABEL,
  ENTITY_TYPE_LABELS,
  GRAPH_STRUCTURAL_COLORS,
  entityTypeGraphColor,
} from "../../constants/entityTypes";
import type { ConnectionModel } from "./connectionModel";

const LIST = "flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-600";
const SWATCH = "inline-block h-3 w-3 border border-slate-700";

export function NodeTypeLegend({ model }: { model: ConnectionModel }) {
  const labels = new Map<string, string>();
  for (const n of model.nodes) {
    if (n.role !== "entity" && !n.role.startsWith("endpoint")) continue;
    const key = n.label.toLowerCase();
    if (!labels.has(key)) labels.set(key, ENTITY_TYPE_LABELS[key] ?? (key === "" ? ENTITY_TYPE_FALLBACK_LABEL : n.label));
  }
  const hasCategory = model.nodes.some((n) => n.role === "category");
  const hasBridge = model.nodes.some((n) => n.role === "bridge");
  if (labels.size === 0 && !hasCategory && !hasBridge) return null;
  return (
    <div className="space-y-1">
      {labels.size > 0 && (
        <ul className={LIST} aria-label="Node colour by entity type">
          {[...labels].map(([key, text]) => (
            <li key={key} className="flex items-center gap-1">
              <span
                aria-hidden="true"
                className={`${SWATCH} rounded-full`}
                style={{ backgroundColor: entityTypeGraphColor(key) }}
              />
              {text}
            </li>
          ))}
        </ul>
      )}
      {(hasCategory || hasBridge) && (
        <ul className={LIST} aria-label="Other node kinds">
          {hasCategory && (
            <li className="flex items-center gap-1">
              <span
                aria-hidden="true"
                className={`${SWATCH} rotate-45 scale-90`}
                style={{ backgroundColor: GRAPH_STRUCTURAL_COLORS.category }}
              />
              Shared category
            </li>
          )}
          {hasBridge && (
            <li className="flex items-center gap-1">
              <span
                aria-hidden="true"
                className={`${SWATCH} rounded-sm border-dashed`}
                style={{ backgroundColor: GRAPH_STRUCTURAL_COLORS.bridge }}
              />
              Reference value (not in your library)
            </li>
          )}
        </ul>
      )}
    </div>
  );
}
