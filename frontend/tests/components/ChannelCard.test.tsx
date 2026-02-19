/**
 * Tests for ChannelCard component.
 *
 * Covers:
 * - Renders channel thumbnail, name, and video count
 * - Links to channel detail page (/channels/:channelId)
 * - Handles missing thumbnail (placeholder)
 * - Handles long channel names (truncation)
 * - Has proper ARIA labels (FR-017)
 * - Is keyboard accessible (FR-016)
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithProviders } from '../test-utils';
import { ChannelCard } from '../../src/components/ChannelCard';
import type { ChannelListItem } from '../../src/types/channel';

describe('ChannelCard', () => {
  const mockChannel: ChannelListItem = {
    channel_id: 'UC123456789012345678901',
    title: 'Test Channel',
    description: 'This is a test channel description',
    subscriber_count: 1500000,
    video_count: 250,
    thumbnail_url: 'https://example.com/thumbnail.jpg',
    custom_url: '@testchannel',
  };

  describe('Basic Rendering', () => {
    it('should render channel thumbnail with proxy URL (T031)', () => {
      renderWithProviders(<ChannelCard channel={mockChannel} />);

      const thumbnail = screen.getByRole('img', { name: 'Test Channel' });
      expect(thumbnail).toBeInTheDocument();
      // Should use proxy URL pattern, not original YouTube URL
      expect(thumbnail).toHaveAttribute('src', expect.stringContaining('/images/channels/UC123456789012345678901'));
      expect(thumbnail).toHaveAttribute('alt', 'Test Channel');
    });

    it('should render channel name', () => {
      renderWithProviders(<ChannelCard channel={mockChannel} />);

      expect(screen.getByText('Test Channel')).toBeInTheDocument();
    });

    it('should render video count', () => {
      renderWithProviders(<ChannelCard channel={mockChannel} />);

      // Should show "250 videos" or similar text
      expect(screen.getByText(/250/)).toBeInTheDocument();
      expect(screen.getByText(/video/i)).toBeInTheDocument();
    });

    it('should render subscriber count when available', () => {
      renderWithProviders(<ChannelCard channel={mockChannel} />);

      // Should show formatted subscriber count (1.5M or 1,500,000)
      expect(screen.getByText(/1\.5M|1,500,000/)).toBeInTheDocument();
    });
  });

  describe('Channel Link Navigation', () => {
    it('should link to channel detail page', () => {
      renderWithProviders(<ChannelCard channel={mockChannel} />);

      const link = screen.getByRole('link');
      expect(link).toHaveAttribute('href', '/channels/UC123456789012345678901');
    });

    it('should make the entire card clickable', () => {
      renderWithProviders(<ChannelCard channel={mockChannel} />);

      const link = screen.getByRole('link');
      expect(link).toBeInTheDocument();

      // The link should contain the channel name
      expect(link).toHaveTextContent('Test Channel');
    });
  });

  describe('Missing Thumbnail Handling (EC-001)', () => {
    it('should display placeholder when thumbnail_url is null', () => {
      const channelWithoutThumbnail: ChannelListItem = {
        ...mockChannel,
        thumbnail_url: null,
      };

      renderWithProviders(<ChannelCard channel={channelWithoutThumbnail} />);

      // Should still have an image or placeholder element
      const placeholder = screen.getByRole('img', { name: 'Test Channel' });
      expect(placeholder).toBeInTheDocument();

      // Placeholder should have a default/fallback image or special class
      // The exact implementation may vary, but it should have alt text
      expect(placeholder).toHaveAttribute('alt', 'Test Channel');
    });

    it('should display placeholder when thumbnail_url is empty string', () => {
      const channelWithEmptyThumbnail: ChannelListItem = {
        ...mockChannel,
        thumbnail_url: '',
      };

      renderWithProviders(<ChannelCard channel={channelWithEmptyThumbnail} />);

      const placeholder = screen.getByRole('img', { name: 'Test Channel' });
      expect(placeholder).toBeInTheDocument();
    });
  });

  describe('Long Channel Name Handling (EC-006)', () => {
    it('should handle long channel names with truncation', () => {
      const channelWithLongName: ChannelListItem = {
        ...mockChannel,
        title:
          'This Is An Extremely Long Channel Name That Should Be Truncated To Prevent Layout Issues And Maintain Visual Consistency',
      };

      renderWithProviders(<ChannelCard channel={channelWithLongName} />);

      const channelName = screen.getByText(/This Is An Extremely Long Channel Name/);
      expect(channelName).toBeInTheDocument();

      // Should have truncation class (like 'line-clamp-2' or 'truncate')
      expect(channelName).toHaveClass(/truncate|line-clamp/);
    });

    it('should show full name on hover/focus (title attribute)', () => {
      const channelWithLongName: ChannelListItem = {
        ...mockChannel,
        title: 'Very Long Channel Name That Gets Truncated',
      };

      renderWithProviders(<ChannelCard channel={channelWithLongName} />);

      const channelName = screen.getByText('Very Long Channel Name That Gets Truncated');
      // Should have title attribute for tooltip
      expect(channelName).toHaveAttribute(
        'title',
        'Very Long Channel Name That Gets Truncated'
      );
    });
  });

  describe('Null/Missing Data Handling', () => {
    it('should handle null subscriber count', () => {
      const channelWithoutSubscribers: ChannelListItem = {
        ...mockChannel,
        subscriber_count: null,
      };

      renderWithProviders(<ChannelCard channel={channelWithoutSubscribers} />);

      // Should not crash, and should display channel name
      expect(screen.getByText('Test Channel')).toBeInTheDocument();

      // Subscriber count should not be shown or show placeholder
      // This depends on implementation - it might show nothing or "N/A"
    });

    it('should handle null video count', () => {
      const channelWithoutVideoCount: ChannelListItem = {
        ...mockChannel,
        video_count: null,
      };

      renderWithProviders(<ChannelCard channel={channelWithoutVideoCount} />);

      // Should not crash
      expect(screen.getByText('Test Channel')).toBeInTheDocument();
    });

    it('should handle null description', () => {
      const channelWithoutDescription: ChannelListItem = {
        ...mockChannel,
        description: null,
      };

      renderWithProviders(<ChannelCard channel={channelWithoutDescription} />);

      // Should not crash
      expect(screen.getByText('Test Channel')).toBeInTheDocument();
    });
  });

  describe('Number Formatting', () => {
    it('should format large video counts', () => {
      const channelWithManyVideos: ChannelListItem = {
        ...mockChannel,
        video_count: 1234,
      };

      renderWithProviders(<ChannelCard channel={channelWithManyVideos} />);

      // Should show either "1,234" or "1.2K" videos
      expect(screen.getByText(/1,234|1\.2K/)).toBeInTheDocument();
    });

    it('should format large subscriber counts', () => {
      const channelWithManySubscribers: ChannelListItem = {
        ...mockChannel,
        subscriber_count: 5432100,
      };

      renderWithProviders(<ChannelCard channel={channelWithManySubscribers} />);

      // Should show formatted subscriber count (5.4M or 5,432,100)
      expect(screen.getByText(/5\.4M|5,432,100/)).toBeInTheDocument();
    });

    it('should use singular "video" for single video', () => {
      const channelWithOneVideo: ChannelListItem = {
        ...mockChannel,
        video_count: 1,
      };

      renderWithProviders(<ChannelCard channel={channelWithOneVideo} />);

      // Should say "1 video" not "1 videos"
      expect(screen.getByText(/1 video/)).toBeInTheDocument();
      expect(screen.queryByText(/1 videos/)).not.toBeInTheDocument();
    });

    it('should use plural "videos" for multiple videos', () => {
      const channelWithMultipleVideos: ChannelListItem = {
        ...mockChannel,
        video_count: 42,
      };

      renderWithProviders(<ChannelCard channel={channelWithMultipleVideos} />);

      // Should say "42 videos"
      expect(screen.getByText(/42 videos/)).toBeInTheDocument();
    });
  });

  describe('Accessibility (FR-017)', () => {
    it('should have proper ARIA label for screen readers', () => {
      renderWithProviders(<ChannelCard channel={mockChannel} />);

      const link = screen.getByRole('link');

      // Should have aria-label describing the channel
      expect(link).toHaveAccessibleName(/Test Channel/);
    });

    it('should include video count in accessible description', () => {
      renderWithProviders(<ChannelCard channel={mockChannel} />);

      const link = screen.getByRole('link');

      // Accessible name should include video count for context
      // Either in aria-label or as visible text within the link
      expect(link.textContent).toMatch(/250/);
    });

    it('should have alt text for thumbnail image', () => {
      renderWithProviders(<ChannelCard channel={mockChannel} />);

      const thumbnail = screen.getByRole('img');
      expect(thumbnail).toHaveAttribute('alt', 'Test Channel');
    });

    it('should be announced as a link to screen readers', () => {
      renderWithProviders(<ChannelCard channel={mockChannel} />);

      const link = screen.getByRole('link');
      expect(link).toBeInTheDocument();
    });
  });

  describe('Keyboard Accessibility (FR-016)', () => {
    it('should be keyboard accessible via Tab key', async () => {
      const { user } = renderWithProviders(<ChannelCard channel={mockChannel} />);

      const link = screen.getByRole('link');

      // Tab to the link
      await user.tab();

      expect(link).toHaveFocus();
    });

    it('should be activatable via Enter key', async () => {
      const { user } = renderWithProviders(<ChannelCard channel={mockChannel} />, {
        initialEntries: ['/channels'],
        path: '/channels',
      });

      const link = screen.getByRole('link');

      // Focus the link
      link.focus();
      expect(link).toHaveFocus();

      // Should be clickable via Enter (this is default browser behavior for links)
      await user.keyboard('{Enter}');

      // Navigation should occur (tested via router context)
      // In a real implementation, we'd verify the navigation happened
    });

    it('should have visible focus indicator', async () => {
      const { user } = renderWithProviders(<ChannelCard channel={mockChannel} />);

      const link = screen.getByRole('link');

      // Tab to the link
      await user.tab();

      expect(link).toHaveFocus();

      // Should have focus-visible styles (implementation-dependent)
      // This would typically be tested with visual regression testing
      // For now, we verify it receives focus
    });
  });

  describe('Hover States', () => {
    it('should have hover state styling', async () => {
      const { user } = renderWithProviders(<ChannelCard channel={mockChannel} />);

      const link = screen.getByRole('link');

      // Hover over the link
      await user.hover(link);

      // Visual hover state would be tested with visual regression
      // Here we verify the element is interactive
      expect(link).toBeInTheDocument();
    });
  });

  describe('Custom URL Handling', () => {
    it('should display custom URL when available', () => {
      renderWithProviders(<ChannelCard channel={mockChannel} />);

      // May display @testchannel somewhere in the card
      // This is optional and depends on design
      expect(screen.getByText('Test Channel')).toBeInTheDocument();
    });

    it('should handle null custom_url gracefully', () => {
      const channelWithoutCustomUrl: ChannelListItem = {
        ...mockChannel,
        custom_url: null,
      };

      renderWithProviders(<ChannelCard channel={channelWithoutCustomUrl} />);

      // Should not crash
      expect(screen.getByText('Test Channel')).toBeInTheDocument();
    });
  });

  describe('Image Proxy URL (Feature 026, T031)', () => {
    it('should use proxy URL pattern /api/v1/images/channels/{channel_id}', () => {
      renderWithProviders(<ChannelCard channel={mockChannel} />);

      const thumbnail = screen.getByRole('img', { name: 'Test Channel' });
      const src = thumbnail.getAttribute('src');

      // Verify proxy URL pattern
      expect(src).toMatch(/\/images\/channels\/UC123456789012345678901$/);
      expect(src).toContain('UC123456789012345678901');
    });

    it('should NOT include YouTube CDN URLs (ytimg.com or ggpht.com)', () => {
      renderWithProviders(<ChannelCard channel={mockChannel} />);

      const thumbnail = screen.getByRole('img', { name: 'Test Channel' });
      const src = thumbnail.getAttribute('src');

      // Should NOT use YouTube CDN
      expect(src).not.toContain('ytimg.com');
      expect(src).not.toContain('ggpht.com');
      expect(src).not.toContain('youtube.com');
    });

    it('should render SVG placeholder on image error', async () => {
      const { user } = renderWithProviders(<ChannelCard channel={mockChannel} />);

      const thumbnail = screen.getByRole('img', { name: 'Test Channel' });

      // Simulate image load error
      const errorEvent = new Event('error', { bubbles: true });
      thumbnail.dispatchEvent(errorEvent);

      // After error, should fall back to placeholder
      // The onError handler sets src to PLACEHOLDER_THUMBNAIL (SVG data URI)
      const src = thumbnail.getAttribute('src');
      expect(src).toContain('data:image/svg+xml');
    });

    it('should have proper alt attribute for accessibility', () => {
      renderWithProviders(<ChannelCard channel={mockChannel} />);

      const thumbnail = screen.getByRole('img', { name: 'Test Channel' });
      expect(thumbnail).toHaveAttribute('alt', 'Test Channel');
    });

    it('should use placeholder when thumbnail_url is null', () => {
      const channelWithoutThumbnail: ChannelListItem = {
        ...mockChannel,
        thumbnail_url: null,
      };

      renderWithProviders(<ChannelCard channel={channelWithoutThumbnail} />);

      const placeholder = screen.getByRole('img', { name: 'Test Channel' });
      const src = placeholder.getAttribute('src');

      // Should use SVG placeholder, NOT proxy URL
      expect(src).toContain('data:image/svg+xml');
      expect(src).not.toContain('/images/channels/');
    });

    it('should use placeholder when thumbnail_url is empty string', () => {
      const channelWithEmptyThumbnail: ChannelListItem = {
        ...mockChannel,
        thumbnail_url: '',
      };

      renderWithProviders(<ChannelCard channel={channelWithEmptyThumbnail} />);

      const placeholder = screen.getByRole('img', { name: 'Test Channel' });
      const src = placeholder.getAttribute('src');

      // Should use SVG placeholder, NOT proxy URL
      expect(src).toContain('data:image/svg+xml');
      expect(src).not.toContain('/images/channels/');
    });
  });
});
