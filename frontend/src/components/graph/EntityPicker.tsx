/**
 * EntityPicker — selects one entity BY ID for the Connection Explorer (FR-002).
 *
 * Search results are filtered against the graph: graph-present entities are
 * listed first and selectable; entities missing from the current graph are
 * shown but disabled with an explanation, so a user is not led into a
 * guaranteed dead end.
 */

import { useId, useState } from "react";

import { useEntityDetail } from "../../hooks/useEntityDetail";
import { useEntitySearch } from "../../hooks/useEntitySearch";
import { useGraphPresence } from "../../hooks/useConnection";

interface EntityPickerProps {
  label: string;
  selectedId: string | null;
  /** Display name for the selection, when known (a deep-link only knows the id). */
  selectedName: string | undefined;
  onSelect: (id: string, name: string) => void;
  onClear: () => void;
}

export function EntityPicker({
  label,
  selectedId,
  selectedName,
  onSelect,
  onClear,
}: EntityPickerProps) {
  const inputId = useId();
  const [text, setText] = useState("");
  // A reload or deep link knows only the id: resolve the name instead of showing the raw id.
  const { entityDetail } = useEntityDetail(selectedId && !selectedName ? selectedId : null);
  const { entities, isLoading, isBelowMinChars } = useEntitySearch(text);
  const { present, isLoading: presenceLoading } = useGraphPresence(
    entities.map((e) => e.entity_id),
  );

  const ordered = [...entities].sort(
    (x, y) => Number(present.has(y.entity_id)) - Number(present.has(x.entity_id)),
  );

  if (selectedId) {
    return (
      <div>
        <span className="block text-sm font-medium text-slate-700">{label}</span>
        <div className="mt-1 flex items-center justify-between gap-2 rounded-md border border-slate-300 bg-white px-3 py-2 text-sm">
          <span data-testid="picker-selected">
            {selectedName ?? entityDetail?.canonical_name ?? `Entity ${selectedId.slice(0, 8)}…`}
          </span>
          <button
            type="button"
            onClick={onClear}
            aria-label={`Change ${label}`}
            className="text-indigo-700 hover:underline"
          >
            Change
          </button>
        </div>
      </div>
    );
  }

  return (
    <div>
      <label htmlFor={inputId} className="block text-sm font-medium text-slate-700">
        {label}
      </label>
      <input
        id={inputId}
        type="search"
        value={text}
        onChange={(e) => setText(e.target.value)}
        autoComplete="off"
        placeholder="Search entities (2+ characters)"
        className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-600"
      />
      {!isBelowMinChars && (
        <div className="mt-1" aria-live="polite">
          {isLoading && <p className="text-xs text-slate-500">Searching…</p>}
          {!isLoading && ordered.length === 0 && (
            <p className="text-xs text-slate-500">No matching entities.</p>
          )}
          <ul aria-label={`${label} results`} className="space-y-0.5">
            {ordered.map((entity) => {
              // While presence is loading, don't flash "not in current graph" — treat as
              // present (enabled); the real state settles once the probe resolves (FR-002, MEDIUM
              // from the US1 review).
              const inGraph = presenceLoading || present.has(entity.entity_id);
              return (
                <li key={entity.entity_id}>
                  <button
                    type="button"
                    disabled={!inGraph}
                    onClick={() => {
                      onSelect(entity.entity_id, entity.canonical_name);
                      setText("");
                    }}
                    className="flex w-full items-center justify-between gap-2 rounded px-2 py-1.5 text-left text-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:text-slate-400 disabled:hover:bg-transparent"
                  >
                    <span>{entity.canonical_name}</span>
                    {!inGraph && (
                      <span className="text-xs">not in current graph</span>
                    )}
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}
