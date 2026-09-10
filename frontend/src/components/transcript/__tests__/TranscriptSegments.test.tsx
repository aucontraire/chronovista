/**
 * Unit tests for the TranscriptSegments component (Feature 048, T016a and
 * general coverage).
 *
 * Merged from two divergent copies (#309 Phase 3 consolidation):
 * - Active-segment highlighting suite (TC-001 .. TC-009): FR-014 highlight
 *   behaviour, correction-precedence (amber over blue), null/undefined
 *   guards, and the action-button stopPropagation fix.
 * - General behavior suite: loading/error states, segment rendering,
 *   end-of-transcript indicator, empty state, keyboard navigation
 *   (NFR-A11-A14), ARIA attributes (NFR-A15), and virtualization
 *   (NFR-P12-P16).
 *
 * Both suites render the real component and mock the same hook
 * (`useTranscriptSegments`); the highlighting suite additionally mocks
 * `useCorrectSegment`/`useRevertSegment`/`useSegmentCorrectionHistory`/
 * `usePrefersReducedMotion`/`formatTimestamp`, which the general suite did
 * not need to mock explicitly (its assertions don't exercise those paths) —
 * merging under one mock setup is safe since those extra mocks default to
 * inert/idle values.
 *
 * The general suite originally lived under `tests/`, which `tsconfig.json`
 * excludes from `tsc --noEmit` (only `src` and `tests/test-utils.tsx` are
 * checked — see #159). Moving it into `src/**__tests__/` brings its mock
 * literals into strict typechecking, so its `useTranscriptSegments` mock
 * return values (previously missing `isFetchingPreviousPage`,
 * `hasPreviousPage`, `fetchPreviousPage`, `seekToTimestamp`) are now built
 * through the shared `makeTranscriptSegmentsReturn` factory + overrides
 * instead of ad hoc partial object literals — same values, now type-complete.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { TranscriptSegments } from "../TranscriptSegments";
import type { TranscriptSegmentsProps } from "../TranscriptSegments";
import type { TranscriptSegment } from "../../../types/transcript";

// ---------------------------------------------------------------------------
// Module-level mocks — must appear before any imports of the mocked modules
// (vi.mock is hoisted by Vitest)
// ---------------------------------------------------------------------------

vi.mock("../../../hooks/useTranscriptSegments", () => ({
  useTranscriptSegments: vi.fn(),
}));

vi.mock("../../../hooks/useCorrectSegment", () => ({
  useCorrectSegment: vi.fn(),
}));

vi.mock("../../../hooks/useRevertSegment", () => ({
  useRevertSegment: vi.fn(),
}));

vi.mock("../../../hooks/useSegmentCorrectionHistory", () => ({
  useSegmentCorrectionHistory: vi.fn(),
}));

vi.mock("../../../hooks/usePrefersReducedMotion", () => ({
  usePrefersReducedMotion: vi.fn().mockReturnValue(false),
}));

// Virtualizer mock — prevents reliance on layout calculations not available
// in happy-dom. Without this the virtual list renders no items.
vi.mock("@tanstack/react-virtual", () => ({
  useVirtualizer: vi.fn(() => ({
    getVirtualItems: () => [],
    getTotalSize: () => 0,
    measureElement: vi.fn(),
    scrollToIndex: vi.fn(),
  })),
}));

vi.mock("../../../utils/formatTimestamp", () => ({
  formatTimestamp: vi.fn((seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  }),
}));

// ---------------------------------------------------------------------------
// Import mocked hook references after vi.mock declarations
// ---------------------------------------------------------------------------

import { useTranscriptSegments } from "../../../hooks/useTranscriptSegments";
import { useCorrectSegment } from "../../../hooks/useCorrectSegment";
import { useRevertSegment } from "../../../hooks/useRevertSegment";
import { useSegmentCorrectionHistory } from "../../../hooks/useSegmentCorrectionHistory";

const mockUseTranscriptSegments = vi.mocked(useTranscriptSegments);
const mockUseCorrectSegment = vi.mocked(useCorrectSegment);
const mockUseRevertSegment = vi.mocked(useRevertSegment);
const mockUseSegmentCorrectionHistory = vi.mocked(useSegmentCorrectionHistory);

// ---------------------------------------------------------------------------
// Factories
// ---------------------------------------------------------------------------

/**
 * Creates a minimal TranscriptSegment. Defaults to `has_correction: false`
 * so tests that need amber behaviour must set it explicitly.
 */
function makeSegment(
  id: number,
  startTime: number,
  overrides: Partial<TranscriptSegment> = {}
): TranscriptSegment {
  return {
    id,
    text: `Segment ${id} text`,
    start_time: startTime,
    end_time: startTime + 5,
    duration: 5,
    has_correction: false,
    corrected_at: null,
    correction_count: 0,
    ...overrides,
  };
}

/**
 * Returns the return value for `useTranscriptSegments` loaded with the given
 * segments and no loading / error state, merged with any overrides. Using a
 * single factory (rather than ad hoc object literals) keeps every call
 * type-complete against `UseTranscriptSegmentsResult`.
 */
