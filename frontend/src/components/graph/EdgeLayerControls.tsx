/**
 * EdgeLayerControls — per-layer toggles + legend for Explore mode (Feature 115, FR-006/7/21).
 *
 * Real checkboxes (keyboard-operable, state announced natively and shown by the check mark, not
 * colour). Each row's legend swatch repeats the on-canvas line style (solid / dashed / dotted),
 * so a layer is identifiable without colour as well.
 */

import type { EdgeLayer } from "../../api/graph";
import { ToggleRow } from "./ToggleRow";

export const EDGE_LAYERS: readonly EdgeLayer[] = ["verified", "category", "co_occurrence"];

/** FR-007: verified + category shown, co-occurrence opt-in. */
export const DEFAULT_ENABLED_LAYERS: ReadonlySet<EdgeLayer> = new Set<EdgeLayer>([
  "verified",
  "category",
]);

const COPY: Record<EdgeLayer, { label: string; hint: string; dash: string | undefined; color: string; width: number }> = {
  verified: { label: "Verified relationships", hint: "solid line", dash: undefined, color: "#334155", width: 3.5 },
  category: { label: "Shared categories", hint: "dashed line", dash: "6 4", color: "#334155", width: 1.5 },
  co_occurrence: {
    label: "Co-occurrence hints",
    hint: "dotted, faint line — appear together; not a knowledge-base fact",
    dash: "1.5 3",
    color: "#c026d3",
    width: 1.5,
  },
};

interface EdgeLayerControlsProps {
  enabled: ReadonlySet<EdgeLayer>;
  onToggle: (layer: EdgeLayer) => void;
}

export function EdgeLayerControls({ enabled, onToggle }: EdgeLayerControlsProps) {
  return (
    <fieldset className="space-y-1">
      <legend className="text-sm font-medium text-slate-800">Edge layers</legend>
      {EDGE_LAYERS.map((layer) => {
        const { label, hint, dash, color, width } = COPY[layer];
        return (
          <ToggleRow
            key={layer}
            checked={enabled.has(layer)}
            onChange={() => onToggle(layer)}
            className="text-sm"
          >
            <svg width="28" height="8" aria-hidden="true" focusable="false">
              <line
                x1="0"
                y1="4"
                x2="28"
                y2="4"
                stroke={color}
                strokeWidth={width}
                {...(dash !== undefined ? { strokeDasharray: dash } : {})}
              />
            </svg>
            <span>
              {label} <span className="text-xs text-slate-500">({hint})</span>
            </span>
          </ToggleRow>
        );
      })}
    </fieldset>
  );
}
