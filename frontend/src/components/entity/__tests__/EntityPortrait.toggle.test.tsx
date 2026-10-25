/**
 * EntityPortrait source toggle (Feature 092, US3).
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { EntityPortrait } from "../EntityPortrait";
import type { EntityImageState } from "../../../api/entityMentions";

const setSourceMock = vi.fn();
vi.mock("../../../api/entityMentions", async () => {
  const actual = await vi.importActual<
    typeof import("../../../api/entityMentions")
  >("../../../api/entityMentions");
  return {
    ...actual,
    setEntityImageSource: (...args: unknown[]) => setSourceMock(...args),
  };
});

const ENTITY_ID = "11111111-1111-4111-8111-111111111111";

function setup(image: EntityImageState) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const spy = vi.spyOn(queryClient, "invalidateQueries");
  render(
    <QueryClientProvider client={queryClient}>
      <EntityPortrait
        entityId={ENTITY_ID}
        canonicalName="Sample Entity"
        image={image}
      />
    </QueryClientProvider>,
  );
  return spy;
}

describe("EntityPortrait source toggle", () => {
  beforeEach(() => setSourceMock.mockReset());

  it("is hidden when only a manual image exists", () => {
    setup({
      has_manual: true,
      has_wikidata: false,
      source: "manual",
      version: "v1",
    });
    expect(screen.queryByRole("group", { name: "Portrait source" })).toBeNull();
  });

  it("is hidden when only a Wikidata image exists", () => {
    setup({
      has_manual: false,
      has_wikidata: true,
      source: "wikidata",
      version: "v1",
    });
    expect(screen.queryByRole("group", { name: "Portrait source" })).toBeNull();
  });

  it("shows when both exist, reflects the active source, and switches", async () => {
    setSourceMock.mockResolvedValue({
      has_manual: true,
      has_wikidata: true,
      source: "wikidata",
      version: "v2",
    });
    const spy = setup({
      has_manual: true,
      has_wikidata: true,
      source: "manual",
      version: "v1",
    });

    expect(screen.getByRole("button", { name: "Your image" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Automated image" }),
    );

    await waitFor(() =>
      expect(setSourceMock).toHaveBeenCalledWith(ENTITY_ID, "wikidata"),
    );
    await waitFor(() =>
      expect(spy).toHaveBeenCalledWith({
        queryKey: ["entity-detail", ENTITY_ID],
      }),
    );
  });

  it("does not fire when clicking the already active source", async () => {
    setup({
      has_manual: true,
      has_wikidata: true,
      source: "manual",
      version: "v1",
    });
    await userEvent.click(screen.getByRole("button", { name: "Your image" }));
    expect(setSourceMock).not.toHaveBeenCalled();
  });
});
