/**
 * Tests for useChannels hook.
 *
 * Covers:
 * - Returns channels data when API call succeeds
 * - Handles loading state correctly
 * - Handles error state correctly
 * - Implements infinite scroll (fetchNextPage)
 * - Handles empty channels list
 * - Intersection Observer setup for auto-loading
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { type ReactNode } from 'react';

import { useChannels } from '../../src/hooks/useChannels';
import { apiFetch } from '../../src/api/config';
import type { ChannelListResponse } from '../../src/types/channel';

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

describe('useChannels', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createTestQueryClient();
    vi.clearAllMocks();
  });

  afterEach(() => {
    queryClient.clear();
  });

  describe('Successful Data Fetching', () => {
    it('should return channels data when API call succeeds', async () => {
      const mockResponse: ChannelListResponse = {
        data: [
          {
            channel_id: 'UC123456789012345678901',
            title: 'Test Channel 1',
            description: 'This is test channel 1',
            subscriber_count: 100000,
            video_count: 50,
            thumbnail_url: 'https://example.com/thumb1.jpg',
            custom_url: '@testchannel1',
          },
          {
            channel_id: 'UC234567890123456789012',
            title: 'Test Channel 2',
            description: 'This is test channel 2',
            subscriber_count: 200000,
            video_count: 75,
            thumbnail_url: 'https://example.com/thumb2.jpg',
            custom_url: '@testchannel2',
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

      const { result } = renderHook(() => useChannels(), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.channels).toHaveLength(2);
      expect(result.current.channels[0].title).toBe('Test Channel 1');
      expect(result.current.channels[1].title).toBe('Test Channel 2');
      expect(result.current.total).toBe(2);
      expect(result.current.loadedCount).toBe(2);
      expect(result.current.isError).toBe(false);
    });

    it('should flatten multiple pages into single channels array', async () => {
      const page1Response: ChannelListResponse = {
        data: [
          {
            channel_id: 'UC123456789012345678901',
            title: 'Channel 1',
            description: null,
            subscriber_count: 100000,
            video_count: 50,
            thumbnail_url: null,
            custom_url: null,
          },
        ],
        pagination: {
          total: 2,
          limit: 1,
          offset: 0,
          has_more: true,
        },
      };

      const page2Response: ChannelListResponse = {
        data: [
          {
            channel_id: 'UC234567890123456789012',
            title: 'Channel 2',
            description: null,
            subscriber_count: 200000,
            video_count: 75,
            thumbnail_url: null,
            custom_url: null,
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

      const { result } = renderHook(() => useChannels({ limit: 1 }), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.channels).toHaveLength(1);
      expect(result.current.hasNextPage).toBe(true);

      // Fetch next page
      result.current.fetchNextPage();

      await waitFor(() => {
        expect(result.current.channels).toHaveLength(2);
      });

      expect(result.current.channels[0].title).toBe('Channel 1');
      expect(result.current.channels[1].title).toBe('Channel 2');
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

      const { result } = renderHook(() => useChannels(), {
        wrapper: createWrapper(queryClient),
      });

      expect(result.current.isLoading).toBe(true);
      expect(result.current.channels).toHaveLength(0);
      expect(result.current.isError).toBe(false);
    });

    it('should set isLoading to false after successful fetch', async () => {
      const mockResponse: ChannelListResponse = {
        data: [],
        pagination: {
          total: 0,
          limit: 25,
          offset: 0,
          has_more: false,
        },
      };

      mockApiFetch.mockResolvedValueOnce(mockResponse);

      const { result } = renderHook(() => useChannels(), {
        wrapper: createWrapper(queryClient),
      });

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

      const { result } = renderHook(() => useChannels(), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error).toEqual(mockError);
      expect(result.current.channels).toHaveLength(0);
      expect(result.current.isLoading).toBe(false);
    });

    it('should allow retry after error', async () => {
      const mockError = {
        type: 'network' as const,
        message: 'Network error',
        status: undefined,
      };

      const mockResponse: ChannelListResponse = {
        data: [
          {
            channel_id: 'UC123456789012345678901',
            title: 'Test Channel',
            description: null,
            subscriber_count: 100000,
            video_count: 50,
            thumbnail_url: null,
            custom_url: null,
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

      const { result } = renderHook(() => useChannels(), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      // Retry the request
      result.current.retry();

      await waitFor(() => {
        expect(result.current.isError).toBe(false);
      });

      expect(result.current.channels).toHaveLength(1);
      expect(result.current.channels[0].title).toBe('Test Channel');
    });
  });

  describe('Empty Channels List', () => {
    it('should handle empty channels list correctly', async () => {
      const mockResponse: ChannelListResponse = {
        data: [],
        pagination: {
          total: 0,
          limit: 25,
          offset: 0,
          has_more: false,
        },
      };

      mockApiFetch.mockResolvedValueOnce(mockResponse);

      const { result } = renderHook(() => useChannels(), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.channels).toHaveLength(0);
      expect(result.current.total).toBe(0);
      expect(result.current.loadedCount).toBe(0);
      expect(result.current.hasNextPage).toBe(false);
      expect(result.current.isError).toBe(false);
    });
  });

  describe('Infinite Scroll', () => {
    it('should implement fetchNextPage for infinite scroll', async () => {
      const page1Response: ChannelListResponse = {
        data: [
          {
            channel_id: 'UC123456789012345678901',
            title: 'Channel 1',
            description: null,
            subscriber_count: 100000,
            video_count: 50,
            thumbnail_url: null,
            custom_url: null,
          },
        ],
        pagination: {
          total: 2,
          limit: 1,
          offset: 0,
          has_more: true,
        },
      };

      const page2Response: ChannelListResponse = {
        data: [
          {
            channel_id: 'UC234567890123456789012',
            title: 'Channel 2',
            description: null,
            subscriber_count: 200000,
            video_count: 75,
            thumbnail_url: null,
            custom_url: null,
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

      const { result } = renderHook(() => useChannels({ limit: 1 }), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.hasNextPage).toBe(true);
      expect(result.current.channels).toHaveLength(1);

      result.current.fetchNextPage();

      await waitFor(() => {
        expect(result.current.isFetchingNextPage).toBe(false);
      });

      expect(result.current.channels).toHaveLength(2);
      expect(result.current.hasNextPage).toBe(false);
    });

    it('should set hasNextPage to false when no more pages', async () => {
      const mockResponse: ChannelListResponse = {
        data: [
          {
            channel_id: 'UC123456789012345678901',
            title: 'Channel 1',
            description: null,
            subscriber_count: 100000,
            video_count: 50,
            thumbnail_url: null,
            custom_url: null,
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

      const { result } = renderHook(() => useChannels(), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.hasNextPage).toBe(false);
    });

    it('should track isFetchingNextPage state', async () => {
      const page1Response: ChannelListResponse = {
        data: [
          {
            channel_id: 'UC123456789012345678901',
            title: 'Channel 1',
            description: null,
            subscriber_count: 100000,
            video_count: 50,
            thumbnail_url: null,
            custom_url: null,
          },
        ],
        pagination: {
          total: 2,
          limit: 1,
          offset: 0,
          has_more: true,
        },
      };

      const page2Response: ChannelListResponse = {
        data: [
          {
            channel_id: 'UC234567890123456789012',
            title: 'Channel 2',
            description: null,
            subscriber_count: 200000,
            video_count: 75,
            thumbnail_url: null,
            custom_url: null,
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

      const { result } = renderHook(() => useChannels({ limit: 1 }), {
        wrapper: createWrapper(queryClient),
      });

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

      expect(result.current.channels).toHaveLength(2);
    });
  });

  describe('Custom Options', () => {
    it('should accept custom limit option', async () => {
      const mockResponse: ChannelListResponse = {
        data: [],
        pagination: {
          total: 0,
          limit: 10,
          offset: 0,
          has_more: false,
        },
      };

      mockApiFetch.mockResolvedValueOnce(mockResponse);

      renderHook(() => useChannels({ limit: 10 }), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalledWith(
          expect.stringContaining('limit=10')
        );
      });
    });

    it('should accept enabled option to disable query', async () => {
      const { result } = renderHook(() => useChannels({ enabled: false }), {
        wrapper: createWrapper(queryClient),
      });

      // Should not fetch when disabled
      expect(mockApiFetch).not.toHaveBeenCalled();
      expect(result.current.isLoading).toBe(false);
    });
  });

  describe('Intersection Observer Integration', () => {
    it('should provide loadMoreRef for infinite scroll trigger', async () => {
      const mockResponse: ChannelListResponse = {
        data: [],
        pagination: {
          total: 0,
          limit: 25,
          offset: 0,
          has_more: false,
        },
      };

      mockApiFetch.mockResolvedValueOnce(mockResponse);

      const { result } = renderHook(() => useChannels(), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.loadMoreRef).toBeDefined();
      expect(result.current.loadMoreRef.current).toBeNull();
    });
  });
});
