/**
 * Tests for useSegmentCorrectionHistory hook.
 *
 * Implements tests for T014: Correction history fetching with enabled/disabled
 * control, pagination, and empty history handling.
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

import { apiFetch } from "../../api/config";
import { useSegmentCorrectionHistory } from "../useSegmentCorrectionHistory";
import type { CorrectionHistoryResponse, CorrectionAuditRecord } from "../../types/corrections";

// Mock the apiFetch function
vi.mock("../../api/config", () => ({
  apiFetch: vi.fn(),
}));

const mockedApiFetch = vi.mocked(apiFetch);

// --- Test Fixtures ---

const VIDEO_ID = "test-video-id";
const LANGUAGE_CODE = "en";
const SEGMENT_ID = 42;

function makeCorrectionRecord(
  overrides: Partial<CorrectionAuditRecord> = {}
): CorrectionAuditRecord {
  return {
    id: "uuid-record-1",
    video_id: VIDEO_ID,
    language_code: LANGUAGE_CODE,
    segment_id: SEGMENT_ID,
    correction_type: "asr_error",
    original_text: "Original text",
    corrected_text: "Corrected text",
    correction_note: null,
    corrected_by_user_id: null,
    corrected_at: "2024-01-01T12:00:00Z",
    version_number: 1,
    ...overrides,
  };
}

function makeHistoryResponse(
  records: CorrectionAuditRecord[],
  paginationOverrides: Partial<CorrectionHistoryResponse["pagination"]> = {}
): CorrectionHistoryResponse {
  return {
    data: records,
    pagination: {
      total: records.length,
      offset: 0,
      limit: 50,
      has_more: false,
      ...paginationOverrides,
    },
  };
}

// --- Test Helpers ---

function createWrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return React.createElement(
      QueryClientProvider,
      { client: queryClient },
      children
    );
  };
}

function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
}

// --- Tests ---

describe("useSegmentCorrectionHistory", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createQueryClient();
    vi.clearAllMocks();
  });

  it("fetches correction history when enabled is true", async () => {
    const records = [
      makeCorrectionRecord({ id: "record-1", version_number: 1 }),
      makeCorrectionRecord({ id: "record-2", version_number: 2, correction_type: "revert" }),
    ];
    const historyResponse = makeHistoryResponse(records);
    mockedApiFetch.mockResolvedValueOnce(historyResponse);

    const { result } = renderHook(
      () =>
        useSegmentCorrectionHistory(VIDEO_ID, LANGUAGE_CODE, SEGMENT_ID, {
          enabled: true,
        }),
      { wrapper: createWrapper(queryClient) }
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toEqual(historyResponse);
    expect(result.current.data?.data).toHaveLength(2);
    expect(mockedApiFetch).toHaveBeenCalledTimes(1);
  });

  it("does not fetch when enabled is false", async () => {
    const { result } = renderHook(
      () =>
        useSegmentCorrectionHistory(VIDEO_ID, LANGUAGE_CODE, SEGMENT_ID, {
          enabled: false,
        }),
      { wrapper: createWrapper(queryClient) }
    );

    // Query should remain in the 'pending' state (not fetched)
    expect(result.current.isPending).toBe(true);
    expect(result.current.isFetching).toBe(false);
    expect(mockedApiFetch).not.toHaveBeenCalled();
  });

  it("returns paginated data with correct pagination metadata", async () => {
    const records = Array.from({ length: 3 }, (_, i) =>
      makeCorrectionRecord({
        id: `record-${i + 1}`,
        version_number: i + 1,
      })
    );
    const historyResponse = makeHistoryResponse(records, {
      total: 10,
      offset: 0,
      limit: 3,
      has_more: true,
    });
    mockedApiFetch.mockResolvedValueOnce(historyResponse);

    const { result } = renderHook(
      () =>
        useSegmentCorrectionHistory(VIDEO_ID, LANGUAGE_CODE, SEGMENT_ID, {
          enabled: true,
        }),
      { wrapper: createWrapper(queryClient) }
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data?.pagination.total).toBe(10);
    expect(result.current.data?.pagination.has_more).toBe(true);
    expect(result.current.data?.pagination.limit).toBe(3);
    expect(result.current.data?.data).toHaveLength(3);
  });

  it("handles empty correction history gracefully", async () => {
    const emptyResponse = makeHistoryResponse([]);
    mockedApiFetch.mockResolvedValueOnce(emptyResponse);

    const { result } = renderHook(
      () =>
        useSegmentCorrectionHistory(VIDEO_ID, LANGUAGE_CODE, SEGMENT_ID, {
          enabled: true,
        }),
      { wrapper: createWrapper(queryClient) }
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data?.data).toHaveLength(0);
    expect(result.current.data?.pagination.total).toBe(0);
    expect(result.current.data?.pagination.has_more).toBe(false);
  });

  it("constructs the API URL with correct query parameters", async () => {
    mockedApiFetch.mockResolvedValueOnce(makeHistoryResponse([]));

    renderHook(
      () =>
        useSegmentCorrectionHistory(VIDEO_ID, LANGUAGE_CODE, SEGMENT_ID, {
          enabled: true,
          offset: 0,
        }),
      { wrapper: createWrapper(queryClient) }
    );

    await waitFor(() => expect(mockedApiFetch).toHaveBeenCalledTimes(1));

    const calledEndpoint = mockedApiFetch.mock.calls[0]?.[0] as string;
    expect(calledEndpoint).toContain(`/videos/${VIDEO_ID}/transcript/segments/${SEGMENT_ID}/corrections`);
    expect(calledEndpoint).toContain("language_code=en");
    expect(calledEndpoint).toContain("limit=50");
    expect(calledEndpoint).toContain("offset=0");
  });

  it("uses a different cache key for different offset values", async () => {
    // First request at offset 0
    const page1 = makeHistoryResponse(
      [makeCorrectionRecord({ id: "r1" })],
      { offset: 0, total: 2, limit: 1, has_more: true }
    );
    // Second request at offset 1
    const page2 = makeHistoryResponse(
      [makeCorrectionRecord({ id: "r2", version_number: 2 })],
      { offset: 1, total: 2, limit: 1, has_more: false }
    );

    mockedApiFetch
      .mockResolvedValueOnce(page1)
      .mockResolvedValueOnce(page2);

    const { result: result1 } = renderHook(
      () =>
        useSegmentCorrectionHistory(VIDEO_ID, LANGUAGE_CODE, SEGMENT_ID, {
          enabled: true,
          offset: 0,
        }),
      { wrapper: createWrapper(queryClient) }
    );

    const { result: result2 } = renderHook(
      () =>
        useSegmentCorrectionHistory(VIDEO_ID, LANGUAGE_CODE, SEGMENT_ID, {
          enabled: true,
          offset: 1,
        }),
      { wrapper: createWrapper(queryClient) }
    );

    await waitFor(() => {
      expect(result1.current.isSuccess).toBe(true);
      expect(result2.current.isSuccess).toBe(true);
    });

    // Both results should have different data due to different cache keys
    expect(result1.current.data?.data[0]?.id).toBe("r1");
    expect(result2.current.data?.data[0]?.id).toBe("r2");
  });
});
