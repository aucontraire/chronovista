/**
 * Tests for EntitiesPage component.
 *
 * Coverage (Feature 038):
 * - Initial render with page title and toolbar
 * - Loading skeleton (EntityLoadingState) during initial fetch
 * - Successful data display: entity cards with all fields
 * - Entity card singular/plural copy for mention_count and video_count
 * - Entity card "No description available" fallback
 * - Entity card links navigate to /entities/:entityId
 * - Entity card aria-label content
 * - Type filter tab selection updates URL search param
 * - "All" tab is selected by default; fallback for unknown types
 * - Has-mentions toggle: aria-checked state and URL param
 * - Search input: value synced from URL param
 * - Sort dropdown: value synced from URL param, "Name (A-Z)" option
 * - Empty state without active filters (no-data message + CLI hint)
 * - Empty state with active filters (filter-adjustment message)
 * - Full error state when no entities are loaded (retry button)
 * - Inline error when entities are loaded but next page fails
 * - Pagination status shown when hasNextPage is true
 * - "All N entities loaded" message at end of list (no next page)
 * - Inline "Loading more entities..." indicator during isFetchingNextPage
 * - Infinite scroll sentinel div is rendered when there is no error
 * - Sentinel div is hidden when isError is true
 * - ARIA live region announces entity count
 * - Accessibility: entity list has role="list"
 * - Accessibility: loading state has role="status" and aria-busy
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, within } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { RefObject } from "react";

import { EntitiesPage } from "../EntitiesPage";

// ---------------------------------------------------------------------------
// Mock useEntities hook
// ---------------------------------------------------------------------------

vi.mock("../../hooks/useEntityMentions", () => ({
  useEntities: vi.fn(),
  // Other hooks in the module are not used by EntitiesPage but must be present
  // to avoid import errors in the module itself.
  useVideoEntities: vi.fn(() => ({
    entities: [],
    isLoading: false,
    isError: false,
    error: null,
  })),
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
  useCreateManualAssociation: vi.fn(() => ({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
    reset: vi.fn(),
  })),
  useDeleteManualAssociation: vi.fn(() => ({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
    reset: vi.fn(),
  })),
  useClassifyTag: vi.fn(() => ({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
    reset: vi.fn(),
  })),
  useCreateEntity: vi.fn(() => ({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
    reset: vi.fn(),
  })),
  useCheckDuplicate: vi.fn(() => ({
    data: null,
    isLoading: false,
    isError: false,
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
}));

import { useEntities } from "../../hooks/useEntityMentions";
import type { EntityListItem } from "../../api/entityMentions";

// ---------------------------------------------------------------------------
// Test data factories
// ---------------------------------------------------------------------------

function createEntity(overrides: Partial<EntityListItem> = {}): EntityListItem {
  return {
    entity_id: "entity-uuid-001",
    canonical_name: "Noam Chomsky",
    entity_type: "person",
    description: "American linguist and political commentator.",
    status: "active",
    mention_count: 42,
    video_count: 8,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Default hook return values
// ---------------------------------------------------------------------------

type UseEntitiesReturn = ReturnType<typeof useEntities>;

/** Default "idle, no data" state. */
const defaultUseEntities: UseEntitiesReturn = {
  entities: [],
  total: null,
  loadedCount: 0,
  isLoading: false,
  isError: false,
  error: null,
  hasNextPage: false,
  isFetchingNextPage: false,
  fetchNextPage: vi.fn(),
  retry: vi.fn(),
  loadMoreRef: { current: null } as RefObject<HTMLDivElement | null>,
};

/** Convenience helper: override specific fields. */
function makeHookReturn(
  overrides: Partial<UseEntitiesReturn>
): UseEntitiesReturn {
  return { ...defaultUseEntities, ...overrides };
}

// ---------------------------------------------------------------------------
// Render helper
// ---------------------------------------------------------------------------

