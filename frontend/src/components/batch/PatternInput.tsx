/**
 * PatternInput Component
 *
 * Implements:
 * - FR-001: Pattern text input field
 * - FR-002: Replacement text input field
 * - FR-003: Toggle controls for regex, case-insensitive, and cross-segment modes
 * - FR-024: Lock all controls during an in-progress apply operation
 * - FR-029: Notify parent when pattern or replacement changes (stale preview signal)
 *
 * Features:
 * - Accessible labelled inputs with ARIA attributes
 * - Three mode toggles rendered as role="switch" buttons with 44x44px touch targets
 * - Collapsible filter section (language, channel, video IDs)
 * - "Preview matches" button disabled when pattern is empty, loading, or locked
 * - All controls disabled when isLocked is true
 *
 * @see FR-001: Pattern input
 * @see FR-002: Replacement input
 * @see FR-003: Mode toggles
 * @see FR-024: Lock during apply
 * @see FR-029: Stale preview signal
 */

import { useState, useId, useCallback } from 'react';
import type { BatchPreviewRequest } from '../../types/batchCorrections';
import { EntityAutocomplete } from './EntityAutocomplete';
import type { EntityOption } from './EntityAutocomplete';

// ---------------------------------------------------------------------------
// Prop types
// ---------------------------------------------------------------------------

export interface PatternInputProps {
  /** Called when user clicks Preview with the assembled request. */
  onPreview: (request: BatchPreviewRequest) => void;
  /** Whether a preview is currently loading. */
  isLoading?: boolean;
  /** Whether controls should be locked (during apply). */
  isLocked?: boolean;
  /**
   * Called when pattern or replacement changes.
   * The parent uses this to clear a stale preview result (FR-029).
   */
  onPatternChange?: () => void;
  /**
   * Called when the user selects or clears an entity in EntityAutocomplete.
   * The parent (BatchCorrectionsPage) stores this and passes entity_id into
   * the apply mutation (T026 / FR-010).
   */
  onEntityChange?: (entity: EntityOption | null) => void;
  /**
   * Alias names for the currently selected entity (asr_error aliases already
   * excluded by the backend). When provided, the mismatch warning is suppressed
   * if the replacement text matches any alias (case-insensitive) in addition to
   * the canonical name.
   */
  entityAliasNames?: string[];
}

// ---------------------------------------------------------------------------
// Internal helper types
// ---------------------------------------------------------------------------

