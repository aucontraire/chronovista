/**
 * Tests for ChannelDetailPage pinned-entity video filtering (Feature 070, US2).
 *
 * Coverage:
 * - No pins in the URL: the channel video list uses useChannelVideos, unchanged (byte-for-byte US1 behavior)
 * - Pins in the URL: the channel video list switches to useVideos, scoped to the channel + pinned entities
 * - The pinned request MUST carry include_unavailable=true (FR-007 count/result agreement)
 * - Pinning a second entity narrows to the AND set (both entity_id values reach useVideos)
 * - Composition (FR-005): an active sort in the URL is preserved, not reset, when pins are applied
 * - Empty AND-intersection (US2 scenario 4): shows an empty state with a clear unpin affordance
 */

import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter, Routes, Route, useBlocker } from "react-router-dom";
import { QueryClientProvider, QueryClient } from "@tanstack/react-query";
import { describe, it, expect, vi, beforeEach } from "vitest";
import type { Mock } from "vitest";

import { ChannelDetailPage } from "../ChannelDetailPage";
import type { ChannelDetail } from "../../types/channel";

vi.mock("../../api/config", () => ({
  apiFetch: vi.fn(),
  API_BASE_URL: "http://localhost:8765/api/v1",
  API_TIMEOUT: 10000,
  RECOVERY_TIMEOUT: 660000,
  isApiError: vi.fn(),
}));

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return {
    ...actual,
    useBlocker: vi.fn(() => ({
      state: "unblocked" as const,
      reset: undefined,
      proceed: undefined,
      location: undefined,
    })),
  };
});

vi.mock("../../hooks/useChannelDetail", () => ({
  useChannelDetail: vi.fn(),
}));

vi.mock("../../hooks/useChannelVideos", () => ({
  useChannelVideos: vi.fn(),
}));

vi.mock("../../hooks/useVideos", () => ({
  useVideos: vi.fn(),
}));

vi.mock("../../hooks/useChannelEntities", () => ({
  useChannelEntities: vi.fn(() => ({
    data: { channel_id: "test-channel-1", total_entities: 0, items: [] },
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
  })),
}));

vi.mock("../../components/VideoGrid", () => ({
  VideoGrid: ({ videos }: { videos: unknown[] }) => (
    <div data-testid="video-grid">{videos.length} videos rendered</div>
  ),
}));

vi.mock("../../components/LoadingState", () => ({
  LoadingState: () => <div data-testid="loading-state" />,
}));

vi.mock("../../stores/recoveryStore", () => {
  const mockStore = {
    sessions: new Map(),
    startRecovery: vi.fn(),
    updatePhase: vi.fn(),
    setResult: vi.fn(),
    setError: vi.fn(),
    setAbortController: vi.fn(),
    cancelRecovery: vi.fn(),
    getActiveSession: vi.fn(() => undefined),
    getActiveSessions: vi.fn(() => []),
    hasActiveRecovery: vi.fn(() => false),
  };
  const useRecoveryStore = Object.assign(
    vi.fn((selector?: (s: typeof mockStore) => unknown) =>
      selector ? selector(mockStore) : mockStore
    ),
    { getState: vi.fn().mockReturnValue(mockStore), setState: vi.fn(() => {}) }
  );
  return { useRecoveryStore };
});

import { useChannelDetail } from "../../hooks/useChannelDetail";
import { useChannelVideos } from "../../hooks/useChannelVideos";
import { useVideos } from "../../hooks/useVideos";

const CHANNEL_ID = "test-channel-1";

const mockChannel: ChannelDetail = {
  channel_id: CHANNEL_ID,
  title: "Test Channel",
  description: "A test channel",
  thumbnail_url: null,
  subscriber_count: 100,
  video_count: 10,
  country: "US",
  is_subscribed: true,
  availability_status: "available",
  recovered_at: null,
  recovery_source: null,
  custom_url: null,
  default_language: null,
  created_at: "2024-01-01T00:00:00Z",
  updated_at: "2024-01-01T00:00:00Z",
};

function baseVideosResult(overrides: Record<string, unknown> = {}) {
  return {
    videos: [],
    total: 0,
    loadedCount: 0,
    isLoading: false,
    isError: false,
    error: null,
    hasNextPage: false,
    isFetchingNextPage: false,
    fetchNextPage: vi.fn(),
    retry: vi.fn(),
    loadMoreRef: { current: null },
    ...overrides,
  };
}

