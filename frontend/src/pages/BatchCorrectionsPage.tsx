/**
 * BatchCorrectionsPage
 *
 * Implements the batch find-and-replace workflow (Feature 036):
 * - T020: Page composition with PatternInput, MatchList, and phase-driven UI
 * - T021: Route /corrections/batch (registered in router/index.tsx)
 * - T022: Preview flow wiring — PatternInput -> useBatchPreview -> MatchList
 * - T027: State machine extended with applying/complete phases; ApplyControls +
 *         ResultSummary wired; controls locked during apply (FR-024)
 * - T028: Post-apply statusMap built from BatchApplyResult and passed to
 *         MatchList so each MatchCard shows applied/skipped/failed badge (FR-025)
 * - T029: Retry handler re-submits useBatchApply with only failed_segment_ids
 *         (FR-026)
 * - T030: Focus management — first match card focused after preview loads;
 *         ResultSummary focused after apply completes (NFR-003)
 * - T036: Pair-based selection — TOGGLE_SELECT auto-toggles partner segments
 *         that share the same non-null pair_id (FR-016)
 * - T037: Auto-rebuild toggle — `autoRebuild` state (default true) wired to
 *         ApplyControls checkbox; flag sent in apply and retry requests (FR-012)
 *
 * State machine (useReducer):
 *   idle        — initial; no preview run yet
 *   previewing  — preview result loaded; user can toggle selections
 *   applying    — apply in progress (FR-024)
 *   complete    — apply finished; result summary shown (FR-025/FR-026)
 *
 * FR-008: All matches selected by default when preview loads.
 * FR-029: Changing the pattern clears a stale preview (dispatches RESET).
 * FR-024: Controls locked while applying (isLocked prop on PatternInput).
 */

import { useEffect, useReducer, useCallback, useRef, useState } from "react";
import { useLocation } from "react-router-dom";

import { ApplyControls } from "../components/batch/ApplyControls";
import { MatchList } from "../components/batch/MatchList";
import { PatternInput } from "../components/batch/PatternInput";
import { ResultSummary } from "../components/batch/ResultSummary";
import { CrossSegmentPanel } from "../components/corrections/CrossSegmentPanel";
import { useBatchApply } from "../hooks/useBatchApply";
import { useBatchPreview } from "../hooks/useBatchPreview";
import { useBatchRebuild } from "../hooks/useBatchRebuild";
import { useEntityDetail } from "../hooks/useEntityDetail";
import type {
  BatchApplyResult,
  BatchPreviewMatch,
  BatchPreviewRequest,
} from "../types/batchCorrections";
import type { CorrectionType } from "../types/corrections";
import type { EntityOption } from "../components/batch/EntityAutocomplete";

// ---------------------------------------------------------------------------
// State machine
// ---------------------------------------------------------------------------

type BatchState =
  | { phase: "idle" }
  | {
      phase: "previewing";
      matches: BatchPreviewMatch[];
      totalCount: number;
      selected: Set<number>;
      /** The preview request that produced these matches — forwarded to apply. */
      request: BatchPreviewRequest;
    }
  | {
      phase: "applying";
      matches: BatchPreviewMatch[];
      selected: Set<number>;
      total: number;
      /** Forwarded from previewing so ApplyControls can display pattern/replacement. */
      request: BatchPreviewRequest;
    }
  | {
      phase: "complete";
      matches: BatchPreviewMatch[];
      result: BatchApplyResult;
      selected: Set<number>;
      /** Forwarded so retry can reconstruct the apply request. */
      request: BatchPreviewRequest;
    };

type BatchAction =
  | {
      type: "PREVIEW_SUCCESS";
      matches: BatchPreviewMatch[];
      totalCount: number;
      request: BatchPreviewRequest;
    }
  | { type: "TOGGLE_SELECT"; segmentId: number }
  | { type: "SELECT_ALL" }
  | { type: "DESELECT_ALL" }
  | { type: "START_APPLY"; total: number }
  | { type: "APPLY_COMPLETE"; result: BatchApplyResult }
  | { type: "RESET" };

