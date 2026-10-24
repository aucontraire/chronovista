/**
 * EntityPortrait accessibility and remove control (Feature 092, FR-016).
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { EntityPortrait } from "../EntityPortrait";
import type { EntityImageState } from "../../../api/entityMentions";

const removeMock = vi.fn();
const setSourceMock = vi.fn();
const uploadMock = vi.fn();
vi.mock("../../../api/entityMentions", async () => {
  const actual = await vi.importActual<
    typeof import("../../../api/entityMentions")
  >("../../../api/entityMentions");
  return {
    ...actual,
    removeEntityImage: (...args: unknown[]) => removeMock(...args),
    setEntityImageSource: (...args: unknown[]) => setSourceMock(...args),
    uploadEntityImage: (...args: unknown[]) => uploadMock(...args),
  };
});

const ENTITY_ID = "11111111-1111-4111-8111-111111111111";
const BOTH: EntityImageState = {
  has_manual: true,
  has_wikidata: true,
  source: "manual",
  version: "v1",
};

function setup(image?: EntityImageState) {
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

describe("EntityPortrait accessibility", () => {
  beforeEach(() => {
    removeMock.mockReset();
    setSourceMock.mockReset();
    uploadMock.mockReset();
  });

  it("gives every control a programmatic name and the image alt text", () => {
    setup(BOTH);
    expect(screen.getByLabelText("Replace portrait")).toBeInTheDocument();
    expect(
      screen.getByRole("group", { name: "Portrait source" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Your image" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Wikidata image" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Remove portrait" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Sample Entity" })).toHaveAttribute(
      "alt",
    );
    expect(
      screen.getByRole("link", {
        name: "Open full-size portrait of Sample Entity",
      }),
    ).toBeInTheDocument();
  });

  it("renders no live region while idle", () => {
    setup(BOTH);
    expect(screen.queryByRole("status")).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("is keyboard operable with a visible focus indicator", async () => {
    setSourceMock.mockResolvedValue({ ...BOTH, source: "wikidata" });
    setup(BOTH);
    const wikidata = screen.getByRole("button", { name: "Wikidata image" });
    expect(wikidata.className).toContain("focus-visible:ring-2");
    expect(
      screen.getByRole("button", { name: "Remove portrait" }).className,
    ).toContain("focus-visible:ring-2");
    expect(screen.getByLabelText("Replace portrait").className).toContain(
      "focus-visible:ring-2",
    );

    wikidata.focus();
    expect(wikidata).toHaveFocus();
    await userEvent.keyboard("{Enter}");
    await waitFor(() =>
      expect(setSourceMock).toHaveBeenCalledWith(ENTITY_ID, "wikidata"),
    );
    expect(await screen.findByRole("status")).toHaveTextContent(
      "Now showing Wikidata image.",
    );
  });

  it("removes the manual image, invalidates entity-detail and announces it", async () => {
    removeMock.mockResolvedValue(undefined);
    const spy = setup(BOTH);
    const remove = screen.getByRole("button", { name: "Remove portrait" });
    remove.focus();
    await userEvent.keyboard(" ");

    await waitFor(() => expect(removeMock).toHaveBeenCalledWith(ENTITY_ID));
    await waitFor(() =>
      expect(spy).toHaveBeenCalledWith({
        queryKey: ["entity-detail", ENTITY_ID],
      }),
    );
    expect(await screen.findByRole("status")).toHaveTextContent(
      "Your portrait was removed.",
    );
  });

  it("hides the remove control when there is no manual image", () => {
    setup({
      has_manual: false,
      has_wikidata: true,
      source: "wikidata",
      version: "v1",
    });
    expect(
      screen.queryByRole("button", { name: "Remove portrait" }),
    ).toBeNull();
  });

  it("announces a failed removal with an alert", async () => {
    removeMock.mockRejectedValue({ message: "Remove failed" });
    setup(BOTH);
    await userEvent.click(
      screen.getByRole("button", { name: "Remove portrait" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("Remove failed");
  });

  it("announces a successful upload", async () => {
    uploadMock.mockResolvedValue({ ...BOTH });
    setup();
    await userEvent.upload(
      screen.getByLabelText("Upload portrait"),
      new File(["x"], "a.png", { type: "image/png" }),
    );
    expect(await screen.findByRole("status")).toHaveTextContent(
      "Portrait uploaded.",
    );
  });
});
