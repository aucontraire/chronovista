/**
 * Tests for ChannelEntityPanel pin-to-filter toggles (Feature 070, US2).
 *
 * Coverage:
 * - Reading the URL with pins pre-populates pinned state (FR-006/SC-004)
 * - Clicking a pin toggle updates the URL's repeated entity_id param
 * - Clicking an already-pinned toggle removes it from the URL
 * - Pin controls are real aria-pressed toggle buttons
 * - A pin/unpin change is announced via an aria-live="polite" region
 */

import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter, useSearchParams } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import type { Mock } from "vitest";

vi.mock("../../../hooks/useChannelEntities", () => ({
  useChannelEntities: vi.fn(),
}));

import { ChannelEntityPanel } from "../ChannelEntityPanel";
import { useChannelEntities } from "../../../hooks/useChannelEntities";
import type { ChannelEntityRanking } from "../../../types/channel";

const CHANNEL_ID = "UC-test-channel-001";

function createEntity(overrides: Partial<ChannelEntityRanking> = {}): ChannelEntityRanking {
  return {
    entity_id: "entity-uuid-001",
    display_name: "Test Entity",
    entity_type: "person",
    channel_video_count: 5,
    corpus_video_count: 20,
    share: 0.25,
    is_ranked: true,
    ...overrides,
  };
}

/** Renders the URL's entity_id params as text so tests can assert on them. */
function SearchParamsProbe() {
  const [searchParams] = useSearchParams();
  return <div data-testid="entity-id-params">{searchParams.getAll("entity_id").join(",")}</div>;
}

function renderPanel(initialEntries: string[] = ["/"]) {
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <ChannelEntityPanel channelId={CHANNEL_ID} />
      <SearchParamsProbe />
    </MemoryRouter>
  );
}

describe("ChannelEntityPanel — pin to filter (US2)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  function mockTwoEntities() {
    const items = [
      createEntity({ entity_id: "e1", display_name: "First Entity" }),
      createEntity({ entity_id: "e2", display_name: "Second Entity" }),
    ];
    (useChannelEntities as Mock).mockReturnValue({
      data: { channel_id: CHANNEL_ID, total_entities: 2, items },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });
  }

  describe("URL restoration (FR-006/SC-004)", () => {
    it("marks a pinned entity's toggle as aria-pressed=true on initial render", () => {
      mockTwoEntities();
      renderPanel(["/?entity_id=e1"]);

      expect(screen.getByRole("button", { name: /unpin first entity/i })).toHaveAttribute(
        "aria-pressed",
        "true"
      );
      expect(
        screen.getByRole("button", { name: /pin second entity to filter/i })
      ).toHaveAttribute("aria-pressed", "false");
    });
  });

  describe("Toggling a pin", () => {
    it("adds the entity_id param to the URL when pinning", () => {
      mockTwoEntities();
      renderPanel(["/"]);

      fireEvent.click(screen.getByRole("button", { name: /pin first entity to filter/i }));

      expect(screen.getByTestId("entity-id-params")).toHaveTextContent("e1");
      expect(screen.getByRole("button", { name: /unpin first entity/i })).toHaveAttribute(
        "aria-pressed",
        "true"
      );
    });

    it("pinning a second entity narrows the URL to both ids (AND)", () => {
      mockTwoEntities();
      renderPanel(["/?entity_id=e1"]);

      fireEvent.click(screen.getByRole("button", { name: /pin second entity to filter/i }));

      expect(screen.getByTestId("entity-id-params")).toHaveTextContent("e1,e2");
    });

    it("removes the entity_id param from the URL when unpinning", () => {
      mockTwoEntities();
      renderPanel(["/?entity_id=e1&entity_id=e2"]);

      fireEvent.click(screen.getByRole("button", { name: /unpin first entity/i }));

      expect(screen.getByTestId("entity-id-params")).toHaveTextContent("e2");
    });
  });

  describe("Accessibility (FR-015)", () => {
    it("renders each pin control as an aria-pressed toggle button", () => {
      mockTwoEntities();
      renderPanel(["/"]);

      const button = screen.getByRole("button", { name: /pin first entity to filter/i });
      expect(button).toHaveAttribute("aria-pressed", "false");
      expect(button.tagName).toBe("BUTTON");
    });

    it("announces a pin via an aria-live polite region", () => {
      mockTwoEntities();
      renderPanel(["/"]);

      fireEvent.click(screen.getByRole("button", { name: /pin first entity to filter/i }));

      const liveRegion = screen.getByText(/pinned first entity to filter/i);
      expect(liveRegion.closest('[aria-live="polite"]')).not.toBeNull();
    });

    it("announces an unpin via an aria-live polite region", () => {
      mockTwoEntities();
      renderPanel(["/?entity_id=e1"]);

      fireEvent.click(screen.getByRole("button", { name: /unpin first entity/i }));

      const liveRegion = screen.getByText(/unpinned first entity/i);
      expect(liveRegion.closest('[aria-live="polite"]')).not.toBeNull();
    });
  });
});
