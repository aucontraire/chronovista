/**
 * Tests for EntityMentionsPanel component.
 *
 * Coverage (Feature 038, T030):
 * - Renders nothing (hidden) when entities is empty and not loading
 * - Shows loading skeleton when isLoading is true
 * - Groups entities by type with section headings
 * - Shows count badges next to entity names
 * - Each entity chip links to /entities/{entity_id}
 * - Invokes onEntityClick callback when a chip is clicked
 * - Renders all known entity type groups in correct order
 */

import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import { EntityMentionsPanel } from "../EntityMentionsPanel";
import type { EntityMentionsPanelProps } from "../EntityMentionsPanel";
import type { VideoEntitySummary } from "../../api/entityMentions";

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
    ...overrides,
  };
}

function renderPanel(props: Partial<EntityMentionsPanelProps> = {}) {
  const defaultProps: EntityMentionsPanelProps = {
    entities: [],
    isLoading: false,
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
  describe("Empty state", () => {
    it("renders nothing when entities is empty and not loading", () => {
      const { container } = renderPanel({ entities: [], isLoading: false });
      expect(container.firstChild).toBeNull();
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
        createEntity({ entity_id: "e1", canonical_name: "Noam Chomsky", mention_count: 12 }),
      ];
      renderPanel({ entities });
      expect(screen.getByText("Noam Chomsky")).toBeInTheDocument();
    });

    it("shows count badge next to entity name", () => {
      const entities = [
        createEntity({ entity_id: "e1", canonical_name: "Noam Chomsky", mention_count: 12 }),
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
});
