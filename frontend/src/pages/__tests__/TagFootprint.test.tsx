/**
 * Tests for the tag-footprint surfaces (Feature 097, US4).
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router-dom";

import { CandidateDetailPage } from "../CandidateDetailPage";
import { EntityTagFootprintSection } from "../../components/entity/EntityTagFootprintSection";
import { useLinkEntityTag } from "../../hooks/useEntityTags";
import * as candidatesApi from "../../api/candidates";
import type { CandidateDetail, TagFootprintMatch } from "../../api/candidates";

const candidateFootprintMock = vi.fn();
const approveMutateMock = vi.fn();
const entityFootprintMock = vi.fn();

vi.mock("../../hooks/useCandidates", () => ({
  useCandidateDetail: () => ({
    data: {
      id: "c-1",
      source_channel: "relation",
      wikidata_qid: "Q1",
      label: "Candidate Alpha",
      label_normalized: "candidate alpha",
      type_hint: "person",
      token_count: 2,
      corroboration_count: 1,
      dangling_edge_count: 0,
      salience: 0.5,
      score: 1,
      triage: "worth_review",
      provenance: {},
      possible_duplicate_of_id: null,
      review_status: "pending",
      reviewed_by: null,
      reviewed_at: null,
      created_entity_id: null,
      last_generated_at: "2026-01-01T00:00:00Z",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    } satisfies CandidateDetail,
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
  }),
  useCandidateTagFootprint: (...a: unknown[]) => candidateFootprintMock(...a),
  useApproveCandidate: () => ({ mutate: approveMutateMock, isPending: false }),
  useRejectCandidate: () => ({ mutate: vi.fn(), isPending: false }),
}));
vi.mock("../../hooks/useEntityDetail", () => ({
  useEntityDetail: () => ({ entityDetail: undefined, isLoading: false }),
}));

vi.mock("../../hooks/useEntityTags", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../hooks/useEntityTags")>();
  return {
    ...actual,
    useEntityTagFootprint: (...a: unknown[]) => entityFootprintMock(...a),
  };
});

const match = (over: Partial<TagFootprintMatch> = {}): TagFootprintMatch => ({
  normalized_form: "sample tag",
  would_newly_associate: 4,
  owned_by_entity_id: null,
  ...over,
});

function renderCandidate() {
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

describe("candidate tag-footprint preview", () => {
  it("shows the preview when a delta is positive", () => {
    candidateFootprintMock.mockReturnValue({ data: { matches: [match()] } });
    renderCandidate();
    expect(
      screen.getByText(/would also associate 4 more videos/)
    ).toBeInTheDocument();
  });

  it("shows nothing when matches is empty", () => {
    candidateFootprintMock.mockReturnValue({ data: { matches: [] } });
    renderCandidate();
    expect(screen.queryByText(/If approved, linking/)).not.toBeInTheDocument();
  });

  it("still shows the matching tag, informationally, when the delta is 0", () => {
    candidateFootprintMock.mockReturnValue({
      data: { matches: [match({ would_newly_associate: 0 })] },
    });
    renderCandidate();
    expect(screen.getByText(/Matches tag/)).toBeInTheDocument();
    expect(screen.queryByText(/If approved, linking/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /link tag/i })).not.toBeInTheDocument();
  });
});

const INSPECT_NAME = "View videos tagged «sample tag» (opens in a new tab)";

describe("tag inspect link", () => {
  it("opens the canonical-tag videos filter in a new tab (candidate)", () => {
    candidateFootprintMock.mockReturnValue({ data: { matches: [match()] } });
    renderCandidate();
    const a = screen.getByRole("link", { name: INSPECT_NAME });
    expect(a).toHaveAttribute("href", "/videos?canonical_tag=sample%20tag");
    expect(a).toHaveAttribute("target", "_blank");
    expect(a).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("opens the canonical-tag videos filter in a new tab (entity)", () => {
    entityFootprintMock.mockReturnValue({ data: { matches: [match()] } });
    renderSection();
    const a = screen.getByRole("link", { name: INSPECT_NAME });
    expect(a).toHaveAttribute("href", "/videos?canonical_tag=sample%20tag");
    expect(a).toHaveAttribute("target", "_blank");
    expect(a).toHaveAttribute("rel", "noopener noreferrer");
  });
});

describe("link-on-approval opt-in", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    approveMutateMock.mockReset();
  });

  const checkbox = () => screen.queryByRole("checkbox", { name: /link this tag when i approve/i });

  function approveWith(result: Record<string, unknown>) {
    approveMutateMock.mockImplementation(
      (_vars: unknown, opts: { onSuccess: (r: unknown) => void }) => opts.onSuccess(result)
    );
  }

  it("is offered, unchecked, for a single unowned match", () => {
    candidateFootprintMock.mockReturnValue({ data: { matches: [match()] } });
    renderCandidate();
    expect(checkbox()).not.toBeChecked();
  });

  it("is not offered when owned elsewhere, with no match, or with several matches", () => {
    candidateFootprintMock.mockReturnValue({
      data: { matches: [match({ owned_by_entity_id: "e-9" })] },
    });
    const { unmount } = renderCandidate();
    expect(checkbox()).not.toBeInTheDocument();
    unmount();
    candidateFootprintMock.mockReturnValue({ data: { matches: [] } });
    const second = renderCandidate();
    expect(checkbox()).not.toBeInTheDocument();
    second.unmount();
    candidateFootprintMock.mockReturnValue({
      data: { matches: [match(), match({ normalized_form: "other tag" })] },
    });
    renderCandidate();
    expect(checkbox()).not.toBeInTheDocument();
  });

  it("links the created entity when checked and approved", async () => {
    candidateFootprintMock.mockReturnValue({ data: { matches: [match()] } });
    const linkSpy = vi.spyOn(candidatesApi, "linkEntityTag").mockResolvedValue({
      normalized_form: "sample tag",
      linked_entity_id: "e-new",
    });
    approveWith({ outcome: "approved", candidate_id: "c-1", created_entity_id: "e-new", detail: null });
    renderCandidate();
    fireEvent.click(checkbox()!);
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    await waitFor(() =>
      expect(linkSpy).toHaveBeenCalledWith("e-new", {
        normalized_form: "sample tag",
        entity_type: "person",
      })
    );
  });

  it("does not link when left unchecked", () => {
    candidateFootprintMock.mockReturnValue({ data: { matches: [match()] } });
    const linkSpy = vi.spyOn(candidatesApi, "linkEntityTag");
    approveWith({ outcome: "approved", candidate_id: "c-1", created_entity_id: "e-new", detail: null });
    renderCandidate();
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    expect(linkSpy).not.toHaveBeenCalled();
  });

  it("skips the link silently when the outcome is superseded", () => {
    candidateFootprintMock.mockReturnValue({ data: { matches: [match()] } });
    const linkSpy = vi.spyOn(candidatesApi, "linkEntityTag");
    approveWith({ outcome: "superseded", candidate_id: "c-1", created_entity_id: null, detail: null });
    renderCandidate();
    fireEvent.click(checkbox()!);
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    expect(linkSpy).not.toHaveBeenCalled();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

describe("link consequence info", () => {
  const SENTENCE = /linking connects every video that has this tag to this entity/i;

  it("reveals the consequence and dismisses with Escape, returning focus", () => {
    candidateFootprintMock.mockReturnValue({ data: { matches: [match()] } });
    renderCandidate();
    const info = screen.getByRole("button", { name: /what does linking a tag do/i });
    expect(info).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText(SENTENCE)).not.toBeInTheDocument();
    fireEvent.click(info);
    expect(info).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText(SENTENCE)).toBeInTheDocument();
    fireEvent.keyDown(info, { key: "Escape" });
    expect(screen.queryByText(SENTENCE)).not.toBeInTheDocument();
    expect(info).toHaveFocus();
  });

  it("is also present beside the entity Link button", () => {
    entityFootprintMock.mockReturnValue({ data: { matches: [match()] } });
    renderSection();
    fireEvent.click(screen.getByRole("button", { name: /what does linking a tag do/i }));
    expect(screen.getByText(SENTENCE)).toBeInTheDocument();
  });
});

function renderSection(client = new QueryClient()) {
  return {
    client,
    ...render(
      <QueryClientProvider client={client}>
        <EntityTagFootprintSection
          entityId="e-1"
          entityName="Entity One"
          entityType="person"
        />
      </QueryClientProvider>
    ),
  };
}

describe("EntityTagFootprintSection", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    entityFootprintMock.mockReset();
  });

  it("renders nothing when there is no matching tag", () => {
    entityFootprintMock.mockReturnValue({ data: { matches: [] } });
    const { container } = renderSection();
    expect(container).toBeEmptyDOMElement();
  });

  it("shows an unlinked delta-0 match with a Link button", () => {
    entityFootprintMock.mockReturnValue({
      data: { matches: [match({ would_newly_associate: 0 })] },
    });
    renderSection();
    expect(screen.getByText(/already associated by name/i)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /link tag sample tag/i })
    ).toBeInTheDocument();
  });

  it("links with the entity type and invalidates the association family", async () => {
    entityFootprintMock.mockReturnValue({ data: { matches: [match()] } });
    const linkSpy = vi.spyOn(candidatesApi, "linkEntityTag").mockResolvedValue({
      normalized_form: "sample tag",
      linked_entity_id: "e-1",
    });
    const client = new QueryClient();
    const invalidate = vi.spyOn(client, "invalidateQueries");
    renderSection(client);

    fireEvent.click(screen.getByRole("button", { name: /link tag sample tag/i }));

    await waitFor(() =>
      expect(linkSpy).toHaveBeenCalledWith("e-1", {
        normalized_form: "sample tag",
        entity_type: "person",
      })
    );
    await waitFor(() => {
      const keys = invalidate.mock.calls.map((c) => JSON.stringify(c[0]?.queryKey));
      for (const k of [
        ["entity-detail", "e-1"],
        ["entity-videos"],
        ["video-entities"],
        ["entities"],
        ["entitySearch"],
        ["entity-tags", "e-1"],
        ["canonical-tags"],
        ["entity-tag-footprint", "e-1"],
      ]) {
        expect(keys).toContain(JSON.stringify(k));
      }
    });
  });

  it("shows an informational note, with no link action, for a tag owned by another entity", () => {
    entityFootprintMock.mockReturnValue({
      data: { matches: [match({ owned_by_entity_id: "e-2" })] },
    });
    const linkSpy = vi.spyOn(candidatesApi, "linkEntityTag");
    renderSection();

    expect(
      screen.getByText(/already linked to another entity/i)
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /link tag sample tag/i })
    ).not.toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(linkSpy).not.toHaveBeenCalled();
  });

  it("shows a Linked confirmation, not a Link button, when already owned by this entity", () => {
    entityFootprintMock.mockReturnValue({
      data: { matches: [match({ owned_by_entity_id: "e-1" })] },
    });
    renderSection();
    expect(screen.getByText(/✓ Linked/)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});

// Guards the export used by the section.
describe("useLinkEntityTag", () => {
  it("is exported", () => {
    expect(typeof useLinkEntityTag).toBe("function");
  });
});
