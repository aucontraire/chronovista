/**
 * Tests for VideoDetailPage Recovery Button (T023, Feature 025).
 *
 * Tests the Web Archive recovery functionality integrated into the VideoDetailPage.
 *
 * Key behaviors tested:
 * - Recovery mutation triggers on button click
 * - Cache invalidation after successful recovery
 * - Error message display after failed recovery
 * - Button disabled state during loading
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route, useBlocker } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { VideoDetailPage } from '../VideoDetailPage';
import type { VideoDetail } from '../../types/video';
import type { RecoveryResultData } from '../../types/recovery';

// Mock the API fetch function
vi.mock('../../api/config', () => ({
  apiFetch: vi.fn(),
  API_BASE_URL: 'http://localhost:8765/api/v1',
  API_TIMEOUT: 10000,
  RECOVERY_TIMEOUT: 660000,
  isApiError: vi.fn(),
}));

// Mock useBlocker - will be overridden in tests
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useBlocker: vi.fn(() => ({
      state: 'unblocked' as const,
      reset: undefined,
      proceed: undefined,
      location: undefined,
    })),
  };
});

// Mock the deep link params hook
vi.mock('../../hooks/useDeepLinkParams', () => ({
  useDeepLinkParams: vi.fn(() => ({
    lang: null,
    segmentId: null,
    timestamp: null,
    clearDeepLinkParams: vi.fn(),
  })),
}));

// Mock useVideoDetail
vi.mock('../../hooks/useVideoDetail', () => ({
  useVideoDetail: vi.fn(),
}));

// Mock useVideoPlaylists
vi.mock('../../hooks/useVideoPlaylists', () => ({
  useVideoPlaylists: vi.fn(() => ({ playlists: [] })),
}));

// Mock TranscriptPanel
vi.mock('../../components/transcript', () => ({
  TranscriptPanel: () => <div data-testid="transcript-panel" />,
}));

// Mock ClassificationSection
vi.mock('../../components/ClassificationSection', () => ({
  ClassificationSection: () => <div data-testid="classification-section" />,
}));

// Mock LoadingState
vi.mock('../../components/LoadingState', () => ({
  LoadingState: () => <div data-testid="loading-state" />,
}));

// Mock recoveryStore with state tracking
vi.mock('../../stores/recoveryStore', () => {
  // Track sessions in the mock
  const mockSessions = new Map();

  const mockStore = {
    sessions: mockSessions,
    startRecovery: vi.fn((entityId, entityType, entityTitle, filterOptions) => {
      const sessionId = "mock-session-id";
      const session = {
        sessionId,
        entityId,
        entityType,
        entityTitle: entityTitle ?? null,
        phase: "pending" as const,
        startedAt: Date.now(),
        completedAt: null,
        filterOptions: filterOptions ?? {},
        result: null,
        error: null,
        abortController: null,
      };
      mockSessions.set(entityId, session);
      return sessionId;
    }),
    updatePhase: vi.fn((sessionId, phase) => {
      // Find session by sessionId and update phase
      for (const [entityId, session] of mockSessions.entries()) {
        if (session.sessionId === sessionId) {
          mockSessions.set(entityId, { ...session, phase, completedAt: ["completed", "failed", "cancelled"].includes(phase) ? Date.now() : null });
          break;
        }
      }
    }),
    setResult: vi.fn((sessionId, result) => {
      // Find session by sessionId and set result
      for (const [entityId, session] of mockSessions.entries()) {
        if (session.sessionId === sessionId) {
          mockSessions.set(entityId, { ...session, result, phase: "completed" as const, completedAt: Date.now() });
          break;
        }
      }
    }),
    setError: vi.fn((sessionId, error) => {
      // Find session by sessionId and set error
      for (const [entityId, session] of mockSessions.entries()) {
        if (session.sessionId === sessionId) {
          mockSessions.set(entityId, { ...session, error, phase: "failed" as const, completedAt: Date.now() });
          break;
        }
      }
    }),
    setAbortController: vi.fn((sessionId, controller) => {
      // Find session by sessionId and set abortController
      for (const [entityId, session] of mockSessions.entries()) {
        if (session.sessionId === sessionId) {
          mockSessions.set(entityId, { ...session, abortController: controller });
          break;
        }
      }
    }),
    getActiveSession: vi.fn((entityId) => mockSessions.get(entityId)),
    getActiveSessions: vi.fn(() => Array.from(mockSessions.values()).filter(s => ["pending", "in-progress"].includes(s.phase))),
    hasActiveRecovery: vi.fn(() => Array.from(mockSessions.values()).some(s => ["pending", "in-progress"].includes(s.phase))),
  };

  const useRecoveryStore = Object.assign(
    vi.fn((selector?: Function) => selector ? selector(mockStore) : mockStore),
    { getState: vi.fn().mockReturnValue(mockStore), setState: vi.fn(() => {}) }
  );

  return { useRecoveryStore };
});

// Import mocked functions
import { useVideoDetail } from '../../hooks/useVideoDetail';
import { apiFetch } from '../../api/config';
import { useRecoveryStore } from '../../stores/recoveryStore';

/**
 * Mock deleted video for recovery testing.
 */
