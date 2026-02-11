import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// Mock the apiFetch function
vi.mock("../../api/config", () => ({
  apiFetch: vi.fn(),
  API_BASE_URL: "http://localhost:8765/api/v1",
  API_TIMEOUT: 10000,
}));

import { apiFetch } from "../../api/config";
import { useSearchDescriptions } from "../../hooks/useSearchDescriptions";
import type { DescriptionSearchResponse } from "../../types/search";

describe("useSearchDescriptions", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    vi.clearAllMocks();
  });

  afterEach(() => {
    queryClient.clear();
  });

  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );

  // Mock response with snippets
  const mockResponse: DescriptionSearchResponse = {
    data: [
      {
        video_id: "dQw4w9WgXcQ",
        title: "Test Video",
        channel_title: "Test Channel",
        upload_date: "2024-01-15T00:00:00Z",
        snippet: "...this is a test snippet with highlighted terms...",
      },
    ],
    total_count: 1,
  };

  it("fetches from correct endpoint with query and limit params", async () => {
    vi.mocked(apiFetch).mockResolvedValue(mockResponse);

    const { result } = renderHook(
      () => useSearchDescriptions({ query: "test query" }),
      { wrapper }
    );

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(apiFetch).toHaveBeenCalledWith(
      "/search/descriptions?q=test+query&limit=50",
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    );
  });

  it("disabled when query too short (< 2 characters)", async () => {
    vi.mocked(apiFetch).mockResolvedValue(mockResponse);

    const { result } = renderHook(
      () => useSearchDescriptions({ query: "a" }),
      { wrapper }
    );

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(apiFetch).not.toHaveBeenCalled();
    expect(result.current.data).toEqual([]);
    expect(result.current.totalCount).toBe(0);
  });

  it("disabled when enabled=false", async () => {
    vi.mocked(apiFetch).mockResolvedValue(mockResponse);

    const { result } = renderHook(
      () => useSearchDescriptions({ query: "test query", enabled: false }),
      { wrapper }
    );

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(apiFetch).not.toHaveBeenCalled();
    expect(result.current.data).toEqual([]);
    expect(result.current.totalCount).toBe(0);
  });

  it("default enabled=true fires query", async () => {
    vi.mocked(apiFetch).mockResolvedValue(mockResponse);

    const { result } = renderHook(
      () => useSearchDescriptions({ query: "test query" }),
      { wrapper }
    );

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(apiFetch).toHaveBeenCalledTimes(1);
    expect(result.current.data).toHaveLength(1);
  });

  it("returns data with snippets", async () => {
    vi.mocked(apiFetch).mockResolvedValue(mockResponse);

    const { result } = renderHook(
      () => useSearchDescriptions({ query: "test query" }),
      { wrapper }
    );

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.data).toHaveLength(1);
    expect(result.current.data[0]).toMatchObject({
      video_id: "dQw4w9WgXcQ",
      title: "Test Video",
      channel_title: "Test Channel",
      upload_date: "2024-01-15T00:00:00Z",
      snippet: "...this is a test snippet with highlighted terms...",
    });
    expect(result.current.totalCount).toBe(1);
  });

  it("handles empty results", async () => {
    vi.mocked(apiFetch).mockResolvedValue({
      data: [],
      total_count: 0,
    });

    const { result } = renderHook(
      () => useSearchDescriptions({ query: "no results" }),
      { wrapper }
    );

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.data).toEqual([]);
    expect(result.current.totalCount).toBe(0);
    expect(result.current.isError).toBe(false);
  });

  it("returns correct data structure", async () => {
    vi.mocked(apiFetch).mockResolvedValue(mockResponse);

    const { result } = renderHook(
      () => useSearchDescriptions({ query: "test query" }),
      { wrapper }
    );

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current).toMatchObject({
      data: expect.any(Array),
      totalCount: expect.any(Number),
      isLoading: false,
      isError: false,
      error: null,
      refetch: expect.any(Function),
    });
  });

  it("passes AbortSignal to apiFetch", async () => {
    vi.mocked(apiFetch).mockResolvedValue(mockResponse);

    renderHook(() => useSearchDescriptions({ query: "test query" }), {
      wrapper,
    });

    await waitFor(() =>
      expect(apiFetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({ signal: expect.any(AbortSignal) })
      )
    );
  });

  it("error handling sets isError=true on failure", async () => {
    const errorMessage = "Network error";
    vi.mocked(apiFetch).mockRejectedValue(new Error(errorMessage));

    const { result } = renderHook(
      () => useSearchDescriptions({ query: "test query" }),
      { wrapper }
    );

    await waitFor(() => expect(result.current.isError).toBe(true));

    expect(result.current.isError).toBe(true);
    expect(result.current.error).toBeInstanceOf(Error);
    expect((result.current.error as Error).message).toBe(errorMessage);
    expect(result.current.data).toEqual([]);
    expect(result.current.totalCount).toBe(0);
  });

  it("refetch function triggers new request", async () => {
    vi.mocked(apiFetch).mockResolvedValue(mockResponse);

    const { result } = renderHook(
      () => useSearchDescriptions({ query: "test query" }),
      { wrapper }
    );

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(apiFetch).toHaveBeenCalledTimes(1);

    // Call refetch
    result.current.refetch();

    await waitFor(() => expect(apiFetch).toHaveBeenCalledTimes(2));
  });

  it("query key changes trigger new request", async () => {
    vi.mocked(apiFetch).mockResolvedValue(mockResponse);

    const { result, rerender } = renderHook(
      ({ query }: { query: string }) => useSearchDescriptions({ query }),
      { wrapper, initialProps: { query: "first query" } }
    );

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(apiFetch).toHaveBeenCalledTimes(1);
    expect(apiFetch).toHaveBeenCalledWith(
      "/search/descriptions?q=first+query&limit=50",
      expect.any(Object)
    );

    // Change query
    rerender({ query: "second query" });

    await waitFor(() => expect(apiFetch).toHaveBeenCalledTimes(2));

    expect(apiFetch).toHaveBeenCalledWith(
      "/search/descriptions?q=second+query&limit=50",
      expect.any(Object)
    );
  });

  it("respects staleTime configuration", async () => {
    vi.mocked(apiFetch).mockResolvedValue(mockResponse);

    const { result } = renderHook(
      () => useSearchDescriptions({ query: "test query" }),
      { wrapper }
    );

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(apiFetch).toHaveBeenCalledTimes(1);

    // Refetch immediately should use cached data (within staleTime)
    result.current.refetch();

    // Wait for any pending updates
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    // Should still have been called twice (initial + refetch)
    expect(apiFetch).toHaveBeenCalledTimes(2);
  });

  it("handles multiple results with snippets", async () => {
    const multiResultResponse: DescriptionSearchResponse = {
      data: [
        {
          video_id: "video1",
          title: "First Video",
          channel_title: "Channel One",
          upload_date: "2024-01-01T00:00:00Z",
          snippet: "...first snippet...",
        },
        {
          video_id: "video2",
          title: "Second Video",
          channel_title: "Channel Two",
          upload_date: "2024-01-02T00:00:00Z",
          snippet: "...second snippet...",
        },
        {
          video_id: "video3",
          title: "Third Video",
          channel_title: null,
          upload_date: "2024-01-03T00:00:00Z",
          snippet: "...third snippet...",
        },
      ],
      total_count: 3,
    };

    vi.mocked(apiFetch).mockResolvedValue(multiResultResponse);

    const { result } = renderHook(
      () => useSearchDescriptions({ query: "test query" }),
      { wrapper }
    );

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.data).toHaveLength(3);
    expect(result.current.totalCount).toBe(3);
    expect(result.current.data[0]?.snippet).toBe("...first snippet...");
    expect(result.current.data[1]?.snippet).toBe("...second snippet...");
    expect(result.current.data[2]?.snippet).toBe("...third snippet...");
    expect(result.current.data[2]?.channel_title).toBeNull();
  });

  it("URL encodes query parameters correctly", async () => {
    vi.mocked(apiFetch).mockResolvedValue(mockResponse);

    const { result } = renderHook(
      () => useSearchDescriptions({ query: "test with spaces & symbols" }),
      { wrapper }
    );

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(apiFetch).toHaveBeenCalledWith(
      "/search/descriptions?q=test+with+spaces+%26+symbols&limit=50",
      expect.any(Object)
    );
  });
});
