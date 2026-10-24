/**
 * EntityVideoExcludeButton — unlink control (Feature 091).
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";

import { EntityVideoExcludeButton } from "../EntityVideoExcludeButton";

const createMock = vi.fn();
vi.mock("../../../api/entityMentions", async () => {
  const actual = await vi.importActual<
    typeof import("../../../api/entityMentions")
  >("../../../api/entityMentions");
  return {
    ...actual,
    createEntityVideoExclusion: (...args: unknown[]) => createMock(...args),
  };
});

const ENTITY_ID = "11111111-1111-4111-8111-111111111111";

function setup() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const spy = vi.spyOn(queryClient, "invalidateQueries");
  render(
    <QueryClientProvider client={queryClient}>
      <EntityVideoExcludeButton
        entityId={ENTITY_ID}
        entityName="Sample Entity"
        videoId="vid0000001"
      />
    </QueryClientProvider>
  );
  return spy;
}

describe("EntityVideoExcludeButton", () => {
  beforeEach(() => {
    createMock.mockReset();
  });

  it("is a labelled, keyboard-operable button that fires the exclude mutation", async () => {
    createMock.mockResolvedValue({ data: { exclusion: {}, already_excluded: false } });
    setup();
    const user = userEvent.setup();

    const button = screen.getByRole("button", {
      name: "Remove this video from Sample Entity",
    });
    button.focus();
    await user.keyboard("{Enter}");

    await waitFor(() =>
      expect(createMock).toHaveBeenCalledWith(ENTITY_ID, { videoId: "vid0000001" })
    );
  });

  it("invalidates list, count, video-entities and search caches on success", async () => {
    createMock.mockResolvedValue({ data: { exclusion: {}, already_excluded: false } });
    const spy = setup();

    await userEvent.setup().click(screen.getByRole("button"));

    await waitFor(() => {
      const keys = spy.mock.calls.map((c) => c[0]?.queryKey);
      expect(keys).toContainEqual(["entity-videos"]);
      expect(keys).toContainEqual(["video-entities", "vid0000001"]);
      expect(keys).toContainEqual(["entitySearch"]);
      expect(keys).toContainEqual(["entity-detail", ENTITY_ID]);
    });
  });

  it("shows an alert and does not invalidate when the request fails", async () => {
    createMock.mockRejectedValue({ type: "server", message: "boom" });
    const spy = setup();

    await userEvent.setup().click(screen.getByRole("button"));

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(spy).not.toHaveBeenCalled();
  });
});
