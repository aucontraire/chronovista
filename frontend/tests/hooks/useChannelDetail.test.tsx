/**
 * Tests for useChannelDetail hook.
 *
 * Covers:
 * - Returns channel data when API call succeeds
 * - Handles loading state correctly
 * - Handles error state correctly
 * - Handles 404 for non-existent channel (EC-005)
 * - Returns undefined when channelId is not provided
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { type ReactNode } from 'react';

import { useChannelDetail } from '../../src/hooks/useChannelDetail';
import { apiFetch } from '../../src/api/config';
import type { ChannelDetailResponse } from '../../src/types/channel';

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

describe('useChannelDetail', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createTestQueryClient();
    vi.clearAllMocks();
  });

  afterEach(() => {
    queryClient.clear();
  });

  describe('Successful Data Fetching', () => {
    it('should return channel data when API call succeeds', async () => {
      const mockResponse: ChannelDetailResponse = {
        data: {
          channel_id: 'UC123456789012345678901',
          title: 'Test Channel',
          description: 'This is a test channel description',
          subscriber_count: 1500000,
          video_count: 250,
          thumbnail_url: 'https://example.com/thumbnail.jpg',
          custom_url: '@testchannel',
          default_language: 'en',
          country: 'US',
          is_subscribed: true,
          created_at: '2024-01-01T00:00:00Z',
          updated_at: '2024-01-15T10:30:00Z',
        },
      };

      mockApiFetch.mockResolvedValueOnce(mockResponse);

      const { result } = renderHook(
        () => useChannelDetail('UC123456789012345678901'),
        {
          wrapper: createWrapper(queryClient),
        }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.data).toEqual(mockResponse.data);
      expect(result.current.data?.title).toBe('Test Channel');
      expect(result.current.data?.is_subscribed).toBe(true);
      expect(result.current.data?.subscriber_count).toBe(1500000);
      expect(result.current.isError).toBe(false);
    });

    it('should return channel with all metadata fields populated', async () => {
      const mockResponse: ChannelDetailResponse = {
        data: {
          channel_id: 'UC234567890123456789012',
          title: 'Complete Channel',
          description: 'Full description text',
          subscriber_count: 5000000,
          video_count: 1000,
          thumbnail_url: 'https://example.com/complete.jpg',
          custom_url: '@complete',
          default_language: 'es',
          country: 'ES',
          is_subscribed: false,
          created_at: '2023-06-15T12:00:00Z',
          updated_at: '2024-02-01T08:00:00Z',
        },
      };

      mockApiFetch.mockResolvedValueOnce(mockResponse);

      const { result } = renderHook(
        () => useChannelDetail('UC234567890123456789012'),
        {
          wrapper: createWrapper(queryClient),
        }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      const channel = result.current.data;
      expect(channel).toBeDefined();
      expect(channel?.channel_id).toBe('UC234567890123456789012');
      expect(channel?.title).toBe('Complete Channel');
      expect(channel?.description).toBe('Full description text');
      expect(channel?.subscriber_count).toBe(5000000);
      expect(channel?.video_count).toBe(1000);
      expect(channel?.thumbnail_url).toBe('https://example.com/complete.jpg');
      expect(channel?.custom_url).toBe('@complete');
      expect(channel?.default_language).toBe('es');
      expect(channel?.country).toBe('ES');
      expect(channel?.is_subscribed).toBe(false);
      expect(channel?.created_at).toBe('2023-06-15T12:00:00Z');
      expect(channel?.updated_at).toBe('2024-02-01T08:00:00Z');
    });

    it('should handle channel with null optional fields (EC-004)', async () => {
      const mockResponse: ChannelDetailResponse = {
        data: {
          channel_id: 'UC345678901234567890123',
          title: 'Minimal Channel',
          description: null,
          subscriber_count: null,
          video_count: null,
          thumbnail_url: null,
          custom_url: null,
          default_language: null,
          country: null,
          is_subscribed: false,
          created_at: '2024-01-01T00:00:00Z',
          updated_at: '2024-01-01T00:00:00Z',
        },
      };

      mockApiFetch.mockResolvedValueOnce(mockResponse);

      const { result } = renderHook(
        () => useChannelDetail('UC345678901234567890123'),
        {
          wrapper: createWrapper(queryClient),
        }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      const channel = result.current.data;
      expect(channel).toBeDefined();
      expect(channel?.title).toBe('Minimal Channel');
      expect(channel?.description).toBeNull();
      expect(channel?.subscriber_count).toBeNull();
      expect(channel?.video_count).toBeNull();
      expect(channel?.thumbnail_url).toBeNull();
      expect(channel?.custom_url).toBeNull();
      expect(channel?.default_language).toBeNull();
      expect(channel?.country).toBeNull();
      expect(result.current.isError).toBe(false);
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
        () => useChannelDetail('UC123456789012345678901'),
        {
          wrapper: createWrapper(queryClient),
        }
      );

      expect(result.current.isLoading).toBe(true);
      expect(result.current.data).toBeUndefined();
      expect(result.current.isError).toBe(false);
    });

    it('should set isLoading to false after successful fetch', async () => {
      const mockResponse: ChannelDetailResponse = {
        data: {
          channel_id: 'UC123456789012345678901',
          title: 'Test Channel',
          description: null,
          subscriber_count: null,
          video_count: null,
          thumbnail_url: null,
          custom_url: null,
          default_language: null,
          country: null,
          is_subscribed: false,
          created_at: '2024-01-01T00:00:00Z',
          updated_at: '2024-01-01T00:00:00Z',
        },
      };

      mockApiFetch.mockResolvedValueOnce(mockResponse);

      const { result } = renderHook(
        () => useChannelDetail('UC123456789012345678901'),
        {
          wrapper: createWrapper(queryClient),
        }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.isError).toBe(false);
      expect(result.current.data).toBeDefined();
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
        () => useChannelDetail('UC123456789012345678901'),
        {
          wrapper: createWrapper(queryClient),
        }
      );

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error).toEqual(mockError);
      expect(result.current.data).toBeUndefined();
      expect(result.current.isLoading).toBe(false);
    });

    it('should allow retry after error', async () => {
      const mockError = {
        type: 'network' as const,
        message: 'Network error',
        status: undefined,
      };

      const mockResponse: ChannelDetailResponse = {
        data: {
          channel_id: 'UC123456789012345678901',
          title: 'Test Channel',
          description: null,
          subscriber_count: null,
          video_count: null,
          thumbnail_url: null,
          custom_url: null,
          default_language: null,
          country: null,
          is_subscribed: false,
          created_at: '2024-01-01T00:00:00Z',
          updated_at: '2024-01-01T00:00:00Z',
        },
      };

      // First call fails, second succeeds
      mockApiFetch.mockRejectedValueOnce(mockError).mockResolvedValueOnce(mockResponse);

      const { result } = renderHook(
        () => useChannelDetail('UC123456789012345678901'),
        {
          wrapper: createWrapper(queryClient),
        }
      );

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      // Retry the request
      result.current.refetch();

      await waitFor(() => {
        expect(result.current.isError).toBe(false);
      });

      expect(result.current.data?.title).toBe('Test Channel');
    });
  });

  describe('404 Not Found (EC-005)', () => {
    it('should handle 404 for non-existent channel', async () => {
      const mockError = {
        type: 'server' as const,
        message: 'Channel not found',
        status: 404,
      };

      mockApiFetch.mockRejectedValueOnce(mockError);

      const { result } = renderHook(
        () => useChannelDetail('UC999999999999999999999'),
        {
          wrapper: createWrapper(queryClient),
        }
      );

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error?.status).toBe(404);
      expect(result.current.error?.message).toContain('not found');
      expect(result.current.data).toBeUndefined();
    });

    it('should distinguish 404 from other errors', async () => {
      const mock404Error = {
        type: 'server' as const,
        message: 'Channel not found',
        status: 404,
      };

      mockApiFetch.mockRejectedValueOnce(mock404Error);

      const { result: result404 } = renderHook(
        () => useChannelDetail('UC999999999999999999999'),
        {
          wrapper: createWrapper(queryClient),
        }
      );

      await waitFor(() => {
        expect(result404.current.isError).toBe(true);
      });

      expect(result404.current.error?.status).toBe(404);

      // Test with 500 error
      const mock500Error = {
        type: 'server' as const,
        message: 'Internal server error',
        status: 500,
      };

      const queryClient2 = createTestQueryClient();
      mockApiFetch.mockRejectedValueOnce(mock500Error);

      const { result: result500 } = renderHook(
        () => useChannelDetail('UC123456789012345678901'),
        {
          wrapper: createWrapper(queryClient2),
        }
      );

      await waitFor(() => {
        expect(result500.current.isError).toBe(true);
      });

      expect(result500.current.error?.status).toBe(500);
      expect(result500.current.error?.status).not.toBe(404);
    });
  });

  describe('Undefined Channel ID', () => {
    it('should return undefined when channelId is not provided', () => {
      const { result } = renderHook(() => useChannelDetail(undefined), {
        wrapper: createWrapper(queryClient),
      });

      expect(result.current.data).toBeUndefined();
      expect(result.current.isLoading).toBe(false);
      expect(result.current.isError).toBe(false);
      expect(mockApiFetch).not.toHaveBeenCalled();
    });

    it('should not fetch when channelId is empty string', () => {
      const { result } = renderHook(() => useChannelDetail(''), {
        wrapper: createWrapper(queryClient),
      });

      expect(result.current.data).toBeUndefined();
      expect(result.current.isLoading).toBe(false);
      expect(mockApiFetch).not.toHaveBeenCalled();
    });

    it('should be enabled when valid channelId is provided', async () => {
      const mockResponse: ChannelDetailResponse = {
        data: {
          channel_id: 'UC123456789012345678901',
          title: 'Test Channel',
          description: null,
          subscriber_count: null,
          video_count: null,
          thumbnail_url: null,
          custom_url: null,
          default_language: null,
          country: null,
          is_subscribed: false,
          created_at: '2024-01-01T00:00:00Z',
          updated_at: '2024-01-01T00:00:00Z',
        },
      };

      mockApiFetch.mockResolvedValueOnce(mockResponse);

      const { result } = renderHook(
        () => useChannelDetail('UC123456789012345678901'),
        {
          wrapper: createWrapper(queryClient),
        }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(mockApiFetch).toHaveBeenCalledWith(
        expect.stringContaining('/channels/UC123456789012345678901')
      );
    });
  });

  describe('Query Key Management', () => {
    it('should use channelId in query key', async () => {
      const mockResponse: ChannelDetailResponse = {
        data: {
          channel_id: 'UC123456789012345678901',
          title: 'Test Channel',
          description: null,
          subscriber_count: null,
          video_count: null,
          thumbnail_url: null,
          custom_url: null,
          default_language: null,
          country: null,
          is_subscribed: false,
          created_at: '2024-01-01T00:00:00Z',
          updated_at: '2024-01-01T00:00:00Z',
        },
      };

      mockApiFetch.mockResolvedValueOnce(mockResponse);

      renderHook(() => useChannelDetail('UC123456789012345678901'), {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalled();
      });

      // Verify query was cached (can be fetched from cache)
      const cachedData = queryClient.getQueryData([
        'channel',
        'UC123456789012345678901',
      ]);
      expect(cachedData).toBeDefined();
    });

    it('should cache different channels separately', async () => {
      const mockResponse1: ChannelDetailResponse = {
        data: {
          channel_id: 'UC123456789012345678901',
          title: 'Channel 1',
          description: null,
          subscriber_count: null,
          video_count: null,
          thumbnail_url: null,
          custom_url: null,
          default_language: null,
          country: null,
          is_subscribed: false,
          created_at: '2024-01-01T00:00:00Z',
          updated_at: '2024-01-01T00:00:00Z',
        },
      };

      const mockResponse2: ChannelDetailResponse = {
        data: {
          channel_id: 'UC234567890123456789012',
          title: 'Channel 2',
          description: null,
          subscriber_count: null,
          video_count: null,
          thumbnail_url: null,
          custom_url: null,
          default_language: null,
          country: null,
          is_subscribed: false,
          created_at: '2024-01-01T00:00:00Z',
          updated_at: '2024-01-01T00:00:00Z',
        },
      };

      mockApiFetch
        .mockResolvedValueOnce(mockResponse1)
        .mockResolvedValueOnce(mockResponse2);

      const { result: result1 } = renderHook(
        () => useChannelDetail('UC123456789012345678901'),
        {
          wrapper: createWrapper(queryClient),
        }
      );

      const { result: result2 } = renderHook(
        () => useChannelDetail('UC234567890123456789012'),
        {
          wrapper: createWrapper(queryClient),
        }
      );

      await waitFor(() => {
        expect(result1.current.isLoading).toBe(false);
        expect(result2.current.isLoading).toBe(false);
      });

      expect(result1.current.data?.title).toBe('Channel 1');
      expect(result2.current.data?.title).toBe('Channel 2');
    });
  });
});