function makeTranscriptSegmentsReturn(
  segments: TranscriptSegment[],
  overrides: Record<string, unknown> = {}
) {
  return {
    segments,
    totalCount: segments.length,
    isLoading: false,
    isFetchingNextPage: false,
    hasNextPage: false,
    isFetchingPreviousPage: false,
    hasPreviousPage: false,
    isError: false,
    error: null,
    fetchNextPage: vi.fn(),
    fetchPreviousPage: vi.fn(),
    retry: vi.fn(),
    cancelRequests: vi.fn(),
    seekToTimestamp: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  };
}

/** Minimal idle mutation result for useCorrectSegment / useRevertSegment. */
function makeMutationReturn(overrides: Record<string, unknown> = {}) {
  return {
    mutate: vi.fn(),
    mutateAsync: vi.fn(),
    isPending: false,
    isPaused: false,
    isError: false,
    isSuccess: false,
    isIdle: true,
    error: null,
    data: undefined,
    variables: undefined,
    reset: vi.fn(),
    context: undefined,
    status: "idle" as const,
    failureCount: 0,
    failureReason: null,
    submittedAt: 0,
    ...overrides,
  };
}

/** Minimal idle query result for useSegmentCorrectionHistory. */
function makeHistoryReturn(overrides: Record<string, unknown> = {}) {
  return {
    data: undefined,
    isLoading: false,
    isFetching: false,
    isRefetching: false,
    isError: false,
    isSuccess: false,
    isPending: true,
    isPaused: false,
    isEnabled: true,
    isLoadingError: false,
    isRefetchError: false,
    isPlaceholderData: false,
    isFetched: false,
    isFetchedAfterMount: false,
    isStale: false,
    isInitialLoading: false,
    dataUpdatedAt: 0,
    errorUpdatedAt: 0,
    errorUpdateCount: 0,
    failureCount: 0,
    failureReason: null,
    fetchStatus: "idle" as const,
    status: "pending" as const,
    error: null,
    refetch: vi.fn(),
    promise: Promise.resolve(undefined) as never,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Render helper
// ---------------------------------------------------------------------------

/**
 * Wraps TranscriptSegments in the providers required by the component and
 * its internal hooks, then returns the RTL render result.
 *
 * Required defaults:
 * - `videoId` and `languageCode` are mandatory on the component.
 * - `seekTo` is kept undefined by default so tests that care about the
 *   "no player" path (activeSegmentId=undefined) reflect reality.
 */
function renderTranscriptSegments(props: Partial<TranscriptSegmentsProps> = {}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <TranscriptSegments
        videoId="test-video-id"
        languageCode="en"
        {...props}
      />
    </QueryClientProvider>
  );
}

// ---------------------------------------------------------------------------
// Test data constants
// ---------------------------------------------------------------------------

/**
 * Three non-overlapping segments with a small gap between segments 1 and 2.
 *
 * Segment 1: 0.0 – 4.9 s
 * Gap:       4.9 – 5.0 s  (Edge Case 6)
 * Segment 2: 5.0 – 9.9 s
 * Segment 3: 10.0 – 14.9 s
 */
const segmentA = makeSegment(1, 0.0);       // boundary segment
const segmentB = makeSegment(2, 5.0);       // mid-range segment
const segmentC = makeSegment(3, 10.0);      // third segment for multi-segment tests
const threeSegments: TranscriptSegment[] = [segmentA, segmentB, segmentC];

/**
 * A corrected version of segmentA — has_correction=true triggers the amber
 * highlight path, which takes precedence over the blue active-playback path.
 */
const correctedSegmentA = makeSegment(1, 0.0, {
  has_correction: true,
  corrected_at: "2024-01-15T10:00:00Z",
  correction_count: 1,
});

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.clearAllMocks();

  // Provide sensible defaults for every test. Individual tests override as
  // needed by calling the mock's `.mockReturnValue(...)` again.
  mockUseTranscriptSegments.mockReturnValue(
    makeTranscriptSegmentsReturn(threeSegments) as ReturnType<typeof useTranscriptSegments>
  );
  mockUseCorrectSegment.mockReturnValue(
    makeMutationReturn() as ReturnType<typeof useCorrectSegment>
  );
  mockUseRevertSegment.mockReturnValue(
    makeMutationReturn() as ReturnType<typeof useRevertSegment>
  );
  mockUseSegmentCorrectionHistory.mockReturnValue(
    makeHistoryReturn() as ReturnType<typeof useSegmentCorrectionHistory>
  );
});

// ---------------------------------------------------------------------------
// Helper — locate all rendered segment rows by their data attribute
// ---------------------------------------------------------------------------

/**
 * Returns every rendered div that carries `data-segment-id`.
 * The component sets this attribute on each segment row element.
 */
function getAllSegmentRows(container: HTMLElement): HTMLElement[] {
  return Array.from(
    container.querySelectorAll<HTMLElement>("[data-segment-id]")
  );
}

/**
 * Returns the segment row for the given segment id, or throws if not found.
 */
function getSegmentRow(container: HTMLElement, segmentId: number): HTMLElement {
  const el = container.querySelector<HTMLElement>(
    `[data-segment-id="${segmentId}"]`
  );
  if (!el) {
    throw new Error(`Segment row with data-segment-id="${segmentId}" not found in DOM`);
  }
  return el;
}

// ---------------------------------------------------------------------------
// TC-001: Segment at exact start_time boundary is highlighted
// ---------------------------------------------------------------------------

