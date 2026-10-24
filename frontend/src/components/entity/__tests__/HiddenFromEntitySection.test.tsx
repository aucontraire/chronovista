/**
 * HiddenFromEntitySection — restore section (Feature 091).
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor, render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { HiddenFromEntitySection } from "../HiddenFromEntitySection";

const fetchMock = vi.fn();
const deleteMock = vi.fn();
vi.mock("../../../api/entityMentions", async () => {
  const actual = await vi.importActual<
    typeof import("../../../api/entityMentions")
  >("../../../api/entityMentions");
  return {
    ...actual,
    fetchEntityVideoExclusions: (...args: unknown[]) => fetchMock(...args),
    deleteEntityVideoExclusion: (...args: unknown[]) => deleteMock(...args),
  };
});

const ENTITY_ID = "11111111-1111-4111-8111-111111111111";

function listResponse(videoIds: string[]) {
  return {
    data: videoIds.map((video_id) => ({
      entity_id: ENTITY_ID,
      video_id,
      excluded_by: "user",
      excluded_at: "2026-01-01T00:00:00Z",
      reason: null,
    })),
    pagination: { total: videoIds.length, limit: 100, offset: 0, has_more: false },
  };
}

function setup() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const spy = vi.spyOn(queryClient, "invalidateQueries");
  render(
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <HiddenFromEntitySection entityId={ENTITY_ID} entityName="Sample Entity" />
      </QueryClientProvider>
    </MemoryRouter>
  );
  return spy;
}

describe("HiddenFromEntitySection", () => {
  beforeEach(() => {
    fetchMock.mockReset();
    deleteMock.mockReset();
  });

  it("renders nothing when there are no exclusions", async () => {
    fetchMock.mockResolvedValue(listResponse([]));
    setup();
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(screen.queryByTestId("hidden-from-entity")).not.toBeInTheDocument();
  });

  it("lists exclusions with a link and Restore button each", async () => {
    fetchMock.mockResolvedValue(listResponse(["vid0000001", "vid0000002"]));
    setup();

    expect(
      await screen.findByRole("heading", { name: /Hidden from this entity \(2\)/ })
    ).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /^Restore video/ })).toHaveLength(2);
    expect(screen.getByRole("link", { name: "Video vid0000001" })).toHaveAttribute(
      "href",
      "/videos/vid0000001"
    );
  });

  it("Restore fires the delete mutation and invalidates association caches", async () => {
    fetchMock.mockResolvedValue(listResponse(["vid0000001"]));
    deleteMock.mockResolvedValue(undefined);
    const spy = setup();

    await userEvent
      .setup()
      .click(await screen.findByRole("button", { name: /^Restore video vid0000001/ }));

    await waitFor(() =>
      expect(deleteMock).toHaveBeenCalledWith(ENTITY_ID, "vid0000001")
    );
    await waitFor(() => {
      const keys = spy.mock.calls.map((c) => c[0]?.queryKey);
      expect(keys).toContainEqual(["entity-videos"]);
      expect(keys).toContainEqual(["video-entities", "vid0000001"]);
      expect(keys).toContainEqual(["entitySearch"]);
      expect(keys).toContainEqual(["entity-detail", ENTITY_ID]);
      expect(keys).toContainEqual(["entity-exclusions", ENTITY_ID]);
    });
  });
});
