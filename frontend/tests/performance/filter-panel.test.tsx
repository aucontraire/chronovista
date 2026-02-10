/**
 * Performance tests for VideoFilters (Filter Panel) Component
 *
 * Tests NFR-001: Filter panel render < 200ms
 *
 * This test suite validates that the filter panel components render
 * within the specified performance threshold using React Testing Library
 * and performance.now() measurements.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderWithProviders } from '../test-utils';
import { VideoFilters } from '../../src/components/VideoFilters';
import { QueryClient } from '@tanstack/react-query';

// Mock hooks to provide fast, consistent data
vi.mock('../../src/hooks/useCategories', () => ({
  useCategories: () => ({
    categories: Array.from({ length: 20 }, (_, i) => ({
      category_id: String(i + 1),
      name: `Category ${i + 1}`,
      assignable: true,
    })),
    isLoading: false,
    isError: false,
    error: null,
  }),
}));

vi.mock('../../src/hooks/useTopics', () => ({
  useTopics: () => ({
    topics: Array.from({ length: 100 }, (_, i) => ({
      topic_id: `/m/topic_${i}`,
      name: `Topic ${i}`,
      parent_topic_id: i > 10 ? `/m/topic_${Math.floor(i / 10)}` : null,
      parent_path: i > 10 ? `Parent ${Math.floor(i / 10)}` : null,
      depth: i > 10 ? 1 : 0,
      video_count: Math.floor(Math.random() * 100),
    })),
    isLoading: false,
    isError: false,
    error: null,
  }),
}));

vi.mock('../../src/hooks/useOnlineStatus', () => ({
  useOnlineStatus: () => true,
}));

// Mock react-router-dom's useSearchParams
const mockSetSearchParams = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useSearchParams: () => [new URLSearchParams(), mockSetSearchParams],
  };
});

describe('VideoFilters Performance (NFR-001)', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    });
    // Reset performance marks
    if (typeof performance !== 'undefined' && performance.clearMarks) {
      performance.clearMarks();
      performance.clearMeasures();
    }
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  describe('Initial Render Performance', () => {
    it('NFR-001: should render filter panel in under 200ms', () => {
      const iterations = 10;
      const renderTimes: number[] = [];

      for (let i = 0; i < iterations; i++) {
        // Clear any previous renders
        document.body.innerHTML = '';

        const startTime = performance.now();

        renderWithProviders(
          <VideoFilters videoCount={100} />,
          { queryClient }
        );

        const endTime = performance.now();
        const renderTime = endTime - startTime;
        renderTimes.push(renderTime);
      }

      // Calculate p95 render time
      renderTimes.sort((a, b) => a - b);
      const p95Index = Math.floor(renderTimes.length * 0.95);
      const p95 = renderTimes[p95Index] ?? renderTimes[renderTimes.length - 1];

      // Calculate average
      const avg = renderTimes.reduce((a, b) => a + b, 0) / renderTimes.length;

      // Log results for debugging
      console.log('\nFilter panel render performance (NFR-001):');
      console.log(`  Average: ${avg.toFixed(1)}ms`);
      console.log(`  p95: ${p95.toFixed(1)}ms`);
      console.log(`  Max: ${Math.max(...renderTimes).toFixed(1)}ms`);
      console.log(`  Min: ${Math.min(...renderTimes).toFixed(1)}ms`);

      // Assert p95 is under 200ms
      expect(p95).toBeLessThan(200);
    });

    it('should render with active filters in under 200ms', () => {
      // Test with pre-populated filters
      const startTime = performance.now();

      renderWithProviders(
        <VideoFilters videoCount={50} />,
        {
          queryClient,
          initialEntries: ['/?tag=music&tag=rock&category=10&topic_id=/m/topic_1'],
        }
      );

      const endTime = performance.now();
      const renderTime = endTime - startTime;

      console.log(`\nFilter panel with active filters: ${renderTime.toFixed(1)}ms`);

      // Should still be under 200ms with active filters
      expect(renderTime).toBeLessThan(200);
    });

    it('should render with maximum filters in under 200ms', () => {
      // Test with maximum number of filters (10 tags, 10 topics, 1 category = 21)
      const tags = Array.from({ length: 10 }, (_, i) => `tag${i}`);
      const topics = Array.from({ length: 10 }, (_, i) => `/m/topic_${i}`);
      const params = new URLSearchParams();
      tags.forEach(tag => params.append('tag', tag));
      topics.forEach(topic => params.append('topic_id', topic));
      params.append('category', '10');

      const startTime = performance.now();

      renderWithProviders(
        <VideoFilters videoCount={10} />,
        {
          queryClient,
          initialEntries: [`/?${params.toString()}`],
        }
      );

      const endTime = performance.now();
      const renderTime = endTime - startTime;

      console.log(`\nFilter panel with max filters: ${renderTime.toFixed(1)}ms`);

      // Should still be under 200ms even with max filters
      expect(renderTime).toBeLessThan(200);
    });
  });

  describe('Component Update Performance', () => {
    it('should update filter count display in under 50ms', async () => {
      const { rerender } = renderWithProviders(
        <VideoFilters videoCount={100} />,
        { queryClient }
      );

      // Measure re-render time with new video count
      const startTime = performance.now();

      rerender(
        <VideoFilters videoCount={50} />
      );

      const endTime = performance.now();
      const updateTime = endTime - startTime;

      console.log(`\nFilter count update: ${updateTime.toFixed(1)}ms`);

      // Updates should be very fast
      expect(updateTime).toBeLessThan(50);
    });
  });
});

describe('Subcomponent Render Performance', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('should handle large topic list without performance degradation', async () => {
    // This test validates that even with many topics, render stays fast
    const iterations = 5;
    const renderTimes: number[] = [];

    for (let i = 0; i < iterations; i++) {
      document.body.innerHTML = '';

      const startTime = performance.now();

      renderWithProviders(
        <VideoFilters videoCount={1000} />,
        { queryClient }
      );

      const endTime = performance.now();
      renderTimes.push(endTime - startTime);
    }

    const avg = renderTimes.reduce((a, b) => a + b, 0) / renderTimes.length;
    const max = Math.max(...renderTimes);

    console.log(`\nLarge topic list render: avg=${avg.toFixed(1)}ms, max=${max.toFixed(1)}ms`);

    // Even with 100 topics (from mock), should render in under 200ms
    expect(avg).toBeLessThan(200);
  });
});