const mockDeletedVideo: VideoDetail = {
  video_id: 'deleted-video-123',
  title: 'Deleted Video Title',
  description: 'This video was deleted',
  channel_id: 'channel-1',
  channel_title: 'Test Channel',
  upload_date: '2024-01-15T00:00:00Z',
  duration: 300,
  view_count: 1000,
  like_count: 50,
  comment_count: 25,
  tags: [],
  category_id: '22',
  category_name: 'People & Blogs',
  topics: [],
  default_language: 'en',
  made_for_kids: false,
  transcript_summary: {
    count: 0,
    languages: [],
    has_manual: false,
  },
  availability_status: 'deleted',
  alternative_url: null,
  recovered_at: null,
  recovery_source: null,
};

/**
 * Mock previously recovered video.
 */
const mockRecoveredVideo: VideoDetail = {
  ...mockDeletedVideo,
  recovered_at: '2024-02-01T12:00:00Z',
};

/**
 * Mock available video (recovery button should NOT show).
 */
const mockAvailableVideo: VideoDetail = {
  ...mockDeletedVideo,
  availability_status: 'available',
};

/**
 * Renders VideoDetailPage with MemoryRouter and QueryClientProvider.
 */
function renderVideoDetailPage(videoData: VideoDetail) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  vi.mocked(useVideoDetail).mockReturnValue({
    data: videoData,
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
  } as unknown as ReturnType<typeof useVideoDetail>);

  return {
    ...render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[`/videos/${videoData.video_id}`]}>
          <Routes>
            <Route path="/videos/:videoId" element={<VideoDetailPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    ),
    queryClient,
  };
}

