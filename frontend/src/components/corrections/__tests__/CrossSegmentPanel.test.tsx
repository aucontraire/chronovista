/**
 * Tests for CrossSegmentPanel component.
 *
 * Coverage:
 * - Renders loading state initially (skeleton)
 * - Renders candidate cards with data
 * - Clicking a candidate calls prefillForm with correct values (crossSegment: true)
 * - Shows inline notice after pre-fill
 * - Notice auto-dismisses after 3 seconds
 * - Notice dismiss button hides notice immediately
 * - Empty state when no candidates
 * - Confidence displayed as percentage
 * - Partial-correction badge shown when is_partially_corrected is true
 * - Candidates ranked by confidence (highest first)
 * - Keyboard accessible: Enter triggers prefillForm
 * - Keyboard accessible: Space triggers prefillForm
 * - Error state renders alert when fetch fails
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { CrossSegmentPanel } from "../CrossSegmentPanel";
import { useCrossSegmentCandidates } from "../../../hooks/useCrossSegmentCandidates";
import type { CrossSegmentCandidate } from "../../../types/corrections";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock("../../../hooks/useCrossSegmentCandidates", () => ({
  useCrossSegmentCandidates: vi.fn(),
}));

const mockedUseHook = vi.mocked(useCrossSegmentCandidates);

// ---------------------------------------------------------------------------
// Test fixtures
// ---------------------------------------------------------------------------

function makeCandidate(overrides: Partial<CrossSegmentCandidate> = {}): CrossSegmentCandidate {
  return {
    segment_n_id: 1,
    segment_n_text: "the senator said",
    segment_n1_id: 2,
    segment_n1_text: "bernie would win",
    proposed_correction: "Bernie",
    source_pattern: "bernie",
    confidence: 0.85,
    is_partially_corrected: false,
    video_id: "video-uuid-001",
    discovery_source: "correction_pattern",
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Default hook return stubs
// ---------------------------------------------------------------------------

function makeIdleHook(): ReturnType<typeof useCrossSegmentCandidates> {
  return {
    data: undefined,
    isLoading: false,
    isFetching: false,
    isError: false,
    isSuccess: false,
    error: null,
    status: "pending",
    fetchStatus: "idle",
    isPending: true,
    isRefetching: false,
    isRefetchError: false,
    isLoadingError: false,
    isStale: false,
    isPlaceholderData: false,
    dataUpdatedAt: 0,
    errorUpdatedAt: 0,
    errorUpdateCount: 0,
    failureCount: 0,
    failureReason: null,
    refetch: vi.fn(),
    promise: Promise.resolve([]),
  } as unknown as ReturnType<typeof useCrossSegmentCandidates>;
}

function makeLoadingHook(): ReturnType<typeof useCrossSegmentCandidates> {
  return {
    ...makeIdleHook(),
    isLoading: true,
    isPending: true,
    status: "pending",
    fetchStatus: "fetching",
  } as unknown as ReturnType<typeof useCrossSegmentCandidates>;
}

function makeSuccessHook(
  data: CrossSegmentCandidate[]
): ReturnType<typeof useCrossSegmentCandidates> {
  return {
    ...makeIdleHook(),
    data,
    isLoading: false,
    isSuccess: true,
    isPending: false,
    status: "success",
    fetchStatus: "idle",
  } as unknown as ReturnType<typeof useCrossSegmentCandidates>;
}

function makeErrorHook(): ReturnType<typeof useCrossSegmentCandidates> {
  return {
    ...makeIdleHook(),
    data: undefined,
    isLoading: false,
    isError: true,
    isPending: false,
    error: new Error("Network error"),
    status: "error",
    fetchStatus: "idle",
  } as unknown as ReturnType<typeof useCrossSegmentCandidates>;
}

// ---------------------------------------------------------------------------
// Render helper
// ---------------------------------------------------------------------------

function renderPanel(prefillForm = vi.fn()) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <CrossSegmentPanel prefillForm={prefillForm} />
    </QueryClientProvider>
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("CrossSegmentPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  // -------------------------------------------------------------------------
  // Section header
  // -------------------------------------------------------------------------

  it("renders the section heading", () => {
    mockedUseHook.mockReturnValue(makeSuccessHook([]));
    renderPanel();
    expect(
      screen.getByRole("heading", { name: /suggested cross-segment candidates/i, level: 2 })
    ).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Loading state
  // -------------------------------------------------------------------------

  it("renders loading skeleton when isLoading is true", () => {
    mockedUseHook.mockReturnValue(makeLoadingHook());
    renderPanel();
    expect(
      screen.getByRole("status", { name: /loading cross-segment candidates/i })
    ).toBeInTheDocument();
  });

  it("does not render candidate cards when loading", () => {
    mockedUseHook.mockReturnValue(makeLoadingHook());
    renderPanel();
    expect(screen.queryByRole("button", { name: /apply cross-segment correction/i })).not.toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Empty state
  // -------------------------------------------------------------------------

  it("renders empty state when no candidates exist", () => {
    mockedUseHook.mockReturnValue(makeSuccessHook([]));
    renderPanel();
    expect(
      screen.getByText(/no cross-segment candidates found/i)
    ).toBeInTheDocument();
  });

  it("does not render candidate cards in empty state", () => {
    mockedUseHook.mockReturnValue(makeSuccessHook([]));
    renderPanel();
    expect(screen.queryByRole("button", { name: /apply cross-segment correction/i })).not.toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Error state
  // -------------------------------------------------------------------------

  it("renders error alert when fetch fails", () => {
    mockedUseHook.mockReturnValue(makeErrorHook());
    renderPanel();
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText(/failed to load cross-segment candidates/i)).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Candidate rendering
  // -------------------------------------------------------------------------

  it("renders candidate cards with segment texts", () => {
    const candidate = makeCandidate({
      segment_n_text: "the senator said",
      segment_n1_text: "bernie would win",
    });
    mockedUseHook.mockReturnValue(makeSuccessHook([candidate]));
    renderPanel();

    expect(screen.getByText("the senator said")).toBeInTheDocument();
    expect(screen.getByText("bernie would win")).toBeInTheDocument();
  });

  it("renders source pattern and proposed correction on candidate cards", () => {
    const candidate = makeCandidate({
      source_pattern: "bernie",
      proposed_correction: "Bernie",
    });
    mockedUseHook.mockReturnValue(makeSuccessHook([candidate]));
    renderPanel();

    expect(screen.getAllByText("bernie").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Bernie").length).toBeGreaterThan(0);
  });

  it("renders confidence as a percentage", () => {
    const candidate = makeCandidate({ confidence: 0.85 });
    mockedUseHook.mockReturnValue(makeSuccessHook([candidate]));
    renderPanel();

    expect(screen.getByText(/85% confidence/i)).toBeInTheDocument();
  });

  it("rounds confidence to nearest integer percentage", () => {
    const candidate = makeCandidate({ confidence: 0.876 });
    mockedUseHook.mockReturnValue(makeSuccessHook([candidate]));
    renderPanel();

    expect(screen.getByText(/88% confidence/i)).toBeInTheDocument();
  });

  it("shows partial-correction badge when is_partially_corrected is true", () => {
    const candidate = makeCandidate({ is_partially_corrected: true });
    mockedUseHook.mockReturnValue(makeSuccessHook([candidate]));
    renderPanel();

    expect(screen.getByText("Partial")).toBeInTheDocument();
  });

  it("does not show partial-correction badge when is_partially_corrected is false", () => {
    const candidate = makeCandidate({ is_partially_corrected: false });
    mockedUseHook.mockReturnValue(makeSuccessHook([candidate]));
    renderPanel();

    expect(screen.queryByText("Partial")).not.toBeInTheDocument();
  });

  it("shows Entity badge when discovery_source is entity_alias", () => {
    const candidate = makeCandidate({ discovery_source: "entity_alias" });
    mockedUseHook.mockReturnValue(makeSuccessHook([candidate]));
    renderPanel();

    expect(screen.getByText("Entity")).toBeInTheDocument();
  });

  it("does not show Entity badge when discovery_source is correction_pattern", () => {
    const candidate = makeCandidate({ discovery_source: "correction_pattern" });
    mockedUseHook.mockReturnValue(makeSuccessHook([candidate]));
    renderPanel();

    expect(screen.queryByText("Entity")).not.toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Ranking by confidence
  // -------------------------------------------------------------------------

  it("renders candidates sorted by confidence descending (highest first)", () => {
    const candidates = [
      makeCandidate({ segment_n_id: 10, source_pattern: "low", confidence: 0.4 }),
      makeCandidate({ segment_n_id: 20, source_pattern: "high", confidence: 0.9 }),
      makeCandidate({ segment_n_id: 30, source_pattern: "mid", confidence: 0.7 }),
    ];
    mockedUseHook.mockReturnValue(makeSuccessHook(candidates));
    renderPanel();

    const cards = screen.getAllByRole("button", { name: /apply cross-segment correction/i });
    // Confidence is rendered as "confidence XX%" in the aria-label
    expect(cards[0]).toHaveAttribute(
      "aria-label",
      expect.stringContaining("confidence 90%")
    );
    expect(cards[1]).toHaveAttribute(
      "aria-label",
      expect.stringContaining("confidence 70%")
    );
    expect(cards[2]).toHaveAttribute(
      "aria-label",
      expect.stringContaining("confidence 40%")
    );
  });

  // -------------------------------------------------------------------------
  // Pre-fill on click
  // -------------------------------------------------------------------------

  it("calls prefillForm with correct values when a candidate is clicked", () => {
    const prefillForm = vi.fn();
    const candidate = makeCandidate({
      source_pattern: "bernie",
      proposed_correction: "Bernie",
    });
    mockedUseHook.mockReturnValue(makeSuccessHook([candidate]));
    renderPanel(prefillForm);

    fireEvent.click(
      screen.getByRole("button", { name: /apply cross-segment correction/i })
    );

    expect(prefillForm).toHaveBeenCalledTimes(1);
    expect(prefillForm).toHaveBeenCalledWith({
      pattern: "bernie",
      replacement: "Bernie",
      crossSegment: true,
    });
  });

  it("always passes crossSegment: true in prefillForm call", () => {
    const prefillForm = vi.fn();
    const candidate = makeCandidate({ is_partially_corrected: true });
    mockedUseHook.mockReturnValue(makeSuccessHook([candidate]));
    renderPanel(prefillForm);

    fireEvent.click(
      screen.getByRole("button", { name: /apply cross-segment correction/i })
    );

    expect(prefillForm).toHaveBeenCalledWith(
      expect.objectContaining({ crossSegment: true })
    );
  });

  // -------------------------------------------------------------------------
  // Keyboard accessibility
  // -------------------------------------------------------------------------

  it("calls prefillForm when Enter is pressed on a candidate card", () => {
    const prefillForm = vi.fn();
    const candidate = makeCandidate({
      source_pattern: "bernie",
      proposed_correction: "Bernie",
    });
    mockedUseHook.mockReturnValue(makeSuccessHook([candidate]));
    renderPanel(prefillForm);

    const card = screen.getByRole("button", { name: /apply cross-segment correction/i });
    fireEvent.keyDown(card, { key: "Enter" });

    expect(prefillForm).toHaveBeenCalledTimes(1);
    expect(prefillForm).toHaveBeenCalledWith({
      pattern: "bernie",
      replacement: "Bernie",
      crossSegment: true,
    });
  });

  it("calls prefillForm when Space is pressed on a candidate card", () => {
    const prefillForm = vi.fn();
    const candidate = makeCandidate({
      source_pattern: "bernie",
      proposed_correction: "Bernie",
    });
    mockedUseHook.mockReturnValue(makeSuccessHook([candidate]));
    renderPanel(prefillForm);

    const card = screen.getByRole("button", { name: /apply cross-segment correction/i });
    fireEvent.keyDown(card, { key: " " });

    expect(prefillForm).toHaveBeenCalledTimes(1);
  });

  it("does not call prefillForm for other key presses", () => {
    const prefillForm = vi.fn();
    const candidate = makeCandidate();
    mockedUseHook.mockReturnValue(makeSuccessHook([candidate]));
    renderPanel(prefillForm);

    const card = screen.getByRole("button", { name: /apply cross-segment correction/i });
    fireEvent.keyDown(card, { key: "Tab" });
    fireEvent.keyDown(card, { key: "Escape" });

    expect(prefillForm).not.toHaveBeenCalled();
  });

  it("candidate cards have tabIndex=0 for keyboard focusability", () => {
    const candidate = makeCandidate();
    mockedUseHook.mockReturnValue(makeSuccessHook([candidate]));
    renderPanel();

    const card = screen.getByRole("button", { name: /apply cross-segment correction/i });
    expect(card).toHaveAttribute("tabindex", "0");
  });

  // -------------------------------------------------------------------------
  // Inline notice
  // -------------------------------------------------------------------------

  it("shows inline notice after a candidate is clicked", () => {
    const candidate = makeCandidate();
    mockedUseHook.mockReturnValue(makeSuccessHook([candidate]));
    renderPanel();

    fireEvent.click(
      screen.getByRole("button", { name: /apply cross-segment correction/i })
    );

    expect(
      screen.getByText(/form updated with cross-segment pattern/i)
    ).toBeInTheDocument();
  });

  it("notice auto-dismisses after 3 seconds", () => {
    const candidate = makeCandidate();
    mockedUseHook.mockReturnValue(makeSuccessHook([candidate]));
    renderPanel();

    fireEvent.click(
      screen.getByRole("button", { name: /apply cross-segment correction/i })
    );

    expect(
      screen.getByText(/form updated with cross-segment pattern/i)
    ).toBeInTheDocument();

    // Advance fake timers past the 3-second auto-dismiss threshold.
    act(() => {
      vi.advanceTimersByTime(3001);
    });

    expect(
      screen.queryByText(/form updated with cross-segment pattern/i)
    ).not.toBeInTheDocument();
  });

  it("notice dismiss button hides notice immediately", () => {
    const candidate = makeCandidate();
    mockedUseHook.mockReturnValue(makeSuccessHook([candidate]));
    renderPanel();

    fireEvent.click(
      screen.getByRole("button", { name: /apply cross-segment correction/i })
    );

    expect(
      screen.getByText(/form updated with cross-segment pattern/i)
    ).toBeInTheDocument();

    // Click the dismiss (×) button — notice should vanish synchronously.
    fireEvent.click(screen.getByRole("button", { name: /dismiss notice/i }));

    expect(
      screen.queryByText(/form updated with cross-segment pattern/i)
    ).not.toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Multiple candidates
  // -------------------------------------------------------------------------

  it("renders all candidate cards when multiple candidates exist", () => {
    const candidates = [
      makeCandidate({ segment_n_id: 1, segment_n1_id: 2, source_pattern: "pattern-a", confidence: 0.9 }),
      makeCandidate({ segment_n_id: 3, segment_n1_id: 4, source_pattern: "pattern-b", confidence: 0.7 }),
    ];
    mockedUseHook.mockReturnValue(makeSuccessHook(candidates));
    renderPanel();

    const cards = screen.getAllByRole("button", { name: /apply cross-segment correction/i });
    expect(cards).toHaveLength(2);
  });

  it("calls prefillForm for the correct candidate when multiple candidates are shown", () => {
    const prefillForm = vi.fn();
    const candidates = [
      makeCandidate({
        segment_n_id: 1,
        segment_n1_id: 2,
        source_pattern: "alpha",
        proposed_correction: "Alpha",
        confidence: 0.9,
      }),
      makeCandidate({
        segment_n_id: 3,
        segment_n1_id: 4,
        source_pattern: "beta",
        proposed_correction: "Beta",
        confidence: 0.7,
      }),
    ];
    mockedUseHook.mockReturnValue(makeSuccessHook(candidates));
    renderPanel(prefillForm);

    // Click the second card (lower confidence = second in sorted order)
    const cards = screen.getAllByRole("button", { name: /apply cross-segment correction/i });
    fireEvent.click(cards[1]!);

    expect(prefillForm).toHaveBeenCalledWith({
      pattern: "beta",
      replacement: "Beta",
      crossSegment: true,
    });
  });
});
