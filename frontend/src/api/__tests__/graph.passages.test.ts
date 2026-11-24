/**
 * Tests for the Feature 118 passages fetchers: exact URL and query string.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { apiFetch } from "../config";
import { fetchFartherVideos, fetchPairPassages } from "../graph";

vi.mock("../config", async () => {
  const actual = await vi.importActual<typeof import("../config")>("../config");
  return { ...actual, apiFetch: vi.fn() };
});

const mockedApiFetch = vi.mocked(apiFetch);

beforeEach(() => {
  vi.clearAllMocks();
  mockedApiFetch.mockResolvedValue({});
});

describe("fetchPairPassages", () => {
  it("sends a, b and window only when no paging is given", async () => {
    await fetchPairPassages({ a: "id-a", b: "id-b", window: 30 });
    expect(mockedApiFetch.mock.calls[0]?.[0]).toBe(
      "/graph/connect/passages?a=id-a&b=id-b&window=30",
    );
  });

  it("appends limit and offset when given", async () => {
    await fetchPairPassages({ a: "id-a", b: "id-b", window: 120, limit: 12, offset: 24 });
    expect(mockedApiFetch.mock.calls[0]?.[0]).toBe(
      "/graph/connect/passages?a=id-a&b=id-b&window=120&limit=12&offset=24",
    );
  });

  it("keeps offset 0 (falsy but present)", async () => {
    await fetchPairPassages({ a: "id-a", b: "id-b", window: 15, offset: 0 });
    expect(mockedApiFetch.mock.calls[0]?.[0]).toContain("&offset=0");
  });
});

describe("fetchFartherVideos", () => {
  it("targets the farther endpoint without paging", async () => {
    await fetchFartherVideos({ a: "id-a", b: "id-b", window: 60 });
    expect(mockedApiFetch.mock.calls[0]?.[0]).toBe(
      "/graph/connect/passages/farther?a=id-a&b=id-b&window=60",
    );
  });

  it("appends limit and offset when given", async () => {
    await fetchFartherVideos({ a: "id-a", b: "id-b", window: 60, limit: 20, offset: 40 });
    expect(mockedApiFetch.mock.calls[0]?.[0]).toBe(
      "/graph/connect/passages/farther?a=id-a&b=id-b&window=60&limit=20&offset=40",
    );
  });
});
