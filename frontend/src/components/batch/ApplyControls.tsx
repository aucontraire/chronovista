/**
 * ApplyControls Component
 *
 * Renders the apply button and inline confirmation strip for the batch
 * corrections workflow (T024).
 *
 * Implements:
 * - FR-010: Inline confirmation strip anchored above the Apply button
 * - FR-024: Spinner + locked state while apply is in progress
 * - NFR-003: Focus moves to the confirmation strip when it appears
 * - WCAG 2.5.8: 44×44 px minimum touch targets on all interactive elements
 * - Escape key dismisses the confirmation strip
 *
 * @see T024, T037 in batch corrections spec
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import {
  CORRECTION_TYPE_DESCRIPTIONS,
  CORRECTION_TYPE_LABELS,
} from '../../types/corrections';
import type { CorrectionType } from '../../types/corrections';

// ---------------------------------------------------------------------------
// Prop types
// ---------------------------------------------------------------------------

export interface ApplyControlsProps {
  /** Number of currently selected segments. */
  selectedCount: number;
  /** The search pattern shown in the confirmation strip. */
  pattern: string;
  /** The replacement text shown in the confirmation strip. */
  replacement: string;
  /** Whether the apply mutation is in progress. */
  isApplying: boolean;
  /** Total segments being applied — used for the in-progress label (FR-024). */
  applyTotal?: number;
  /** Called when the user confirms the apply action. */
  onApply: () => void;
  /** Whether auto-rebuild is enabled (FR-012). */
  autoRebuild?: boolean;
  /** Toggle auto-rebuild setting (FR-012). */
  onToggleAutoRebuild?: () => void;
  /** Optional note to attach to each audit record for error pattern analysis. */
  correctionNote?: string;
  /** Called when the correction note field changes. */
  onCorrectionNoteChange?: (note: string) => void;
  /** The correction type to attach to each audit record. */
  correctionType?: CorrectionType;
  /** Called when the correction type selection changes. */
  onCorrectionTypeChange?: (type: CorrectionType) => void;
}

// ---------------------------------------------------------------------------
// Internal sub-components
// ---------------------------------------------------------------------------

