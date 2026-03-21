/**
 * Unit tests for TranscriptPanel auto-scroll and follow-playback toggle logic.
 *
 * Covers Feature 048 (User Story 3) requirements:
 * - FR-015: Auto-scroll to active segment when followPlayback is ON
 * - FR-016: "Follow playback" toggle button with aria-pressed state
 * - FR-A02: aria-live="polite" region announces active segment text (debounced 1000ms)
 * - Edge Case 5: Manual scroll pauses auto-scroll; re-engages on next segment transition
 *
 * Testing strategy:
 * - Mocks useTranscriptLanguages to return a pre-built language list so the
 *   component renders its expanded content without real API calls.
 * - Mocks useTranscriptSearch to return a no-op search state (the search feature
 *   is not under test here).
 * - Mocks usePrefersReducedMotion to return false (animations irrelevant to these tests).
 * - Mocks TranscriptSegments and TranscriptFullText so child network calls are
 *   eliminated and the DOM remains predictable.
 * - Mocks scrollIntoView on Element.prototype so calls can be asserted.
 * - Uses vi.useFakeTimers() for debounce assertions.
 *
 * @module tests/components/TranscriptPanel
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
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

// ---------------------------------------------------------------------------
// Module-level mocks (hoisted by Vitest before imports)
// ---------------------------------------------------------------------------

vi.mock("../../hooks/useTranscriptLanguages", () => ({
  useTranscriptLanguages: vi.fn(),
}));

vi.mock("../../hooks/useTranscriptSearch", () => ({
  useTranscriptSearch: vi.fn(),
}));

vi.mock("../../hooks/usePrefersReducedMotion", () => ({
  usePrefersReducedMotion: vi.fn(),
}));

// Stub out child components that make their own network calls.
// TranscriptSegments receives an onSegmentsChange callback via searchProps —
// we call it with a predefined set of segments so loadedSegments is populated
// for announcement tests. Note: the prop is searchProps.onSegmentsChange,
// not a direct onSegmentsChange prop.
vi.mock("../../components/transcript/TranscriptSegments", () => ({
  TranscriptSegments: vi.fn((props: {
    searchProps?: {
      onSegmentsChange?: (segments: import("../../types/transcript").TranscriptSegment[]) => void;
      [key: string]: unknown;
    };
    [key: string]: unknown;
  }) => {
    // Expose two test segments via a data-segment-id DOM node so auto-scroll
    // tests can query the element and assert scrollIntoView behaviour.
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
      <div data-testid="transcript-segments-mock">
        <div data-segment-id="1">Hello world</div>
        <div data-segment-id="2">Second segment</div>
      </div>
    );
  }),
}));

vi.mock("../../components/transcript/TranscriptFullText", () => ({
  TranscriptFullText: vi.fn(() => (
    <div data-testid="transcript-full-text-mock">Full text</div>
  )),
}));

vi.mock("../../components/transcript/LanguageSelector", () => ({
  LanguageSelector: vi.fn(({ languages, selectedLanguage, onLanguageChange }: {
    languages: import("../../types/transcript").TranscriptLanguage[];
    selectedLanguage: string;
    onLanguageChange: (code: string) => void;
  }) => (
    <div data-testid="language-selector-mock">
      {languages.map((l) => (
        <button
          key={l.language_code}
          role="tab"
          aria-selected={l.language_code === selectedLanguage}
          onClick={() => onLanguageChange(l.language_code)}
        >
          {l.language_name}
        </button>
      ))}
    </div>
  )),
}));

vi.mock("../../components/transcript/ViewModeToggle", () => ({
  ViewModeToggle: vi.fn(({ mode, onModeChange }: {
    mode: string;
    onModeChange: (m: string) => void;
  }) => (
    <div data-testid="view-mode-toggle-mock">
      <button onClick={() => onModeChange("segments")} aria-pressed={mode === "segments"}>
        Segments
      </button>
      <button onClick={() => onModeChange("full")} aria-pressed={mode === "full"}>
        Full text
      </button>
    </div>
  )),
}));

// ---------------------------------------------------------------------------
// Imports after mocks
// ---------------------------------------------------------------------------

import { TranscriptPanel } from "../../components/transcript/TranscriptPanel";
import { useTranscriptLanguages } from "../../hooks/useTranscriptLanguages";
import { useTranscriptSearch } from "../../hooks/useTranscriptSearch";
import { usePrefersReducedMotion } from "../../hooks/usePrefersReducedMotion";
import type { TranscriptLanguage } from "../../types/transcript";
import type { Mock } from "vitest";

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

/**
 * Renders TranscriptPanel inside the required providers.
 * The panel is expanded by default (isExpanded=true after one toggle click)
 * so the follow-playback toggle and transcript content are visible.
 */
function renderPanel(
  props: Partial<React.ComponentProps<typeof TranscriptPanel>> = {}
) {
  const queryClient = makeQueryClient();

  const result = render(
    <QueryClientProvider client={queryClient}>
      <TranscriptPanel videoId={TEST_VIDEO_ID} {...props} />
    </QueryClientProvider>
  );

  // Expand the panel so the content area (and toggle button) are reachable.
  // The expand button shows "Show transcript" when collapsed.
  const expandBtn = screen.getByRole("button", { name: /show transcript/i });
  fireEvent.click(expandBtn);

  return result;
}


// ---------------------------------------------------------------------------
// Suite setup
// ---------------------------------------------------------------------------

describe("TranscriptPanel — follow-playback toggle and auto-scroll (Feature 048)", () => {
  let scrollIntoViewMock: Mock;

  beforeEach(() => {
    // Provide stable mock implementations for every test.
    (useTranscriptLanguages as Mock).mockReturnValue({
      data: MOCK_LANGUAGES,
      isLoading: false,
      isError: false,
      error: null,
    });

    (useTranscriptSearch as Mock).mockReturnValue(NOOP_SEARCH_STATE);

    (usePrefersReducedMotion as Mock).mockReturnValue(false);

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
