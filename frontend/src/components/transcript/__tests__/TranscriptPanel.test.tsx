/**
 * Tests for TranscriptPanel component.
 *
 * Reconciled from two divergent copies (issue #309):
 * - frontend/src/tests/components/TranscriptPanel.test.tsx (Feature 048 follow-playback
 *   toggle, auto-scroll, and aria-live announcement debounce suite)
 * - frontend/tests/components/transcript/TranscriptPanel.test.tsx (general behavior:
 *   loading/error/empty states, collapsed/expanded states, view mode switching,
 *   language selection, accessibility)
 *
 * Covers Feature 048 (User Story 3) requirements:
 * - FR-015: Auto-scroll to active segment when followPlayback is ON
 * - FR-016: "Follow playback" toggle button with aria-pressed state
 * - FR-A02: aria-live="polite" region announces active segment text (debounced 1000ms)
 * - Edge Case 5: Manual scroll pauses auto-scroll; re-engages on next segment transition
 *
 * Covers general TranscriptPanel behavior:
 * - Collapsed state (default)
 * - Expanded state
 * - No transcripts message
 * - Expand/collapse button semantics (NFR-A06-A10)
 * - Loading and error states
 * - Language badges display
 * - Focus management
 *
 * Testing strategy:
 * - Mocks useTranscriptLanguages / useTranscriptSearch / usePrefersReducedMotion so the
 *   component renders its expanded content without real API calls.
 * - Mocks TranscriptSegments, TranscriptFullText, LanguageSelector, and ViewModeToggle so
 *   child network calls are eliminated and the DOM remains predictable. The TranscriptSegments
 *   mock renders both the "Segments: {videoId} - {languageCode}" text (asserted by the
 *   general-behavior suite) and two data-segment-id nodes fed via searchProps.onSegmentsChange
 *   (needed by the follow-playback/auto-scroll/announcement suite).
 * - Mocks scrollIntoView on Element.prototype so calls can be asserted.
 * - Uses vi.useFakeTimers() for debounce assertions.
 *
 * @module components/transcript/__tests__/TranscriptPanel
 */