function renderPage(initialEntry: string) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });

  vi.mocked(useChannelDetail).mockReturnValue({
    data: mockChannel,
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
  } as unknown as ReturnType<typeof useChannelDetail>);

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/channels/:channelId" element={<ChannelDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("ChannelDetailPage — pinned entity video filtering (US2)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useBlocker).mockReturnValue({
      state: "unblocked" as const,
      reset: undefined,
      proceed: undefined,
      location: undefined,
    });
  });

  describe("No pins present", () => {
    it("uses useChannelVideos and renders its videos, unchanged from US1", () => {
      (useChannelVideos as Mock).mockReturnValue(
        baseVideosResult({ videos: [{ video_id: "v1" }], total: 1, loadedCount: 1 })
      );
      (useVideos as Mock).mockReturnValue(baseVideosResult());

      renderPage(`/channels/${CHANNEL_ID}`);

      expect(screen.getByTestId("video-grid")).toHaveTextContent("1 videos rendered");
      // useVideos was called (unconditionally, per Rules of Hooks) but disabled.
      expect(useVideos).toHaveBeenCalledWith(expect.objectContaining({ enabled: false }));
      expect(useChannelVideos).toHaveBeenCalledWith(
        CHANNEL_ID,
        expect.objectContaining({ enabled: true })
      );
    });
  });

  describe("Pins present", () => {
    it("switches to useVideos scoped to the channel + pinned entity, with include_unavailable=true", () => {
      (useChannelVideos as Mock).mockReturnValue(baseVideosResult());
      (useVideos as Mock).mockReturnValue(
        baseVideosResult({ videos: [{ video_id: "v2" }], total: 1, loadedCount: 1 })
      );

      renderPage(`/channels/${CHANNEL_ID}?entity_id=e1`);

      expect(screen.getByTestId("video-grid")).toHaveTextContent("1 videos rendered");
      expect(useVideos).toHaveBeenCalledWith(
        expect.objectContaining({
          channelId: CHANNEL_ID,
          entityIds: ["e1"],
          includeUnavailable: true,
          enabled: true,
        })
      );
      expect(useChannelVideos).toHaveBeenCalledWith(
        CHANNEL_ID,
        expect.objectContaining({ enabled: false })
      );
    });

    it("narrows to the AND set: both pinned entity ids reach useVideos", () => {
      (useChannelVideos as Mock).mockReturnValue(baseVideosResult());
      (useVideos as Mock).mockReturnValue(baseVideosResult());

      renderPage(`/channels/${CHANNEL_ID}?entity_id=e1&entity_id=e2`);

      expect(useVideos).toHaveBeenCalledWith(
        expect.objectContaining({
          entityIds: ["e1", "e2"],
          includeUnavailable: true,
        })
      );
    });

    it("preserves the active sort from the URL instead of resetting it (FR-005)", () => {
      (useChannelVideos as Mock).mockReturnValue(baseVideosResult());
      (useVideos as Mock).mockReturnValue(baseVideosResult());

      renderPage(`/channels/${CHANNEL_ID}?entity_id=e1&sort_by=title&sort_order=asc`);

      expect(useVideos).toHaveBeenCalledWith(
        expect.objectContaining({
          entityIds: ["e1"],
          sortBy: "title",
          sortOrder: "asc",
        })
      );
    });

    it("shows an empty state with an unpin affordance when the AND-intersection has no matches", () => {
      (useChannelVideos as Mock).mockReturnValue(baseVideosResult());
      (useVideos as Mock).mockReturnValue(
        baseVideosResult({ videos: [], total: 0, loadedCount: 0 })
      );

      renderPage(`/channels/${CHANNEL_ID}?entity_id=e1&entity_id=e2`);

      expect(screen.getByText(/no videos match these pinned entities/i)).toBeInTheDocument();
      const clearButtons = screen.getAllByRole("button", { name: /clear pinned entities/i });
      expect(clearButtons.length).toBeGreaterThan(0);
    });

    it("clicking the unpin affordance removes the entity_id params from the URL", () => {
      (useChannelVideos as Mock).mockReturnValue(baseVideosResult());
      (useVideos as Mock).mockReturnValue(
        baseVideosResult({ videos: [], total: 0, loadedCount: 0 })
      );

      renderPage(`/channels/${CHANNEL_ID}?entity_id=e1`);

      const [clearButton] = screen.getAllByRole("button", { name: /clear pinned entities/i });
      fireEvent.click(clearButton as HTMLElement);

      // After clearing, useChannelVideos should be re-invoked as enabled (US1 mode).
      expect(useChannelVideos).toHaveBeenLastCalledWith(
        CHANNEL_ID,
        expect.objectContaining({ enabled: true })
      );
    });
  });
});
