/**
 * EntityDetailPage — per-alias case-sensitivity toggle (#177).
 *
 * An alias that is also an ordinary word matches every occurrence of that word.
 * Case sometimes separates the two and sometimes does not — on real data one
 * entity's lowercase hits were almost all the common noun, while another's were
 * mostly the person with automatic transcription failing to capitalise. So the
 * switch is a per-alias human decision, and these tests cover the two things
 * that make it usable: it persists, and it rebuilds mentions afterwards.
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
// Stubbed for the same reason as the sections above: the global useQuery mock
// hands every consumer the entity payload, which this panel cannot read.
vi.mock("../../components/entity/CooccurringPanel", () => ({
  CooccurringPanel: () => null,
}));

vi.mock("../../api/entityMentions", () => ({
  createEntityAlias: vi.fn(),
  updateEntityAlias: vi.fn(),
}));

vi.mock("@tanstack/react-query", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@tanstack/react-query")>();
  return { ...actual, useQuery: vi.fn() };
});

import { useQuery } from "@tanstack/react-query";
import { updateEntityAlias } from "../../api/entityMentions";

const ALIAS_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";

function mockEntity(caseSensitive = false) {
  return {
    entity_id: "entity-uuid-001",
    canonical_name: "Marcus Reed",
    entity_type: "person",
    description: null,
    status: "active",
    mention_count: 50,
    video_count: 12,
    by_source: { manual: 0, transcript: 12, title: 0, description: 0, tag: 0 },
    aliases: [
      {
        id: ALIAS_ID,
        alias_name: "Ordinaryword",
        alias_type: "name_variant",
        occurrence_count: 4,
        case_sensitive: caseSensitive,
      },
    ],
    exclusion_patterns: [] as string[],
  };
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/entities/entity-uuid-001"]}>
        <Routes>
          <Route path="/entities/:entityId" element={<EntityDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("EntityDetailPage — alias case-sensitivity toggle (#177)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useQuery).mockReturnValue({
      data: mockEntity(),
      isLoading: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof useQuery>);
    vi.mocked(updateEntityAlias).mockResolvedValue({
      id: ALIAS_ID,
      alias_name: "Ordinaryword",
      alias_type: "name_variant",
      occurrence_count: 4,
      case_sensitive: true,
    });
  });

  it("renders an unchecked toggle for an alias that matches any casing", () => {
    renderPage();
    const toggle = screen.getByRole("checkbox", { name: /match case/i });
    expect(toggle).toBeInTheDocument();
    expect(toggle).not.toBeChecked();
  });

  it("reflects an alias that already opted in", () => {
    vi.mocked(useQuery).mockReturnValue({
      data: mockEntity(true),
      isLoading: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof useQuery>);

    renderPage();
    expect(screen.getByRole("checkbox", { name: /match case/i })).toBeChecked();
  });

  it("persists the change against the alias, not the entity", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("checkbox", { name: /match case/i }));

    await waitFor(() => {
      expect(updateEntityAlias).toHaveBeenCalledWith(
        "entity-uuid-001",
        ALIAS_ID,
        true
      );
    });
  });

  it("rebuilds mentions after the flag is saved", async () => {
    // Without this the toggle is inert: matching rules are applied when a scan
    // runs, so flipping the switch alone changes nothing the user can see, and
    // they conclude the feature is broken.
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("checkbox", { name: /match case/i }));

    await waitFor(() => {
      expect(scanMutate).toHaveBeenCalledTimes(1);
    });
    const [variables] = scanMutate.mock.calls[0] as [
      { options?: { full_rescan?: boolean } },
    ];
    expect(variables.options?.full_rescan).toBe(true);
  });

  it("does not rescan when saving the flag failed", async () => {
    // Rebuilding against a flag that was never stored would silently produce
    // the old result and read as the toggle not working.
    vi.mocked(updateEntityAlias).mockRejectedValue(new Error("boom"));
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("checkbox", { name: /match case/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(/could not save/i);
    });
    expect(scanMutate).not.toHaveBeenCalled();
  });

  it("reverts the switch when saving failed", async () => {
    vi.mocked(updateEntityAlias).mockRejectedValue(new Error("boom"));
    const user = userEvent.setup();
    renderPage();

    const toggle = screen.getByRole("checkbox", { name: /match case/i });
    await user.click(toggle);

    await waitFor(() => expect(toggle).not.toBeChecked());
  });
});
