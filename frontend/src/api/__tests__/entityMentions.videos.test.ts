/**
 * Tests for fetchEntityVideos include_unavailable handling.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { apiFetch } from "../config";
import { fetchEntityVideos } from "../entityMentions";

vi.mock("../config", async () => {
  const actual = await vi.importActual<typeof import("../config")>("../config");
  return { ...actual, apiFetch: vi.fn() };
});

const mockedApiFetch = vi.mocked(apiFetch);

beforeEach(() => {
  vi.clearAllMocks();
  mockedApiFetch.mockResolvedValue({ data: [], pagination: {} });
});

describe("fetchEntityVideos include_unavailable", () => {
  it("omits include_unavailable by default", async () => {
    await fetchEntityVideos("e1", { limit: 20 });
    expect(mockedApiFetch.mock.calls[0]?.[0]).toBe("/entities/e1/videos?limit=20");
  });

  it("omits include_unavailable when false", async () => {
    await fetchEntityVideos("e1", { includeUnavailable: false });
    expect(mockedApiFetch.mock.calls[0]?.[0]).toBe("/entities/e1/videos");
  });

  it("appends include_unavailable=true when set", async () => {
    await fetchEntityVideos("e1", { includeUnavailable: true });
    expect(mockedApiFetch.mock.calls[0]?.[0]).toBe(
      "/entities/e1/videos?include_unavailable=true"
    );
  });
});