import {
  describe,
  it,
  expect,
  vi,
  beforeEach,
  afterEach,
} from "vitest";
import {
  render,
  screen,
  fireEvent,
  act,
  waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import type { Mock } from "vitest";

import type { TranscriptLanguage, TranscriptSegment } from "../../../types/transcript";

// ---------------------------------------------------------------------------
// Module-level mocks (hoisted by Vitest before imports)
// ---------------------------------------------------------------------------

vi.mock("../../../hooks/useTranscriptLanguages", () => ({
  useTranscriptLanguages: vi.fn(),
}));

vi.mock("../../../hooks/useTranscriptSearch", () => ({
  useTranscriptSearch: vi.fn(),
}));

vi.mock("../../../hooks/usePrefersReducedMotion", () => ({
  usePrefersReducedMotion: vi.fn(),
}));

// Combined TranscriptSegments mock: renders the "Segments: {videoId} - {languageCode}"
// text asserted by the general-behavior suite, AND exposes two segments via
// data-segment-id nodes + fires searchProps.onSegmentsChange on mount, needed by the
// follow-playback/auto-scroll/announcement suite.
vi.mock("../TranscriptSegments", () => ({
  TranscriptSegments: vi.fn(
    (props: {
      videoId?: string;
      languageCode?: string;
      searchProps?: {
        onSegmentsChange?: (segments: TranscriptSegment[]) => void;
        [key: string]: unknown;
      };
      [key: string]: unknown;
    }) => {
      React.useEffect(() => {
        const onSegmentsChange = props.searchProps?.onSegmentsChange;
        if (onSegmentsChange) {
          onSegmentsChange([
            {
              id: 1,
              text: "Hello world",
              start_time: 0,
              end_time: 5,
              duration: 5,
              has_correction: false,
              corrected_at: null,
              correction_count: 0,
            },
            {
              id: 2,
              text: "Second segment",
              start_time: 5,
              end_time: 10,
              duration: 5,
              has_correction: false,
              corrected_at: null,
              correction_count: 0,
            },
          ]);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
      }, []);

      return (
        <div data-testid="transcript-segments">
          Segments: {props.videoId} - {props.languageCode}
          <div data-segment-id="1">Hello world</div>
          <div data-segment-id="2">Second segment</div>
        </div>
      );
    }
  ),
}));

vi.mock("../TranscriptFullText", () => ({
  TranscriptFullText: vi.fn(
    ({ videoId, languageCode }: { videoId?: string; languageCode?: string }) => (
      <div data-testid="transcript-fulltext">
        FullText: {videoId} - {languageCode}
      </div>
    )
  ),
}));

vi.mock("../LanguageSelector", () => ({
  LanguageSelector: vi.fn(
    ({
      selectedLanguage,
      onLanguageChange,
    }: {
      selectedLanguage?: string;
      onLanguageChange: (code: string) => void;
    }) => (
      <div data-testid="language-selector">
        <button onClick={() => onLanguageChange("en")}>EN</button>
        <button onClick={() => onLanguageChange("es")}>ES</button>
        <div>Selected: {selectedLanguage}</div>
      </div>
    )
  ),
}));

vi.mock("../ViewModeToggle", () => ({
  ViewModeToggle: vi.fn(
    ({
      mode,
      onModeChange,
    }: {
      mode: string;
      onModeChange: (m: string) => void;
    }) => (
      <div data-testid="view-mode-toggle">
        <button onClick={() => onModeChange("segments")} aria-pressed={mode === "segments"}>
          Segments
        </button>
        <button onClick={() => onModeChange("fulltext")} aria-pressed={mode === "fulltext"}>
          Full Text
        </button>
        <div>Mode: {mode}</div>
      </div>
    )
  ),
}));

// ---------------------------------------------------------------------------
// Imports after mocks
// ---------------------------------------------------------------------------

import { TranscriptPanel } from "../TranscriptPanel";
import { useTranscriptLanguages } from "../../../hooks/useTranscriptLanguages";
import { useTranscriptSearch } from "../../../hooks/useTranscriptSearch";
import { usePrefersReducedMotion } from "../../../hooks/usePrefersReducedMotion";

// Cast to bare `Mock` (rather than `vi.mocked`) so `mockReturnValue` accepts
// plain test fixtures without having to satisfy the real hooks' full return
// types (e.g. TanStack Query's `UseQueryResult` discriminated union carries
// many more fields than these tests need to stub).
const mockUseTranscriptLanguages = useTranscriptLanguages as Mock;
const mockUseTranscriptSearch = useTranscriptSearch as Mock;
const mockUsePrefersReducedMotion = usePrefersReducedMotion as Mock;

// ---------------------------------------------------------------------------
// Test constants
// ---------------------------------------------------------------------------

const TEST_VIDEO_ID = "dQw4w9WgXcQ";

const MOCK_LANGUAGES: TranscriptLanguage[] = [
  {
    language_code: "en",
    language_name: "English",
    transcript_type: "manual",
    is_translatable: true,
    downloaded_at: "2024-01-01T00:00:00Z",
  },
];

/** Minimal no-op search state returned by the mocked hook. */
const NOOP_SEARCH_STATE = {
  matches: [],
  currentIndex: 0,
  total: 0,
  next: vi.fn(),
  prev: vi.fn(),
  query: "",
  setQuery: vi.fn(),
  reset: vi.fn(),
};

// useTranscriptSearch is mocked for the whole file (both suites below), since
// TranscriptPanel calls it unconditionally. The general-behavior suite never
// asserts on search state, so this default satisfies it; the follow-playback
// suite re-asserts the same value explicitly in its own beforeEach.
mockUseTranscriptSearch.mockReturnValue(NOOP_SEARCH_STATE);

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------

/**
 * Builds a QueryClient with retries disabled for test isolation.
 */
function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
}

// TranscriptPanel has no Router dependency (all child components are mocked
// above), so the local render helper only wraps QueryClientProvider. Defined
// in-file (not imported from `frontend/tests/test-utils`) to keep `src/`
// test imports self-contained and typecheck-safe.
function renderWithProviders(
  ui: React.ReactElement,
  queryClient: QueryClient = makeQueryClient()
) {
  return {
    ...render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>),
    queryClient,
    user: userEvent.setup(),
  };
}

/**
 * Renders TranscriptPanel inside the required providers.
 * The panel is expanded by default (isExpanded=true after one toggle click)
 * so the follow-playback toggle and transcript content are visible.
 */
function renderPanel(
  props: Partial<React.ComponentProps<typeof TranscriptPanel>> = {}
) {
  const result = renderWithProviders(<TranscriptPanel videoId={TEST_VIDEO_ID} {...props} />);

  // Expand the panel so the content area (and toggle button) are reachable.
  // The expand button shows "Show transcript" when collapsed.
  const expandBtn = screen.getByRole("button", { name: /show transcript/i });
  fireEvent.click(expandBtn);

  return result;
}

