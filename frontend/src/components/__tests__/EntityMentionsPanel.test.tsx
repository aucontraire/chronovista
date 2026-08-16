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
 * - Shows search/link UI (T025)
 *
 * Note: Full search-UI behaviour is tested in the TDD suite at
 * src/tests/components/EntityMentionsPanel.test.tsx.  This file tests
 * the baseline chip/group behaviour and panel structure.
 */

import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
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
});