/** Inline spinner icon used in the Apply button during the applying phase. */
function Spinner() {
  return (
    <svg
      aria-hidden="true"
      className="w-4 h-4 animate-spin flex-shrink-0"
      fill="none"
      viewBox="0 0 24 24"
    >
      <circle
        className="opacity-25"
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="4"
      />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"
      />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

/**
 * ApplyControls provides a single "Apply to N selected" button that, when
 * clicked, opens an inline confirmation strip instead of a modal dialog.
 * The strip shows the pattern/replacement pair and requires an explicit
 * "Confirm" click before `onApply` is invoked.
 *
 * Focus is moved into the strip on open (NFR-003) and Escape dismisses it.
 *
 * @example
 * ```tsx
 * <ApplyControls
 *   selectedCount={state.selected.size}
 *   pattern={previewRequest.pattern}
 *   replacement={previewRequest.replacement}
 *   isApplying={state.phase === 'applying'}
 *   applyTotal={state.phase === 'applying' ? state.total : undefined}
 *   onApply={() => {
 *     dispatch({ type: 'START_APPLY', total: state.selected.size });
 *     applyMutation.mutate(...);
 *   }}
 * />
 * ```
 */
export function ApplyControls({
  selectedCount,
  pattern,
  replacement,
  isApplying,
  applyTotal,
  onApply,
  autoRebuild = true,
  onToggleAutoRebuild,
  correctionNote = '',
  onCorrectionNoteChange,
  correctionType,
  onCorrectionTypeChange,
}: ApplyControlsProps) {
  // Whether the inline confirmation strip is visible.
  const [showConfirmation, setShowConfirmation] = useState(false);

  // Ref to the confirmation strip container — used for programmatic focus.
  const confirmationRef = useRef<HTMLDivElement>(null);

  // Ref to the "Confirm" button inside the strip — focused on strip open.
  const confirmButtonRef = useRef<HTMLButtonElement>(null);

  const isApplyDisabled = selectedCount === 0 || isApplying;

  // -------------------------------------------------------------------------
  // Focus management (NFR-003)
  // -------------------------------------------------------------------------

  // Move focus to the Confirm button when the strip becomes visible so
  // keyboard and AT users can confirm or cancel without extra tabbing.
  useEffect(() => {
    if (showConfirmation) {
      confirmButtonRef.current?.focus();
    }
  }, [showConfirmation]);

  // -------------------------------------------------------------------------
  // Keyboard handling
  // -------------------------------------------------------------------------

  const handleStripKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLDivElement>) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        setShowConfirmation(false);
      }
    },
    [],
  );

  // -------------------------------------------------------------------------
  // Handlers
  // -------------------------------------------------------------------------

  const handleApplyClick = () => {
    if (isApplyDisabled) return;
    setShowConfirmation(true);
  };

  const handleConfirm = () => {
    setShowConfirmation(false);
    onApply();
  };

  const handleCancel = () => {
    setShowConfirmation(false);
  };

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  return (
    <div className="space-y-3">

      {/* Inline confirmation strip (FR-010) — shown above the button.
          On mobile this strip must remain in normal flow so it appears above
          the sticky action bar rather than being obscured by it. */}
      {showConfirmation && (
        <div
          ref={confirmationRef}
          role="region"
          aria-label="Confirm batch apply"
          onKeyDown={handleStripKeyDown}
          className="rounded-lg border border-blue-200 bg-blue-50 p-4 space-y-3"
        >
          {/* Description */}
          <div className="space-y-1">
            <p className="text-sm font-medium text-blue-900">
              Replace{' '}
              <span className="font-mono bg-blue-100 px-1 py-0.5 rounded text-blue-800">
                &lsquo;{pattern}&rsquo;
              </span>{' '}
              with{' '}
              <span className="font-mono bg-blue-100 px-1 py-0.5 rounded text-blue-800">
                {replacement === '' ? (
                  <em className="not-italic text-blue-600">(empty — deletes match)</em>
                ) : (
                  <>&lsquo;{replacement}&rsquo;</>
                )}
              </span>{' '}
              in{' '}
              <span className="font-semibold">{selectedCount}</span>{' '}
              {selectedCount !== 1 ? 'segments' : 'segment'}
            </p>
            <p className="text-xs text-blue-700">
              Each correction can be individually reverted from the video page.
            </p>
          </div>

          {/* Action buttons */}
          <div className="flex items-center gap-3">
            <button
              ref={confirmButtonRef}
              type="button"
              onClick={handleConfirm}
              className={[
                'inline-flex items-center gap-2 px-4 py-2 rounded-md',
                'min-h-[44px] min-w-[44px]',
                'text-sm font-medium text-white',
                'bg-blue-600 hover:bg-blue-700 active:bg-blue-800',
                'focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2',
                'transition-colors',
              ].join(' ')}
            >
              Confirm
            </button>
            <button
              type="button"
              onClick={handleCancel}
              className={[
                'inline-flex items-center gap-2 px-4 py-2 rounded-md',
                'min-h-[44px] min-w-[44px]',
                'text-sm font-medium text-slate-700',
                'bg-white border border-slate-300',
                'hover:bg-slate-50 active:bg-slate-100',
                'focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2',
                'transition-colors',
              ].join(' ')}
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Apply button row — sticky bottom bar on mobile, static on desktop.
          NFR-004: on narrow viewports the row is fixed to the bottom edge so
          the primary action is always reachable without scrolling. The
          sm:static reset removes all fixed-bar chrome on sm and above. */}
      <div
        className={[
          'fixed bottom-0 left-0 right-0 z-10',
          'bg-white border-t border-slate-200 shadow-lg',
          'p-4',
          'sm:static sm:bg-transparent sm:border-0 sm:shadow-none sm:p-0',
        ].join(' ')}
      >

      {/* Correction type select — categorizes the batch correction for audit records */}
      {onCorrectionTypeChange !== undefined && correctionType !== undefined && (
        <div className="mb-3">
          <label
            htmlFor="apply-correction-type"
            className="block text-xs font-medium text-slate-600 mb-1"
          >
            Correction type
          </label>
          <select
            id="apply-correction-type"
            value={correctionType}
            onChange={(e) => onCorrectionTypeChange(e.target.value as CorrectionType)}
            disabled={isApplying}
            className={[
              'w-full sm:max-w-md px-3 py-2 rounded-md border text-sm text-slate-700',
              'min-h-[44px]',
              'border-slate-300 bg-white',
              'focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 focus:border-blue-500',
              isApplying ? 'opacity-50 cursor-not-allowed bg-slate-50' : '',
            ].join(' ')}
          >
            {(Object.entries(CORRECTION_TYPE_LABELS) as [CorrectionType, string][]).map(
              ([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              )
            )}
          </select>
          <p className="mt-1 text-xs text-slate-500">
            {CORRECTION_TYPE_DESCRIPTIONS[correctionType]}
          </p>
        </div>
      )}

      {/* Correction note input — optional metadata for error pattern analysis */}
      {onCorrectionNoteChange !== undefined && (
        <div className="mb-3">
          <label
            htmlFor="apply-correction-note"
            className="block text-xs font-medium text-slate-600 mb-1"
          >
            Correction note{' '}
            <span className="font-normal text-slate-400">
              — Optional. Helps categorize error patterns (e.g., ASR proper noun, accent, speaker name)
            </span>
          </label>
          <input
            id="apply-correction-note"
            type="text"
            value={correctionNote}
            onChange={(e) => onCorrectionNoteChange(e.target.value)}
            disabled={isApplying}
            placeholder="e.g., ASR proper noun, accent variation, speaker name"
            className={[
              'w-full sm:max-w-md px-3 rounded-md border text-sm text-slate-700',
              'min-h-[44px]',
              'border-slate-300 bg-white',
              'placeholder:text-slate-400',
              'focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 focus:border-blue-500',
              isApplying ? 'opacity-50 cursor-not-allowed bg-slate-50' : '',
            ].join(' ')}
          />
        </div>
      )}

      <div className="flex flex-wrap items-center gap-4">
        <button
          type="button"
          onClick={handleApplyClick}
          disabled={isApplyDisabled}
          aria-busy={isApplying}
          className={[
            'inline-flex items-center gap-2 px-5 py-2.5 rounded-md',
            'min-h-[44px] min-w-[44px]',
            'text-sm font-medium',
            'focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2',
            'transition-colors',
            isApplyDisabled
              ? 'bg-blue-300 text-white cursor-not-allowed'
              : 'bg-blue-600 text-white hover:bg-blue-700 active:bg-blue-800',
          ].join(' ')}
        >
          {isApplying ? (
            <>
              <Spinner />
              {applyTotal !== undefined
                ? `Applying ${applyTotal} correction${applyTotal !== 1 ? 's' : ''}...`
                : 'Applying...'}
            </>
          ) : (
            `Apply to ${selectedCount} selected`
          )}
        </button>

        {/* Auto-rebuild toggle (FR-012 / T037) */}
        {onToggleAutoRebuild !== undefined && (
          <label className="inline-flex items-center gap-2 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={autoRebuild}
              onChange={onToggleAutoRebuild}
              disabled={isApplying}
              className={[
                'w-4 h-4 rounded border-slate-300 text-blue-600',
                'focus:ring-2 focus:ring-blue-500 focus:ring-offset-2',
                isApplying ? 'opacity-50 cursor-not-allowed' : '',
              ].join(' ')}
            />
            <span
              className={[
                'text-sm text-slate-600',
                isApplying ? 'opacity-50' : '',
              ].join(' ')}
            >
              Auto-rebuild transcript text after apply
            </span>
          </label>
        )}

        {/* Hint when nothing is selected */}
        {selectedCount === 0 && !isApplying && (
          <p className="text-sm text-slate-400">
            Select at least one match to apply.
          </p>
        )}
      </div>
      </div>{/* end sticky-bar wrapper */}
    </div>
  );
}
