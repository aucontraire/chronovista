/**
 * Tests for PhoneticVariantsSection component.
 *
 * Coverage:
 * - Renders collapsed by default, does not fetch data when collapsed
 * - Expands on button click, shows loading then data
 * - Confidence slider filters results (client-side via hook)
 * - Register as Alias button calls API and transitions to success state
 * - Find & Replace button navigates with correct route state
 * - Empty state shown when no matches pass threshold
 * - Error state rendered when fetch fails
 * - aria-expanded toggles correctly
 * - Table columns present when data loads
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { PhoneticVariantsSection } from "../PhoneticVariantsSection";
import { usePhoneticMatches } from "../../../hooks/usePhoneticMatches";
import { createEntityAlias } from "../../../api/entityMentions";
import type { PhoneticMatch } from "../../../types/corrections";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock("../../../hooks/usePhoneticMatches", () => ({
  usePhoneticMatches: vi.fn(),
}));

vi.mock("../../../api/entityMentions", () => ({
  createEntityAlias: vi.fn(),
}));

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

const mockedUsePhoneticMatches = vi.mocked(usePhoneticMatches);
const mockedCreateEntityAlias = vi.mocked(createEntityAlias);

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makePhoneticMatch(overrides: Partial<PhoneticMatch> = {}): PhoneticMatch {
  return {
    original_text: "noam chomski",
    proposed_correction: "Noam Chomsky",
    confidence: 0.8,
    evidence_description: "Phonetic similarity via double metaphone",
    video_id: "video-uuid-001",
    segment_id: 42,
    video_title: "Chomsky on Language",
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Hook stub helpers
// ---------------------------------------------------------------------------

type HookResult = ReturnType<typeof usePhoneticMatches>;

function makeIdleHook(): HookResult {
  return {
    data: undefined,
    isLoading: false,
    isFetching: false,
    isError: false,
    isSuccess: false,
    error: null,
    effectiveServerFloor: 0.3,
  };
}

function makeLoadingHook(): HookResult {
  return {
    ...makeIdleHook(),
    isLoading: true,
  };
}

function makeSuccessHook(data: PhoneticMatch[]): HookResult {
  return {
    ...makeIdleHook(),
    data,
    isSuccess: true,
  };
}

function makeErrorHook(): HookResult {
  return {
    ...makeIdleHook(),
    isError: true,
    error: new Error("Network error"),
  };
}

// ---------------------------------------------------------------------------
// Render helper
// ---------------------------------------------------------------------------

function renderSection(entityId = "entity-uuid-001") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <PhoneticVariantsSection entityId={entityId} />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

function getDisclosureButton() {
  return screen.getByRole("button", { name: /suspected asr variants/i });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("PhoneticVariantsSection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Default: idle (collapsed — hook receives enabled=false)
    mockedUsePhoneticMatches.mockReturnValue(makeIdleHook());
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  // -------------------------------------------------------------------------
  // Collapsed by default
  // -------------------------------------------------------------------------

  it("renders the section header collapsed by default", () => {
    renderSection();
    const btn = getDisclosureButton();
    expect(btn).toBeInTheDocument();
    expect(btn).toHaveAttribute("aria-expanded", "false");
  });

  it("does not render the table when collapsed", () => {
    renderSection();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("does not pass enabled=true to the hook when collapsed", () => {
    renderSection();
    expect(mockedUsePhoneticMatches).toHaveBeenCalledWith(
      expect.objectContaining({ enabled: false })
    );
  });

  // -------------------------------------------------------------------------
  // Expanding the section
  // -------------------------------------------------------------------------

  it("expands on button click and sets aria-expanded to true", () => {
    renderSection();
    fireEvent.click(getDisclosureButton());
    expect(getDisclosureButton()).toHaveAttribute("aria-expanded", "true");
  });

  it("shows loading skeleton while fetching after expand", () => {
    mockedUsePhoneticMatches.mockReturnValue(makeLoadingHook());
    renderSection();
    fireEvent.click(getDisclosureButton());
    expect(
      screen.getByRole("status", { name: /loading phonetic variants/i })
    ).toBeInTheDocument();
  });

  it("passes enabled=true to the hook after expansion", () => {
    renderSection();
    fireEvent.click(getDisclosureButton());
    expect(mockedUsePhoneticMatches).toHaveBeenCalledWith(
      expect.objectContaining({ enabled: true })
    );
  });

  it("collapses again on second click", () => {
    renderSection();
    fireEvent.click(getDisclosureButton());
    expect(getDisclosureButton()).toHaveAttribute("aria-expanded", "true");
    fireEvent.click(getDisclosureButton());
    expect(getDisclosureButton()).toHaveAttribute("aria-expanded", "false");
  });

  // -------------------------------------------------------------------------
  // Table columns
  // -------------------------------------------------------------------------

  it("renders all table column headers when data is present", () => {
    mockedUsePhoneticMatches.mockReturnValue(
      makeSuccessHook([makePhoneticMatch()])
    );
    renderSection();
    fireEvent.click(getDisclosureButton());

    expect(screen.getByText("Original Text")).toBeInTheDocument();
    expect(screen.getByText("Proposed Correction")).toBeInTheDocument();
    expect(screen.getByText("Confidence")).toBeInTheDocument();
    expect(screen.getByText("Evidence")).toBeInTheDocument();
    expect(screen.getByText("Video Title")).toBeInTheDocument();
    expect(screen.getByText("Actions")).toBeInTheDocument();
  });

  it("renders match data in table rows", () => {
    const match = makePhoneticMatch({
      original_text: "chomski",
      proposed_correction: "Chomsky",
      video_title: "Test Video",
      evidence_description: "Double metaphone",
    });
    mockedUsePhoneticMatches.mockReturnValue(makeSuccessHook([match]));
    renderSection();
    fireEvent.click(getDisclosureButton());

    expect(screen.getByText("chomski")).toBeInTheDocument();
    expect(screen.getByText("Chomsky")).toBeInTheDocument();
    expect(screen.getByText("Test Video")).toBeInTheDocument();
    expect(screen.getByText("Double metaphone")).toBeInTheDocument();
  });

  it("renders confidence as a percentage badge", () => {
    const match = makePhoneticMatch({ confidence: 0.75 });
    mockedUsePhoneticMatches.mockReturnValue(makeSuccessHook([match]));
    renderSection();
    fireEvent.click(getDisclosureButton());

    expect(screen.getByLabelText("75% confidence")).toBeInTheDocument();
  });

  it("shows 'Unknown video' when video_title is null", () => {
    const match = makePhoneticMatch({ video_title: null });
    mockedUsePhoneticMatches.mockReturnValue(makeSuccessHook([match]));
    renderSection();
    fireEvent.click(getDisclosureButton());

    expect(screen.getByText("Unknown video")).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Confidence slider
  // -------------------------------------------------------------------------

  it("renders the confidence threshold slider when expanded", () => {
    mockedUsePhoneticMatches.mockReturnValue(makeSuccessHook([]));
    renderSection();
    fireEvent.click(getDisclosureButton());

    const slider = screen.getByRole("slider", { name: /confidence threshold/i });
    expect(slider).toBeInTheDocument();
    expect(slider).toHaveAttribute("min", "0");
    expect(slider).toHaveAttribute("max", "1");
    expect(slider).toHaveAttribute("step", "0.05");
  });

  it("slider has correct aria-valuetext", () => {
    mockedUsePhoneticMatches.mockReturnValue(makeSuccessHook([]));
    renderSection();
    fireEvent.click(getDisclosureButton());

    const slider = screen.getByRole("slider", { name: /confidence threshold/i });
    // Default displayThreshold is 0.5 → 50%
    expect(slider).toHaveAttribute(
      "aria-valuetext",
      "Confidence threshold: 50%"
    );
  });

  it("updates displayed threshold percentage when slider changes", () => {
    mockedUsePhoneticMatches.mockReturnValue(makeSuccessHook([]));
    renderSection();
    fireEvent.click(getDisclosureButton());

    const slider = screen.getByRole("slider", { name: /confidence threshold/i });
    fireEvent.change(slider, { target: { value: "0.7" } });

    // The label/display should now show 70%
    expect(screen.getByText("70%")).toBeInTheDocument();
  });

  it("passes displayThreshold to the hook when slider changes", () => {
    mockedUsePhoneticMatches.mockReturnValue(makeSuccessHook([]));
    renderSection();
    fireEvent.click(getDisclosureButton());

    const slider = screen.getByRole("slider", { name: /confidence threshold/i });
    fireEvent.change(slider, { target: { value: "0.8" } });

    expect(mockedUsePhoneticMatches).toHaveBeenCalledWith(
      expect.objectContaining({ displayThreshold: 0.8 })
    );
  });

  // -------------------------------------------------------------------------
  // Register as Alias
  // -------------------------------------------------------------------------

  it("renders 'Register as Alias' button for each match", () => {
    const match = makePhoneticMatch({ original_text: "chomski" });
    mockedUsePhoneticMatches.mockReturnValue(makeSuccessHook([match]));
    renderSection();
    fireEvent.click(getDisclosureButton());

    expect(
      screen.getByRole("button", { name: /register "chomski" as alias/i })
    ).toBeInTheDocument();
  });

  it("calls createEntityAlias with correct args when Register as Alias is clicked", async () => {
    mockedCreateEntityAlias.mockResolvedValueOnce({
      alias_name: "chomski",
      alias_type: "name_variant",
      occurrence_count: 1,
    });
    const match = makePhoneticMatch({
      original_text: "chomski",
      proposed_correction: "Chomsky",
    });
    mockedUsePhoneticMatches.mockReturnValue(makeSuccessHook([match]));
    renderSection();
    fireEvent.click(getDisclosureButton());

    const registerBtn = screen.getByRole("button", {
      name: /register "chomski" as alias/i,
    });
    fireEvent.click(registerBtn);

    await waitFor(() => {
      expect(mockedCreateEntityAlias).toHaveBeenCalledWith(
        "entity-uuid-001",
        "chomski",
        "name_variant"
      );
    });
  });

  it("shows 'Registered' checkmark state after successful alias creation", async () => {
    mockedCreateEntityAlias.mockResolvedValueOnce({
      alias_name: "chomski",
      alias_type: "name_variant",
      occurrence_count: 1,
    });
    const match = makePhoneticMatch({ original_text: "chomski" });
    mockedUsePhoneticMatches.mockReturnValue(makeSuccessHook([match]));
    renderSection();
    fireEvent.click(getDisclosureButton());

    fireEvent.click(
      screen.getByRole("button", { name: /register "chomski" as alias/i })
    );

    await waitFor(() => {
      expect(screen.getByLabelText("Alias registered")).toBeInTheDocument();
    });
    // The register button should no longer be present
    expect(
      screen.queryByRole("button", { name: /register "chomski" as alias/i })
    ).not.toBeInTheDocument();
  });

  it("shows error message when alias creation fails", async () => {
    mockedCreateEntityAlias.mockRejectedValueOnce(
      Object.assign(new Error("Server error"), { status: 500 })
    );
    const match = makePhoneticMatch({ original_text: "chomski" });
    mockedUsePhoneticMatches.mockReturnValue(makeSuccessHook([match]));
    // Use real timers for this test — we only need to verify the error appears,
    // not that it auto-dismisses after the 4-second timeout.
    vi.useRealTimers();
    renderSection();
    fireEvent.click(getDisclosureButton());

    fireEvent.click(
      screen.getByRole("button", { name: /register "chomski" as alias/i })
    );

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
      expect(
        screen.getByText(/failed to register alias/i)
      ).toBeInTheDocument();
    });
  });

  it("shows 409 conflict message when alias already exists", async () => {
    mockedCreateEntityAlias.mockRejectedValueOnce(
      Object.assign(new Error("Conflict"), { status: 409 })
    );
    const match = makePhoneticMatch({ original_text: "chomski" });
    mockedUsePhoneticMatches.mockReturnValue(makeSuccessHook([match]));
    // Use real timers for this test — we only need to verify the conflict
    // message appears, not the auto-dismiss behaviour.
    vi.useRealTimers();
    renderSection();
    fireEvent.click(getDisclosureButton());

    fireEvent.click(
      screen.getByRole("button", { name: /register "chomski" as alias/i })
    );

    await waitFor(() => {
      expect(screen.getByText(/this alias already exists/i)).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Find & Replace navigation
  // -------------------------------------------------------------------------

  it("renders 'Find & Replace' button for each match", () => {
    const match = makePhoneticMatch({
      original_text: "chomski",
      proposed_correction: "Chomsky",
    });
    mockedUsePhoneticMatches.mockReturnValue(makeSuccessHook([match]));
    renderSection();
    fireEvent.click(getDisclosureButton());

    expect(
      screen.getByRole("button", {
        name: /find and replace "chomski" with "Chomsky"/i,
      })
    ).toBeInTheDocument();
  });

  it("navigates to /corrections/batch with state when Find & Replace is clicked", () => {
    const match = makePhoneticMatch({
      original_text: "chomski",
      proposed_correction: "Chomsky",
    });
    mockedUsePhoneticMatches.mockReturnValue(makeSuccessHook([match]));
    renderSection();
    fireEvent.click(getDisclosureButton());

    fireEvent.click(
      screen.getByRole("button", {
        name: /find and replace "chomski" with "Chomsky"/i,
      })
    );

    expect(mockNavigate).toHaveBeenCalledTimes(1);
    expect(mockNavigate).toHaveBeenCalledWith("/corrections/batch", {
      state: {
        pattern: "chomski",
        replacement: "Chomsky",
      },
    });
  });

  // -------------------------------------------------------------------------
  // Empty state
  // -------------------------------------------------------------------------

  it("shows empty state message when no matches are found", () => {
    mockedUsePhoneticMatches.mockReturnValue(makeSuccessHook([]));
    renderSection();
    fireEvent.click(getDisclosureButton());

    expect(
      screen.getByText(/no suspected asr variants found/i)
    ).toBeInTheDocument();
  });

  it("does not render the table in empty state", () => {
    mockedUsePhoneticMatches.mockReturnValue(makeSuccessHook([]));
    renderSection();
    fireEvent.click(getDisclosureButton());

    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Error state
  // -------------------------------------------------------------------------

  it("shows error alert when fetch fails", () => {
    mockedUsePhoneticMatches.mockReturnValue(makeErrorHook());
    renderSection();
    fireEvent.click(getDisclosureButton());

    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(
      screen.getByText(/failed to load phonetic variants/i)
    ).toBeInTheDocument();
  });

  it("does not render the table in error state", () => {
    mockedUsePhoneticMatches.mockReturnValue(makeErrorHook());
    renderSection();
    fireEvent.click(getDisclosureButton());

    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Multiple matches
  // -------------------------------------------------------------------------

  it("renders all match rows when multiple matches are returned", () => {
    const matches = [
      makePhoneticMatch({
        original_text: "match-a",
        segment_id: 1,
        video_id: "v1",
      }),
      makePhoneticMatch({
        original_text: "match-b",
        segment_id: 2,
        video_id: "v2",
      }),
    ];
    mockedUsePhoneticMatches.mockReturnValue(makeSuccessHook(matches));
    renderSection();
    fireEvent.click(getDisclosureButton());

    expect(screen.getByText("match-a")).toBeInTheDocument();
    expect(screen.getByText("match-b")).toBeInTheDocument();
  });
});
