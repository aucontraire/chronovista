/**
 * Tests for the read-only relationship candidate queue (Feature 107).
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import type {
  RelationshipCandidate,
  RelationshipCandidateListResponse,
} from "../../hooks/useRelationshipCandidates";
import { RelationshipCandidatesPage } from "../RelationshipCandidatesPage";

const hookMock = vi.fn();
vi.mock("../../hooks/useRelationshipCandidates", () => ({
  useRelationshipCandidates: (...a: unknown[]) => hookMock(...a),
}));

function makeCandidate(
  n: number,
  over: Partial<RelationshipCandidate> = {}
): RelationshipCandidate {
  return {
    id: `rc-${n}`,
    entity_a: { id: `a-${n}`, canonical_name: `Entity A${n}`, entity_type: "person" },
    entity_b: { id: `b-${n}`, canonical_name: `Entity B${n}`, entity_type: "person" },
    shared_video_count: 10 + n,
    lift: 9 - n,
    both_typed_eligible: false,
    kb_corroboration_count: 0,
    kb_corroboration_detail: [],
    channel: "title_description",
    channel_video_universe: 1000,
    status: "candidate",
    review_status: null,
    reviewed_at: null,
    ...over,
  };
}

function respond(
  items: RelationshipCandidate[],
  over: Partial<RelationshipCandidateListResponse> = {}
) {
  hookMock.mockReturnValue({
    data: {
      items,
      total: over.total ?? items.length,
      total_before_scoping: over.total ?? items.length,
      head_cutoff: over.total ?? items.length,
      limit: 50,
      offset: 0,
      generated_at: "2026-01-01T00:00:00Z",
      ...over,
    },
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
  });
}

function renderPage() {
  return render(
    <MemoryRouter>
      <RelationshipCandidatesPage />
    </MemoryRouter>
  );
}

describe("RelationshipCandidatesPage", () => {
  beforeEach(() => hookMock.mockReset());

  it("renders rows in the order the API returned them and labels each a candidate", () => {
    respond([makeCandidate(1), makeCandidate(2), makeCandidate(3)]);
    renderPage();
    const rows = screen.getAllByRole("listitem");
    expect(rows).toHaveLength(3);
    expect(within(rows[0]!).getByText("Entity A1")).toBeInTheDocument();
    expect(within(rows[2]!).getByText("Entity A3")).toBeInTheDocument();
    rows.forEach((r) => expect(within(r).getByText("candidate")).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: /confirm|reject|approve/i })).toBeNull();
  });

  it("links both entities to /entities/{id} and shows evidence fields", () => {
    respond([makeCandidate(1, { kb_corroboration_count: 2, kb_corroboration_detail: ["field_x", "field_y"] })]);
    renderPage();
    expect(screen.getByRole("link", { name: "Entity A1" })).toHaveAttribute("href", "/entities/a-1");
    expect(screen.getByRole("link", { name: "Entity B1" })).toHaveAttribute("href", "/entities/b-1");
    expect(screen.getByText("11")).toBeInTheDocument();
    expect(screen.getByText("8.00")).toBeInTheDocument();
    expect(screen.getByText("corroboration 2")).toHaveAttribute("title", "field_x, field_y");
  });

  it("shows the typed-eligible badge without hiding ineligible rows", () => {
    respond([makeCandidate(1, { both_typed_eligible: true }), makeCandidate(2)]);
    renderPage();
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    expect(screen.getAllByText("typed-eligible")).toHaveLength(1);
    expect(hookMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ eligible_only: false })
    );
  });

  it("passes eligible_only to the hook when the toggle is checked", () => {
    respond([makeCandidate(1)]);
    renderPage();
    fireEvent.click(screen.getByRole("checkbox", { name: /measured-precision only/i }));
    expect(hookMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ eligible_only: true, offset: 0 })
    );
  });

  it("renders a friendly empty state, not an error, when total is 0", () => {
    respond([]);
    renderPage();
    expect(screen.getByText(/no relationship candidates yet/i)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows generated_at and pagination with total", () => {
    respond([makeCandidate(1)], { total: 120 });
    renderPage();
    expect(screen.getByText(/last generated/i)).toBeInTheDocument();
    expect(screen.getByText("Showing 1-1 of 120")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(hookMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ offset: 50 })
    );
  });

  it("shows top-N-of-M provenance and stops pagination at the scoped head", () => {
    respond([makeCandidate(1)], {
      total: 500,
      total_before_scoping: 3755,
      head_cutoff: 500,
    });
    renderPage();
    expect(
      screen.getByText(/Showing 1-1 of 500 — top 500 of 3,755/)
    ).toBeInTheDocument();
    const next = screen.getByRole("button", { name: "Next" });
    for (let i = 0; i < 9; i++) {
      expect(next).toBeEnabled();
      fireEvent.click(next);
    }
    expect(next).toBeDisabled();
  });

  it("omits the top-N suffix when a filter leaves fewer rows than the head", () => {
    respond([makeCandidate(1)], {
      total: 388,
      total_before_scoping: 600,
      head_cutoff: 500,
    });
    renderPage();
    expect(screen.getByText("Showing 1-1 of 388")).toBeInTheDocument();
    expect(screen.queryByText(/top 500/)).not.toBeInTheDocument();
  });

  it("defaults to review=all, sort_by=rank desc", () => {
    respond([makeCandidate(1)]);
    renderPage();
    expect(hookMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ review: "all", sort_by: "rank", sort_dir: "desc" })
    );
    expect(screen.getByRole("radio", { name: "All" })).toBeChecked();
  });

  it("review toggle sets the review param, resets offset, and changes the shown set", () => {
    const all = [
      makeCandidate(1, { review_status: "co_cast" }),
      makeCandidate(2),
    ];
    hookMock.mockImplementation((...args: unknown[]) => {
      const p = (args[0] ?? { review: "all" }) as { review: string };
      const items = all.filter((c) =>
        p.review === "all" ? true : p.review === "reviewed" ? c.review_status !== null : c.review_status === null
      );
      return {
        data: { items, total: items.length, total_before_scoping: items.length, head_cutoff: items.length, limit: 50, offset: 0, generated_at: null },
        isLoading: false, isError: false, error: null, refetch: vi.fn(),
      };
    });
    renderPage();
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    fireEvent.click(screen.getByRole("radio", { name: "Reviewed" }));
    expect(hookMock).toHaveBeenLastCalledWith(expect.objectContaining({ review: "reviewed", offset: 0 }));
    expect(screen.getAllByRole("listitem")).toHaveLength(1);
    fireEvent.click(screen.getByRole("radio", { name: "Not reviewed" }));
    expect(hookMock).toHaveBeenLastCalledWith(expect.objectContaining({ review: "unreviewed" }));
    expect(screen.getByText("Entity A2")).toBeInTheDocument();
    expect(screen.queryByText("Entity A1")).toBeNull();
  });

  it("clicking a sort header sets sort_by desc, toggles dir on re-click, and resets offset", () => {
    respond([makeCandidate(1)], { total: 120 });
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.click(screen.getByRole("button", { name: "Lift, not sorted" }));
    expect(hookMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ sort_by: "lift", sort_dir: "desc", offset: 0 })
    );
    const lift = screen.getByRole("button", { name: "Lift, sorted descending" });
    expect(lift).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(lift);
    expect(hookMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ sort_by: "lift", sort_dir: "asc" })
    );
    fireEvent.click(screen.getByRole("button", { name: "Shared videos, not sorted" }));
    expect(hookMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ sort_by: "shared_video_count", sort_dir: "desc" })
    );
    fireEvent.click(screen.getByRole("button", { name: "Reset to rank" }));
    expect(hookMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ sort_by: "rank", sort_dir: "desc" })
    );
  });

  it("shows the verdict badge from review_status, and an unreviewed treatment when null", () => {
    respond([
      makeCandidate(1, { review_status: "coincidence", reviewed_at: "2026-01-02T00:00:00Z" }),
      makeCandidate(2),
    ]);
    renderPage();
    const rows = screen.getAllByRole("listitem");
    expect(within(rows[0]!).getByTestId("review-status-badge")).toHaveTextContent("coincidence");
    expect(within(rows[1]!).getByTestId("review-status-badge")).toHaveTextContent("unreviewed");
  });

  it("verdict checkboxes send a repeatable verdict param, reset offset, and change the shown set", () => {
    const all = [
      makeCandidate(1, { review_status: "co_cast" }),
      makeCandidate(2, { review_status: "covers" }),
      makeCandidate(3, { review_status: "artifact" }),
    ];
    hookMock.mockImplementation((...args: unknown[]) => {
      const p = (args[0] ?? { verdict: [] }) as { verdict: string[] };
      const items = all.filter((c) => p.verdict.length === 0 || p.verdict.includes(c.review_status ?? ""));
      return {
        data: { items, total: 120, total_before_scoping: 120, head_cutoff: 120, limit: 50, offset: 0, generated_at: null },
        isLoading: false, isError: false, error: null, refetch: vi.fn(),
      };
    });
    renderPage();
    expect(hookMock).toHaveBeenLastCalledWith(expect.objectContaining({ verdict: [] }));
    expect(screen.getAllByRole("listitem")).toHaveLength(3);
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.click(screen.getByRole("checkbox", { name: /co_cast/ }));
    fireEvent.click(screen.getByRole("checkbox", { name: /covers/ }));
    expect(hookMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ verdict: ["co_cast", "covers"], offset: 0 })
    );
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    fireEvent.click(screen.getByRole("button", { name: "Clear categories" }));
    expect(hookMock).toHaveBeenLastCalledWith(expect.objectContaining({ verdict: [] }));
  });

  it("has a keyboard-operable info button that reveals lift and corroboration help, and an updated intro", () => {
    respond([makeCandidate(1)]);
    renderPage();
    expect(screen.getByText(/Pairs you.ve reviewed show their verdict/)).toBeInTheDocument();
    expect(screen.queryByText(/nothing here is a verdict/i)).toBeNull();
    const btn = screen.getByRole("button", { name: "What do these terms mean?" });
    expect(btn).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText(/Legend & glossary/)).toBeNull();
    expect(screen.queryByText("co_cast", { selector: "span" })).toBeNull();
    fireEvent.click(btn);
    expect(btn).toHaveAttribute("aria-expanded", "true");
    const panel = screen.getByRole("region", { name: "Relationship candidate key" });
    for (const v of ["associated_with", "co_cast", "covers", "coincidence", "artifact", "unreviewed"]) {
      expect(within(panel).getByText(v)).toBeInTheDocument();
    }
    expect(within(panel).getByText(/castmates/i)).toBeInTheDocument();
    expect(within(panel).getByText("Lift")).toBeInTheDocument();
    expect(within(panel).getByText("Corroboration")).toBeInTheDocument();
    expect(within(panel).getByText(/than chance would predict/)).toBeInTheDocument();
    expect(within(panel).getByText(/knowledge base already partially supports/)).toBeInTheDocument();
    fireEvent.keyDown(panel, { key: "Escape" });
    expect(btn).toHaveAttribute("aria-expanded", "false");
  });
});
