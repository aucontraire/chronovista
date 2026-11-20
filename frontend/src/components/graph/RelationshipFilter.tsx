/**
 * RelationshipFilter — hide/show whole relationship types (every "educated at" edge, …) in BOTH
 * the graph and the table. It lists the types present in the full model with their edge counts;
 * checked = shown. This composes with the coarse edge-layer toggles: a layer decides which edges
 * are fetched at all, this decides which fetched edges are displayed, so an edge shows only when
 * both allow it.
 */

import type { ConnectionModel } from "./connectionModel";
import { ToggleRow } from "./ToggleRow";

interface RelationshipFilterProps {
  model: ConnectionModel;
  hidden: ReadonlySet<string>;
  onToggle: (edgeType: string) => void;
  /** Hide every type (`true`) or show every type (`false`). */
  onSetAll: (hide: boolean) => void;
}

export function RelationshipFilter({ model, hidden, onToggle, onSetAll }: RelationshipFilterProps) {
  const types = new Map<string, { label: string; count: number }>();
  for (const e of model.edges) {
    const entry = types.get(e.edgeType);
    if (entry) entry.count += 1;
    else types.set(e.edgeType, { label: e.relationship, count: 1 });
  }
  if (types.size === 0) return null;
  const button = "rounded border border-slate-300 px-2 py-0.5 text-xs text-slate-700 hover:bg-slate-50";
  return (
    <fieldset className="space-y-1" data-testid="relationship-filter">
      <legend className="text-sm font-medium text-slate-800">Relationship types</legend>
      <div className="flex gap-2">
        <button type="button" className={button} onClick={() => onSetAll(false)}>
          Show all
        </button>
        <button type="button" className={button} onClick={() => onSetAll(true)}>
          Hide all
        </button>
      </div>
      <ul className="flex flex-wrap gap-x-4 gap-y-1">
        {[...types].map(([edgeType, { label, count }]) => (
          <li key={edgeType}>
            <ToggleRow checked={!hidden.has(edgeType)} onChange={() => onToggle(edgeType)} className="text-xs">
              {label} <span className="text-slate-500">({count})</span>
            </ToggleRow>
          </li>
        ))}
      </ul>
    </fieldset>
  );
}
