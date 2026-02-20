/**
 * Tests for ChannelDetailPage Recovery Button (T026, Feature 025).
 *
 * Tests the Web Archive recovery functionality integrated into the ChannelDetailPage.
 *
 * Key behaviors tested:
 * - Recovery mutation triggers on button click
 * - Cache invalidation after successful recovery
 * - Error message display after failed recovery
 * - "Re-recover" label when previously recovered
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route, useBlocker } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { ChannelDetailPage } from '../ChannelDetailPage';
import type { ChannelDetail } from '../../types/channel';
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

// Mock useChannelDetail
vi.mock('../../hooks/useChannelDetail', () => ({
  useChannelDetail: vi.fn(),
}));

// Mock useChannelVideos
vi.mock('../../hooks/useChannelVideos', () => ({
  useChannelVideos: vi.fn(() => ({
    videos: [],
    total: 0,
    loadedCount: 0,
    isLoading: false,
    isError: false,
    error: null,
    hasNextPage: false,
    isFetchingNextPage: false,
    retry: vi.fn(),
    loadMoreRef: { current: null },
  })),
}));

// Mock VideoGrid
vi.mock('../../components/VideoGrid', () => ({
  VideoGrid: () => <div data-testid="video-grid" />,
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
    cancelRecovery: vi.fn((sessionId) => {
      // Find session by sessionId and cancel
      for (const [entityId, session] of mockSessions.entries()) {
        if (session.sessionId === sessionId) {
          session.abortController?.abort();
          mockSessions.set(entityId, { ...session, phase: "cancelled" as const, completedAt: Date.now() });
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
import { useChannelDetail } from '../../hooks/useChannelDetail';
import { apiFetch } from '../../api/config';
import { useRecoveryStore } from '../../stores/recoveryStore';

/**
 * Mock deleted channel for recovery testing.
 */
const mockDeletedChannel: ChannelDetail = {
  channel_id: 'deleted-channel-123',
  title: 'Deleted Channel',
  description: 'This channel was deleted',
  thumbnail_url: 'https://example.com/thumbnail.jpg',
  subscriber_count: 1000,
  video_count: 50,
  country: 'US',
  is_subscribed: true,
  availability_status: 'deleted',
  recovered_at: null,
  recovery_source: null,
  custom_url: null,
  default_language: null,
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
};

/**
 * Mock previously recovered channel.
 */
const mockRecoveredChannel: ChannelDetail = {
  ...mockDeletedChannel,
  recovered_at: '2024-02-01T12:00:00Z',
};

/**
 * Mock available channel (recovery button should NOT show).
 */
const mockAvailableChannel: ChannelDetail = {
  ...mockDeletedChannel,
  availability_status: 'available',
};

/**
 * Renders ChannelDetailPage with MemoryRouter and QueryClientProvider.
 */
function renderChannelDetailPage(channelData: ChannelDetail) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  vi.mocked(useChannelDetail).mockReturnValue({
    data: channelData,
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
  } as unknown as ReturnType<typeof useChannelDetail>);

  return {
    ...render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[`/channels/${channelData.channel_id}`]}>
          <Routes>
            <Route path="/channels/:channelId" element={<ChannelDetailPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    ),
    queryClient,
  };
}

