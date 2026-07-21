import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { installPreloadErrorReload } from "../preloadErrorReload";

describe("installPreloadErrorReload", () => {
  let reloadSpy: ReturnType<typeof vi.fn>;

  // Install the handler exactly once — re-installing would stack listeners.
  beforeAll(() => {
    installPreloadErrorReload();
  });

  beforeEach(() => {
    sessionStorage.clear();
    reloadSpy = vi.fn();
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { reload: reloadSpy },
    });
  });

  function firePreloadError(): void {
    window.dispatchEvent(new Event("vite:preloadError", { cancelable: true }));
  }

  it("reloads the page once when a dynamic import fails", () => {
    firePreloadError();
    expect(reloadSpy).toHaveBeenCalledTimes(1);
  });

  it("does not reload again within the guard window (no reload loop)", () => {
    firePreloadError();
    firePreloadError();
    firePreloadError();
    expect(reloadSpy).toHaveBeenCalledTimes(1);
  });

  it("reloads again once the guard window has elapsed", () => {
    vi.useFakeTimers();
    try {
      firePreloadError();
      expect(reloadSpy).toHaveBeenCalledTimes(1);

      vi.advanceTimersByTime(10_001);
      firePreloadError();
      expect(reloadSpy).toHaveBeenCalledTimes(2);
    } finally {
      vi.useRealTimers();
    }
  });
});
