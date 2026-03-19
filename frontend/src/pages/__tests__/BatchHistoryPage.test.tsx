/**
 * Tests for BatchHistoryPage — Feature 046 (T009).
 *
 * Coverage:
 * - Renders loading state initially (skeleton)
 * - Renders table with batch data
 * - Renders empty state when no batches exist
 * - Revert button opens confirmation dialog
 * - Confirm revert calls mutation with correct batch ID
 * - Cancel closes dialog without reverting
 * - Error states (404, 409) display correctly in dialog
 * - Load More button appears when has_more=true
 * - Focus management: dialog gets focus on open; trigger gets focus on close
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  render,
  screen,
  fireEvent,
  waitFor,
  act,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { BatchHistoryPage } from "../BatchHistoryPage";

// ---------------------------------------------------------------------------
// Mock hooks
// ---------------------------------------------------------------------------

vi.mock("../../hooks/useBatchHistory", () => ({
  useBatchHistory: vi.fn(),
  useRevertBatch: vi.fn(),
}));

vi.mock("../../api/config", () => ({
  apiFetch: vi.fn(),
  isApiError: vi.fn((err: unknown): boolean => {
    return (
      typeof err === "object" &&
      err !== null &&
      "type" in err &&
      "message" in err
    );
  }),
}));

import { useBatchHistory, useRevertBatch } from "../../hooks/useBatchHistory";
import type { BatchSummary } from "../../types/corrections";

const mockedUseBatchHistory = vi.mocked(useBatchHistory);
const mockedUseRevertBatch = vi.mocked(useRevertBatch);

// ---------------------------------------------------------------------------
// Test data
// ---------------------------------------------------------------------------

function makeBatchSummary(overrides: Partial<BatchSummary> = {}): BatchSummary {
  return {
    batch_id: "batch-uuid-001",
    correction_count: 5,
    corrected_by_user_id: "user:batch",
    pattern: "colour",
    replacement: "color",
    batch_timestamp: "2025-01-15T10:00:00Z",
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Default mock returns
// ---------------------------------------------------------------------------

const defaultMutateResult = {
  mutate: vi.fn(),
  mutateAsync: vi.fn(),
  isPending: false,
  isPaused: false,
  isSuccess: false,
  isError: false,
  isIdle: true,
  data: undefined,
  error: null,
  reset: vi.fn(),
  context: undefined,
  failureCount: 0,
  failureReason: null,
  status: "idle" as const,
  variables: undefined,
  submittedAt: 0,
};

function makeDefaultBatchHistory(overrides: Partial<ReturnType<typeof useBatchHistory>> = {}) {
  return {
    data: undefined,
    isLoading: false,
    isFetching: false,
    isError: false,
    isSuccess: false,
    error: null,
    hasNextPage: false,
    isFetchingNextPage: false,
    fetchNextPage: vi.fn(),
    fetchPreviousPage: vi.fn(),
    hasPreviousPage: false,
    isFetchingPreviousPage: false,
    isFetchNextPageError: false,
    isFetchPreviousPageError: false,
    isRefetching: false,
    isRefetchError: false,
    isLoadingError: false,
    isPending: false,
    isPaused: false,
    isPlaceholderData: false,
    isStale: false,
    dataUpdatedAt: 0,
    errorUpdatedAt: 0,
    errorUpdateCount: 0,
    failureCount: 0,
    failureReason: null,
    refetch: vi.fn(),
    status: "pending" as const,
    fetchStatus: "idle" as const,
    ...overrides,
  } as ReturnType<typeof useBatchHistory>;
}

// ---------------------------------------------------------------------------
// Render helper
// ---------------------------------------------------------------------------

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <BatchHistoryPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("BatchHistoryPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedUseRevertBatch.mockReturnValue(defaultMutateResult as ReturnType<typeof useRevertBatch>);
  });

  // -------------------------------------------------------------------------
  // Loading state
  // -------------------------------------------------------------------------

  it("renders a loading skeleton during initial fetch", () => {
    mockedUseBatchHistory.mockReturnValue(
      makeDefaultBatchHistory({ isLoading: true, isPending: true })
    );

    renderPage();

    // The skeleton has an aria-label for screen readers
    expect(
      screen.getByRole("status", { name: /loading batch history/i })
    ).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Table with data
  // -------------------------------------------------------------------------

  it("renders the page heading", () => {
    mockedUseBatchHistory.mockReturnValue(
      makeDefaultBatchHistory({
        isSuccess: true,
        data: {
          pages: [{ data: [], pagination: { has_more: false, total: 0, offset: 0, limit: 20 } }],
          pageParams: [0],
        },
      })
    );

    renderPage();

    expect(
      screen.getByRole("heading", { name: /batch history/i, level: 1 })
    ).toBeInTheDocument();
  });

  it("renders a table with batch data when batches exist", () => {
    const batch = makeBatchSummary({
      pattern: "teh",
      replacement: "the",
      correction_count: 10,
      corrected_by_user_id: "user:cli",
    });
    mockedUseBatchHistory.mockReturnValue(
      makeDefaultBatchHistory({
        isSuccess: true,
        data: {
          pages: [
            {
              data: [batch],
              pagination: { has_more: false, total: 1, offset: 0, limit: 20 },
            },
          ],
          pageParams: [0],
        },
      })
    );

    renderPage();

    // Table headers
    expect(screen.getByRole("columnheader", { name: /pattern/i })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: /replacement/i })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: /count/i })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: /actor/i })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: /timestamp/i })).toBeInTheDocument();

    // Row data
    expect(screen.getByText("teh")).toBeInTheDocument();
    expect(screen.getByText("the")).toBeInTheDocument();
    expect(screen.getByText("10")).toBeInTheDocument();
    expect(screen.getByText("user:cli")).toBeInTheDocument();
  });

  it("renders multiple rows when multiple batches exist", () => {
    const batches = [
      makeBatchSummary({ batch_id: "b1", pattern: "colour", replacement: "color" }),
      makeBatchSummary({ batch_id: "b2", pattern: "favourite", replacement: "favorite" }),
      makeBatchSummary({ batch_id: "b3", pattern: "neighbour", replacement: "neighbor" }),
    ];
    mockedUseBatchHistory.mockReturnValue(
      makeDefaultBatchHistory({
        isSuccess: true,
        data: {
          pages: [
            {
              data: batches,
              pagination: { has_more: false, total: 3, offset: 0, limit: 20 },
            },
          ],
          pageParams: [0],
        },
      })
    );

    renderPage();

    expect(screen.getByText("colour")).toBeInTheDocument();
    expect(screen.getByText("favourite")).toBeInTheDocument();
    expect(screen.getByText("neighbour")).toBeInTheDocument();

    // Three Revert buttons — one per row
    const revertButtons = screen.getAllByRole("button", { name: /revert batch/i });
    expect(revertButtons).toHaveLength(3);
  });

  // -------------------------------------------------------------------------
  // Empty state
  // -------------------------------------------------------------------------

  it("renders empty state when no batches exist", () => {
    mockedUseBatchHistory.mockReturnValue(
      makeDefaultBatchHistory({
        isSuccess: true,
        data: {
          pages: [
            {
              data: [],
              pagination: { has_more: false, total: 0, offset: 0, limit: 20 },
            },
          ],
          pageParams: [0],
        },
      })
    );

    renderPage();

    expect(
      screen.getByText(/no batch operations found/i)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/apply a find-replace batch to see history here/i)
    ).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Revert dialog
  // -------------------------------------------------------------------------

  it("opens confirmation dialog when Revert button is clicked", async () => {
    const batch = makeBatchSummary({ pattern: "colour", replacement: "color" });
    mockedUseBatchHistory.mockReturnValue(
      makeDefaultBatchHistory({
        isSuccess: true,
        data: {
          pages: [
            {
              data: [batch],
              pagination: { has_more: false, total: 1, offset: 0, limit: 20 },
            },
          ],
          pageParams: [0],
        },
      })
    );

    renderPage();

    const revertBtn = screen.getByRole("button", { name: /revert batch/i });
    fireEvent.click(revertBtn);

    await waitFor(() => {
      expect(screen.getByRole("dialog")).toBeInTheDocument();
    });

    // Dialog shows batch details
    expect(
      screen.getByText(/revert batch correction/i)
    ).toBeInTheDocument();
    // Pattern and replacement appear inside dialog
    expect(screen.getAllByText("colour")).not.toHaveLength(0);
    expect(screen.getAllByText("color")).not.toHaveLength(0);
  });

  it("calls mutate with the correct batch ID when Confirm Revert is clicked", async () => {
    const mutateFn = vi.fn();
    mockedUseRevertBatch.mockReturnValue({
      ...defaultMutateResult,
      mutate: mutateFn,
    } as ReturnType<typeof useRevertBatch>);

    const batch = makeBatchSummary({ batch_id: "batch-target-99" });
    mockedUseBatchHistory.mockReturnValue(
      makeDefaultBatchHistory({
        isSuccess: true,
        data: {
          pages: [
            {
              data: [batch],
              pagination: { has_more: false, total: 1, offset: 0, limit: 20 },
            },
          ],
          pageParams: [0],
        },
      })
    );

    renderPage();

    fireEvent.click(screen.getByRole("button", { name: /revert batch/i }));

    await waitFor(() => {
      expect(screen.getByRole("dialog")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /confirm revert/i }));

    expect(mutateFn).toHaveBeenCalledWith(
      "batch-target-99",
      expect.objectContaining({ onSuccess: expect.any(Function) })
    );
  });

  it("closes dialog without calling mutate when Cancel is clicked", async () => {
    const mutateFn = vi.fn();
    mockedUseRevertBatch.mockReturnValue({
      ...defaultMutateResult,
      mutate: mutateFn,
    } as ReturnType<typeof useRevertBatch>);

    const batch = makeBatchSummary();
    mockedUseBatchHistory.mockReturnValue(
      makeDefaultBatchHistory({
        isSuccess: true,
        data: {
          pages: [
            {
              data: [batch],
              pagination: { has_more: false, total: 1, offset: 0, limit: 20 },
            },
          ],
          pageParams: [0],
        },
      })
    );

    renderPage();

    fireEvent.click(screen.getByRole("button", { name: /revert batch/i }));

    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });

    expect(mutateFn).not.toHaveBeenCalled();
  });

  it("closes dialog when Escape key is pressed", async () => {
    const batch = makeBatchSummary();
    mockedUseBatchHistory.mockReturnValue(
      makeDefaultBatchHistory({
        isSuccess: true,
        data: {
          pages: [
            {
              data: [batch],
              pagination: { has_more: false, total: 1, offset: 0, limit: 20 },
            },
          ],
          pageParams: [0],
        },
      })
    );

    renderPage();

    fireEvent.click(screen.getByRole("button", { name: /revert batch/i }));
    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument());

    // Press Escape
    fireEvent.keyDown(document, { key: "Escape" });

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Error states in dialog
  // -------------------------------------------------------------------------

  it("shows 404 error message in dialog when batch is not found", async () => {
    const notFoundError = Object.assign(new Error("Not found"), {
      type: "server",
      message: "Something went wrong on the server.",
      status: 404,
    });

    mockedUseRevertBatch.mockReturnValue({
      ...defaultMutateResult,
      isError: true,
      error: notFoundError,
      variables: "batch-uuid-001",
    } as unknown as ReturnType<typeof useRevertBatch>);

    const batch = makeBatchSummary();
    mockedUseBatchHistory.mockReturnValue(
      makeDefaultBatchHistory({
        isSuccess: true,
        data: {
          pages: [
            {
              data: [batch],
              pagination: { has_more: false, total: 1, offset: 0, limit: 20 },
            },
          ],
          pageParams: [0],
        },
      })
    );

    renderPage();

    fireEvent.click(screen.getByRole("button", { name: /revert batch/i }));
    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument());

    // The error is shown in the dialog
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(/batch not found/i);
  });

  it("shows 409 error message in dialog when batch is already reverted", async () => {
    const conflictError = Object.assign(new Error("Conflict"), {
      type: "server",
      message: "Something went wrong on the server.",
      status: 409,
    });

    mockedUseRevertBatch.mockReturnValue({
      ...defaultMutateResult,
      isError: true,
      error: conflictError,
      variables: "batch-uuid-001",
    } as unknown as ReturnType<typeof useRevertBatch>);

    const batch = makeBatchSummary();
    mockedUseBatchHistory.mockReturnValue(
      makeDefaultBatchHistory({
        isSuccess: true,
        data: {
          pages: [
            {
              data: [batch],
              pagination: { has_more: false, total: 1, offset: 0, limit: 20 },
            },
          ],
          pageParams: [0],
        },
      })
    );

    renderPage();

    fireEvent.click(screen.getByRole("button", { name: /revert batch/i }));
    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument());

    expect(screen.getByRole("alert")).toHaveTextContent(
      /this batch has already been reverted/i
    );
  });

  // -------------------------------------------------------------------------
  // Load More
  // -------------------------------------------------------------------------

  it("shows Load More button when has_more is true", () => {
    const batch = makeBatchSummary();
    mockedUseBatchHistory.mockReturnValue(
      makeDefaultBatchHistory({
        isSuccess: true,
        hasNextPage: true,
        data: {
          pages: [
            {
              data: [batch],
              pagination: { has_more: true, total: 50, offset: 0, limit: 20 },
            },
          ],
          pageParams: [0],
        },
      })
    );

    renderPage();

    expect(
      screen.getByRole("button", { name: /load more batch operations/i })
    ).toBeInTheDocument();
  });

  it("does not show Load More button when has_more is false", () => {
    const batch = makeBatchSummary();
    mockedUseBatchHistory.mockReturnValue(
      makeDefaultBatchHistory({
        isSuccess: true,
        hasNextPage: false,
        data: {
          pages: [
            {
              data: [batch],
              pagination: { has_more: false, total: 1, offset: 0, limit: 20 },
            },
          ],
          pageParams: [0],
        },
      })
    );

    renderPage();

    expect(
      screen.queryByRole("button", { name: /load more batch operations/i })
    ).not.toBeInTheDocument();
  });

  it("calls fetchNextPage when Load More is clicked", async () => {
    const fetchNextPageFn = vi.fn();
    const batch = makeBatchSummary();
    mockedUseBatchHistory.mockReturnValue(
      makeDefaultBatchHistory({
        isSuccess: true,
        hasNextPage: true,
        fetchNextPage: fetchNextPageFn,
        data: {
          pages: [
            {
              data: [batch],
              pagination: { has_more: true, total: 50, offset: 0, limit: 20 },
            },
          ],
          pageParams: [0],
        },
      })
    );

    renderPage();

    fireEvent.click(
      screen.getByRole("button", { name: /load more batch operations/i })
    );

    expect(fetchNextPageFn).toHaveBeenCalledTimes(1);
  });

  // -------------------------------------------------------------------------
  // Focus management (FR-027)
  // -------------------------------------------------------------------------

  it("moves focus into the dialog when it opens", async () => {
    const batch = makeBatchSummary();
    mockedUseBatchHistory.mockReturnValue(
      makeDefaultBatchHistory({
        isSuccess: true,
        data: {
          pages: [
            {
              data: [batch],
              pagination: { has_more: false, total: 1, offset: 0, limit: 20 },
            },
          ],
          pageParams: [0],
        },
      })
    );

    renderPage();

    const revertBtn = screen.getByRole("button", { name: /revert batch/i });
    await act(async () => {
      fireEvent.click(revertBtn);
    });

    await waitFor(() => {
      expect(screen.getByRole("dialog")).toBeInTheDocument();
    });

    // After the dialog mounts, focus should be inside it.
    // The Cancel button receives focus first per the implementation.
    const dialog = screen.getByRole("dialog");
    expect(dialog.contains(document.activeElement)).toBe(true);
  });

  it("returns focus to the Revert button when dialog is cancelled", async () => {
    const batch = makeBatchSummary();
    mockedUseBatchHistory.mockReturnValue(
      makeDefaultBatchHistory({
        isSuccess: true,
        data: {
          pages: [
            {
              data: [batch],
              pagination: { has_more: false, total: 1, offset: 0, limit: 20 },
            },
          ],
          pageParams: [0],
        },
      })
    );

    renderPage();

    const revertBtn = screen.getByRole("button", { name: /revert batch/i });
    revertBtn.focus();

    await act(async () => {
      fireEvent.click(revertBtn);
    });

    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument());

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    });

    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    );

    // Focus should have returned to the revert button
    expect(document.activeElement).toBe(revertBtn);
  });

  // -------------------------------------------------------------------------
  // Query error state
  // -------------------------------------------------------------------------

  it("renders an error message when the query fails", () => {
    mockedUseBatchHistory.mockReturnValue(
      makeDefaultBatchHistory({
        isError: true,
        error: new Error("Network error"),
      })
    );

    renderPage();

    expect(
      screen.getByRole("alert")
    ).toBeInTheDocument();
    expect(
      screen.getByText(/failed to load batch history/i)
    ).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Accessibility
  // -------------------------------------------------------------------------

  it("renders a <main> landmark", () => {
    mockedUseBatchHistory.mockReturnValue(
      makeDefaultBatchHistory({
        isSuccess: true,
        data: {
          pages: [
            {
              data: [],
              pagination: { has_more: false, total: 0, offset: 0, limit: 20 },
            },
          ],
          pageParams: [0],
        },
      })
    );

    renderPage();

    expect(screen.getByRole("main")).toBeInTheDocument();
  });

  it("dialog has aria-modal and aria-labelledby attributes", async () => {
    const batch = makeBatchSummary();
    mockedUseBatchHistory.mockReturnValue(
      makeDefaultBatchHistory({
        isSuccess: true,
        data: {
          pages: [
            {
              data: [batch],
              pagination: { has_more: false, total: 1, offset: 0, limit: 20 },
            },
          ],
          pageParams: [0],
        },
      })
    );

    renderPage();

    fireEvent.click(screen.getByRole("button", { name: /revert batch/i }));
    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument());

    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveAttribute("aria-labelledby");
  });
});