/**
 * Tests for useRevertSegment hook.
 *
 * Implements tests for T013: Correction revert with server-confirmed cache
 * patching (no optimistic update) and error handling.
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import {
  QueryClient,
  QueryClientProvider,
  InfiniteData,
} from "@tanstack/react-query";
import React from "react";

import { apiFetch } from "../../api/config";
import { useRevertSegment } from "../useRevertSegment";
import { segmentsQueryKey } from "../useTranscriptSegments";
import type { SegmentListResponse, TranscriptSegment } from "../../types/transcript";
import type { CorrectionRevertResponse } from "../../types/corrections";

// Mock the apiFetch function
vi.mock("../../api/config", () => ({
  apiFetch: vi.fn(),
}));

const mockedApiFetch = vi.mocked(apiFetch);

// --- Test Fixtures ---

const VIDEO_ID = "test-video-id";
const LANGUAGE_CODE = "en";

function makeSegment(overrides: Partial<TranscriptSegment> = {}): TranscriptSegment {
  return {
    id: 1,
    text: "Corrected text",
    start_time: 0,
    end_time: 5,
    duration: 5,
    has_correction: true,
    corrected_at: "2024-01-01T10:00:00Z",
    correction_count: 2,
    ...overrides,
  };
}

function makeSegmentListResponse(
  segments: TranscriptSegment[]
): SegmentListResponse {
  return {
    data: segments,
    pagination: {
      total: segments.length,
      offset: 0,
      limit: 50,
      has_more: false,
    },
  };
}

function makeInfiniteData(
  pages: SegmentListResponse[]
): InfiniteData<SegmentListResponse> {
  return {
    pages,
    pageParams: pages.map((_, i) => ({ offset: i * 50, limit: 50 })),
  };
}

function makeRevertApiResponse(
  overrides: Partial<CorrectionRevertResponse> = {}
): { data: CorrectionRevertResponse } {
  return {
    data: {
      correction: {
        id: "uuid-revert-1",
        video_id: VIDEO_ID,
        language_code: LANGUAGE_CODE,
        segment_id: 1,
        correction_type: "revert",
        original_text: "Corrected text",
        corrected_text: "Original text",
        correction_note: null,
        corrected_by_user_id: null,
        corrected_at: "2024-01-01T12:00:00Z",
        version_number: 2,
      },
      segment_state: {
        has_correction: false,
        effective_text: "Original text",
      },
      ...overrides,
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

describe("useRevertSegment", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createQueryClient();
    vi.clearAllMocks();
  });

  it("patches cache with server-confirmed segment state on successful revert", async () => {
    const segment = makeSegment({ id: 1, text: "Corrected text", has_correction: true });
    const initialData = makeInfiniteData([makeSegmentListResponse([segment])]);
    const qKey = segmentsQueryKey(VIDEO_ID, LANGUAGE_CODE);

    queryClient.setQueryData(qKey, initialData);

    const apiResponse = makeRevertApiResponse();
    mockedApiFetch.mockResolvedValueOnce(apiResponse);

    const { result } = renderHook(
      () => useRevertSegment(VIDEO_ID, LANGUAGE_CODE),
      { wrapper: createWrapper(queryClient) }
    );

    await act(async () => {
      result.current.mutate({ segmentId: 1 });
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const cached = queryClient.getQueryData<InfiniteData<SegmentListResponse>>(qKey);
    const updatedSegment = cached?.pages[0]?.data[0];

    expect(updatedSegment?.has_correction).toBe(false);
    expect(updatedSegment?.text).toBe("Original text");
  });

  it("sets corrected_at to null and correction_count to 0 when has_correction is false after revert", async () => {
    const segment = makeSegment({
      id: 1,
      has_correction: true,
      correction_count: 1,
      corrected_at: "2024-01-01T10:00:00Z",
    });
    const initialData = makeInfiniteData([makeSegmentListResponse([segment])]);
    const qKey = segmentsQueryKey(VIDEO_ID, LANGUAGE_CODE);

    queryClient.setQueryData(qKey, initialData);

    // Server says no more corrections remain
    const apiResponse = makeRevertApiResponse({
      segment_state: { has_correction: false, effective_text: "Original text" },
    });
    mockedApiFetch.mockResolvedValueOnce(apiResponse);

    const { result } = renderHook(
      () => useRevertSegment(VIDEO_ID, LANGUAGE_CODE),
      { wrapper: createWrapper(queryClient) }
    );

    await act(async () => {
      result.current.mutate({ segmentId: 1 });
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const cached = queryClient.getQueryData<InfiniteData<SegmentListResponse>>(qKey);
    const updatedSegment = cached?.pages[0]?.data[0];

    expect(updatedSegment?.has_correction).toBe(false);
    expect(updatedSegment?.corrected_at).toBeNull();
    expect(updatedSegment?.correction_count).toBe(0);
  });

  it("sets corrected_at from correction record and decrements correction_count when has_correction remains true", async () => {
    const segment = makeSegment({
      id: 1,
      has_correction: true,
      correction_count: 3,
      corrected_at: "2024-01-01T10:00:00Z",
    });
    const initialData = makeInfiniteData([makeSegmentListResponse([segment])]);
    const qKey = segmentsQueryKey(VIDEO_ID, LANGUAGE_CODE);

    queryClient.setQueryData(qKey, initialData);

    // Server says a prior correction still exists after partial revert
    const partialRevertTimestamp = "2023-12-15T08:30:00Z";
    const apiResponse = makeRevertApiResponse({
      correction: {
        id: "uuid-revert-2",
        video_id: VIDEO_ID,
        language_code: LANGUAGE_CODE,
        segment_id: 1,
        correction_type: "revert",
        original_text: "Latest correction",
        corrected_text: "Earlier correction",
        correction_note: null,
        corrected_by_user_id: null,
        corrected_at: partialRevertTimestamp,
        version_number: 3,
      },
      segment_state: {
        has_correction: true,
        effective_text: "Earlier correction",
      },
    });
    mockedApiFetch.mockResolvedValueOnce(apiResponse);

    const { result } = renderHook(
      () => useRevertSegment(VIDEO_ID, LANGUAGE_CODE),
      { wrapper: createWrapper(queryClient) }
    );

    await act(async () => {
      result.current.mutate({ segmentId: 1 });
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const cached = queryClient.getQueryData<InfiniteData<SegmentListResponse>>(qKey);
    const updatedSegment = cached?.pages[0]?.data[0];

    expect(updatedSegment?.has_correction).toBe(true);
    expect(updatedSegment?.text).toBe("Earlier correction");
    expect(updatedSegment?.corrected_at).toBe(partialRevertTimestamp);
    expect(updatedSegment?.correction_count).toBe(2); // Math.max(0, 3 - 1)
  });

  it("does not modify cache before server responds (no optimistic update)", async () => {
    const segment = makeSegment({
      id: 1,
      text: "Corrected text",
      has_correction: true,
      correction_count: 1,
    });
    const initialData = makeInfiniteData([makeSegmentListResponse([segment])]);
    const qKey = segmentsQueryKey(VIDEO_ID, LANGUAGE_CODE);

    queryClient.setQueryData(qKey, initialData);

    // Delay the API response so we can inspect mid-flight state
    let resolveApiFetch!: (value: unknown) => void;
    const pendingApiFetch = new Promise((resolve) => {
      resolveApiFetch = resolve;
    });
    mockedApiFetch.mockReturnValueOnce(pendingApiFetch as Promise<never>);

    const { result } = renderHook(
      () => useRevertSegment(VIDEO_ID, LANGUAGE_CODE),
      { wrapper: createWrapper(queryClient) }
    );

    act(() => {
      result.current.mutate({ segmentId: 1 });
    });

    await waitFor(() => expect(result.current.isPending).toBe(true));

    // While mutation is pending, cache should be unchanged
    const cached = queryClient.getQueryData<InfiniteData<SegmentListResponse>>(qKey);
    const segmentDuringMutation = cached?.pages[0]?.data[0];

    expect(segmentDuringMutation?.text).toBe("Corrected text");
    expect(segmentDuringMutation?.has_correction).toBe(true);
    expect(segmentDuringMutation?.correction_count).toBe(1);

    // Resolve the API call to clean up
    resolveApiFetch(makeRevertApiResponse());
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
  });

  it("calls invalidateQueries on error", async () => {
    const qKey = segmentsQueryKey(VIDEO_ID, LANGUAGE_CODE);
    queryClient.setQueryData(qKey, makeInfiniteData([makeSegmentListResponse([])]));

    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    mockedApiFetch.mockRejectedValueOnce(new Error("Revert failed"));

    const { result } = renderHook(
      () => useRevertSegment(VIDEO_ID, LANGUAGE_CODE),
      { wrapper: createWrapper(queryClient) }
    );

    await act(async () => {
      result.current.mutate({ segmentId: 1 });
    });

    await waitFor(() => expect(result.current.isError).toBe(true));

    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: qKey,
    });

    invalidateSpy.mockRestore();
  });
});
