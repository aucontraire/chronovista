/**
 * Tests for DiffAnalysisPage — Feature 046 (T013).
 *
 * Coverage:
 * - Renders loading state (skeleton)
 * - Renders table with pattern data
 * - Page has correct heading
 * - Sort by frequency toggles direction (asc ↔ desc)
 * - aria-sort attribute on frequency <th> updates correctly
 * - Sort announcement appears in hidden live region (FR-028)
 * - Error token filter works client-side (instant)
 * - Entity name rendered as link when entity_id is present
 * - Entity column is empty when entity_id is null
 * - "Find & Replace" button calls navigate with correct state (US2)
 * - Empty state — no data
 * - Empty state — filters produce no results
 * - Query error state
 * - <main> landmark present
 * - "Show completed" toggle renders with correct label
 * - Default state: toggle is unchecked, hook called with showCompleted: false
 * - When toggled on: hook called with showCompleted: true
 * - Completed rows (remaining_matches=0) show "Completed" badge, not "Find & Replace"
 * - Completed rows have muted/grayed styling (opacity-60)
 * - Non-completed rows still show "Find & Replace" button
 * - Entity link remains functional on completed rows
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  render,
  screen,
  fireEvent,
  within,
  waitFor,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { DiffAnalysisPage } from "../DiffAnalysisPage";

// ---------------------------------------------------------------------------
// Mock hooks and navigation
// ---------------------------------------------------------------------------

const mockNavigate = vi.fn();

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

vi.mock("../../hooks/useDiffAnalysis", () => ({
  useDiffAnalysis: vi.fn(),
}));

import { useDiffAnalysis } from "../../hooks/useDiffAnalysis";
import type { DiffErrorPattern } from "../../types/corrections";

const mockedUseDiffAnalysis = vi.mocked(useDiffAnalysis);

// ---------------------------------------------------------------------------
// Test fixtures
// ---------------------------------------------------------------------------

function makePattern(overrides: Partial<DiffErrorPattern> = {}): DiffErrorPattern {
  return {
    error_token: "barak",
    canonical_form: "Barack",
    frequency: 12,
    remaining_matches: 8,
    entity_id: null,
    entity_name: null,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Default mock returns
// ---------------------------------------------------------------------------

function makeDefaultQueryResult(
  overrides: Partial<ReturnType<typeof useDiffAnalysis>> = {}
) {
  return {
    data: undefined,
    isLoading: false,
    isFetching: false,
    isError: false,
    isSuccess: false,
    error: null,
    refetch: vi.fn(),
    status: "pending" as const,
    fetchStatus: "idle" as const,
    isPending: false,
    isPaused: false,
    isRefetching: false,
    isRefetchError: false,
    isLoadingError: false,
    isPlaceholderData: false,
    isStale: false,
    dataUpdatedAt: 0,
    errorUpdatedAt: 0,
    errorUpdateCount: 0,
    failureCount: 0,
    failureReason: null,
    ...overrides,
  } as ReturnType<typeof useDiffAnalysis>;
}

// ---------------------------------------------------------------------------
// Render helper
// ---------------------------------------------------------------------------

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <DiffAnalysisPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("DiffAnalysisPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // -------------------------------------------------------------------------
  // Heading and landmark
  // -------------------------------------------------------------------------

  it("renders the ASR Error Patterns heading", () => {
    mockedUseDiffAnalysis.mockReturnValue(
      makeDefaultQueryResult({ isSuccess: true, data: [] })
    );

    renderPage();

    expect(
      screen.getByRole("heading", { name: "ASR Error Patterns", level: 1 })
    ).toBeInTheDocument();
  });

  it("renders a <main> landmark", () => {
    mockedUseDiffAnalysis.mockReturnValue(
      makeDefaultQueryResult({ isSuccess: true, data: [] })
    );

    renderPage();

    expect(screen.getByRole("main")).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Loading state
  // -------------------------------------------------------------------------

  it("renders a loading skeleton during initial fetch", () => {
    mockedUseDiffAnalysis.mockReturnValue(
      makeDefaultQueryResult({ isLoading: true, isPending: true })
    );

    renderPage();

    expect(
      screen.getByRole("status", { name: /loading asr error patterns/i })
    ).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Table with data
  // -------------------------------------------------------------------------

  it("renders table with error token and canonical form data", () => {
    const pattern = makePattern({
      error_token: "obamma",
      canonical_form: "Obama",
      frequency: 25,
    });

    mockedUseDiffAnalysis.mockReturnValue(
      makeDefaultQueryResult({ isSuccess: true, data: [pattern] })
    );

    renderPage();

    expect(screen.getByText("obamma")).toBeInTheDocument();
    expect(screen.getByText("Obama")).toBeInTheDocument();
    expect(screen.getByText("25")).toBeInTheDocument();
  });

  it("renders table column headers", () => {
    mockedUseDiffAnalysis.mockReturnValue(
      makeDefaultQueryResult({ isSuccess: true, data: [makePattern()] })
    );

    renderPage();

    expect(
      screen.getByRole("columnheader", { name: /error token/i })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("columnheader", { name: /canonical form/i })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("columnheader", { name: /entity/i })
    ).toBeInTheDocument();
  });

  it("renders multiple rows when multiple patterns exist", () => {
    const patterns = [
      makePattern({ error_token: "barak", canonical_form: "Barack", frequency: 20 }),
      makePattern({ error_token: "hussain", canonical_form: "Hussein", frequency: 10 }),
      makePattern({ error_token: "obamma", canonical_form: "Obama", frequency: 5 }),
    ];

    mockedUseDiffAnalysis.mockReturnValue(
      makeDefaultQueryResult({ isSuccess: true, data: patterns })
    );

    renderPage();

    expect(screen.getByText("barak")).toBeInTheDocument();
    expect(screen.getByText("hussain")).toBeInTheDocument();
    expect(screen.getByText("obamma")).toBeInTheDocument();

    const buttons = screen.getAllByRole("button", { name: /find and replace/i });
    expect(buttons).toHaveLength(3);
  });

  // -------------------------------------------------------------------------
  // Sort by frequency (FR-008)
  // -------------------------------------------------------------------------

  it("renders frequency column as a sortable button with aria-sort", () => {
    mockedUseDiffAnalysis.mockReturnValue(
      makeDefaultQueryResult({ isSuccess: true, data: [makePattern()] })
    );

    renderPage();

    const freqHeader = screen.getByRole("columnheader", {
      name: /frequency/i,
    });
    // Initially sorted descending
    expect(freqHeader).toHaveAttribute("aria-sort", "descending");

    // The button is inside the th
    const sortBtn = within(freqHeader).getByRole("button");
    expect(sortBtn).toBeInTheDocument();
  });

  it("toggles sort direction from descending to ascending on click", () => {
    const patterns = [
      makePattern({ error_token: "high", frequency: 100 }),
      makePattern({ error_token: "low", canonical_form: "Low", frequency: 1 }),
    ];

    mockedUseDiffAnalysis.mockReturnValue(
      makeDefaultQueryResult({ isSuccess: true, data: patterns })
    );

    renderPage();

    const freqHeader = screen.getByRole("columnheader", { name: /frequency/i });
    expect(freqHeader).toHaveAttribute("aria-sort", "descending");

    const sortBtn = within(freqHeader).getByRole("button");
    fireEvent.click(sortBtn);

    expect(freqHeader).toHaveAttribute("aria-sort", "ascending");
  });

  it("toggles sort direction from ascending back to descending on second click", () => {
    mockedUseDiffAnalysis.mockReturnValue(
      makeDefaultQueryResult({ isSuccess: true, data: [makePattern()] })
    );

    renderPage();

    const freqHeader = screen.getByRole("columnheader", { name: /frequency/i });
    const sortBtn = within(freqHeader).getByRole("button");

    // desc → asc
    fireEvent.click(sortBtn);
    expect(freqHeader).toHaveAttribute("aria-sort", "ascending");

    // asc → desc
    fireEvent.click(sortBtn);
    expect(freqHeader).toHaveAttribute("aria-sort", "descending");
  });

  it("sorts rows by frequency descending by default", () => {
    const patterns = [
      makePattern({ error_token: "low", canonical_form: "Low", frequency: 3 }),
      makePattern({ error_token: "high", canonical_form: "High", frequency: 50 }),
      makePattern({ error_token: "mid", canonical_form: "Mid", frequency: 20 }),
    ];

    mockedUseDiffAnalysis.mockReturnValue(
      makeDefaultQueryResult({ isSuccess: true, data: patterns })
    );

    renderPage();

    const rows = screen.getAllByRole("row");
    // rows[0] is the header row; rows[1] should be the highest frequency
    const firstDataRow = rows[1];
    expect(firstDataRow).toHaveTextContent("high");
  });

  it("sorts rows by frequency ascending after clicking sort button", () => {
    const patterns = [
      makePattern({ error_token: "low", canonical_form: "Low", frequency: 3 }),
      makePattern({ error_token: "high", canonical_form: "High", frequency: 50 }),
    ];

    mockedUseDiffAnalysis.mockReturnValue(
      makeDefaultQueryResult({ isSuccess: true, data: patterns })
    );

    renderPage();

    const freqHeader = screen.getByRole("columnheader", { name: /frequency/i });
    const sortBtn = within(freqHeader).getByRole("button");
    fireEvent.click(sortBtn);

    const rows = screen.getAllByRole("row");
    // After ascending sort, first data row should be lowest frequency
    const firstDataRow = rows[1];
    expect(firstDataRow).toHaveTextContent("low");
  });

  // -------------------------------------------------------------------------
  // Live region sort announcements (FR-028)
  // -------------------------------------------------------------------------

  it("announces sort direction change in a live region after clicking sort button", () => {
    mockedUseDiffAnalysis.mockReturnValue(
      makeDefaultQueryResult({ isSuccess: true, data: [makePattern()] })
    );

    renderPage();

    const freqHeader = screen.getByRole("columnheader", { name: /frequency/i });
    const sortBtn = within(freqHeader).getByRole("button");
    fireEvent.click(sortBtn);

    // The sr-only live region should announce the new sort direction
    const liveRegion = document.querySelector('[role="status"][aria-live="polite"]');
    expect(liveRegion).toBeInTheDocument();
    expect(liveRegion?.textContent).toMatch(/sorted by frequency.*ascending/i);
  });

  it("announces descending when toggled back from ascending", () => {
    mockedUseDiffAnalysis.mockReturnValue(
      makeDefaultQueryResult({ isSuccess: true, data: [makePattern()] })
    );

    renderPage();

    const freqHeader = screen.getByRole("columnheader", { name: /frequency/i });
    const sortBtn = within(freqHeader).getByRole("button");

    // desc → asc
    fireEvent.click(sortBtn);
    // asc → desc
    fireEvent.click(sortBtn);

    const liveRegion = document.querySelector('[role="status"][aria-live="polite"]');
    expect(liveRegion?.textContent).toMatch(/sorted by frequency.*descending/i);
  });

  // -------------------------------------------------------------------------
  // Error token client-side filter
  // -------------------------------------------------------------------------

  it("filters rows by error token when user types in the filter input", () => {
    const patterns = [
      makePattern({ error_token: "barak", canonical_form: "Barack", frequency: 10 }),
      makePattern({ error_token: "hussain", canonical_form: "Hussein", frequency: 5 }),
    ];

    mockedUseDiffAnalysis.mockReturnValue(
      makeDefaultQueryResult({ isSuccess: true, data: patterns })
    );

    renderPage();

    // Both rows visible initially
    expect(screen.getByText("barak")).toBeInTheDocument();
    expect(screen.getByText("hussain")).toBeInTheDocument();

    // Filter to only "barak"
    const filterInput = screen.getByRole("searchbox", {
      name: /filter patterns by error token/i,
    });
    fireEvent.change(filterInput, { target: { value: "barak" } });

    expect(screen.getByText("barak")).toBeInTheDocument();
    expect(screen.queryByText("hussain")).not.toBeInTheDocument();
  });

  it("filter is case-insensitive for error token", () => {
    const patterns = [
      makePattern({ error_token: "Barak", canonical_form: "Barack", frequency: 10 }),
    ];

    mockedUseDiffAnalysis.mockReturnValue(
      makeDefaultQueryResult({ isSuccess: true, data: patterns })
    );

    renderPage();

    const filterInput = screen.getByRole("searchbox", {
      name: /filter patterns by error token/i,
    });
    fireEvent.change(filterInput, { target: { value: "barak" } });

    expect(screen.getByText("Barak")).toBeInTheDocument();
  });

  it("shows empty state with filter message when error token filter matches nothing", () => {
    const pattern = makePattern({ error_token: "barak" });

    mockedUseDiffAnalysis.mockReturnValue(
      makeDefaultQueryResult({ isSuccess: true, data: [pattern] })
    );

    renderPage();

    const filterInput = screen.getByRole("searchbox", {
      name: /filter patterns by error token/i,
    });
    fireEvent.change(filterInput, { target: { value: "zzznomatch" } });

    expect(
      screen.getByText(/no patterns match the current filters/i)
    ).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Entity column
  // -------------------------------------------------------------------------

  it("renders entity name as a link to /entities/{id} when entity_id is present", () => {
    const pattern = makePattern({
      entity_id: "entity-uuid-abc",
      entity_name: "Barack Obama",
    });

    mockedUseDiffAnalysis.mockReturnValue(
      makeDefaultQueryResult({ isSuccess: true, data: [pattern] })
    );

    renderPage();

    const entityLink = screen.getByRole("link", { name: "Barack Obama" });
    expect(entityLink).toBeInTheDocument();
    expect(entityLink).toHaveAttribute("href", "/entities/entity-uuid-abc");
  });

  it("renders empty entity cell when entity_id is null", () => {
    const pattern = makePattern({ entity_id: null, entity_name: null });

    mockedUseDiffAnalysis.mockReturnValue(
      makeDefaultQueryResult({ isSuccess: true, data: [pattern] })
    );

    renderPage();

    // There should be no link in the entity column
    expect(screen.queryByRole("link")).not.toBeInTheDocument();

    // The entity column header still exists
    expect(
      screen.getByRole("columnheader", { name: /entity/i })
    ).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Find & Replace action (US2)
  // -------------------------------------------------------------------------

  it("calls navigate with correct state when Find & Replace is clicked", () => {
    const pattern = makePattern({
      error_token: "barak",
      canonical_form: "Barack",
    });

    mockedUseDiffAnalysis.mockReturnValue(
      makeDefaultQueryResult({ isSuccess: true, data: [pattern] })
    );

    renderPage();

    const findReplaceBtn = screen.getByRole("button", {
      name: /find and replace.*barak.*Barack/i,
    });
    fireEvent.click(findReplaceBtn);

    expect(mockNavigate).toHaveBeenCalledWith("/corrections/batch", {
      state: {
        pattern: "\\bbarak\\b",
        replacement: "Barack",
        isRegex: true,
      },
    });
  });

  it("calls navigate with the correct pattern for each row independently", () => {
    const patterns = [
      makePattern({ error_token: "alpha", canonical_form: "Alpha", frequency: 5 }),
      makePattern({ error_token: "beta", canonical_form: "Beta", frequency: 3 }),
    ];

    mockedUseDiffAnalysis.mockReturnValue(
      makeDefaultQueryResult({ isSuccess: true, data: patterns })
    );

    renderPage();

    const betaBtn = screen.getByRole("button", {
      name: /find and replace.*beta.*Beta/i,
    });
    fireEvent.click(betaBtn);

    expect(mockNavigate).toHaveBeenCalledWith("/corrections/batch", {
      state: {
        pattern: "\\bbeta\\b",
        replacement: "Beta",
        isRegex: true,
      },
    });
  });

  // -------------------------------------------------------------------------
  // Empty state
  // -------------------------------------------------------------------------

  it("renders empty state when no patterns exist and no filters active", () => {
    mockedUseDiffAnalysis.mockReturnValue(
      makeDefaultQueryResult({ isSuccess: true, data: [] })
    );

    renderPage();

    expect(
      screen.getByText(/no asr error patterns found/i)
    ).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Query error state
  // -------------------------------------------------------------------------

  it("renders an error message when the query fails", () => {
    mockedUseDiffAnalysis.mockReturnValue(
      makeDefaultQueryResult({
        isError: true,
        error: new Error("Network error"),
      })
    );

    renderPage();

    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(
      screen.getByText(/failed to load asr error patterns/i)
    ).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Show completed toggle
  // -------------------------------------------------------------------------

  it('renders a "Show completed" checkbox toggle', () => {
    mockedUseDiffAnalysis.mockReturnValue(
      makeDefaultQueryResult({ isSuccess: true, data: [] })
    );

    renderPage();

    const toggle = screen.getByRole("checkbox", { name: /show completed/i });
    expect(toggle).toBeInTheDocument();
  });

  it("toggle is unchecked by default", () => {
    mockedUseDiffAnalysis.mockReturnValue(
      makeDefaultQueryResult({ isSuccess: true, data: [] })
    );

    renderPage();

    const toggle = screen.getByRole("checkbox", { name: /show completed/i });
    expect(toggle).not.toBeChecked();
  });

  it("calls useDiffAnalysis with showCompleted: false by default", () => {
    mockedUseDiffAnalysis.mockReturnValue(
      makeDefaultQueryResult({ isSuccess: true, data: [] })
    );

    renderPage();

    expect(mockedUseDiffAnalysis).toHaveBeenCalledWith(
      expect.objectContaining({ showCompleted: false })
    );
  });

  it("calls useDiffAnalysis with showCompleted: true when toggle is checked", async () => {
    mockedUseDiffAnalysis.mockReturnValue(
      makeDefaultQueryResult({ isSuccess: true, data: [] })
    );

    renderPage();

    const toggle = screen.getByRole("checkbox", { name: /show completed/i });
    fireEvent.click(toggle);

    await waitFor(() => {
      expect(mockedUseDiffAnalysis).toHaveBeenCalledWith(
        expect.objectContaining({ showCompleted: true })
      );
    });
  });

  it("toggle becomes checked after clicking", () => {
    mockedUseDiffAnalysis.mockReturnValue(
      makeDefaultQueryResult({ isSuccess: true, data: [] })
    );

    renderPage();

    const toggle = screen.getByRole("checkbox", { name: /show completed/i });
    expect(toggle).not.toBeChecked();

    fireEvent.click(toggle);

    expect(toggle).toBeChecked();
  });

  // -------------------------------------------------------------------------
  // Completed row behavior (remaining_matches === 0)
  // -------------------------------------------------------------------------

  it('shows "Completed" badge instead of "Find & Replace" button for completed patterns', () => {
    const completedPattern = makePattern({
      error_token: "barak",
      canonical_form: "Barack",
      remaining_matches: 0,
    });

    mockedUseDiffAnalysis.mockReturnValue(
      makeDefaultQueryResult({ isSuccess: true, data: [completedPattern] })
    );

    renderPage();

    expect(screen.getByText("Completed")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /find and replace/i })
    ).not.toBeInTheDocument();
  });

  it("completed badge has title attribute set to 'All instances corrected'", () => {
    const completedPattern = makePattern({ remaining_matches: 0 });

    mockedUseDiffAnalysis.mockReturnValue(
      makeDefaultQueryResult({ isSuccess: true, data: [completedPattern] })
    );

    renderPage();

    const badge = screen.getByText("Completed");
    expect(badge).toHaveAttribute("title", "All instances corrected");
  });

  it("completed row has muted styling (opacity-60 class)", () => {
    const completedPattern = makePattern({ remaining_matches: 0 });

    mockedUseDiffAnalysis.mockReturnValue(
      makeDefaultQueryResult({ isSuccess: true, data: [completedPattern] })
    );

    renderPage();

    const rows = screen.getAllByRole("row");
    // rows[0] is header; rows[1] is the data row
    const dataRow = rows[1];
    expect(dataRow).toBeDefined();
    expect(dataRow!.className).toMatch(/opacity-60/);
  });

  it("non-completed row does not have muted styling", () => {
    const activePattern = makePattern({ remaining_matches: 5 });

    mockedUseDiffAnalysis.mockReturnValue(
      makeDefaultQueryResult({ isSuccess: true, data: [activePattern] })
    );

    renderPage();

    const rows = screen.getAllByRole("row");
    const dataRow = rows[1];
    expect(dataRow).toBeDefined();
    expect(dataRow!.className).not.toMatch(/opacity-60/);
  });

  it('non-completed rows still show "Find & Replace" button', () => {
    const activePattern = makePattern({
      error_token: "barak",
      canonical_form: "Barack",
      remaining_matches: 3,
    });

    mockedUseDiffAnalysis.mockReturnValue(
      makeDefaultQueryResult({ isSuccess: true, data: [activePattern] })
    );

    renderPage();

    expect(
      screen.getByRole("button", { name: /find and replace.*barak.*Barack/i })
    ).toBeInTheDocument();
    expect(screen.queryByText("Completed")).not.toBeInTheDocument();
  });

  it("mixed rows: completed show badge, active show Find & Replace", () => {
    const patterns = [
      makePattern({
        error_token: "active",
        canonical_form: "Active",
        remaining_matches: 4,
      }),
      makePattern({
        error_token: "done",
        canonical_form: "Done",
        remaining_matches: 0,
      }),
    ];

    mockedUseDiffAnalysis.mockReturnValue(
      makeDefaultQueryResult({ isSuccess: true, data: patterns })
    );

    renderPage();

    expect(
      screen.getByRole("button", { name: /find and replace.*active.*Active/i })
    ).toBeInTheDocument();
    expect(screen.getByText("Completed")).toBeInTheDocument();
  });

  it("entity link on completed row remains functional", () => {
    const completedWithEntity = makePattern({
      remaining_matches: 0,
      entity_id: "entity-uuid-xyz",
      entity_name: "Barack Obama",
    });

    mockedUseDiffAnalysis.mockReturnValue(
      makeDefaultQueryResult({ isSuccess: true, data: [completedWithEntity] })
    );

    renderPage();

    const entityLink = screen.getByRole("link", { name: "Barack Obama" });
    expect(entityLink).toBeInTheDocument();
    expect(entityLink).toHaveAttribute("href", "/entities/entity-uuid-xyz");
  });
});
