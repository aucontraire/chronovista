/**
 * Tests for WatchedFilterTabs (Feature 061, T028).
 *
 * Covers FR-006 (three values, All default), FR-030 (keyboard operable, selected
 * value exposed to assistive technology), and FR-035 (visible focus indicator).
 */

import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { WatchedFilterTabs } from "../WatchedFilterTabs";

describe("WatchedFilterTabs", () => {
  it("renders the three filter values (FR-006)", () => {
    render(<WatchedFilterTabs currentFilter="all" onFilterChange={vi.fn()} />);

    const tabs = screen.getAllByRole("tab");
    expect(tabs).toHaveLength(3);
    expect(tabs.map((t) => t.textContent?.trim())).toEqual([
      "All",
      "Watched",
      "Unwatched",
    ]);
  });

  it("exposes the selected value to assistive technology (FR-030)", () => {
    render(
      <WatchedFilterTabs currentFilter="unwatched" onFilterChange={vi.fn()} />
    );

    expect(screen.getByRole("tab", { name: /show only unwatched/i })).toHaveAttribute(
      "aria-selected",
      "true"
    );
    expect(screen.getByRole("tab", { name: /show all videos/i })).toHaveAttribute(
      "aria-selected",
      "false"
    );
  });

  it("is reachable by keyboard with only the selected tab in tab order", () => {
    render(
      <WatchedFilterTabs currentFilter="watched" onFilterChange={vi.fn()} />
    );

    // Roving tabindex: one stop for the whole group, arrows move within it.
    expect(screen.getByRole("tab", { name: /only watched/i })).toHaveAttribute(
      "tabindex",
      "0"
    );
    expect(screen.getByRole("tab", { name: /all videos/i })).toHaveAttribute(
      "tabindex",
      "-1"
    );
  });

  it("moves and activates with arrow keys (FR-030)", async () => {
    const user = userEvent.setup();
    const onFilterChange = vi.fn();
    render(
      <WatchedFilterTabs currentFilter="all" onFilterChange={onFilterChange} />
    );

    screen.getByRole("tab", { name: /all videos/i }).focus();
    await user.keyboard("{ArrowRight}");

    expect(onFilterChange).toHaveBeenCalledWith("watched");
  });

  it("wraps at both ends and supports Home/End (FR-030)", async () => {
    const user = userEvent.setup();
    const onFilterChange = vi.fn();
    render(
      <WatchedFilterTabs currentFilter="all" onFilterChange={onFilterChange} />
    );

    screen.getByRole("tab", { name: /all videos/i }).focus();
    await user.keyboard("{ArrowLeft}");
    expect(onFilterChange).toHaveBeenLastCalledWith("unwatched");

    await user.keyboard("{Home}");
    expect(onFilterChange).toHaveBeenLastCalledWith("all");

    await user.keyboard("{End}");
    expect(onFilterChange).toHaveBeenLastCalledWith("unwatched");
  });

  it("activates on click", async () => {
    const user = userEvent.setup();
    const onFilterChange = vi.fn();
    render(
      <WatchedFilterTabs currentFilter="all" onFilterChange={onFilterChange} />
    );

    await user.click(screen.getByRole("tab", { name: /only unwatched/i }));
    expect(onFilterChange).toHaveBeenCalledWith("unwatched");
  });

  it("shows playlist counts as badges", () => {
    render(
      <WatchedFilterTabs
        currentFilter="all"
        onFilterChange={vi.fn()}
        counts={{ all: 4973, watched: 2581, unwatched: 2392 }}
      />
    );

    // Formatted with separators; these are the playlist figures, which stay
    // fixed as the filter moves (FR-005b).
    expect(screen.getByRole("tab", { name: /all videos/i })).toHaveTextContent(
      "4,973"
    );
    expect(screen.getByRole("tab", { name: /only unwatched/i })).toHaveTextContent(
      "2,392"
    );
  });

  it("declares a visible focus indicator (FR-035)", () => {
    render(<WatchedFilterTabs currentFilter="all" onFilterChange={vi.fn()} />);

    // Focus must be visible, not suppressed by outline-none alone.
    const tab = screen.getByRole("tab", { name: /all videos/i });
    expect(tab.className).toContain("focus:ring-2");
  });
});
