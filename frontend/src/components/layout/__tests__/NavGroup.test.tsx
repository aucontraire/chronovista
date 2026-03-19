/**
 * Tests for NavGroup component — Feature 046 (US0) sidebar restructuring.
 *
 * Coverage:
 * - Renders expanded by default when defaultExpanded=true
 * - Renders collapsed by default when defaultExpanded=false
 * - Toggle collapse on button click
 * - Toggle expand on button click when collapsed
 * - localStorage persistence: reads initial state from storage
 * - localStorage persistence: writes state changes to storage
 * - Auto-expand when a child route is active (mock useLocation)
 * - Compact mode: click navigates to first child (mock useNavigate)
 * - aria-expanded attribute updates correctly
 * - Child routes render as NavItem links when expanded
 * - Child routes are hidden when collapsed
 * - Group header has accessible title (tooltip)
 * - Chevron is present in expanded state
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { NavGroup } from "../NavGroup";
import type { NavRoute } from "../../../router/routes";

// ---------------------------------------------------------------------------
// Mock useNavigate so we can assert navigation calls
// ---------------------------------------------------------------------------
const mockNavigate = vi.fn();
vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

// ---------------------------------------------------------------------------
// Test fixtures
// ---------------------------------------------------------------------------

const MOCK_ICON: React.FC<React.SVGProps<SVGSVGElement>> = (props) => (
  <svg data-testid="group-icon" {...props} />
);

const CHILD_ICON: React.FC<React.SVGProps<SVGSVGElement>> = (props) => (
  <svg data-testid="child-icon" {...props} />
);

const mockRoutes: NavRoute[] = [
  {
    kind: "route",
    path: "/search",
    label: "Search",
    tooltip: "Search transcripts",
    icon: CHILD_ICON,
  },
  {
    kind: "route",
    path: "/corrections/batch",
    label: "Find & Replace",
    tooltip: "Batch corrections",
    icon: CHILD_ICON,
  },
];

const STORAGE_KEY = "test.navgroup.expanded";

// ---------------------------------------------------------------------------
// Render helpers
// ---------------------------------------------------------------------------

interface RenderOptions {
  currentPath?: string;
  defaultExpanded?: boolean;
  storageKey?: string;
}

function renderNavGroup({
  currentPath = "/",
  defaultExpanded = true,
  storageKey = STORAGE_KEY,
}: RenderOptions = {}) {
  return render(
    <MemoryRouter initialEntries={[currentPath]}>
      <ul>
        <NavGroup
          label="Transcripts"
          tooltip="Transcripts navigation group"
          icon={MOCK_ICON}
          routes={mockRoutes}
          defaultExpanded={defaultExpanded}
          storageKey={storageKey}
        />
      </ul>
    </MemoryRouter>
  );
}

// ---------------------------------------------------------------------------
// localStorage mock helpers
// ---------------------------------------------------------------------------

function setLocalStorage(key: string, value: string) {
  localStorage.setItem(key, value);
}

// ---------------------------------------------------------------------------
// Setup / teardown
// ---------------------------------------------------------------------------

beforeEach(() => {
  localStorage.clear();
  mockNavigate.mockClear();
});

afterEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("NavGroup — default expansion", () => {
  it("renders expanded by default when defaultExpanded=true", () => {
    renderNavGroup({ defaultExpanded: true });
    // Children are visible when expanded
    expect(screen.getByRole("link", { name: /search/i })).toBeInTheDocument();
  });

  it("renders collapsed by default when defaultExpanded=false", () => {
    renderNavGroup({ defaultExpanded: false });
    // Children are hidden when collapsed
    expect(
      screen.queryByRole("link", { name: /search/i })
    ).not.toBeInTheDocument();
  });
});

describe("NavGroup — toggle behaviour", () => {
  it("collapses when the header button is clicked while expanded", () => {
    renderNavGroup({ defaultExpanded: true });

    const button = screen.getByRole("button", { name: /transcripts/i });
    fireEvent.click(button);

    expect(
      screen.queryByRole("link", { name: /search/i })
    ).not.toBeInTheDocument();
  });

  it("expands when the header button is clicked while collapsed", () => {
    renderNavGroup({ defaultExpanded: false });

    const button = screen.getByRole("button", { name: /transcripts/i });
    fireEvent.click(button);

    expect(screen.getByRole("link", { name: /search/i })).toBeInTheDocument();
  });
});

describe("NavGroup — aria-expanded", () => {
  it("aria-expanded is 'true' when expanded", () => {
    renderNavGroup({ defaultExpanded: true });
    const button = screen.getByRole("button", { name: /transcripts/i });
    expect(button).toHaveAttribute("aria-expanded", "true");
  });

  it("aria-expanded is 'false' when collapsed", () => {
    renderNavGroup({ defaultExpanded: false });
    const button = screen.getByRole("button", { name: /transcripts/i });
    expect(button).toHaveAttribute("aria-expanded", "false");
  });

  it("aria-expanded updates to 'false' after collapsing", () => {
    renderNavGroup({ defaultExpanded: true });
    const button = screen.getByRole("button", { name: /transcripts/i });
    fireEvent.click(button);
    expect(button).toHaveAttribute("aria-expanded", "false");
  });

  it("aria-expanded updates to 'true' after expanding", () => {
    renderNavGroup({ defaultExpanded: false });
    const button = screen.getByRole("button", { name: /transcripts/i });
    fireEvent.click(button);
    expect(button).toHaveAttribute("aria-expanded", "true");
  });
});

describe("NavGroup — localStorage persistence", () => {
  it("reads initial collapsed state from localStorage", () => {
    setLocalStorage(STORAGE_KEY, "false");
    renderNavGroup({ defaultExpanded: true }); // defaultExpanded is overridden by storage

    expect(
      screen.queryByRole("link", { name: /search/i })
    ).not.toBeInTheDocument();
  });

  it("reads initial expanded state from localStorage", () => {
    setLocalStorage(STORAGE_KEY, "true");
    renderNavGroup({ defaultExpanded: false }); // defaultExpanded is overridden by storage

    expect(screen.getByRole("link", { name: /search/i })).toBeInTheDocument();
  });

  it("writes collapsed state to localStorage after toggle", () => {
    renderNavGroup({ defaultExpanded: true });

    const button = screen.getByRole("button", { name: /transcripts/i });
    fireEvent.click(button);

    expect(localStorage.getItem(STORAGE_KEY)).toBe("false");
  });

  it("writes expanded state to localStorage after toggle", () => {
    renderNavGroup({ defaultExpanded: false });

    const button = screen.getByRole("button", { name: /transcripts/i });
    fireEvent.click(button);

    expect(localStorage.getItem(STORAGE_KEY)).toBe("true");
  });
});

describe("NavGroup — auto-expand when child route is active", () => {
  it("auto-expands when current path matches a child route", () => {
    // Start collapsed, navigate to a child route — should auto-expand
    renderNavGroup({
      currentPath: "/search",
      defaultExpanded: false,
    });

    // The group should auto-expand because /search is an active child
    expect(screen.getByRole("link", { name: /search/i })).toBeInTheDocument();
  });

  it("stays collapsed when no child route is active and defaultExpanded is false", () => {
    renderNavGroup({
      currentPath: "/videos",
      defaultExpanded: false,
    });

    expect(
      screen.queryByRole("link", { name: /search/i })
    ).not.toBeInTheDocument();
  });

  it("auto-expands for nested child path (sub-route prefix match)", () => {
    // /corrections/batch is a child; /corrections/batch/123 should still match
    renderNavGroup({
      currentPath: "/corrections/batch/123",
      defaultExpanded: false,
    });

    expect(screen.getByRole("link", { name: /find & replace/i })).toBeInTheDocument();
  });
});

describe("NavGroup — child routes render as NavItem links", () => {
  it("renders all child routes as links when expanded", () => {
    renderNavGroup({ defaultExpanded: true });

    expect(screen.getByRole("link", { name: /search/i })).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /find & replace/i })
    ).toBeInTheDocument();
  });

  it("each child link has the correct href", () => {
    renderNavGroup({ defaultExpanded: true });

    const searchLink = screen.getByRole("link", { name: /search/i });
    expect(searchLink).toHaveAttribute("href", "/search");

    const batchLink = screen.getByRole("link", { name: /find & replace/i });
    expect(batchLink).toHaveAttribute("href", "/corrections/batch");
  });

  it("child routes are not rendered when collapsed", () => {
    renderNavGroup({ defaultExpanded: false });

    expect(
      screen.queryByRole("link", { name: /search/i })
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: /find & replace/i })
    ).not.toBeInTheDocument();
  });
});

describe("NavGroup — group header", () => {
  it("renders the group label text", () => {
    renderNavGroup({ defaultExpanded: true });
    // The label text is rendered in the button
    expect(
      screen.getByRole("button", { name: /transcripts/i })
    ).toBeInTheDocument();
  });

  it("header button has title attribute set to tooltip", () => {
    renderNavGroup({ defaultExpanded: true });
    const button = screen.getByRole("button", { name: /transcripts/i });
    expect(button).toHaveAttribute("title", "Transcripts navigation group");
  });

  it("renders the group icon", () => {
    renderNavGroup({ defaultExpanded: true });
    expect(screen.getByTestId("group-icon")).toBeInTheDocument();
  });
});

describe("NavGroup — compact mode (< 1024px)", () => {
  beforeEach(() => {
    // Simulate compact viewport
    Object.defineProperty(window, "innerWidth", {
      writable: true,
      configurable: true,
      value: 768,
    });
  });

  afterEach(() => {
    Object.defineProperty(window, "innerWidth", {
      writable: true,
      configurable: true,
      value: 1024,
    });
  });

  it("clicking the header navigates to the first child route in compact mode", () => {
    renderNavGroup({ defaultExpanded: true });

    const button = screen.getByRole("button", { name: /transcripts/i });
    fireEvent.click(button);

    expect(mockNavigate).toHaveBeenCalledWith("/search");
  });

  it("does not toggle expand/collapse state in compact mode", () => {
    renderNavGroup({ defaultExpanded: true });

    const button = screen.getByRole("button", { name: /transcripts/i });
    fireEvent.click(button);

    // State should not have changed from expanded — links still visible
    expect(screen.getByRole("link", { name: /search/i })).toBeInTheDocument();
  });
});
