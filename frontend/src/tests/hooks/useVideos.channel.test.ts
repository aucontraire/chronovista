/**
 * useVideos — channelId parameter (Feature 070, US2).
 *
 * `ChannelDetailPage` reuses `useVideos` (rather than `useChannelVideos`) to
 * fetch the AND-intersection of pinned entities scoped to one channel, so
 * `channel_id` must reach the request URL AND the query key — the same
 * stale-until-reload trap the entity params guard against in
 * `useVideos.entity.test.ts`.
 *
 * @module tests/hooks/useVideos.channel
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

import { useVideos } from "../../hooks/useVideos";
import type { VideoListResponse } from "../../types/video";
import * as apiConfig from "../../api/config";

vi.mock("../../api/config", () => ({
  apiFetch: vi.fn(),
  API_BASE_URL: "http://localhost:8765/api/v1",
  API_TIMEOUT: 10000,
}));

const mockResponse: VideoListResponse = {
  data: [],
  pagination: { total: 0, limit: 25, offset: 0, has_more: false },
};

function createWrapper(queryClient: QueryClient) {
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children);
}

function newClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

/** Last URL passed to apiFetch. */
function lastUrl(): string {
  const calls = vi.mocked(apiConfig.apiFetch).mock.calls;
  return String(calls[calls.length - 1]?.[0] ?? "");
}

describe("useVideos — channelId parameter", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(apiConfig.apiFetch).mockResolvedValue(mockResponse);
  });

  it("sends channel_id when provided", async () => {
    const queryClient = newClient();
    renderHook(() => useVideos({ channelId: "UC-channel-1", entityIds: ["e1"] }), {
      wrapper: createWrapper(queryClient),
    });

    await waitFor(() => expect(apiConfig.apiFetch).toHaveBeenCalled());
    const params = new URLSearchParams(lastUrl().split("?")[1]);
    expect(params.get("channel_id")).toBe("UC-channel-1");
  });

  it("omits channel_id entirely when not provided", async () => {
    const queryClient = newClient();
    renderHook(() => useVideos({ entityIds: ["e1"] }), {
      wrapper: createWrapper(queryClient),
    });

    await waitFor(() => expect(apiConfig.apiFetch).toHaveBeenCalled());
    const params = new URLSearchParams(lastUrl().split("?")[1]);
    expect(params.has("channel_id")).toBe(false);
  });

  it("refetches when channel_id changes (cache key covers it)", async () => {
    const queryClient = newClient();
    const wrapper = createWrapper(queryClient);

    const { rerender } = renderHook(
      (props: Parameters<typeof useVideos>[0]) => useVideos(props),
      { wrapper, initialProps: { channelId: "UC-1", entityIds: ["e1"] } }
    );
    await waitFor(() => expect(apiConfig.apiFetch).toHaveBeenCalledTimes(1));

    rerender({ channelId: "UC-2", entityIds: ["e1"] });
    await waitFor(() => expect(apiConfig.apiFetch).toHaveBeenCalledTimes(2));

    const params = new URLSearchParams(lastUrl().split("?")[1]);
    expect(params.get("channel_id")).toBe("UC-2");
  });

  it("does NOT refetch when nothing relevant changed", async () => {
    const queryClient = newClient();
    const wrapper = createWrapper(queryClient);

    const { rerender } = renderHook(
      (props: Parameters<typeof useVideos>[0]) => useVideos(props),
      { wrapper, initialProps: { channelId: "UC-1", entityIds: ["e1"] } }
    );
    await waitFor(() => expect(apiConfig.apiFetch).toHaveBeenCalledTimes(1));

    rerender({ channelId: "UC-1", entityIds: ["e1"] });
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(apiConfig.apiFetch).toHaveBeenCalledTimes(1);
  });

  it("carries include_unavailable=true alongside channel_id + entity_id (pinned-request shape)", async () => {
    const queryClient = newClient();
    renderHook(
      () =>
        useVideos({
          channelId: "UC-channel-1",
          entityIds: ["e1", "e2"],
          includeUnavailable: true,
        }),
      { wrapper: createWrapper(queryClient) }
    );

    await waitFor(() => expect(apiConfig.apiFetch).toHaveBeenCalled());
    const params = new URLSearchParams(lastUrl().split("?")[1]);
    expect(params.get("channel_id")).toBe("UC-channel-1");
    expect(params.getAll("entity_id")).toEqual(["e1", "e2"]);
    expect(params.get("include_unavailable")).toBe("true");
  });
});
