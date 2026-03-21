/**
 * useYouTubePlayer — manages the full lifecycle of a YouTube IFrame Player.
 *
 * Responsibilities:
 * - Injects the YouTube IFrame API script once (idempotent across mounts)
 * - Creates and destroys a YT.Player instance per component mount
 * - Polls getCurrentTime() via requestAnimationFrame at ~250 ms granularity
 *   while the player is in the PLAYING state
 * - Derives the active transcript segment via binary search on start_time
 * - Exposes stable seekTo / togglePlayback / toggleFollowPlayback callbacks
 *
 * @module hooks/useYouTubePlayer
 */

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type RefObject,
} from "react";

// ---------------------------------------------------------------------------
// Container-ready sentinel
// ---------------------------------------------------------------------------

/**
 * Polls via requestAnimationFrame until `containerRef.current` is non-null,
 * then calls `onReady`. Returns a cancel function that stops polling.
 *
 * This is used to defer player creation until the DOM element that the
 * IFrame API will replace has actually mounted. Without this guard the hook's
 * useEffect fires synchronously on mount (before a conditionally-rendered
 * VideoEmbed has had a chance to attach the ref), causing createPlayer() to
 * return early and — if the YT script was already loaded — never creating the
 * player at all.
 *
 * The `destroyed` flag is checked on every frame so the caller's cleanup
 * function can cancel the poll without a separate cancel handle.
 */
function waitForContainer(
  containerRef: RefObject<HTMLDivElement | null>,
  onReady: () => void,
  destroyedRef: RefObject<boolean>
): () => void {
  // Fast path: if the container is already in the DOM (e.g. the effect fires
  // after a synchronous render in tests, or the div was already mounted before
  // videoId changed), call onReady immediately without going through rAF.
  if (containerRef.current !== null) {
    onReady();
    // Nothing to cancel — return a no-op cleanup.
    return (): void => undefined;
  }

  // Slow path: the container div isn't mounted yet (e.g. VideoEmbed is
  // conditionally rendered and hasn't appeared in the DOM on this render pass).
  // Poll via requestAnimationFrame until the ref is populated.
  let rafId: number | null = null;

  function poll(): void {
    if (destroyedRef.current) return;
    if (containerRef.current !== null) {
      onReady();
      return;
    }
    rafId = requestAnimationFrame(poll);
  }

  rafId = requestAnimationFrame(poll);

  return (): void => {
    if (rafId !== null) {
      cancelAnimationFrame(rafId);
      rafId = null;
    }
  };
}

import type { TranscriptSegment } from "../types/transcript";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const YOUTUBE_IFRAME_API_SRC = "https://www.youtube.com/iframe_api";
const YOUTUBE_NOCOOKIE_HOST = "https://www.youtube-nocookie.com";
const API_LOAD_TIMEOUT_MS = 10_000;
/** Minimum elapsed milliseconds between getCurrentTime() samples. */
const POLL_INTERVAL_MS = 250;

// ---------------------------------------------------------------------------
// Error code → human-readable message (FR-010)
// ---------------------------------------------------------------------------

const ERROR_MESSAGES: Readonly<Record<number, string>> = {
  2: "The video ID is invalid.",
  5: "The video cannot be played in an embedded player.",
  100: "The video was not found. It may have been removed.",
  101: "The video owner does not allow embedded playback.",
  150: "The video owner does not allow embedded playback.",
} as const;

function errorMessageForCode(code: number): string {
  return ERROR_MESSAGES[code] ?? `An unknown player error occurred (code ${code}).`;
}

// ---------------------------------------------------------------------------
// Module-level IFrame API loading state (shared across all hook instances)
// ---------------------------------------------------------------------------

/**
 * Tracks whether the YT IFrame API script has already been injected into the
 * document. Using a module-level variable means multiple components can mount
 * concurrently without duplicating the script tag.
 */
let apiScriptInjected = false;

// ---------------------------------------------------------------------------
// Binary search helper
// ---------------------------------------------------------------------------

