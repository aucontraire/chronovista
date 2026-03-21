/**
 * Minimal TypeScript declarations for the YouTube IFrame Player API.
 * Covers only the subset of the YT namespace used by this application.
 *
 * Do NOT install @types/youtube — this file is intentionally scoped to
 * the APIs consumed by Feature 048 (Video Embed & Transcript Sync).
 *
 * Reference: https://developers.google.com/youtube/iframe_api_reference
 */

declare namespace YT {
  /**
   * Numeric state values emitted by the player's onStateChange event.
   * Each value corresponds to a distinct playback lifecycle phase.
   */
  const enum PlayerState {
    /** Player has been created but no video has been cued yet, or the player
     *  was reset. */
    UNSTARTED = -1,
    /** Playback reached the end of the video. */
    ENDED = 0,
    /** Video is actively playing. */
    PLAYING = 1,
    /** Playback is paused. */
    PAUSED = 2,
    /** Player is buffering content. */
    BUFFERING = 3,
    /** A video has been cued and is ready to play, but is not yet playing. */
    CUED = 5,
  }

  /**
   * Common player parameter overrides passed via the `playerVars` option.
   * All properties are optional — omit to accept the YouTube default.
   */
  interface PlayerVars {
    /** Whether to autoplay the video on load (0 = no, 1 = yes). */
    autoplay?: 0 | 1;
    /** Whether to show the player controls UI (0 = hidden, 1 = shown). */
    controls?: 0 | 1;
    /** Whether to show related videos from other channels after playback
     *  ends (0 = same channel only, 1 = any channel). */
    rel?: 0 | 1;
    /** Whether to suppress the YouTube logo in the control bar
     *  (0 = full branding, 1 = modest branding). */
    modestbranding?: 0 | 1;
    /** The origin domain, used as an extra security measure when the JS API
     *  is enabled (e.g., "https://example.com"). */
    origin?: string;
    /** Whether to enable the JavaScript API so the host page can control
     *  the player (0 = disabled, 1 = enabled). Must be 1 to use YT.Player. */
    enablejsapi?: 0 | 1;
  }

  /**
   * Event object passed to `onReady` and `onStateChange` callbacks.
   */
  interface PlayerEvent {
    /** The YT.Player instance that fired the event. */
    target: Player;
  }

  /**
   * Event object passed to the `onError` callback.
   * The `data` field carries one of the documented error codes:
   * - 2   — invalid parameter value
   * - 5   — HTML5 player error
   * - 100 — video not found or removed
   * - 101 — video not allowed in embedded players (owner restriction)
   * - 150 — same as 101 (alternate code used by YouTube)
   */
  interface OnErrorEvent {
    /** Numeric error code emitted by the player. */
    data: number;
    /** The YT.Player instance that fired the error. */
    target: Player;
  }

  /**
   * Constructor options for `new YT.Player(...)`.
   */
  interface PlayerOptions {
    /** Height of the embedded player (pixels as number, or CSS string). */
    height?: string | number;
    /** Width of the embedded player (pixels as number, or CSS string). */
    width?: string | number;
    /** YouTube video ID to load immediately on player creation. */
    videoId?: string;
    /** Granular player parameter overrides (mapped to IFrame API query params). */
    playerVars?: PlayerVars;
    /** Lifecycle event callbacks registered at construction time. */
    events?: {
      /** Fired when the player is fully initialized and ready to receive API
       *  calls. */
      onReady?: (event: PlayerEvent) => void;
      /** Fired whenever the player transitions between playback states.
       *  Read `event.target.getPlayerState()` to determine the new state. */
      onStateChange?: (event: PlayerEvent) => void;
      /** Fired when an error occurs in the player. */
      onError?: (event: OnErrorEvent) => void;
    };
  }

  /**
   * The YouTube IFrame Player instance.
   * Obtain via `new YT.Player(elementId, options)`.
   */
  class Player {
    /**
     * Creates a new YouTube IFrame Player, replacing the given element (or
     * inserting into the element identified by `elementId`) with the player
     * iframe.
     *
     * @param elementId - The `id` attribute of a `<div>` to replace, or a
     *   direct `HTMLElement` reference.
     * @param options   - Configuration and event callbacks for the player.
     */
    constructor(elementId: string | HTMLElement, options: PlayerOptions);

    /**
     * Seeks to the specified time in the video.
     *
     * @param seconds        - Target playback position in seconds.
     * @param allowSeekAhead - When `true`, allows the player to make a new
     *   server request for segments beyond the currently buffered range.
     */
    seekTo(seconds: number, allowSeekAhead: boolean): void;

    /** Starts or resumes playback of the currently loaded/cued video. */
    playVideo(): void;

    /** Pauses playback of the currently playing video. */
    pauseVideo(): void;

    /**
     * Returns the current playback position in seconds, as a floating-point
     * number (e.g., 63.5 for 1 minute 3.5 seconds into the video).
     */
    getCurrentTime(): number;

    /**
     * Returns the current playback state as a `YT.PlayerState` value.
     * Use this inside an `onStateChange` handler or to poll player status.
     */
    getPlayerState(): PlayerState;

    /**
     * Destroys the player and removes the underlying `<iframe>` from the DOM.
     * Call this in a React cleanup effect (`useEffect` return) to prevent
     * memory leaks when the component unmounts.
     */
    destroy(): void;
  }
}

/**
 * Augment the global `Window` interface to declare the callback that the
 * YouTube IFrame API script invokes once it has fully loaded.
 *
 * Assign a function to `window.onYouTubeIframeAPIReady` before (or
 * immediately after) injecting the `<script src="https://www.youtube.com/
 * iframe_api">` tag.  The API will call it as soon as `YT.Player` is
 * available.
 */
interface Window {
  onYouTubeIframeAPIReady: (() => void) | undefined;
}
