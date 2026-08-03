/**
 * Tests for navRoutes structure — Feature 046 (US0) sidebar restructuring.
 *
 * Verifies:
 * - All expected top-level entries are present
 * - The Transcripts group has the correct children
 * - Flat nav items remain as NavRoute (kind: "route")
 * - The Transcripts group is a NavGroupRoute (kind: "group")
 * - Each child of Transcripts group carries correct paths and labels
 * - Setup and Settings appear after the separator (admin/config section)
 */

import { describe, it, expect } from "vitest";
import {
  navRoutes,
  type NavRoute,
  type NavGroupRoute,
  type NavEntry,
} from "../routes";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function findRoute(entries: NavEntry[], path: string): NavRoute | undefined {
  for (const entry of entries) {
    if (entry.kind === "route" && entry.path === path) return entry;
    if (entry.kind === "group") {
      const match = entry.children.find((c) => c.path === path);
      if (match) return match;
    }
  }
  return undefined;
}

function findGroup(entries: NavEntry[], label: string): NavGroupRoute | undefined {
  return entries.find(
    (e): e is NavGroupRoute => e.kind === "group" && e.label === label
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("navRoutes — top-level structure", () => {
  // Asserted as one explicit ordered list rather than per-index tests. The
  // previous form checked navRoutes[0..6] individually, so inserting an entry
  // renumbered every later assertion and broke 12 tests at once — the same
  // brittleness as a mock that dispatches by call number. Order is still
  // covered, but a deliberate change now edits one list.
  it("has the expected top-level entries in order", () => {
    const shape = navRoutes.map((e) =>
      e.kind === "route"
        ? `route:${e.path}`
        : e.kind === "group"
          ? `group:${e.label}`
          : "separator"
    );

    expect(shape).toEqual([
      // Feature 061: an ADDITIONAL destination. `/` still redirects to /videos,
      // so the landing page is unchanged (FR-014a).
      "route:/overview",
      "route:/videos",
      "group:Transcripts",
      "route:/channels",
      "route:/playlists",
      "route:/entities",
      "group:Tags",
      "route:/search",
      "separator",
      "route:/onboarding",
      "route:/settings",
    ]);
  });

  it("Overview is a flat route with label and icon", () => {
    const route = findRoute(navRoutes, "/overview");
    expect(route).toBeDefined();
    expect(route?.label).toBe("Overview");
    expect(route?.tooltip).toBeTruthy();
    expect(route?.icon).toBeDefined();
  });
});

describe("navRoutes — flat NavRoute entries", () => {
  it("/videos route has correct label and tooltip", () => {
    const route = findRoute(navRoutes, "/videos");
    expect(route).toBeDefined();
    expect(route?.label).toBe("Videos");
    expect(route?.tooltip).toBeTruthy();
    expect(route?.icon).toBeDefined();
  });

  it("/channels route has correct label and tooltip", () => {
    const route = findRoute(navRoutes, "/channels");
    expect(route).toBeDefined();
    expect(route?.label).toBe("Channels");
    expect(route?.icon).toBeDefined();
  });

  it("/playlists route has correct label and tooltip", () => {
    const route = findRoute(navRoutes, "/playlists");
    expect(route).toBeDefined();
    expect(route?.label).toBe("Playlists");
    expect(route?.icon).toBeDefined();
  });

  it("/entities route has correct label and tooltip", () => {
    const route = findRoute(navRoutes, "/entities");
    expect(route).toBeDefined();
    expect(route?.label).toBe("Entities");
    expect(route?.icon).toBeDefined();
  });

  it("/search route is a top-level flat route (not nested under Transcripts)", () => {
    const topLevel = navRoutes.find(
      (e): e is NavRoute => e.kind === "route" && e.path === "/search"
    );
    expect(topLevel).toBeDefined();
    expect(topLevel?.label).toBe("Search");
    expect(topLevel?.icon).toBeDefined();
  });
});

describe("navRoutes — config section order", () => {
  // Positions are expressed relative to the separator rather than as absolute
  // indices, so inserting a content route above it does not renumber these.
  const separatorIndex = () => navRoutes.findIndex((e) => e.kind === "separator");

  it("has exactly one separator", () => {
    expect(navRoutes.filter((e) => e.kind === "separator")).toHaveLength(1);
  });

  it("Setup route appears immediately after the separator", () => {
    const entry = navRoutes[separatorIndex() + 1];
    expect(entry?.kind).toBe("route");
    if (entry?.kind === "route") {
      expect(entry.path).toBe("/onboarding");
      expect(entry.label).toBe("Setup");
    }
  });

  it("Settings route appears after Setup", () => {
    const entry = navRoutes[separatorIndex() + 2];
    expect(entry?.kind).toBe("route");
    if (entry?.kind === "route") {
      expect(entry.path).toBe("/settings");
      expect(entry.label).toBe("Settings");
    }
  });

  it("Setup and Settings are both below the separator", () => {
    const separatorIndex = navRoutes.findIndex((e) => e.kind === "separator");
    const setupIndex = navRoutes.findIndex(
      (e): e is NavRoute => e.kind === "route" && e.path === "/onboarding"
    );
    const settingsIndex = navRoutes.findIndex(
      (e): e is NavRoute => e.kind === "route" && e.path === "/settings"
    );
    expect(setupIndex).toBeGreaterThan(separatorIndex);
    expect(settingsIndex).toBeGreaterThan(separatorIndex);
    expect(settingsIndex).toBeGreaterThan(setupIndex);
  });
});

describe("navRoutes — Transcripts group", () => {
  it("Transcripts group exists", () => {
    const group = findGroup(navRoutes, "Transcripts");
    expect(group).toBeDefined();
  });

  it("Transcripts group has kind='group'", () => {
    const group = findGroup(navRoutes, "Transcripts");
    expect(group?.kind).toBe("group");
  });

  it("Transcripts group has an icon", () => {
    const group = findGroup(navRoutes, "Transcripts");
    expect(group?.icon).toBeDefined();
  });

  it("Transcripts group has a tooltip", () => {
    const group = findGroup(navRoutes, "Transcripts");
    expect(group?.tooltip).toBeTruthy();
  });

  it("Transcripts group has a storageKey", () => {
    const group = findGroup(navRoutes, "Transcripts");
    expect(group?.storageKey).toBeTruthy();
  });

  it("Transcripts group defaultExpanded is true", () => {
    const group = findGroup(navRoutes, "Transcripts");
    expect(group?.defaultExpanded).toBe(true);
  });

  it("Transcripts group has exactly 3 children", () => {
    const group = findGroup(navRoutes, "Transcripts");
    expect(group?.children).toHaveLength(3);
  });

  it("Transcripts group children all have kind='route'", () => {
    const group = findGroup(navRoutes, "Transcripts");
    group?.children.forEach((child) => {
      expect(child.kind).toBe("route");
    });
  });

  it("Transcripts group contains Find & Replace child at /corrections/batch", () => {
    const group = findGroup(navRoutes, "Transcripts");
    const child = group?.children.find((c) => c.path === "/corrections/batch");
    expect(child).toBeDefined();
    expect(child?.label).toBe("Find & Replace");
    expect(child?.icon).toBeDefined();
  });

  it("Transcripts group contains Batch History child at /corrections/batch/history", () => {
    const group = findGroup(navRoutes, "Transcripts");
    const child = group?.children.find(
      (c) => c.path === "/corrections/batch/history"
    );
    expect(child).toBeDefined();
    expect(child?.label).toBe("Batch History");
    expect(child?.icon).toBeDefined();
  });

  it("Transcripts group contains ASR Error Patterns child at /corrections/diff-analysis", () => {
    const group = findGroup(navRoutes, "Transcripts");
    const child = group?.children.find(
      (c) => c.path === "/corrections/diff-analysis"
    );
    expect(child).toBeDefined();
    expect(child?.label).toBe("ASR Error Patterns");
    expect(child?.icon).toBeDefined();
  });

  it("Transcripts group child order is Find & Replace, Batch History, ASR Error Patterns", () => {
    const group = findGroup(navRoutes, "Transcripts");
    const labels = group?.children.map((c) => c.label);
    expect(labels).toEqual([
      "Find & Replace",
      "Batch History",
      "ASR Error Patterns",
    ]);
  });
});

describe("navRoutes — Tags group (Feature 056)", () => {
  it("Tags group exists", () => {
    const group = findGroup(navRoutes, "Tags");
    expect(group).toBeDefined();
  });

  it("Tags group has kind='group'", () => {
    const group = findGroup(navRoutes, "Tags");
    expect(group?.kind).toBe("group");
  });

  it("Tags group has an icon", () => {
    const group = findGroup(navRoutes, "Tags");
    expect(group?.icon).toBeDefined();
  });

  it("Tags group has a tooltip", () => {
    const group = findGroup(navRoutes, "Tags");
    expect(group?.tooltip).toBeTruthy();
  });

  it("Tags group has storageKey 'chronovista.sidebar.tagsExpanded'", () => {
    const group = findGroup(navRoutes, "Tags");
    expect(group?.storageKey).toBe("chronovista.sidebar.tagsExpanded");
  });

  it("Tags group defaultExpanded is true", () => {
    const group = findGroup(navRoutes, "Tags");
    expect(group?.defaultExpanded).toBe(true);
  });

  it("Tags group has exactly 1 child", () => {
    const group = findGroup(navRoutes, "Tags");
    expect(group?.children).toHaveLength(1);
  });

  it("Tags group contains Merge Tags child at /tags/merge", () => {
    const group = findGroup(navRoutes, "Tags");
    const child = group?.children.find((c) => c.path === "/tags/merge");
    expect(child).toBeDefined();
    expect(child?.label).toBe("Merge Tags");
    expect(child?.icon).toBeDefined();
  });

  it("Tags group is positioned after Entities and before the config separator", () => {
    const entitiesIndex = navRoutes.findIndex(
      (e): e is NavRoute => e.kind === "route" && e.path === "/entities"
    );
    const tagsGroupIndex = navRoutes.findIndex(
      (e) => e.kind === "group" && e.label === "Tags"
    );
    const separatorIndex = navRoutes.findIndex((e) => e.kind === "separator");
    expect(tagsGroupIndex).toBeGreaterThan(entitiesIndex);
    expect(tagsGroupIndex).toBeLessThan(separatorIndex);
  });
});
