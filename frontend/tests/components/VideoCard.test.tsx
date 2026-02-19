/**
 * Tests for VideoCard component - Image Proxy URLs (Feature 026, T032).
 *
 * Covers:
 * - Thumbnail renders with proxy URL pattern
 * - 16:9 aspect ratio class (aspect-video)
 * - Lazy loading attribute
 * - Error fallback to SVG placeholder
 * - No YouTube CDN URLs in rendered output
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { VideoCard } from '../../src/components/VideoCard';
import type { VideoListItem } from '../../src/types/video';

/**
 * Test factory to generate VideoListItem test data.
 */
function createTestVideo(overrides: Partial<VideoListItem> = {}): VideoListItem {
  return {
    video_id: 'test-video-123',
    title: 'Test Video Title',
    channel_id: 'channel-1',
    channel_title: 'Test Channel',
    upload_date: '2024-01-15T00:00:00Z',
    duration: 300,
    view_count: 1000,
    transcript_summary: {
      count: 1,
      languages: ['en'],
      has_manual: true,
    },
    availability_status: 'available',
    ...overrides,
  };
}

/**
 * Helper to render VideoCard with MemoryRouter.
 */
function renderVideoCard(video: VideoListItem) {
  return render(
    <MemoryRouter>
      <VideoCard video={video} />
    </MemoryRouter>
  );
}

