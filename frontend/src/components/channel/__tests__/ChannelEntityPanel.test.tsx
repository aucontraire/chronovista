/**
 * Tests for ChannelEntityPanel component (Feature 070, US1).
 *
 * Coverage:
 * - Renders the ranked group in the given (server) order
 * - Share formatting per FR-011: whole-number rounding, "<1%" for any share below 1%
 * - "Also appears" group renders single-video (is_ranked: false) entities
 * - "Also appears" heading is absent when every entity is ranked
 * - Loading, error, and empty states each render distinctly
 */

import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import type { Mock } from "vitest";

// ---------------------------------------------------------------------------
// Mock the hook used inside ChannelEntityPanel — must be declared before imports
// ---------------------------------------------------------------------------

vi.mock("../../../hooks/useChannelEntities", () => ({
  useChannelEntities: vi.fn(),
}));

import { ChannelEntityPanel } from "../ChannelEntityPanel";
import { useChannelEntities } from "../../../hooks/useChannelEntities";
import type { ChannelEntitiesResponse, ChannelEntityRanking } from "../../../types/channel";

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------

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

function mockHookReturn(overrides: {
  data?: ChannelEntitiesResponse | undefined;
  isLoading?: boolean;
  isError?: boolean;
  error?: { message: string } | null;
  refetch?: () => void;
}) {
  (useChannelEntities as Mock).mockReturnValue({
    data: undefined,
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
    ...overrides,
  });
}

