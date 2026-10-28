/**
 * Tests for the candidate review read substrate (Feature 097, Phase 2).
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router-dom";

import type { CandidateDetail } from "../../api/candidates";
import { CandidatesPage } from "../CandidatesPage";
import { CandidateDetailPage } from "../CandidateDetailPage";

const listMock = vi.fn();
const detailMock = vi.fn();
const entityMock = vi.fn();
const approveMock = vi.fn();
const rejectMock = vi.fn();

vi.mock("../../hooks/useCandidates", () => ({
  useGenerationStatus: () => ({ data: { run: null } }),
  useStartGeneration: () => ({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
    data: undefined,
  }),
  useCandidateSummary: () => ({ data: undefined, isError: false }),
  useCandidatesList: (...a: unknown[]) => listMock(...a),
  useCandidateDetail: (...a: unknown[]) => detailMock(...a),
  useCandidateTagFootprint: () => ({ data: undefined }),
  useApproveCandidate: () => approveMock(),
  useRejectCandidate: () => rejectMock(),
}));
vi.mock("../../hooks/useEntityDetail", () => ({
  useEntityDetail: (...a: unknown[]) => entityMock(...a),
}));

function makeCandidate(over: Partial<CandidateDetail> = {}): CandidateDetail {
  return {
    id: "c-1",
    source_channel: "relation",
    wikidata_qid: "Q123",
    label: "Candidate Alpha",
    label_normalized: "candidate alpha",
    type_hint: "person",
    token_count: 2,
    corroboration_count: 3,
    dangling_edge_count: 4,
    salience: 0.5,
    score: 1.25,
    triage: "worth_review",
    provenance: { seed_entity_ids: ["seed-1", "seed-2"], relations: ["spouse"] },
    possible_duplicate_of_id: null,
    review_status: "pending",
    reviewed_by: null,
    reviewed_at: null,
    created_entity_id: null,
    last_generated_at: "2026-01-01T00:00:00Z",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...over,
  };
}

function listState(over: Record<string, unknown> = {}) {
  return {
    candidates: [
      makeCandidate(),
      makeCandidate({ id: "c-2", label: "Candidate Beta" }),
    ],
    total: 2,
    loadedCount: 2,
    isLoading: false,
    isError: false,
    error: null,
    hasNextPage: false,
    isFetchingNextPage: false,
    fetchNextPage: vi.fn(),
    retry: vi.fn(),
    loadMoreRef: { current: null },
    ...over,
  };
}

function renderList() {
  return render(
    <MemoryRouter initialEntries={["/candidates"]}>
      <CandidatesPage />
    </MemoryRouter>
  );
}

function renderDetail() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
    <MemoryRouter initialEntries={["/candidates/c-1"]}>
      <Routes>
        <Route path="/candidates/:candidateId" element={<CandidateDetailPage />} />
      </Routes>
    </MemoryRouter>
    </QueryClientProvider>
  );
}

type MutateOpts = {
  onSuccess?: (r: unknown) => void;
  onError?: (e: unknown) => void;
};

/** A mutation stub whose mutate() settles with the given result or error. */
function mutationStub(settle: { result?: unknown; error?: unknown }, isPending = false) {
  const mutate = vi.fn((_vars: unknown, opts?: MutateOpts) => {
    if (settle.error !== undefined) opts?.onError?.(settle.error);
    else opts?.onSuccess?.(settle.result);
  });
  return { mutate, isPending };
}

beforeEach(() => {
  vi.clearAllMocks();
  approveMock.mockReturnValue(mutationStub({}));
  rejectMock.mockReturnValue(mutationStub({}));
  entityMock.mockImplementation((id: string) => ({
    entityDetail: { canonical_name: `Name of ${id}` },
    aliasNames: [],
    isLoading: false,
  }));
});

describe("CandidatesPage", () => {
  it("renders ranked rows linking to the detail page", () => {
    listMock.mockReturnValue(listState());
    renderList();
    const link = screen.getByRole("link", { name: /Candidate Alpha/ });
    expect(link).toHaveAttribute("href", "/candidates/c-1");
    expect(screen.getByText("Candidate Beta")).toBeInTheDocument();
    expect(screen.getAllByText("Worth review", { selector: "span" })).toHaveLength(2);
  });

  it("renders a loading status", () => {
    listMock.mockReturnValue(listState({ isLoading: true, candidates: [] }));
    renderList();
    expect(screen.getByRole("status", { name: "Loading candidates" })).toHaveAttribute(
      "aria-busy",
      "true"
    );
  });

  it("renders the empty state", () => {
    listMock.mockReturnValue(listState({ candidates: [], total: 0 }));
    renderList();
    expect(screen.getByText("No pending candidates")).toBeInTheDocument();
  });

  it("renders an error with a working Retry", () => {
    const retry = vi.fn();
    listMock.mockReturnValue(
      listState({
        candidates: [],
        isError: true,
        error: { message: "boom" },
        retry,
      })
    );
    renderList();
    expect(screen.getByRole("alert")).toHaveTextContent("boom");
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(retry).toHaveBeenCalledTimes(1);
  });
});

