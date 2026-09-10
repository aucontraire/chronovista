/**
 * Tests for EntityMentionsPanel component.
 *
 * Coverage (Feature 038, T030; Feature 050, T025):
 * - Shows loading skeleton when isLoading is true
 * - Always renders the panel (T011 — empty state with message)
 * - Groups entities by type with section headings
 * - Shows count badges next to entity names
 * - Each entity chip links to /entities/{entity_id}
 * - Invokes onEntityClick callback when a chip is clicked
 * - Renders all known entity type groups in correct order
 * - Shows search/link UI (T025) — full autocomplete behaviour (TC-S01..S10)
 *
 * Merged from two divergent copies (#309 Phase 3 consolidation): this file
 * (baseline chip/group/rescan behaviour) absorbed
 * `src/tests/components/EntityMentionsPanel.test.tsx` (the T025 search
 * autocomplete TDD suite, plus a "baseline behaviour" suite that mostly
 * duplicated tests already here).
 *
 * Dropped as duplicates of tests already in this file (documented, not
 * silently lost — same intent, same assertion, different test titles):
 * - Loading skeleton: "renders a skeleton section..." / "renders animated
 *   skeleton chips..." → covered by "shows an accessible loading label" /
 *   "shows skeleton elements when isLoading is true" below.
 * - Empty state: "renders the 'Entity Mentions' heading..." / "shows the
 *   empty-state message when no entities exist" → covered by the two tests
 *   under "Empty state" below.
 * - Chip rendering: "renders a chip with the canonical entity name" /
 *   "renders the mention count badge..." / "links each chip to the entity
 *   detail page" → covered by "shows entity names within chips" / "shows
 *   count badge next to entity name" / "Entity links (T033)" below.
 * - Entity type grouping: individual "People"/"Organizations"/"Places"
 *   heading tests → covered by "renders a section heading for each entity
 *   type group" below, which already asserts all three.
 * - onEntityClick: "invokes onEntityClick with (0, timestamp)..." →
 *   covered by "calls onEntityClick with timestamp when chip is clicked"
 *   below.
 * - Search UI: "renders a search input (role='searchbox') within the
 *   panel" → covered by "renders a search input within the panel" below.
 *
 * The source suite mocked `react-router-dom` with a stub `<Link>` instead
 * of wrapping in `<MemoryRouter>`; this merge keeps this file's existing
 * `<MemoryRouter>` approach throughout (both render the same resulting
 * anchor markup, so no assertion needed to change).
 */

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { MemoryRouter } from "react-router-dom";

// ---------------------------------------------------------------------------
// Mock hooks used inside EntityMentionsPanel — must be declared before imports
// ---------------------------------------------------------------------------

vi.mock("../../hooks/useEntitySearch", () => ({
  useEntitySearch: vi.fn(),
}));

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

import { EntityMentionsPanel } from "../EntityMentionsPanel";
import type { EntityMentionsPanelProps } from "../EntityMentionsPanel";
import type { VideoEntitySummary } from "../../api/entityMentions";
import { useEntitySearch } from "../../hooks/useEntitySearch";
import { useCreateManualAssociation, useDeleteManualAssociation, useScanVideoEntities } from "../../hooks/useEntityMentions";
import type { Mock } from "vitest";

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------

function createEntity(overrides: Partial<VideoEntitySummary> = {}): VideoEntitySummary {
  return {
    entity_id: "entity-uuid-001",
    canonical_name: "Test Entity",
    entity_type: "person",
    description: null,
    mention_count: 3,
    first_mention_time: 42.5,
    sources: ["transcript"],
    has_manual: false,
    ...overrides,
  };
}

const VIDEO_ID = "test-video-001";

// ---------------------------------------------------------------------------
// Search-autocomplete fixtures (T025) — used only by the "Entity search
// autocomplete" describe block below.
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