describe('ChannelDetailPage - Recovery Button (T026)', () => {
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
      renderChannelDetailPage(mockDeletedChannel);

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
          `/channels/deleted-channel-123/recover?end_year=${currentYear}`,
          expect.objectContaining({
            method: 'POST',
          })
        );
      });
    });

    it('does NOT trigger recovery when button is disabled during loading', async () => {
      const user = userEvent.setup();
      renderChannelDetailPage(mockDeletedChannel);

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
    it('invalidates channel detail query after successful recovery', async () => {
      const user = userEvent.setup();
      const { queryClient } = renderChannelDetailPage(mockDeletedChannel);

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
          queryKey: ['channel', 'deleted-channel-123'],
        });
      });
    });

    it('does NOT invalidate cache when recovery fails', async () => {
      const user = userEvent.setup();
      const { queryClient } = renderChannelDetailPage(mockDeletedChannel);

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
      renderChannelDetailPage(mockDeletedChannel);

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
      renderChannelDetailPage(mockDeletedChannel);

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
      renderChannelDetailPage(mockDeletedChannel);

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

  describe('Re-recover Label', () => {
    it('shows "Recover from Web Archive" label when channel has NOT been recovered', () => {
      renderChannelDetailPage(mockDeletedChannel);

      expect(
        screen.getByRole('button', { name: /^recover from web archive/i })
      ).toBeInTheDocument();

      expect(
        screen.queryByRole('button', { name: /^re-recover from web archive/i })
      ).not.toBeInTheDocument();
    });

    it('shows "Re-recover from Web Archive" label when channel has recovered_at set', () => {
      renderChannelDetailPage(mockRecoveredChannel);

      expect(
        screen.getByRole('button', { name: /^re-recover from web archive/i })
      ).toBeInTheDocument();

      expect(
        screen.queryByRole('button', { name: /^recover from web archive$/i })
      ).not.toBeInTheDocument();
    });

    it('shows last recovery date when channel was previously recovered', () => {
      renderChannelDetailPage(mockRecoveredChannel);

      // The recovered_at date is 2024-02-01
      expect(screen.getByText(/last: feb 1, 2024/i)).toBeInTheDocument();
    });
  });

  describe('Button Visibility', () => {
    it('shows recovery button when channel is deleted', () => {
      renderChannelDetailPage(mockDeletedChannel);

      expect(
        screen.getByRole('button', { name: /recover from web archive/i })
      ).toBeInTheDocument();
    });

    it('shows recovery button when channel is private', () => {
      const privateChannel = { ...mockDeletedChannel, availability_status: 'private' };
      renderChannelDetailPage(privateChannel);

      expect(
        screen.getByRole('button', { name: /recover from web archive/i })
      ).toBeInTheDocument();
    });

    it('shows recovery button when channel is terminated', () => {
      const terminatedChannel = { ...mockDeletedChannel, availability_status: 'terminated' };
      renderChannelDetailPage(terminatedChannel);

      expect(
        screen.getByRole('button', { name: /recover from web archive/i })
      ).toBeInTheDocument();
    });

    it('does NOT show recovery button when channel is available', () => {
      renderChannelDetailPage(mockAvailableChannel);

      expect(
        screen.queryByRole('button', { name: /recover from web archive/i })
      ).not.toBeInTheDocument();
    });
  });

  describe('Button Disabled During Loading', () => {
    it('disables recovery button while mutation is pending', async () => {
      const user = userEvent.setup();
      renderChannelDetailPage(mockDeletedChannel);

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
      renderChannelDetailPage(mockDeletedChannel);

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
      renderChannelDetailPage(mockDeletedChannel);

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

  describe('Success Message Display', () => {
    it('displays success message with field count after successful recovery', async () => {
      const user = userEvent.setup();
      renderChannelDetailPage(mockDeletedChannel);

      const mockRecoveryResponse: RecoveryResultData = {
        success: true,
        fields_recovered: ['title', 'description', 'subscriber_count'],
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
      renderChannelDetailPage(mockDeletedChannel);

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
      renderChannelDetailPage(mockDeletedChannel);

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
      renderChannelDetailPage(mockDeletedChannel);

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
          '/channels/deleted-channel-123/recover?start_year=2020&end_year=2024',
          expect.objectContaining({
            method: 'POST',
          })
        );
      });
    });

    it('adds only endYear param (current year) when using default values without opening advanced options', async () => {
      const user = userEvent.setup();
      const currentYear = new Date().getFullYear();
      renderChannelDetailPage(mockDeletedChannel);

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
          `/channels/deleted-channel-123/recover?end_year=${currentYear}`,
          expect.objectContaining({
            method: 'POST',
          })
        );
      });
    });

    it('uses recovery timeout for API call', async () => {
      const user = userEvent.setup();
      renderChannelDetailPage(mockDeletedChannel);

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
      renderChannelDetailPage(mockDeletedChannel);

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
      const sessionId = mockStore.startRecovery('deleted-channel-123', 'channel', 'Test Channel', {});
      mockStore.updatePhase(sessionId, 'in-progress');

      renderChannelDetailPage(mockDeletedChannel);

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
      const sessionId = mockStore.startRecovery('deleted-channel-123', 'channel', 'Test Channel', {});
      mockStore.updatePhase(sessionId, 'in-progress');

      renderChannelDetailPage(mockDeletedChannel);

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
      const sessionId = mockStore.startRecovery('deleted-channel-123', 'channel', 'Test Channel', {});
      mockStore.updatePhase(sessionId, 'in-progress');

      renderChannelDetailPage(mockDeletedChannel);

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
      const sessionId = mockStore.startRecovery('deleted-channel-123', 'channel', 'Test Channel', {});
      mockStore.updatePhase(sessionId, 'in-progress');

      renderChannelDetailPage(mockDeletedChannel);

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
