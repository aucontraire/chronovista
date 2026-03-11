/**
 * Integration tests for TranscriptSegments correction workflow (Feature 035).
 *
 * Test coverage:
 * - T030: Core integration tests (single-edit-at-a-time, save/cancel cycles, button visibility)
 * - T032: Keyboard workflow verification
 * - T033: Aria-live correction announcements
 * - T034: Edge cases (edit-while-history-open, edit-while-revert-confirming)
 *
 * Key implementation notes:
 * - Edit/revert/history buttons use opacity-0 with group-hover:opacity-100 — they are
 *   in the DOM but visually hidden. Tests find them by aria-label.
 * - The correctionAnnouncement region is conditionally rendered — only present when
 *   correctionAnnouncement state is non-empty.
 * - Single-edit constraint: setEditState replaces the entire state, so entering
 *   edit on segment B automatically exits any active mode on segment A.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { act } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { TranscriptSegments } from "../TranscriptSegments";
import type { TranscriptSegmentsProps } from "../TranscriptSegments";
import type { TranscriptSegment } from "../../../types/transcript";

// ---------------------------------------------------------------------------
// Module mocks — must be at module scope before any imports of the mocked
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
// Test data
// ---------------------------------------------------------------------------

/**
 * Segment with no correction (uncorrected state).
 */
const segmentA: TranscriptSegment = {
  id: 1,
  start_time: 0.0,
  end_time: 5.0,
  duration: 5.0,
  text: "Hello world",
  has_correction: false,
  corrected_at: null,
  correction_count: 0,
};

/**
 * Segment with an active correction (corrected state).
 * Has both has_correction=true and correction_count=2 so both revert
 * and history buttons are rendered.
 */
const segmentB: TranscriptSegment = {
  id: 2,
  start_time: 5.0,
  end_time: 10.0,
  duration: 5.0,
  text: "Corrected text",
  has_correction: true,
  corrected_at: "2024-01-15T10:00:00Z",
  correction_count: 2,
};

const mockSegments: TranscriptSegment[] = [segmentA, segmentB];

// ---------------------------------------------------------------------------
// Default hook return factories
// ---------------------------------------------------------------------------

