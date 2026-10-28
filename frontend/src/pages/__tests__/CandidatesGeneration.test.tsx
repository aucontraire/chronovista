/**
 * Tests for UI-triggered candidate generation (Feature 097, US2).
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import type { GenerationRunResponse } from "../../api/candidates";
import { CandidatesPage } from "../CandidatesPage";

const statusMock = vi.fn();
const startMock = vi.fn();
const mutateMock = vi.fn();

vi.mock("../../hooks/useCandidates", () => ({
  useCandidateSummary: () => ({ data: undefined, isError: false }),
  useCandidatesList: () => ({
    candidates: [],
    total: 0,
    loadedCount: 0,
    isLoading: false,
    isError: false,
    error: null,
    hasNextPage: false,
    isFetchingNextPage: false,
    fetchNextPage: vi.fn(),
    retry: vi.fn(),
    loadMoreRef: { current: null },
  }),
  useGenerationStatus: () => statusMock(),
  useStartGeneration: () => startMock(),
}));

function makeRun(over: Partial<GenerationRunResponse> = {}): GenerationRunResponse {
  return {
    id: "run-1",
    source_channel: "relation",
    status: "running",
    progress_percent: 10,
    seeds_grounded: 5,
    candidates_discovered: 0,
    candidates_upserted: 0,
    superseded: 0,
    pending_total: 0,
    by_triage: {},
    empty_reason: null,
    error: null,
    started_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    completed_at: null,
    ...over,
  };
}

function setStatus(run: GenerationRunResponse | null) {
  statusMock.mockReturnValue({ data: { run } });
}

function setStart(over: Record<string, unknown> = {}) {
  startMock.mockReturnValue({
    mutate: mutateMock,
    isPending: false,
    isError: false,
    error: null,
    data: undefined,
    ...over,
  });
}

function renderPage() {
  return render(
    <MemoryRouter>
      <CandidatesPage />
    </MemoryRouter>
  );
}

describe("CandidatesPage generation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setStatus(null);
    setStart();
  });

  it("shows the Generate prompt on an empty queue and triggers a run", () => {
    renderPage();
    const button = screen.getByRole("button", { name: "Generate candidates" });
    expect(button).toBeEnabled();
    fireEvent.click(button);
    expect(mutateMock).toHaveBeenCalledTimes(1);
  });

  it("renders an advancing progress bar and disables the button while running", () => {
    setStatus(makeRun({ progress_percent: 10 }));
    const { rerender } = renderPage();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "10");
    expect(screen.getByRole("button", { name: "Generating..." })).toBeDisabled();
    expect(
      screen.getByRole("group", { name: "Candidate generation progress" })
    ).toBeInTheDocument();

    setStatus(makeRun({ progress_percent: 60 }));
    rerender(
      <MemoryRouter>
        <CandidatesPage />
      </MemoryRouter>
    );
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "60");
  });

  it("shows a result summary on completion without a progress bar", () => {
    setStatus(
      makeRun({
        status: "completed",
        progress_percent: 100,
        candidates_discovered: 12,
        pending_total: 9,
      })
    );
    renderPage();
    expect(screen.getByText(/12 discovered, 9 pending/)).toBeInTheDocument();
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Generate candidates" })).toBeEnabled();
  });

  it("shows the empty reason when completed with nothing found", () => {
    setStatus(makeRun({ status: "completed", progress_percent: 100, empty_reason: "no grounded seeds" }));
    renderPage();
    expect(screen.getByText(/no grounded seeds/)).toBeInTheDocument();
  });

  it("shows the error and a working Retry on failure", () => {
    setStatus(makeRun({ status: "failed", error: "upstream timeout" }));
    renderPage();
    expect(screen.getByRole("alert")).toHaveTextContent("upstream timeout");
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(mutateMock).toHaveBeenCalledTimes(1);
  });

  it("reports an already-running state after a 409", () => {
    setStatus(makeRun({ progress_percent: 40 }));
    setStart({ data: { alreadyRunning: true } });
    renderPage();
    expect(screen.getByText("Generation is already running.")).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "40");
  });
});