describe("CandidateDetailPage", () => {
  it("terms explainer opens with the detail-only terms and closes on Escape", () => {
    detailMock.mockReturnValue({ data: makeCandidate(), isLoading: false, isError: false });
    renderDetail();
    const btn = screen.getByRole("button", { name: "What do these terms mean?" });
    expect(btn).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("region", { name: "Candidate review terms" })).not.toBeInTheDocument();
    fireEvent.click(btn);
    const panel = screen.getByRole("region", { name: "Candidate review terms" });
    expect(btn).toHaveAttribute("aria-expanded", "true");
    expect(within(panel).getByText("Dangling edges", { selector: "dt" })).toBeInTheDocument();
    expect(within(panel).getByText(/gaps in your graph/)).toBeInTheDocument();
    expect(within(panel).getByText("Token count", { selector: "dt" })).toBeInTheDocument();
    expect(within(panel).getByText(/One-word names are noisier/)).toBeInTheDocument();
    expect(within(panel).getByText("No library presence", { selector: "dt" })).toBeInTheDocument();
    fireEvent.keyDown(panel, { key: "Escape" });
    expect(btn).toHaveAttribute("aria-expanded", "false");
    expect(btn).toHaveFocus();
  });

  it("renders provenance, Wikidata link, and no duplicate indicator", () => {
    detailMock.mockReturnValue({ data: makeCandidate(), isLoading: false, isError: false });
    renderDetail();
    expect(screen.getByRole("heading", { name: "Candidate Alpha" })).toBeInTheDocument();
    expect(screen.getByText(/«spouse»/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Name of seed-1" })).toHaveAttribute(
      "href",
      "/entities/seed-1"
    );
    const wd = screen.getByRole("link", { name: "View on Wikidata" });
    expect(wd).toHaveAttribute("href", "https://www.wikidata.org/wiki/Q123");
    expect(wd).toHaveAttribute("rel", "noopener noreferrer");
    expect(screen.queryByText(/Possible duplicate/)).not.toBeInTheDocument();
  });

  it("links the possible duplicate when set", () => {
    detailMock.mockReturnValue({
      data: makeCandidate({ possible_duplicate_of_id: "dup-1" }),
      isLoading: false,
      isError: false,
    });
    renderDetail();
    expect(screen.getByRole("link", { name: /Possible duplicate/ })).toHaveAttribute(
      "href",
      "/entities/dup-1"
    );
  });

  it("shows not found on 404", () => {
    detailMock.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: { status: 404 },
      refetch: vi.fn(),
    });
    renderDetail();
    expect(screen.getByRole("alert")).toHaveTextContent("Candidate not found.");
  });
});

describe("CandidateDetailPage verdict", () => {
  const verdict = (outcome: string, created: string | null = null) => ({
    outcome,
    candidate_id: "c-1",
    created_entity_id: created,
    detail: null,
  });

  beforeEach(() => {
    detailMock.mockReturnValue({ data: makeCandidate(), isLoading: false, isError: false });
  });

  it("approve shows 'Entity created' and links the new entity", async () => {
    const stub = mutationStub({ result: verdict("approved", "e-9") });
    approveMock.mockReturnValue(stub);
    renderDetail();
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    expect(stub.mutate).toHaveBeenCalledWith({ candidateId: "c-1" }, expect.anything());
    expect(await screen.findByText("Entity created.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View entity" })).toHaveAttribute(
      "href",
      "/entities/e-9"
    );
  });

  it("shows the superseded message", async () => {
    approveMock.mockReturnValue(mutationStub({ result: verdict("superseded") }));
    renderDetail();
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    expect(
      await screen.findByText(/Already existed.*linked, not duplicated/)
    ).toBeInTheDocument();
  });

  it("reject shows the rejected message", async () => {
    const stub = mutationStub({ result: verdict("rejected") });
    rejectMock.mockReturnValue(stub);
    renderDetail();
    fireEvent.click(screen.getByRole("button", { name: "Reject" }));
    expect(stub.mutate).toHaveBeenCalledTimes(1);
    expect(await screen.findByText("Candidate rejected.")).toBeInTheDocument();
  });

  it("shows 'Already decided' for a failed outcome", async () => {
    approveMock.mockReturnValue(mutationStub({ result: verdict("failed") }));
    renderDetail();
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    expect(await screen.findByText("Already decided.")).toBeInTheDocument();
  });

  it("maps a 404 to 'candidate no longer exists'", async () => {
    approveMock.mockReturnValue(mutationStub({ error: { type: "client", message: "x", status: 404 } }));
    renderDetail();
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    expect(await screen.findByText(/no longer exists/)).toBeInTheDocument();
  });

  it("on 409 explains the identity requirement and removes the actions", async () => {
    approveMock.mockReturnValue(mutationStub({ error: { type: "client", message: "x", status: 409 } }));
    renderDetail();
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    expect(
      await screen.findByText(/canonical identity must be established first/)
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reject" })).not.toBeInTheDocument();
  });

  it("disables both buttons while a mutation is pending", () => {
    approveMock.mockReturnValue(mutationStub({}, true));
    renderDetail();
    expect(screen.getByRole("button", { name: "Approving..." })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Reject" })).toBeDisabled();
  });

  it("announces via a polite live region and moves focus to the outcome", async () => {
    approveMock.mockReturnValue(mutationStub({ result: verdict("approved") }));
    renderDetail();
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    const msg = await screen.findByText("Entity created.");
    expect(msg.closest("[aria-live='polite']")).not.toBeNull();
    await waitFor(() => expect(msg).toHaveFocus());
  });
});