describe("TC-001: Segment at exact start_time boundary is highlighted (FR-014)", () => {
  it("applies border-blue-500 to the active segment when activeSegmentId matches", () => {
    const { container } = renderTranscriptSegments({
      activeSegmentId: segmentA.id, // id=1, start_time=0.0 — exact boundary
    });

    const row = getSegmentRow(container, segmentA.id);
    expect(row.className).toContain("border-blue-500");
  });

  it("applies bg-blue-50 to the active segment when activeSegmentId matches", () => {
    const { container } = renderTranscriptSegments({
      activeSegmentId: segmentA.id,
    });

    const row = getSegmentRow(container, segmentA.id);
    expect(row.className).toContain("bg-blue-50");
  });

  it("does NOT apply blue classes to segments that are not active", () => {
    const { container } = renderTranscriptSegments({
      activeSegmentId: segmentA.id,
    });

    // segmentB and segmentC are not active — they should not have blue classes
    const rowB = getSegmentRow(container, segmentB.id);
    const rowC = getSegmentRow(container, segmentC.id);

    expect(rowB.className).not.toContain("border-blue-500");
    expect(rowB.className).not.toContain("bg-blue-50");
    expect(rowC.className).not.toContain("border-blue-500");
    expect(rowC.className).not.toContain("bg-blue-50");
  });
});

// ---------------------------------------------------------------------------
// TC-002: Mid-range active segment is highlighted correctly
// ---------------------------------------------------------------------------

describe("TC-002: Mid-range active segment is highlighted (FR-014)", () => {
  it("highlights the mid-range segment (segmentB, id=2) when it is active", () => {
    const { container } = renderTranscriptSegments({
      activeSegmentId: segmentB.id, // id=2, start_time=5.0
    });

    const row = getSegmentRow(container, segmentB.id);
    expect(row.className).toContain("border-blue-500");
    expect(row.className).toContain("bg-blue-50");
  });

  it("does not highlight segmentA when segmentB is active", () => {
    const { container } = renderTranscriptSegments({
      activeSegmentId: segmentB.id,
    });

    const rowA = getSegmentRow(container, segmentA.id);
    expect(rowA.className).not.toContain("border-blue-500");
    expect(rowA.className).not.toContain("bg-blue-50");
  });

  it("highlights the last segment (segmentC, id=3) when it is active", () => {
    const { container } = renderTranscriptSegments({
      activeSegmentId: segmentC.id, // id=3, start_time=10.0
    });

    const rowC = getSegmentRow(container, segmentC.id);
    expect(rowC.className).toContain("border-blue-500");
    expect(rowC.className).toContain("bg-blue-50");
  });
});

// ---------------------------------------------------------------------------
// TC-003: activeSegmentId={null} — no segment receives blue classes
// ---------------------------------------------------------------------------

describe("TC-003: activeSegmentId=null — no active highlight rendered (Edge Case 6, FR-017)", () => {
  it("renders all three segment rows without blue highlight classes when activeSegmentId is null", () => {
    const { container } = renderTranscriptSegments({
      activeSegmentId: null,
    });

    const rows = getAllSegmentRows(container);
    // The component renders 3 segments in the non-virtualised path.
    expect(rows.length).toBe(3);

    for (const row of rows) {
      expect(row.className).not.toContain("border-blue-500");
      expect(row.className).not.toContain("bg-blue-50");
    }
  });

  it("applies the transparent border to all segments when activeSegmentId is null", () => {
    const { container } = renderTranscriptSegments({
      activeSegmentId: null,
    });

    const rows = getAllSegmentRows(container);
    for (const row of rows) {
      // Default non-active styling includes a transparent left border
      expect(row.className).toContain("border-transparent");
    }
  });
});

// ---------------------------------------------------------------------------
// TC-004: activeSegmentId undefined (prop omitted) — no active highlight
// ---------------------------------------------------------------------------

describe("TC-004: activeSegmentId undefined (no player) — no active highlight", () => {
  it("renders without blue highlight when activeSegmentId prop is omitted entirely", () => {
    // Do not pass activeSegmentId — simulates the "no player mounted" state.
    const { container } = renderTranscriptSegments();

    const rows = getAllSegmentRows(container);
    for (const row of rows) {
      expect(row.className).not.toContain("border-blue-500");
      expect(row.className).not.toContain("bg-blue-50");
    }
  });

  it("applies the transparent border to all segments when no player is mounted", () => {
    const { container } = renderTranscriptSegments();

    const rows = getAllSegmentRows(container);
    for (const row of rows) {
      expect(row.className).toContain("border-transparent");
    }
  });
});

// ---------------------------------------------------------------------------
// TC-005: Timestamp gap — component renders without blue classes (Edge Case 6)
// ---------------------------------------------------------------------------

describe("TC-005: Timestamp gap returns no highlight (Edge Case 6)", () => {
  /**
   * When the playhead is in a gap between segments, the hook sets
   * activeSegmentId to null. This test verifies the component renders
   * correctly for that hook output — no row is highlighted blue.
   */
  it("renders no blue highlight when the hook signals a gap via null", () => {
    // Simulate the hook output for a gap: activeSegmentId=null
    const { container } = renderTranscriptSegments({
      activeSegmentId: null,
    });

    const rows = getAllSegmentRows(container);
    for (const row of rows) {
      expect(row.className).not.toContain("border-blue-500");
      expect(row.className).not.toContain("bg-blue-50");
    }
  });

  it("renders all segment rows during a gap (no rows are missing)", () => {
    const { container } = renderTranscriptSegments({
      activeSegmentId: null,
    });

    // All three segments must still render — gaps do not remove rows
    expect(getAllSegmentRows(container)).toHaveLength(3);
  });
});

