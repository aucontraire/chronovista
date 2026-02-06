/**
 * Unit tests for usePrefersReducedMotion hook.
 *
 * Tests the FR-012c accessibility requirement: Detect user's reduced motion preference.
 *
 * @module tests/hooks/usePrefersReducedMotion
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook } from "@testing-library/react";
import { usePrefersReducedMotion } from "../../hooks/usePrefersReducedMotion";

describe("usePrefersReducedMotion", () => {
  beforeEach(() => {
    // Reset matchMedia mock before each test
    vi.clearAllMocks();
  });

  it("returns false by default when user has not enabled reduced motion", () => {
    // Mock matchMedia to return matches: false
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));

    const { result } = renderHook(() => usePrefersReducedMotion());
    expect(result.current).toBe(false);
  });

  it("returns true when user has enabled reduced motion", () => {
    // Mock matchMedia to return matches: true
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: true,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));

    const { result } = renderHook(() => usePrefersReducedMotion());
    expect(result.current).toBe(true);
  });

  it("queries the correct media query string", () => {
    const matchMediaSpy = vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));

    window.matchMedia = matchMediaSpy;

    renderHook(() => usePrefersReducedMotion());

    expect(matchMediaSpy).toHaveBeenCalledWith("(prefers-reduced-motion: reduce)");
  });

  it("registers event listener for media query changes (modern browsers)", () => {
    const addEventListenerSpy = vi.fn();
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: addEventListenerSpy,
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));

    renderHook(() => usePrefersReducedMotion());

    expect(addEventListenerSpy).toHaveBeenCalledWith("change", expect.any(Function));
  });

  it("falls back to addListener for older browsers", () => {
    const addListenerSpy = vi.fn();
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: addListenerSpy,
      removeListener: vi.fn(),
      // No addEventListener method (older browser)
      dispatchEvent: vi.fn(),
    }));

    renderHook(() => usePrefersReducedMotion());

    expect(addListenerSpy).toHaveBeenCalledWith(expect.any(Function));
  });

  it("cleans up event listener on unmount (modern browsers)", () => {
    const removeEventListenerSpy = vi.fn();
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: removeEventListenerSpy,
      dispatchEvent: vi.fn(),
    }));

    const { unmount } = renderHook(() => usePrefersReducedMotion());
    unmount();

    expect(removeEventListenerSpy).toHaveBeenCalledWith("change", expect.any(Function));
  });

  it("cleans up listener on unmount (older browsers)", () => {
    const removeListenerSpy = vi.fn();
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: removeListenerSpy,
      // No removeEventListener method (older browser)
      dispatchEvent: vi.fn(),
    }));

    const { unmount } = renderHook(() => usePrefersReducedMotion());
    unmount();

    expect(removeListenerSpy).toHaveBeenCalledWith(expect.any(Function));
  });

  it("updates when media query changes", () => {
    let changeHandler: ((event: MediaQueryListEvent) => void) | null = null;

    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn((event: string, handler: (event: MediaQueryListEvent) => void) => {
        if (event === "change") {
          changeHandler = handler;
        }
      }),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));

    const { result, rerender } = renderHook(() => usePrefersReducedMotion());

    // Initially false
    expect(result.current).toBe(false);

    // Simulate media query change event
    if (changeHandler) {
      changeHandler({ matches: true } as MediaQueryListEvent);
    }

    rerender();

    // Should now be true
    expect(result.current).toBe(true);
  });

  it("handles missing matchMedia gracefully (SSR scenario)", () => {
    // Save original matchMedia
    const originalMatchMedia = window.matchMedia;

    // Remove matchMedia to simulate SSR
    // @ts-expect-error - Testing SSR scenario
    delete window.matchMedia;

    const { result } = renderHook(() => usePrefersReducedMotion());

    // Should default to false
    expect(result.current).toBe(false);

    // Restore matchMedia
    window.matchMedia = originalMatchMedia;
  });
});
