/**
 * EntityDetailPage — alias name/type edit affordance (#289).
 *
 * A rename changes what text matches, so — like the case-sensitivity flag —
 * it must be followed by a full rescan for the change to take effect. A
 * type-only edit doesn't affect matching, so it only needs the alias list
 * refreshed, not a rescan. An empty body (no field actually changed) must be
 * unreachable — the backend 422s on it — so Save stays disabled until
 * something changes.
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
import { updateEntityAlias } from "../../api/entityMentions";

const ALIAS_ID = "cccccccc-cccc-4ccc-8ccc-cccccccccccc";
const ENTITY_ID = "entity-uuid-003";

function mockEntity() {
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
        occurrence_count: 4,
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

function openEditor() {
  return screen.getByRole("button", { name: /edit alias "test alias"/i });
}

describe("EntityDetailPage — alias name/type edit (#289)", () => {
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
      alias_name: "Test Alias",
      alias_type: "name_variant",
      occurrence_count: 4,
      case_sensitive: false,
    });
  });

  it("renders an Edit control for the alias", () => {
    renderPage();
    expect(openEditor()).toBeInTheDocument();
  });

  it("opens an editor pre-filled with the current name and type", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(openEditor());

    expect(screen.getByRole("textbox", { name: /alias name for "test alias"/i })).toHaveValue("Test Alias");
    expect(screen.getByRole("combobox", { name: /alias type for "test alias"/i })).toHaveValue("name_variant");
  });

  it("disables Save until a field actually changes — an empty PATCH must be unreachable", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(openEditor());

    expect(screen.getByRole("button", { name: /^save$/i })).toBeDisabled();
  });

  it("disables Save when the name is cleared to blank", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(openEditor());
    await user.clear(screen.getByRole("textbox", { name: /alias name for "test alias"/i }));

    expect(screen.getByRole("button", { name: /^save$/i })).toBeDisabled();
  });

  it("enables Save once the name changes, and calls updateEntityAlias with only alias_name", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(openEditor());
    const nameInput = screen.getByRole("textbox", { name: /alias name for "test alias"/i });
    await user.clear(nameInput);
    await user.type(nameInput, "Renamed Alias");

    expect(screen.getByRole("button", { name: /^save$/i })).not.toBeDisabled();
    await user.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => {
      expect(updateEntityAlias).toHaveBeenCalledWith(ENTITY_ID, ALIAS_ID, {
        alias_name: "Renamed Alias",
      });
    });
  });

  it("rebuilds mentions after a rename — matching changed", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(openEditor());
    const nameInput = screen.getByRole("textbox", { name: /alias name for "test alias"/i });
    await user.clear(nameInput);
    await user.type(nameInput, "Renamed Alias");
    await user.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => {
      expect(scanMutate).toHaveBeenCalledTimes(1);
    });
    const [variables] = scanMutate.mock.calls[0] as [
      { options?: { full_rescan?: boolean } },
    ];
    expect(variables.options?.full_rescan).toBe(true);
  });

  it("changing only the type calls updateEntityAlias with only alias_type, and does NOT rescan", async () => {
    const user = userEvent.setup();
    const { queryClient } = renderPage();
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    await user.click(openEditor());
    await user.selectOptions(screen.getByRole("combobox", { name: /alias type for "test alias"/i }), "nickname");
    await user.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => {
      expect(updateEntityAlias).toHaveBeenCalledWith(ENTITY_ID, ALIAS_ID, {
        alias_type: "nickname",
      });
    });
    // A type-only change doesn't affect what text matches — no rescan.
    expect(scanMutate).not.toHaveBeenCalled();
    // The alias list still needs a plain refresh.
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["entity-detail", ENTITY_ID] })
    );
  });

  it("closes the editor on successful save", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(openEditor());
    const nameInput = screen.getByRole("textbox", { name: /alias name for "test alias"/i });
    await user.clear(nameInput);
    await user.type(nameInput, "Renamed Alias");
    await user.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => {
      expect(screen.queryByRole("textbox", { name: /alias name for "test alias"/i })).not.toBeInTheDocument();
    });
  });

  it("Cancel closes the editor without calling the API", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(openEditor());
    const nameInput = screen.getByRole("textbox", { name: /alias name for "test alias"/i });
    await user.clear(nameInput);
    await user.type(nameInput, "Renamed Alias");
    await user.click(screen.getByRole("button", { name: /^cancel$/i }));

    expect(updateEntityAlias).not.toHaveBeenCalled();
    expect(screen.queryByRole("textbox", { name: /alias name for "test alias"/i })).not.toBeInTheDocument();
  });

  it("shows the accents-and-case-ignored message on a 409 rename collision, and keeps the editor open", async () => {
    vi.mocked(updateEntityAlias).mockRejectedValue({ status: 409 });
    const user = userEvent.setup();
    renderPage();

    await user.click(openEditor());
    const nameInput = screen.getByRole("textbox", { name: /alias name for "test alias"/i });
    await user.clear(nameInput);
    await user.type(nameInput, "Renamed Alias");
    await user.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(/already covered by an existing alias/i);
    });
    expect(screen.getByRole("textbox", { name: /alias name for "test alias"/i })).toBeInTheDocument();
    expect(scanMutate).not.toHaveBeenCalled();
  });

  it("shows a not-found message on a 404", async () => {
    vi.mocked(updateEntityAlias).mockRejectedValue({ status: 404 });
    const user = userEvent.setup();
    renderPage();

    await user.click(openEditor());
    const nameInput = screen.getByRole("textbox", { name: /alias name for "test alias"/i });
    await user.clear(nameInput);
    await user.type(nameInput, "Renamed Alias");
    await user.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(/alias not found/i);
    });
  });
});