/**
 * Finds the index of the last segment whose start_time is <= currentTime.
 * Returns -1 when no such segment exists (currentTime is before the first
 * segment, or the segments array is empty).
 *
 * Gaps between segments: if currentTime falls inside a gap the caller checks
 * whether the matched segment's end_time has already passed; if so it returns
 * null for activeSegmentId (Edge Case 6).
 *
 * @param segments    - Flat, ordered array of transcript segments.
 * @param currentTime - Current playback position in seconds.
 * @returns Index into `segments`, or -1 if before the first segment.
 */
function binarySearchActiveSegmentIndex(
  segments: readonly TranscriptSegment[],
  currentTime: number
): number {
  if (segments.length === 0) return -1;

  let lo = 0;
  let hi = segments.length - 1;
  let result = -1;

  while (lo <= hi) {
    // Bitwise right-shift is safe here: indices are always small positive ints.
    const mid = (lo + hi) >>> 1;
    const seg = segments[mid];
    // noUncheckedIndexedAccess: `seg` is `TranscriptSegment | undefined`.
    // Because `mid` is always in [0, segments.length - 1] it is never
    // undefined, but we guard defensively to satisfy the type checker.
    if (seg === undefined) break;

    if (seg.start_time <= currentTime) {
      result = mid;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }

  return result;
}

// ---------------------------------------------------------------------------
// Public types
// ---------------------------------------------------------------------------

/**
 * Player error with a numeric code and a human-readable message.
 */
export interface PlayerError {
  /** Raw YouTube IFrame API error code. */
  code: number;
  /** Human-readable description of the error. */
  message: string;
}

/**
 * All state values exposed by useYouTubePlayer.
 */
export interface PlayerState {
  /** True once the IFrame API is fully loaded and the player is ready. */
  isReady: boolean;
  /** True while the player is actively playing (not paused, buffering, etc.). */
  isPlaying: boolean;
  /** Current playback position in seconds (updated at ~250 ms intervals). */
  currentTime: number;
  /**
   * ID of the transcript segment that contains the current playback position,
   * or null when no segment is active (gap between segments, or before the
   * first segment).
   */
  activeSegmentId: number | null;
  /** Non-null when the player has emitted an error event. */
  error: PlayerError | null;
  /**
   * When true the transcript panel should auto-scroll to keep the active
   * segment visible. Toggled by toggleFollowPlayback().
   */
  followPlayback: boolean;
}

/**
 * Stable control methods exposed by useYouTubePlayer.
 */
export interface PlayerControls {
  /** Seeks to `seconds` and begins playback. */
  seekTo: (seconds: number) => void;
  /** Toggles between play and pause. */
  togglePlayback: () => void;
  /** Toggles whether the transcript panel auto-scrolls during playback. */
  toggleFollowPlayback: () => void;
}

/**
 * Full return type of useYouTubePlayer.
 */
export interface UseYouTubePlayerResult extends PlayerState, PlayerControls {
  /**
   * Attach this ref to the `<div>` element that the IFrame Player will
   * replace. The element must be in the DOM before the player is created.
   *
   * React 19's useRef initialises DOM refs to null until the element mounts,
   * so the generic is `HTMLDivElement | null`.
   */
  containerRef: RefObject<HTMLDivElement | null>;
}

// ---------------------------------------------------------------------------
// Hook parameters
// ---------------------------------------------------------------------------

export interface UseYouTubePlayerOptions {
  /** YouTube video ID to embed. */
  videoId: string;
  /**
   * Ordered array of transcript segments used to derive activeSegmentId.
   * Pass an empty array when segments are not yet loaded.
   */
  segments: TranscriptSegment[];
  /**
   * When false the hook is a no-op: no script injection, no player creation,
   * no polling. Defaults to true for backward compatibility.
   *
   * Use this to defer player initialisation until the container div is
   * guaranteed to be rendered (e.g. pass `enabled: hasTranscript` so the hook
   * does not start the 10-second API-load timeout before a transcript exists).
   * When this prop transitions false → true the effect re-runs and creates the
   * player normally, clearing any stale error state from the disabled phase.
   */
  enabled?: boolean;
}

// ---------------------------------------------------------------------------
// Hook implementation
// ---------------------------------------------------------------------------

/**
 * Manages the full lifecycle of a YouTube IFrame Player.
 *
 * @param options - videoId and transcript segments for active-segment matching.
 * @returns Player state and stable control callbacks.
 *
 * @example
 * ```tsx
 * const {
 *   containerRef,
 *   isReady,
 *   isPlaying,
 *   currentTime,
 *   activeSegmentId,
 *   error,
 *   followPlayback,
 *   seekTo,
 *   togglePlayback,
 *   toggleFollowPlayback,
 * } = useYouTubePlayer({ videoId: 'dQw4w9WgXcQ', segments });
 *
 * return <div ref={containerRef} />;
 * ```
 */
export function useYouTubePlayer({
  videoId,
  segments,
  enabled = true,
}: UseYouTubePlayerOptions): UseYouTubePlayerResult {
  // --------------------------------------------------------------------------
  // Refs (not state — player internals must not trigger re-renders)
  // --------------------------------------------------------------------------

  /** The YT.Player instance. Null before the API is ready and after destroy(). */
  const playerRef = useRef<YT.Player | null>(null);

  /** The <div> that the IFrame Player replaces on mount. */
  const containerRef = useRef<HTMLDivElement>(null);

  /**
   * rAF handle for the polling loop. Stored in a ref so the cleanup function
   * in useEffect can cancel it without closing over a stale value.
   */
  const rafHandleRef = useRef<number | null>(null);

  /**
   * Timestamp of the last getCurrentTime() sample (performance.now() units).
   * Used to gate the 250 ms poll interval inside the rAF loop.
   */
  const lastPollTimeRef = useRef<number>(0);

  /**
   * Whether the rAF loop should continue. Set to false on pause/end/unmount so
   * the loop exits without needing to cancel the outstanding rAF handle when
   * the state transition and the scheduled frame race.
   */
  const pollingActiveRef = useRef<boolean>(false);

  /**
   * Stable reference to the segments prop so the rAF callback can read the
   * current list without being re-created on every render.
   */
  const segmentsRef = useRef<TranscriptSegment[]>(segments);

  // Keep segmentsRef in sync with the prop on every render (no effect needed).
  segmentsRef.current = segments;

  // --------------------------------------------------------------------------
  // React state (values that drive the UI)
  // --------------------------------------------------------------------------

  const [isReady, setIsReady] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [activeSegmentId, setActiveSegmentId] = useState<number | null>(null);
  const [error, setError] = useState<PlayerError | null>(null);
  const [followPlayback, setFollowPlayback] = useState(true);

  // --------------------------------------------------------------------------
  // Polling loop (rAF-based at ~250 ms)
  // --------------------------------------------------------------------------

  /**
   * Schedules a single rAF frame. Each frame checks whether 250 ms have
   * elapsed since the last poll; if so it reads getCurrentTime() and
   * updates activeSegmentId, then schedules the next frame.
   *
   * The loop stops automatically when pollingActiveRef becomes false (set by
   * the onStateChange handler on pause/end/unmount cleanup).
   */
  const schedulePollingFrame = useCallback((): void => {
    const tick = (now: DOMHighResTimeStamp): void => {
      if (!pollingActiveRef.current) {
        rafHandleRef.current = null;
        return;
      }

      if (now - lastPollTimeRef.current >= POLL_INTERVAL_MS) {
        lastPollTimeRef.current = now;

        const player = playerRef.current;
        if (player !== null) {
          const time = player.getCurrentTime();
          setCurrentTime(time);

          // Binary-search for the active segment.
          const segs = segmentsRef.current;
          const idx = binarySearchActiveSegmentIndex(segs, time);

          if (idx === -1) {
            // Before the first segment.
            setActiveSegmentId(null);
          } else {
            const seg = segs[idx];
            if (seg === undefined) {
              setActiveSegmentId(null);
            } else if (time <= seg.end_time) {
              // Inside this segment's time range.
              setActiveSegmentId(seg.id);
            } else {
              // In a gap after this segment but before the next (Edge Case 6).
              setActiveSegmentId(null);
            }
          }
        }
      }

      // Schedule the next frame only if still polling.
      if (pollingActiveRef.current) {
        rafHandleRef.current = requestAnimationFrame(tick);
      } else {
        rafHandleRef.current = null;
      }
    };

    rafHandleRef.current = requestAnimationFrame(tick);
  }, []); // No dependencies — reads all values through refs.

  const stopPolling = useCallback((): void => {
    pollingActiveRef.current = false;
    if (rafHandleRef.current !== null) {
      cancelAnimationFrame(rafHandleRef.current);
      rafHandleRef.current = null;
    }
  }, []);

  const startPolling = useCallback((): void => {
    if (pollingActiveRef.current) return; // Already running.
    pollingActiveRef.current = true;
    lastPollTimeRef.current = 0; // Force an immediate first sample.
    schedulePollingFrame();
  }, [schedulePollingFrame]);

  // --------------------------------------------------------------------------
  // Player event handlers
  // --------------------------------------------------------------------------

  const handleReady = useCallback((): void => {
    setIsReady(true);
  }, []);

  const handleStateChange = useCallback(
    (event: YT.PlayerEvent): void => {
      const state = event.target.getPlayerState();
      // YT.PlayerState is a const enum, so values are inlined at compile time.
      // eslint-disable-next-line @typescript-eslint/no-unsafe-enum-comparison
      const playing = state === (1 as number); // YT.PlayerState.PLAYING = 1
      setIsPlaying(playing);

      if (playing) {
        startPolling();
      } else {
        stopPolling();
      }
    },
    [startPolling, stopPolling]
  );

  const handleError = useCallback((event: YT.OnErrorEvent): void => {
    stopPolling();
    setIsPlaying(false);
    setError({
      code: event.data,
      message: errorMessageForCode(event.data),
    });
  }, [stopPolling]);

  // --------------------------------------------------------------------------
  // IFrame API script injection & player creation
  // --------------------------------------------------------------------------

  /**
   * Stable ref tracking whether the current effect run has been cleaned up.
   * Passed to waitForContainer so the rAF poll can bail out after unmount
   * without capturing a local `destroyed` boolean through a stale closure.
   */
  const destroyedRef = useRef<boolean>(false);

  useEffect(() => {
    // When enabled transitions false → true, clear any stale error that
    // accumulated during the disabled phase (e.g. the -1 timeout that fired
    // while the container div was not yet rendered).
    setError(null);

    // No-op when the caller has explicitly disabled the hook. This prevents
    // script injection, player creation, and the 10-second API-load timeout
    // from starting before the embed container is guaranteed to be in the DOM.
    // When enabled later transitions to true the effect re-runs (because
    // enabled is in the dependency array) and creates the player normally.
    if (!enabled) return;

    // Reset the destroyed sentinel for this effect run.
    destroyedRef.current = false;

    let timeoutId: ReturnType<typeof setTimeout> | null = null;
    // Cancel handle returned by waitForContainer, called in cleanup.
    let cancelContainerPoll: (() => void) | null = null;

    /**
     * Creates a new YT.Player instance using the current containerRef.
     *
     * This function is only called after waitForContainer confirms that
     * containerRef.current is non-null, so the null check here is a defensive
     * guard for unexpected re-entrancy only.
     */
    function createPlayer(): void {
      if (destroyedRef.current) return;
      if (containerRef.current === null) return;

      // Clear any pending API load timeout — we have both a container and the
      // API, so the timeout is no longer needed.
      if (timeoutId !== null) {
        clearTimeout(timeoutId);
        timeoutId = null;
      }

      playerRef.current = new YT.Player(containerRef.current, {
        videoId,
        host: YOUTUBE_NOCOOKIE_HOST,
        playerVars: {
          autoplay: 0,
          rel: 0,
          enablejsapi: 1,
          origin: window.location.origin,
          modestbranding: 1,
        },
        events: {
          onReady: handleReady,
          onStateChange: handleStateChange,
          onError: handleError,
        },
      } as YT.PlayerOptions & { host: string });
    }

    function onAPILoadTimeout(): void {
      if (destroyedRef.current) return;
      setError({
        code: -1,
        message:
          "The YouTube player failed to load within 10 seconds. " +
          "Check your network connection and try again.",
      });
    }

    if (typeof window.YT !== "undefined" && typeof window.YT.Player === "function") {
      // API already loaded from a previous component mount.
      // Wait for the container div to be attached to the DOM before creating
      // the player. When VideoEmbed is rendered conditionally (e.g. only when
      // hasTranscript is true) the ref is null on this first effect run; the
      // rAF poll detects the mount on the next frame(s) and calls createPlayer.
      cancelContainerPoll = waitForContainer(containerRef, createPlayer, destroyedRef);
    } else {
      // The YT IFrame API script has not been loaded yet.
      // We set the 10-second timeout now because the network request is the
      // genuine failure mode we want to guard against (NFR-006). Container
      // availability is handled inside onYouTubeIframeAPIReady via its own
      // waitForContainer call, so the timeout will be cleared as soon as the
      // API loads AND the container is ready.
      timeoutId = setTimeout(onAPILoadTimeout, API_LOAD_TIMEOUT_MS);

      // Chain the new callback after any existing one so we don't overwrite
      // another mounted instance's callback.
      const previousCallback = window.onYouTubeIframeAPIReady;
      window.onYouTubeIframeAPIReady = (): void => {
        if (typeof previousCallback === "function") {
          previousCallback();
        }
        // When the API fires its ready callback the container may still not be
        // mounted (e.g. if hasTranscript was determined asynchronously). Poll
        // until the div is available, then create the player.
        cancelContainerPoll = waitForContainer(containerRef, createPlayer, destroyedRef);
      };

      // Inject the script tag exactly once across all hook instances.
      if (!apiScriptInjected) {
        apiScriptInjected = true;
        const script = document.createElement("script");
        script.src = YOUTUBE_IFRAME_API_SRC;
        script.async = true;
        document.head.appendChild(script);
      }
    }

    // Cleanup: stop polling, destroy player, prevent stale callbacks.
    return (): void => {
      destroyedRef.current = true;

      // Cancel any in-flight container-ready poll.
      if (cancelContainerPoll !== null) {
        cancelContainerPoll();
        cancelContainerPoll = null;
      }

      if (timeoutId !== null) {
        clearTimeout(timeoutId);
      }

      stopPolling();

      if (playerRef.current !== null) {
        try {
          playerRef.current.destroy();
        } catch {
          // destroy() can throw if the iframe was already removed from the DOM.
        }
        playerRef.current = null;
      }
    };
    // handleReady / handleStateChange / handleError are stable (useCallback with
    // no or stable deps). videoId intentionally included: a videoId change means
    // we must recreate the player from scratch. enabled is included so that the
    // effect re-runs when the caller transitions false → true (e.g. after a
    // transcript is downloaded) and creates the player at that point.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [videoId, enabled]);

  // --------------------------------------------------------------------------
  // Stable control methods
  // --------------------------------------------------------------------------

  const seekTo = useCallback((seconds: number): void => {
    const player = playerRef.current;
    if (player === null) return;
    player.seekTo(seconds, /* allowSeekAhead */ true);
    player.playVideo();
  }, []);

  const togglePlayback = useCallback((): void => {
    const player = playerRef.current;
    if (player === null) return;
    const state = player.getPlayerState();
    // const enum values are inlined; compare as numbers to avoid TS issues.
    if (state === (1 as number)) {
      // PLAYING
      player.pauseVideo();
    } else {
      player.playVideo();
    }
  }, []);

  const toggleFollowPlayback = useCallback((): void => {
    setFollowPlayback((prev) => !prev);
  }, []);

  // --------------------------------------------------------------------------
  // Return
  // --------------------------------------------------------------------------

  return {
    // Ref
    containerRef,
    // State
    isReady,
    isPlaying,
    currentTime,
    activeSegmentId,
    error,
    followPlayback,
    // Methods
    seekTo,
    togglePlayback,
    toggleFollowPlayback,
  };
}
