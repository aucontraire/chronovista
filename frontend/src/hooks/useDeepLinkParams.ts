import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";

/**
 * Deep link URL parameters for transcript navigation.
 *
 * These parameters allow direct linking to specific transcript content:
 * - `lang`: Auto-select a specific language track
 * - `seg`: Scroll to and highlight a specific segment
 * - `t`: Fallback timestamp when segment ID unavailable
 */
export interface DeepLinkParams {
  /**
   * BCP-47 language code to auto-select (from ?lang=).
   *
   * @example "en", "es", "fr-CA"
   */
  lang: string | null;

  /**
   * Segment ID to scroll to and highlight (from ?seg=).
   *
   * Must be a positive integer. Zero, negative, or invalid values return null.
   */
  segmentId: number | null;

  /**
   * Start time in seconds as fallback (from ?t=).
   *
   * Must be non-negative. Negative or invalid values return null.
   */
  timestamp: number | null;

  /**
   * Selectively remove only lang/seg/t from URL without adding history entry.
   *
   * Preserves all other query parameters and uses replace to avoid polluting
   * browser history.
   */
  clearDeepLinkParams: () => void;
}

/**
 * Extract and type deep link URL parameters from the browser URL.
 *
 * Parses `lang`, `seg`, and `t` query parameters for transcript navigation.
 * Provides validation and type coercion for segment IDs and timestamps.
 *
 * @returns Parsed deep link parameters and cleanup function
 *
 * @example
 * ```tsx
 * function TranscriptView() {
 *   const { lang, segmentId, timestamp, clearDeepLinkParams } = useDeepLinkParams();
 *
 *   useEffect(() => {
 *     if (segmentId) {
 *       scrollToSegment(segmentId);
 *       clearDeepLinkParams();
 *     }
 *   }, [segmentId, clearDeepLinkParams]);
 *
 *   return <Transcript languageCode={lang} />;
 * }
 * ```
 */
export function useDeepLinkParams(): DeepLinkParams {
  const [searchParams] = useSearchParams();

  const params = useMemo(() => {
    // Extract raw string value or null
    const langRaw = searchParams.get("lang");
    const lang = langRaw && langRaw.trim() !== "" ? langRaw : null;

    // Parse segment ID - must be positive integer
    const segRaw = searchParams.get("seg");
    let segmentId: number | null = null;
    if (segRaw !== null) {
      const parsed = parseInt(segRaw, 10);
      if (!isNaN(parsed) && parsed > 0) {
        segmentId = parsed;
      }
    }

    // Parse timestamp - must be non-negative
    const tRaw = searchParams.get("t");
    let timestamp: number | null = null;
    if (tRaw !== null) {
      const parsed = parseInt(tRaw, 10);
      if (!isNaN(parsed) && parsed >= 0) {
        timestamp = parsed;
      }
    }

    return { lang, segmentId, timestamp };
  }, [searchParams]);

  const clearDeepLinkParams = useCallback(() => {
    // Use the History API directly instead of React Router's setSearchParams.
    // setSearchParams triggers a React Router navigation which causes
    // ScrollRestoration to scroll the window to the top — undoing the
    // deep link scroll-to-segment positioning. replaceState updates the
    // URL silently without any React state changes or scroll side effects.
    const url = new URL(window.location.href);
    url.searchParams.delete("lang");
    url.searchParams.delete("seg");
    url.searchParams.delete("t");
    window.history.replaceState(
      window.history.state, // preserve React Router's internal state
      "",
      url.pathname + url.search
    );
  }, []);

  return {
    ...params,
    clearDeepLinkParams,
  };
}
