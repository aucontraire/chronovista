import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { CandidatesPage } from "../CandidatesPage";

vi.mock("../../hooks/useCandidates", () => ({
  useCandidatesList: () => ({
    candidates: [],
    total: 0,
    isLoading: false,
    isError: false,
    error: null,
    hasNextPage: false,
    isFetchingNextPage: false,
    retry: vi.fn(),
    loadMoreRef: { current: null },
  }),
  useCandidateSummary: () => ({ data: undefined, isError: true }),
  useGenerationStatus: () => ({ data: undefined }),
  useStartGeneration: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
}));

function setup() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <CandidatesPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
  return screen.getByRole("button", { name: "What do these terms mean?" });
}

describe("Candidates terms explainer", () => {
  it("is collapsed by default and opens with definitions", async () => {
    const user = userEvent.setup();
    const btn = setup();
    expect(btn).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("region", { name: "Candidate review terms" })).not.toBeInTheDocument();
    await user.click(btn);
    expect(btn).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("region", { name: "Candidate review terms" })).toBeInTheDocument();
    expect(screen.getByText("Corroboration", { selector: "dt" })).toBeInTheDocument();
    expect(screen.getByText("No library presence", { selector: "dt" })).toBeInTheDocument();
  });

  it("is keyboard operable and Escape closes it, returning focus", async () => {
    const user = userEvent.setup();
    const btn = setup();
    btn.focus();
    await user.keyboard("{Enter}");
    expect(btn).toHaveAttribute("aria-expanded", "true");
    await user.keyboard("{Escape}");
    expect(btn).toHaveAttribute("aria-expanded", "false");
    expect(btn).toHaveFocus();
  });

  it("closes on outside click", async () => {
    const user = userEvent.setup();
    const btn = setup();
    await user.click(btn);
    await user.click(document.body);
    expect(btn).toHaveAttribute("aria-expanded", "false");
  });
});