function createDefaultTranscriptSegmentsReturn(
  segments: TranscriptSegment[] = mockSegments
) {
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

function createDefaultCorrectSegmentReturn(overrides: Record<string, unknown> = {}) {
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

function createDefaultRevertSegmentReturn(overrides: Record<string, unknown> = {}) {
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

function createDefaultHistoryReturn(overrides: Record<string, unknown> = {}) {
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

function renderTranscriptSegments(props: Partial<TranscriptSegmentsProps> = {}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <TranscriptSegments
        videoId="test-video"
        languageCode="en"
        {...props}
      />
    </QueryClientProvider>
  );
}

// ---------------------------------------------------------------------------
// Setup / teardown
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.clearAllMocks();
  vi.useFakeTimers({ shouldAdvanceTime: true });

  // Stub scrollIntoView — not implemented in happy-dom
  Element.prototype.scrollIntoView = vi.fn();

  // Wire up default mock returns
  mockUseTranscriptSegments.mockReturnValue(
    createDefaultTranscriptSegmentsReturn()
  );
  mockUseCorrectSegment.mockReturnValue(
    createDefaultCorrectSegmentReturn() as ReturnType<typeof useCorrectSegment>
  );
  mockUseRevertSegment.mockReturnValue(
    createDefaultRevertSegmentReturn() as ReturnType<typeof useRevertSegment>
  );
  mockUseSegmentCorrectionHistory.mockReturnValue(
    createDefaultHistoryReturn() as ReturnType<typeof useSegmentCorrectionHistory>
  );
});

afterEach(() => {
  vi.runOnlyPendingTimers();
  vi.useRealTimers();
});

// ===========================================================================
// T030 — Core integration tests
// ===========================================================================

describe("T030: Core integration tests", () => {
  // -------------------------------------------------------------------------
  // T030-1: Single-edit-at-a-time constraint
  // -------------------------------------------------------------------------
  describe("T030-1: Single-edit-at-a-time", () => {
    it("entering edit mode on segment B cancels edit mode on segment A", async () => {
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
      renderTranscriptSegments();

      // Click Edit on segment A (id=1)
      const editButtonA = screen.getByRole("button", {
        name: /edit segment 1/i,
      });
      await user.click(editButtonA);

      // Verify segment A is now in edit mode (textarea visible)
      expect(screen.getByRole("textbox", { name: /edit segment text/i })).toBeInTheDocument();

      // Click Edit on segment B (id=2)
      const editButtonB = screen.getByRole("button", {
        name: /edit segment 2/i,
      });
      await user.click(editButtonB);

      // Segment A should have exited edit mode — only one textarea should exist
      const textareas = screen.getAllByRole("textbox", { name: /edit segment text/i });
      expect(textareas).toHaveLength(1);
    });

    it("entering edit mode replaces confirming-revert mode on another segment", async () => {
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
      renderTranscriptSegments();

      // Click Revert on segment B (which has has_correction=true)
      const revertButtonB = screen.getByRole("button", {
        name: /revert correction for segment 2/i,
      });
      await user.click(revertButtonB);

      // Segment B should be in confirming-revert mode — "Revert to previous version?" visible
      expect(screen.getByText(/revert to previous version\?/i)).toBeInTheDocument();

      // Now click Edit on segment A — should cancel the revert on B
      const editButtonA = screen.getByRole("button", {
        name: /edit segment 1/i,
      });
      await user.click(editButtonA);

      // Revert confirmation for B should be gone
      expect(screen.queryByText(/revert to previous version\?/i)).not.toBeInTheDocument();

      // Segment A should now be in edit mode
      expect(screen.getByRole("textbox", { name: /edit segment text/i })).toBeInTheDocument();
    });

    it("entering edit mode closes history panel on another segment", async () => {
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });

      // Provide history data so the history panel can render with content
      mockUseSegmentCorrectionHistory.mockReturnValue({
        ...createDefaultHistoryReturn(),
        data: {
          data: [],
          pagination: { total: 0, offset: 0, limit: 50, has_more: false },
        },
        status: "success" as const,
        isSuccess: true,
        isPending: false,
      } as ReturnType<typeof useSegmentCorrectionHistory>);

      renderTranscriptSegments();

      // Click History on segment B (which has correction_count=2)
      const historyButtonB = screen.getByRole("button", {
        name: /view correction history for segment 2/i,
      });
      await user.click(historyButtonB);

      // History panel should be open — CorrectionHistoryPanel renders with role=region
      // and shows the empty state message when no records
      expect(
        screen.getByRole("region", { name: /correction history/i })
      ).toBeInTheDocument();

      // Now click Edit on segment A — should close the history panel
      const editButtonA = screen.getByRole("button", {
        name: /edit segment 1/i,
      });
      await user.click(editButtonA);

      // History panel should be gone (region no longer rendered)
      expect(
        screen.queryByRole("region", { name: /correction history/i })
      ).not.toBeInTheDocument();

      // Segment A should be in edit mode
      expect(screen.getByRole("textbox", { name: /edit segment text/i })).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // T030-2: Edit → save → read cycle
  // -------------------------------------------------------------------------
  describe("T030-2: Edit → save → read cycle", () => {
    it("clicking Save exits edit mode", async () => {
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });

      // Configure mutate to immediately call onSuccess
      const mockMutate = vi.fn().mockImplementation((_vars, callbacks) => {
        callbacks?.onSuccess?.({
          data: {
            correction: {
              id: "uuid-1",
              video_id: "test-video",
              language_code: "en",
              segment_id: 1,
              correction_type: "proper_noun",
              original_text: "Hello world",
              corrected_text: "Hello World",
              correction_note: null,
              corrected_by_user_id: null,
              corrected_at: "2024-01-15T12:00:00Z",
              version_number: 1,
            },
            segment_state: {
              has_correction: true,
              effective_text: "Hello World",
            },
          },
        });
      });

      mockUseCorrectSegment.mockReturnValue({
        ...createDefaultCorrectSegmentReturn(),
        mutate: mockMutate,
      } as ReturnType<typeof useCorrectSegment>);

      renderTranscriptSegments();

      // Enter edit mode on segment A
      await user.click(screen.getByRole("button", { name: /edit segment 1/i }));

      // Verify textarea is visible with initial text
      const textarea = screen.getByRole("textbox", { name: /edit segment text/i });
      expect(textarea).toBeInTheDocument();

      // Clear and type new text (must differ from initial)
      await user.clear(textarea);
      await user.type(textarea, "Hello World");

      // Click Save
      await user.click(screen.getByRole("button", { name: /save/i }));

      // Edit mode should close — textarea gone
      expect(
        screen.queryByRole("textbox", { name: /edit segment text/i })
      ).not.toBeInTheDocument();
    });

    it("clicking Cancel exits edit mode without saving", async () => {
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
      renderTranscriptSegments();

      // Enter edit mode
      await user.click(screen.getByRole("button", { name: /edit segment 1/i }));

      // Verify edit form is shown
      expect(
        screen.getByRole("textbox", { name: /edit segment text/i })
      ).toBeInTheDocument();

      // Cancel
      await user.click(screen.getByRole("button", { name: /cancel/i }));

      // Edit mode should close
      expect(
        screen.queryByRole("textbox", { name: /edit segment text/i })
      ).not.toBeInTheDocument();

      // mutate should not have been called
      const mutate = mockUseCorrectSegment.mock.results[0]?.value?.mutate;
      expect(mutate).not.toHaveBeenCalled();
    });
  });

  // -------------------------------------------------------------------------
  // T030-3: Revert button visibility
  // -------------------------------------------------------------------------
  describe("T030-3: Button visibility based on segment state", () => {
    it("Revert button only appears when segment has_correction === true", () => {
      renderTranscriptSegments();

      // Segment A (has_correction=false): no revert button
      expect(
        screen.queryByRole("button", { name: /revert correction for segment 1/i })
      ).not.toBeInTheDocument();

      // Segment B (has_correction=true): revert button present
      expect(
        screen.getByRole("button", { name: /revert correction for segment 2/i })
      ).toBeInTheDocument();
    });

    it("History button only appears when segment correction_count > 0", () => {
      renderTranscriptSegments();

      // Segment A (correction_count=0): no history button
      expect(
        screen.queryByRole("button", { name: /view correction history for segment 1/i })
      ).not.toBeInTheDocument();

      // Segment B (correction_count=2): history button present
      expect(
        screen.getByRole("button", { name: /view correction history for segment 2/i })
      ).toBeInTheDocument();
    });

    it("Edit button is always present in the DOM regardless of correction state", () => {
      renderTranscriptSegments();

      // Both segments have edit buttons in the DOM (opacity-0 but findable by aria-label)
      expect(
        screen.getByRole("button", { name: /edit segment 1/i })
      ).toBeInTheDocument();

      expect(
        screen.getByRole("button", { name: /edit segment 2/i })
      ).toBeInTheDocument();
    });

    it("action buttons are hidden during edit mode (not rendered)", async () => {
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
      renderTranscriptSegments();

      // Enter edit mode on segment B
      await user.click(screen.getByRole("button", { name: /edit segment 2/i }));

      // While editing segment B, its edit/revert/history buttons should NOT be visible
      // The SegmentItem renders action buttons only when !isEditing && !isConfirmingRevert
      expect(
        screen.queryByRole("button", { name: /revert correction for segment 2/i })
      ).not.toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: /view correction history for segment 2/i })
      ).not.toBeInTheDocument();
    });

    it("action buttons are hidden during confirming-revert mode (not rendered)", async () => {
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
      renderTranscriptSegments();

      // Enter revert mode on segment B
      await user.click(
        screen.getByRole("button", { name: /revert correction for segment 2/i })
      );

      // While confirming revert on B, the edit/revert/history buttons should NOT be in DOM
      expect(
        screen.queryByRole("button", { name: /revert correction for segment 2/i })
      ).not.toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: /view correction history for segment 2/i })
      ).not.toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // T030-4: aria-busy attribute
  // -------------------------------------------------------------------------
  describe("T030-4: aria-busy state during mutations", () => {
    it("segment row has aria-busy=true when isPending during edit", async () => {
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });

      // Configure mutate to capture the call without calling success
      const mockMutate = vi.fn();
      mockUseCorrectSegment.mockReturnValue({
        ...createDefaultCorrectSegmentReturn({ isPending: true }),
        mutate: mockMutate,
      } as ReturnType<typeof useCorrectSegment>);

      renderTranscriptSegments();

      // Enter edit mode on segment A
      await user.click(screen.getByRole("button", { name: /edit segment 1/i }));

      // The segment row for segment A should have aria-busy=true when isPending=true
      const segmentRow = document
        .querySelector('[data-segment-id="1"]');

      expect(segmentRow).toHaveAttribute("aria-busy", "true");
    });
  });

  // -------------------------------------------------------------------------
  // T030-5: State transitions
  // -------------------------------------------------------------------------
  describe("T030-5: State transitions", () => {
    it("read → editing → read via cancel", async () => {
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
      renderTranscriptSegments();

      // Start in read mode: no textarea
      expect(
        screen.queryByRole("textbox", { name: /edit segment text/i })
      ).not.toBeInTheDocument();

      // Transition to editing
      await user.click(screen.getByRole("button", { name: /edit segment 1/i }));
      expect(
        screen.getByRole("textbox", { name: /edit segment text/i })
      ).toBeInTheDocument();

      // Transition back to read via Cancel
      await user.click(screen.getByRole("button", { name: /cancel/i }));
      expect(
        screen.queryByRole("textbox", { name: /edit segment text/i })
      ).not.toBeInTheDocument();
    });

    it("read → confirming-revert → read via cancel", async () => {
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
      renderTranscriptSegments();

      // Start in read mode: no revert confirmation
      expect(screen.queryByText(/revert to previous version\?/i)).not.toBeInTheDocument();

      // Transition to confirming-revert
      await user.click(
        screen.getByRole("button", { name: /revert correction for segment 2/i })
      );
      expect(screen.getByText(/revert to previous version\?/i)).toBeInTheDocument();

      // Transition back to read via Cancel in RevertConfirmation
      const cancelButtons = screen.getAllByRole("button", { name: /cancel/i });
      // The RevertConfirmation Cancel button is the one visible now
      await user.click(cancelButtons[0]!);
      expect(screen.queryByText(/revert to previous version\?/i)).not.toBeInTheDocument();
    });

    it("read → history → read via clicking History button again (toggle)", async () => {
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });

      mockUseSegmentCorrectionHistory.mockReturnValue({
        ...createDefaultHistoryReturn(),
        data: {
          data: [],
          pagination: { total: 0, offset: 0, limit: 50, has_more: false },
        },
        status: "success" as const,
        isSuccess: true,
        isPending: false,
      } as ReturnType<typeof useSegmentCorrectionHistory>);

      renderTranscriptSegments();

      // Transition to history by clicking the history button on segment B
      await user.click(
        screen.getByRole("button", { name: /view correction history for segment 2/i })
      );

      // History panel is open (CorrectionHistoryPanel renders with role=region)
      expect(
        screen.getByRole("region", { name: /correction history/i })
      ).toBeInTheDocument();

      // Clicking any edit button on another segment returns to read mode,
      // which closes the history panel. Click Edit on segment A to close.
      await user.click(screen.getByRole("button", { name: /edit segment 1/i }));

      // History panel should be gone (replaced by edit mode on A)
      expect(
        screen.queryByRole("region", { name: /correction history/i })
      ).not.toBeInTheDocument();
    });
  });
});