function renderPanel(initialEntries: string[] = ["/"]) {
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <ChannelEntityPanel channelId={CHANNEL_ID} />
    </MemoryRouter>
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("ChannelEntityPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("Heading", () => {
    it("renders the Entities heading", () => {
      mockHookReturn({
        data: { channel_id: CHANNEL_ID, total_entities: 0, items: [] },
      });
      renderPanel();
      expect(screen.getByRole("heading", { name: /entities/i })).toBeInTheDocument();
    });
  });

  describe("Loading state", () => {
    it("shows a loading status region", () => {
      mockHookReturn({ isLoading: true });
      renderPanel();
      const status = screen.getByRole("status");
      expect(status).toHaveAttribute("aria-busy", "true");
      expect(status).toHaveTextContent(/loading entities/i);
    });

    it("does not render ranked list content while loading", () => {
      mockHookReturn({ isLoading: true });
      renderPanel();
      expect(screen.queryByRole("list", { name: /ranked by distinctiveness/i })).not.toBeInTheDocument();
    });
  });

  describe("Error state", () => {
    it("shows an alert with the error message", () => {
      mockHookReturn({
        isError: true,
        error: { message: "Could not reach the server" },
      });
      renderPanel();
      const alert = screen.getByRole("alert");
      expect(alert).toHaveTextContent(/could not reach the server/i);
    });

    it("retries via the hook's refetch when the Retry button is clicked", () => {
      const refetch = vi.fn();
      mockHookReturn({
        isError: true,
        error: { message: "Server error" },
        refetch,
      });
      renderPanel();
      fireEvent.click(screen.getByRole("button", { name: /retry/i }));
      expect(refetch).toHaveBeenCalledOnce();
    });
  });

  describe("Empty state", () => {
    it("shows an explicit empty message when the channel has zero entities", () => {
      mockHookReturn({
        data: { channel_id: CHANNEL_ID, total_entities: 0, items: [] },
      });
      renderPanel();
      expect(screen.getByText(/no entities found/i)).toBeInTheDocument();
    });
  });

  describe("Ranked group ordering", () => {
    it("renders ranked entities in the order given by the API", () => {
      const items = [
        createEntity({ entity_id: "e1", display_name: "First Entity", is_ranked: true }),
        createEntity({ entity_id: "e2", display_name: "Second Entity", is_ranked: true }),
        createEntity({ entity_id: "e3", display_name: "Third Entity", is_ranked: true }),
      ];
      mockHookReturn({
        data: { channel_id: CHANNEL_ID, total_entities: 3, items },
      });
      renderPanel();

      const list = screen.getByRole("list", { name: /ranked by distinctiveness/i });
      const rows = list.querySelectorAll('[role="listitem"]');
      const names = Array.from(rows).map((row) => row.textContent ?? "");
      expect(names[0]).toContain("First Entity");
      expect(names[1]).toContain("Second Entity");
      expect(names[2]).toContain("Third Entity");
    });
  });

  describe("Share formatting (FR-011)", () => {
    it("rounds a normal share to the nearest whole percent", () => {
      mockHookReturn({
        data: {
          channel_id: CHANNEL_ID,
          total_entities: 1,
          items: [createEntity({ display_name: "Normal Share Entity", share: 0.2126 })],
        },
      });
      renderPanel();
      expect(screen.getByText("21%")).toBeInTheDocument();
    });

    it("renders '<1%' for a tiny share (rounds to 0)", () => {
      mockHookReturn({
        data: {
          channel_id: CHANNEL_ID,
          total_entities: 1,
          items: [createEntity({ display_name: "Tiny Share Entity", share: 0.004 })],
        },
      });
      renderPanel();
      expect(screen.getByText("<1%")).toBeInTheDocument();
    });

    it("renders '<1%' for a share in the 0.5–0.99% band (FR-011: below 1%, not rounds-to-0)", () => {
      // 0.7% is below 1% so FR-011 requires "<1%"; it must NOT round up to "1%".
      mockHookReturn({
        data: {
          channel_id: CHANNEL_ID,
          total_entities: 1,
          items: [createEntity({ display_name: "Sub One Percent Entity", share: 0.007 })],
        },
      });
      renderPanel();
      expect(screen.getByText("<1%")).toBeInTheDocument();
      expect(screen.queryByText("1%")).not.toBeInTheDocument();
    });

    it("renders '1%' at exactly 1%", () => {
      mockHookReturn({
        data: {
          channel_id: CHANNEL_ID,
          total_entities: 1,
          items: [createEntity({ display_name: "One Percent Entity", share: 0.01 })],
        },
      });
      renderPanel();
      expect(screen.getByText("1%")).toBeInTheDocument();
    });

    it("renders '—' rather than 'NaN%' for a non-finite share", () => {
      mockHookReturn({
        data: {
          channel_id: CHANNEL_ID,
          total_entities: 1,
          items: [
            createEntity({
              display_name: "Bad Share Entity",
              share: null as unknown as number,
            }),
          ],
        },
      });
      renderPanel();
      expect(screen.getByText("—")).toBeInTheDocument();
      expect(screen.queryByText(/NaN/)).not.toBeInTheDocument();
    });

    it("rounds 0.505 up to 51%", () => {
      mockHookReturn({
        data: {
          channel_id: CHANNEL_ID,
          total_entities: 1,
          items: [createEntity({ display_name: "Rounding Entity", share: 0.505 })],
        },
      });
      renderPanel();
      expect(screen.getByText("51%")).toBeInTheDocument();
    });
  });

  describe("Also appears group", () => {
    it("renders a single-video (is_ranked: false) entity under 'Also appears'", () => {
      const items = [
        createEntity({ entity_id: "e1", display_name: "Ranked Entity", is_ranked: true }),
        createEntity({
          entity_id: "e2",
          display_name: "Single Video Entity",
          is_ranked: false,
          channel_video_count: 1,
          share: 0.05,
        }),
      ];
      mockHookReturn({
        data: { channel_id: CHANNEL_ID, total_entities: 2, items },
      });
      renderPanel();

      expect(screen.getByText(/also appears/i)).toBeInTheDocument();
      const alsoAppearsList = screen.getByRole("list", { name: /exactly one video/i });
      expect(alsoAppearsList).toHaveTextContent("Single Video Entity");
    });

    it("does not render the 'Also appears' heading when every entity is ranked", () => {
      const items = [
        createEntity({ entity_id: "e1", display_name: "Ranked One", is_ranked: true }),
        createEntity({ entity_id: "e2", display_name: "Ranked Two", is_ranked: true }),
      ];
      mockHookReturn({
        data: { channel_id: CHANNEL_ID, total_entities: 2, items },
      });
      renderPanel();

      expect(screen.queryByText(/also appears/i)).not.toBeInTheDocument();
    });

    it("omits the empty ranked list when every entity is 'also appears'", () => {
      const items = [
        createEntity({
          entity_id: "e1",
          display_name: "Solo One",
          is_ranked: false,
          channel_video_count: 1,
        }),
        createEntity({
          entity_id: "e2",
          display_name: "Solo Two",
          is_ranked: false,
          channel_video_count: 1,
        }),
      ];
      mockHookReturn({
        data: { channel_id: CHANNEL_ID, total_entities: 2, items },
      });
      renderPanel();

      // The ranked list is absent entirely (no empty labelled list in the a11y tree).
      expect(
        screen.queryByRole("list", { name: /ranked by distinctiveness/i })
      ).not.toBeInTheDocument();
      // Everything is under "Also appears".
      const alsoAppearsList = screen.getByRole("list", { name: /exactly one video/i });
      expect(alsoAppearsList).toHaveTextContent("Solo One");
      expect(alsoAppearsList).toHaveTextContent("Solo Two");
    });
  });

  describe("Top-N expansion (US3 / FR-009)", () => {
    // 12 ranked + 3 also-appears = 15 total (> TOP_N of 10).
    const manyItems = [
      ...Array.from({ length: 12 }, (_, i) =>
        createEntity({
          entity_id: `r${i}`,
          display_name: `Ranked ${i}`,
          is_ranked: true,
        })
      ),
      ...Array.from({ length: 3 }, (_, i) =>
        createEntity({
          entity_id: `a${i}`,
          display_name: `Also ${i}`,
          is_ranked: false,
          channel_video_count: 1,
        })
      ),
    ];

    it("renders only the top 10 initially with a 'Show all N' control", () => {
      mockHookReturn({
        data: { channel_id: CHANNEL_ID, total_entities: 15, items: manyItems },
      });
      renderPanel();

      // Only the top 10 ranked rows render; "also appears" is hidden while collapsed.
      expect(screen.getAllByRole("listitem")).toHaveLength(10);
      expect(screen.queryByText(/also appears/i)).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: /show all 15/i })).toBeInTheDocument();
    });

    it("reveals the remainder including 'also appears' when expanded", () => {
      mockHookReturn({
        data: { channel_id: CHANNEL_ID, total_entities: 15, items: manyItems },
      });
      renderPanel();

      fireEvent.click(screen.getByRole("button", { name: /show all 15/i }));

      // All 15 rows now render, plus the "also appears" group.
      expect(screen.getAllByRole("listitem")).toHaveLength(15);
      expect(screen.getByText(/also appears/i)).toBeInTheDocument();
      // The control toggles to a collapse affordance with aria-expanded.
      const toggle = screen.getByRole("button", { name: /show less/i });
      expect(toggle).toHaveAttribute("aria-expanded", "true");
    });

    it("shows no expand control when there are 10 or fewer entities", () => {
      const items = Array.from({ length: 10 }, (_, i) =>
        createEntity({ entity_id: `r${i}`, display_name: `Ranked ${i}`, is_ranked: true })
      );
      mockHookReturn({
        data: { channel_id: CHANNEL_ID, total_entities: 10, items },
      });
      renderPanel();

      expect(screen.queryByRole("button", { name: /show all/i })).not.toBeInTheDocument();
      expect(screen.getAllByRole("listitem")).toHaveLength(10);
    });
  });

  describe("Accessibility", () => {
    it("announces the loaded entity count via a polite status region", () => {
      const items = [createEntity()];
      mockHookReturn({
        data: { channel_id: CHANNEL_ID, total_entities: 1, items },
      });
      renderPanel();

      expect(screen.getByText(/loaded 1 entity/i)).toBeInTheDocument();
    });
  });
});
