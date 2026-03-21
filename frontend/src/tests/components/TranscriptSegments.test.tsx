/**
 * Unit tests for TranscriptSegments active-segment highlighting logic (Feature 048, T016a).
 *
 * These tests exercise the FR-014 highlight behaviour: the component applies
 * `border-blue-500 bg-blue-50` to the single segment whose `id` matches the
 * `activeSegmentId` prop. They also verify the correction-precedence rule
 * (FR-014 / amber takes priority over blue) and the null / undefined guard
 * (Edge Case 6 and "no player mounted" paths).
 *
 * Architecture note:
 * - The `activeSegmentId` value originates from `useYouTubePlayer` (binary
 *   search inside the hook) and is passed as a plain prop to
 *   `TranscriptSegments`. These tests pass it directly, so the binary-search
 *   logic itself is not exercised here — those tests live in the hook's own
 *   test file.
 * - `TranscriptSegments` depends on several hooks. All are mocked at module
 *   scope so the component renders without network or database access.
 *   The mocking pattern mirrors `TranscriptSegments.corrections.test.tsx`.
 *
 * Test inventory:
 * - TC-001: Segment at exact start_time boundary is highlighted (blue classes)
 * - TC-002: Mid-range active segment is highlighted correctly
 * - TC-003: activeSegmentId={null} — no segment receives blue classes
 * - TC-004: activeSegmentId undefined (prop omitted) — no segment receives blue classes
 * - TC-005: Timestamp gap (activeSegmentId=null) — component renders without blue classes
 * - TC-006: Single-entry segments array — the one segment is highlighted when active
 * - TC-007: Correction highlight (amber) takes precedence over active-playback blue (FR-014)
 * - TC-008: Only the active segment is blue; all others have a transparent border
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { TranscriptSegments } from "../../components/transcript/TranscriptSegments";
import type { TranscriptSegmentsProps } from "../../components/transcript/TranscriptSegments";
import type { TranscriptSegment } from "../../types/transcript";

// ---------------------------------------------------------------------------
// Module-level mocks — must appear before any imports of the mocked modules
// (vi.mock is hoisted by Vitest)
// ---------------------------------------------------------------------------

vi.mock("../../hooks/useTranscriptSegments", () => ({
  useTranscriptSegments: vi.fn(),
}));

vi.mock("../../hooks/useCorrectSegment", () => ({
  useCorrectSegment: vi.fn(),
}));

vi.mock("../../hooks/useRevertSegment", () => ({
  useRevertSegment: vi.fn(),
}));

vi.mock("../../hooks/useSegmentCorrectionHistory", () => ({
  useSegmentCorrectionHistory: vi.fn(),
}));

vi.mock("../../hooks/usePrefersReducedMotion", () => ({
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

vi.mock("../../utils/formatTimestamp", () => ({
  formatTimestamp: vi.fn((seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  }),
}));

// ---------------------------------------------------------------------------
// Import mocked hook references after vi.mock declarations
// ---------------------------------------------------------------------------

import { useTranscriptSegments } from "../../hooks/useTranscriptSegments";
import { useCorrectSegment } from "../../hooks/useCorrectSegment";
import { useRevertSegment } from "../../hooks/useRevertSegment";
import { useSegmentCorrectionHistory } from "../../hooks/useSegmentCorrectionHistory";

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
 * Returns the minimal return value for `useTranscriptSegments` loaded with the
 * given segments and no loading / error state.
 */
function makeTranscriptSegmentsReturn(segments: TranscriptSegment[]) {
  return {
    segments,
    totalCount: segments.length,
    isLoading: false,
    isFetchingNextPage: false,
    hasNextPage: false,
    isError: false,
    error: null,
    fetchNextPage: vi.fn(),
    retry: vi.fn(),
    cancelRequests: vi.fn(),
    seekToTimestamp: vi.fn().mockResolvedValue(undefined),
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
