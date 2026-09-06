/**
 * EntityDetailPage — alias delete affordance (#289, "Level 1" follow-up).
 *
 * Deleting an alias is destructive, so it requires a confirm step. The
 * backend also retracts the alias's auto-detected (rule_match) mentions —
 * preserving manually-added and correction-derived ones — so the
 * confirmation must say mentions will be REMOVED (using occurrence_count as
 * the "about N" figure), and a successful delete must invalidate the same
 * association-affecting query families a mention-changing scan does
 * (entity-detail, entity-videos, video-entities, entities, entitySearch) —
 * without actually triggering a rescan, since the server already did the
 * removal and recompute.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { EntityDetailPage } from "../EntityDetailPage";

const scanMutate = vi.fn();

vi.mock("../../hooks/useEntityMentions", () => ({
  useEntityVideos: vi.fn(() => ({
    videos: [],
    total: null,
    pagination: null,
    isLoading: false,
    isError: false,
    error: null,
    hasNextPage: false,
    isFetchingNextPage: false,
    fetchNextPage: vi.fn(),
    loadMoreRef: { current: null },
  })),
  useVideoEntities: vi.fn(() => ({
    entities: [],
    isLoading: false,
    isError: false,
    error: null,
  })),
  useDeleteManualAssociation: vi.fn(() => ({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
    isSuccess: false,
  })),
  useScanEntity: vi.fn(() => ({
    mutate: scanMutate,
    isPending: false,
    isError: false,
    error: null,
    data: null,
    reset: vi.fn(),
  })),
  useScanVideoEntities: vi.fn(() => ({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
    data: null,
    reset: vi.fn(),
  })),
  useUpdateEntity: vi.fn(() => ({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
    isSuccess: false,
    reset: vi.fn(),
  })),
}));

vi.mock("../../components/corrections/PhoneticVariantsSection", () => ({
  PhoneticVariantsSection: () => null,
}));
vi.mock("../../components/corrections/ExclusionPatternsSection", () => ({
  ExclusionPatternsSection: () => null,
}));
vi.mock("../../components/entity/CooccurringPanel", () => ({
  CooccurringPanel: () => null,
}));

vi.mock("../../api/entityMentions", () => ({
  createEntityAlias: vi.fn(),
  updateEntityAlias: vi.fn(),
  deleteEntityAlias: vi.fn(),
}));

vi.mock("@tanstack/react-query", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@tanstack/react-query")>();
  return { ...actual, useQuery: vi.fn() };
});

import { useQuery } from "@tanstack/react-query";
import { deleteEntityAlias } from "../../api/entityMentions";

const ALIAS_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
const ENTITY_ID = "entity-uuid-002";

function mockEntity(occurrenceCount = 7) {
  return {
    entity_id: ENTITY_ID,
    canonical_name: "Test Person",
    entity_type: "person",
    description: null,
    status: "active",
    mention_count: 50,
    video_count: 12,
    by_source: { manual: 0, transcript: 12, title: 0, description: 0, tag: 0 },
    aliases: [
      {
        id: ALIAS_ID,
        alias_name: "Test Alias",
        alias_type: "name_variant",
        occurrence_count: occurrenceCount,
        case_sensitive: false,
      },
    ],
    exclusion_patterns: [] as string[],
  };
}

function renderPage(queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })) {
  return {
    queryClient,
    ...render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[`/entities/${ENTITY_ID}`]}>
          <Routes>
            <Route path="/entities/:entityId" element={<EntityDetailPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    ),
  };
}

describe("EntityDetailPage — alias delete (#289)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useQuery).mockReturnValue({
      data: mockEntity(),
      isLoading: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof useQuery>);
    vi.mocked(deleteEntityAlias).mockResolvedValue({
      id: ALIAS_ID,
      alias_name: "Test Alias",
      alias_type: "name_variant",
      occurrence_count: 7,
      case_sensitive: false,
      removed_mention_count: 7,
    });
  });

  it("renders a Delete control for the alias", () => {
    renderPage();
    expect(
      screen.getByRole("button", { name: /delete alias "test alias"/i })
    ).toBeInTheDocument();
  });

  it("does not delete on a single click — shows a confirmation first", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("button", { name: /delete alias "test alias"/i }));

    expect(deleteEntityAlias).not.toHaveBeenCalled();
    expect(
      screen.getByRole("button", { name: /confirm deletion of alias "test alias"/i })
    ).toBeInTheDocument();
  });

  it("surfaces the occurrence_count in the confirmation, and warns the auto-detected mentions will be removed", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("button", { name: /delete alias "test alias"/i }));

    expect(screen.getByText(/remove about 7 auto-detected mentions/i)).toBeInTheDocument();
  });

  it("says manually-added and correction-derived mentions are kept", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("button", { name: /delete alias "test alias"/i }));

    expect(screen.getByText(/will be kept/i)).toBeInTheDocument();
    expect(screen.queryByText(/stay on the entity/i)).not.toBeInTheDocument();
  });

  it("Cancel dismisses the confirmation without deleting", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("button", { name: /delete alias "test alias"/i }));
    await user.click(screen.getByRole("button", { name: /cancel deletion of alias "test alias"/i }));

    expect(deleteEntityAlias).not.toHaveBeenCalled();
    expect(
      screen.queryByRole("button", { name: /confirm deletion of alias "test alias"/i })
    ).not.toBeInTheDocument();
  });

  it("confirming calls deleteEntityAlias with the entity and alias ids", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("button", { name: /delete alias "test alias"/i }));
    await user.click(screen.getByRole("button", { name: /confirm deletion of alias "test alias"/i }));

    await waitFor(() => {
      expect(deleteEntityAlias).toHaveBeenCalledWith(ENTITY_ID, ALIAS_ID);
    });
  });

  it("invalidates entity-detail, entity-videos, video-entities, entities, and entitySearch after a successful delete", async () => {
    // The backend now retracts the alias's auto-detected mentions on
    // delete, changing entity↔video associations — the same shape of
    // change useScanEntity's getInvalidationKeys covers, so the delete
    // success path must invalidate the same families or a deleted alias's
    // mentions would still show in the video list until a manual refresh.
    const user = userEvent.setup();
    const { queryClient } = renderPage();
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    await user.click(screen.getByRole("button", { name: /delete alias "test alias"/i }));
    await user.click(screen.getByRole("button", { name: /confirm deletion of alias "test alias"/i }));

    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: ["entity-detail", ENTITY_ID] })
      );
    });
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["entity-videos", ENTITY_ID] })
    );
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["video-entities"] })
    );
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["entities"] })
    );
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["entitySearch"] })
    );
  });

  it("does NOT trigger a rescan on delete — the server already removed the mentions and recomputed counts", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("button", { name: /delete alias "test alias"/i }));
    await user.click(screen.getByRole("button", { name: /confirm deletion of alias "test alias"/i }));

    await waitFor(() => {
      expect(deleteEntityAlias).toHaveBeenCalled();
    });
    expect(scanMutate).not.toHaveBeenCalled();
  });

  it("shows an inline error and keeps the confirmation open when the delete fails", async () => {
    vi.mocked(deleteEntityAlias).mockRejectedValue({ status: 500 });
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("button", { name: /delete alias "test alias"/i }));
    await user.click(screen.getByRole("button", { name: /confirm deletion of alias "test alias"/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(/failed to delete alias/i);
    });
    expect(
      screen.getByRole("button", { name: /confirm deletion of alias "test alias"/i })
    ).toBeInTheDocument();
  });

  it("shows a not-found message on a 404", async () => {
    vi.mocked(deleteEntityAlias).mockRejectedValue({ status: 404 });
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("button", { name: /delete alias "test alias"/i }));
    await user.click(screen.getByRole("button", { name: /confirm deletion of alias "test alias"/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(/alias not found/i);
    });
  });
});