interface ToggleButtonProps {
  /** The ARIA-accessible label for the switch. */
  label: string;
  /** Shorter visible text rendered inside the button. */
  shortLabel: string;
  /** Current on/off state. */
  checked: boolean;
  /** Fired when the user activates the toggle. */
  onChange: (next: boolean) => void;
  /** When true, the toggle is visually and functionally disabled. */
  disabled: boolean;
  /** Element id used to associate the toggle with an external label, if any. */
  id?: string;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/**
 * A single accessible toggle button that follows the ARIA switch pattern.
 *
 * - Uses role="switch" with aria-checked for screen readers.
 * - Minimum 44x44px touch target (WCAG 2.5.8).
 * - Keyboard-activated via Space and Enter keys.
 */
function ToggleButton({
  label,
  shortLabel,
  checked,
  onChange,
  disabled,
  id,
}: ToggleButtonProps) {
  const handleKeyDown = (e: React.KeyboardEvent<HTMLButtonElement>) => {
    if (e.key === ' ' || e.key === 'Enter') {
      e.preventDefault();
      if (!disabled) {
        onChange(!checked);
      }
    }
  };

  return (
    <button
      id={id}
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      onKeyDown={handleKeyDown}
      className={[
        // Minimum 44x44px touch target
        'inline-flex items-center gap-2 px-3 min-h-[44px] min-w-[44px]',
        'rounded-md border text-sm font-medium',
        'transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2',
        checked && !disabled
          ? 'bg-blue-600 border-blue-700 text-white'
          : 'bg-white border-slate-300 text-slate-700',
        disabled
          ? 'opacity-50 cursor-not-allowed'
          : 'hover:bg-slate-50 cursor-pointer',
        checked && !disabled ? 'hover:bg-blue-700' : '',
      ]
        .filter(Boolean)
        .join(' ')}
    >
      {/* Visual track indicator */}
      <span
        aria-hidden="true"
        className={[
          'inline-block w-7 h-4 rounded-full border transition-colors flex-shrink-0',
          checked
            ? 'bg-white border-white/50'
            : 'bg-slate-200 border-slate-300',
        ].join(' ')}
      >
        <span
          className={[
            'block w-3 h-3 rounded-full mt-0.5 transition-transform',
            checked ? 'bg-blue-600 translate-x-3.5' : 'bg-slate-400 translate-x-0.5',
          ].join(' ')}
        />
      </span>
      {shortLabel}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

/**
 * PatternInput provides the pattern/replacement form fields, mode toggles, and
 * scope filters for the batch correction preview workflow.
 *
 * @example
 * ```tsx
 * <PatternInput
 *   onPreview={(request) => runPreview(request)}
 *   isLoading={isPreviewLoading}
 *   isLocked={isApplying}
 *   onPatternChange={() => setPreviewResult(null)}
 * />
 * ```
 */
export function PatternInput({
  onPreview,
  isLoading = false,
  isLocked = false,
  onPatternChange,
  onEntityChange,
  entityAliasNames = [],
}: PatternInputProps) {
  // -------------------------------------------------------------------------
  // Form state
  // -------------------------------------------------------------------------
  const [pattern, setPattern] = useState('');
  const [replacement, setReplacement] = useState('');
  const [isRegex, setIsRegex] = useState(false);
  const [caseInsensitive, setCaseInsensitive] = useState(false);
  const [crossSegment, setCrossSegment] = useState(false);

  // Entity link state (T025 / FR-011)
  const [selectedEntity, setSelectedEntity] = useState<EntityOption | null>(null);

  // Filter section state
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [language, setLanguage] = useState('');
  const [channelId, setChannelId] = useState('');
  const [videoIdsRaw, setVideoIdsRaw] = useState('');

  // -------------------------------------------------------------------------
  // Unique IDs for label associations (React 18+ useId)
  // -------------------------------------------------------------------------
  const patternId = useId();
  const replacementId = useId();
  const languageId = useId();
  const channelId_ = useId();
  const videoIdsId = useId();

  // -------------------------------------------------------------------------
  // Derived state
  // -------------------------------------------------------------------------
  const isDisabled = isLocked;
  const isPreviewDisabled = !pattern.trim() || isLoading || isLocked;

  /**
   * True when an entity is selected but the replacement text matches neither
   * the entity's canonical name nor any of its registered aliases
   * (case-insensitive). Alias names are supplied by the parent from the entity
   * detail endpoint, which already filters out `asr_error` aliases.
   */
  const hasMismatch =
    selectedEntity !== null &&
    (() => {
      const normalizedReplacement = replacement.trim().toLowerCase();
      if (normalizedReplacement === selectedEntity.name.toLowerCase()) return false;
      return !entityAliasNames.some(
        (alias) => normalizedReplacement === alias.toLowerCase()
      );
    })();

  // -------------------------------------------------------------------------
  // Handlers
  // -------------------------------------------------------------------------

  /** Parse the comma-separated video IDs field into a trimmed string array. */
  const parseVideoIds = (raw: string): string[] | null => {
    const ids = raw
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean);
    return ids.length > 0 ? ids : null;
  };

  const handlePatternChange = useCallback(
    (value: string) => {
      setPattern(value);
      onPatternChange?.();
    },
    [onPatternChange]
  );

  const handleReplacementChange = useCallback(
    (value: string) => {
      setReplacement(value);
      onPatternChange?.();
      // FR-011: auto-clear entity link when replacement text is cleared
      if (!value.trim()) {
        setSelectedEntity(null);
        onEntityChange?.(null);
      }
    },
    [onPatternChange, onEntityChange]
  );

  const handleEntitySelect = useCallback(
    (entity: EntityOption | null) => {
      setSelectedEntity(entity);
      onEntityChange?.(entity);
    },
    [onEntityChange]
  );

  const handlePreview = () => {
    if (isPreviewDisabled) return;

    const request: BatchPreviewRequest = {
      pattern: pattern.trim(),
      replacement,
      ...(isRegex && { is_regex: true }),
      ...(caseInsensitive && { case_insensitive: true }),
      ...(crossSegment && { cross_segment: true }),
      ...(language.trim() ? { language: language.trim() } : {}),
      ...(channelId.trim() ? { channel_id: channelId.trim() } : {}),
    };

    const parsedVideoIds = parseVideoIds(videoIdsRaw);
    if (parsedVideoIds !== null) {
      request.video_ids = parsedVideoIds;
    }

    onPreview(request);
  };

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  return (
    <section
      aria-label="Batch pattern configuration"
      className="bg-white border border-slate-200 rounded-lg shadow-sm"
    >
      {/* Main form fields */}
      <div className="p-4 space-y-4 sm:p-6">

        {/* Pattern + Replacement row */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">

          {/* Pattern field */}
          <div className="space-y-1.5">
            <label
              htmlFor={patternId}
              className="block text-sm font-medium text-slate-700"
            >
              Find pattern
            </label>
            <input
              id={patternId}
              type="text"
              value={pattern}
              onChange={(e) => handlePatternChange(e.target.value)}
              disabled={isDisabled}
              placeholder="Enter text or regex pattern..."
              aria-describedby={`${patternId}-hint`}
              className={[
                'w-full px-3 py-2 rounded-md border text-sm text-slate-900',
                'placeholder-slate-400',
                'focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent',
                'transition-colors',
                isDisabled
                  ? 'bg-slate-100 border-slate-200 text-slate-400 cursor-not-allowed'
                  : 'bg-white border-slate-300',
              ].join(' ')}
            />
            <p
              id={`${patternId}-hint`}
              className="text-xs text-slate-500"
            >
              {isRegex
                ? 'Python re syntax — use capture groups for backreferences in replacement.'
                : 'Literal text to find.'}
            </p>
          </div>

          {/* Replacement field */}
          <div className="space-y-1.5">
            <label
              htmlFor={replacementId}
              className="block text-sm font-medium text-slate-700"
            >
              Replace with
            </label>
            <input
              id={replacementId}
              type="text"
              value={replacement}
              onChange={(e) => handleReplacementChange(e.target.value)}
              disabled={isDisabled}
              placeholder="Replacement text (leave empty to delete)"
              aria-describedby={`${replacementId}-hint`}
              className={[
                'w-full px-3 py-2 rounded-md border text-sm text-slate-900',
                'placeholder-slate-400',
                'focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent',
                'transition-colors',
                isDisabled
                  ? 'bg-slate-100 border-slate-200 text-slate-400 cursor-not-allowed'
                  : 'bg-white border-slate-300',
              ].join(' ')}
            />
            <p
              id={`${replacementId}-hint`}
              className="text-xs text-slate-500"
            >
              {isRegex
                ? 'Use \\1, \\2 for capture group backreferences.'
                : 'Leave empty to delete matched text.'}
            </p>
          </div>
        </div>

        {/* Entity link — below the pattern/replacement row (T025 / FR-010) */}
        <EntityAutocomplete
          searchText={replacement}
          selectedEntity={selectedEntity}
          onEntitySelect={handleEntitySelect}
          disabled={isDisabled}
          hasMismatch={hasMismatch}
        />

        {/* Toggle row */}
        <fieldset className="space-y-2">
          <legend className="text-sm font-medium text-slate-700">
            Match options
          </legend>
          <div
            role="group"
            aria-label="Match mode toggles"
            className="flex flex-wrap gap-2"
          >
            <ToggleButton
              label="Treat pattern as a regular expression"
              shortLabel="Regex"
              checked={isRegex}
              onChange={setIsRegex}
              disabled={isDisabled}
            />
            <ToggleButton
              label="Case insensitive match"
              shortLabel="Case insensitive"
              checked={caseInsensitive}
              onChange={setCaseInsensitive}
              disabled={isDisabled}
            />
            <ToggleButton
              label="Match across segment boundaries"
              shortLabel="Cross-segment"
              checked={crossSegment}
              onChange={setCrossSegment}
              disabled={isDisabled}
            />
          </div>
          {crossSegment && (
            <p
              role="note"
              className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-2 py-1.5"
            >
              Cross-segment matching is slower and may increase preview time for large result sets.
            </p>
          )}
        </fieldset>

        {/* Scope filters — collapsible on desktop, bottom sheet on mobile */}
        <div className="border-t border-slate-100 pt-4">
          <button
            type="button"
            aria-expanded={filtersOpen}
            aria-controls="scope-filters-panel"
            onClick={() => setFiltersOpen((prev) => !prev)}
            disabled={isDisabled}
            className={[
              'inline-flex items-center gap-2 text-sm font-medium',
              'min-h-[44px] min-w-[44px] px-2 -ml-2',
              'focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 rounded',
              isDisabled ? 'text-slate-400 cursor-not-allowed' : 'text-slate-600 hover:text-slate-900',
            ].join(' ')}
          >
            {/* Chevron icon — desktop only */}
            <svg
              aria-hidden="true"
              className={[
                'hidden sm:block w-4 h-4 transition-transform',
                filtersOpen ? 'rotate-90' : '',
              ].join(' ')}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 5l7 7-7 7"
              />
            </svg>
            {/* Filter icon — mobile only */}
            <svg
              aria-hidden="true"
              className="sm:hidden w-4 h-4"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2a1 1 0 01-.293.707L13 13.414V19a1 1 0 01-.553.894l-4 2A1 1 0 017 21v-7.586L3.293 6.707A1 1 0 013 6V4z"
              />
            </svg>
            <span className="sm:hidden">More filters</span>
            <span className="hidden sm:inline">Scope filters</span>
            {(language.trim() || channelId.trim() || videoIdsRaw.trim()) && (
              <span
                aria-label="Active scope filters"
                className="ml-1 inline-flex items-center justify-center w-4 h-4 rounded-full bg-blue-100 text-blue-700 text-xs font-semibold"
              >
                {
                  [language.trim(), channelId.trim(), videoIdsRaw.trim()].filter(
                    Boolean
                  ).length
                }
              </span>
            )}
          </button>

          {/* Desktop: inline collapsible panel */}
          {filtersOpen && (
            <div
              id="scope-filters-panel"
              className="hidden sm:grid mt-4 grid-cols-1 gap-4 sm:grid-cols-3"
            >
              {/* Language filter */}
              <div className="space-y-1.5">
                <label
                  htmlFor={languageId}
                  className="block text-sm font-medium text-slate-700"
                >
                  Language
                </label>
                <input
                  id={languageId}
                  type="text"
                  value={language}
                  onChange={(e) => setLanguage(e.target.value)}
                  disabled={isDisabled}
                  placeholder="e.g. en, en-US, es"
                  aria-describedby={`${languageId}-hint`}
                  className={[
                    'w-full px-3 py-2 rounded-md border text-sm text-slate-900',
                    'placeholder-slate-400',
                    'focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent',
                    'transition-colors',
                    isDisabled
                      ? 'bg-slate-100 border-slate-200 text-slate-400 cursor-not-allowed'
                      : 'bg-white border-slate-300',
                  ].join(' ')}
                />
                <p id={`${languageId}-hint`} className="text-xs text-slate-500">
                  BCP-47 language code
                </p>
              </div>

              {/* Channel ID filter */}
              <div className="space-y-1.5">
                <label
                  htmlFor={channelId_}
                  className="block text-sm font-medium text-slate-700"
                >
                  Channel
                </label>
                <input
                  id={channelId_}
                  type="text"
                  value={channelId}
                  onChange={(e) => setChannelId(e.target.value)}
                  disabled={isDisabled}
                  placeholder="e.g. UCxxxxxxxx"
                  aria-describedby={`${channelId_}-hint`}
                  className={[
                    'w-full px-3 py-2 rounded-md border text-sm text-slate-900',
                    'placeholder-slate-400',
                    'focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent',
                    'transition-colors',
                    isDisabled
                      ? 'bg-slate-100 border-slate-200 text-slate-400 cursor-not-allowed'
                      : 'bg-white border-slate-300',
                  ].join(' ')}
                />
                <p id={`${channelId_}-hint`} className="text-xs text-slate-500">
                  YouTube channel ID
                </p>
              </div>

              {/* Video IDs filter */}
              <div className="space-y-1.5">
                <label
                  htmlFor={videoIdsId}
                  className="block text-sm font-medium text-slate-700"
                >
                  Video IDs
                </label>
                <input
                  id={videoIdsId}
                  type="text"
                  value={videoIdsRaw}
                  onChange={(e) => setVideoIdsRaw(e.target.value)}
                  disabled={isDisabled}
                  placeholder="dQw4w9WgXcQ, abc123, ..."
                  aria-describedby={`${videoIdsId}-hint`}
                  className={[
                    'w-full px-3 py-2 rounded-md border text-sm text-slate-900',
                    'placeholder-slate-400',
                    'focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent',
                    'transition-colors',
                    isDisabled
                      ? 'bg-slate-100 border-slate-200 text-slate-400 cursor-not-allowed'
                      : 'bg-white border-slate-300',
                  ].join(' ')}
                />
                <p id={`${videoIdsId}-hint`} className="text-xs text-slate-500">
                  Comma-separated YouTube video IDs
                </p>
              </div>
            </div>
          )}
        </div>

        {/* Mobile: bottom sheet overlay */}
        {filtersOpen && (
          <div className="sm:hidden fixed inset-0 z-50">
            {/* Backdrop */}
            <div
              className="absolute inset-0 bg-black/30"
              aria-hidden="true"
              onClick={() => setFiltersOpen(false)}
            />
            {/* Sheet */}
            <div
              role="dialog"
              aria-modal="true"
              aria-label="Scope filters"
              className="absolute bottom-0 left-0 right-0 bg-white rounded-t-xl shadow-xl p-5 space-y-4 max-h-[70vh] overflow-y-auto"
            >
              {/* Sheet header */}
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-slate-800">
                  Scope Filters
                </h3>
                <button
                  type="button"
                  onClick={() => setFiltersOpen(false)}
                  className="inline-flex items-center justify-center min-h-[44px] min-w-[44px] text-slate-400 hover:text-slate-600 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
                  aria-label="Close filters"
                >
                  <svg
                    className="w-5 h-5"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                    aria-hidden="true"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M6 18L18 6M6 6l12 12"
                    />
                  </svg>
                </button>
              </div>

              {/* Language filter */}
              <div className="space-y-1.5">
                <label
                  htmlFor={`${languageId}-mobile`}
                  className="block text-sm font-medium text-slate-700"
                >
                  Language
                </label>
                <input
                  id={`${languageId}-mobile`}
                  type="text"
                  value={language}
                  onChange={(e) => setLanguage(e.target.value)}
                  disabled={isDisabled}
                  placeholder="e.g. en, en-US, es"
                  aria-describedby={`${languageId}-mobile-hint`}
                  className={[
                    'w-full px-3 py-2 rounded-md border text-sm text-slate-900',
                    'placeholder-slate-400',
                    'focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent',
                    'transition-colors',
                    isDisabled
                      ? 'bg-slate-100 border-slate-200 text-slate-400 cursor-not-allowed'
                      : 'bg-white border-slate-300',
                  ].join(' ')}
                />
                <p id={`${languageId}-mobile-hint`} className="text-xs text-slate-500">
                  BCP-47 language code
                </p>
              </div>

              {/* Channel ID filter */}
              <div className="space-y-1.5">
                <label
                  htmlFor={`${channelId_}-mobile`}
                  className="block text-sm font-medium text-slate-700"
                >
                  Channel
                </label>
                <input
                  id={`${channelId_}-mobile`}
                  type="text"
                  value={channelId}
                  onChange={(e) => setChannelId(e.target.value)}
                  disabled={isDisabled}
                  placeholder="e.g. UCxxxxxxxx"
                  aria-describedby={`${channelId_}-mobile-hint`}
                  className={[
                    'w-full px-3 py-2 rounded-md border text-sm text-slate-900',
                    'placeholder-slate-400',
                    'focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent',
                    'transition-colors',
                    isDisabled
                      ? 'bg-slate-100 border-slate-200 text-slate-400 cursor-not-allowed'
                      : 'bg-white border-slate-300',
                  ].join(' ')}
                />
                <p id={`${channelId_}-mobile-hint`} className="text-xs text-slate-500">
                  YouTube channel ID
                </p>
              </div>

              {/* Video IDs filter */}
              <div className="space-y-1.5">
                <label
                  htmlFor={`${videoIdsId}-mobile`}
                  className="block text-sm font-medium text-slate-700"
                >
                  Video IDs
                </label>
                <input
                  id={`${videoIdsId}-mobile`}
                  type="text"
                  value={videoIdsRaw}
                  onChange={(e) => setVideoIdsRaw(e.target.value)}
                  disabled={isDisabled}
                  placeholder="dQw4w9WgXcQ, abc123, ..."
                  aria-describedby={`${videoIdsId}-mobile-hint`}
                  className={[
                    'w-full px-3 py-2 rounded-md border text-sm text-slate-900',
                    'placeholder-slate-400',
                    'focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent',
                    'transition-colors',
                    isDisabled
                      ? 'bg-slate-100 border-slate-200 text-slate-400 cursor-not-allowed'
                      : 'bg-white border-slate-300',
                  ].join(' ')}
                />
                <p id={`${videoIdsId}-mobile-hint`} className="text-xs text-slate-500">
                  Comma-separated YouTube video IDs
                </p>
              </div>

              {/* Done button */}
              <button
                type="button"
                onClick={() => setFiltersOpen(false)}
                className="w-full mt-2 px-4 py-2.5 rounded-md bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 transition-colors"
              >
                Done
              </button>
            </div>
          </div>
        )}

        {/* Action row */}
        <div className="flex items-center gap-3 pt-2">
          <button
            type="button"
            onClick={handlePreview}
            disabled={isPreviewDisabled}
            aria-busy={isLoading}
            aria-describedby={
              !pattern.trim() ? 'preview-btn-hint' : undefined
            }
            className={[
              'inline-flex items-center gap-2 px-4 py-2 rounded-md',
              'min-h-[44px] min-w-[44px]',
              'text-sm font-medium',
              'focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2',
              'transition-colors',
              isPreviewDisabled
                ? 'bg-blue-300 text-white cursor-not-allowed'
                : 'bg-blue-600 text-white hover:bg-blue-700 active:bg-blue-800',
            ].join(' ')}
          >
            {isLoading ? (
              <>
                {/* Spinner */}
                <svg
                  aria-hidden="true"
                  className="w-4 h-4 animate-spin"
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
                Searching...
              </>
            ) : (
              'Preview matches'
            )}
          </button>

          {isLocked && (
            <p
              role="status"
              className="text-sm text-slate-500"
            >
              Controls locked while applying corrections.
            </p>
          )}

          {!pattern.trim() && !isLocked && (
            <p
              id="preview-btn-hint"
              className="text-sm text-slate-400"
            >
              Enter a pattern to preview matches.
            </p>
          )}
        </div>
      </div>
    </section>
  );
}
