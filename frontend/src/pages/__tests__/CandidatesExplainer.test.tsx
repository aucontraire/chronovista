import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { TermsExplainer } from "../../components/candidates/TermsExplainer";
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
    expect(screen.getByText("No title, description, or transcript match", { selector: "dt" })).toBeInTheDocument();
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

describe("TermsExplainer corpus-source derivation", () => {
  async function openWith(sources?: readonly string[]) {
    const user = userEvent.setup();
    render(
      <TermsExplainer
        heading={<h1>Heading</h1>}
        terms={["grounds_nowhere", "salience"]}
        corpusSources={sources}
      />
    );
    await user.click(screen.getByRole("button", { name: "What do these terms mean?" }));
  }

  it("reflects exactly the sources given (two sources, no transcript)", async () => {
    await openWith(["title", "description"]);
    expect(screen.getByText("No title or description match", { selector: "dt" })).toBeInTheDocument();
    expect(screen.getByText(/in their title or description\.$/)).toBeInTheDocument();
    expect(screen.queryByText(/transcript/i)).not.toBeInTheDocument();
  });

  it("names every source when transcript is included", async () => {
    await openWith(["title", "description", "transcript"]);
    expect(screen.getByText("No title, description, or transcript match", { selector: "dt" })).toBeInTheDocument();
    expect(screen.getByText(/in their title, description, or transcript\.$/)).toBeInTheDocument();
    expect(screen.queryByText(/not checked/i)).not.toBeInTheDocument();
  });
});