function renderPage(initialSearch = "") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const initialEntry = `/entities${initialSearch}`;
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/entities" element={<EntitiesPage />} />
          <Route path="/entities/:entityId" element={<div>Entity Detail</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(useEntities).mockReturnValue(defaultUseEntities);
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("EntitiesPage", () => {
  // -------------------------------------------------------------------------
  // Rendering — basic structure
  // -------------------------------------------------------------------------

  describe("Basic rendering", () => {
    it("renders the page heading", () => {
      vi.mocked(useEntities).mockReturnValue(
        makeHookReturn({ entities: [createEntity()], total: 1, loadedCount: 1 })
      );
      renderPage();
      expect(
        screen.getByRole("heading", { name: "Entities", level: 1 })
      ).toBeInTheDocument();
    });

    it("sets the document title to 'Entities - ChronoVista'", () => {
      vi.mocked(useEntities).mockReturnValue(
        makeHookReturn({ entities: [createEntity()], total: 1, loadedCount: 1 })
      );
      renderPage();
      expect(document.title).toBe("Entities - ChronoVista");
    });

    it("renders the type filter tabs toolbar", () => {
      vi.mocked(useEntities).mockReturnValue(
        makeHookReturn({ entities: [createEntity()], total: 1, loadedCount: 1 })
      );
      renderPage();
      // TypeFilterTabs renders a <nav role="tablist" aria-label="Entity type filter">
      // The explicit role="tablist" overrides the implicit "navigation" role.
      expect(
        screen.getByRole("tablist", { name: "Entity type filter" })
      ).toBeInTheDocument();
    });

    it("renders the search input", () => {
      vi.mocked(useEntities).mockReturnValue(
        makeHookReturn({ entities: [createEntity()], total: 1, loadedCount: 1 })
      );
      renderPage();
      expect(
        screen.getByRole("searchbox", { name: /search entities/i })
      ).toBeInTheDocument();
    });

    it("renders the sort dropdown", () => {
      vi.mocked(useEntities).mockReturnValue(
        makeHookReturn({ entities: [createEntity()], total: 1, loadedCount: 1 })
      );
      renderPage();
      expect(screen.getByRole("combobox", { name: /sort by/i })).toBeInTheDocument();
    });

    it("renders the has-mentions toggle button", () => {
      vi.mocked(useEntities).mockReturnValue(
        makeHookReturn({ entities: [createEntity()], total: 1, loadedCount: 1 })
      );
      renderPage();
      expect(
        screen.getByRole("switch", { name: /has mentions/i })
      ).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Loading state
  // -------------------------------------------------------------------------

  describe("Loading state", () => {
    beforeEach(() => {
      vi.mocked(useEntities).mockReturnValue(
        makeHookReturn({ isLoading: true })
      );
    });

    it("renders the loading skeleton with role='status'", () => {
      renderPage();
      expect(
        screen.getByRole("status", { name: /loading entities/i })
      ).toBeInTheDocument();
    });

    it("skeleton has aria-busy='true'", () => {
      renderPage();
      const status = screen.getByRole("status", { name: /loading entities/i });
      expect(status).toHaveAttribute("aria-busy", "true");
    });

    it("renders a screen-reader announcement", () => {
      renderPage();
      expect(screen.getByText(/loading entities/i)).toBeInTheDocument();
    });

    it("does not render entity cards during loading", () => {
      renderPage();
      expect(screen.queryByRole("list", { name: /entity list/i })).not.toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Data display — entity cards
  // -------------------------------------------------------------------------

  describe("Entity card display", () => {
    it("renders the entity canonical name as a heading", () => {
      vi.mocked(useEntities).mockReturnValue(
        makeHookReturn({
          entities: [createEntity({ canonical_name: "Marie Curie" })],
          total: 1,
          loadedCount: 1,
        })
      );
      renderPage();
      expect(screen.getByRole("heading", { name: "Marie Curie" })).toBeInTheDocument();
    });

    it("renders the entity type badge label inside the card", () => {
      vi.mocked(useEntities).mockReturnValue(
        makeHookReturn({
          entities: [createEntity({ entity_type: "person", canonical_name: "Badge Test" })],
          total: 1,
          loadedCount: 1,
        })
      );
      renderPage();
      // "Person" also appears as a type-filter tab; query within the card link
      const card = screen.getByRole("link", { name: /Badge Test/i });
      expect(within(card).getByText("Person")).toBeInTheDocument();
    });

    it("renders the entity description when present", () => {
      vi.mocked(useEntities).mockReturnValue(
        makeHookReturn({
          entities: [
            createEntity({
              description: "Nobel Prize winning physicist.",
            }),
          ],
          total: 1,
          loadedCount: 1,
        })
      );
      renderPage();
      expect(
        screen.getByText("Nobel Prize winning physicist.")
      ).toBeInTheDocument();
    });

    it("renders 'No description available.' when description is null", () => {
      vi.mocked(useEntities).mockReturnValue(
        makeHookReturn({
          entities: [createEntity({ description: null })],
          total: 1,
          loadedCount: 1,
        })
      );
      renderPage();
      expect(screen.getByText("No description available.")).toBeInTheDocument();
    });

    it("renders mention_count in the stats row", () => {
      vi.mocked(useEntities).mockReturnValue(
        makeHookReturn({
          entities: [createEntity({ mention_count: 17, video_count: 3 })],
          total: 1,
          loadedCount: 1,
        })
      );
      renderPage();
      expect(screen.getByText("17")).toBeInTheDocument();
    });

    it("renders video_count in the stats row", () => {
      vi.mocked(useEntities).mockReturnValue(
        makeHookReturn({
          entities: [createEntity({ mention_count: 17, video_count: 3 })],
          total: 1,
          loadedCount: 1,
        })
      );
      renderPage();
      expect(screen.getByText("3")).toBeInTheDocument();
    });

    it("uses singular 'mention' copy when mention_count is 1", () => {
      vi.mocked(useEntities).mockReturnValue(
        makeHookReturn({
          entities: [createEntity({ mention_count: 1, video_count: 2 })],
          total: 1,
          loadedCount: 1,
        })
      );
      renderPage();
      // The card's aria-label contains "1 mention in"
      const link = screen.getByRole("link", {
        name: /1 mention in/i,
      });
      expect(link).toBeInTheDocument();
    });

    it("uses plural 'mentions' copy when mention_count is greater than 1", () => {
      vi.mocked(useEntities).mockReturnValue(
        makeHookReturn({
          entities: [createEntity({ mention_count: 5, video_count: 2 })],
          total: 1,
          loadedCount: 1,
        })
      );
      renderPage();
      const link = screen.getByRole("link", {
        name: /5 mentions in/i,
      });
      expect(link).toBeInTheDocument();
    });

    it("uses singular 'video' copy when video_count is 1", () => {
      vi.mocked(useEntities).mockReturnValue(
        makeHookReturn({
          entities: [createEntity({ mention_count: 3, video_count: 1 })],
          total: 1,
          loadedCount: 1,
        })
      );
      renderPage();
      const link = screen.getByRole("link", {
        name: /in 1 video$/i,
      });
      expect(link).toBeInTheDocument();
    });

    it("renders cards for multiple entities", () => {
      vi.mocked(useEntities).mockReturnValue(
        makeHookReturn({
          entities: [
            createEntity({ entity_id: "e1", canonical_name: "Alan Turing" }),
            createEntity({ entity_id: "e2", canonical_name: "Ada Lovelace" }),
            createEntity({ entity_id: "e3", canonical_name: "Grace Hopper" }),
          ],
          total: 3,
          loadedCount: 3,
        })
      );
      renderPage();
      expect(screen.getByText("Alan Turing")).toBeInTheDocument();
      expect(screen.getByText("Ada Lovelace")).toBeInTheDocument();
      expect(screen.getByText("Grace Hopper")).toBeInTheDocument();
    });

    it("renders localized mention count (toLocaleString)", () => {
      vi.mocked(useEntities).mockReturnValue(
        makeHookReturn({
          entities: [createEntity({ mention_count: 1000, video_count: 5 })],
          total: 1,
          loadedCount: 1,
        })
      );
      renderPage();
      // 1000 formatted by toLocaleString produces "1,000" in en-US
      expect(screen.getByText("1,000")).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Navigation — entity card links
  // -------------------------------------------------------------------------

  describe("Navigation", () => {
    it("entity card links to /entities/:entityId", () => {
      vi.mocked(useEntities).mockReturnValue(
        makeHookReturn({
          entities: [
            createEntity({
              entity_id: "uuid-abc-123",
              canonical_name: "Test Entity",
            }),
          ],
          total: 1,
          loadedCount: 1,
        })
      );
      renderPage();
      const link = screen.getByRole("link", { name: /Test Entity/i });
      expect(link).toHaveAttribute("href", "/entities/uuid-abc-123");
    });

    it("each card has an accessible aria-label containing canonical name and stats", () => {
      vi.mocked(useEntities).mockReturnValue(
        makeHookReturn({
          entities: [
            createEntity({
              entity_id: "uuid-xyz",
              canonical_name: "MIT",
              entity_type: "organization",
              mention_count: 10,
              video_count: 4,
            }),
          ],
          total: 1,
          loadedCount: 1,
        })
      );
      renderPage();
      const link = screen.getByRole("link", {
        name: /MIT — 10 mentions in 4 videos/i,
      });
      expect(link).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Type filter tabs
  // -------------------------------------------------------------------------

  describe("Type filter tabs", () => {
    beforeEach(() => {
      vi.mocked(useEntities).mockReturnValue(
        makeHookReturn({ entities: [createEntity()], total: 1, loadedCount: 1 })
      );
    });

    it("renders all type tabs", () => {
      renderPage();
      // The <nav> has role="tablist", so query by that explicit role
      const tablist = screen.getByRole("tablist", { name: "Entity type filter" });
      const tabs = within(tablist).getAllByRole("tab");
      const labels = tabs.map((t) => t.textContent);
      expect(labels).toEqual([
        "All",
        "Person",
        "Organization",
        "Place",
        "Event",
        "Work",
        "Technical Term",
        "Concept",
        "Other",
      ]);
    });

    it("'All' tab is selected by default (aria-selected='true')", () => {
      renderPage();
      const allTab = screen.getByRole("tab", { name: "All" });
      expect(allTab).toHaveAttribute("aria-selected", "true");
    });

    it("other tabs are not selected by default", () => {
      renderPage();
      const personTab = screen.getByRole("tab", { name: "Person" });
      expect(personTab).toHaveAttribute("aria-selected", "false");
    });

    it("clicking a type tab sets aria-selected='true' on that tab", () => {
      renderPage();
      const personTab = screen.getByRole("tab", { name: "Person" });
      fireEvent.click(personTab);
      expect(personTab).toHaveAttribute("aria-selected", "true");
    });

    it("clicking a type tab deselects the 'All' tab", () => {
      renderPage();
      const personTab = screen.getByRole("tab", { name: "Person" });
      fireEvent.click(personTab);
      const allTab = screen.getByRole("tab", { name: "All" });
      expect(allTab).toHaveAttribute("aria-selected", "false");
    });

    it("initialises the correct tab as selected from URL search param", () => {
      renderPage("?type=organization");
      const orgTab = screen.getByRole("tab", { name: "Organization" });
      expect(orgTab).toHaveAttribute("aria-selected", "true");
    });

    it("falls back to 'All' tab when URL type param is invalid", () => {
      renderPage("?type=invalid_type");
      const allTab = screen.getByRole("tab", { name: "All" });
      expect(allTab).toHaveAttribute("aria-selected", "true");
    });

    it("clicking 'All' tab deselects any active type tab", () => {
      renderPage("?type=place");
      const allTab = screen.getByRole("tab", { name: "All" });
      const placeTab = screen.getByRole("tab", { name: "Place" });
      expect(placeTab).toHaveAttribute("aria-selected", "true");
      fireEvent.click(allTab);
      expect(allTab).toHaveAttribute("aria-selected", "true");
      expect(placeTab).toHaveAttribute("aria-selected", "false");
    });
  });

  // -------------------------------------------------------------------------
  // Has-mentions toggle
  // -------------------------------------------------------------------------

  describe("Has-mentions toggle", () => {
    beforeEach(() => {
      vi.mocked(useEntities).mockReturnValue(
        makeHookReturn({ entities: [createEntity()], total: 1, loadedCount: 1 })
      );
    });

    it("toggle is off by default (aria-checked='false')", () => {
      renderPage();
      const toggle = screen.getByRole("switch", { name: /has mentions/i });
      expect(toggle).toHaveAttribute("aria-checked", "false");
    });

    it("toggle is on when URL param has_mentions=true is present", () => {
      renderPage("?has_mentions=true");
      const toggle = screen.getByRole("switch", { name: /has mentions/i });
      expect(toggle).toHaveAttribute("aria-checked", "true");
    });

    it("clicking the toggle turns it on", () => {
      renderPage();
      const toggle = screen.getByRole("switch", { name: /has mentions/i });
      fireEvent.click(toggle);
      expect(toggle).toHaveAttribute("aria-checked", "true");
    });

    it("clicking the toggle when on turns it off", () => {
      renderPage("?has_mentions=true");
      const toggle = screen.getByRole("switch", { name: /has mentions/i });
      fireEvent.click(toggle);
      expect(toggle).toHaveAttribute("aria-checked", "false");
    });
  });

  // -------------------------------------------------------------------------
  // Search input
  // -------------------------------------------------------------------------

  describe("Search input", () => {
    beforeEach(() => {
      vi.mocked(useEntities).mockReturnValue(
        makeHookReturn({ entities: [createEntity()], total: 1, loadedCount: 1 })
      );
    });

    it("search input is empty by default", () => {
      renderPage();
      const input = screen.getByRole("searchbox", { name: /search entities/i });
      expect(input).toHaveValue("");
    });

    it("search input reflects the URL search param value", () => {
      renderPage("?search=Chomsky");
      const input = screen.getByRole("searchbox", { name: /search entities/i });
      expect(input).toHaveValue("Chomsky");
    });

    it("typing in the search input updates its value", () => {
      renderPage();
      const input = screen.getByRole("searchbox", {
        name: /search entities/i,
      }) as HTMLInputElement;
      fireEvent.change(input, { target: { value: "Einstein" } });
      expect(input).toHaveValue("Einstein");
    });

    it("clearing the search input sets value to empty string", () => {
      renderPage("?search=Einstein");
      const input = screen.getByRole("searchbox", {
        name: /search entities/i,
      }) as HTMLInputElement;
      fireEvent.change(input, { target: { value: "" } });
      expect(input).toHaveValue("");
    });
  });

  // -------------------------------------------------------------------------
  // Sort dropdown
  // -------------------------------------------------------------------------

  describe("Sort dropdown", () => {
    beforeEach(() => {
      vi.mocked(useEntities).mockReturnValue(
        makeHookReturn({ entities: [createEntity()], total: 1, loadedCount: 1 })
      );
    });

    it("defaults to 'Mentions' sort option", () => {
      renderPage();
      const select = screen.getByRole("combobox", {
        name: /sort by/i,
      }) as HTMLSelectElement;
      expect(select.value).toBe("mentions");
    });

    it("reflects 'name' sort when URL param is set", () => {
      renderPage("?sort=name");
      const select = screen.getByRole("combobox", {
        name: /sort by/i,
      }) as HTMLSelectElement;
      expect(select.value).toBe("name");
    });

    it("renders both sort options", () => {
      renderPage();
      expect(screen.getByRole("option", { name: "Mentions" })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: "Name (A-Z)" })).toBeInTheDocument();
    });

    it("changing the sort dropdown updates the selected value", () => {
      renderPage();
      const select = screen.getByRole("combobox", {
        name: /sort by/i,
      }) as HTMLSelectElement;
      fireEvent.change(select, { target: { value: "name" } });
      expect(select.value).toBe("name");
    });

    it("falls back to 'mentions' when URL sort param is invalid", () => {
      renderPage("?sort=invalid");
      const select = screen.getByRole("combobox", {
        name: /sort by/i,
      }) as HTMLSelectElement;
      expect(select.value).toBe("mentions");
    });
  });

  // -------------------------------------------------------------------------
  // Entity type badge colours (spot-check)
  // -------------------------------------------------------------------------

  describe("Entity type badges", () => {
    const TYPE_LABEL_MAP: Record<string, string> = {
      person: "Person",
      organization: "Organization",
      place: "Place",
      event: "Event",
      work: "Work",
      other: "Other",
    };

    Object.entries(TYPE_LABEL_MAP).forEach(([type, expectedLabel]) => {
      it(`renders '${expectedLabel}' badge for entity_type '${type}'`, () => {
        const uniqueName = `TypeBadgeTest_${type}`;
        vi.mocked(useEntities).mockReturnValue(
          makeHookReturn({
            entities: [createEntity({ entity_type: type, canonical_name: uniqueName })],
            total: 1,
            loadedCount: 1,
          })
        );
        renderPage();
        // Query within the card to avoid collision with tab buttons that share the same label
        const card = screen.getByRole("link", { name: new RegExp(uniqueName, "i") });
        expect(within(card).getByText(expectedLabel)).toBeInTheDocument();
      });
    });

    it("renders the raw type string as badge label for unknown types", () => {
      vi.mocked(useEntities).mockReturnValue(
        makeHookReturn({
          entities: [createEntity({ entity_type: "species", canonical_name: "SpeciesEntity" })],
          total: 1,
          loadedCount: 1,
        })
      );
      renderPage();
      const card = screen.getByRole("link", { name: /SpeciesEntity/i });
      expect(within(card).getByText("species")).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Empty state
  // -------------------------------------------------------------------------

  describe("Empty state", () => {
    it("shows 'No entities yet' heading when no entities and no active filters", () => {
      // Default mock returns empty entities
      renderPage();
      expect(screen.getByText("No entities yet")).toBeInTheDocument();
    });

    it("shows the CLI hint command when no active filters", () => {
      renderPage();
      expect(
        screen.getByText(/chronovista entities scan/i)
      ).toBeInTheDocument();
    });

    it("shows 'No entities match your filters' when type filter is active", () => {
      renderPage("?type=person");
      expect(
        screen.getByText("No entities match your filters")
      ).toBeInTheDocument();
    });

    it("shows 'No entities match your filters' when has_mentions is active", () => {
      renderPage("?has_mentions=true");
      expect(
        screen.getByText("No entities match your filters")
      ).toBeInTheDocument();
    });

    it("shows 'No entities match your filters' when search is active", () => {
      renderPage("?search=test");
      expect(
        screen.getByText("No entities match your filters")
      ).toBeInTheDocument();
    });

    it("hides CLI hint when active filters are present", () => {
      renderPage("?type=person");
      expect(
        screen.queryByText(/chronovista entities scan/i)
      ).not.toBeInTheDocument();
    });

    it("shows filter-adjustment guidance message when filters are active", () => {
      renderPage("?search=something");
      expect(
        screen.getByText(/try adjusting your filters or search term/i)
      ).toBeInTheDocument();
    });

    it("empty state container has role='status'", () => {
      renderPage();
      expect(
        screen.getByRole("status", { name: /no entities found/i })
      ).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Error state — full (no entities loaded)
  // -------------------------------------------------------------------------

  describe("Full error state", () => {
    beforeEach(() => {
      vi.mocked(useEntities).mockReturnValue(
        makeHookReturn({
          isError: true,
          entities: [],
          error: { message: "Network error occurred" } as never,
        })
      );
    });

    it("renders the error alert container", () => {
      renderPage();
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });

    it("shows 'Could not load entities' label", () => {
      renderPage();
      expect(
        screen.getByText(/could not load entities/i)
      ).toBeInTheDocument();
    });

    it("renders the error message from the error object", () => {
      renderPage();
      expect(
        screen.getByText("Network error occurred")
      ).toBeInTheDocument();
    });

    it("renders a Retry button", () => {
      renderPage();
      expect(
        screen.getByRole("button", { name: /retry/i })
      ).toBeInTheDocument();
    });

    it("clicking Retry calls the retry function", () => {
      const retrySpy = vi.fn();
      vi.mocked(useEntities).mockReturnValue(
        makeHookReturn({
          isError: true,
          entities: [],
          error: { message: "Failure" } as never,
          retry: retrySpy,
        })
      );
      renderPage();
      fireEvent.click(screen.getByRole("button", { name: /retry/i }));
      expect(retrySpy).toHaveBeenCalledOnce();
    });

    it("renders a fallback message when error has no message property", () => {
      vi.mocked(useEntities).mockReturnValue(
        makeHookReturn({
          isError: true,
          entities: [],
          error: null,
        })
      );
      renderPage();
      expect(
        screen.getByText(/an error occurred while loading entities/i)
      ).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Inline error state (entities loaded, next page fails)
  // -------------------------------------------------------------------------

  describe("Inline error state (partial load)", () => {
    it("renders inline error alert when isError and entities are present", () => {
      vi.mocked(useEntities).mockReturnValue(
        makeHookReturn({
          isError: true,
          entities: [createEntity()],
          total: 2,
          loadedCount: 1,
          error: { message: "Next page failed" } as never,
        })
      );
      renderPage();
      // The full error state uses role="alert" and shows the entities list too
      expect(screen.getByRole("alert")).toBeInTheDocument();
      expect(screen.getByText("Next page failed")).toBeInTheDocument();
    });

    it("still renders entity cards alongside the inline error", () => {
      vi.mocked(useEntities).mockReturnValue(
        makeHookReturn({
          isError: true,
          entities: [createEntity({ canonical_name: "Carl Sagan" })],
          total: 2,
          loadedCount: 1,
          error: { message: "Page 2 failed" } as never,
        })
      );
      renderPage();
      expect(screen.getByText("Carl Sagan")).toBeInTheDocument();
    });

    it("renders an inline Retry button in the partial error state", () => {
      vi.mocked(useEntities).mockReturnValue(
        makeHookReturn({
          isError: true,
          entities: [createEntity()],
          total: 2,
          loadedCount: 1,
          error: { message: "Partial fail" } as never,
        })
      );
      renderPage();
      expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
    });

    it("inline Retry calls the retry function", () => {
      const retrySpy = vi.fn();
      vi.mocked(useEntities).mockReturnValue(
        makeHookReturn({
          isError: true,
          entities: [createEntity()],
          total: 2,
          loadedCount: 1,
          error: { message: "Page fail" } as never,
          retry: retrySpy,
        })
      );
      renderPage();
      fireEvent.click(screen.getByRole("button", { name: /retry/i }));
      expect(retrySpy).toHaveBeenCalledOnce();
    });
  });

  // -------------------------------------------------------------------------
  // Pagination
  // -------------------------------------------------------------------------

  describe("Pagination", () => {
    it("renders 'Showing X of Y entities' when hasNextPage is true", () => {
      vi.mocked(useEntities).mockReturnValue(
        makeHookReturn({
          entities: [createEntity()],
          total: 50,
          loadedCount: 1,
          hasNextPage: true,
        })
      );
      renderPage();
      expect(screen.getByText("Showing 1 of 50 entities")).toBeInTheDocument();
    });

    it("does not render pagination status when hasNextPage is false", () => {
      vi.mocked(useEntities).mockReturnValue(
        makeHookReturn({
          entities: [createEntity()],
          total: 1,
          loadedCount: 1,
          hasNextPage: false,
        })
      );
      renderPage();
      expect(
        screen.queryByText(/showing \d+ of \d+/i)
      ).not.toBeInTheDocument();
    });

    it("renders 'All N entities loaded' when hasNextPage is false and total > 0", () => {
      vi.mocked(useEntities).mockReturnValue(
        makeHookReturn({
          entities: [createEntity(), createEntity({ entity_id: "e2" })],
          total: 2,
          loadedCount: 2,
          hasNextPage: false,
        })
      );
      renderPage();
      expect(screen.getByText("All 2 entities loaded")).toBeInTheDocument();
    });

    it("uses singular 'entity' in all-loaded message when total is 1", () => {
      vi.mocked(useEntities).mockReturnValue(
        makeHookReturn({
          entities: [createEntity()],
          total: 1,
          loadedCount: 1,
          hasNextPage: false,
        })
      );
      renderPage();
      expect(screen.getByText("All 1 entity loaded")).toBeInTheDocument();
    });

    it("shows 'Loading more entities...' when isFetchingNextPage is true", () => {
      vi.mocked(useEntities).mockReturnValue(
        makeHookReturn({
          entities: [createEntity()],
          total: 10,
          loadedCount: 1,
          hasNextPage: true,
          isFetchingNextPage: true,
        })
      );
      renderPage();
      expect(
        screen.getByText(/loading more entities/i)
      ).toBeInTheDocument();
    });

    it("does not show 'Loading more' when isFetchingNextPage is false", () => {
      vi.mocked(useEntities).mockReturnValue(
        makeHookReturn({
          entities: [createEntity()],
          total: 1,
          loadedCount: 1,
          hasNextPage: false,
          isFetchingNextPage: false,
        })
      );
      renderPage();
      expect(
        screen.queryByText(/loading more entities/i)
      ).not.toBeInTheDocument();
    });

    it("shows count text next to the heading when total is known", () => {
      vi.mocked(useEntities).mockReturnValue(
        makeHookReturn({
          entities: [createEntity()],
          total: 24,
          loadedCount: 1,
        })
      );
      renderPage();
      // The count badge appears alongside the h1
      expect(screen.getByText("24 entities")).toBeInTheDocument();
    });

    it("uses singular 'entity' in count badge when total is 1", () => {
      vi.mocked(useEntities).mockReturnValue(
        makeHookReturn({
          entities: [createEntity()],
          total: 1,
          loadedCount: 1,
        })
      );
      renderPage();
      expect(screen.getByText("1 entity")).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Infinite scroll sentinel
  // -------------------------------------------------------------------------

  describe("Infinite scroll sentinel", () => {
    it("renders the IntersectionObserver sentinel div when there is no error", () => {
      vi.mocked(useEntities).mockReturnValue(
        makeHookReturn({
          entities: [createEntity()],
          total: 1,
          loadedCount: 1,
          isError: false,
          hasNextPage: false,
        })
      );
      const { container } = renderPage();
      // The sentinel is a div with aria-hidden="true" and h-4 class
      const sentinel = container.querySelector('[aria-hidden="true"].h-4');
      expect(sentinel).toBeInTheDocument();
    });

    it("does not render the sentinel when isError is true (no entities)", () => {
      vi.mocked(useEntities).mockReturnValue(
        makeHookReturn({
          isError: true,
          entities: [],
          error: { message: "fail" } as never,
        })
      );
      const { container } = renderPage();
      // The full error state is shown instead of the list — the sentinel <div> is absent.
      // Use a specific selector targeting a <div> (not SVG) with aria-hidden and class h-4.
      const sentinel = container.querySelector('div[aria-hidden="true"].h-4');
      expect(sentinel).not.toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Accessibility
  // -------------------------------------------------------------------------

  describe("Accessibility", () => {
    it("entity list grid has role='list' and accessible label", () => {
      vi.mocked(useEntities).mockReturnValue(
        makeHookReturn({
          entities: [createEntity()],
          total: 1,
          loadedCount: 1,
        })
      );
      renderPage();
      expect(
        screen.getByRole("list", { name: /entity list/i })
      ).toBeInTheDocument();
    });

    it("each entity card is wrapped in a listitem", () => {
      vi.mocked(useEntities).mockReturnValue(
        makeHookReturn({
          entities: [createEntity(), createEntity({ entity_id: "e2" })],
          total: 2,
          loadedCount: 2,
        })
      );
      renderPage();
      const listitems = screen.getAllByRole("listitem");
      expect(listitems).toHaveLength(2);
    });

    it("ARIA live region announces total entity count", () => {
      vi.mocked(useEntities).mockReturnValue(
        makeHookReturn({
          entities: [createEntity()],
          total: 5,
          loadedCount: 1,
        })
      );
      const { container } = renderPage();
      // The sr-only live region has role="status" aria-live="polite" and class "sr-only"
      const liveRegion = container.querySelector('[role="status"][aria-live="polite"].sr-only');
      expect(liveRegion).toBeInTheDocument();
      expect(liveRegion).toHaveTextContent(/showing 5 entities/i);
    });

    it("type filter tabs nav has an accessible label via role='tablist'", () => {
      vi.mocked(useEntities).mockReturnValue(
        makeHookReturn({ entities: [createEntity()], total: 1, loadedCount: 1 })
      );
      renderPage();
      // The <nav> carries explicit role="tablist" and aria-label="Entity type filter"
      expect(
        screen.getByRole("tablist", { name: "Entity type filter" })
      ).toBeInTheDocument();
    });

    it("search input has an associated label via htmlFor", () => {
      vi.mocked(useEntities).mockReturnValue(
        makeHookReturn({ entities: [createEntity()], total: 1, loadedCount: 1 })
      );
      renderPage();
      // getByLabelText confirms the label-input association
      const input = screen.getByLabelText(/search entities/i);
      expect(input).toBeInTheDocument();
    });

    it("sort dropdown has an associated label", () => {
      vi.mocked(useEntities).mockReturnValue(
        makeHookReturn({ entities: [createEntity()], total: 1, loadedCount: 1 })
      );
      renderPage();
      const select = screen.getByLabelText(/sort by/i);
      expect(select).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // useEntities hook call params
  // -------------------------------------------------------------------------

  describe("useEntities hook params", () => {
    it("calls useEntities with default sort 'mentions' and no type", () => {
      renderPage();
      expect(vi.mocked(useEntities)).toHaveBeenCalledWith(
        expect.objectContaining({ sort: "mentions" })
      );
      const callArg = vi.mocked(useEntities).mock.calls[0]?.[0];
      expect(callArg).not.toHaveProperty("type");
    });

    it("calls useEntities with type when type URL param is set", () => {
      renderPage("?type=person");
      expect(vi.mocked(useEntities)).toHaveBeenCalledWith(
        expect.objectContaining({ type: "person" })
      );
    });

    it("does not include type in params when type is 'all'", () => {
      renderPage("?type=all");
      const callArg = vi.mocked(useEntities).mock.calls[0]?.[0];
      expect(callArg).not.toHaveProperty("type");
    });

    it("calls useEntities with has_mentions:true when toggle is active", () => {
      renderPage("?has_mentions=true");
      expect(vi.mocked(useEntities)).toHaveBeenCalledWith(
        expect.objectContaining({ has_mentions: true })
      );
    });

    it("does not include has_mentions in params when toggle is off", () => {
      renderPage();
      const callArg = vi.mocked(useEntities).mock.calls[0]?.[0];
      expect(callArg).not.toHaveProperty("has_mentions");
    });

    it("calls useEntities with search when search URL param is set", () => {
      renderPage("?search=Curie");
      expect(vi.mocked(useEntities)).toHaveBeenCalledWith(
        expect.objectContaining({ search: "Curie" })
      );
    });

    it("does not include search in params when search is empty", () => {
      renderPage();
      const callArg = vi.mocked(useEntities).mock.calls[0]?.[0];
      expect(callArg).not.toHaveProperty("search");
    });

    it("calls useEntities with sort 'name' when sort URL param is 'name'", () => {
      renderPage("?sort=name");
      expect(vi.mocked(useEntities)).toHaveBeenCalledWith(
        expect.objectContaining({ sort: "name" })
      );
    });
  });
});