// ---------------------------------------------------------------------------
// TC-006: Single-entry segments array — the one segment is highlighted when active
// ---------------------------------------------------------------------------

describe("TC-006: Single-segment transcript highlights correctly", () => {
  const singleSegment = makeSegment(42, 0.0);

  beforeEach(() => {
    mockUseTranscriptSegments.mockReturnValue(
      makeTranscriptSegmentsReturn([singleSegment]) as ReturnType<typeof useTranscriptSegments>
    );
  });

  it("applies blue highlight to the only segment when it is the active one", () => {
    const { container } = renderTranscriptSegments({
      activeSegmentId: singleSegment.id,
    });

    const row = getSegmentRow(container, singleSegment.id);
    expect(row.className).toContain("border-blue-500");
    expect(row.className).toContain("bg-blue-50");
  });

  it("applies no blue highlight to the only segment when activeSegmentId is null", () => {
    const { container } = renderTranscriptSegments({
      activeSegmentId: null,
    });

    const row = getSegmentRow(container, singleSegment.id);
    expect(row.className).not.toContain("border-blue-500");
    expect(row.className).not.toContain("bg-blue-50");
  });

  it("applies transparent border when the only segment is not active", () => {
    const { container } = renderTranscriptSegments({
      activeSegmentId: null,
    });

    const row = getSegmentRow(container, singleSegment.id);
    expect(row.className).toContain("border-transparent");
  });
});

// ---------------------------------------------------------------------------
// TC-007: Correction highlight (amber) takes precedence over blue (FR-014)
// ---------------------------------------------------------------------------

describe("TC-007: Correction highlight takes precedence over active-playback blue (FR-014)", () => {
  /**
   * When a segment has `has_correction: true` AND it is the active playback
   * segment, the component applies amber classes instead of blue ones.
   * This mirrors the three-tier precedence in SegmentItem:
   *   deep-link (yellow) > correction (amber) > active-playback (blue) > default
   */
  beforeEach(() => {
    // Replace segmentA with its corrected counterpart.
    const segments = [correctedSegmentA, segmentB, segmentC];
    mockUseTranscriptSegments.mockReturnValue(
      makeTranscriptSegmentsReturn(segments) as ReturnType<typeof useTranscriptSegments>
    );
  });

  it("applies amber border (border-amber-400) when the active segment has a correction", () => {
    const { container } = renderTranscriptSegments({
      activeSegmentId: correctedSegmentA.id,
    });

    const row = getSegmentRow(container, correctedSegmentA.id);
    expect(row.className).toContain("border-amber-400");
  });

  it("applies amber background (bg-amber-50) when the active segment has a correction", () => {
    const { container } = renderTranscriptSegments({
      activeSegmentId: correctedSegmentA.id,
    });

    const row = getSegmentRow(container, correctedSegmentA.id);
    expect(row.className).toContain("bg-amber-50");
  });

  it("does NOT apply blue border (border-blue-500) when the active segment has a correction", () => {
    const { container } = renderTranscriptSegments({
      activeSegmentId: correctedSegmentA.id,
    });

    const row = getSegmentRow(container, correctedSegmentA.id);
    expect(row.className).not.toContain("border-blue-500");
  });

  it("does NOT apply blue background (bg-blue-50) when the active segment has a correction", () => {
    const { container } = renderTranscriptSegments({
      activeSegmentId: correctedSegmentA.id,
    });

    const row = getSegmentRow(container, correctedSegmentA.id);
    expect(row.className).not.toContain("bg-blue-50");
  });

  it("applies amber to the corrected active segment even when other segments are plain active", () => {
    // segmentB is also marked active in this scenario to ensure amber wins
    // for the corrected segment and blue applies to the non-corrected one.
    // (Only one activeSegmentId is provided — we use the corrected segment.)
    const { container } = renderTranscriptSegments({
      activeSegmentId: correctedSegmentA.id,
    });

    // correctedSegmentA → amber, NOT blue
    const rowA = getSegmentRow(container, correctedSegmentA.id);
    expect(rowA.className).toContain("border-amber-400");
    expect(rowA.className).not.toContain("border-blue-500");

    // segmentB is not active — default transparent border
    const rowB = getSegmentRow(container, segmentB.id);
    expect(rowB.className).toContain("border-transparent");
    expect(rowB.className).not.toContain("border-blue-500");
  });

  it("applies amber even when correction is active but activeSegmentId is null (no blue override)", () => {
    // has_correction=true, but the player is in a gap (null) — the corrected
    // segment still shows amber because has_correction takes priority over the
    // default transparent border.
    const { container } = renderTranscriptSegments({
      activeSegmentId: null,
    });

    const row = getSegmentRow(container, correctedSegmentA.id);
    // Amber highlight for correction is independent of playback position.
    expect(row.className).toContain("border-amber-400");
    expect(row.className).toContain("bg-amber-50");
    // Definitely no blue.
    expect(row.className).not.toContain("border-blue-500");
    expect(row.className).not.toContain("bg-blue-50");
  });
});