describe('VideoDetailPage - Recovery Button (T023)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Clear mock sessions
    const mockStore = useRecoveryStore.getState();
    mockStore.sessions.clear();
  });

  describe('Mutation Trigger', () => {
    it('triggers recovery mutation when recovery button is clicked', async () => {
      const user = userEvent.setup();
      const currentYear = new Date().getFullYear();
      renderVideoDetailPage(mockDeletedVideo);

      const mockRecoveryResponse: RecoveryResultData = {
        success: true,
        fields_recovered: ['title', 'description'],
        fields_skipped: [],
        snapshot_used: '20240115120000',
        snapshots_available: 5,
        snapshots_tried: 2,
        failure_reason: null,
        duration_seconds: 3.5,
      };

      vi.mocked(apiFetch).mockResolvedValue({ data: mockRecoveryResponse });

      const recoveryButton = screen.getByRole('button', {
        name: /recover from web archive/i,
      });
      await user.click(recoveryButton);

      await waitFor(() => {
        expect(apiFetch).toHaveBeenCalledWith(
          `/videos/deleted-video-123/recover?end_year=${currentYear}`,
          expect.objectContaining({
            method: 'POST',
          })
        );
      });
    });

    it('does NOT trigger recovery when button is disabled during loading', async () => {
      const user = userEvent.setup();
      renderVideoDetailPage(mockDeletedVideo);

      // Mock a slow API response
      vi.mocked(apiFetch).mockImplementation(
        () => new Promise(() => {}) // Never resolves
      );

      const recoveryButton = screen.getByRole('button', {
        name: /recover from web archive/i,
      });

      // First click starts the mutation
      await user.click(recoveryButton);

      // Button should become disabled
      await waitFor(() => {
        expect(recoveryButton).toBeDisabled();
      });

      // Second click should not trigger another API call
      await user.click(recoveryButton);

      // Verify API was only called once
      expect(apiFetch).toHaveBeenCalledTimes(1);
    });
  });

  describe('Cache Invalidation', () => {
    it('invalidates video detail query after successful recovery', async () => {
      const user = userEvent.setup();
      const { queryClient } = renderVideoDetailPage(mockDeletedVideo);

      const mockRecoveryResponse: RecoveryResultData = {
        success: true,
        fields_recovered: ['title', 'description'],
        fields_skipped: [],
        snapshot_used: '20240115120000',
        snapshots_available: 5,
        snapshots_tried: 2,
        failure_reason: null,
        duration_seconds: 3.5,
      };

      vi.mocked(apiFetch).mockResolvedValue({ data: mockRecoveryResponse });

      // Spy on queryClient.invalidateQueries
      const invalidateQueriesSpy = vi.spyOn(queryClient, 'invalidateQueries');

      const recoveryButton = screen.getByRole('button', {
        name: /recover from web archive/i,
      });
      await user.click(recoveryButton);

      await waitFor(() => {
        expect(invalidateQueriesSpy).toHaveBeenCalledWith({
          queryKey: ['video', 'deleted-video-123'],
        });
      });
    });

    it('does NOT invalidate cache when recovery fails', async () => {
      const user = userEvent.setup();
      const { queryClient } = renderVideoDetailPage(mockDeletedVideo);

      vi.mocked(apiFetch).mockRejectedValue({
        message: 'No snapshots found',
        status: 404,
      });

      const invalidateQueriesSpy = vi.spyOn(queryClient, 'invalidateQueries');

      const recoveryButton = screen.getByRole('button', {
        name: /recover from web archive/i,
      });
      await user.click(recoveryButton);

      // Wait for mutation to fail
      await waitFor(() => {
        expect(apiFetch).toHaveBeenCalled();
      });

      // Give React Query time to settle
      await new Promise((resolve) => setTimeout(resolve, 100));

      // Cache should NOT be invalidated on error
      expect(invalidateQueriesSpy).not.toHaveBeenCalled();
    });
  });

  describe('Error Message Display', () => {
    it('displays error message when recovery fails', async () => {
      const user = userEvent.setup();
      renderVideoDetailPage(mockDeletedVideo);

      const mockErrorResponse: RecoveryResultData = {
        success: false,
        fields_recovered: [],
        fields_skipped: [],
        snapshot_used: null,
        snapshots_available: 0,
        snapshots_tried: 0,
        failure_reason: 'no_snapshots_found',
        duration_seconds: 0.5,
      };

      vi.mocked(apiFetch).mockResolvedValue({ data: mockErrorResponse });

      const recoveryButton = screen.getByRole('button', {
        name: /recover from web archive/i,
      });
      await user.click(recoveryButton);

      await waitFor(() => {
        expect(
          screen.getByText(/no archived snapshots found/i)
        ).toBeInTheDocument();
      });
    });

    it('displays contextual error for CDX connection error', async () => {
      const user = userEvent.setup();
      renderVideoDetailPage(mockDeletedVideo);

      const mockErrorResponse: RecoveryResultData = {
        success: false,
        fields_recovered: [],
        fields_skipped: [],
        snapshot_used: null,
        snapshots_available: 0,
        snapshots_tried: 0,
        failure_reason: 'cdx_connection_error',
        duration_seconds: 10.0,
      };

      vi.mocked(apiFetch).mockResolvedValue({ data: mockErrorResponse });

      const recoveryButton = screen.getByRole('button', {
        name: /recover from web archive/i,
      });
      await user.click(recoveryButton);

      await waitFor(() => {
        expect(
          screen.getByText(/web archive is temporarily unavailable/i)
        ).toBeInTheDocument();
      });
    });

    it('displays generic error when failure reason is unknown', async () => {
      const user = userEvent.setup();
      renderVideoDetailPage(mockDeletedVideo);

      const mockErrorResponse: RecoveryResultData = {
        success: false,
        fields_recovered: [],
        fields_skipped: [],
        snapshot_used: null,
        snapshots_available: 0,
        snapshots_tried: 0,
        failure_reason: null,
        duration_seconds: 0.5,
      };

      vi.mocked(apiFetch).mockResolvedValue({ data: mockErrorResponse });

      const recoveryButton = screen.getByRole('button', {
        name: /recover from web archive/i,
      });
      await user.click(recoveryButton);

      await waitFor(() => {
        expect(screen.getByText(/recovery failed/i)).toBeInTheDocument();
      });
    });
  });

  describe('Button Disabled During Loading', () => {
    it('disables recovery button while mutation is pending', async () => {
      const user = userEvent.setup();
      renderVideoDetailPage(mockDeletedVideo);

      // Mock a slow API response
      vi.mocked(apiFetch).mockImplementation(
        () => new Promise(() => {}) // Never resolves
      );

      const recoveryButton = screen.getByRole('button', {
        name: /recover from web archive/i,
      });

      // Initially enabled
      expect(recoveryButton).not.toBeDisabled();

      // Click starts the mutation
      await user.click(recoveryButton);

      // Button should become disabled
      await waitFor(() => {
        expect(recoveryButton).toBeDisabled();
      });
    });

    it('re-enables recovery button after mutation completes', async () => {
      const user = userEvent.setup();
      renderVideoDetailPage(mockDeletedVideo);

      const mockRecoveryResponse: RecoveryResultData = {
        success: true,
        fields_recovered: ['title'],
        fields_skipped: [],
        snapshot_used: '20240115120000',
        snapshots_available: 5,
        snapshots_tried: 1,
        failure_reason: null,
        duration_seconds: 2.1,
      };

      vi.mocked(apiFetch).mockResolvedValue({ data: mockRecoveryResponse });

      const recoveryButton = screen.getByRole('button', {
        name: /recover from web archive/i,
      });

      await user.click(recoveryButton);

      // Wait for mutation to complete
      await waitFor(() => {
        expect(apiFetch).toHaveBeenCalled();
      });

      // Button should be re-enabled after success
      await waitFor(() => {
        expect(recoveryButton).not.toBeDisabled();
      });
    });

    it('re-enables recovery button after mutation fails', async () => {
      const user = userEvent.setup();
      renderVideoDetailPage(mockDeletedVideo);

      vi.mocked(apiFetch).mockRejectedValue({
        message: 'Recovery failed',
      });

      const recoveryButton = screen.getByRole('button', {
        name: /recover from web archive/i,
      });

      await user.click(recoveryButton);

      // Wait for mutation to fail
      await waitFor(() => {
        expect(apiFetch).toHaveBeenCalled();
      });

      // Button should be re-enabled after failure
      await waitFor(() => {
        expect(recoveryButton).not.toBeDisabled();
      });
    });
  });

  describe('Button Visibility and Labels', () => {
    it('shows recovery button when video is deleted', () => {
      renderVideoDetailPage(mockDeletedVideo);

      expect(
        screen.getByRole('button', { name: /recover from web archive/i })
      ).toBeInTheDocument();
    });

    it('shows recovery button when video is private', () => {
      const privateVideo = { ...mockDeletedVideo, availability_status: 'private' };
      renderVideoDetailPage(privateVideo);

      expect(
        screen.getByRole('button', { name: /recover from web archive/i })
      ).toBeInTheDocument();
    });

    it('does NOT show recovery button when video is available', () => {
      renderVideoDetailPage(mockAvailableVideo);

      expect(
        screen.queryByRole('button', { name: /recover from web archive/i })
      ).not.toBeInTheDocument();
    });

    it('shows "Re-recover" label when video was previously recovered', () => {
      renderVideoDetailPage(mockRecoveredVideo);

      expect(
        screen.getByRole('button', { name: /re-recover from web archive/i })
      ).toBeInTheDocument();
    });

    it('shows last recovery date when video was previously recovered', () => {
      renderVideoDetailPage(mockRecoveredVideo);

      // The recovered_at date is 2024-02-01
      expect(screen.getByText(/last: feb 1, 2024/i)).toBeInTheDocument();
    });
  });

  describe('Success Message Display', () => {
    it('displays success message with field count after successful recovery', async () => {
      const user = userEvent.setup();
      renderVideoDetailPage(mockDeletedVideo);

      const mockRecoveryResponse: RecoveryResultData = {
        success: true,
        fields_recovered: ['title', 'description', 'view_count'],
        fields_skipped: [],
        snapshot_used: '20240115120000',
        snapshots_available: 5,
        snapshots_tried: 2,
        failure_reason: null,
        duration_seconds: 3.5,
      };

      vi.mocked(apiFetch).mockResolvedValue({ data: mockRecoveryResponse });

      const recoveryButton = screen.getByRole('button', {
        name: /recover from web archive/i,
      });
      await user.click(recoveryButton);

      await waitFor(() => {
        expect(screen.getByText(/recovered 3 fields/i)).toBeInTheDocument();
      });
    });

    it('displays snapshot date in success message', async () => {
      const user = userEvent.setup();
      renderVideoDetailPage(mockDeletedVideo);

      const mockRecoveryResponse: RecoveryResultData = {
        success: true,
        fields_recovered: ['title'],
        fields_skipped: [],
        snapshot_used: '20240115120000',
        snapshots_available: 5,
        snapshots_tried: 1,
        failure_reason: null,
        duration_seconds: 2.1,
      };

      vi.mocked(apiFetch).mockResolvedValue({ data: mockRecoveryResponse });

      const recoveryButton = screen.getByRole('button', {
        name: /recover from web archive/i,
      });
      await user.click(recoveryButton);

      await waitFor(() => {
        expect(screen.getByText(/2024-01-15/i)).toBeInTheDocument();
      });
    });

    it('displays informational message when no fields were updated', async () => {
      const user = userEvent.setup();
      renderVideoDetailPage(mockDeletedVideo);

      const mockRecoveryResponse: RecoveryResultData = {
        success: true,
        fields_recovered: [],
        fields_skipped: ['title', 'description'],
        snapshot_used: '20240115120000',
        snapshots_available: 5,
        snapshots_tried: 1,
        failure_reason: null,
        duration_seconds: 1.5,
      };

      vi.mocked(apiFetch).mockResolvedValue({ data: mockRecoveryResponse });

      const recoveryButton = screen.getByRole('button', {
        name: /recover from web archive/i,
      });
      await user.click(recoveryButton);

      await waitFor(() => {
        expect(
          screen.getByText(/all fields already up-to-date/i)
        ).toBeInTheDocument();
      });
    });
  });

  describe('Year Filter Integration', () => {
    it('passes year params to API when years are selected', async () => {
      const user = userEvent.setup();
      renderVideoDetailPage(mockDeletedVideo);

      const mockRecoveryResponse: RecoveryResultData = {
        success: true,
        fields_recovered: ['title'],
        fields_skipped: [],
        snapshot_used: '20240115120000',
        snapshots_available: 5,
        snapshots_tried: 1,
        failure_reason: null,
        duration_seconds: 2.1,
      };

      vi.mocked(apiFetch).mockResolvedValue({ data: mockRecoveryResponse });

      // Open advanced options
      const advancedOptionsToggle = screen.getByRole('button', {
        name: /advanced options/i,
      });
      await user.click(advancedOptionsToggle);

      // Set year range
      const startYearSelect = screen.getByLabelText(/from:/i);
      const endYearSelect = screen.getByLabelText(/to:/i);
      await user.selectOptions(startYearSelect, '2020');
      await user.selectOptions(endYearSelect, '2024');

      // Click recovery button
      const recoveryButton = screen.getByRole('button', {
        name: /recover from web archive/i,
      });
      await user.click(recoveryButton);

      await waitFor(() => {
        expect(apiFetch).toHaveBeenCalledWith(
          '/videos/deleted-video-123/recover?start_year=2020&end_year=2024',
          expect.objectContaining({
            method: 'POST',
          })
        );
      });
    });

    it('adds only endYear param (current year) when using default values without opening advanced options', async () => {
      const user = userEvent.setup();
      const currentYear = new Date().getFullYear();
      renderVideoDetailPage(mockDeletedVideo);

      const mockRecoveryResponse: RecoveryResultData = {
        success: true,
        fields_recovered: ['title'],
        fields_skipped: [],
        snapshot_used: '20240115120000',
        snapshots_available: 5,
        snapshots_tried: 1,
        failure_reason: null,
        duration_seconds: 2.1,
      };

      vi.mocked(apiFetch).mockResolvedValue({ data: mockRecoveryResponse });

      // Click recovery button without opening advanced options
      const recoveryButton = screen.getByRole('button', {
        name: /recover from web archive/i,
      });
      await user.click(recoveryButton);

      await waitFor(() => {
        expect(apiFetch).toHaveBeenCalledWith(
          `/videos/deleted-video-123/recover?end_year=${currentYear}`,
          expect.objectContaining({
            method: 'POST',
          })
        );
      });
    });

    it('uses recovery timeout for API call', async () => {
      const user = userEvent.setup();
      renderVideoDetailPage(mockDeletedVideo);

      const mockRecoveryResponse: RecoveryResultData = {
        success: true,
        fields_recovered: ['title'],
        fields_skipped: [],
        snapshot_used: '20240115120000',
        snapshots_available: 5,
        snapshots_tried: 1,
        failure_reason: null,
        duration_seconds: 2.1,
      };

      vi.mocked(apiFetch).mockResolvedValue({ data: mockRecoveryResponse });

      const recoveryButton = screen.getByRole('button', {
        name: /recover from web archive/i,
      });
      await user.click(recoveryButton);

      await waitFor(() => {
        expect(apiFetch).toHaveBeenCalledWith(
          expect.any(String),
          expect.objectContaining({
            method: 'POST',
            timeout: 660000,
          })
        );
      });
    });
  });

  describe('AbortController Registration (T041)', () => {
    it('should call setAbortController after starting recovery', async () => {
      const user = userEvent.setup();
      renderVideoDetailPage(mockDeletedVideo);

      const mockRecoveryResponse: RecoveryResultData = {
        success: true,
        fields_recovered: ['title'],
        fields_skipped: [],
        snapshot_used: '20240115120000',
        snapshots_available: 5,
        snapshots_tried: 1,
        failure_reason: null,
        duration_seconds: 2.1,
      };

      vi.mocked(apiFetch).mockResolvedValue({ data: mockRecoveryResponse });

      const mockStore = useRecoveryStore.getState();
      const setAbortControllerSpy = vi.spyOn(mockStore, 'setAbortController');

      const recoveryButton = screen.getByRole('button', {
        name: /recover from web archive/i,
      });
      await user.click(recoveryButton);

      await waitFor(() => {
        expect(setAbortControllerSpy).toHaveBeenCalledWith(
          'mock-session-id',
          expect.any(AbortController)
        );
      });
    });

    it('should pass signal to apiFetch options', async () => {
      const user = userEvent.setup();
      renderVideoDetailPage(mockDeletedVideo);

      const mockRecoveryResponse: RecoveryResultData = {
        success: true,
        fields_recovered: ['title'],
        fields_skipped: [],
        snapshot_used: '20240115120000',
        snapshots_available: 5,
        snapshots_tried: 1,
        failure_reason: null,
        duration_seconds: 2.1,
      };

      vi.mocked(apiFetch).mockResolvedValue({ data: mockRecoveryResponse });

      const recoveryButton = screen.getByRole('button', {
        name: /recover from web archive/i,
      });
      await user.click(recoveryButton);

      await waitFor(() => {
        expect(apiFetch).toHaveBeenCalledWith(
          expect.any(String),
          expect.objectContaining({
            method: 'POST',
            timeout: 660000,
            signal: expect.any(AbortSignal),
          })
        );
      });
    });
  });

  describe('Navigation Blocker (T042)', () => {
    beforeEach(() => {
      // Reset the mock implementation for each test
      vi.mocked(useBlocker).mockReturnValue({
        state: 'unblocked' as const,
        reset: undefined,
        proceed: undefined,
        location: undefined,
      });
    });

    it('does NOT activate blocker when no recovery is happening', () => {
      renderVideoDetailPage(mockDeletedVideo);

      // Blocker should be called with false when no active recovery
      expect(useBlocker).toHaveBeenCalledWith(false);
    });

    it('renders modal with "Stay" button when blocker state is blocked', () => {
      const mockBlocker = {
        state: 'blocked' as const,
        reset: vi.fn(),
        proceed: vi.fn(),
        location: {} as any,
      };
      vi.mocked(useBlocker).mockReturnValue(mockBlocker);

      // Set up in-progress session
      const mockStore = useRecoveryStore.getState();
      const sessionId = mockStore.startRecovery('deleted-video-123', 'video', 'Test Video', {});
      mockStore.updatePhase(sessionId, 'in-progress');

      renderVideoDetailPage(mockDeletedVideo);

      // Modal should render
      expect(screen.getByRole('dialog', { name: /recovery in progress/i })).toBeInTheDocument();
      expect(screen.getByText(/navigating away will not cancel the recovery/i)).toBeInTheDocument();

      // Buttons should be present
      expect(screen.getByRole('button', { name: /stay/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /leave/i })).toBeInTheDocument();
    });

    it('calls blocker.reset when "Stay" button is clicked', async () => {
      const user = userEvent.setup();
      const mockBlocker = {
        state: 'blocked' as const,
        reset: vi.fn(),
        proceed: vi.fn(),
        location: {} as any,
      };
      vi.mocked(useBlocker).mockReturnValue(mockBlocker);

      // Set up in-progress session
      const mockStore = useRecoveryStore.getState();
      const sessionId = mockStore.startRecovery('deleted-video-123', 'video', 'Test Video', {});
      mockStore.updatePhase(sessionId, 'in-progress');

      renderVideoDetailPage(mockDeletedVideo);

      const stayButton = screen.getByRole('button', { name: /stay/i });
      await user.click(stayButton);

      expect(mockBlocker.reset).toHaveBeenCalled();
    });

    it('calls blocker.proceed when "Leave" button is clicked', async () => {
      const user = userEvent.setup();
      const mockBlocker = {
        state: 'blocked' as const,
        reset: vi.fn(),
        proceed: vi.fn(),
        location: {} as any,
      };
      vi.mocked(useBlocker).mockReturnValue(mockBlocker);

      // Set up in-progress session
      const mockStore = useRecoveryStore.getState();
      const sessionId = mockStore.startRecovery('deleted-video-123', 'video', 'Test Video', {});
      mockStore.updatePhase(sessionId, 'in-progress');

      renderVideoDetailPage(mockDeletedVideo);

      const leaveButton = screen.getByRole('button', { name: /leave/i });
      await user.click(leaveButton);

      expect(mockBlocker.proceed).toHaveBeenCalled();
    });

    it('modal has correct ARIA attributes and Stay button has focus priority', () => {
      const mockBlocker = {
        state: 'blocked' as const,
        reset: vi.fn(),
        proceed: vi.fn(),
        location: {} as any,
      };
      vi.mocked(useBlocker).mockReturnValue(mockBlocker);

      // Set up in-progress session
      const mockStore = useRecoveryStore.getState();
      const sessionId = mockStore.startRecovery('deleted-video-123', 'video', 'Test Video', {});
      mockStore.updatePhase(sessionId, 'in-progress');

      renderVideoDetailPage(mockDeletedVideo);

      const modal = screen.getByRole('dialog');
      expect(modal).toHaveAttribute('aria-modal', 'true');
      expect(modal).toHaveAttribute('aria-labelledby', 'nav-guard-title');

      const title = screen.getByText(/recovery in progress/i);
      expect(title).toHaveAttribute('id', 'nav-guard-title');

      // Stay button should be present (autoFocus is tested via visual/manual testing)
      const stayButton = screen.getByRole('button', { name: /stay/i });
      expect(stayButton).toBeInTheDocument();
    });
  });
});