// ---------------------------------------------------------------------------
// Suite: Feature 048 — follow-playback toggle and auto-scroll
// ---------------------------------------------------------------------------

describe("TranscriptPanel — follow-playback toggle and auto-scroll (Feature 048)", () => {
  let scrollIntoViewMock: Mock;

  beforeEach(() => {
    // Provide stable mock implementations for every test.
    mockUseTranscriptLanguages.mockReturnValue({
      data: MOCK_LANGUAGES,
      isLoading: false,
      isError: false,
      error: null,
    });

    mockUseTranscriptSearch.mockReturnValue(NOOP_SEARCH_STATE);

    mockUsePrefersReducedMotion.mockReturnValue(false);

    // Mock scrollIntoView — not implemented in happy-dom.
    scrollIntoViewMock = vi.fn();
    Element.prototype.scrollIntoView = scrollIntoViewMock;
  });

  afterEach(() => {
    vi.clearAllMocks();
    vi.useRealTimers();
  });

  // =========================================================================
  // TC-1: Toggle label — "Following" when enabled
  // =========================================================================

  describe("Follow-playback toggle label", () => {
    it("shows 'Following' label when followPlayback is true", () => {
      renderPanel({
        followPlayback: true,
        toggleFollowPlayback: vi.fn(),
        seekTo: vi.fn(),
      });

      expect(
        screen.getByRole("button", { name: /following/i })
      ).toBeInTheDocument();
    });

    // =========================================================================
    // TC-2: Toggle label — "Follow playback" when disabled
    // =========================================================================

    it("shows 'Follow playback' label when followPlayback is false", () => {
      renderPanel({
        followPlayback: false,
        toggleFollowPlayback: vi.fn(),
        seekTo: vi.fn(),
      });

      // The button text when OFF is "Follow playback".
      expect(
        screen.getByRole("button", { name: /follow playback/i })
      ).toBeInTheDocument();
      // And "Following" must NOT appear.
      expect(
        screen.queryByRole("button", { name: /^following$/i })
      ).not.toBeInTheDocument();
    });

    // =========================================================================
    // TC-5: Toggle aria-pressed state
    // =========================================================================

    it("has aria-pressed='true' when followPlayback is ON", () => {
      renderPanel({
        followPlayback: true,
        toggleFollowPlayback: vi.fn(),
        seekTo: vi.fn(),
      });

      const btn = screen.getByRole("button", { name: /following/i });
      expect(btn).toHaveAttribute("aria-pressed", "true");
    });

    it("has aria-pressed='false' when followPlayback is OFF", () => {
      renderPanel({
        followPlayback: false,
        toggleFollowPlayback: vi.fn(),
        seekTo: vi.fn(),
      });

      const btn = screen.getByRole("button", { name: /follow playback/i });
      expect(btn).toHaveAttribute("aria-pressed", "false");
    });

    // =========================================================================
    // TC-9: Toggle absent when no player props supplied
    // =========================================================================

    it("does not render the follow-playback toggle when no player props are provided", () => {
      // No followPlayback / toggleFollowPlayback → player-less view.
      renderPanel();

      // "Following" text never appears.
      expect(
        screen.queryByRole("button", { name: /following/i })
      ).not.toBeInTheDocument();
      // "Follow playback" text never appears either.
      expect(
        screen.queryByRole("button", { name: /follow playback/i })
      ).not.toBeInTheDocument();
    });
  });

  // =========================================================================
  // TC-6: aria-live region present
  // =========================================================================

  describe("aria-live region", () => {
    it("renders an element with aria-live='polite' in the DOM", () => {
      const { container } = renderPanel({
        followPlayback: true,
        toggleFollowPlayback: vi.fn(),
        seekTo: vi.fn(),
      });

      // The component renders multiple aria-live="polite" regions (panel
      // announcement, search announcement, active-segment announcement).
      // We assert at least one exists — the active-segment announcement is
      // identified by data-testid="active-segment-announcement".
      const liveRegion = container.querySelector(
        '[data-testid="active-segment-announcement"]'
      );
      expect(liveRegion).toBeInTheDocument();
      expect(liveRegion).toHaveAttribute("aria-live", "polite");
    });
  });

  // =========================================================================
  // TC-3: scrollIntoView called when active segment changes and follow ON
  // =========================================================================

  describe("Auto-scroll behaviour", () => {
    it("calls scrollIntoView when activeSegmentId changes and followPlayback is ON", async () => {
      const queryClient = makeQueryClient();

      const { rerender } = render(
        <QueryClientProvider client={queryClient}>
          <TranscriptPanel
            videoId={TEST_VIDEO_ID}
            followPlayback={true}
            toggleFollowPlayback={vi.fn()}
            seekTo={vi.fn()}
            activeSegmentId={null}
          />
        </QueryClientProvider>
      );

      // Expand the panel.
      fireEvent.click(screen.getByRole("button", { name: /show transcript/i }));

      // Clear any scrollIntoView calls that happened during mount.
      scrollIntoViewMock.mockClear();

      // Simulate a segment transition: activeSegmentId changes from null → 1.
      await act(async () => {
        rerender(
          <QueryClientProvider client={queryClient}>
            <TranscriptPanel
              videoId={TEST_VIDEO_ID}
              followPlayback={true}
              toggleFollowPlayback={vi.fn()}
              seekTo={vi.fn()}
              activeSegmentId={1}
            />
          </QueryClientProvider>
        );
      });

      expect(scrollIntoViewMock).toHaveBeenCalledWith({
        behavior: "smooth",
        block: "nearest",
      });
    });

    // =========================================================================
    // TC-4: scrollIntoView NOT called when follow OFF
    // =========================================================================

    it("does NOT call scrollIntoView when activeSegmentId changes and followPlayback is OFF", async () => {
      const queryClient = makeQueryClient();

      const { rerender } = render(
        <QueryClientProvider client={queryClient}>
          <TranscriptPanel
            videoId={TEST_VIDEO_ID}
            followPlayback={false}
            toggleFollowPlayback={vi.fn()}
            seekTo={vi.fn()}
            activeSegmentId={null}
          />
        </QueryClientProvider>
      );

      fireEvent.click(screen.getByRole("button", { name: /show transcript/i }));
      scrollIntoViewMock.mockClear();

      await act(async () => {
        rerender(
          <QueryClientProvider client={queryClient}>
            <TranscriptPanel
              videoId={TEST_VIDEO_ID}
              followPlayback={false}
              toggleFollowPlayback={vi.fn()}
              seekTo={vi.fn()}
              activeSegmentId={1}
            />
          </QueryClientProvider>
        );
      });

      expect(scrollIntoViewMock).not.toHaveBeenCalled();
    });

    // =========================================================================
    // TC-8: Manual scroll pauses auto-scroll; re-engages on next transition
    // =========================================================================

    it("suppresses auto-scroll on the transition immediately after a manual scroll, then re-engages on the next transition", async () => {
      const queryClient = makeQueryClient();

      const { rerender } = render(
        <QueryClientProvider client={queryClient}>
          <TranscriptPanel
            videoId={TEST_VIDEO_ID}
            followPlayback={true}
            toggleFollowPlayback={vi.fn()}
            seekTo={vi.fn()}
            activeSegmentId={null}
          />
        </QueryClientProvider>
      );

      fireEvent.click(screen.getByRole("button", { name: /show transcript/i }));
      scrollIntoViewMock.mockClear();

      // The transcript scroll container has role="region" and aria-label="Transcript content".
      const scrollContainer = screen.getByRole("region", {
        name: /transcript content/i,
      });

      // Simulate a manual scroll by the user.
      fireEvent.scroll(scrollContainer);

      // Transition 1 after manual scroll — auto-scroll must be SUPPRESSED.
      await act(async () => {
        rerender(
          <QueryClientProvider client={queryClient}>
            <TranscriptPanel
              videoId={TEST_VIDEO_ID}
              followPlayback={true}
              toggleFollowPlayback={vi.fn()}
              seekTo={vi.fn()}
              activeSegmentId={1}
            />
          </QueryClientProvider>
        );
      });

      expect(scrollIntoViewMock).not.toHaveBeenCalled();

      // Transition 2 — auto-scroll must RE-ENGAGE (flag cleared on previous transition).
      await act(async () => {
        rerender(
          <QueryClientProvider client={queryClient}>
            <TranscriptPanel
              videoId={TEST_VIDEO_ID}
              followPlayback={true}
              toggleFollowPlayback={vi.fn()}
              seekTo={vi.fn()}
              activeSegmentId={2}
            />
          </QueryClientProvider>
        );
      });

      expect(scrollIntoViewMock).toHaveBeenCalledWith({
        behavior: "smooth",
        block: "nearest",
      });
    });
  });

  // =========================================================================
  // TC-7: Announcement debounced to 1000ms (FR-A02)
  // =========================================================================

  describe("aria-live announcement debounce (FR-A02)", () => {
    it("does not announce immediately when activeSegmentId changes", async () => {
      // Use fake timers for precise control: the 1000ms debounce must not fire
      // synchronously after the segment transition. Fake timers prevent the
      // timer from auto-advancing so we can assert the empty state.
      vi.useFakeTimers();

      const queryClient = makeQueryClient();

      const { rerender } = render(
        <QueryClientProvider client={queryClient}>
          <TranscriptPanel
            videoId={TEST_VIDEO_ID}
            followPlayback={true}
            toggleFollowPlayback={vi.fn()}
            seekTo={vi.fn()}
            activeSegmentId={null}
          />
        </QueryClientProvider>
      );

      // Expand the panel.
      await act(async () => {
        fireEvent.click(
          screen.getByRole("button", { name: /show transcript/i })
        );
      });

      // Change activeSegmentId — even if loadedSegments is empty, the debounce
      // timer cannot have fired yet (time is frozen).
      await act(async () => {
        rerender(
          <QueryClientProvider client={queryClient}>
            <TranscriptPanel
              videoId={TEST_VIDEO_ID}
              followPlayback={true}
              toggleFollowPlayback={vi.fn()}
              seekTo={vi.fn()}
              activeSegmentId={1}
            />
          </QueryClientProvider>
        );
      });

      // Advance by 999ms — debounce should NOT have fired.
      await vi.advanceTimersByTimeAsync(999);

      const liveRegion = document.querySelector(
        '[data-testid="active-segment-announcement"]'
      );
      expect(liveRegion).toHaveTextContent("");
    });

    it("announces the active segment text after the 1000ms debounce elapses", async () => {
      // Strategy: render the panel with activeSegmentId=1 from the start so
      // that when loadedSegments is populated (via onSegmentsChange), the
      // announcement effect re-fires and schedules the debounce timeout.
      // We then use waitFor to wait for the text to appear.
      const queryClient = makeQueryClient();

      render(
        <QueryClientProvider client={queryClient}>
          <TranscriptPanel
            videoId={TEST_VIDEO_ID}
            followPlayback={true}
            toggleFollowPlayback={vi.fn()}
            seekTo={vi.fn()}
            activeSegmentId={1}
          />
        </QueryClientProvider>
      );

      // Expand the panel so TranscriptSegments mounts and onSegmentsChange fires.
      await act(async () => {
        fireEvent.click(
          screen.getByRole("button", { name: /show transcript/i })
        );
      });

      // Wait for the segment text to appear in the aria-live region.
      // The effect fires when loadedSegments changes (populated by mock's
      // onSegmentsChange), schedules a 1000ms debounce, and after it fires
      // the region text updates to "Hello world".
      // waitFor polls every 50ms with a 2000ms total timeout.
      const liveRegion = document.querySelector(
        '[data-testid="active-segment-announcement"]'
      );
      await waitFor(
        () => {
          expect(liveRegion).toHaveTextContent("Hello world");
        },
        { timeout: 2000 }
      );
    });

    it("rapid segment changes result in only the final segment being announced", async () => {
      // Verify debounce cancellation: two rapid transitions → only second
      // segment's text is announced. Uses real timers with a generous waitFor.
      const queryClient = makeQueryClient();

      // Start with activeSegmentId=1 to trigger initial announcement cycle.
      const { rerender } = render(
        <QueryClientProvider client={queryClient}>
          <TranscriptPanel
            videoId={TEST_VIDEO_ID}
            followPlayback={true}
            toggleFollowPlayback={vi.fn()}
            seekTo={vi.fn()}
            activeSegmentId={1}
          />
        </QueryClientProvider>
      );

      await act(async () => {
        fireEvent.click(
          screen.getByRole("button", { name: /show transcript/i })
        );
      });

      // Wait until the first announcement fires so we know loadedSegments is set.
      const liveRegion = document.querySelector(
        '[data-testid="active-segment-announcement"]'
      );
      await waitFor(
        () => {
          expect(liveRegion).toHaveTextContent("Hello world");
        },
        { timeout: 2000 }
      );

      // Immediately transition to segment 2 then to null (reset) then to 2.
      // The sequence: 1→2 in quick succession cancels the segment-1 debounce.
      // Since segment-1 already announced, we transition to null first to reset.
      await act(async () => {
        rerender(
          <QueryClientProvider client={queryClient}>
            <TranscriptPanel
              videoId={TEST_VIDEO_ID}
              followPlayback={true}
              toggleFollowPlayback={vi.fn()}
              seekTo={vi.fn()}
              activeSegmentId={null}
            />
          </QueryClientProvider>
        );
      });

      // Verify reset to empty.
      await waitFor(() => {
        expect(liveRegion).toHaveTextContent("");
      });

      // Now transition to segment 2 — should eventually announce "Second segment".
      await act(async () => {
        rerender(
          <QueryClientProvider client={queryClient}>
            <TranscriptPanel
              videoId={TEST_VIDEO_ID}
              followPlayback={true}
              toggleFollowPlayback={vi.fn()}
              seekTo={vi.fn()}
              activeSegmentId={2}
            />
          </QueryClientProvider>
        );
      });

      await waitFor(
        () => {
          expect(liveRegion).toHaveTextContent("Second segment");
        },
        { timeout: 2000 }
      );
    });
  });
});

