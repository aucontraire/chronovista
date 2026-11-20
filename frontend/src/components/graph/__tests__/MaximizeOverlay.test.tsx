/**
 * In-app maximize (Feature 115, US5: FR-017/018/019/025). The real ExplorePanel + ConnectionGraph run
 * over the fake Cytoscape from fakeCytoscape.ts so the SAME-instance guarantee is observable; the
 * neighborhood hooks are stubbed.
 */

import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ExplorePanel } from "../ExplorePanel";
import { MaximizeOverlay } from "../MaximizeOverlay";
import { fake } from "./fakeCytoscape";
import { fixtureSubgraph } from "./fixtures";

vi.mock("cytoscape-fcose", () => ({ default: {} }));
vi.mock("cytoscape", async () => (await import("./fakeCytoscape")).fakeCytoscapeModule);

const baseHook = vi.fn();
vi.mock("../../../hooks/useNeighborhood", () => ({
  useNeighborhood: (...args: unknown[]) => baseHook(...args),
  useExpansions: () => ({ results: [], pending: 0, failed: 0 }),
}));

function withSubgraph(neighbors: number) {
  baseHook.mockReturnValue({
    subgraph: fixtureSubgraph(neighbors),
    isLoading: false,
    failure: null,
    refetch: vi.fn(),
  });
}