// ---------------------------------------------------------------------------
// TC-008: Only the active segment is blue; all others have a transparent border
// ---------------------------------------------------------------------------

describe("TC-008: Exactly one segment is highlighted; all others have default border", () => {
  it("highlights only segmentA when activeSegmentId=1 across three uncorrected segments", () => {
    const { container } = renderTranscriptSegments({
      activeSegmentId: segmentA.id,
    });

    const rowA = getSegmentRow(container, segmentA.id);
    const rowB = getSegmentRow(container, segmentB.id);
    const rowC = getSegmentRow(container, segmentC.id);

    // Active segment
    expect(rowA.className).toContain("border-blue-500");
    expect(rowA.className).toContain("bg-blue-50");

    // Inactive segments — must carry the default transparent border
    expect(rowB.className).toContain("border-transparent");
    expect(rowB.className).not.toContain("border-blue-500");
    expect(rowB.className).not.toContain("bg-blue-50");

    expect(rowC.className).toContain("border-transparent");
    expect(rowC.className).not.toContain("border-blue-500");
    expect(rowC.className).not.toContain("bg-blue-50");
  });

  it("highlights only segmentC when activeSegmentId=3 across three uncorrected segments", () => {
    const { container } = renderTranscriptSegments({
      activeSegmentId: segmentC.id,
    });

    const rowA = getSegmentRow(container, segmentA.id);
    const rowB = getSegmentRow(container, segmentB.id);
    const rowC = getSegmentRow(container, segmentC.id);

    expect(rowA.className).toContain("border-transparent");
    expect(rowA.className).not.toContain("border-blue-500");

    expect(rowB.className).toContain("border-transparent");
    expect(rowB.className).not.toContain("border-blue-500");

    expect(rowC.className).toContain("border-blue-500");
    expect(rowC.className).toContain("bg-blue-50");
  });

  it("counts exactly one segment row carrying border-blue-500 when one segment is active", () => {
    const { container } = renderTranscriptSegments({
      activeSegmentId: segmentB.id,
    });

    const rows = getAllSegmentRows(container);
    const blueRows = rows.filter((row) => row.className.includes("border-blue-500"));

    expect(blueRows).toHaveLength(1);
  });

  it("counts zero segment rows carrying border-blue-500 when activeSegmentId is null", () => {
    const { container } = renderTranscriptSegments({
      activeSegmentId: null,
    });

    const rows = getAllSegmentRows(container);
    const blueRows = rows.filter((row) => row.className.includes("border-blue-500"));

    expect(blueRows).toHaveLength(0);
  });

  it("counts zero segment rows carrying border-blue-500 when activeSegmentId is undefined", () => {
    const { container } = renderTranscriptSegments();

    const rows = getAllSegmentRows(container);
    const blueRows = rows.filter((row) => row.className.includes("border-blue-500"));

    expect(blueRows).toHaveLength(0);
  });

  it("verifies that all non-active rows carry border-transparent and not border-blue-500", () => {
    const { container } = renderTranscriptSegments({
      activeSegmentId: segmentA.id,
    });

    const rows = getAllSegmentRows(container);
    const inactiveRows = rows.filter(
      (row) => row.getAttribute("data-segment-id") !== String(segmentA.id)
    );

    for (const row of inactiveRows) {
      expect(row.className).toContain("border-transparent");
      expect(row.className).not.toContain("border-blue-500");
    }
  });

  it("verifies that an activeSegmentId not present in the segments list highlights nothing", () => {
    // id=999 is not in threeSegments — no row should be highlighted
    const { container } = renderTranscriptSegments({
      activeSegmentId: 999,
    });

    const rows = getAllSegmentRows(container);
    const blueRows = rows.filter((row) => row.className.includes("border-blue-500"));

    expect(blueRows).toHaveLength(0);
  });

  it("applies text content of the active segment's text to the highlighted row", () => {
    // Sanity-check: the highlighted row contains the expected segment text
    renderTranscriptSegments({
      activeSegmentId: segmentB.id,
    });

    expect(screen.getByText("Segment 2 text")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// TC-009: Edit/revert/history buttons do not trigger click-to-seek (bug fix)
//
// The bug: clicking the edit (pencil), revert, or history action buttons on a
// transcript segment was bubbling up to the segment row div and triggering
// handleSegmentClick, which called seekTo() and started video playback.
//
// The fix: each button's onClick handler calls e.stopPropagation() before
// invoking the action handler, so the click event does not reach the row div.
//
// These tests verify:
//   - Clicking each action button does NOT call seekTo
//   - The expected in-component side-effect (state transition) DOES occur,
//     proving the button's own handler fired correctly
//   - Clicking the segment text area (outside any button) DOES still call seekTo,
//     confirming the fix did not break the normal click-to-seek flow
// ---------------------------------------------------------------------------

describe("TC-009: Action buttons do not propagate click to segment row (stopPropagation fix)", () => {
  /**
   * A segment with has_correction=true and correction_count=1 so that the
   * revert and history buttons are both rendered (their visibility gates are
   * has_correction and correction_count > 0 respectively).
   */
  const correctionSegment = makeSegment(10, 30.0, {
    has_correction: true,
    corrected_at: "2024-06-01T12:00:00Z",
    correction_count: 1,
    text: "Correction segment text",
  });

  beforeEach(() => {
    mockUseTranscriptSegments.mockReturnValue(
      makeTranscriptSegmentsReturn([correctionSegment]) as ReturnType<
        typeof useTranscriptSegments
      >
    );
  });

  // -------------------------------------------------------------------------
  // TC-009a: Edit (pencil) button
  // -------------------------------------------------------------------------

  it("clicking the edit button does NOT call seekTo", () => {
    const seekTo = vi.fn();
    renderTranscriptSegments({ seekTo });

    const editBtn = screen.getByRole("button", {
      name: `Edit segment ${correctionSegment.id}`,
    });
    fireEvent.click(editBtn);

    expect(seekTo).not.toHaveBeenCalled();
  });

  it("clicking the edit button opens the inline edit form (handler fired)", () => {
    // Verify the button's own handler (handleEdit) ran — the SegmentEditForm
    // replaces the read-view when editState transitions to { mode: "editing" }.
    const seekTo = vi.fn();
    renderTranscriptSegments({ seekTo });

    const editBtn = screen.getByRole("button", {
      name: `Edit segment ${correctionSegment.id}`,
    });
    fireEvent.click(editBtn);

    // SegmentEditForm renders a textarea with aria-label="Edit segment text".
    // Its presence confirms handleEdit was called and state transitioned.
    expect(
      screen.getByRole("textbox", { name: /edit segment text/i })
    ).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // TC-009b: Revert button
  // -------------------------------------------------------------------------

  it("clicking the revert button does NOT call seekTo", () => {
    const seekTo = vi.fn();
    renderTranscriptSegments({ seekTo });

    const revertBtn = screen.getByRole("button", {
      name: `Revert correction for segment ${correctionSegment.id}`,
    });
    fireEvent.click(revertBtn);

    expect(seekTo).not.toHaveBeenCalled();
  });

  it("clicking the revert button shows the revert confirmation UI (handler fired)", () => {
    // handleRevert transitions editState to { mode: "confirming-revert" },
    // causing RevertConfirmation to render in place of the segment text.
    const seekTo = vi.fn();
    renderTranscriptSegments({ seekTo });

    const revertBtn = screen.getByRole("button", {
      name: `Revert correction for segment ${correctionSegment.id}`,
    });
    fireEvent.click(revertBtn);

    // RevertConfirmation renders the confirmation label text and a "Confirm"
    // button. The label text confirms handleRevert fired and state transitioned.
    expect(
      screen.getByText(/revert to previous version\?/i)
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /^confirm$/i })
    ).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // TC-009c: History button
  // -------------------------------------------------------------------------

  it("clicking the history button does NOT call seekTo", () => {
    const seekTo = vi.fn();
    renderTranscriptSegments({ seekTo });

    const historyBtn = screen.getByRole("button", {
      name: `View correction history for segment ${correctionSegment.id}`,
    });
    fireEvent.click(historyBtn);

    expect(seekTo).not.toHaveBeenCalled();
  });

  it("clicking the history button opens the correction history panel (handler fired)", () => {
    // handleHistory transitions editState to { mode: "history" },
    // causing CorrectionHistoryPanel to render below the segment row.
    const seekTo = vi.fn();
    renderTranscriptSegments({ seekTo });

    const historyBtn = screen.getByRole("button", {
      name: `View correction history for segment ${correctionSegment.id}`,
    });
    fireEvent.click(historyBtn);

    // CorrectionHistoryPanel renders role="region" aria-label="Correction history".
    // Its presence confirms handleHistory fired and editState transitioned.
    expect(
      screen.getByRole("region", { name: /correction history/i })
    ).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // TC-009d: Normal click-to-seek still works on the segment text area
  //
  // Regression guard — verify the fix did not accidentally suppress
  // handleSegmentClick for clicks on the segment row itself (outside buttons).
  // -------------------------------------------------------------------------

  it("clicking the segment text area DOES call seekTo with the correct timestamp", () => {
    const seekTo = vi.fn();
    renderTranscriptSegments({ seekTo });

    // Click the segment's text paragraph — this is inside the row div but
    // outside any action button, so it should bubble to handleSegmentClick.
    const segmentText = screen.getByText(correctionSegment.text);
    fireEvent.click(segmentText);

    expect(seekTo).toHaveBeenCalledTimes(1);
    expect(seekTo).toHaveBeenCalledWith(correctionSegment.start_time);
  });

  it("clicking the segment text area does NOT call seekTo when seekTo prop is omitted", () => {
    // When no player is mounted (seekTo=undefined), click-to-seek is a no-op.
    // This verifies the fix didn't accidentally break the no-player path.
    renderTranscriptSegments(); // no seekTo

    const segmentText = screen.getByText(correctionSegment.text);
    // Should not throw and seekTo is simply undefined — nothing to assert on,
    // but we verify the render is stable and the text is still present.
    fireEvent.click(segmentText);

    expect(segmentText).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// General behavior suite: loading/error states, rendering, end-of-transcript,
// empty state, keyboard navigation, ARIA attributes, virtualization.
// ---------------------------------------------------------------------------

describe("TranscriptSegments — general behavior", () => {
  const mockSegments: TranscriptSegment[] = [
    makeSegment(1, 0.5, {
      text: "Welcome to this video tutorial.",
      end_time: 3.2,
      duration: 2.7,
    }),
    makeSegment(2, 3.5, {
      text: "Today we will learn about React testing.",
      end_time: 7.1,
      duration: 3.6,
    }),
    makeSegment(3, 7.5, {
      text: "Let us start with the basics.",
      end_time: 10.0,
      duration: 2.5,
    }),
  ];

  describe("Loading States", () => {
    it("should render skeleton segments during initial load", () => {
      mockUseTranscriptSegments.mockReturnValue(
        makeTranscriptSegmentsReturn([], {
          isLoading: true,
        }) as ReturnType<typeof useTranscriptSegments>
      );

      renderTranscriptSegments();

      expect(
        screen.getByRole("status", { name: "Loading transcript segments" })
      ).toBeInTheDocument();
      expect(screen.getByText("Loading transcript segments...")).toBeInTheDocument();
    });

    it("should render 3 skeleton segments during loading (FR-020d)", () => {
      mockUseTranscriptSegments.mockReturnValue(
        makeTranscriptSegmentsReturn([], {
          isLoading: true,
        }) as ReturnType<typeof useTranscriptSegments>
      );

      const { container } = renderTranscriptSegments();

      // Count skeleton elements (animated pulse divs)
      const skeletons = container.querySelectorAll(".animate-pulse");
      expect(skeletons.length).toBe(3);
    });

    it("should show loading indicator when fetching next page", () => {
      mockUseTranscriptSegments.mockReturnValue(
        makeTranscriptSegmentsReturn(mockSegments, {
          totalCount: 100,
          isFetchingNextPage: true,
          hasNextPage: true,
        }) as ReturnType<typeof useTranscriptSegments>
      );

      renderTranscriptSegments();

      expect(
        screen.getByRole("status", { name: "Loading more segments" })
      ).toBeInTheDocument();
      expect(screen.getByText("Loading more segments...")).toBeInTheDocument();
    });
  });

  describe("Segments Rendering", () => {
    beforeEach(() => {
      mockUseTranscriptSegments.mockReturnValue(
        makeTranscriptSegmentsReturn(mockSegments) as ReturnType<
          typeof useTranscriptSegments
        >
      );
    });

    it("should render all segments with timestamps and text", () => {
      renderTranscriptSegments();

      expect(screen.getByText("Welcome to this video tutorial.")).toBeInTheDocument();
      expect(
        screen.getByText("Today we will learn about React testing.")
      ).toBeInTheDocument();
      expect(screen.getByText("Let us start with the basics.")).toBeInTheDocument();
    });

    it("should render timestamps in MM:SS format (FR-018)", () => {
      renderTranscriptSegments();

      expect(screen.getByText("0:00")).toBeInTheDocument(); // 0.5s rounded down
      expect(screen.getByText("0:03")).toBeInTheDocument(); // 3.5s
      expect(screen.getByText("0:07")).toBeInTheDocument(); // 7.5s
    });

    it("should render timestamp on left and text on right (FR-018)", () => {
      const { container } = renderTranscriptSegments();

      const segmentContainers = container.querySelectorAll("[data-segment-id]");
      expect(segmentContainers.length).toBe(3);

      // Check first segment structure
      const firstSegment = segmentContainers[0];
      expect(firstSegment).toHaveClass("flex");
      expect(firstSegment).toHaveClass("gap-4");
    });
  });

  describe("Error States", () => {
    it("should render error message when fetch fails with no segments", () => {
      mockUseTranscriptSegments.mockReturnValue(
        makeTranscriptSegmentsReturn([], {
          isError: true,
          error: { type: "network", message: "Network error" },
        }) as ReturnType<typeof useTranscriptSegments>
      );

      renderTranscriptSegments();

      expect(screen.getByRole("alert")).toBeInTheDocument();
      expect(screen.getByText("Could not load transcript segments.")).toBeInTheDocument();
    });

    it("should render retry button in error state", () => {
      mockUseTranscriptSegments.mockReturnValue(
        makeTranscriptSegmentsReturn([], {
          isError: true,
          error: { type: "network", message: "Network error" },
        }) as ReturnType<typeof useTranscriptSegments>
      );

      renderTranscriptSegments();

      expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
    });

    it("should call retry when retry button is clicked", async () => {
      const mockRetry = vi.fn();
      mockUseTranscriptSegments.mockReturnValue(
        makeTranscriptSegmentsReturn([], {
          isError: true,
          error: { type: "network", message: "Network error" },
          retry: mockRetry,
        }) as ReturnType<typeof useTranscriptSegments>
      );

      renderTranscriptSegments();
      const user = userEvent.setup();

      const retryButton = screen.getByRole("button", { name: /retry/i });
      await user.click(retryButton);

      await waitFor(() => {
        expect(mockRetry).toHaveBeenCalledTimes(1);
      });
    });

    it("should preserve loaded segments when error occurs during pagination (FR-025b)", () => {
      mockUseTranscriptSegments.mockReturnValue(
        makeTranscriptSegmentsReturn(mockSegments, {
          totalCount: 100,
          hasNextPage: true,
          isError: true,
          error: { type: "network", message: "Network error" },
        }) as ReturnType<typeof useTranscriptSegments>
      );

      renderTranscriptSegments();

      // Segments should still be visible
      expect(screen.getByText("Welcome to this video tutorial.")).toBeInTheDocument();
      expect(
        screen.getByText("Today we will learn about React testing.")
      ).toBeInTheDocument();

      // Error message should be shown inline
      expect(screen.getByText("Could not load more segments.")).toBeInTheDocument();
    });
  });

  describe("End of Transcript", () => {
    it('should show "End of transcript" when all segments loaded (FR-020e)', () => {
      mockUseTranscriptSegments.mockReturnValue(
        makeTranscriptSegmentsReturn(mockSegments) as ReturnType<
          typeof useTranscriptSegments
        >
      );

      renderTranscriptSegments();

      expect(screen.getByText("End of transcript")).toBeInTheDocument();
    });

    it('should NOT show "End of transcript" when more segments available', () => {
      mockUseTranscriptSegments.mockReturnValue(
        makeTranscriptSegmentsReturn(mockSegments, {
          totalCount: 100,
          hasNextPage: true,
        }) as ReturnType<typeof useTranscriptSegments>
      );

      renderTranscriptSegments();

      expect(screen.queryByText("End of transcript")).not.toBeInTheDocument();
    });
  });

  describe("Empty State", () => {
    it("should show message when no segments available", () => {
      mockUseTranscriptSegments.mockReturnValue(
        makeTranscriptSegmentsReturn([]) as ReturnType<typeof useTranscriptSegments>
      );

      renderTranscriptSegments();

      expect(
        screen.getByText("No transcript segments available for this language.")
      ).toBeInTheDocument();
    });
  });

  describe("Keyboard Navigation (NFR-A11-A14)", () => {
    beforeEach(() => {
      mockUseTranscriptSegments.mockReturnValue(
        makeTranscriptSegmentsReturn(mockSegments) as ReturnType<
          typeof useTranscriptSegments
        >
      );
    });

    it('should be focusable with tabindex="0" (NFR-A11)', () => {
      renderTranscriptSegments();

      const container = screen.getByRole("region", { name: "Transcript segments" });
      expect(container).toHaveAttribute("tabindex", "0");
    });

    it("should scroll down when ArrowDown is pressed (NFR-A12)", async () => {
      renderTranscriptSegments();
      const user = userEvent.setup();

      const container = screen.getByRole("region", { name: "Transcript segments" });
      container.focus();

      await user.keyboard("{ArrowDown}");

      // scrollBy should be called on the container
      expect(container.scrollBy).toHaveBeenCalled();
    });

    it("should scroll up when ArrowUp is pressed (NFR-A12)", async () => {
      renderTranscriptSegments();
      const user = userEvent.setup();

      const container = screen.getByRole("region", { name: "Transcript segments" });
      container.focus();

      await user.keyboard("{ArrowUp}");

      expect(container.scrollBy).toHaveBeenCalled();
    });

    it("should scroll by viewport height with PageDown (NFR-A13)", async () => {
      renderTranscriptSegments();
      const user = userEvent.setup();

      const container = screen.getByRole("region", { name: "Transcript segments" });
      container.focus();

      await user.keyboard("{PageDown}");

      expect(container.scrollBy).toHaveBeenCalled();
    });

    it("should scroll by viewport height with PageUp (NFR-A13)", async () => {
      renderTranscriptSegments();
      const user = userEvent.setup();

      const container = screen.getByRole("region", { name: "Transcript segments" });
      container.focus();

      await user.keyboard("{PageUp}");

      expect(container.scrollBy).toHaveBeenCalled();
    });

    it("should scroll to beginning with Home key (NFR-A14)", async () => {
      renderTranscriptSegments();
      const user = userEvent.setup();

      const container = screen.getByRole("region", { name: "Transcript segments" });
      container.focus();

      await user.keyboard("{Home}");

      expect(container.scrollTo).toHaveBeenCalledWith(
        expect.objectContaining({ top: 0 })
      );
    });

    it("should scroll to end with End key (NFR-A14)", async () => {
      renderTranscriptSegments();
      const user = userEvent.setup();

      const container = screen.getByRole("region", { name: "Transcript segments" });
      container.focus();

      await user.keyboard("{End}");

      expect(container.scrollTo).toHaveBeenCalled();
    });
  });

  describe("Accessibility Attributes (NFR-A15)", () => {
    beforeEach(() => {
      mockUseTranscriptSegments.mockReturnValue(
        makeTranscriptSegmentsReturn(mockSegments) as ReturnType<
          typeof useTranscriptSegments
        >
      );
    });

    it("should have region role with proper label", () => {
      renderTranscriptSegments();

      expect(
        screen.getByRole("region", { name: "Transcript segments" })
      ).toBeInTheDocument();
    });

    it("should have visible focus indicator", () => {
      renderTranscriptSegments();

      const container = screen.getByRole("region", { name: "Transcript segments" });
      expect(container).toHaveClass("focus-visible:ring-2");
      expect(container).toHaveClass("focus-visible:ring-blue-500");
    });
  });

  describe("Virtualization (NFR-P12-P16)", () => {
    it("should use standard rendering for < 500 segments", () => {
      mockUseTranscriptSegments.mockReturnValue(
        makeTranscriptSegmentsReturn(mockSegments) as ReturnType<
          typeof useTranscriptSegments
        >
      );

      const { container } = renderTranscriptSegments();

      // Standard rendering should show all segment elements directly
      const segmentElements = container.querySelectorAll("[data-segment-id]");
      expect(segmentElements.length).toBe(3);
    });
  });
});