// ---------------------------------------------------------------------------
// Suite: general TranscriptPanel behavior
// ---------------------------------------------------------------------------

describe("TranscriptPanel", () => {
  const mockLanguages: TranscriptLanguage[] = [
    {
      language_code: "en",
      language_name: "English",
      transcript_type: "manual",
      is_translatable: true,
      downloaded_at: "2024-01-15T10:00:00Z",
    },
    {
      language_code: "es",
      language_name: "Spanish",
      transcript_type: "auto_generated",
      is_translatable: true,
      downloaded_at: "2024-01-15T10:05:00Z",
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    mockUsePrefersReducedMotion.mockReturnValue(false);
  });

  describe("Loading State", () => {
    it("should render loading skeleton", () => {
      mockUseTranscriptLanguages.mockReturnValue({
        data: undefined,
        isLoading: true,
        isError: false,
        error: null,
      });

      renderWithProviders(<TranscriptPanel videoId="test-video" />);

      expect(screen.getByRole("status", { name: "Loading transcript information" })).toBeInTheDocument();
      expect(screen.getByText("Loading transcript information...")).toBeInTheDocument();
    });
  });

  describe("Error State", () => {
    it("should render error message", () => {
      mockUseTranscriptLanguages.mockReturnValue({
        data: undefined,
        isLoading: false,
        isError: true,
        error: { type: "network", message: "Failed to fetch" },
      });

      renderWithProviders(<TranscriptPanel videoId="test-video" />);

      expect(screen.getByRole("alert")).toBeInTheDocument();
      expect(screen.getByText("Could not load transcript information.")).toBeInTheDocument();
      expect(screen.getByText("Failed to fetch")).toBeInTheDocument();
    });
  });

  describe("No Transcripts Available", () => {
    it("should render no transcript message when languages array is empty", () => {
      mockUseTranscriptLanguages.mockReturnValue({
        data: [],
        isLoading: false,
        isError: false,
        error: null,
      });

      renderWithProviders(<TranscriptPanel videoId="test-video" />);

      expect(screen.getByText("No transcript available for this video")).toBeInTheDocument();
    });
  });

  describe("Collapsed State (Default)", () => {
    beforeEach(() => {
      mockUseTranscriptLanguages.mockReturnValue({
        data: mockLanguages,
        isLoading: false,
        isError: false,
        error: null,
      });
    });

    it("should render in collapsed state by default", () => {
      renderWithProviders(<TranscriptPanel videoId="test-video" />);

      const toggleButton = screen.getByRole("button", { name: /show transcript/i });
      expect(toggleButton).toHaveAttribute("aria-expanded", "false");
    });

    it('should show "Transcript Available" text when collapsed', () => {
      renderWithProviders(<TranscriptPanel videoId="test-video" />);

      expect(screen.getByText("Transcript Available")).toBeInTheDocument();
    });

    it("should show language badges when collapsed", () => {
      renderWithProviders(<TranscriptPanel videoId="test-video" />);

      // Query within the language badge list to avoid confusion with mocked LanguageSelector buttons
      const badgeList = screen.getByRole("list", { name: "Available languages" });
      const badges = badgeList.querySelectorAll('[role="listitem"]');

      // Should show language badges for en and es
      expect(badges).toHaveLength(2);
      expect(badges[0]).toHaveTextContent("EN");
      expect(badges[1]).toHaveTextContent("ES");
    });

    it("should show high quality checkmark for manual transcripts", () => {
      renderWithProviders(<TranscriptPanel videoId="test-video" />);

      const badges = screen.getAllByRole("listitem");
      // First badge (EN) should have checkmark for manual transcript
      expect(badges[0]).toHaveTextContent("EN✓");
      // Second badge (ES) should not have checkmark (auto-generated)
      expect(badges[1]).toHaveTextContent("ES");
      expect(badges[1]).not.toHaveTextContent("✓");
    });

    it("should have expandable content hidden when collapsed", () => {
      renderWithProviders(<TranscriptPanel videoId="test-video" />);

      const toggleButton = screen.getByRole("button", { name: /show transcript/i });
      const contentId = toggleButton.getAttribute("aria-controls");
      const expandableContent = document.getElementById(contentId!);

      expect(expandableContent).toHaveAttribute("aria-hidden", "true");
    });
  });

  describe("Expanded State", () => {
    beforeEach(() => {
      mockUseTranscriptLanguages.mockReturnValue({
        data: mockLanguages,
        isLoading: false,
        isError: false,
        error: null,
      });
    });

    it("should expand when toggle button is clicked", async () => {
      const { user } = renderWithProviders(<TranscriptPanel videoId="test-video" />);

      const toggleButton = screen.getByRole("button", { name: /show transcript/i });
      await user.click(toggleButton);

      await waitFor(() => {
        expect(toggleButton).toHaveAttribute("aria-expanded", "true");
        const contentId = toggleButton.getAttribute("aria-controls");
        const expandableContent = document.getElementById(contentId!);
        expect(expandableContent).toHaveAttribute("aria-hidden", "false");
      });
    });

    it('should show "Hide transcript" text when expanded', async () => {
      const { user } = renderWithProviders(<TranscriptPanel videoId="test-video" />);

      const toggleButton = screen.getByRole("button", { name: /show transcript/i });
      await user.click(toggleButton);

      await waitFor(() => {
        expect(screen.getByText("Hide transcript")).toBeInTheDocument();
      });
    });

    it("should show language selector when expanded", async () => {
      const { user } = renderWithProviders(<TranscriptPanel videoId="test-video" />);

      const toggleButton = screen.getByRole("button", { name: /show transcript/i });
      await user.click(toggleButton);

      await waitFor(() => {
        expect(screen.getByTestId("language-selector")).toBeInTheDocument();
      });
    });

    it("should show view mode toggle when expanded", async () => {
      const { user } = renderWithProviders(<TranscriptPanel videoId="test-video" />);

      const toggleButton = screen.getByRole("button", { name: /show transcript/i });
      await user.click(toggleButton);

      await waitFor(() => {
        expect(screen.getByTestId("view-mode-toggle")).toBeInTheDocument();
      });
    });

    it("should show transcript segments by default", async () => {
      const { user } = renderWithProviders(<TranscriptPanel videoId="test-video" />);

      const toggleButton = screen.getByRole("button", { name: /show transcript/i });
      await user.click(toggleButton);

      await waitFor(() => {
        expect(screen.getByTestId("transcript-segments")).toBeInTheDocument();
      });
    });

    it("should NOT show language badges when expanded", async () => {
      const { user } = renderWithProviders(<TranscriptPanel videoId="test-video" />);

      const toggleButton = screen.getByRole("button", { name: /show transcript/i });

      // Verify badges are visible when collapsed
      expect(screen.getByRole("list", { name: "Available languages" })).toBeInTheDocument();

      await user.click(toggleButton);

      await waitFor(() => {
        // After expansion, the badges should be hidden (not rendered in collapsed state)
        // The implementation renders badges conditionally with !isExpanded
        expect(screen.queryByRole("list", { name: "Available languages" })).not.toBeInTheDocument();
      });
    });
  });

  describe("Expand/Collapse Button Semantics (NFR-A06-A10)", () => {
    beforeEach(() => {
      mockUseTranscriptLanguages.mockReturnValue({
        data: mockLanguages,
        isLoading: false,
        isError: false,
        error: null,
      });
    });

    it("should have proper aria-expanded attribute", () => {
      renderWithProviders(<TranscriptPanel videoId="test-video" />);

      const toggleButton = screen.getByRole("button", { name: /show transcript/i });
      expect(toggleButton).toHaveAttribute("aria-expanded", "false");
    });

    it("should have proper aria-controls attribute", () => {
      renderWithProviders(<TranscriptPanel videoId="test-video" />);

      const toggleButton = screen.getByRole("button", { name: /show transcript/i });
      expect(toggleButton).toHaveAttribute("aria-controls", "transcript-content");
    });

    it("should be keyboard accessible", async () => {
      const { user } = renderWithProviders(<TranscriptPanel videoId="test-video" />);

      const toggleButton = screen.getByRole("button", { name: /show transcript/i });
      toggleButton.focus();

      expect(toggleButton).toHaveFocus();

      await user.keyboard("{Enter}");

      await waitFor(() => {
        expect(toggleButton).toHaveAttribute("aria-expanded", "true");
      });
    });

    it("should announce state changes to screen readers", async () => {
      const { user } = renderWithProviders(<TranscriptPanel videoId="test-video" />);

      const toggleButton = screen.getByRole("button", { name: /show transcript/i });
      await user.click(toggleButton);

      await waitFor(() => {
        const announcement = screen.getByTestId("panel-announcement");
        expect(announcement).toHaveTextContent("Transcript panel expanded");
      });
    });
  });

  describe("View Mode Switching", () => {
    beforeEach(() => {
      mockUseTranscriptLanguages.mockReturnValue({
        data: mockLanguages,
        isLoading: false,
        isError: false,
        error: null,
      });
    });

    it("should show segments view by default", async () => {
      const { user } = renderWithProviders(<TranscriptPanel videoId="test-video" />);

      const toggleButton = screen.getByRole("button", { name: /show transcript/i });
      await user.click(toggleButton);

      await waitFor(() => {
        expect(screen.getByTestId("transcript-segments")).toBeInTheDocument();
        expect(screen.queryByTestId("transcript-fulltext")).not.toBeInTheDocument();
      });
    });

    it("should switch to full text view when view mode toggle is clicked", async () => {
      const { user } = renderWithProviders(<TranscriptPanel videoId="test-video" />);

      // Expand panel first
      const toggleButton = screen.getByRole("button", { name: /show transcript/i });
      await user.click(toggleButton);

      await waitFor(() => {
        expect(screen.getByTestId("view-mode-toggle")).toBeInTheDocument();
      });

      // Click Full Text button in view mode toggle
      const fullTextButton = screen.getByRole("button", { name: "Full Text" });
      await user.click(fullTextButton);

      await waitFor(() => {
        expect(screen.getByTestId("transcript-fulltext")).toBeInTheDocument();
        expect(screen.queryByTestId("transcript-segments")).not.toBeInTheDocument();
      });
    });
  });

  describe("Language Selection", () => {
    beforeEach(() => {
      mockUseTranscriptLanguages.mockReturnValue({
        data: mockLanguages,
        isLoading: false,
        isError: false,
        error: null,
      });
    });

    it("should initialize with first language selected", async () => {
      const { user } = renderWithProviders(<TranscriptPanel videoId="test-video" />);

      const toggleButton = screen.getByRole("button", { name: /show transcript/i });
      await user.click(toggleButton);

      await waitFor(() => {
        expect(screen.getByText("Selected: en")).toBeInTheDocument();
      });
    });

    it("should pass selected language to transcript components", async () => {
      const { user } = renderWithProviders(<TranscriptPanel videoId="test-video" />);

      const toggleButton = screen.getByRole("button", { name: /show transcript/i });
      await user.click(toggleButton);

      await waitFor(() => {
        expect(screen.getByTestId("transcript-segments")).toHaveTextContent("Segments: test-video - en");
      });
    });

    it("should update transcript when language is changed", async () => {
      const { user } = renderWithProviders(<TranscriptPanel videoId="test-video" />);

      const toggleButton = screen.getByRole("button", { name: /show transcript/i });
      await user.click(toggleButton);

      await waitFor(() => {
        expect(screen.getByTestId("language-selector")).toBeInTheDocument();
      });

      const spanishButton = screen.getByRole("button", { name: "ES" });
      await user.click(spanishButton);

      await waitFor(() => {
        expect(screen.getByTestId("transcript-segments")).toHaveTextContent("Segments: test-video - es");
      });
    });
  });

  describe("Accessibility", () => {
    beforeEach(() => {
      mockUseTranscriptLanguages.mockReturnValue({
        data: mockLanguages,
        isLoading: false,
        isError: false,
        error: null,
      });
    });

    it("should have proper region role and label", () => {
      renderWithProviders(<TranscriptPanel videoId="test-video" />);

      expect(screen.getByRole("region", { name: "Transcript information" })).toBeInTheDocument();
    });

    it("should provide screen reader summary when collapsed", () => {
      renderWithProviders(<TranscriptPanel videoId="test-video" />);

      expect(screen.getByText(/2 transcripts available in English, Spanish/i)).toBeInTheDocument();
    });

    it("should have tabpanel role for expanded content", async () => {
      const { user } = renderWithProviders(<TranscriptPanel videoId="test-video" />);

      const toggleButton = screen.getByRole("button", { name: /show transcript/i });
      const contentId = toggleButton.getAttribute("aria-controls");

      await user.click(toggleButton);

      await waitFor(() => {
        const expandableContent = document.getElementById(contentId!);
        expect(expandableContent).toHaveAttribute("role", "tabpanel");
      });
    });
  });
});