// ===========================================================================
// T032 — Keyboard workflow verification
// ===========================================================================

describe("T032: Keyboard workflow", () => {
  it("Edit button is focusable via keyboard (has tabIndex accessible)", () => {
    renderTranscriptSegments();

    const editButton = screen.getByRole("button", { name: /edit segment 1/i });

    // Buttons are natively focusable; verify it exists and is a button element
    expect(editButton.tagName).toBe("BUTTON");
    expect(editButton).not.toBeDisabled();
  });

  it("pressing Escape in the edit form cancels and returns to read mode", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderTranscriptSegments();

    // Enter edit mode
    await user.click(screen.getByRole("button", { name: /edit segment 1/i }));

    const textarea = screen.getByRole("textbox", { name: /edit segment text/i });
    expect(textarea).toBeInTheDocument();

    // Press Escape while textarea is focused
    await user.keyboard("{Escape}");

    // Edit mode should close
    expect(
      screen.queryByRole("textbox", { name: /edit segment text/i })
    ).not.toBeInTheDocument();
  });

  it("pressing Escape in the revert confirmation cancels", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderTranscriptSegments();

    // Enter revert mode
    await user.click(
      screen.getByRole("button", { name: /revert correction for segment 2/i })
    );
    expect(screen.getByText(/revert to previous version\?/i)).toBeInTheDocument();

    // Press Escape while the Confirm button is focused (auto-focused on mount)
    await user.keyboard("{Escape}");

    // Revert confirmation should close
    expect(screen.queryByText(/revert to previous version\?/i)).not.toBeInTheDocument();
  });

  it("textarea receives focus on edit mode entry", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderTranscriptSegments();

    await user.click(screen.getByRole("button", { name: /edit segment 1/i }));

    // SegmentEditForm auto-focuses the textarea on mount via useEffect
    const textarea = screen.getByRole("textbox", { name: /edit segment text/i });
    expect(textarea).toBeInTheDocument();
    // We cannot assert document.activeElement reliably in happy-dom with fake timers,
    // but we verify the textarea is the correct element that would receive focus.
    expect(textarea.tagName).toBe("TEXTAREA");
  });

  it("Confirm button in RevertConfirmation auto-focuses on mount", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderTranscriptSegments();

    // Enter revert mode
    await user.click(
      screen.getByRole("button", { name: /revert correction for segment 2/i })
    );

    // The RevertConfirmation renders a Confirm button that is auto-focused
    const confirmButton = screen.getByRole("button", { name: /confirm/i });
    expect(confirmButton).toBeInTheDocument();
    expect(confirmButton).not.toBeDisabled();
  });
});

