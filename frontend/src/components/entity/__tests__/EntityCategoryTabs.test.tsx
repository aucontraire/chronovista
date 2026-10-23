import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { EntityCategoryTabs } from "../EntityCategoryTabs";

const TABS = [
  { key: "all", label: "First view", panel: <p>first content</p> },
  { key: "second", label: "Second view", panel: <p>second content</p> },
  { key: "third", label: "Third view", panel: <p>third content</p> },
];

function renderTabs() {
  return render(<EntityCategoryTabs tabs={TABS} />);
}

describe("EntityCategoryTabs", () => {
  it("renders a tablist with the first tab selected and its panel shown", () => {
    renderTabs();
    expect(screen.getByRole("tablist")).toBeInTheDocument();
    const tabs = screen.getAllByRole("tab");
    expect(tabs).toHaveLength(3);
    expect(tabs[0]).toHaveAttribute("aria-selected", "true");
    expect(tabs[1]).toHaveAttribute("aria-selected", "false");
    expect(tabs[0]).toHaveAttribute("tabindex", "0");
    expect(tabs[1]).toHaveAttribute("tabindex", "-1");
    expect(screen.getByText("first content")).toBeInTheDocument();
  });

  it("links the active tab and panel through aria-controls / aria-labelledby", () => {
    renderTabs();
    const tab = screen.getByTestId("category-tab-all");
    const panel = screen.getByRole("tabpanel");
    expect(tab.getAttribute("aria-controls")).toBe(panel.id);
    expect(panel.getAttribute("aria-labelledby")).toBe(tab.id);
  });

  it("sets aria-controls only on the active tab", () => {
    renderTabs();
    expect(screen.getByTestId("category-tab-all")).toHaveAttribute("aria-controls");
    expect(screen.getByTestId("category-tab-second")).not.toHaveAttribute(
      "aria-controls"
    );
  });

  it("focuses the tab on click", () => {
    renderTabs();
    fireEvent.click(screen.getByTestId("category-tab-second"));
    expect(screen.getByTestId("category-tab-second")).toHaveFocus();
  });

  it("lazy-mounts: inactive panels are absent until activated", () => {
    renderTabs();
    expect(screen.queryByText("second content")).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId("category-tab-second"));
    expect(screen.getByText("second content")).toBeInTheDocument();
    expect(screen.queryByText("first content")).not.toBeInTheDocument();
    expect(screen.getByTestId("category-tab-second")).toHaveAttribute(
      "aria-selected",
      "true"
    );
  });

  it("moves selection with arrow keys, wrapping at the ends", () => {
    renderTabs();
    const first = screen.getByTestId("category-tab-all");
    fireEvent.keyDown(first, { key: "ArrowRight" });
    expect(screen.getByTestId("category-tab-second")).toHaveAttribute(
      "aria-selected",
      "true"
    );
    expect(screen.getByTestId("category-tab-second")).toHaveFocus();
    fireEvent.keyDown(screen.getByTestId("category-tab-second"), {
      key: "ArrowLeft",
    });
    fireEvent.keyDown(screen.getByTestId("category-tab-all"), {
      key: "ArrowLeft",
    });
    expect(screen.getByTestId("category-tab-third")).toHaveAttribute(
      "aria-selected",
      "true"
    );
  });

  it("jumps with Home and End", () => {
    renderTabs();
    fireEvent.keyDown(screen.getByTestId("category-tab-all"), { key: "End" });
    expect(screen.getByText("third content")).toBeInTheDocument();
    fireEvent.keyDown(screen.getByTestId("category-tab-third"), { key: "Home" });
    expect(screen.getByText("first content")).toBeInTheDocument();
    expect(screen.queryByText("third content")).not.toBeInTheDocument();
  });
});