describe("maximize: same cy instance, resize + fit", () => {
  beforeEach(() => {
    fake.reset();
    baseHook.mockReset();
    withSubgraph(12);
    vi.stubGlobal(
      "ResizeObserver",
      class {
        observe() {}
        disconnect() {}
      },
    );
  });
  afterEach(() => vi.unstubAllGlobals());

  async function setup() {
    const user = userEvent.setup();
    render(
      <>
        <button type="button">Outside control</button>
        <ExplorePanel seeds={["a", "b"]} />
      </>,
    );
    await waitFor(() => expect(fake.layoutCalls).toHaveLength(1));
    return { user, cy: fake.instances[0]! };
  }

  it("keeps the same instance across maximize and exit, resizing and fitting both times", async () => {
    const { user, cy } = await setup();
    const layoutsBefore = fake.layoutCalls.length;
    const addedBefore = cy.added.length;

    await user.click(screen.getByRole("button", { name: "Maximize graph" }));
    expect(screen.getByRole("dialog", { name: /maximized/i })).toBeInTheDocument();
    await waitFor(() => expect(cy.fit).toHaveBeenCalledTimes(1));
    expect(cy.resize).toHaveBeenCalled();

    await user.keyboard("{Escape}");
    await waitFor(() => expect(cy.fit).toHaveBeenCalledTimes(2));

    expect(fake.instances).toHaveLength(1);
    expect(fake.instances[0]).toBe(cy);
    expect(cy.destroy).not.toHaveBeenCalled();
    // Nothing was re-added or re-laid out: the layout survived.
    expect(cy.added).toHaveLength(addedBefore);
    expect(fake.layoutCalls).toHaveLength(layoutsBefore);
  });

  it("is a modal dialog: background inert, scroll locked, focus in, Escape exits and returns focus", async () => {
    const { user } = await setup();
    const trigger = screen.getByRole("button", { name: "Maximize graph" });
    await user.click(trigger);

    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveFocus();
    expect(document.body.style.overflow).toBe("hidden");
    expect(screen.getByText("Outside control").hasAttribute("inert")).toBe(true);
    expect(trigger.closest("[inert]")).not.toBeNull();

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
    expect(document.body.style.overflow).not.toBe("hidden");
    expect(screen.getByText("Outside control").hasAttribute("inert")).toBe(false);
  });

  it("the floating toolbar reuses the layer controls (moved, not duplicated) and Fit re-fits", async () => {
    const { user, cy } = await setup();
    await user.click(screen.getByRole("button", { name: "Maximize graph" }));
    const toolbar = screen.getByRole("toolbar", { name: /graph controls/i });
    expect(screen.getAllByRole("checkbox", { name: /verified relationships/i })).toHaveLength(1);

    await user.click(within(toolbar).getByRole("checkbox", { name: /co-occurrence hints/i }));
    expect(baseHook.mock.calls.at(-1)![1]).toMatchObject({
      edgeTypes: ["verified", "category", "co_occurrence"],
    });

    await waitFor(() => expect(cy.fit).toHaveBeenCalledTimes(1));
    await user.click(within(toolbar).getByRole("button", { name: "Fit to view" }));
    await waitFor(() => expect(cy.fit).toHaveBeenCalledTimes(2));
    expect(cy.destroy).not.toHaveBeenCalled();
  });

  it("shows the node-type legend inside the maximized overlay too", async () => {
    const { user } = await setup();
    await user.click(screen.getByRole("button", { name: "Maximize graph" }));
    const toolbar = screen.getByRole("toolbar", { name: /graph controls/i });
    expect(within(toolbar).getByRole("list", { name: /colour by entity type/i })).toHaveTextContent("Person");
  });

  it("shares one relationship-filter state between the toolbar and the table slot", async () => {
    const { user } = await setup();
    const slotFilter = () => screen.getByTestId("relationship-filter");
    const edgeTypeBox = () => within(slotFilter()).getAllByRole("checkbox")[0]!;
    const label = edgeTypeBox().closest("label")!.textContent;

    // Toggle off in full screen (the toolbar copy; the table-slot copy is not rendered then).
    await user.click(screen.getByRole("button", { name: "Maximize graph" }));
    const toolbar = screen.getByRole("toolbar", { name: /graph controls/i });
    expect(screen.getAllByTestId("relationship-filter")).toHaveLength(1);
    await user.click(within(toolbar).getAllByRole("checkbox").find((c) => c.closest("label")?.textContent === label)!);
    expect(edgeTypeBox()).not.toBeChecked();
    await user.keyboard("{Escape}");

    // Back in the page: the table-slot copy shows it still off.
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(edgeTypeBox()).not.toBeChecked();
    expect(screen.getAllByRole("row")).toHaveLength(1); // header only: its edges are hidden in the table

    // And the other way round: turn it back on here, re-open full screen, it is on there too.
    await user.click(edgeTypeBox());
    await user.click(screen.getByRole("button", { name: "Maximize graph" }));
    expect(within(screen.getByTestId("relationship-filter")).getAllByRole("checkbox")[0]).toBeChecked();
  });

  it("keeps the toolbar actions first and the panel scrollable, so nothing is cramped out of reach", async () => {
    const { user } = await setup();
    await user.click(screen.getByRole("button", { name: "Maximize graph" }));
    const toolbar = screen.getByRole("toolbar", { name: /graph controls/i });
    expect(toolbar.className).toContain("overflow-y-auto");
    const buttons = within(toolbar).getAllByRole("button").map((b) => b.textContent);
    expect(buttons.slice(0, 3)).toEqual(["Fit to view", "View table", "Exit full screen"]);
    expect(within(toolbar).getByRole("button", { name: "Hide all" })).toBeInTheDocument();
  });

  it("View table leaves the dialog and focuses the table", async () => {
    const { user } = await setup();
    await user.click(screen.getByRole("button", { name: "Maximize graph" }));
    await user.click(within(screen.getByRole("toolbar")).getByRole("button", { name: "View table" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("table").parentElement).toHaveFocus();
  });

  it("does not lift the cap: same request limits, same elements, ceiling-sized graphs still render", async () => {
    const { user, cy } = await setup();
    const optionsBefore = baseHook.mock.calls.at(-1)![1];
    await user.click(screen.getByRole("button", { name: "Maximize graph" }));
    expect(baseHook.mock.calls.at(-1)![1]).toEqual(optionsBefore);
    expect(optionsBefore).toMatchObject({ ceiling: 250 });
    expect(cy.added.filter((d) => d.group === "nodes")).toHaveLength(14);
  });

  it("renders graphs up to the 250-node ceiling (above Connect's 150 default) and hides beyond it", () => {
    withSubgraph(198); // 200 nodes
    const { unmount } = render(<ExplorePanel seeds={["a"]} />);
    expect(screen.getByTestId("connection-graph")).toBeInTheDocument();
    unmount();
    withSubgraph(258); // 260 nodes
    render(<ExplorePanel seeds={["a"]} />);
    expect(screen.getByTestId("graph-too-large")).toBeInTheDocument();
  });
});

describe("MaximizeOverlay Escape precedence (FR-025)", () => {
  function Harness({ onExit }: { onExit: () => void }) {
    const [open, setOpen] = useState(true);
    return (
      <MaximizeOverlay
        maximized
        onExit={onExit}
        label="Test overlay"
        returnFocusRef={{ current: null }}
        toolbar={
          <div>
            <button type="button" aria-expanded={open} onClick={() => setOpen(true)}>
              Menu
            </button>
            {open && (
              <div
                role="menu"
                onKeyDown={(e) => {
                  if (e.key === "Escape") {
                    e.preventDefault(); // a popover consuming Escape
                    setOpen(false);
                  }
                }}
              >
                <button type="button" role="menuitem">
                  Item
                </button>
              </div>
            )}
          </div>
        }
      >
        <div>graph</div>
      </MaximizeOverlay>
    );
  }

  it("closes an open popover first, and exits only on the next Escape", async () => {
    const user = userEvent.setup();
    const onExit = vi.fn();
    render(<Harness onExit={onExit} />);
    screen.getByRole("menuitem", { name: "Item" }).focus();

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    expect(onExit).not.toHaveBeenCalled();

    await user.keyboard("{Escape}");
    expect(onExit).toHaveBeenCalledTimes(1);
  });
});