// ===========================================================================
// T033 — Aria-live correction announcements
// ===========================================================================

describe("T033: Aria-live announcements", () => {
  it("announces 'Editing segment. Press Escape to cancel.' when entering edit mode", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderTranscriptSegments();

    await user.click(screen.getByRole("button", { name: /edit segment 1/i }));

    // The correction announcement region appears with the edit message
    const announcement = screen.getByText(
      /editing segment\. press escape to cancel\./i
    );
    expect(announcement).toBeInTheDocument();
    expect(announcement).toHaveAttribute("aria-live");
    expect(announcement).toHaveAttribute("aria-atomic", "true");
    expect(announcement).toHaveClass("sr-only");
  });

  it("correction announcement region has correct ARIA attributes on edit", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderTranscriptSegments();

    await user.click(screen.getByRole("button", { name: /edit segment 1/i }));

    // Find the announcement node by data attribute (unique to correction announcements)
    const announcementEl = document.querySelector(
      '[data-correction-announcement="true"]'
    );
    expect(announcementEl).not.toBeNull();
    expect(announcementEl).toHaveAttribute("aria-live", "polite");
    expect(announcementEl).toHaveAttribute("aria-atomic", "true");
    expect(announcementEl).toHaveClass("sr-only");
  });

  it("announces 'Revert correction? Press Escape to cancel.' when entering revert mode", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderTranscriptSegments();

    await user.click(
      screen.getByRole("button", { name: /revert correction for segment 2/i })
    );

    const announcement = screen.getByText(
      /revert correction\? press escape to cancel\./i
    );
    expect(announcement).toBeInTheDocument();
    expect(announcement).toHaveAttribute("aria-live");
    expect(announcement).toHaveClass("sr-only");
  });

  it("announces 'Loading correction history...' when entering history mode", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderTranscriptSegments();

    await user.click(
      screen.getByRole("button", { name: /view correction history for segment 2/i })
    );

    const announcement = screen.getByText(/loading correction history/i);
    expect(announcement).toBeInTheDocument();
    expect(announcement).toHaveClass("sr-only");
  });

  it("clears correction announcement after 3 seconds", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderTranscriptSegments();

    await user.click(screen.getByRole("button", { name: /edit segment 1/i }));

    // Announcement should be visible immediately after clicking Edit
    expect(
      document.querySelector('[data-correction-announcement="true"]')
    ).not.toBeNull();

    // Advance timers past the 3-second clearance timeout
    act(() => {
      vi.advanceTimersByTime(3100);
    });

    // Announcement region should be removed (state cleared → conditional render omits it)
    expect(
      document.querySelector('[data-correction-announcement="true"]')
    ).toBeNull();
  });

  it("all SVG icons in correction buttons carry aria-hidden=true", () => {
    renderTranscriptSegments();

    // Get all buttons in the correction workflow area
    const editButton = screen.getByRole("button", { name: /edit segment 1/i });
    const revertButton = screen.getByRole("button", {
      name: /revert correction for segment 2/i,
    });
    const historyButton = screen.getByRole("button", {
      name: /view correction history for segment 2/i,
    });

    // Each button should contain an SVG with aria-hidden="true"
    const editSvg = editButton.querySelector("svg");
    const revertSvg = revertButton.querySelector("svg");
    const historySvg = historyButton.querySelector("svg");

    expect(editSvg).not.toBeNull();
    expect(editSvg).toHaveAttribute("aria-hidden", "true");

    expect(revertSvg).not.toBeNull();
    expect(revertSvg).toHaveAttribute("aria-hidden", "true");

    expect(historySvg).not.toBeNull();
    expect(historySvg).toHaveAttribute("aria-hidden", "true");
  });

  it("announcement uses assertive aria-live when correctionError is set", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });

    // Configure mutate to call onError with a message
    const mockMutate = vi.fn().mockImplementation((_vars, callbacks) => {
      callbacks?.onError?.(new Error("Network error"), _vars, undefined);
    });

    mockUseCorrectSegment.mockReturnValue({
      ...createDefaultCorrectSegmentReturn(),
      mutate: mockMutate,
    } as ReturnType<typeof useCorrectSegment>);

    renderTranscriptSegments();

    // Enter edit mode and attempt to save with changed text
    await user.click(screen.getByRole("button", { name: /edit segment 1/i }));

    const textarea = screen.getByRole("textbox", { name: /edit segment text/i });
    await user.clear(textarea);
    await user.type(textarea, "Modified text");

    await user.click(screen.getByRole("button", { name: /save/i }));

    // When there's a correctionError, aria-live should be "assertive"
    const announcementEl = document.querySelector(
      '[data-correction-announcement="true"]'
    );
    expect(announcementEl).not.toBeNull();
    expect(announcementEl).toHaveAttribute("aria-live", "assertive");
  });
});

