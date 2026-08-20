/**
 * Tests for usePinnedEntities (Feature 070, US2).
 *
 * Covers the URL-addressability contract (FR-006 / SC-004): pins are
 * repeated `entity_id` query params, restored on read, toggled without
 * disturbing other params, and clearable in one call for the empty-result
 * unpin affordance.
 */

import { describe, it, expect } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { MemoryRouter, useSearchParams } from "react-router-dom";

import { usePinnedEntities } from "../usePinnedEntities";

function renderWithRouter(initialEntries: string[] = ["/"]) {
  return renderHook(
    () => {
      const pinned = usePinnedEntities();
      const [searchParams] = useSearchParams();
      return { pinned, searchParams };
    },
    {
      wrapper: ({ children }) => (
        <MemoryRouter initialEntries={initialEntries}>{children}</MemoryRouter>
      ),
    }
  );
}

describe("usePinnedEntities", () => {
  it("returns an empty pin list when the URL has no entity_id params", () => {
    const { result } = renderWithRouter(["/channels/UC1"]);
    expect(result.current.pinned.pinnedEntityIds).toEqual([]);
    expect(result.current.pinned.isPinned("e1")).toBe(false);
  });

  it("restores pinned state from the URL (FR-006/SC-004)", () => {
    const { result } = renderWithRouter(["/channels/UC1?entity_id=e1&entity_id=e2"]);
    expect(result.current.pinned.pinnedEntityIds).toEqual(["e1", "e2"]);
    expect(result.current.pinned.isPinned("e1")).toBe(true);
    expect(result.current.pinned.isPinned("e2")).toBe(true);
    expect(result.current.pinned.isPinned("e3")).toBe(false);
  });

  it("dedupes a repeated entity_id from a hand-edited URL", () => {
    const { result } = renderWithRouter([
      "/channels/UC1?entity_id=e1&entity_id=e1&entity_id=e2",
    ]);
    // Count must reflect distinct pins, not raw param occurrences.
    expect(result.current.pinned.pinnedEntityIds).toEqual(["e1", "e2"]);
  });

  it("togglePin adds an entity_id param when not yet pinned", () => {
    const { result } = renderWithRouter(["/channels/UC1"]);

    act(() => result.current.pinned.togglePin("e1"));

    expect(result.current.pinned.pinnedEntityIds).toEqual(["e1"]);
    expect(result.current.searchParams.getAll("entity_id")).toEqual(["e1"]);
  });

  it("togglePin removes the entity_id param when already pinned", () => {
    const { result } = renderWithRouter(["/channels/UC1?entity_id=e1&entity_id=e2"]);

    act(() => result.current.pinned.togglePin("e1"));

    expect(result.current.pinned.pinnedEntityIds).toEqual(["e2"]);
  });

  it("pinning a second entity narrows to the AND set (both ids present)", () => {
    const { result } = renderWithRouter(["/channels/UC1?entity_id=e1"]);

    act(() => result.current.pinned.togglePin("e2"));

    expect(result.current.pinned.pinnedEntityIds).toEqual(["e1", "e2"]);
  });

  it("preserves unrelated URL params when toggling a pin", () => {
    const { result } = renderWithRouter(["/channels/UC1?sort_by=title&sort_order=asc"]);

    act(() => result.current.pinned.togglePin("e1"));

    expect(result.current.searchParams.get("sort_by")).toBe("title");
    expect(result.current.searchParams.get("sort_order")).toBe("asc");
    expect(result.current.searchParams.getAll("entity_id")).toEqual(["e1"]);
  });

  it("clearPins removes every entity_id param at once", () => {
    const { result } = renderWithRouter([
      "/channels/UC1?entity_id=e1&entity_id=e2&sort_by=title",
    ]);

    act(() => result.current.pinned.clearPins());

    expect(result.current.pinned.pinnedEntityIds).toEqual([]);
    expect(result.current.searchParams.get("sort_by")).toBe("title");
  });
});
