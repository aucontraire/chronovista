import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { fixturePairPassages } from "../../components/graph/__tests__/fixtures";

const fetchFarther = vi.fn();
const fetchPassages = vi.fn();
vi.mock("../../api/graph", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/graph")>()),
  fetchFartherVideos: (...args: unknown[]) => fetchFarther(...args),
  fetchPairPassages: (...args: unknown[]) => fetchPassages(...args),
}));

import {
  pendingRefetchInterval,
  useFartherVideos,
  usePairPassages,
} from "../usePairPassages";

function wrapper() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
}

const queryWith = (pending: number | null) => ({
  state: {
    data:
      pending === null
        ? undefined
        : { pages: [fixturePairPassages({ pending_scopes: pending })] },
  },
});

describe("pendingRefetchInterval", () => {
  it("polls every 3000 ms while the first page has pending scopes", () => {
    expect(pendingRefetchInterval(queryWith(2))).toBe(3000);
  });

  it("stops at zero pending scopes and before any data", () => {
    expect(pendingRefetchInterval(queryWith(0))).toBe(false);
    expect(pendingRefetchInterval(queryWith(null))).toBe(false);
  });
});

describe("usePairPassages", () => {
  beforeEach(() => fetchPassages.mockReset());

  it("fetches with the window and exposes refetch", async () => {
    fetchPassages.mockResolvedValue(fixturePairPassages());
    const { result } = renderHook(() => usePairPassages("a-id", "b-id", 60), {
      wrapper: wrapper(),
    });
    await waitFor(() => expect(result.current.first).toBeDefined());
    expect(fetchPassages).toHaveBeenCalledWith(
      expect.objectContaining({ a: "a-id", b: "b-id", window: 60, offset: 0 }),
      expect.anything(),
    );
    expect(typeof result.current.refetch).toBe("function");
  });

  describe("polling (fake timers)", () => {
    beforeEach(() => vi.useFakeTimers());
    afterEach(() => vi.useRealTimers());

    it("re-polls every 3 s while pending_scopes > 0 (wiring of the interval)", async () => {
      fetchPassages.mockResolvedValue(fixturePairPassages({ pending_scopes: 1 }));
      renderHook(() => usePairPassages("a-id", "b-id", 30), { wrapper: wrapper() });
      await vi.advanceTimersByTimeAsync(0);
      expect(fetchPassages).toHaveBeenCalledTimes(1);
      await vi.advanceTimersByTimeAsync(3000);
      expect(fetchPassages).toHaveBeenCalledTimes(2);
      await vi.advanceTimersByTimeAsync(3000);
      expect(fetchPassages).toHaveBeenCalledTimes(3);
    });

    it("does not re-poll when nothing is pending", async () => {
      fetchPassages.mockResolvedValue(fixturePairPassages({ pending_scopes: 0 }));
      renderHook(() => usePairPassages("a-id", "b-id", 30), { wrapper: wrapper() });
      await vi.advanceTimersByTimeAsync(0);
      await vi.advanceTimersByTimeAsync(10000);
      expect(fetchPassages).toHaveBeenCalledTimes(1);
    });

    it("stops polling after a refetch returns pending_scopes 0", async () => {
      fetchPassages
        .mockResolvedValueOnce(fixturePairPassages({ pending_scopes: 1 }))
        .mockResolvedValue(fixturePairPassages({ pending_scopes: 0 }));
      renderHook(() => usePairPassages("a-id", "b-id", 30), { wrapper: wrapper() });
      await vi.advanceTimersByTimeAsync(0);
      await vi.advanceTimersByTimeAsync(3000);
      expect(fetchPassages).toHaveBeenCalledTimes(2);
      await vi.advanceTimersByTimeAsync(10000);
      expect(fetchPassages).toHaveBeenCalledTimes(2);
    });
  });

  it("a window change uses a new query key, so it fetches with the new window", async () => {
    fetchPassages.mockResolvedValue(fixturePairPassages());
    const { rerender } = renderHook(
      ({ w }: { w: 15 | 30 | 60 | 120 }) => usePairPassages("a-id", "b-id", w),
      { wrapper: wrapper(), initialProps: { w: 30 as 15 | 30 | 60 | 120 } },
    );
    await waitFor(() => expect(fetchPassages).toHaveBeenCalledTimes(1));
    rerender({ w: 120 });
    await waitFor(() => expect(fetchPassages).toHaveBeenCalledTimes(2));
    expect(fetchPassages).toHaveBeenLastCalledWith(
      expect.objectContaining({ window: 120, offset: 0 }),
      expect.anything(),
    );
  });
});

describe("useFartherVideos", () => {
  beforeEach(() => fetchFarther.mockReset());

  it("does not fetch until enabled", async () => {
    fetchFarther.mockResolvedValue({ items: [], offset: 0, total: 0, returned: 0, truncated: false });
    const { result, rerender } = renderHook(
      ({ on }) => useFartherVideos("a-id", "b-id", 30, on),
      { wrapper: wrapper(), initialProps: { on: false } },
    );
    expect(fetchFarther).not.toHaveBeenCalled();
    rerender({ on: true });
    await waitFor(() => expect(fetchFarther).toHaveBeenCalledTimes(1));
    expect(fetchFarther).toHaveBeenCalledWith(
      expect.objectContaining({ window: 30, limit: 20, offset: 0 }),
      expect.anything(),
    );
    await waitFor(() => expect(result.current.total).toBe(0));
  });
});