describe('VideoCard - Image Proxy URLs (Feature 026, T032)', () => {
  describe('Thumbnail Proxy URL', () => {
    it('should render thumbnail with proxy URL /api/v1/images/videos/{video_id}?quality=mqdefault', () => {
      const video = createTestVideo({ video_id: 'test-video-123' });
      renderVideoCard(video);

      const thumbnail = screen.getByRole('img', { name: /test video title/i });
      const src = thumbnail.getAttribute('src');

      // Verify proxy URL pattern
      expect(src).toMatch(/\/images\/videos\/test-video-123\?quality=mqdefault$/);
      expect(src).toContain('test-video-123');
      expect(src).toContain('quality=mqdefault');
    });

    it('should include video_id in proxy URL path', () => {
      const video = createTestVideo({ video_id: 'abc-xyz-456' });
      renderVideoCard(video);

      const thumbnail = screen.getByRole('img');
      const src = thumbnail.getAttribute('src');

      expect(src).toContain('/images/videos/abc-xyz-456');
    });

    it('should append quality query parameter', () => {
      const video = createTestVideo();
      renderVideoCard(video);

      const thumbnail = screen.getByRole('img');
      const src = thumbnail.getAttribute('src');

      expect(src).toContain('?quality=mqdefault');
    });
  });

  describe('Aspect Ratio', () => {
    it('should have 16:9 aspect ratio class (aspect-video)', () => {
      const video = createTestVideo();
      renderVideoCard(video);

      const thumbnail = screen.getByRole('img');

      // Verify aspect-video class is present
      expect(thumbnail).toHaveClass('aspect-video');
    });

    it('should maintain aspect ratio across different videos', () => {
      const videos = [
        createTestVideo({ video_id: 'video-1' }),
        createTestVideo({ video_id: 'video-2' }),
        createTestVideo({ video_id: 'video-3' }),
      ];

      videos.forEach((video) => {
        const { unmount } = renderVideoCard(video);
        const thumbnail = screen.getByRole('img');
        expect(thumbnail).toHaveClass('aspect-video');
        unmount();
      });
    });
  });

  describe('Lazy Loading', () => {
    it('should have loading="lazy" attribute', () => {
      const video = createTestVideo();
      renderVideoCard(video);

      const thumbnail = screen.getByRole('img');
      expect(thumbnail).toHaveAttribute('loading', 'lazy');
    });
  });

  describe('Error Fallback', () => {
    it('should render SVG placeholder on image error', () => {
      const video = createTestVideo();
      renderVideoCard(video);

      const thumbnail = screen.getByRole('img');

      // Simulate image load error
      const errorEvent = new Event('error', { bubbles: true });
      thumbnail.dispatchEvent(errorEvent);

      // After error, should fall back to placeholder
      // The onError handler sets src to PLACEHOLDER_THUMBNAIL (SVG data URI)
      const src = thumbnail.getAttribute('src');
      expect(src).toContain('data:image/svg+xml');
    });

    it('should fallback to placeholder with play icon SVG', () => {
      const video = createTestVideo();
      renderVideoCard(video);

      const thumbnail = screen.getByRole('img');

      // Trigger error
      const errorEvent = new Event('error', { bubbles: true });
      thumbnail.dispatchEvent(errorEvent);

      const src = thumbnail.getAttribute('src');
      // Placeholder should be an SVG data URI
      expect(src).toMatch(/^data:image\/svg\+xml/);
    });
  });

  describe('No YouTube CDN URLs', () => {
    it('should NOT include ytimg.com in rendered output', () => {
      const video = createTestVideo();
      renderVideoCard(video);

      const thumbnail = screen.getByRole('img');
      const src = thumbnail.getAttribute('src');

      expect(src).not.toContain('ytimg.com');
    });

    it('should NOT include ggpht.com in rendered output', () => {
      const video = createTestVideo();
      renderVideoCard(video);

      const thumbnail = screen.getByRole('img');
      const src = thumbnail.getAttribute('src');

      expect(src).not.toContain('ggpht.com');
    });

    it('should NOT include youtube.com in rendered output', () => {
      const video = createTestVideo();
      renderVideoCard(video);

      const thumbnail = screen.getByRole('img');
      const src = thumbnail.getAttribute('src');

      expect(src).not.toContain('youtube.com');
    });

    it('should only use local proxy URL', () => {
      const video = createTestVideo();
      renderVideoCard(video);

      const thumbnail = screen.getByRole('img');
      const src = thumbnail.getAttribute('src');

      // Should start with API base URL or relative path
      expect(src).toMatch(/^(http:\/\/localhost|\/).*\/images\/videos\//);
    });
  });

  describe('Accessibility', () => {
    it('should have alt text with video title', () => {
      const video = createTestVideo({ title: 'My Awesome Video' });
      renderVideoCard(video);

      const thumbnail = screen.getByRole('img', { name: /my awesome video/i });
      expect(thumbnail).toHaveAttribute('alt', 'My Awesome Video');
    });

    it('should have alt text for unavailable videos', () => {
      const video = createTestVideo({
        title: '',
        availability_status: 'deleted',
      });
      renderVideoCard(video);

      const thumbnail = screen.getByRole('img', { name: /video thumbnail/i });
      expect(thumbnail).toHaveAttribute('alt');
    });
  });

  describe('Edge Cases', () => {
    it('should handle video with special characters in video_id', () => {
      const video = createTestVideo({ video_id: 'dQw4w9WgXcQ' });
      renderVideoCard(video);

      const thumbnail = screen.getByRole('img');
      const src = thumbnail.getAttribute('src');

      expect(src).toContain('/images/videos/dQw4w9WgXcQ');
      expect(src).toContain('?quality=mqdefault');
    });

    it('should render correctly for unavailable videos', () => {
      const video = createTestVideo({
        availability_status: 'deleted',
        title: 'Deleted Video',
      });
      renderVideoCard(video);

      const thumbnail = screen.getByRole('img');
      const src = thumbnail.getAttribute('src');

      // Should still use proxy URL even for unavailable videos
      expect(src).toMatch(/\/images\/videos\//);
      expect(src).toContain('?quality=mqdefault');
    });

    it('should render correctly for private videos', () => {
      const video = createTestVideo({
        availability_status: 'private',
      });
      renderVideoCard(video);

      const thumbnail = screen.getByRole('img');
      const src = thumbnail.getAttribute('src');

      // Should still use proxy URL
      expect(src).toMatch(/\/images\/videos\//);
    });

    it('should handle empty title gracefully', () => {
      const video = createTestVideo({ title: '' });
      renderVideoCard(video);

      const thumbnail = screen.getByRole('img');
      expect(thumbnail).toBeInTheDocument();
      expect(thumbnail).toHaveAttribute('alt');
    });
  });

  describe('Image Dimensions', () => {
    it('should use full width with aspect ratio', () => {
      const video = createTestVideo();
      renderVideoCard(video);

      const thumbnail = screen.getByRole('img');

      // Should have full width class
      expect(thumbnail).toHaveClass('w-full');
    });

    it('should have object-cover for image fitting', () => {
      const video = createTestVideo();
      renderVideoCard(video);

      const thumbnail = screen.getByRole('img');

      // Should use object-cover to maintain aspect ratio
      expect(thumbnail).toHaveClass('object-cover');
    });
  });

  describe('Consistent Quality Parameter', () => {
    it('should always use mqdefault quality', () => {
      const videos = [
        createTestVideo({ video_id: 'video-1' }),
        createTestVideo({ video_id: 'video-2' }),
        createTestVideo({ video_id: 'video-3' }),
      ];

      videos.forEach((video) => {
        const { unmount } = renderVideoCard(video);
        const thumbnail = screen.getByRole('img');
        const src = thumbnail.getAttribute('src');
        expect(src).toContain('quality=mqdefault');
        unmount();
      });
    });

    it('should not use other quality parameters', () => {
      const video = createTestVideo();
      renderVideoCard(video);

      const thumbnail = screen.getByRole('img');
      const src = thumbnail.getAttribute('src');

      // Should NOT use other YouTube quality parameters
      expect(src).not.toContain('maxresdefault');
      expect(src).not.toContain('sddefault');
      expect(src).not.toContain('hqdefault');
      expect(src).not.toContain('default.jpg');
    });
  });
});
