/**
 * FilterToggle - Boolean filter checkbox with URL state synchronization.
 *
 * Implements FR-002 (boolean filter toggles), FR-005 (WCAG 2.5.8 hit area),
 * FR-027 (snake_case param keys), FR-032 (focus management).
 *
 * Usage:
 * ```tsx
 * <FilterToggle paramKey="liked_only" label="Show Liked Only" />
 * <FilterToggle paramKey="has_transcript" label="Has Transcripts" />
 * ```
 */

import { useUrlParamBoolean } from '../hooks/useUrlParam';

export interface FilterToggleProps {
  /** URL parameter key (snake_case per FR-027) */
  paramKey: string;
  /** Visible label text */
  label: string;
}

/**
 * Boolean filter toggle checkbox with URL synchronization.
 *
 * - Renders native `<input type="checkbox">` with associated `<label>` (FR-002)
 * - Checking sets `paramKey=true` in URL
 * - Unchecking REMOVES param from URL (not `=false`)
 * - 44×44px minimum interactive hit area per WCAG 2.5.8 (FR-005)
 * - Focus remains on checkbox after state change (FR-032)
 */
export function FilterToggle({ paramKey, label }: FilterToggleProps) {
  const [isChecked, setIsChecked] = useUrlParamBoolean(paramKey);

  // Generate unique ID for label association
  const checkboxId = `filter-toggle-${paramKey}`;

  return (
    <div className="flex items-center min-h-[44px]">
      <input
        id={checkboxId}
        type="checkbox"
        checked={isChecked}
        onChange={(e) => setIsChecked(e.target.checked)}
        className="h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
      />
      <label
        htmlFor={checkboxId}
        className="ml-2 text-sm font-medium text-slate-700 cursor-pointer"
      >
        {label}
      </label>
    </div>
  );
}
