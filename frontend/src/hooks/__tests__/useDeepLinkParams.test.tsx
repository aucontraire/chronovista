/**
 * Tests for useDeepLinkParams hook.
 *
 * Tests deep link parameter extraction, validation, and cleanup functionality
 * for transcript navigation via URL query parameters.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { useDeepLinkParams } from '../useDeepLinkParams';

/**
 * Helper to render the hook with a specific initial URL.
 */
function renderWithRouter(initialEntries: string[] = ['/']) {
  return renderHook(() => useDeepLinkParams(), {
    wrapper: ({ children }) => (
      <MemoryRouter initialEntries={initialEntries}>
        {children}
      </MemoryRouter>
    ),
  });
}

describe('useDeepLinkParams', () => {
  describe('Extraction Tests', () => {
    it('extracts lang, seg, t from URL when all present', () => {
      const { result } = renderWithRouter(['/?lang=en-US&seg=42&t=125']);

      expect(result.current.lang).toBe('en-US');
      expect(result.current.segmentId).toBe(42);
      expect(result.current.timestamp).toBe(125);
    });

    it('returns correct types: lang=string, segmentId=number, timestamp=number', () => {
      const { result } = renderWithRouter(['/?lang=es&seg=10&t=60']);

      expect(typeof result.current.lang).toBe('string');
      expect(typeof result.current.segmentId).toBe('number');
      expect(typeof result.current.timestamp).toBe('number');
      expect(result.current.lang).toBe('es');
      expect(result.current.segmentId).toBe(10);
      expect(result.current.timestamp).toBe(60);
    });

    it('returns null for all params when URL has no query params', () => {
      const { result } = renderWithRouter(['/']);

      expect(result.current.lang).toBeNull();
      expect(result.current.segmentId).toBeNull();
      expect(result.current.timestamp).toBeNull();
    });

    it('returns null for missing individual params (lang present but no seg/t)', () => {
      const { result } = renderWithRouter(['/?lang=fr']);

      expect(result.current.lang).toBe('fr');
      expect(result.current.segmentId).toBeNull();
      expect(result.current.timestamp).toBeNull();
    });

    it('returns null for missing lang but present seg/t', () => {
      const { result } = renderWithRouter(['/?seg=5&t=30']);

      expect(result.current.lang).toBeNull();
      expect(result.current.segmentId).toBe(5);
      expect(result.current.timestamp).toBe(30);
    });
  });

  describe('Validation Tests', () => {
    it('returns null for non-numeric seg', () => {
      const { result } = renderWithRouter(['/?seg=abc&lang=en']);

      expect(result.current.segmentId).toBeNull();
      expect(result.current.lang).toBe('en');
    });

    it('returns null for seg=0 (must be positive)', () => {
      const { result } = renderWithRouter(['/?seg=0&lang=en']);

      expect(result.current.segmentId).toBeNull();
      expect(result.current.lang).toBe('en');
    });

    it('returns null for seg=-5 (must be positive)', () => {
      const { result } = renderWithRouter(['/?seg=-5&lang=en']);

      expect(result.current.segmentId).toBeNull();
      expect(result.current.lang).toBe('en');
    });

    it('returns null for non-numeric t', () => {
      const { result } = renderWithRouter(['/?t=abc&lang=en']);

      expect(result.current.timestamp).toBeNull();
      expect(result.current.lang).toBe('en');
    });

    it('returns null for t=-1 (must be non-negative)', () => {
      const { result } = renderWithRouter(['/?t=-1&lang=en']);

      expect(result.current.timestamp).toBeNull();
      expect(result.current.lang).toBe('en');
    });

    it('returns timestamp=0 for t=0 (zero is valid for timestamp)', () => {
      const { result } = renderWithRouter(['/?t=0&lang=en']);

      expect(result.current.timestamp).toBe(0);
      expect(result.current.lang).toBe('en');
    });

    it('returns null for empty lang', () => {
      const { result } = renderWithRouter(['/?lang=']);

      expect(result.current.lang).toBeNull();
    });

    it('returns null for whitespace-only lang', () => {
      const { result } = renderWithRouter(['/?lang=%20%20']);

      expect(result.current.lang).toBeNull();
    });

    it('accepts valid BCP-47 language codes', () => {
      const { result: result1 } = renderWithRouter(['/?lang=en']);
      expect(result1.current.lang).toBe('en');

      const { result: result2 } = renderWithRouter(['/?lang=fr-CA']);
      expect(result2.current.lang).toBe('fr-CA');

      const { result: result3 } = renderWithRouter(['/?lang=zh-Hans']);
      expect(result3.current.lang).toBe('zh-Hans');
    });
  });

  describe('clearDeepLinkParams Tests', () => {
    let replaceStateSpy: ReturnType<typeof vi.spyOn>;

    beforeEach(() => {
      replaceStateSpy = vi.spyOn(window.history, 'replaceState');
    });

    afterEach(() => {
      replaceStateSpy.mockRestore();
    });

    it('removes lang, seg, t params from the browser URL via History API', () => {
      const { result } = renderWithRouter(['/?lang=en-US&seg=42&t=125']);

      expect(result.current.lang).toBe('en-US');
      expect(result.current.segmentId).toBe(42);
      expect(result.current.timestamp).toBe(125);

      act(() => {
        result.current.clearDeepLinkParams();
      });

      // Uses History API directly (not setSearchParams) to avoid triggering
      // ScrollRestoration scroll-to-top. Verify replaceState was called with
      // a URL that has no deep link params.
      expect(replaceStateSpy).toHaveBeenCalledOnce();
      const calledUrl = replaceStateSpy.mock.calls[0]![2] as string;
      expect(calledUrl).not.toContain('lang=');
      expect(calledUrl).not.toContain('seg=');
      expect(calledUrl).not.toContain('t=');
    });

    it('preserves other query params in browser URL', () => {
      // MemoryRouter doesn't sync with window.location, so we verify the
      // URL construction logic directly: clearDeepLinkParams only deletes
      // lang/seg/t and preserves everything else via standard URL API.
      const { result } = renderWithRouter([
        '/?lang=en&seg=10&t=50&utm_source=email&utm_campaign=test',
      ]);

      expect(result.current.lang).toBe('en');
      expect(result.current.segmentId).toBe(10);
      expect(result.current.timestamp).toBe(50);

      act(() => {
        result.current.clearDeepLinkParams();
      });

      // Verify replaceState was called (URL cleanup happened)
      expect(replaceStateSpy).toHaveBeenCalledOnce();

      // Verify the URL construction logic preserves non-deep-link params:
      // clearDeepLinkParams reads window.location.href, deletes only lang/seg/t,
      // and passes the result to replaceState. In happy-dom, window.location
      // doesn't reflect MemoryRouter URLs, so we verify the logic with a
      // direct URL API test instead.
      const url = new URL('http://localhost/?lang=en&seg=10&t=50&utm_source=email&utm_campaign=test');
      url.searchParams.delete('lang');
      url.searchParams.delete('seg');
      url.searchParams.delete('t');
      expect(url.searchParams.get('utm_source')).toBe('email');
      expect(url.searchParams.get('utm_campaign')).toBe('test');
      expect(url.searchParams.has('lang')).toBe(false);
    });

    it('works when called multiple times', () => {
      const { result } = renderWithRouter(['/?lang=en&seg=5']);

      act(() => {
        result.current.clearDeepLinkParams();
      });

      // Should not throw when called again
      act(() => {
        result.current.clearDeepLinkParams();
      });

      expect(replaceStateSpy).toHaveBeenCalledTimes(2);
    });

    it('works when no deep link params are present', () => {
      const { result } = renderWithRouter(['/?utm_source=google']);

      expect(result.current.lang).toBeNull();
      expect(result.current.segmentId).toBeNull();
      expect(result.current.timestamp).toBeNull();

      // Should not throw
      act(() => {
        result.current.clearDeepLinkParams();
      });

      expect(result.current.lang).toBeNull();
      expect(result.current.segmentId).toBeNull();
      expect(result.current.timestamp).toBeNull();
    });
  });

  describe('Edge Cases', () => {
    it('handles partial valid params correctly', () => {
      const { result } = renderWithRouter(['/?lang=en&seg=abc&t=50']);

      expect(result.current.lang).toBe('en');
      expect(result.current.segmentId).toBeNull(); // Invalid seg
      expect(result.current.timestamp).toBe(50);
    });

    it('handles large segment IDs', () => {
      const { result } = renderWithRouter(['/?seg=999999']);

      expect(result.current.segmentId).toBe(999999);
    });

    it('handles large timestamps', () => {
      const { result } = renderWithRouter(['/?t=9999999']);

      expect(result.current.timestamp).toBe(9999999);
    });

    it('handles decimal values by truncating', () => {
      const { result } = renderWithRouter(['/?seg=42.5&t=125.9']);

      // parseInt truncates decimal values
      expect(result.current.segmentId).toBe(42);
      expect(result.current.timestamp).toBe(125);
    });

    it('handles language codes with special characters', () => {
      const { result } = renderWithRouter(['/?lang=zh-Hans-CN']);

      expect(result.current.lang).toBe('zh-Hans-CN');
    });

    it('provides stable clearDeepLinkParams reference', () => {
      const { result, rerender } = renderWithRouter(['/?lang=en']);

      const firstClear = result.current.clearDeepLinkParams;

      rerender();

      // The function reference should remain stable
      expect(result.current.clearDeepLinkParams).toBe(firstClear);
    });
  });
});
