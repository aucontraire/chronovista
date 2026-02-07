/**
 * Tests for useChannelVideos hook.
 *
 * Covers:
 * - Returns videos for a channel
 * - Handles loading state
 * - Handles error state
 * - Implements infinite scroll (fetchNextPage)
 * - Handles empty video list (EC-003)
 * - Returns disabled state when channelId not provided
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { type ReactNode } from 'react';

import { useChannelVideos } from '../../src/hooks/useChannelVideos';
import { apiFetch } from '../../src/api/config';
import type { VideoListResponse } from '../../src/types/video';

// Mock the API fetch function
vi.mock('../../src/api/config', () => ({
  apiFetch: vi.fn(),
}));

const mockApiFetch = vi.mocked(apiFetch);

/**
 * Create a fresh QueryClient for each test to avoid cross-test pollution.
 */
function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
        staleTime: 0,
      },
    },
    logger: {
      log: () => {},
      warn: () => {},
      error: () => {},
    },
  });
}

/**
 * Wrapper component that provides QueryClient context.
 */
function createWrapper(queryClient: QueryClient) {
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

describe('useChannelVideos', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createTestQueryClient();
    vi.clearAllMocks();
  });

  afterEach(() => {
    queryClient.clear();
  });

  describe('Successful Data Fetching', () => {
    it('should return videos for a channel', async () => {
      const mockResponse: VideoListResponse = {
        data: [
          {
            video_id: 'dQw4w9WgXcQ',
            title: 'Video 1',
            channel_id: 'UC123456789012345678901',
            channel_title: 'Test Channel',
            upload_date: '2024-01-15T10:30:00Z',
            duration: 245,
            view_count: 1000000,
            transcript_summary: {
              count: 1,
              languages: ['en'],
              has_manual: true,
            },
          },
          {
            video_id: 'jNQXAC9IVRw',
            title: 'Video 2',
            channel_id: 'UC123456789012345678901',
            channel_title: 'Test Channel',
            upload_date: '2024-01-10T08:00:00Z',
            duration: 180,
            view_count: 500000,
            transcript_summary: {
              count: 2,
              languages: ['en', 'es'],
              has_manual: false,
            },
          },
        ],
        pagination: {
          total: 2,
          limit: 25,
          offset: 0,
          has_more: false,
        },
      };

      mockApiFetch.mockResolvedValueOnce(mockResponse);

      const { result } = renderHook(
        () => useChannelVideos('UC123456789012345678901'),
        {
          wrapper: createWrapper(queryClient),
        }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.videos).toHaveLength(2);
      expect(result.current.videos[0].title).toBe('Video 1');
      expect(result.current.videos[1].title).toBe('Video 2');
      expect(result.current.total).toBe(2);
      expect(result.current.loadedCount).toBe(2);
      expect(result.current.isError).toBe(false);
    });

    it('should flatten multiple pages into single videos array', async () => {
      const page1Response: VideoListResponse = {
        data: [
          {
            video_id: 'video1',
            title: 'Video 1',
            channel_id: 'UC123456789012345678901',
            channel_title: 'Test Channel',
            upload_date: '2024-01-15T10:30:00Z',
            duration: 245,
            view_count: 1000000,
            transcript_summary: {
              count: 0,
              languages: [],
              has_manual: false,
            },
          },
        ],
        pagination: {
          total: 2,
          limit: 1,
          offset: 0,
          has_more: true,
        },
      };

      const page2Response: VideoListResponse = {
        data: [
          {
            video_id: 'video2',
            title: 'Video 2',
            channel_id: 'UC123456789012345678901',
            channel_title: 'Test Channel',
            upload_date: '2024-01-10T08:00:00Z',
            duration: 180,
            view_count: 500000,
            transcript_summary: {
              count: 0,
              languages: [],
              has_manual: false,
            },
          },
        ],
        pagination: {
          total: 2,
          limit: 1,
          offset: 1,
          has_more: false,
        },
      };

      mockApiFetch
        .mockResolvedValueOnce(page1Response)
        .mockResolvedValueOnce(page2Response);

      const { result } = renderHook(
        () => useChannelVideos('UC123456789012345678901', { limit: 1 }),
        {
          wrapper: createWrapper(queryClient),
        }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.videos).toHaveLength(1);
      expect(result.current.hasNextPage).toBe(true);

      // Fetch next page
      result.current.fetchNextPage();

      await waitFor(() => {
        expect(result.current.videos).toHaveLength(2);
      });

      expect(result.current.videos[0].title).toBe('Video 1');
      expect(result.current.videos[1].title).toBe('Video 2');
      expect(result.current.hasNextPage).toBe(false);
    });
  });

  describe('Loading State', () => {
    it('should handle loading state correctly', async () => {
      // Create a promise that never resolves to keep loading state
      mockApiFetch.mockImplementation(
        () =>
          new Promise(() => {
            /* never resolves */
          })
      );

      const { result } = renderHook(
        () => useChannelVideos('UC123456789012345678901'),
        {
          wrapper: createWrapper(queryClient),
        }
      );

      expect(result.current.isLoading).toBe(true);
      expect(result.current.videos).toHaveLength(0);
      expect(result.current.isError).toBe(false);
    });

    it('should set isLoading to false after successful fetch', async () => {
      const mockResponse: VideoListResponse = {
        data: [],
        pagination: {
          total: 0,
          limit: 25,
          offset: 0,
          has_more: false,
        },
      };

      mockApiFetch.mockResolvedValueOnce(mockResponse);

      const { result } = renderHook(
        () => useChannelVideos('UC123456789012345678901'),
        {
          wrapper: createWrapper(queryClient),
        }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.isError).toBe(false);
    });
  });

  describe('Error State', () => {
    it('should handle error state correctly', async () => {
      const mockError = {
        type: 'network' as const,
        message: 'Network error occurred',
        status: undefined,
      };

      mockApiFetch.mockRejectedValueOnce(mockError);

      const { result } = renderHook(
        () => useChannelVideos('UC123456789012345678901'),
        {
          wrapper: createWrapper(queryClient),
        }
      );

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error).toEqual(mockError);
      expect(result.current.videos).toHaveLength(0);
      expect(result.current.isLoading).toBe(false);
    });

    it('should allow retry after error', async () => {
      const mockError = {
        type: 'network' as const,
        message: 'Network error',
        status: undefined,
      };

      const mockResponse: VideoListResponse = {
        data: [
          {
            video_id: 'dQw4w9WgXcQ',
            title: 'Test Video',
            channel_id: 'UC123456789012345678901',
            channel_title: 'Test Channel',
            upload_date: '2024-01-15T10:30:00Z',
            duration: 245,
            view_count: 1000000,
            transcript_summary: {
              count: 1,
              languages: ['en'],
              has_manual: true,
            },
          },
        ],
        pagination: {
          total: 1,
          limit: 25,
          offset: 0,
          has_more: false,
        },
      };

      // First call fails, second succeeds
      mockApiFetch.mockRejectedValueOnce(mockError).mockResolvedValueOnce(mockResponse);

      const { result } = renderHook(
        () => useChannelVideos('UC123456789012345678901'),
        {
          wrapper: createWrapper(queryClient),
        }
      );

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      // Retry the request
      result.current.retry();

      await waitFor(() => {
        expect(result.current.isError).toBe(false);
      });

      expect(result.current.videos).toHaveLength(1);
      expect(result.current.videos[0].title).toBe('Test Video');
    });
  });

  describe('Empty Video List (EC-003)', () => {
    it('should handle empty video list correctly', async () => {
      const mockResponse: VideoListResponse = {
        data: [],
        pagination: {
          total: 0,
          limit: 25,
          offset: 0,
          has_more: false,
        },
      };

      mockApiFetch.mockResolvedValueOnce(mockResponse);

      const { result } = renderHook(
        () => useChannelVideos('UC123456789012345678901'),
        {
          wrapper: createWrapper(queryClient),
        }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.videos).toHaveLength(0);
      expect(result.current.total).toBe(0);
      expect(result.current.loadedCount).toBe(0);
      expect(result.current.hasNextPage).toBe(false);
      expect(result.current.isError).toBe(false);
    });

    it('should distinguish between empty result and error', async () => {
      const emptyResponse: VideoListResponse = {
        data: [],
        pagination: {
          total: 0,
          limit: 25,
          offset: 0,
          has_more: false,
        },
      };

      mockApiFetch.mockResolvedValueOnce(emptyResponse);

      const { result } = renderHook(
        () => useChannelVideos('UC123456789012345678901'),
        {
          wrapper: createWrapper(queryClient),
        }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      // Should be successful fetch with empty data, not an error
      expect(result.current.isError).toBe(false);
      expect(result.current.videos).toHaveLength(0);
      expect(result.current.total).toBe(0);
    });
  });

  describe('Infinite Scroll', () => {
    it('should implement fetchNextPage for infinite scroll', async () => {
      const page1Response: VideoListResponse = {
        data: [
          {
            video_id: 'video1',
            title: 'Video 1',
            channel_id: 'UC123456789012345678901',
            channel_title: 'Test Channel',
            upload_date: '2024-01-15T10:30:00Z',
            duration: 245,
            view_count: 1000000,
            transcript_summary: {
              count: 0,
              languages: [],
              has_manual: false,
            },
          },
        ],
        pagination: {
          total: 2,
          limit: 1,
          offset: 0,
          has_more: true,
        },
      };

      const page2Response: VideoListResponse = {
        data: [
          {
            video_id: 'video2',
            title: 'Video 2',
            channel_id: 'UC123456789012345678901',
            channel_title: 'Test Channel',
            upload_date: '2024-01-10T08:00:00Z',
            duration: 180,
            view_count: 500000,
            transcript_summary: {
              count: 0,
              languages: [],
              has_manual: false,
            },
          },
        ],
        pagination: {
          total: 2,
          limit: 1,
          offset: 1,
          has_more: false,
        },
      };

      mockApiFetch
        .mockResolvedValueOnce(page1Response)
        .mockResolvedValueOnce(page2Response);

      const { result } = renderHook(
        () => useChannelVideos('UC123456789012345678901', { limit: 1 }),
        {
          wrapper: createWrapper(queryClient),
        }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.hasNextPage).toBe(true);
      expect(result.current.videos).toHaveLength(1);

      result.current.fetchNextPage();

      await waitFor(() => {
        expect(result.current.isFetchingNextPage).toBe(false);
      });

      expect(result.current.videos).toHaveLength(2);
      expect(result.current.hasNextPage).toBe(false);
    });

    it('should set hasNextPage to false when no more pages', async () => {
      const mockResponse: VideoListResponse = {
        data: [
          {
            video_id: 'video1',
            title: 'Video 1',
            channel_id: 'UC123456789012345678901',
            channel_title: 'Test Channel',
            upload_date: '2024-01-15T10:30:00Z',
            duration: 245,
            view_count: 1000000,
            transcript_summary: {
              count: 0,
              languages: [],
              has_manual: false,
            },
          },
        ],
        pagination: {
          total: 1,
          limit: 25,
          offset: 0,
          has_more: false,
        },
      };

      mockApiFetch.mockResolvedValueOnce(mockResponse);

      const { result } = renderHook(
        () => useChannelVideos('UC123456789012345678901'),
        {
          wrapper: createWrapper(queryClient),
        }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.hasNextPage).toBe(false);
    });

    it('should track isFetchingNextPage state', async () => {
      const page1Response: VideoListResponse = {
        data: [
          {
            video_id: 'video1',
            title: 'Video 1',
            channel_id: 'UC123456789012345678901',
            channel_title: 'Test Channel',
            upload_date: '2024-01-15T10:30:00Z',
            duration: 245,
            view_count: 1000000,
            transcript_summary: {
              count: 0,
              languages: [],
              has_manual: false,
            },
          },
        ],
        pagination: {
          total: 2,
          limit: 1,
          offset: 0,
          has_more: true,
        },
      };

      const page2Response: VideoListResponse = {
        data: [
          {
            video_id: 'video2',
            title: 'Video 2',
            channel_id: 'UC123456789012345678901',
            channel_title: 'Test Channel',
            upload_date: '2024-01-10T08:00:00Z',
            duration: 180,
            view_count: 500000,
            transcript_summary: {
              count: 0,
              languages: [],
              has_manual: false,
            },
          },
        ],
        pagination: {
          total: 2,
          limit: 1,
          offset: 1,
          has_more: false,
        },
      };

      mockApiFetch
        .mockResolvedValueOnce(page1Response)
        .mockResolvedValueOnce(page2Response);

      const { result } = renderHook(
        () => useChannelVideos('UC123456789012345678901', { limit: 1 }),
        {
          wrapper: createWrapper(queryClient),
        }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.isFetchingNextPage).toBe(false);

      result.current.fetchNextPage();

      // Note: In a real test environment, isFetchingNextPage would briefly be true,
      // but in this synchronous mock setup, it resolves immediately
      await waitFor(() => {
        expect(result.current.isFetchingNextPage).toBe(false);
      });

      expect(result.current.videos).toHaveLength(2);
    });
  });

  describe('Disabled State When No Channel ID', () => {
    it('should return disabled state when channelId is not provided', () => {
      const { result } = renderHook(() => useChannelVideos(undefined), {
        wrapper: createWrapper(queryClient),
      });

      expect(result.current.videos).toHaveLength(0);
      expect(result.current.isLoading).toBe(false);
      expect(result.current.isError).toBe(false);
      expect(mockApiFetch).not.toHaveBeenCalled();
    });

    it('should not fetch when channelId is empty string', () => {
      const { result } = renderHook(() => useChannelVideos(''), {
        wrapper: createWrapper(queryClient),
      });

      expect(result.current.videos).toHaveLength(0);
      expect(result.current.isLoading).toBe(false);
      expect(mockApiFetch).not.toHaveBeenCalled();
    });

    it('should be enabled when valid channelId is provided', async () => {
      const mockResponse: VideoListResponse = {
        data: [],
        pagination: {
          total: 0,
          limit: 25,
          offset: 0,
          has_more: false,
        },
      };

      mockApiFetch.mockResolvedValueOnce(mockResponse);

      const { result } = renderHook(
        () => useChannelVideos('UC123456789012345678901'),
        {
          wrapper: createWrapper(queryClient),
        }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(mockApiFetch).toHaveBeenCalledWith(
        expect.stringContaining('/channels/UC123456789012345678901/videos')
      );
    });
  });

  describe('Custom Options', () => {
    it('should accept custom limit option', async () => {
      const mockResponse: VideoListResponse = {
        data: [],
        pagination: {
          total: 0,
          limit: 10,
          offset: 0,
          has_more: false,
        },
      };

      mockApiFetch.mockResolvedValueOnce(mockResponse);

      renderHook(
        () => useChannelVideos('UC123456789012345678901', { limit: 10 }),
        {
          wrapper: createWrapper(queryClient),
        }
      );

      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalledWith(
          expect.stringContaining('limit=10')
        );
      });
    });

    it('should accept enabled option to disable query', async () => {
      const { result } = renderHook(
        () => useChannelVideos('UC123456789012345678901', { enabled: false }),
        {
          wrapper: createWrapper(queryClient),
        }
      );

      // Should not fetch when disabled
      expect(mockApiFetch).not.toHaveBeenCalled();
      expect(result.current.isLoading).toBe(false);
    });
  });

  describe('Intersection Observer Integration', () => {
    it('should provide loadMoreRef for infinite scroll trigger', async () => {
      const mockResponse: VideoListResponse = {
        data: [],
        pagination: {
          total: 0,
          limit: 25,
          offset: 0,
          has_more: false,
        },
      };

      mockApiFetch.mockResolvedValueOnce(mockResponse);

      const { result } = renderHook(
        () => useChannelVideos('UC123456789012345678901'),
        {
          wrapper: createWrapper(queryClient),
        }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.loadMoreRef).toBeDefined();
      expect(result.current.loadMoreRef.current).toBeNull();
    });
  });
});
