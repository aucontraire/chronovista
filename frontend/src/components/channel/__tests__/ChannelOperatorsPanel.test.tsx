/**
 * Tests for ChannelOperatorsPanel: states, operator links, type badges.
 */

import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import type { Mock } from "vitest";

vi.mock("../../../hooks/useChannelOperators", () => ({
  useChannelOperators: vi.fn(),
}));

import { ChannelOperatorsPanel } from "../ChannelOperatorsPanel";
import { useChannelOperators } from "../../../hooks/useChannelOperators";
import type { ChannelOperatorsResponse } from "../../../api/channelOwnership";

const CHANNEL_ID = "UC-test-channel-001";

function mockHook(overrides: {
  data?: ChannelOperatorsResponse | undefined;
  isLoading?: boolean;
  isError?: boolean;
  error?: { message: string } | null;
  refetch?: () => void;
}) {
  (useChannelOperators as Mock).mockReturnValue({
    data: undefined,
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
    ...overrides,
  });
}

function renderPanel() {
  return render(
    <MemoryRouter>
      <ChannelOperatorsPanel channelId={CHANNEL_ID} />
    </MemoryRouter>
  );
}

describe("ChannelOperatorsPanel", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders the Operated by heading", () => {
    mockHook({ data: { channel_id: CHANNEL_ID, total_entities: 0, items: [] } });
    renderPanel();
    expect(screen.getByRole("heading", { name: "Operated by" })).toBeInTheDocument();
  });

  it("shows a loading status", () => {
    mockHook({ isLoading: true });
    renderPanel();
    const status = screen.getByRole("status");
    expect(status).toHaveAttribute("aria-busy", "true");
    expect(status).toHaveTextContent(/loading operators/i);
  });

  it("shows an error alert and retries", () => {
    const refetch = vi.fn();
    mockHook({ isError: true, error: { message: "Server error" }, refetch });
    renderPanel();
    expect(screen.getByRole("alert")).toHaveTextContent(/server error/i);
    fireEvent.click(screen.getByRole("button", { name: /retry/i }));
    expect(refetch).toHaveBeenCalledOnce();
  });

  it("shows an empty message", () => {
    mockHook({ data: { channel_id: CHANNEL_ID, total_entities: 0, items: [] } });
    renderPanel();
    expect(screen.getByText(/no operating entities/i)).toBeInTheDocument();
  });

  it("renders each operator as an entity link with a type badge, for non-person types too", () => {
    mockHook({
      data: {
        channel_id: CHANNEL_ID,
        total_entities: 2,
        items: [
          { entity_id: "ent-1", entity_type: "organization", canonical_name: "Placeholder Org" },
          { entity_id: "ent-2", entity_type: "person", canonical_name: "Placeholder Person" },
        ],
      },
    });
    renderPanel();
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    expect(screen.getByRole("link", { name: "Placeholder Org" })).toHaveAttribute(
      "href",
      "/entities/ent-1"
    );
    expect(screen.getByRole("link", { name: "Placeholder Person" })).toHaveAttribute(
      "href",
      "/entities/ent-2"
    );
    expect(screen.getByText("Organization")).toBeInTheDocument();
    expect(screen.getByText("Person")).toBeInTheDocument();
  });
});
