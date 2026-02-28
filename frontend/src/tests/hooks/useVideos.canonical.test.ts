/**
 * Unit tests for useVideos hook — canonical tag support (US3/T017).
 *
 * Tests that the canonicalTags option correctly:
 * - Appends `canonical_tag` query params to the API URL
 * - Includes canonicalTags in the TanStack Query key for cache invalidation
 * - Omits the param entirely when canonicalTags is empty
 * - Produces one `canonical_tag` param per entry (multi-value support)
 *
 * @module tests/hooks/useVideos.canonical
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

import { useVideos } from "../../hooks/useVideos";
import type { VideoListResponse } from "../../types/video";
import * as apiConfig from "../../api/config";

// Mock the API fetch module
vi.mock("../../api/config", () => ({
  apiFetch: vi.fn(),
  API_BASE_URL: "http://localhost:8765/api/v1",
  API_TIMEOUT: 10000,
}));

// ---------------------------------------------------------------------------
// Minimal mock response shared across tests
// ---------------------------------------------------------------------------
const mockVideoListResponse: VideoListResponse = {
  data: [
    {
      video_id: "dQw4w9WgXcQ",
      title: "Test Video",
      channel_id: "UC1234567890123456789012",
      channel_title: "Test Channel",
      upload_date: "2024-01-15T10:30:00Z",
      duration: 240,
      view_count: 1000,
      transcript_summary: { count: 1, languages: ["en"], has_manual: false },
      tags: [],
      category_id: "10",
      category_name: "Music",
      topics: [],
      availability_status: "available",
      recovered_at: null,
      recovery_source: null,
    },
  ],
  pagination: { total: 1, limit: 25, offset: 0, has_more: false },
};

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------

function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false, // disable retries so errors surface immediately
      },
    },
  });
}

function createWrapper(queryClient: QueryClient) {
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("useVideos — canonicalTags option (US3/T017)", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createQueryClient();
    vi.clearAllMocks();
  });

  // -------------------------------------------------------------------------
  // URL building
  // -------------------------------------------------------------------------

  describe("URL query parameter construction", () => {
    it("appends canonical_tag query param for a single canonical tag", async () => {
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce(mockVideoListResponse);

      const { result } = renderHook(
        () => useVideos({ canonicalTags: ["javascript"] }),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => expect(result.current.isLoading).toBe(false));

      // apiFetch is called with (url, { signal })
      const firstCallArgs = vi.mocked(apiConfig.apiFetch).mock.calls[0];
      expect(firstCallArgs).toBeDefined();
      const url = firstCallArgs![0] as string;
      expect(url).toContain("canonical_tag=javascript");
    });

    it("appends multiple canonical_tag params for multiple canonical tags", async () => {
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce(mockVideoListResponse);

      const { result } = renderHook(
        () => useVideos({ canonicalTags: ["javascript", "typescript", "react"] }),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => expect(result.current.isLoading).toBe(false));

      const firstCallArgs = vi.mocked(apiConfig.apiFetch).mock.calls[0];
      expect(firstCallArgs).toBeDefined();
      const url = firstCallArgs![0] as string;

      // Each tag should appear as a separate canonical_tag= param
      const params = new URLSearchParams(url.split("?")[1] ?? "");
      const canonicalTagValues = params.getAll("canonical_tag");
      expect(canonicalTagValues).toHaveLength(3);
      expect(canonicalTagValues).toContain("javascript");
      expect(canonicalTagValues).toContain("typescript");
      expect(canonicalTagValues).toContain("react");
    });

    it("omits canonical_tag param entirely when canonicalTags is an empty array", async () => {
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce(mockVideoListResponse);

      const { result } = renderHook(
        () => useVideos({ canonicalTags: [] }),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => expect(result.current.isLoading).toBe(false));

      const firstCallArgs = vi.mocked(apiConfig.apiFetch).mock.calls[0];
      expect(firstCallArgs).toBeDefined();
      const url = firstCallArgs![0] as string;
      expect(url).not.toContain("canonical_tag");
    });

    it("omits canonical_tag param when canonicalTags is not provided (default)", async () => {
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce(mockVideoListResponse);

      const { result } = renderHook(
        () => useVideos({}),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => expect(result.current.isLoading).toBe(false));

      const firstCallArgs = vi.mocked(apiConfig.apiFetch).mock.calls[0];
      expect(firstCallArgs).toBeDefined();
      const url = firstCallArgs![0] as string;
      expect(url).not.toContain("canonical_tag");
    });

    it("URL-encodes canonical tag values with special characters", async () => {
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce(mockVideoListResponse);

      const { result } = renderHook(
        () => useVideos({ canonicalTags: ["c++", "node.js"] }),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => expect(result.current.isLoading).toBe(false));

      const firstCallArgs = vi.mocked(apiConfig.apiFetch).mock.calls[0];
      expect(firstCallArgs).toBeDefined();
      const url = firstCallArgs![0] as string;

      // URLSearchParams encodes + as %2B and . as literal
      expect(url).toContain("canonical_tag=c%2B%2B");
      expect(url).toContain("canonical_tag=node.js");
    });
  });

  // -------------------------------------------------------------------------
  // Query key (cache invalidation)
  // -------------------------------------------------------------------------

  describe("query key includes canonicalTags for cache invalidation", () => {
    it("different canonicalTags values produce separate cache entries", async () => {
      // First render: canonicalTags = ["javascript"]
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce(mockVideoListResponse);

      const { result: result1 } = renderHook(
        () => useVideos({ canonicalTags: ["javascript"] }),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => expect(result1.current.isLoading).toBe(false));

      // Second render with different tag: should trigger a second API call
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce(mockVideoListResponse);

      const { result: result2 } = renderHook(
        () => useVideos({ canonicalTags: ["python"] }),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => expect(result2.current.isLoading).toBe(false));

      // Two distinct API calls should have been made
      expect(vi.mocked(apiConfig.apiFetch)).toHaveBeenCalledTimes(2);

      const urls = vi.mocked(apiConfig.apiFetch).mock.calls.map(
        (args) => args[0] as string
      );
      expect(urls[0]).toContain("canonical_tag=javascript");
      expect(urls[1]).toContain("canonical_tag=python");
    });

    it("same canonicalTags values reuse the cached result (single API call)", async () => {
      vi.mocked(apiConfig.apiFetch).mockResolvedValue(mockVideoListResponse);

      // First render
      const { result: result1 } = renderHook(
        () => useVideos({ canonicalTags: ["javascript"] }),
        { wrapper: createWrapper(queryClient) }
      );
      await waitFor(() => expect(result1.current.isLoading).toBe(false));

      // Second render with identical canonicalTags (same client)
      const { result: result2 } = renderHook(
        () => useVideos({ canonicalTags: ["javascript"] }),
        { wrapper: createWrapper(queryClient) }
      );
      await waitFor(() => expect(result2.current.isLoading).toBe(false));

      // Cache should be hit; apiFetch called only once
      expect(vi.mocked(apiConfig.apiFetch)).toHaveBeenCalledTimes(1);
    });
  });

  // -------------------------------------------------------------------------
  // Backward compatibility: legacy `tags` param
  // -------------------------------------------------------------------------

  describe("backward compatibility — legacy tags param", () => {
    it("appends tag param for legacy tags while also supporting canonicalTags", async () => {
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce(mockVideoListResponse);

      const { result } = renderHook(
        () =>
          useVideos({
            tags: ["legacy-tag"],
            canonicalTags: ["canonical-form"],
          }),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => expect(result.current.isLoading).toBe(false));

      const firstCallArgs = vi.mocked(apiConfig.apiFetch).mock.calls[0];
      expect(firstCallArgs).toBeDefined();
      const url = firstCallArgs![0] as string;

      expect(url).toContain("tag=legacy-tag");
      expect(url).toContain("canonical_tag=canonical-form");
    });

    it("uses separate cache entries when tags differ from canonicalTags", async () => {
      vi.mocked(apiConfig.apiFetch).mockResolvedValue(mockVideoListResponse);

      const { result: r1 } = renderHook(
        () => useVideos({ tags: ["raw"], canonicalTags: [] }),
        { wrapper: createWrapper(queryClient) }
      );
      await waitFor(() => expect(r1.current.isLoading).toBe(false));

      const { result: r2 } = renderHook(
        () => useVideos({ tags: [], canonicalTags: ["raw"] }),
        { wrapper: createWrapper(queryClient) }
      );
      await waitFor(() => expect(r2.current.isLoading).toBe(false));

      // tags and canonicalTags are distinct query key dimensions
      expect(vi.mocked(apiConfig.apiFetch)).toHaveBeenCalledTimes(2);
    });
  });

  // -------------------------------------------------------------------------
  // Return values
  // -------------------------------------------------------------------------

  describe("return values", () => {
    it("returns videos data when canonicalTags filter is applied", async () => {
      vi.mocked(apiConfig.apiFetch).mockResolvedValueOnce(mockVideoListResponse);

      const { result } = renderHook(
        () => useVideos({ canonicalTags: ["music"] }),
        { wrapper: createWrapper(queryClient) }
      );

      await waitFor(() => expect(result.current.isLoading).toBe(false));

      expect(result.current.videos).toHaveLength(1);
      expect(result.current.videos[0]?.video_id).toBe("dQw4w9WgXcQ");
      expect(result.current.total).toBe(1);
      expect(result.current.isError).toBe(false);
    });
  });
});