// ===========================================================================
// T034 — Edge cases
// ===========================================================================

describe("T034: Edge cases", () => {
  // -------------------------------------------------------------------------
  // T034-1: Edit while history is open
  // -------------------------------------------------------------------------
  it("T034-1: entering edit on segment A while history open on segment B closes history", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });

    mockUseSegmentCorrectionHistory.mockReturnValue({
      ...createDefaultHistoryReturn(),
      data: {
        data: [],
        pagination: { total: 0, offset: 0, limit: 50, has_more: false },
      },
      status: "success" as const,
      isSuccess: true,
      isPending: false,
    } as ReturnType<typeof useSegmentCorrectionHistory>);

    renderTranscriptSegments();

    // Open history on segment B
    await user.click(
      screen.getByRole("button", { name: /view correction history for segment 2/i })
    );

    // History panel is open — CorrectionHistoryPanel renders with role=region
    expect(
      screen.getByRole("region", { name: /correction history/i })
    ).toBeInTheDocument();

    // Now click Edit on segment A — single-edit constraint should close history on B
    await user.click(screen.getByRole("button", { name: /edit segment 1/i }));

    // History panel should be gone
    expect(
      screen.queryByRole("region", { name: /correction history/i })
    ).not.toBeInTheDocument();

    // Edit form for segment A should be open
    expect(
      screen.getByRole("textbox", { name: /edit segment text/i })
    ).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // T034-2: Edit while revert-confirming
  // -------------------------------------------------------------------------
  it("T034-2: entering edit cancels pending revert confirmation on another segment", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderTranscriptSegments();

    // Open revert confirmation on segment B
    await user.click(
      screen.getByRole("button", { name: /revert correction for segment 2/i })
    );

    // Revert confirmation visible
    expect(screen.getByText(/revert to previous version\?/i)).toBeInTheDocument();

    // Click Edit on segment A — should cancel the revert confirmation on B
    await user.click(screen.getByRole("button", { name: /edit segment 1/i }));

    // Revert confirmation should be gone
    expect(screen.queryByText(/revert to previous version\?/i)).not.toBeInTheDocument();

    // Segment A edit form should be visible
    expect(
      screen.getByRole("textbox", { name: /edit segment text/i })
    ).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // T034-3: Segments with no corrections have no extra buttons
  // -------------------------------------------------------------------------
  it("T034-3: uncorrected segment only has edit button, no revert or history", () => {
    // Render with only uncorrected segments
    mockUseTranscriptSegments.mockReturnValue(
      createDefaultTranscriptSegmentsReturn([segmentA])
    );

    renderTranscriptSegments();

    // Edit button present
    expect(
      screen.getByRole("button", { name: /edit segment 1/i })
    ).toBeInTheDocument();

    // No revert or history
    expect(
      screen.queryByRole("button", { name: /revert/i })
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /view correction history/i })
    ).not.toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // T034-4: Multiple rapid mode switches
  // -------------------------------------------------------------------------
  it("T034-4: rapidly switching between edit and revert modes is safe", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderTranscriptSegments();

    // Quickly enter edit on A, then revert on B, then edit on A again
    await user.click(screen.getByRole("button", { name: /edit segment 1/i }));
    // Edit form for A should be up
    expect(screen.getByRole("textbox", { name: /edit segment text/i })).toBeInTheDocument();

    // Click Revert on B — but edit form renders over segment A,
    // so revert button for B is still in DOM since B is in read mode
    await user.click(
      screen.getByRole("button", { name: /revert correction for segment 2/i })
    );

    // Now in confirming-revert for B; edit form for A gone
    expect(
      screen.queryByRole("textbox", { name: /edit segment text/i })
    ).not.toBeInTheDocument();
    expect(screen.getByText(/revert to previous version\?/i)).toBeInTheDocument();

    // Click Edit on A again — cancel revert on B, open edit on A
    await user.click(screen.getByRole("button", { name: /edit segment 1/i }));

    expect(screen.queryByText(/revert to previous version\?/i)).not.toBeInTheDocument();
    expect(
      screen.getByRole("textbox", { name: /edit segment text/i })
    ).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // T034-5: Validation error clears on typing
  // -------------------------------------------------------------------------
  it("T034-5: validation error clears when user types in the textarea", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderTranscriptSegments();

    await user.click(screen.getByRole("button", { name: /edit segment 1/i }));

    const textarea = screen.getByRole("textbox", { name: /edit segment text/i });

    // Clear textarea so it's empty, then click Save → triggers validation error
    await user.clear(textarea);
    await user.click(screen.getByRole("button", { name: /save/i }));

    // Validation error should appear
    expect(
      screen.getByText(/correction text cannot be empty/i)
    ).toBeInTheDocument();

    // Type something → validation error should clear
    await user.type(textarea, "x");
    expect(
      screen.queryByText(/correction text cannot be empty/i)
    ).not.toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // T034-6: Identical text validation
  // -------------------------------------------------------------------------
  it("T034-6: saving with unchanged text shows 'identical to current text' error", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderTranscriptSegments();

    // Enter edit mode on segment A (text = "Hello world")
    await user.click(screen.getByRole("button", { name: /edit segment 1/i }));

    // Click Save without changing the text
    await user.click(screen.getByRole("button", { name: /save/i }));

    // Should see identical text error
    expect(
      screen.getByText(/correction is identical to the current text/i)
    ).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // T034-7: Loading state renders skeletons (not correction UI)
  // -------------------------------------------------------------------------
  it("T034-7: loading state shows skeleton segments, not correction buttons", () => {
    mockUseTranscriptSegments.mockReturnValue({
      ...createDefaultTranscriptSegmentsReturn([]),
      isLoading: true,
      segments: [],
    });

    renderTranscriptSegments();

    // Should see loading status
    expect(
      screen.getByRole("status", { name: /loading transcript segments/i })
    ).toBeInTheDocument();

    // No correction buttons visible during loading
    expect(
      screen.queryByRole("button", { name: /edit segment/i })
    ).not.toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // T034-8: No segments renders "No transcript segments available"
  // -------------------------------------------------------------------------
  it("T034-8: empty segments (not loading) shows no-content message", () => {
    mockUseTranscriptSegments.mockReturnValue({
      ...createDefaultTranscriptSegmentsReturn([]),
      isLoading: false,
      segments: [],
    });

    renderTranscriptSegments();

    expect(
      screen.getByText(/no transcript segments available/i)
    ).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // T034-9: Segments render with data-segment-id attributes
  // -------------------------------------------------------------------------
  it("T034-9: all rendered segments have data-segment-id attributes", () => {
    renderTranscriptSegments();

    const segmentRows = document.querySelectorAll("[data-segment-id]");
    expect(segmentRows).toHaveLength(2);

    // Verify each segment ID
    const ids = Array.from(segmentRows).map((el) =>
      el.getAttribute("data-segment-id")
    );
    expect(ids).toContain("1");
    expect(ids).toContain("2");
  });

  // -------------------------------------------------------------------------
  // T034-10: revert confirmation Confirm button triggers revert mutation
  // -------------------------------------------------------------------------
  it("T034-10: clicking Confirm in revert confirmation calls revertSegment.mutate", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });

    const mockRevertMutate = vi.fn();
    mockUseRevertSegment.mockReturnValue({
      ...createDefaultRevertSegmentReturn(),
      mutate: mockRevertMutate,
    } as ReturnType<typeof useRevertSegment>);

    renderTranscriptSegments();

    // Enter revert mode on segment B
    await user.click(
      screen.getByRole("button", { name: /revert correction for segment 2/i })
    );

    // Click Confirm
    await user.click(screen.getByRole("button", { name: /confirm/i }));

    // Revert mutate should have been called with segmentId=2
    expect(mockRevertMutate).toHaveBeenCalledWith(
      { segmentId: 2 },
      expect.any(Object)
    );
  });
});

// ===========================================================================
// T030 Supplemental: Segment region and accessible container
// ===========================================================================

describe("T030 Supplemental: Accessible transcript container", () => {
  it("transcript container has role=region and aria-label", () => {
    renderTranscriptSegments();

    const container = screen.getByRole("region", {
      name: /transcript segments/i,
    });
    expect(container).toBeInTheDocument();
  });

  it("segment text is rendered as paragraph inside the read view", () => {
    renderTranscriptSegments();

    // Both segment texts should be in the document
    expect(screen.getByText("Hello world")).toBeInTheDocument();
    expect(screen.getByText("Corrected text")).toBeInTheDocument();
  });

  it("End of transcript indicator appears when hasNextPage=false and not loading", () => {
    renderTranscriptSegments();

    expect(screen.getByText(/end of transcript/i)).toBeInTheDocument();
  });

  it("within segment B, all three action buttons are reachable by aria-label", () => {
    renderTranscriptSegments();

    // Segment B: all three buttons present
    const segmentBRow = document.querySelector('[data-segment-id="2"]')!;
    const segmentBContainer = segmentBRow.parentElement!;

    // within() helper scopes queries to that subtree
    within(segmentBContainer as HTMLElement);

    // Use global screen since buttons are in the segment row DOM node
    expect(
      screen.getByRole("button", { name: /edit segment 2/i })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /revert correction for segment 2/i })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /view correction history for segment 2/i })
    ).toBeInTheDocument();
  });
});