function batchReducer(state: BatchState, action: BatchAction): BatchState {
  switch (action.type) {
    case "PREVIEW_SUCCESS": {
      // FR-008: initialize with every match selected
      const allIds = new Set(action.matches.map((m) => m.segment_id));
      return {
        phase: "previewing",
        matches: action.matches,
        totalCount: action.totalCount,
        selected: allIds,
        request: action.request,
      };
    }

    case "TOGGLE_SELECT": {
      if (state.phase !== "previewing") return state;
      // Immutable Set update — copy first so React detects the change
      const next = new Set(state.selected);

      // FR-016: Pair-based selection — if the toggled match has a non-null
      // pair_id, collect all partner segment IDs that share the same pair_id
      // and toggle them in the same direction as the primary target.
      const toggledMatch = state.matches.find(
        (m) => m.segment_id === action.segmentId
      );
      const pairId = toggledMatch?.pair_id ?? null;

      // Collect the full set of IDs to toggle: the primary target + any partners
      const idsToToggle: number[] = [action.segmentId];
      if (pairId !== null) {
        const partnerIds = state.matches
          .filter(
            (m) => m.pair_id === pairId && m.segment_id !== action.segmentId
          )
          .map((m) => m.segment_id);
        idsToToggle.push(...partnerIds);
      }

      // Direction is determined by the primary target's current state:
      // if it was selected → deselect the whole group; otherwise → select all.
      const wasSelected = next.has(action.segmentId);
      for (const id of idsToToggle) {
        if (wasSelected) {
          next.delete(id);
        } else {
          next.add(id);
        }
      }

      return { ...state, selected: next };
    }

    case "SELECT_ALL": {
      if (state.phase !== "previewing") return state;
      return {
        ...state,
        selected: new Set(state.matches.map((m) => m.segment_id)),
      };
    }

    case "DESELECT_ALL": {
      if (state.phase !== "previewing") return state;
      return { ...state, selected: new Set() };
    }

    case "START_APPLY": {
      // Allow transition from 'previewing' (initial apply) and 'complete'
      // (retry of failed segments — T029 / FR-026).
      if (state.phase !== "previewing" && state.phase !== "complete") {
        return state;
      }
      return {
        phase: "applying",
        matches: state.matches,
        selected: state.selected,
        total: action.total,
        request: state.request,
      };
    }

    case "APPLY_COMPLETE": {
      if (state.phase !== "applying") return state;
      return {
        phase: "complete",
        matches: state.matches,
        result: action.result,
        selected: state.selected,
        request: state.request,
      };
    }

    case "RESET":
      return { phase: "idle" };

    default:
      return state;
  }
}

// ---------------------------------------------------------------------------
// Status map helper (T028)
// ---------------------------------------------------------------------------

/**
 * Builds a per-segment status map from a completed BatchApplyResult.
 *
 * The backend provides per-segment IDs only for failures. All selected
 * segments that are not in failed_segment_ids are marked 'applied' — the
 * aggregate skipped count is surfaced in the ResultSummary stat row instead.
 *
 * @param result - The completed apply result from the server
 * @param selected - The segment IDs the user chose to apply
 */
function buildStatusMap(
  result: BatchApplyResult,
  selected: Set<number>
): Map<number, "applied" | "skipped" | "failed"> {
  const map = new Map<number, "applied" | "skipped" | "failed">();
  const failedSet = new Set(result.failed_segment_ids);
  for (const segId of selected) {
    if (failedSet.has(segId)) {
      map.set(segId, "failed");
    } else {
      map.set(segId, "applied");
    }
  }
  return map;
}

// ---------------------------------------------------------------------------
// Idle instruction panel (FR-027)
// ---------------------------------------------------------------------------

/**
 * Shown in the idle phase below PatternInput to orient first-time users.
 */
