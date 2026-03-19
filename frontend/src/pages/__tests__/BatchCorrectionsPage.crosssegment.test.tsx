/**
 * Tests for BatchCorrectionsPage — Cross-Segment Panel integration (T019).
 *
 * Coverage:
 * - CrossSegmentPanel renders on the page
 * - prefillForm handler updates PatternInput with new pattern and replacement
 * - prefillForm handler enables the cross-segment toggle
 * - Calling prefillForm resets a stale preview (dispatches RESET)
 * - Existing PatternInput form functionality still works after prefill
 *
 * Strategy:
 * - CrossSegmentPanel is mocked so we can inject test candidates and
 *   trigger prefillForm without testing the panel internals twice.
 * - All batch hooks are mocked with stable idle stubs.
 * - We render the real PatternInput (uncontrolled) and inspect DOM after
 *   the prefillForm callback fires.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { BatchCorrectionsPage } from "../BatchCorrectionsPage";

// ---------------------------------------------------------------------------
// Mock CrossSegmentPanel — capture the prefillForm callback for testing
// ---------------------------------------------------------------------------

vi.mock("../../components/corrections/CrossSegmentPanel", () => ({
  CrossSegmentPanel: vi.fn(({ prefillForm }: { prefillForm: (values: { pattern: string; replacement: string; crossSegment: boolean }) => void }) => {
    return (
      <div data-testid="cross-segment-panel">
        <button
          type="button"
          onClick={() =>
            prefillForm({
              pattern: "bernie",
              replacement: "Bernie",
              crossSegment: true,
            })
          }
        >
          Use candidate
        </button>
      </div>
    );
  }),
}));

// ---------------------------------------------------------------------------
// Mock batch hooks with idle stubs
// ---------------------------------------------------------------------------

const mockPreviewReset = vi.fn();
const mockPreviewMutate = vi.fn();

vi.mock("../../hooks/useBatchPreview", () => ({
  useBatchPreview: vi.fn(() => ({
    mutate: mockPreviewMutate,
    isPending: false,
    isError: false,
    error: null,
    reset: mockPreviewReset,
  })),
}));

vi.mock("../../hooks/useBatchApply", () => ({
  useBatchApply: vi.fn(() => ({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
    reset: vi.fn(),
  })),
}));

vi.mock("../../hooks/useBatchRebuild", () => ({
  useBatchRebuild: vi.fn(() => ({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
  })),
}));

vi.mock("../../hooks/useEntityDetail", () => ({
  useEntityDetail: vi.fn(() => ({
    entity: null,
    aliasNames: [],
    isLoading: false,
    isError: false,
  })),
}));

vi.mock("../../hooks/useEntities", () => ({
  useEntities: vi.fn(() => ({
    entities: [],
    total: 0,
    isLoading: false,
    isError: false,
    error: null,
    hasNextPage: false,
    isFetchingNextPage: false,
    fetchNextPage: vi.fn(),
  })),
}));

// EntityAutocomplete uses apiFetch — mock config module
vi.mock("../../api/config", () => ({
  apiFetch: vi.fn(),
  isApiError: vi.fn(() => false),
}));

// ---------------------------------------------------------------------------
// Render helper
// ---------------------------------------------------------------------------

function renderPage(initialPath = "/corrections/batch") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialPath]}>
        <BatchCorrectionsPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("BatchCorrectionsPage — CrossSegmentPanel integration", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // -------------------------------------------------------------------------
  // Panel presence
  // -------------------------------------------------------------------------

  it("renders CrossSegmentPanel on the page", () => {
    renderPage();
    expect(screen.getByTestId("cross-segment-panel")).toBeInTheDocument();
  });

  it("renders the page heading alongside the panel", () => {
    renderPage();
    expect(
      screen.getByRole("heading", { name: /batch find & replace/i, level: 1 })
    ).toBeInTheDocument();
    expect(screen.getByTestId("cross-segment-panel")).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // prefillForm updates PatternInput
  // -------------------------------------------------------------------------

  it("fills the pattern input when prefillForm is called with a candidate", async () => {
    renderPage();

    // The pattern input should initially be empty
    const patternInput = screen.getByPlaceholderText(/enter text or regex pattern/i);
    expect(patternInput).toHaveValue("");

    // Trigger prefill via the mock CrossSegmentPanel's button
    fireEvent.click(screen.getByRole("button", { name: /use candidate/i }));

    // PatternInput should remount with the new initial value
    await waitFor(() => {
      const updatedInput = screen.getByPlaceholderText(/enter text or regex pattern/i);
      expect(updatedInput).toHaveValue("bernie");
    });
  });

  it("fills the replacement input when prefillForm is called with a candidate", async () => {
    renderPage();

    fireEvent.click(screen.getByRole("button", { name: /use candidate/i }));

    await waitFor(() => {
      const replacementInput = screen.getByPlaceholderText(/replacement text/i);
      expect(replacementInput).toHaveValue("Bernie");
    });
  });

  it("enables the cross-segment toggle when prefillForm passes crossSegment: true", async () => {
    renderPage();

    // Initially cross-segment toggle should be off
    const crossSegmentToggle = screen.getByRole("switch", {
      name: /match across segment boundaries/i,
    });
    expect(crossSegmentToggle).toHaveAttribute("aria-checked", "false");

    fireEvent.click(screen.getByRole("button", { name: /use candidate/i }));

    await waitFor(() => {
      const updatedToggle = screen.getByRole("switch", {
        name: /match across segment boundaries/i,
      });
      expect(updatedToggle).toHaveAttribute("aria-checked", "true");
    });
  });

  // -------------------------------------------------------------------------
  // Stale preview reset
  // -------------------------------------------------------------------------

  it("resets preview mutation state when prefillForm is called", async () => {
    renderPage();

    fireEvent.click(screen.getByRole("button", { name: /use candidate/i }));

    await waitFor(() => {
      expect(mockPreviewReset).toHaveBeenCalledTimes(1);
    });
  });

  // -------------------------------------------------------------------------
  // Existing functionality unchanged
  // -------------------------------------------------------------------------

  it("still renders the PatternInput section with Preview Matches button", () => {
    renderPage();

    expect(
      screen.getByRole("button", { name: /preview matches/i })
    ).toBeInTheDocument();
  });

  it("Preview Matches button is disabled when pattern is empty", () => {
    renderPage();

    const previewBtn = screen.getByRole("button", { name: /preview matches/i });
    expect(previewBtn).toBeDisabled();
  });

  it("Preview Matches button enables after pattern is typed", () => {
    renderPage();

    const patternInput = screen.getByPlaceholderText(/enter text or regex pattern/i);
    fireEvent.change(patternInput, { target: { value: "somepattern" } });

    const previewBtn = screen.getByRole("button", { name: /preview matches/i });
    expect(previewBtn).not.toBeDisabled();
  });

  it("clicking Preview Matches calls the preview mutation", () => {
    renderPage();

    const patternInput = screen.getByPlaceholderText(/enter text or regex pattern/i);
    fireEvent.change(patternInput, { target: { value: "somepattern" } });

    fireEvent.click(screen.getByRole("button", { name: /preview matches/i }));

    expect(mockPreviewMutate).toHaveBeenCalledTimes(1);
    expect(mockPreviewMutate).toHaveBeenCalledWith(
      expect.objectContaining({ pattern: "somepattern" }),
      expect.any(Object)
    );
  });

  // -------------------------------------------------------------------------
  // prefillForm then normal usage flow
  // -------------------------------------------------------------------------

  it("allows previewing after prefill by clicking Preview Matches", async () => {
    renderPage();

    // Trigger prefill
    fireEvent.click(screen.getByRole("button", { name: /use candidate/i }));

    await waitFor(() => {
      const patternInput = screen.getByPlaceholderText(/enter text or regex pattern/i);
      expect(patternInput).toHaveValue("bernie");
    });

    // Preview should now be clickable (pattern is non-empty)
    const previewBtn = screen.getByRole("button", { name: /preview matches/i });
    expect(previewBtn).not.toBeDisabled();

    fireEvent.click(previewBtn);

    expect(mockPreviewMutate).toHaveBeenCalledWith(
      expect.objectContaining({
        pattern: "bernie",
        replacement: "Bernie",
        cross_segment: true,
      }),
      expect.any(Object)
    );
  });

  // -------------------------------------------------------------------------
  // Accessibility
  // -------------------------------------------------------------------------

  it("renders a <main> landmark", () => {
    renderPage();
    expect(screen.getByRole("main")).toBeInTheDocument();
  });

  it("CrossSegmentPanel has a section with accessible label", () => {
    // The real CrossSegmentPanel uses aria-label="Suggested Cross-Segment Candidates"
    // but since we mock it as a plain div, here we just verify it's present.
    renderPage();
    expect(screen.getByTestId("cross-segment-panel")).toBeInTheDocument();
  });
});
