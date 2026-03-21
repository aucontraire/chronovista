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
  it("has exactly 9 top-level entries", () => {
    expect(navRoutes).toHaveLength(9);
  });

  it("first entry is Videos flat route", () => {
    const entry = navRoutes[0];
    expect(entry?.kind).toBe("route");
    if (entry?.kind === "route") {
      expect(entry.path).toBe("/videos");
      expect(entry.label).toBe("Videos");
    }
  });

  it("second entry is the Transcripts group", () => {
    const entry = navRoutes[1];
    expect(entry?.kind).toBe("group");
    if (entry?.kind === "group") {
      expect(entry.label).toBe("Transcripts");
    }
  });

  it("third entry is Channels flat route", () => {
    const entry = navRoutes[2];
    expect(entry?.kind).toBe("route");
    if (entry?.kind === "route") {
      expect(entry.path).toBe("/channels");
    }
  });

  it("fourth entry is Playlists flat route", () => {
    const entry = navRoutes[3];
    expect(entry?.kind).toBe("route");
    if (entry?.kind === "route") {
      expect(entry.path).toBe("/playlists");
    }
  });

  it("fifth entry is Entities flat route", () => {
    const entry = navRoutes[4];
    expect(entry?.kind).toBe("route");
    if (entry?.kind === "route") {
      expect(entry.path).toBe("/entities");
    }
  });

  it("sixth entry is Search flat route", () => {
    const entry = navRoutes[5];
    expect(entry?.kind).toBe("route");
    if (entry?.kind === "route") {
      expect(entry.path).toBe("/search");
      expect(entry.label).toBe("Search");
    }
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
  it("separator appears at index 6", () => {
    expect(navRoutes[6]?.kind).toBe("separator");
  });

  it("Setup route appears at index 7, after the separator", () => {
    const entry = navRoutes[7];
    expect(entry?.kind).toBe("route");
    if (entry?.kind === "route") {
      expect(entry.path).toBe("/onboarding");
      expect(entry.label).toBe("Setup");
    }
  });

  it("Settings route appears at index 8, after Setup", () => {
    const entry = navRoutes[8];
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
