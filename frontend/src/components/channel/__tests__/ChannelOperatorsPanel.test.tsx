/**
 * Tests for ChannelOperatorsPanel: states, operator links, type badges.
 */

import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import type { Mock } from "vitest";

vi.mock("../../../hooks/useChannelOperators", () => ({
  useChannelOperators: vi.fn(),
}));

const assignMutate = vi.fn();
let assignState: Record<string, unknown> = {};
const removeMutate = vi.fn();
vi.mock("../../../hooks/useChannelOperatorMutations", () => ({
  useRemoveChannelOperator: () => ({
    mutate: removeMutate,
    isPending: false,
    isError: false,
    error: null,
  }),
  useAssignChannelOperator: () => ({
    mutate: assignMutate,
    isPending: false,
    isError: false,
    error: null,
    reset: vi.fn(),
    ...assignState,
  }),
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
  beforeEach(() => {
    vi.clearAllMocks();
    assignState = {};
  });

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
          { entity_id: "ent-1", entity_type: "organization", canonical_name: "Placeholder Org", provenance: "wikidata" },
          { entity_id: "ent-2", entity_type: "person", canonical_name: "Placeholder Person", provenance: "manual" },
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

  const mixed: ChannelOperatorsResponse = {
    channel_id: CHANNEL_ID,
    total_entities: 2,
    items: [
      { entity_id: "ent-w", entity_type: "organization", canonical_name: "Wiki Org", provenance: "wikidata" },
      { entity_id: "ent-m", entity_type: "person", canonical_name: "Manual Person", provenance: "manual" },
    ],
  };

  it("shows a provenance badge per operator", () => {
    mockHook({ data: mixed });
    renderPanel();
    expect(screen.getByText("per Wikidata")).toBeInTheDocument();
    expect(screen.getByText("you added")).toBeInTheDocument();
  });

  it("offers remove only on manual rows and calls it with the entity id", async () => {
    mockHook({ data: mixed });
    renderPanel();
    expect(screen.getAllByRole("button", { name: /^remove/i })).toHaveLength(1);
    expect(screen.queryByRole("button", { name: /remove wiki org/i })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /remove manual person/i }));
    expect(removeMutate).toHaveBeenCalledWith("ent-m");
  });

  it("submits the trimmed entity id and clears the input on success", async () => {
    mockHook({ data: mixed });
    assignMutate.mockImplementation((_id: string, opts?: { onSuccess?: () => void }) => opts?.onSuccess?.());
    renderPanel();
    const input = screen.getByLabelText(/assign an owner/i);
    await userEvent.type(input, "  ent-new  ");
    await userEvent.click(screen.getByRole("button", { name: "Assign" }));
    expect(assignMutate).toHaveBeenCalledWith("ent-new", expect.any(Object));
    expect(input).toHaveValue("");
  });

  it("shows create-it-first guidance on 404", () => {
    mockHook({ data: mixed });
    assignState = { isError: true, error: { status: 404 } };
    renderPanel();
    expect(screen.getByRole("alert")).toHaveTextContent(/doesn't exist — create it first/i);
  });

  it("shows the server detail on 409", () => {
    mockHook({ data: mixed });
    assignState = { isError: true, error: { status: 409, detail: "Already recorded from Wikidata" } };
    renderPanel();
    expect(screen.getByRole("alert")).toHaveTextContent("Already recorded from Wikidata");
  });
});
