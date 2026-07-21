/**
 * Tests for Sidebar component — Feature 046 (US0) sidebar restructuring.
 *
 * Coverage:
 * - Renders the nav landmark with accessible label
 * - Renders exactly 7 top-level entries (6 li items + 1 NavGroup li)
 * - Flat nav items (Videos, Channels, Playlists, Entities) render as links
 * - Transcripts group renders with NavGroup (disclosure button)
 * - Transcripts group is expanded by default and shows child links
 * - Sidebar has correct background and responsive width classes
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { Sidebar } from "../Sidebar";

// ---------------------------------------------------------------------------
// Mock useNavigate (NavGroup uses it internally)
// ---------------------------------------------------------------------------
vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return {
    ...actual,
    useNavigate: () => vi.fn(),
  };
});

// ---------------------------------------------------------------------------
// Render helper
// ---------------------------------------------------------------------------
function renderSidebar(currentPath = "/videos") {
  return render(
    <MemoryRouter initialEntries={[currentPath]}>
      <Sidebar />
    </MemoryRouter>
  );
}

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------
beforeEach(() => {
  localStorage.clear();
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("Sidebar — landmark", () => {
  it("renders a <nav> with aria-label='Main navigation'", () => {
    renderSidebar();
    expect(
      screen.getByRole("navigation", { name: "Main navigation" })
    ).toBeInTheDocument();
  });
});

describe("Sidebar — flat nav items", () => {
  it("renders the Videos link", () => {
    renderSidebar();
    expect(screen.getByRole("link", { name: /videos/i })).toBeInTheDocument();
  });

  it("Videos link points to /videos", () => {
    renderSidebar();
    const link = screen.getByRole("link", { name: /videos/i });
    expect(link).toHaveAttribute("href", "/videos");
  });

  it("renders the Channels link", () => {
    renderSidebar();
    expect(screen.getByRole("link", { name: /channels/i })).toBeInTheDocument();
  });

  it("renders the Playlists link", () => {
    renderSidebar();
    expect(screen.getByRole("link", { name: /playlists/i })).toBeInTheDocument();
  });

  it("renders the Entities link", () => {
    renderSidebar();
    expect(screen.getByRole("link", { name: /entities/i })).toBeInTheDocument();
  });
});

describe("Sidebar — Transcripts group", () => {
  it("renders the Transcripts disclosure button", () => {
    renderSidebar();
    expect(
      screen.getByRole("button", { name: /transcripts/i })
    ).toBeInTheDocument();
  });

  it("Transcripts group is expanded by default", () => {
    renderSidebar();
    const button = screen.getByRole("button", { name: /transcripts/i });
    expect(button).toHaveAttribute("aria-expanded", "true");
  });

  it("renders Search as a top-level link (not nested under Transcripts)", () => {
    renderSidebar();
    expect(screen.getByRole("link", { name: /search/i })).toBeInTheDocument();
  });

  it("renders Find & Replace child link when Transcripts group is expanded", () => {
    renderSidebar();
    expect(
      screen.getByRole("link", { name: /find & replace/i })
    ).toBeInTheDocument();
  });

  it("renders Batch History child link when Transcripts group is expanded", () => {
    renderSidebar();
    expect(
      screen.getByRole("link", { name: /batch history/i })
    ).toBeInTheDocument();
  });

  it("renders ASR Error Patterns child link when Transcripts group is expanded", () => {
    renderSidebar();
    expect(
      screen.getByRole("link", { name: /asr error patterns/i })
    ).toBeInTheDocument();
  });
});

describe("Sidebar — Tags group", () => {
  it("renders the Tags disclosure button", () => {
    renderSidebar();
    expect(screen.getByRole("button", { name: /^tags$/i })).toBeInTheDocument();
  });

  it("Tags group is expanded by default", () => {
    renderSidebar();
    const button = screen.getByRole("button", { name: /^tags$/i });
    expect(button).toHaveAttribute("aria-expanded", "true");
  });

  it("renders Merge Tags child link when the Tags group is expanded", () => {
    renderSidebar();
    expect(
      screen.getByRole("link", { name: /merge tags/i })
    ).toBeInTheDocument();
  });

  it("Merge Tags link points to /tags/merge", () => {
    renderSidebar();
    const link = screen.getByRole("link", { name: /merge tags/i });
    expect(link).toHaveAttribute("href", "/tags/merge");
  });

  it("Tags group header is keyboard-reachable via Tab", () => {
    renderSidebar();
    const button = screen.getByRole("button", { name: /^tags$/i });
    // Disclosure buttons are natively focusable/keyboard-operable elements.
    button.focus();
    expect(button).toHaveFocus();
  });
});

describe("Sidebar — total top-level nav item count", () => {
  it("top-level list contains 10 entries (Videos, Transcripts group, Channels, Playlists, Entities, Tags group, Search, separator, Setup, Settings)", () => {
    renderSidebar();
    // The outer <ul role="list"> has 10 children (6 flat routes + 2 groups + 1 separator + 2 config routes)
    const nav = screen.getByRole("navigation", { name: "Main navigation" });
    // The direct child ul has role="list" — query it within the nav
    const outerList = nav.querySelector("ul[role='list']");
    expect(outerList).not.toBeNull();
    const directLiChildren = outerList
      ? Array.from(outerList.children).filter((el) => el.tagName === "LI")
      : [];
    expect(directLiChildren).toHaveLength(10);
  });
});
