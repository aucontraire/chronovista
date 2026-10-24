/**
 * EntityPortrait upload control (Feature 092, US1).
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { EntityPortrait } from "../EntityPortrait";

const uploadMock = vi.fn();
vi.mock("../../../api/entityMentions", async () => {
  const actual = await vi.importActual<
    typeof import("../../../api/entityMentions")
  >("../../../api/entityMentions");
  return {
    ...actual,
    uploadEntityImage: (...args: unknown[]) => uploadMock(...args),
  };
});

const ENTITY_ID = "11111111-1111-4111-8111-111111111111";

function setup(image?: {
  has_manual: boolean;
  has_wikidata: boolean;
  source: "manual" | "wikidata";
  version: string | null;
}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const spy = vi.spyOn(queryClient, "invalidateQueries");
  render(
    <QueryClientProvider client={queryClient}>
      <EntityPortrait
        entityId={ENTITY_ID}
        canonicalName="Sample Entity"
        {...(image ? { image } : {})}
      />
    </QueryClientProvider>,
  );
  return spy;
}

describe("EntityPortrait upload control", () => {
  beforeEach(() => {
    uploadMock.mockReset();
  });

  it("uploads the chosen file and invalidates the entity-detail query", async () => {
    uploadMock.mockResolvedValue({
      has_manual: true,
      has_wikidata: false,
      source: "manual",
      version: "2026-01-01T00:00:00Z",
    });
    const spy = setup();
    const file = new File(["x"], "portrait.png", { type: "image/png" });

    await userEvent.upload(screen.getByLabelText("Upload portrait"), file);

    await waitFor(() =>
      expect(uploadMock).toHaveBeenCalledWith(ENTITY_ID, file),
    );
    await waitFor(() =>
      expect(spy).toHaveBeenCalledWith({
        queryKey: ["entity-detail", ENTITY_ID],
      }),
    );
  });

  it("labels the control as replace and busts the cache with image.version", () => {
    setup({
      has_manual: true,
      has_wikidata: false,
      source: "manual",
      version: "v1",
    });
    expect(screen.getByLabelText("Replace portrait")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Sample Entity" })).toHaveAttribute(
      "src",
      expect.stringContaining("?v=v1"),
    );
  });

  it("shows an error and does not invalidate when the upload fails", async () => {
    uploadMock.mockRejectedValue({ message: "Unsupported image type" });
    const spy = setup();
    await userEvent.upload(
      screen.getByLabelText("Upload portrait"),
      new File(["x"], "a.png", { type: "image/png" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Unsupported image type",
    );
    expect(spy).not.toHaveBeenCalled();
  });
});
