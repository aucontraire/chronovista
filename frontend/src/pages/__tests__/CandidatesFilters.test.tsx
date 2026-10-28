/**
 * Tests for candidate queue filters, sort and summary panel (Feature 097, US3).
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { CandidatesPage } from "../CandidatesPage";

const listMock = vi.fn();

vi.mock("../../hooks/useCandidates", () => ({
  useGenerationStatus: () => ({ data: { run: null } }),
  useStartGeneration: () => ({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
    data: undefined,
  }),
  useCandidateSummary: () => ({
    data: {
      source_channel: "relation",
      pending: 120,
      approved: 7,
      rejected: 3,
      superseded: 2,
      worth_review: 80,
      likely_eliminable: 30,
      grounds_nowhere: 10,
    },
    isError: false,
  }),
  useCandidatesList: (...a: unknown[]) => listMock(...a),
}));

function listState() {
  return {
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
  };
}

function renderAt(url = "/candidates") {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <CandidatesPage />
    </MemoryRouter>
  );
}

const lastParams = () => listMock.mock.calls[listMock.mock.calls.length - 1]?.[0];

beforeEach(() => {
  vi.clearAllMocks();
  listMock.mockReturnValue(listState());
});

describe("CandidatesPage filters", () => {
  it("starts with only the default sort and no filters", () => {
    renderAt();
    expect(lastParams()).toEqual({ sort: "score" });
  });

  it("triage selector narrows the query", () => {
    renderAt();
    fireEvent.change(screen.getByLabelText("Triage"), {
      target: { value: "likely_eliminable" },
    });
    expect(lastParams()).toEqual({ sort: "score", triage: "likely_eliminable" });
  });

  it("type filter sets type_hint", () => {
    renderAt();
    fireEvent.change(screen.getByLabelText("Type"), { target: { value: "place" } });
    expect(lastParams()).toEqual({ sort: "score", type_hint: "place" });
  });

  it("hide single-token toggle sets min_token_count and toggles back", () => {
    renderAt();
    const toggle = screen.getByRole("switch", { name: "Hide single-token names" });
    fireEvent.click(toggle);
    expect(lastParams()).toEqual({ sort: "score", min_token_count: 2 });
    expect(toggle).toHaveAttribute("aria-checked", "true");
    fireEvent.click(toggle);
    expect(lastParams()).toEqual({ sort: "score" });
  });

  it("possible-duplicate toggle sets possible_duplicate", () => {
    renderAt();
    fireEvent.click(screen.getByRole("switch", { name: "Possible duplicates only" }));
    expect(lastParams()).toEqual({ sort: "score", possible_duplicate: true });
  });

  it.each(["corroboration", "salience", "score"])("sort %s is forwarded", (value) => {
    renderAt("/candidates?sort=salience");
    fireEvent.change(screen.getByLabelText("Sort by"), { target: { value } });
    expect(lastParams()).toEqual({ sort: value });
  });

  it("reads filters from the URL and ignores invalid values", () => {
    renderAt("/candidates?triage=grounds_nowhere&type=bogus&sort=nope&multi_token=true");
    expect(lastParams()).toEqual({
      sort: "score",
      triage: "grounds_nowhere",
      min_token_count: 2,
    });
    expect(screen.getByLabelText("Type")).toHaveValue("all");
  });

  it("renders summary counts and keeps them while filtering", () => {
    renderAt();
    const status = screen.getByLabelText("Review status counts");
    expect(within(status).getByText("120")).toBeInTheDocument();
    expect(within(status).getByText("7")).toBeInTheDocument();
    const triage = screen.getByLabelText("Pending triage counts");
    expect(within(triage).getByText("80")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Triage"), {
      target: { value: "worth_review" },
    });
    expect(screen.getByLabelText("Review status counts")).toBeInTheDocument();
    expect(screen.getByText("120")).toBeInTheDocument();
  });
});