/** An entity with a manual link — should be disabled (duplicate prevention). */
const MANUALLY_LINKED_RESULT: EntitySearchResult = {
  entity_id: "ent-search-002",
  canonical_name: "Ada Lovelace",
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

function renderPanel(props: Partial<EntityMentionsPanelProps> = {}) {
  const defaultProps: EntityMentionsPanelProps = {
    entities: [],
    isLoading: false,
    videoId: VIDEO_ID,
    ...props,
  };
  return render(
    <MemoryRouter>
      <EntityMentionsPanel {...defaultProps} />
    </MemoryRouter>
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("EntityMentionsPanel", () => {
  beforeEach(() => {
    (useEntitySearch as Mock).mockReturnValue({
      entities: [],
      isLoading: false,
      isFetched: false,
      isError: false,
      isBelowMinChars: true,
    });
    (useCreateManualAssociation as Mock).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      isError: false,
      error: null,
      isSuccess: false,
    });
    (useDeleteManualAssociation as Mock).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      isError: false,
      error: null,
      isSuccess: false,
    });
  });

  describe("Empty state", () => {
    it("renders the panel with the heading even when entities is empty", () => {
      renderPanel({ entities: [], isLoading: false });
      expect(screen.getByRole("heading", { name: /entity mentions/i })).toBeInTheDocument();
    });

    it("shows the empty-state message when entities is empty", () => {
      renderPanel({ entities: [], isLoading: false });
      expect(screen.getByText(/no entity mentions yet/i)).toBeInTheDocument();
    });

    it("does not show the empty-state message when entities are present", () => {
      renderPanel({ entities: [createEntity()] });
      expect(screen.queryByText(/no entity mentions yet/i)).not.toBeInTheDocument();
    });
  });

  describe("Loading state", () => {
    it("shows skeleton elements when isLoading is true", () => {
      renderPanel({ entities: [], isLoading: true });
      const skeletons = screen.getAllByTestId("entity-chip-skeleton");
      expect(skeletons.length).toBeGreaterThan(0);
    });

    it("shows an accessible loading label", () => {
      renderPanel({ entities: [], isLoading: true });
      const section = screen.getByRole("region", { name: /entity mentions loading/i });
      expect(section).toBeInTheDocument();
    });

    it("does not render entity chips while loading", () => {
      renderPanel({ entities: [createEntity()], isLoading: true });
      expect(screen.queryByRole("list")).not.toBeInTheDocument();
    });
  });

  describe("Rendering with entities", () => {
    it("renders the section heading when entities exist", () => {
      const entities = [createEntity()];
      renderPanel({ entities });
      expect(screen.getByText("Entity Mentions")).toBeInTheDocument();
    });

    it("renders a section heading for each entity type group", () => {
      const entities = [
        createEntity({ entity_id: "e1", entity_type: "person", canonical_name: "Alice" }),
        createEntity({ entity_id: "e2", entity_type: "organization", canonical_name: "ACME Corp" }),
        createEntity({ entity_id: "e3", entity_type: "place", canonical_name: "New York" }),
      ];
      renderPanel({ entities });
      expect(screen.getByText("People")).toBeInTheDocument();
      expect(screen.getByText("Organizations")).toBeInTheDocument();
      expect(screen.getByText("Places")).toBeInTheDocument();
    });

    it("shows entity names within chips", () => {
      const entities = [
        createEntity({ entity_id: "e1", canonical_name: "Ada Lovelace", mention_count: 12 }),
      ];
      renderPanel({ entities });
      expect(screen.getByText("Ada Lovelace")).toBeInTheDocument();
    });

    it("shows count badge next to entity name", () => {
      const entities = [
        createEntity({ entity_id: "e1", canonical_name: "Ada Lovelace", mention_count: 12 }),
      ];
      renderPanel({ entities });
      expect(screen.getByText("(12)")).toBeInTheDocument();
    });

    it("does not render a count badge when mention_count is 0", () => {
      const entities = [createEntity({ mention_count: 0 })];
      renderPanel({ entities });
      expect(screen.queryByText(/\(\d+\)/)).not.toBeInTheDocument();
    });

    it("renders a chip for each entity", () => {
      const entities = [
        createEntity({ entity_id: "e1", canonical_name: "Entity A" }),
        createEntity({ entity_id: "e2", canonical_name: "Entity B" }),
        createEntity({ entity_id: "e3", canonical_name: "Entity C" }),
      ];
      renderPanel({ entities });
      expect(screen.getByText("Entity A")).toBeInTheDocument();
      expect(screen.getByText("Entity B")).toBeInTheDocument();
      expect(screen.getByText("Entity C")).toBeInTheDocument();
    });
  });

  describe("Entity links (T033)", () => {
    it("each chip links to /entities/{entity_id}", () => {
      const entities = [
        createEntity({ entity_id: "uuid-abc123", canonical_name: "Test Person" }),
      ];
      renderPanel({ entities });
      const link = screen.getByRole("link", { name: /Test Person/i });
      expect(link).toHaveAttribute("href", "/entities/uuid-abc123");
    });
  });

  describe("Click handler", () => {
    it("calls onEntityClick with timestamp when chip is clicked", () => {
      const onEntityClick = vi.fn();
      const entities = [
        createEntity({
          entity_id: "e1",
          canonical_name: "Clickable Entity",
          first_mention_time: 99.5,
        }),
      ];
      renderPanel({ entities, onEntityClick });
      const link = screen.getByRole("link", { name: /Clickable Entity/i });
      fireEvent.click(link);
      expect(onEntityClick).toHaveBeenCalledWith(0, 99.5);
    });

    it("does not throw when onEntityClick is not provided", () => {
      const entities = [createEntity()];
      renderPanel({ entities });
      const link = screen.getByRole("link", { name: /Test Entity/i });
      expect(() => fireEvent.click(link)).not.toThrow();
    });

    it("does not invoke onEntityClick when first_mention_time is null", () => {
      const onEntityClick = vi.fn();
      const entities = [
        createEntity({
          entity_id: "e1",
          canonical_name: "No Timestamp Entity",
          first_mention_time: null,
          mention_count: 0,
        }),
      ];
      renderPanel({ entities, onEntityClick });
      const link = screen.getByRole("link", { name: /No Timestamp Entity/i });
      fireEvent.click(link);
      expect(onEntityClick).not.toHaveBeenCalled();
    });
  });

  describe("Entity type grouping order", () => {
    it("renders 'People' group before 'Organizations'", () => {
      const entities = [
        createEntity({ entity_id: "o1", entity_type: "organization", canonical_name: "ACME" }),
        createEntity({ entity_id: "p1", entity_type: "person", canonical_name: "Alice" }),
      ];
      renderPanel({ entities });
      const headings = screen.getAllByRole("heading", { level: 4 });
      const headingTexts = headings.map((h) => h.textContent ?? "");
      const peopleIdx = headingTexts.indexOf("People");
      const orgsIdx = headingTexts.indexOf("Organizations");
      expect(peopleIdx).toBeLessThan(orgsIdx);
    });
  });

  describe("Unknown entity type", () => {
    it("renders a generic label for unknown entity types", () => {
      const entities = [
        createEntity({
          entity_id: "x1",
          entity_type: "species",
          canonical_name: "Homo sapiens",
        }),
      ];
      renderPanel({ entities });
      // Falls back to the raw type string as the heading label
      expect(screen.getByText("species")).toBeInTheDocument();
    });
  });

  describe("Accessibility", () => {
    it("section has an accessible label via aria-labelledby", () => {
      const entities = [createEntity()];
      renderPanel({ entities });
      const section = screen.getByRole("region", {
        name: /entity mentions/i,
      });
      expect(section).toBeInTheDocument();
    });

    it("entity chips have descriptive aria-labels including mention count", () => {
      const entities = [
        createEntity({ entity_id: "e1", canonical_name: "John Doe", mention_count: 5 }),
      ];
      renderPanel({ entities });
      const chip = screen.getByRole("link", {
        name: /John Doe.*5 mention/i,
      });
      expect(chip).toBeInTheDocument();
    });
  });

  // ---------------------------------------------------------------------------
  // Manual link badge (T009 baseline)
  // ---------------------------------------------------------------------------

  describe("Manual link badge (T009 baseline)", () => {
    it("shows the [MANUAL] badge for entities with has_manual=true", () => {
      const entities = [
        createEntity({ has_manual: true, sources: ["transcript", "manual"] }),
      ];
      renderPanel({ entities });
      expect(screen.getByText("MANUAL")).toBeInTheDocument();
    });

    it("does not show the [MANUAL] badge when has_manual is false", () => {
      const entities = [createEntity({ has_manual: false })];
      renderPanel({ entities });
      expect(screen.queryByText("MANUAL")).not.toBeInTheDocument();
    });
  });

  // ---------------------------------------------------------------------------
  // Tag association badge (T015, Feature 066)
  // ---------------------------------------------------------------------------

  describe("Tag association badge (T015)", () => {
    it("renders a TAG badge and no mention tally or unlink button for a tag-only entity", () => {
      const entities = [
        createEntity({
          entity_id: "e1",
          canonical_name: "Tag Only Entity",
          sources: ["tag"],
          mention_count: 0,
          has_manual: false,
          first_mention_time: null,
        }),
      ];
      renderPanel({ entities });

      expect(screen.getByText("TAG")).toBeInTheDocument();
      expect(screen.queryByText(/^\(\d+\)$/)).not.toBeInTheDocument();
      expect(
        screen.queryByTestId("unlink-button-e1")
      ).not.toBeInTheDocument();
    });

    it("renders both the mention tally and the TAG badge for a transcript+tag entity", () => {
      const entities = [
        createEntity({
          entity_id: "e2",
          canonical_name: "Transcript And Tag Entity",
          sources: ["transcript", "tag"],
          mention_count: 5,
          has_manual: false,
        }),
      ];
      renderPanel({ entities });

      expect(screen.getByText("(5)")).toBeInTheDocument();
      expect(screen.getByText("TAG")).toBeInTheDocument();
    });

    it("does not render a TAG badge when the entity has no tag source", () => {
      const entities = [
        createEntity({ entity_id: "e3", canonical_name: "Transcript Only", sources: ["transcript"] }),
      ];
      renderPanel({ entities });

      expect(screen.queryByText("TAG")).not.toBeInTheDocument();
    });

    it("includes 'tagged' in the accessible label when the entity has a tag source", () => {
      const entities = [
        createEntity({
          entity_id: "e4",
          canonical_name: "Jane Doe",
          sources: ["tag"],
          mention_count: 0,
        }),
      ];
      renderPanel({ entities });

      const chip = screen.getByRole("link", { name: /Jane Doe.*tagged/i });
      expect(chip).toBeInTheDocument();
    });
  });

  describe("Search UI (T025)", () => {
    it("renders a search input within the panel", () => {
      renderPanel({ entities: [] });
      expect(screen.getByRole("searchbox")).toBeInTheDocument();
    });

    it("renders the search input even when entities exist", () => {
      renderPanel({ entities: [createEntity()] });
      expect(screen.getByRole("searchbox")).toBeInTheDocument();
    });
  });

  // ---------------------------------------------------------------------------
  // Rescan Entity Mentions button (T012, Feature 052)
  // ---------------------------------------------------------------------------

  describe("Rescan Entity Mentions button (T012)", () => {
    it("renders the scan button when hasTranscript is true", () => {
      renderPanel({ entities: [], hasTranscript: true });
      expect(
        screen.getByRole("button", { name: /rescan entity mentions/i })
      ).toBeInTheDocument();
    });

    it("does not render the scan button when hasTranscript is false", () => {
      renderPanel({ entities: [], hasTranscript: false });
      expect(
        screen.queryByRole("button", { name: /rescan entity mentions/i })
      ).not.toBeInTheDocument();
    });

    it("does not render the scan button when hasTranscript is omitted (default)", () => {
      renderPanel({ entities: [] });
      expect(
        screen.queryByRole("button", { name: /rescan entity mentions/i })
      ).not.toBeInTheDocument();
    });

    it("scan button is enabled in idle state", () => {
      renderPanel({ entities: [], hasTranscript: true });
      const button = screen.getByRole("button", { name: /rescan entity mentions/i });
      expect(button).not.toBeDisabled();
    });

    it("shows 'Rescanning...' and disables the button when isPending is true", () => {
      (useScanVideoEntities as Mock).mockReturnValue({
        mutate: vi.fn(),
        isPending: true,
        isError: false,
        error: null,
        data: null,
        reset: vi.fn(),
      });

      renderPanel({ entities: [], hasTranscript: true });

      const button = screen.getByRole("button", { name: /scanning/i });
      expect(button).toBeDisabled();
      expect(button.textContent).toMatch(/scanning/i);
    });

    it("button has aria-busy='true' when isPending is true", () => {
      (useScanVideoEntities as Mock).mockReturnValue({
        mutate: vi.fn(),
        isPending: true,
        isError: false,
        error: null,
        data: null,
        reset: vi.fn(),
      });

      renderPanel({ entities: [], hasTranscript: true });

      const button = screen.getByRole("button", { name: /scanning/i });
      expect(button).toHaveAttribute("aria-busy", "true");
    });

    it("calls useScanVideoEntities.mutate with the videoId when the button is clicked", () => {
      const mockMutate = vi.fn();
      (useScanVideoEntities as Mock).mockReturnValue({
        mutate: mockMutate,
        isPending: false,
        isError: false,
        error: null,
        data: null,
        reset: vi.fn(),
      });

      renderPanel({ entities: [], videoId: VIDEO_ID, hasTranscript: true });

      fireEvent.click(screen.getByRole("button", { name: /rescan entity mentions/i }));

      expect(mockMutate).toHaveBeenCalledOnce();
      expect(mockMutate).toHaveBeenCalledWith(
        expect.objectContaining({ videoId: VIDEO_ID }),
        expect.any(Object)
      );
    });

    it("always requests a rebuild, never an incremental scan", () => {
      // The behaviour, as distinct from the label. An incremental scan only
      // ADDS, so the action a user takes immediately after curating an entity
      // — adding an exclusion pattern, registering a longer competing entity —
      // cannot retract the mentions that motivated the curation. The scan then
      // reports success while the wrong rows survive, which is worse than an
      // error. Renaming the button passes every other test in this file.
      const mockMutate = vi.fn();
      (useScanVideoEntities as Mock).mockReturnValue({
        mutate: mockMutate,
        isPending: false,
        isError: false,
        error: null,
        data: null,
        reset: vi.fn(),
      });

      renderPanel({ entities: [], videoId: VIDEO_ID, hasTranscript: true });
      fireEvent.click(screen.getByRole("button", { name: /rescan entity mentions/i }));

      const [variables] = mockMutate.mock.calls[0] as [
        { options?: { full_rescan?: boolean; sources?: string[] } },
      ];
      expect(variables.options?.full_rescan).toBe(true);
      // All three sources, or a "rebuild" silently skips two of them.
      expect(variables.options?.sources).toEqual([
        "transcript",
        "title",
        "description",
      ]);
    });

    it("tells the user hand-curated mentions survive the rebuild", () => {
      // The delete is scoped to detection_method='rule_match', so manual and
      // correction-derived mentions are preserved — but nobody can infer that
      // from a button labelled "Rescan", and the cost of guessing wrong is
      // that they never press it.
      renderPanel({ entities: [], hasTranscript: true });

      expect(
        screen.getByText(/added or corrected by hand are kept/i)
      ).toBeInTheDocument();
    });

    it("shows success message 'Rebuilt M mentions across N entities' after scan finds results", () => {
      const mockMutate = vi.fn().mockImplementation((_vars, callbacks) => {
        callbacks?.onSuccess?.({
          data: {
            unique_entities: 4,
            mentions_found: 12,
            segments_scanned: 90,
            mentions_skipped: 0,
            unique_videos: 1,
            duration_seconds: 0.4,
            dry_run: false,
          },
        });
      });

      (useScanVideoEntities as Mock).mockReturnValue({
        mutate: mockMutate,
        isPending: false,
        isError: false,
        error: null,
        data: null,
        reset: vi.fn(),
      });

      renderPanel({ entities: [], hasTranscript: true });

      fireEvent.click(screen.getByRole("button", { name: /rescan entity mentions/i }));

      expect(screen.getByText(/rebuilt 12 mentions across 4 entities/i)).toBeInTheDocument();
    });

    it("shows 'No entity mentions found' when scan returns zero results", () => {
      const mockMutate = vi.fn().mockImplementation((_vars, callbacks) => {
        callbacks?.onSuccess?.({
          data: {
            unique_entities: 0,
            mentions_found: 0,
            segments_scanned: 60,
            mentions_skipped: 0,
            unique_videos: 1,
            duration_seconds: 0.2,
            dry_run: false,
          },
        });
      });

      (useScanVideoEntities as Mock).mockReturnValue({
        mutate: mockMutate,
        isPending: false,
        isError: false,
        error: null,
        data: null,
        reset: vi.fn(),
      });

      renderPanel({ entities: [], hasTranscript: true });

      fireEvent.click(screen.getByRole("button", { name: /rescan entity mentions/i }));

      expect(screen.getByText(/no entity mentions found/i)).toBeInTheDocument();
    });

    it("success message uses role='status' for polite accessibility announcement", () => {
      const mockMutate = vi.fn().mockImplementation((_vars, callbacks) => {
        callbacks?.onSuccess?.({
          data: {
            unique_entities: 2,
            mentions_found: 6,
            segments_scanned: 50,
            mentions_skipped: 0,
            unique_videos: 1,
            duration_seconds: 0.2,
            dry_run: false,
          },
        });
      });

      (useScanVideoEntities as Mock).mockReturnValue({
        mutate: mockMutate,
        isPending: false,
        isError: false,
        error: null,
        data: null,
        reset: vi.fn(),
      });

      renderPanel({ entities: [], hasTranscript: true });

      fireEvent.click(screen.getByRole("button", { name: /rescan entity mentions/i }));

      expect(screen.getByRole("status")).toBeInTheDocument();
    });

    it("shows error message with role='alert' when scan fails", () => {
      const mockMutate = vi.fn().mockImplementation((_vars, callbacks) => {
        callbacks?.onError?.({ status: 500, message: "Scan failed. Please try again." });
      });

      (useScanVideoEntities as Mock).mockReturnValue({
        mutate: mockMutate,
        isPending: false,
        isError: false,
        error: null,
        data: null,
        reset: vi.fn(),
      });

      renderPanel({ entities: [], hasTranscript: true });

      fireEvent.click(screen.getByRole("button", { name: /rescan entity mentions/i }));

      const alert = screen.getByRole("alert");
      expect(alert).toBeInTheDocument();
      expect(alert).toHaveTextContent(/scan failed/i);
    });

    it("singular entity/mention labels used when counts are exactly 1", () => {
      const mockMutate = vi.fn().mockImplementation((_vars, callbacks) => {
        callbacks?.onSuccess?.({
          data: {
            unique_entities: 1,
            mentions_found: 1,
            segments_scanned: 30,
            mentions_skipped: 0,
            unique_videos: 1,
            duration_seconds: 0.1,
            dry_run: false,
          },
        });
      });

      (useScanVideoEntities as Mock).mockReturnValue({
        mutate: mockMutate,
        isPending: false,
        isError: false,
        error: null,
        data: null,
        reset: vi.fn(),
      });

      renderPanel({ entities: [], hasTranscript: true });

      fireEvent.click(screen.getByRole("button", { name: /rescan entity mentions/i }));

      expect(screen.getByText(/rebuilt 1 mention across 1 entity/i)).toBeInTheDocument();
    });

    it("error message persists (does not auto-dismiss) after failed scan", () => {
      vi.useFakeTimers();
      const mockMutate = vi.fn().mockImplementation((_vars, callbacks) => {
        callbacks?.onError?.({ message: "Scan failed. Please try again." });
      });

      (useScanVideoEntities as Mock).mockReturnValue({
        mutate: mockMutate,
        isPending: false,
        isError: false,
        error: null,
        data: null,
        reset: vi.fn(),
      });

      renderPanel({ entities: [], hasTranscript: true });

      fireEvent.click(screen.getByRole("button", { name: /rescan entity mentions/i }));

      // Advance timers past the 3-second auto-dismiss window
      vi.advanceTimersByTime(5000);

      const alert = screen.getByRole("alert");
      expect(alert).toBeInTheDocument();

      vi.useRealTimers();
    });

    it("shows a distinct 'already running' message on a 409 launch conflict", () => {
      const mockMutate = vi.fn().mockImplementation((_vars, callbacks) => {
        callbacks?.onError?.({ status: 409, message: "A scan is already in progress for this video" });
      });

      (useScanVideoEntities as Mock).mockReturnValue({
        mutate: mockMutate,
        isPending: false,
        isError: false,
        error: null,
        data: null,
        reset: vi.fn(),
      });

      renderPanel({ entities: [], hasTranscript: true });

      fireEvent.click(screen.getByRole("button", { name: /rescan entity mentions/i }));

      expect(screen.getByRole("alert")).toHaveTextContent(/already running/i);
    });

    it("shows the job's real failure reason when the async scan job fails", () => {
      const mockMutate = vi.fn().mockImplementation((_vars, callbacks) => {
        callbacks?.onError?.({ message: "Transcript fetch timed out" });
      });

      (useScanVideoEntities as Mock).mockReturnValue({
        mutate: mockMutate,
        isPending: false,
        isError: false,
        error: null,
        data: null,
        reset: vi.fn(),
      });

      renderPanel({ entities: [], hasTranscript: true });

      fireEvent.click(screen.getByRole("button", { name: /rescan entity mentions/i }));

      expect(screen.getByRole("alert")).toHaveTextContent("Transcript fetch timed out");
    });

    it("shows a 'Scanning… (this can take a few minutes)' status message while the job is running", () => {
      (useScanVideoEntities as Mock).mockReturnValue({
        mutate: vi.fn(),
        isPending: true,
        isError: false,
        error: null,
        data: null,
        reset: vi.fn(),
      });

      renderPanel({ entities: [], hasTranscript: true });

      expect(
        screen.getByText(/scanning.*this can take a few minutes/i)
      ).toBeInTheDocument();
    });
  });

  // ---------------------------------------------------------------------------
  // Entity search autocomplete (T025 full coverage, Feature 050)
  //
  // The "Search UI (T025)" describe above covers the minimal contract (a
  // searchbox is always rendered). This block covers the full autocomplete
  // behaviour: loading state, result display, already-linked/deprecated
  // handling, selection → createManualAssociation, empty-results messaging,
  // the raw-input → useEntitySearch contract, the isBelowMinChars guard, and
  // results-list accessibility.
  // ---------------------------------------------------------------------------

  describe("Entity search autocomplete (T025 full coverage)", () => {
    afterEach(() => {
      vi.useRealTimers();
    });

    describe("search input field", () => {
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

    describe("loading indicator during search", () => {
      it("shows a loading indicator when useEntitySearch returns isLoading=true", () => {
        (useEntitySearch as Mock).mockReturnValue({
          ...makeIdleSearchState(),
          isLoading: true,
          isBelowMinChars: false,
          entities: [],
        });

        renderPanel();

        // Acceptable forms: a role="status" element, a data-testid, or
        // aria-busy="true" on the dropdown container.
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

    describe("search results display", () => {
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
        expect(screen.getAllByText(/ada lovelace/i).length).toBeGreaterThan(0);
        expect(screen.getByText("Bell Telephone")).toBeInTheDocument();
      });
    });

    describe("already-linked indicator", () => {
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
          mutate: mutateFn,
          isPending: false,
          isError: false,
          error: null,
          isSuccess: false,
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

    describe("deprecated entity handling", () => {
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

        // Acceptable: <button disabled>, aria-disabled="true", or no
        // interactive element rendered for the deprecated item.
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

    describe("entity selection triggers createManualAssociation", () => {
      it("calls mutate with { videoId, entityId } when an active result button is clicked", async () => {
        const mutateFn = vi.fn();
        (useCreateManualAssociation as Mock).mockReturnValue({
          mutate: mutateFn,
          isPending: false,
          isError: false,
          error: null,
          isSuccess: false,
        });
        (useEntitySearch as Mock).mockReturnValue({
          ...makeIdleSearchState(),
          isBelowMinChars: false,
          entities: [ACTIVE_RESULT],
        });

        renderPanel({ videoId: VIDEO_ID });

        const user = userEvent.setup();
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
          mutate: mutateFn,
          isPending: false,
          isError: false,
          error: null,
          isSuccess: false,
        });
        (useEntitySearch as Mock).mockReturnValue({
          ...makeIdleSearchState(),
          isBelowMinChars: false,
          entities: [MANUALLY_LINKED_RESULT],
        });

        renderPanel({ videoId: VIDEO_ID });

        // No "add" button must exist for the manually-linked result.
        expect(
          screen.queryByRole("button", { name: /ada lovelace/i })
        ).not.toBeInTheDocument();
        expect(mutateFn).not.toHaveBeenCalled();
      });
    });

    describe("empty search results message", () => {
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

    // -------------------------------------------------------------------------
    // Debounce lives inside useEntitySearch (via useDebounce at 300 ms). The
    // component must pass the raw, un-filtered input value to the hook on
    // every re-render triggered by input change events.
    // -------------------------------------------------------------------------

    describe("raw input is passed to useEntitySearch on change", () => {
      it("passes the typed value to useEntitySearch after an input change event", async () => {
        vi.useFakeTimers();

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

    // -------------------------------------------------------------------------
    // useEntitySearch sets isBelowMinChars=true when the debounced search is
    // fewer than 2 characters. The component must use this flag to suppress
    // the results dropdown and the empty-results message.
    // -------------------------------------------------------------------------

    describe("minimum query length guard (isBelowMinChars=true)", () => {
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

    describe("search results list accessibility", () => {
      it("renders the results container with role='listbox' or role='list'", () => {
        (useEntitySearch as Mock).mockReturnValue({
          ...makeIdleSearchState(),
          isBelowMinChars: false,
          entities: [ACTIVE_RESULT],
        });

        renderPanel();

        const container = screen.queryByRole("listbox") ?? screen.queryByRole("list");
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
});