function IdleInstructions() {
  return (
    <div
      role="note"
      className="flex flex-col items-center justify-center py-16 text-center"
    >
      {/* Find-and-replace illustration */}
      <div className="w-14 h-14 mb-4 rounded-full bg-blue-50 flex items-center justify-center">
        <svg
          aria-hidden="true"
          className="w-7 h-7 text-blue-400"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          strokeWidth={1.5}
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M10.5 10.5a4.5 4.5 0 1 0-9 0 4.5 4.5 0 0 0 9 0Z" />
          <path d="M13.5 13.5 21 21" />
          <path d="M16.5 3.75 20.25 7.5l-6.75 6.75-3.75.75.75-3.75 6-6.75Z" />
          <path d="M15 5.25l3.75 3.75" />
        </svg>
      </div>
      <p className="text-sm font-medium text-slate-700 max-w-sm">
        Search for text or regex patterns across all transcripts. Preview
        matching segments, review and deselect false positives, then apply
        corrections.
      </p>
      <p className="mt-2 text-xs text-slate-400 max-w-xs">
        Results appear here once you run a preview.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page component
// ---------------------------------------------------------------------------

/**
 * BatchCorrectionsPage is the entry point for the batch find-and-replace
 * workflow. It composes PatternInput, MatchList, ApplyControls, and
 * ResultSummary, all wired through a useReducer state machine.
 *
 * Phase transitions:
 *   idle        → previewing  (PREVIEW_SUCCESS)
 *   previewing  → applying    (START_APPLY)
 *   applying    → complete    (APPLY_COMPLETE)
 *   any         → idle        (RESET or pattern change)
 */
export function BatchCorrectionsPage() {
  // -------------------------------------------------------------------------
  // Router location state — cross-page pre-fill (T014 / US2)
  // -------------------------------------------------------------------------

  /**
   * When navigating from DiffAnalysisPage via the "Find & Replace" action,
   * the router state carries `pattern`, `replacement`, and optionally
   * `crossSegment`. We consume them once on mount (via useState initializers
   * on PatternInput), then clear the history state so back-navigation does
   * not re-apply the pre-fill.
   */
  const location = useLocation();
  const locationState = location.state as
    | { pattern?: string; replacement?: string; crossSegment?: boolean; isRegex?: boolean }
    | null
    | undefined;

  // Capture the initial values synchronously from location state so they can
  // be used as useState initial values inside PatternInput. Using refs means
  // the values are stable across renders and do not cause PatternInput to
  // re-mount if the parent re-renders.
  const prefillPattern = locationState?.pattern ?? "";
  const prefillReplacement = locationState?.replacement ?? "";
  const prefillCrossSegment = locationState?.crossSegment ?? false;
  const prefillIsRegex = locationState?.isRegex ?? false;

  // Clear history state after consuming it so back-navigation does not
  // re-apply the pre-fill (T014 spec requirement).
  useEffect(() => {
    if (locationState?.pattern || locationState?.replacement) {
      window.history.replaceState({}, document.title);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // -------------------------------------------------------------------------
  // Cross-segment panel open/closed state
  // -------------------------------------------------------------------------

  /** Whether the CrossSegmentPanel is expanded. Starts open; collapses on preview. */
  const [crossSegmentOpen, setCrossSegmentOpen] = useState(true);

  // -------------------------------------------------------------------------
  // Cross-segment panel pre-fill state (T017–T019 / US3)
  // -------------------------------------------------------------------------

  /**
   * Tracks the active initial values for PatternInput. When a cross-segment
   * candidate is selected from CrossSegmentPanel, we increment `patternInputKey`
   * to remount PatternInput with the new initial values, which is the only
   * reliable way to drive an uncontrolled form field to a new value.
   *
   * The key starts at 0 (equivalent to the router-state-driven initial render).
   * Each call to handlePrefill bumps it so PatternInput mounts fresh.
   */
  const [patternInputKey, setPatternInputKey] = useState(0);
  const [panelPrefillPattern, setPanelPrefillPattern] = useState(prefillPattern);
  const [panelPrefillReplacement, setPanelPrefillReplacement] = useState(prefillReplacement);
  const [panelPrefillCrossSegment, setPanelPrefillCrossSegment] = useState(prefillCrossSegment);
  const [panelPrefillIsRegex, setPanelPrefillIsRegex] = useState(prefillIsRegex);

  // -------------------------------------------------------------------------
  // State machine
  // -------------------------------------------------------------------------
  const [state, dispatch] = useReducer(batchReducer, { phase: "idle" });

  // -------------------------------------------------------------------------
  // Auto-rebuild toggle (T037 / FR-012)
  // -------------------------------------------------------------------------

  /**
   * Whether to trigger a full-text rebuild after apply completes.
   * Defaults to true per spec (FR-012) so the transcript text stays in sync
   * with the applied corrections without requiring a manual rebuild step.
   */
  const [autoRebuild, setAutoRebuild] = useState(true);

  const handleToggleAutoRebuild = useCallback(() => {
    setAutoRebuild((prev) => !prev);
  }, []);

  // -------------------------------------------------------------------------
  // Correction note (supplementary metadata for error pattern analysis)
  // -------------------------------------------------------------------------

  /**
   * Optional freeform note attached to every audit record produced by this
   * apply operation. Persists across preview refreshes; cleared on full RESET.
   */
  const [correctionNote, setCorrectionNote] = useState('');

  const handleCorrectionNoteChange = useCallback((note: string) => {
    setCorrectionNote(note);
  }, []);

  /**
   * Correction type attached to every audit record produced by this apply
   * operation. Defaults to "proper_noun" — the most common batch correction
   * category (ASR misrecognition of names).
   */
  const [correctionType, setCorrectionType] = useState<CorrectionType>("proper_noun");

  const handleCorrectionTypeChange = useCallback((type: CorrectionType) => {
    setCorrectionType(type);
  }, []);

  // -------------------------------------------------------------------------
  // Entity link (T026 / US5 / FR-010)
  // -------------------------------------------------------------------------

  /**
   * The named entity the user has linked to this correction session via the
   * EntityAutocomplete in PatternInput. When set, its UUID is forwarded to
   * the apply mutation as entity_id so the backend can associate each audit
   * record with the entity.
   *
   * Cleared whenever PatternInput fires onPatternChange (new session).
   */
  const [selectedEntity, setSelectedEntity] = useState<EntityOption | null>(null);

  const handleEntityChange = useCallback((entity: EntityOption | null) => {
    setSelectedEntity(entity);
  }, []);

  // Fetch alias names for the selected entity so the mismatch warning can
  // check replacement text against both the canonical name and registered
  // aliases (e.g. "AMLO" is a valid alias for "Andrés Manuel López Obrador").
  const { aliasNames: selectedEntityAliasNames } = useEntityDetail(
    selectedEntity?.id ?? null
  );

  // -------------------------------------------------------------------------
  // Mutation hooks
  // -------------------------------------------------------------------------
  const previewMutation = useBatchPreview();
  const applyMutation = useBatchApply();
  const rebuildMutation = useBatchRebuild();

  // -------------------------------------------------------------------------
  // Focus management refs (T030 / NFR-003)
  // -------------------------------------------------------------------------

  /**
   * Container ref for the MatchList region. After a successful preview we find
   * the first <article> within it and move focus there so keyboard users land
   * immediately on the first result.
   */
  const matchListRegionRef = useRef<HTMLElement>(null);

  /**
   * Ref for the ResultSummary wrapper div. After apply completes we call
   * `.focus()` on it so AT users hear the apply-complete announcement.
   */
  const resultSummaryRef = useRef<HTMLDivElement>(null);

  // -------------------------------------------------------------------------
  // Derived values for child props (must come before effects that depend on them)
  // -------------------------------------------------------------------------

  /** Whether a preview request is in flight. */
  const isPreviewLoading = previewMutation.isPending;

  /** Controls should lock while an apply operation is in progress (FR-024). */
  const isLocked = state.phase === "applying";

  /** Show the match list section in all non-idle phases. */
  const showMatchList = state.phase !== "idle";

  /**
   * Matches to display in MatchList — persisted through applying/complete so
   * status badges are visible after apply (T028).
   */
  const matchListMatches: BatchPreviewMatch[] =
    state.phase === "previewing" ||
    state.phase === "applying" ||
    state.phase === "complete"
      ? state.matches
      : [];

  const matchListTotalCount: number =
    state.phase === "previewing"
      ? state.totalCount
      : matchListMatches.length;

  const matchListSelectedIds: Set<number> =
    state.phase === "previewing" ||
    state.phase === "applying" ||
    state.phase === "complete"
      ? state.selected
      : new Set<number>();

  /**
   * Per-segment status map — only populated after apply completes (T028).
   * Maps segment_id → 'applied' | 'failed'. 'skipped' is not per-segment
   * (the backend only returns failed IDs), so skipped count comes from the
   * ResultSummary aggregate display.
   */
  const statusMap: Map<number, "applied" | "skipped" | "failed"> | undefined =
    state.phase === "complete"
      ? buildStatusMap(state.result, state.selected)
      : undefined;

  /**
   * Props for ApplyControls that depend on the current phase.
   * These are derived outside JSX for readability.
   */
  const applyControlsPattern =
    state.phase === "previewing" || state.phase === "applying"
      ? state.request.pattern
      : "";
  const applyControlsReplacement =
    state.phase === "previewing" || state.phase === "applying"
      ? state.request.replacement
      : "";
  const applyControlsSelectedCount =
    state.phase === "previewing" ? state.selected.size : 0;
  const applyControlsApplyTotal =
    state.phase === "applying" ? state.total : undefined;

  /**
   * Whether the replacement text does not match the selected entity's
   * canonical name OR any of its registered aliases (case-insensitive).
   * Used to show a mismatch warning in ApplyControls and PatternInput.
   *
   * Alias names are fetched from the entity detail endpoint which already
   * filters out `asr_error` aliases — only genuine aliases are checked.
   */
  const entityHasMismatch =
    selectedEntity !== null &&
    (() => {
      const normalizedReplacement = applyControlsReplacement.trim().toLowerCase();
      if (normalizedReplacement === selectedEntity.name.toLowerCase()) return false;
      return !selectedEntityAliasNames.some(
        (alias) => normalizedReplacement === alias.toLowerCase()
      );
    })();

  // -------------------------------------------------------------------------
  // Page title
  // -------------------------------------------------------------------------
  useEffect(() => {
    document.title = "Batch Find & Replace - ChronoVista";
    return () => {
      document.title = "ChronoVista";
    };
  }, []);

  // -------------------------------------------------------------------------
  // Focus: first match card after preview loads (T030)
  // -------------------------------------------------------------------------
  useEffect(() => {
    if (state.phase !== "previewing") return;
    if (matchListMatches.length === 0) return;
    // Find the first focusable article element inside the match list region.
    const firstCard = matchListRegionRef.current?.querySelector<HTMLElement>(
      "article"
    );
    firstCard?.focus();
  }, [state.phase, matchListMatches.length]); // eslint-disable-line react-hooks/exhaustive-deps

  // -------------------------------------------------------------------------
  // Focus: ResultSummary after apply completes (T030)
  // -------------------------------------------------------------------------
  useEffect(() => {
    if (state.phase !== "complete") return;
    resultSummaryRef.current?.focus();
  }, [state.phase]);

  // -------------------------------------------------------------------------
  // Handlers
  // -------------------------------------------------------------------------

  /** Called by PatternInput when user clicks "Preview matches". */
  const handlePreview = useCallback(
    (request: BatchPreviewRequest) => {
      // Auto-collapse the cross-segment panel so the match results are visible.
      setCrossSegmentOpen(false);
      previewMutation.mutate(request, {
        onSuccess: (data) => {
          dispatch({
            type: "PREVIEW_SUCCESS",
            matches: data.matches,
            totalCount: data.total_count,
            request,
          });
        },
      });
    },
    [previewMutation]
  );

  /**
   * Called by PatternInput whenever pattern or replacement text changes.
   * Resets to idle so stale preview results are cleared (FR-029).
   * Entity selection is intentionally preserved — the user may be correcting
   * another misspelling variant of the same entity (second-round workflow).
   * Entity is cleared via FR-011 (replacement emptied) or handlePrefill
   * (cross-segment candidate selected).
   */
  const handlePatternChange = useCallback(() => {
    dispatch({ type: "RESET" });
    previewMutation.reset();
    setCorrectionNote('');
  }, [previewMutation]);

  /** Toggle a single segment's selection state. */
  const handleToggleSelect = useCallback((segmentId: number) => {
    dispatch({ type: "TOGGLE_SELECT", segmentId });
  }, []);

  const handleSelectAll = useCallback(() => {
    dispatch({ type: "SELECT_ALL" });
  }, []);

  const handleDeselectAll = useCallback(() => {
    dispatch({ type: "DESELECT_ALL" });
  }, []);

  /**
   * Fires when the user confirms the apply action in ApplyControls (T027).
   * Transitions to the 'applying' phase then calls the apply mutation.
   *
   * Optional boolean fields are only included when defined to satisfy
   * exactOptionalPropertyTypes — spreading `undefined` values is not the same
   * as omitting the key in strict mode.
   */
  const handleApply = useCallback(() => {
    if (state.phase !== "previewing") return;
    const selectedIds = [...state.selected];
    const { pattern, replacement, is_regex, case_insensitive, cross_segment } =
      state.request;
    dispatch({ type: "START_APPLY", total: selectedIds.length });
    applyMutation.mutate(
      {
        pattern,
        replacement,
        segment_ids: selectedIds,
        auto_rebuild: autoRebuild,
        correction_type: correctionType,
        ...(is_regex !== undefined && { is_regex }),
        ...(case_insensitive !== undefined && { case_insensitive }),
        ...(cross_segment !== undefined && { cross_segment }),
        ...(correctionNote !== '' && { correction_note: correctionNote }),
        // T026: forward entity_id when an entity is linked (FR-010)
        ...(selectedEntity !== null && { entity_id: selectedEntity.id }),
      },
      {
        onSuccess: (result) => dispatch({ type: "APPLY_COMPLETE", result }),
      }
    );
  }, [state, applyMutation, autoRebuild, correctionNote, correctionType, selectedEntity]);

  /**
   * Re-submits the apply mutation for only the failed segment IDs (T029 / FR-026).
   */
  const handleRetryFailed = useCallback(() => {
    if (state.phase !== "complete") return;
    const failedIds = state.result.failed_segment_ids;
    if (failedIds.length === 0) return;

    const { pattern, replacement, is_regex, case_insensitive, cross_segment } =
      state.request;
    dispatch({ type: "START_APPLY", total: failedIds.length });
    applyMutation.mutate(
      {
        pattern,
        replacement,
        segment_ids: failedIds,
        auto_rebuild: autoRebuild,
        correction_type: correctionType,
        ...(is_regex !== undefined && { is_regex }),
        ...(case_insensitive !== undefined && { case_insensitive }),
        ...(cross_segment !== undefined && { cross_segment }),
        ...(correctionNote !== '' && { correction_note: correctionNote }),
        // T026: forward entity_id on retry as well (FR-010)
        ...(selectedEntity !== null && { entity_id: selectedEntity.id }),
      },
      {
        onSuccess: (result) => dispatch({ type: "APPLY_COMPLETE", result }),
      }
    );
  }, [state, applyMutation, autoRebuild, correctionNote, correctionType, selectedEntity]);

  /**
   * Triggers a full-text rebuild for all affected video IDs (T039 / US5-AC3).
   * Only callable when the state machine is in the 'complete' phase so that
   * `state.result.affected_video_ids` is guaranteed to exist.
   */
  const handleRebuild = useCallback(() => {
    if (state.phase !== "complete") return;
    rebuildMutation.mutate({ video_ids: state.result.affected_video_ids });
  }, [state, rebuildMutation]);

  /**
   * Called by CrossSegmentPanel when the user clicks a candidate card (T019).
   * Pre-fills PatternInput by remounting it with new initial values, then
   * resets the state machine to idle so any stale preview results are cleared.
   */
  const handlePrefill = useCallback(
    (values: { pattern: string; replacement: string; crossSegment: boolean }) => {
      setPanelPrefillPattern(values.pattern);
      setPanelPrefillReplacement(values.replacement);
      setPanelPrefillCrossSegment(values.crossSegment);
      setPanelPrefillIsRegex(false);
      // Remount PatternInput so the new initial values take effect.
      setPatternInputKey((k) => k + 1);
      // Clear any stale preview state.
      dispatch({ type: "RESET" });
      previewMutation.reset();
      setCorrectionNote("");
      setSelectedEntity(null);
    },
    [previewMutation]
  );

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------
  return (
    <main className="container mx-auto px-4 py-8">
      {/* Page header */}
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-gray-900">
          Batch Find &amp; Replace
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          Apply a single correction pattern across all matching transcript
          segments.
        </p>
      </div>

      {/* Main content column */}
      <div className="space-y-6">
        {/* Pattern configuration card — always visible */}
        <PatternInput
          key={patternInputKey}
          onPreview={handlePreview}
          isLoading={isPreviewLoading}
          isLocked={isLocked}
          onPatternChange={handlePatternChange}
          onEntityChange={handleEntityChange}
          entityAliasNames={selectedEntityAliasNames}
          initialPattern={panelPrefillPattern}
          initialReplacement={panelPrefillReplacement}
          initialCrossSegment={panelPrefillCrossSegment}
          initialIsRegex={panelPrefillIsRegex}
        />

        {/* Cross-segment candidates panel (T019) */}
        <div className="border-t border-slate-200 pt-6">
          <CrossSegmentPanel
            prefillForm={handlePrefill}
            isOpen={crossSegmentOpen}
            onToggle={() => setCrossSegmentOpen((prev) => !prev)}
          />
        </div>

        {/* Preview results section */}
        {showMatchList ? (
          <section
            ref={matchListRegionRef}
            aria-label="Preview results"
            className="space-y-4"
          >
            {/*
             * MatchList handles loading skeletons, error banners, empty state,
             * truncation warnings, and the scrollable list of MatchCards.
             *
             * - onSelectAll / onDeselectAll are passed so MatchList renders its
             *   own SelectionHeader (FR-008). We do not duplicate them here.
             * - statusMap is populated after apply completes (T028 / FR-025).
             * - Selection controls are only active in the previewing phase;
             *   in applying/complete the callbacks are omitted so the header
             *   is hidden (cards are read-only at that point).
             */}
            <MatchList
              matches={matchListMatches}
              totalCount={matchListTotalCount}
              isLoading={isPreviewLoading}
              error={previewMutation.error}
              selectedIds={matchListSelectedIds}
              onToggleSelect={handleToggleSelect}
              {...(statusMap !== undefined && { statusMap })}
              {...(state.phase === "previewing" && {
                onSelectAll: handleSelectAll,
                onDeselectAll: handleDeselectAll,
              })}
            />

            {/*
             * ApplyControls — shown while previewing and while applying.
             * Hidden once the operation is complete (ResultSummary takes over).
             * FR-024: isApplying locks the button and shows a spinner.
             */}
            {(state.phase === "previewing" || state.phase === "applying") && (
              <ApplyControls
                selectedCount={applyControlsSelectedCount}
                pattern={applyControlsPattern}
                replacement={applyControlsReplacement}
                isApplying={state.phase === "applying"}
                onApply={handleApply}
                autoRebuild={autoRebuild}
                onToggleAutoRebuild={handleToggleAutoRebuild}
                correctionNote={correctionNote}
                onCorrectionNoteChange={handleCorrectionNoteChange}
                correctionType={correctionType}
                onCorrectionTypeChange={handleCorrectionTypeChange}
                linkedEntity={selectedEntity}
                entityHasMismatch={entityHasMismatch}
                {...(applyControlsApplyTotal !== undefined && {
                  applyTotal: applyControlsApplyTotal,
                })}
              />
            )}

            {/*
             * ResultSummary — shown only after apply completes (FR-013, FR-025,
             * FR-026). The wrapper div carries the ref so the page can move
             * focus into this region after the phase transitions to 'complete'
             * (T030 / NFR-003). ResultSummary's own tabIndex={-1} on its root
             * element means focus landing on the wrapper propagates inward.
             */}
            {state.phase === "complete" && (
              <div ref={resultSummaryRef} tabIndex={-1} className="outline-none">
                <ResultSummary
                  result={state.result}
                  onRetryFailed={handleRetryFailed}
                  showRebuildButton={!state.result.rebuild_triggered}
                  onRebuild={handleRebuild}
                />
              </div>
            )}
          </section>
        ) : (
          <IdleInstructions />
        )}
      </div>
    </main>
  );
}
