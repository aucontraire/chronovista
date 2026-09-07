/**
 * EntityDetailPage — reinforced delete confirmation for the Primary alias
 * (Feature 075, #301, User Story 2).
 *
 * Deleting the Primary alias (the entity's own name) is data-safe and undoable
 * (#298) — in fact the #298 guard keeps every mention that folds to the
 * canonical name, so deleting the self-alias strips ~0 mentions. This suite
 * verifies that the confirmation for the Primary alias is DISTINCT from and
 * STRONGER than the ordinary one: it states the alias is the entity's own name
 * and does NOT threaten mention removal, while remaining a single confirm step.
 * Ordinary aliases must keep the unchanged confirmation (regression guard).
 *
 * Neutral placeholder names only (public repo).
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { EntityDetailPage } from "../EntityDetailPage";

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
    mutate: vi.fn(),
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
  undoAliasDeletion: vi.fn(),
}));

vi.mock("@tanstack/react-query", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@tanstack/react-query")>();
  return { ...actual, useQuery: vi.fn() };
});

import { useQuery } from "@tanstack/react-query";
import { deleteEntityAlias } from "../../api/entityMentions";

const ENTITY_ID = "entity-uuid-075b";
const PRIMARY_ALIAS_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const ORDINARY_ALIAS_ID = "cccccccc-cccc-4ccc-8ccc-cccccccccccc";
const OPERATION_ID = "op-eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee";
const CANONICAL = "Acme Corporation";

function mockEntity() {
  return {
    entity_id: ENTITY_ID,
    canonical_name: CANONICAL,
    entity_type: "organization",
    description: null,
    status: "active",
    mention_count: 40,
    video_count: 9,
    by_source: { manual: 0, transcript: 9, title: 0, description: 0, tag: 0 },
    aliases: [
      {
        id: PRIMARY_ALIAS_ID,
        alias_name: CANONICAL, // self-alias -> Primary
        alias_type: "name_variant",
        occurrence_count: 7,
        case_sensitive: false,
      },
      {
        id: ORDINARY_ALIAS_ID,
        alias_name: "Acme", // ordinary nickname
        alias_type: "nickname",
        occurrence_count: 4,
        case_sensitive: false,
      },
    ],
    exclusion_patterns: [] as string[],
  };
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
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

describe("EntityDetailPage — Primary alias delete guard (#301)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useQuery).mockReturnValue({
      data: mockEntity(),
      isLoading: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof useQuery>);
    vi.mocked(deleteEntityAlias).mockResolvedValue({
      id: PRIMARY_ALIAS_ID,
      alias_name: CANONICAL,
      alias_type: "name_variant",
      occurrence_count: 7,
      case_sensitive: false,
      removed_mention_count: 0, // #298 guard keeps canonical-name mentions
      operation_id: OPERATION_ID,
    });
  });

  it("(a) the Primary alias confirmation states it is the entity's own name and is distinct from the ordinary one", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(
      screen.getByRole("button", { name: new RegExp(`delete alias "${CANONICAL}"`, "i") })
    );

    // Reinforced copy: names it as the entity's own name…
    expect(screen.getByText(/entity's own name/i)).toBeInTheDocument();
    // …and does NOT use the ordinary "remove about N auto-detected mentions" threat,
    // because deleting the self-alias strips no mentions (they match the canonical name).
    expect(
      screen.queryByText(/remove about \d+ auto-detected/i)
    ).not.toBeInTheDocument();
  });

  it("(a') the Primary confirmation is styled distinctly (red) from the ordinary (amber)", async () => {
    const user = userEvent.setup();
    renderPage();

    // Primary confirmation box carries the red styling.
    await user.click(
      screen.getByRole("button", { name: new RegExp(`delete alias "${CANONICAL}"`, "i") })
    );
    const primaryBox = screen.getByText(/entity's own name/i).closest("div");
    expect(primaryBox?.className).toMatch(/red/);
    expect(primaryBox?.className).not.toMatch(/amber/);

    // Ordinary confirmation box carries the amber styling (and not red).
    await user.click(screen.getByRole("button", { name: /delete alias "acme"/i }));
    const ordinaryBox = screen
      .getByText(/remove about 4 auto-detected/i)
      .closest("div");
    expect(ordinaryBox?.className).toMatch(/amber/);
    expect(ordinaryBox?.className).not.toMatch(/red/);
  });

  it("(b) confirming still deletes via the existing path and offers Undo", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(
      screen.getByRole("button", { name: new RegExp(`delete alias "${CANONICAL}"`, "i") })
    );
    await user.click(
      screen.getByRole("button", {
        name: new RegExp(`confirm deletion of alias "${CANONICAL}"`, "i"),
      })
    );

    await waitFor(() => {
      expect(deleteEntityAlias).toHaveBeenCalledWith(ENTITY_ID, PRIMARY_ALIAS_ID);
    });
    await waitFor(() => {
      expect(screen.getByRole("status")).toHaveTextContent(/deleted/i);
    });
    expect(screen.getByRole("button", { name: /^undo$/i })).toBeInTheDocument();
  });

  it("(c) cancelling the Primary alias deletion deletes nothing", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(
      screen.getByRole("button", { name: new RegExp(`delete alias "${CANONICAL}"`, "i") })
    );
    await user.click(
      screen.getByRole("button", {
        name: new RegExp(`cancel deletion of alias "${CANONICAL}"`, "i"),
      })
    );

    expect(deleteEntityAlias).not.toHaveBeenCalled();
    expect(
      screen.queryByRole("button", {
        name: new RegExp(`confirm deletion of alias "${CANONICAL}"`, "i"),
      })
    ).not.toBeInTheDocument();
  });

  it("(d) an ordinary alias keeps the unchanged confirmation (regression guard)", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("button", { name: /delete alias "acme"/i }));

    // Ordinary confirmation copy is unchanged…
    expect(
      screen.getByText(/remove about 4 auto-detected mentions/i)
    ).toBeInTheDocument();
    expect(screen.getByText(/will be kept/i)).toBeInTheDocument();
    // …and it does NOT carry the Primary "entity's own name" wording.
    expect(screen.queryByText(/entity's own name/i)).not.toBeInTheDocument();
  });
});
