/**
 * Unit tests for EntityMentionsPanel — Feature 050, User Story 1 (T025).
 *
 * This file contains two test suites:
 *
 *   1. Existing behaviour (T011/T009 baseline) — tests for the panel shipped
 *      in earlier features: skeleton state, empty-state message, grouped
 *      entity chips, [MANUAL] badge, count badges, and chip navigation links.
 *
 *   2. Entity search autocomplete (T025) — tests for the search/link UI
 *      added in T025.  All hooks are mocked so assertions can be made against
 *      the rendered UI without real API calls.
 *
 * Hook mocking strategy
 * ---------------------
 * `useEntitySearch` (hooks/useEntitySearch) and `useCreateManualAssociation`
 * (hooks/useEntityMentions) are both mocked at the module level so the
 * component renders without TanStack Query providers.
 *
 * @module tests/components/EntityMentionsPanel
 */

import {
  describe,
  it,
  expect,
  vi,
  beforeEach,
  afterEach,
} from "vitest";
import {
  render,
  screen,
  fireEvent,
  waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";

// ---------------------------------------------------------------------------
// Module-level mocks — declared before component imports so Vitest hoisting
// places them at the top of the compiled output.
// ---------------------------------------------------------------------------

// Stub react-router-dom <Link> so tests don't need a <BrowserRouter> wrapper.
vi.mock("react-router-dom", () => ({
  Link: vi.fn(
    ({
      to,
      children,
      ...rest
    }: {
      to: string;
      children: React.ReactNode;
      [key: string]: unknown;
    }) => (
      <a href={to} {...rest}>
        {children}
      </a>
    )
  ),
}));

// Mock useEntitySearch — lives in hooks/useEntitySearch.ts (already exists).
vi.mock("../../hooks/useEntitySearch", () => ({
  useEntitySearch: vi.fn(),
}));

// Mock useCreateManualAssociation — will be created in T024 inside
// hooks/useEntityMentions.ts.  The other exports (useVideoEntities, etc.)
// are re-exported so any existing imports in the component continue to work.
vi.mock("../../hooks/useEntityMentions", () => ({
  useVideoEntities: vi.fn(),
  useEntityVideos: vi.fn(),
  useEntities: vi.fn(),
  useCreateManualAssociation: vi.fn(),
  useDeleteManualAssociation: vi.fn(),
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

// ---------------------------------------------------------------------------
// Imports after mocks
// ---------------------------------------------------------------------------

import { EntityMentionsPanel } from "../../components/EntityMentionsPanel";
import type { EntityMentionsPanelProps } from "../../components/EntityMentionsPanel";
import type { VideoEntitySummary } from "../../api/entityMentions";
import { useEntitySearch } from "../../hooks/useEntitySearch";
import { useCreateManualAssociation, useDeleteManualAssociation } from "../../hooks/useEntityMentions";
import type { Mock } from "vitest";

// ---------------------------------------------------------------------------
// Shared types
//
// EntitySearchResult describes what T025 will display per search result.
// The `is_linked` field indicates whether the entity is already associated
// with the current video.  The remaining fields mirror EntityListItem from
// entityMentions.ts.  This local type will be replaced by the exported one
// once T025 formalises it in the API module.
// ---------------------------------------------------------------------------

interface EntitySearchResult {
  entity_id: string;
  canonical_name: string;
  entity_type: string;
  description: string | null;
  status: string;
  matched_alias: string | null;
  is_linked: boolean | null;
  link_sources: string[] | null;
  mention_count: number;
  video_count: number;
}

// ---------------------------------------------------------------------------
// Test fixtures
// ---------------------------------------------------------------------------

const VIDEO_ID = "test-video-abc123";

/** Returns a fully-typed VideoEntitySummary for use in baseline chip tests. */
function makeEntity(overrides: Partial<VideoEntitySummary> = {}): VideoEntitySummary {
  return {
    entity_id: "ent-001",
    canonical_name: "Noam Chomsky",
    entity_type: "person",
    description: null,
    mention_count: 5,
    first_mention_time: 12.3,
    sources: ["transcript"],
    has_manual: false,
    ...overrides,
  };
}

/** An active entity that is not yet linked to the test video. */
const ACTIVE_RESULT: EntitySearchResult = {
  entity_id: "ent-search-001",
  canonical_name: "MIT Media Lab",
  entity_type: "organization",
  description: "Research laboratory at MIT",
  status: "active",
  matched_alias: null,
  is_linked: false,
  link_sources: null,
  mention_count: 3,
  video_count: 2,
};

/** An entity that is already linked (transcript mention exists on this video). */
/** An entity with a manual link — should be disabled (duplicate prevention). */
const MANUALLY_LINKED_RESULT: EntitySearchResult = {
  entity_id: "ent-search-002",
  canonical_name: "Noam Chomsky",
  entity_type: "person",
  description: null,
  status: "active",
  matched_alias: null,
  is_linked: true,
  link_sources: ["manual"],
  mention_count: 12,
  video_count: 7,
};

/** An entity with only transcript links — should still be selectable for manual linking. */
const TRANSCRIPT_LINKED_RESULT: EntitySearchResult = {
  entity_id: "ent-search-004",
  canonical_name: "Angela Davis",
  entity_type: "person",
  description: null,
  status: "active",
  matched_alias: null,
  is_linked: true,
  link_sources: ["transcript"],
  mention_count: 5,
  video_count: 3,
};

/** A deprecated entity that must not be selectable. */
const DEPRECATED_RESULT: EntitySearchResult = {
  entity_id: "ent-search-003",
  canonical_name: "Bell Telephone",
  entity_type: "organization",
  description: null,
  status: "deprecated",
  matched_alias: null,
  is_linked: false,
  link_sources: null,
  mention_count: 0,
  video_count: 0,
};

// ---------------------------------------------------------------------------
// Default idle hook states installed in beforeEach
// ---------------------------------------------------------------------------

/** useEntitySearch idle state — no query, empty results, not loading. */
function makeIdleSearchState() {
  return {
    entities: [] as EntitySearchResult[],
    isLoading: false,
    isFetched: false,
    isError: false,
    isBelowMinChars: true,
  };
}

/** useCreateManualAssociation idle state — no pending mutation. */
function makeIdleMutationState() {
  return {
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
    isSuccess: false,
  };
}

/** useDeleteManualAssociation idle state — no pending mutation. */
function makeIdleDeleteMutationState() {
  return {
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
    isSuccess: false,
  };
}

// ---------------------------------------------------------------------------
// Render helper
// ---------------------------------------------------------------------------

/**
 * Renders EntityMentionsPanel with sensible defaults.
 */
function renderPanel(
  props: Partial<EntityMentionsPanelProps> & { videoId?: string } = {}
) {
  const { videoId = VIDEO_ID, ...panelProps } = props;
  const fullProps: EntityMentionsPanelProps = {
    entities: [],
    isLoading: false,
    videoId,
    ...panelProps,
  };
  return render(<EntityMentionsPanel {...fullProps} />);
}

// ===========================================================================
// Suite 1: Existing baseline behaviour (shipped in T009/T011)
// ===========================================================================

describe("EntityMentionsPanel — baseline behaviour (T009/T011)", () => {
  beforeEach(() => {
    (useEntitySearch as Mock).mockReturnValue(makeIdleSearchState());
    (useCreateManualAssociation as Mock).mockReturnValue(makeIdleMutationState());
    (useDeleteManualAssociation as Mock).mockReturnValue(makeIdleDeleteMutationState());
  });

  afterEach(() => {
    vi.clearAllMocks();
    vi.useRealTimers();
  });

  // -------------------------------------------------------------------------
  // Loading skeleton
  // -------------------------------------------------------------------------

  describe("loading state", () => {
    it("renders a skeleton section while isLoading is true", () => {
      renderPanel({ isLoading: true });
      expect(
        screen.getByRole("region", { name: /entity mentions loading/i })
      ).toBeInTheDocument();
    });

    it("renders animated skeleton chips during loading", () => {
      renderPanel({ isLoading: true });
      expect(
        screen.getAllByTestId("entity-chip-skeleton").length
      ).toBeGreaterThan(0);
    });

    it("does not render entity chips while loading", () => {
      renderPanel({ entities: [makeEntity()], isLoading: true });
      expect(screen.queryByRole("list")).not.toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Empty state
  // -------------------------------------------------------------------------

  describe("empty state (no entity mentions)", () => {
    it("renders the 'Entity Mentions' heading when entities array is empty", () => {
      renderPanel({ entities: [] });
      expect(
        screen.getByRole("heading", { name: /entity mentions/i })
      ).toBeInTheDocument();
    });

    it("shows the empty-state message when no entities exist", () => {
      renderPanel({ entities: [] });
      expect(screen.getByText(/no entity mentions yet/i)).toBeInTheDocument();
    });

    it("does not show the empty-state message when entities are present", () => {
      renderPanel({ entities: [makeEntity()] });
      expect(
        screen.queryByText(/no entity mentions yet/i)
      ).not.toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Entity chip rendering
  // -------------------------------------------------------------------------

  describe("entity chip rendering", () => {
    it("renders a chip with the canonical entity name", () => {
      renderPanel({ entities: [makeEntity()] });
      expect(screen.getByText("Noam Chomsky")).toBeInTheDocument();
    });

    it("renders the mention count badge next to the chip name", () => {
      renderPanel({ entities: [makeEntity({ mention_count: 12 })] });
      expect(screen.getByText("(12)")).toBeInTheDocument();
    });

    it("does not render a count badge when mention_count is 0", () => {
      renderPanel({ entities: [makeEntity({ mention_count: 0 })] });
      expect(screen.queryByText(/\(\d+\)/)).not.toBeInTheDocument();
    });

    it("links each chip to the entity detail page (/entities/{entity_id})", () => {
      renderPanel({ entities: [makeEntity({ entity_id: "ent-xyz" })] });
      const link = screen.getByRole("link", { name: /noam chomsky/i });
      expect(link).toHaveAttribute("href", "/entities/ent-xyz");
    });

    it("shows the [MANUAL] badge for entities with has_manual=true", () => {
      renderPanel({
        entities: [
          makeEntity({ has_manual: true, sources: ["transcript", "manual"] }),
        ],
      });
      expect(screen.getByText("MANUAL")).toBeInTheDocument();
    });

    it("does not show the [MANUAL] badge when has_manual is false", () => {
      renderPanel({ entities: [makeEntity({ has_manual: false })] });
      expect(screen.queryByText("MANUAL")).not.toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Entity type grouping
  // -------------------------------------------------------------------------

  describe("entity type grouping", () => {
    it("renders a 'People' group heading for entities with type 'person'", () => {
      renderPanel({ entities: [makeEntity({ entity_type: "person" })] });
      expect(
        screen.getByRole("heading", { name: /people/i })
      ).toBeInTheDocument();
    });

    it("renders an 'Organizations' group heading for entities with type 'organization'", () => {
      renderPanel({
        entities: [
          makeEntity({
            entity_id: "ent-org",
            canonical_name: "MIT",
            entity_type: "organization",
          }),
        ],
      });
      expect(
        screen.getByRole("heading", { name: /organizations/i })
      ).toBeInTheDocument();
    });

    it("renders a 'Places' group heading for entities with type 'place'", () => {
      renderPanel({
        entities: [
          makeEntity({
            entity_id: "ent-pl",
            canonical_name: "Boston",
            entity_type: "place",
          }),
        ],
      });
      expect(
        screen.getByRole("heading", { name: /places/i })
      ).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // onEntityClick callback
  // -------------------------------------------------------------------------

  describe("onEntityClick callback", () => {
    it("invokes onEntityClick with (0, timestamp) when chip clicked and first_mention_time is set", () => {
      const onEntityClick = vi.fn();
      renderPanel({
        entities: [makeEntity({ first_mention_time: 42.5 })],
        onEntityClick,
      });
      fireEvent.click(screen.getByRole("link", { name: /noam chomsky/i }));
      expect(onEntityClick).toHaveBeenCalledWith(0, 42.5);
    });

    it("does not invoke onEntityClick when first_mention_time is null", () => {
      const onEntityClick = vi.fn();
      renderPanel({
        entities: [
          makeEntity({ first_mention_time: null, mention_count: 0 }),
        ],
        onEntityClick,
      });
      fireEvent.click(screen.getByRole("link", { name: /noam chomsky/i }));
      expect(onEntityClick).not.toHaveBeenCalled();
    });
  });
});

// ===========================================================================
// Suite 2: Entity search autocomplete — TDD for T025
//
// These tests describe behaviour that DOES NOT EXIST YET.  They will all
// fail until T025 adds the search UI to EntityMentionsPanel.  Do not
// remove or skip them — they are the acceptance criteria for T025.
//
// The hook that will be called is useEntitySearch(rawInputValue) from
// hooks/useEntitySearch.ts.  The hook internally debounces via useDebounce
// and sets isBelowMinChars=true when the debounced search is < 2 chars.
// The component renders results from useEntitySearch().entities and calls
// useCreateManualAssociation().mutate({ videoId, entityId }) on selection.
// ===========================================================================

describe("EntityMentionsPanel — entity search autocomplete (TDD for T025)", () => {
  beforeEach(() => {
    (useEntitySearch as Mock).mockReturnValue(makeIdleSearchState());
    (useCreateManualAssociation as Mock).mockReturnValue(
      makeIdleMutationState()
    );
    (useDeleteManualAssociation as Mock).mockReturnValue(
      makeIdleDeleteMutationState()
    );
  });

  afterEach(() => {
    vi.clearAllMocks();
    vi.useRealTimers();
  });

  // =========================================================================
  // TC-S01: Search field is rendered
  // =========================================================================

  describe("TC-S01: search input field", () => {
    it("renders a search input (role='searchbox') within the panel", () => {
      renderPanel();
      // T025 must render an <input type="search"> or an element with
      // role="searchbox" for entity lookup.
      expect(screen.getByRole("searchbox")).toBeInTheDocument();
    });

    it("the search input has an accessible name via aria-label, aria-labelledby, or placeholder", () => {
      renderPanel();
      const input = screen.getByRole("searchbox");
      const hasAccessibleName =
        Boolean(input.getAttribute("aria-label")) ||
        Boolean(input.getAttribute("aria-labelledby")) ||
        Boolean(input.getAttribute("placeholder"));
      expect(hasAccessibleName).toBe(true);
    });

    it("the search input starts empty", () => {
      renderPanel();
      const input = screen.getByRole("searchbox") as HTMLInputElement;
      expect(input.value).toBe("");
    });
  });

  // =========================================================================
  // TC-S02: Loading state while the search query is in flight
  // =========================================================================

  describe("TC-S02: loading indicator during search", () => {
    it("shows a loading indicator when useEntitySearch returns isLoading=true", () => {
      (useEntitySearch as Mock).mockReturnValue({
        ...makeIdleSearchState(),
        isLoading: true,
        isBelowMinChars: false,
        entities: [],
      });

      renderPanel();

      // T025 must render a loading indicator.  Acceptable forms:
      //   - role="status" element
      //   - data-testid="entity-search-loading" element
      //   - an element with aria-busy="true" on the dropdown container
      const indicator =
        screen.queryByRole("status") ??
        screen.queryByTestId("entity-search-loading") ??
        document.querySelector('[aria-busy="true"]');

      expect(indicator).toBeInTheDocument();
    });

    it("does not show a loading indicator when isLoading is false", () => {
      (useEntitySearch as Mock).mockReturnValue({
        ...makeIdleSearchState(),
        isLoading: false,
      });

      renderPanel();

      expect(
        screen.queryByTestId("entity-search-loading")
      ).not.toBeInTheDocument();
      expect(screen.queryByRole("status")).not.toBeInTheDocument();
    });
  });

  // =========================================================================
  // TC-S03: Search results display — name and entity type
  // =========================================================================

  describe("TC-S03: search results display", () => {
    it("displays the canonical name of each search result", () => {
      (useEntitySearch as Mock).mockReturnValue({
        ...makeIdleSearchState(),
        isBelowMinChars: false,
        entities: [ACTIVE_RESULT],
      });

      renderPanel();

      expect(screen.getByText("MIT Media Lab")).toBeInTheDocument();
    });

    it("displays the entity type label alongside each result name", () => {
      (useEntitySearch as Mock).mockReturnValue({
        ...makeIdleSearchState(),
        isBelowMinChars: false,
        entities: [ACTIVE_RESULT],
      });

      renderPanel();

      // "organization" or "Organizations" must appear somewhere in the result.
      expect(screen.getByText(/organization/i)).toBeInTheDocument();
    });

    it("renders one result item per entity returned by useEntitySearch", () => {
      (useEntitySearch as Mock).mockReturnValue({
        ...makeIdleSearchState(),
        isBelowMinChars: false,
        entities: [ACTIVE_RESULT, MANUALLY_LINKED_RESULT, DEPRECATED_RESULT],
      });

      renderPanel();

      expect(screen.getByText("MIT Media Lab")).toBeInTheDocument();
      // MANUALLY_LINKED_RESULT may already appear as an existing chip — getAllByText handles duplicates.
      expect(screen.getAllByText(/noam chomsky/i).length).toBeGreaterThan(0);
      expect(screen.getByText("Bell Telephone")).toBeInTheDocument();
    });
  });

  // =========================================================================
  // TC-S04: Already-linked indicator for is_linked=true entities
  // =========================================================================

  describe("TC-S04: already-linked indicator", () => {
    it("shows an 'Already linked' label for entities with a manual link", () => {
      (useEntitySearch as Mock).mockReturnValue({
        ...makeIdleSearchState(),
        isBelowMinChars: false,
        entities: [MANUALLY_LINKED_RESULT],
      });

      renderPanel();

      expect(screen.getByText(/already linked/i)).toBeInTheDocument();
    });

    it("does not show 'Already linked' for transcript-only linked entities", () => {
      (useEntitySearch as Mock).mockReturnValue({
        ...makeIdleSearchState(),
        isBelowMinChars: false,
        entities: [TRANSCRIPT_LINKED_RESULT],
      });

      renderPanel();

      expect(screen.queryByText(/already linked/i)).not.toBeInTheDocument();
    });

    it("does not show 'Already linked' for results where is_linked is false", () => {
      (useEntitySearch as Mock).mockReturnValue({
        ...makeIdleSearchState(),
        isBelowMinChars: false,
        entities: [ACTIVE_RESULT],
      });

      renderPanel();

      expect(screen.queryByText(/already linked/i)).not.toBeInTheDocument();
    });

    it("allows selecting transcript-linked entities for manual linking", () => {
      const mutateFn = vi.fn();
      (useCreateManualAssociation as Mock).mockReturnValue({
        ...makeIdleMutationState(),
        mutate: mutateFn,
      });
      (useEntitySearch as Mock).mockReturnValue({
        ...makeIdleSearchState(),
        isBelowMinChars: false,
        entities: [TRANSCRIPT_LINKED_RESULT],
      });

      renderPanel({ videoId: VIDEO_ID });

      // Transcript-linked entity should still have a selectable button
      expect(
        screen.getByRole("button", { name: /angela davis/i })
      ).toBeInTheDocument();
    });
  });

  // =========================================================================
  // TC-S05: Deprecated entity — labelled and not selectable
  // =========================================================================

  describe("TC-S05: deprecated entity handling", () => {
    it("displays a 'deprecated' label for entities with status='deprecated'", () => {
      (useEntitySearch as Mock).mockReturnValue({
        ...makeIdleSearchState(),
        isBelowMinChars: false,
        entities: [DEPRECATED_RESULT],
      });

      renderPanel();

      expect(screen.getByText(/deprecated/i)).toBeInTheDocument();
    });

    it("disables the deprecated result so it cannot be selected (button disabled or aria-disabled=true)", () => {
      (useEntitySearch as Mock).mockReturnValue({
        ...makeIdleSearchState(),
        isBelowMinChars: false,
        entities: [DEPRECATED_RESULT],
      });

      renderPanel();

      // T025 must not allow clicking deprecated results.
      // Acceptable: <button disabled>, aria-disabled="true", or no interactive
      // element rendered for the deprecated item.
      const deprecatedBtn = screen.queryByRole("button", {
        name: /bell telephone/i,
      });
      const deprecatedOption = screen.queryByRole("option", {
        name: /bell telephone/i,
      });
      const deprecatedItem = deprecatedBtn ?? deprecatedOption;

      if (deprecatedItem !== null) {
        const isButtonDisabled =
          deprecatedItem instanceof HTMLButtonElement && deprecatedItem.disabled;
        const hasAriaDisabled =
          deprecatedItem.getAttribute("aria-disabled") === "true";
        expect(isButtonDisabled || hasAriaDisabled).toBe(true);
      } else {
        // No interactive element — the item must still be visible (with label).
        expect(screen.getByText("Bell Telephone")).toBeInTheDocument();
        expect(screen.getByText(/deprecated/i)).toBeInTheDocument();
      }
    });
  });

  // =========================================================================
  // TC-S06: Selecting a result creates a manual association
  // =========================================================================

  describe("TC-S06: entity selection triggers createManualAssociation", () => {
    it("calls mutate with { videoId, entityId } when an active result button is clicked", async () => {
      const mutateFn = vi.fn();
      (useCreateManualAssociation as Mock).mockReturnValue({
        ...makeIdleMutationState(),
        mutate: mutateFn,
      });
      (useEntitySearch as Mock).mockReturnValue({
        ...makeIdleSearchState(),
        isBelowMinChars: false,
        entities: [ACTIVE_RESULT],
      });

      renderPanel({ videoId: VIDEO_ID });

      const user = userEvent.setup();
      // T025 must render an interactive button (or option) for each active,
      // non-linked result.
      const resultButton = screen.getByRole("button", {
        name: /mit media lab/i,
      });
      await user.click(resultButton);

      expect(mutateFn).toHaveBeenCalledWith({
        videoId: VIDEO_ID,
        entityId: ACTIVE_RESULT.entity_id,
      });
    });

    it("does not render a selectable button for manually-linked entities", () => {
      const mutateFn = vi.fn();
      (useCreateManualAssociation as Mock).mockReturnValue({
        ...makeIdleMutationState(),
        mutate: mutateFn,
      });
      (useEntitySearch as Mock).mockReturnValue({
        ...makeIdleSearchState(),
        isBelowMinChars: false,
        entities: [MANUALLY_LINKED_RESULT],
      });

      renderPanel({ videoId: VIDEO_ID });

      // No "add" button must exist for the manually-linked result.
      expect(
        screen.queryByRole("button", { name: /noam chomsky/i })
      ).not.toBeInTheDocument();
      expect(mutateFn).not.toHaveBeenCalled();
    });
  });

  // =========================================================================
  // TC-S07: Empty search results message
  // =========================================================================

  describe("TC-S07: empty search results message", () => {
    it("shows 'No matching entities' when isBelowMinChars is false and results are empty after fetch", () => {
      (useEntitySearch as Mock).mockReturnValue({
        ...makeIdleSearchState(),
        isBelowMinChars: false,
        isFetched: true,
        entities: [],
      });

      renderPanel();

      expect(screen.getByText(/no matching entities/i)).toBeInTheDocument();
    });

    it("does not show 'No matching entities' when isBelowMinChars is true (idle state)", () => {
      (useEntitySearch as Mock).mockReturnValue({
        ...makeIdleSearchState(),
        isBelowMinChars: true,
        isFetched: false,
        entities: [],
      });

      renderPanel();

      expect(
        screen.queryByText(/no matching entities/i)
      ).not.toBeInTheDocument();
    });

    it("does not show 'No matching entities' while the query is still loading", () => {
      (useEntitySearch as Mock).mockReturnValue({
        ...makeIdleSearchState(),
        isBelowMinChars: false,
        isLoading: true,
        isFetched: false,
        entities: [],
      });

      renderPanel();

      expect(
        screen.queryByText(/no matching entities/i)
      ).not.toBeInTheDocument();
    });
  });

  // =========================================================================
  // TC-S08: Debounce — component passes raw input value to useEntitySearch
  //
  // The debounce lives inside useEntitySearch (via useDebounce at 300 ms).
  // The component must pass the raw, un-filtered input value to the hook on
  // every re-render triggered by input change events.  The hook is responsible
  // for gating on isBelowMinChars and for debouncing internally.
  //
  // These tests verify the component's input → hook contract using fake timers
  // to control when React re-renders settle.
  // =========================================================================

  describe("TC-S08: raw input is passed to useEntitySearch on change", () => {
    it("passes the typed value to useEntitySearch after an input change event", async () => {
      vi.useFakeTimers();

      // Capture every search value the hook was called with.
      const searchCallArgs: string[] = [];
      (useEntitySearch as Mock).mockImplementation((search: string) => {
        searchCallArgs.push(search);
        return makeIdleSearchState();
      });

      renderPanel();

      const input = screen.getByRole("searchbox");

      await vi.waitFor(() => {
        fireEvent.change(input, { target: { value: "Noa" } });
      });

      // After the change, React re-renders and calls the hook with "Noa".
      expect(searchCallArgs).toContain("Noa");
    });

    it("passes an empty string to useEntitySearch when the input is cleared", async () => {
      vi.useFakeTimers();

      const searchCallArgs: string[] = [];
      (useEntitySearch as Mock).mockImplementation((search: string) => {
        searchCallArgs.push(search);
        return makeIdleSearchState();
      });

      renderPanel();

      const input = screen.getByRole("searchbox");
      fireEvent.change(input, { target: { value: "Noa" } });
      fireEvent.change(input, { target: { value: "" } });

      expect(searchCallArgs).toContain("");
    });
  });

  // =========================================================================
  // TC-S09: Minimum query length — isBelowMinChars guards the results pane
  //
  // useEntitySearch sets isBelowMinChars=true when the debounced search is
  // fewer than 2 characters.  The component must use this flag to suppress
  // the results dropdown and the empty-results message.
  // =========================================================================

  describe("TC-S09: minimum query length guard (isBelowMinChars=true)", () => {
    it("does not show a results dropdown when isBelowMinChars is true after a single-char input", () => {
      (useEntitySearch as Mock).mockReturnValue({
        ...makeIdleSearchState(),
        isBelowMinChars: true,
        entities: [],
      });

      renderPanel();

      const input = screen.getByRole("searchbox");
      fireEvent.change(input, { target: { value: "N" } });

      // No listbox or named results list should appear.
      expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
      expect(
        screen.queryByRole("list", { name: /search results/i })
      ).not.toBeInTheDocument();
    });

    it("does not show the empty-results message when isBelowMinChars is true", () => {
      (useEntitySearch as Mock).mockReturnValue({
        ...makeIdleSearchState(),
        isBelowMinChars: true,
        entities: [],
      });

      renderPanel();

      const input = screen.getByRole("searchbox");
      fireEvent.change(input, { target: { value: "N" } });

      expect(
        screen.queryByText(/no matching entities/i)
      ).not.toBeInTheDocument();
    });

    it("shows results when isBelowMinChars is false (2+ characters typed)", () => {
      (useEntitySearch as Mock).mockReturnValue({
        ...makeIdleSearchState(),
        isBelowMinChars: false,
        isFetched: true,
        entities: [ACTIVE_RESULT],
      });

      renderPanel();

      const input = screen.getByRole("searchbox");
      fireEvent.change(input, { target: { value: "MI" } });

      expect(screen.getByText("MIT Media Lab")).toBeInTheDocument();
    });
  });

  // =========================================================================
  // TC-S10: Accessibility — results list structure and keyboard navigation
  // =========================================================================

  describe("TC-S10: search results list accessibility", () => {
    it("renders the results container with role='listbox' or role='list'", () => {
      (useEntitySearch as Mock).mockReturnValue({
        ...makeIdleSearchState(),
        isBelowMinChars: false,
        entities: [ACTIVE_RESULT],
      });

      renderPanel();

      const container =
        screen.queryByRole("listbox") ??
        screen.queryByRole("list");
      expect(container).toBeInTheDocument();
    });

    it("each active result has an accessible button labelled with the entity name", () => {
      (useEntitySearch as Mock).mockReturnValue({
        ...makeIdleSearchState(),
        isBelowMinChars: false,
        entities: [ACTIVE_RESULT],
      });

      renderPanel();

      expect(
        screen.getByRole("button", { name: /mit media lab/i })
      ).toBeInTheDocument();
    });

    it("hides the results list when the search input is cleared", async () => {
      // Phase 1: results are showing.
      (useEntitySearch as Mock).mockReturnValue({
        ...makeIdleSearchState(),
        isBelowMinChars: false,
        isFetched: true,
        entities: [ACTIVE_RESULT],
      });

      renderPanel();
      expect(screen.getByText("MIT Media Lab")).toBeInTheDocument();

      // Phase 2: input cleared — hook now returns idle (isBelowMinChars=true).
      (useEntitySearch as Mock).mockReturnValue({
        ...makeIdleSearchState(),
        isBelowMinChars: true,
        entities: [],
      });

      const user = userEvent.setup();
      const input = screen.getByRole("searchbox");
      await user.clear(input);

      await waitFor(() => {
        expect(screen.queryByText("MIT Media Lab")).not.toBeInTheDocument();
      });
    });
  });
});
