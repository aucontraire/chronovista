/**
 * Unit tests for useYouTubePlayer hook.
 *
 * Tests the full YouTube IFrame Player lifecycle including script injection,
 * player creation, state polling via requestAnimationFrame, active segment
 * binary search, error handling, and cleanup.
 *
 * Coverage:
 * - T011-1: Script injection lifecycle (idempotent, correct src, head append)
 * - T011-2: Player creation when API is already loaded
 * - T011-3: Player creation via onYouTubeIframeAPIReady callback
 * - T011-4: isReady transitions to true after onReady event
 * - T011-5: State polling starts on PLAYING, stops on pause/end
 * - T011-6: currentTime state updates during polling
 * - T011-7: Error code handling — codes 2/5/100/101/150 and unknown
 * - T011-8: seekTo calls player.seekTo() and player.playVideo()
 * - T011-9: togglePlayback pauses when playing, plays when paused
 * - T011-10: toggleFollowPlayback flips followPlayback boolean
 * - T011-11: Cleanup on unmount — destroy, stop polling, clear timeout
 * - T011-12: 10-second script load timeout fallback
 * - T011-13: Binary search active segment matching (inside, gap, before, after, empty)
 *
 * @module tests/hooks/useYouTubePlayer
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, act, waitFor, screen } from "@testing-library/react";
import React, { type MutableRefObject } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import {
  useYouTubePlayer,
  type UseYouTubePlayerResult,
} from "../../hooks/useYouTubePlayer";
import type { TranscriptSegment } from "../../types/transcript";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const VIDEO_ID = "dQw4w9WgXcQ";

function makeSegment(
  id: number,
  start_time: number,
  end_time: number,
  text = `Segment ${id}`
): TranscriptSegment {
  return {
    id,
    text,
    start_time,
    end_time,
    duration: end_time - start_time,
    has_correction: false,
    corrected_at: null,
    correction_count: 0,
  };
}

// ---------------------------------------------------------------------------
// YT Player mock types
// ---------------------------------------------------------------------------

interface MockPlayerInstance {
  seekTo: ReturnType<typeof vi.fn>;
  playVideo: ReturnType<typeof vi.fn>;
  pauseVideo: ReturnType<typeof vi.fn>;
  getCurrentTime: ReturnType<typeof vi.fn>;
  getPlayerState: ReturnType<typeof vi.fn>;
  destroy: ReturnType<typeof vi.fn>;
}

interface CapturedPlayerConstruction {
  element: HTMLElement | string | undefined;
  options: {
    videoId?: string;
    host?: string;
    playerVars?: Record<string, unknown>;
    events?: {
      onReady?: (event: { target: MockPlayerInstance }) => void;
      onStateChange?: (event: { target: MockPlayerInstance }) => void;
      onError?: (event: { data: number; target: MockPlayerInstance }) => void;
    };
  };
}

function buildMockPlayerInstance(): MockPlayerInstance {
  return {
    seekTo: vi.fn(),
    playVideo: vi.fn(),
    pauseVideo: vi.fn(),
    getCurrentTime: vi.fn().mockReturnValue(0),
    getPlayerState: vi.fn().mockReturnValue(2), // PAUSED by default
    destroy: vi.fn(),
  };
}

// ---------------------------------------------------------------------------
// Manual rAF queue
//
// Instead of relying on vitest's fake-timer integration with rAF (which
// doesn't reliably pass the `performance.now()` value as the timestamp
// argument), we manage a manual queue of pending rAF callbacks and expose
// `flushRafQueue()` to flush them with a synthetic timestamp.
// ---------------------------------------------------------------------------

interface RafEntry {
  id: number;
  callback: FrameRequestCallback;
}

class RafQueue {
  private queue: RafEntry[] = [];
  private nextId = 1;
  private fakeNow = 0;

  install(): void {
    this.queue = [];
    this.nextId = 1;
    this.fakeNow = 0;

    vi.spyOn(globalThis, "requestAnimationFrame").mockImplementation(
      (callback: FrameRequestCallback): number => {
        const id = this.nextId++;
        this.queue.push({ id, callback });
        return id;
      }
    );

    vi.spyOn(globalThis, "cancelAnimationFrame").mockImplementation(
      (id: number): void => {
        this.queue = this.queue.filter((e) => e.id !== id);
      }
    );
  }

  uninstall(): void {
    vi.mocked(globalThis.requestAnimationFrame).mockRestore();
    vi.mocked(globalThis.cancelAnimationFrame).mockRestore();
  }

  /**
   * Advances the fake timestamp by `deltaMs` and flushes all currently-queued
   * rAF callbacks with the new timestamp.  Newly-scheduled callbacks (from
   * inside flushed callbacks) are NOT flushed in the same call — call
   * `flushOnce` repeatedly to drive the full polling loop.
   */
  flushOnce(deltaMs: number): void {
    this.fakeNow += deltaMs;
    const pending = [...this.queue];
    this.queue = [];
    for (const entry of pending) {
      entry.callback(this.fakeNow);
    }
  }

  /**
   * Flushes rAF frames `count` times, each advancing time by `deltaMs`.
   * Wraps each flush in `act` so React can process state updates between frames.
   */
  async flushFrames(count: number, deltaMs = 300): Promise<void> {
    for (let i = 0; i < count; i++) {
      await act(async () => {
        this.flushOnce(deltaMs);
      });
    }
  }

  get pendingCount(): number {
    return this.queue.length;
  }
}

// ---------------------------------------------------------------------------
// Test component
//
// The hook creates an internal containerRef and guards player creation with
// `if (containerRef.current === null) return`.  We need a real component that
// renders the ref's div AND exposes the hook result to the test via a shared
// MutableRef.
// ---------------------------------------------------------------------------

interface HookHarness {
  result: MutableRefObject<UseYouTubePlayerResult | null>;
  unmount: () => void;
}

function renderHookWithContainer(
  videoId: string,
  segments: TranscriptSegment[],
  queryClient: QueryClient
): HookHarness {
  const resultRef: MutableRefObject<UseYouTubePlayerResult | null> = {
    current: null,
  };

  function TestComponent({
    vid,
    segs,
    resultHolder,
  }: {
    vid: string;
    segs: TranscriptSegment[];
    resultHolder: MutableRefObject<UseYouTubePlayerResult | null>;
  }) {
    const hookResult = useYouTubePlayer({ videoId: vid, segments: segs });
    resultHolder.current = hookResult;
    return React.createElement("div", {
      "data-testid": "player-container",
      ref: hookResult.containerRef as React.RefObject<HTMLDivElement>,
    });
  }

  const { unmount } = render(
    React.createElement(
      QueryClientProvider,
      { client: queryClient },
      React.createElement(TestComponent, {
        vid: videoId,
        segs: segments,
        resultHolder: resultRef,
      })
    )
  );

  return { result: resultRef, unmount };
}

// ---------------------------------------------------------------------------
// Test utilities
// ---------------------------------------------------------------------------

function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("useYouTubePlayer", () => {
  let queryClient: QueryClient;
  let mockPlayerInstance: MockPlayerInstance;
  let captured: CapturedPlayerConstruction;
  const rafQueue = new RafQueue();

  /**
   * Installs a YT global whose Player constructor captures options and returns
   * mockPlayerInstance.  When a constructor function returns a plain object,
   * `new` uses that returned object, so `playerRef.current` will hold the mock.
   */
  function installYTGlobal(): void {
    function MockPlayer(
      this: MockPlayerInstance,
      element: HTMLElement | string,
      options: CapturedPlayerConstruction["options"]
    ) {
      captured.element = element;
      captured.options = options;
      Object.assign(this, mockPlayerInstance);
      return mockPlayerInstance;
    }

    Object.defineProperty(window, "YT", {
      value: { Player: MockPlayer },
      writable: true,
      configurable: true,
    });
  }

  beforeEach(() => {
    queryClient = makeQueryClient();
    vi.clearAllMocks();

    mockPlayerInstance = buildMockPlayerInstance();
    captured = { element: undefined, options: {} };

    window.onYouTubeIframeAPIReady = undefined;

    // Default: API already loaded.
    installYTGlobal();

    // Install the manual rAF queue for all tests.
    rafQueue.install();
  });

  afterEach(() => {
    queryClient.clear();
    // @ts-expect-error — intentionally removing the global
    delete window.YT;
    rafQueue.uninstall();
    vi.useRealTimers();
  });

  // =========================================================================
  // T011-1: Script injection lifecycle
  // =========================================================================

  describe("script injection lifecycle (T011-1)", () => {
    /**
     * These tests run with window.YT absent so the hook follows the script
     * injection path.  We stub document.head.appendChild to prevent happy-dom
     * from trying to load the external URL.
     *
     * The module-level `apiScriptInjected` flag means only the first mount ever
     * injects a script.  Both src and async are verified in a single test to
     * avoid flag-state interference across sequential test runs.
     */

    beforeEach(() => {
      // @ts-expect-error — intentionally removing the global
      delete window.YT;
      vi.spyOn(document.head, "appendChild").mockImplementation((node) => node);
    });

    it("appends a script element with src=iframe_api and async=true to document.head", () => {
      renderHookWithContainer(VIDEO_ID, [], queryClient);

      const appendSpy = vi.mocked(document.head.appendChild);
      const scripts = appendSpy.mock.calls
        .map((c) => c[0])
        .filter((n): n is HTMLScriptElement => n instanceof HTMLScriptElement);

      expect(scripts.length).toBeGreaterThanOrEqual(1);
      const script = scripts[0]!;
      expect(script.src).toBe("https://www.youtube.com/iframe_api");
      expect(script.async).toBe(true);
    });

    it("sets window.onYouTubeIframeAPIReady when the API is not yet loaded", () => {
      renderHookWithContainer(VIDEO_ID, [], queryClient);
      expect(typeof window.onYouTubeIframeAPIReady).toBe("function");
    });

    it("chains the previous onYouTubeIframeAPIReady callback when one is already set", () => {
      const firstCallback = vi.fn();
      window.onYouTubeIframeAPIReady = firstCallback;

      renderHookWithContainer(VIDEO_ID, [], queryClient);

      // The hook must have wrapped firstCallback so the combined callback
      // invokes the original.  We install the YT global before firing the
      // callback because the hook's createPlayer() calls `new YT.Player()`
      // when onYouTubeIframeAPIReady fires; without YT it would throw.
      installYTGlobal();
      window.onYouTubeIframeAPIReady?.();
      expect(firstCallback).toHaveBeenCalledTimes(1);
    });

    it("does not set onYouTubeIframeAPIReady when the API is already loaded", () => {
      installYTGlobal(); // API is available.

      renderHookWithContainer(VIDEO_ID, [], queryClient);

      // The hook takes the early-return path and skips callback registration.
      expect(window.onYouTubeIframeAPIReady).toBeUndefined();
    });

    it("does not inject a script tag when the API is already loaded", () => {
      installYTGlobal();
      const appendSpy = vi.mocked(document.head.appendChild);
      appendSpy.mockClear();

      renderHookWithContainer(VIDEO_ID, [], queryClient);

      const scripts = appendSpy.mock.calls
        .map((c) => c[0])
        .filter((n) => n instanceof HTMLScriptElement);
      expect(scripts.length).toBe(0);
    });
  });

  // =========================================================================
  // T011-2: Player creation when API is already loaded
  // =========================================================================

  describe("player creation when YT API is already loaded (T011-2)", () => {
    it("creates a YT.Player instance immediately (options.videoId is captured)", () => {
      renderHookWithContainer(VIDEO_ID, [], queryClient);
      expect(captured.options.videoId).toBe(VIDEO_ID);
    });

    it("passes the correct videoId to the constructor", () => {
      renderHookWithContainer("abc123xyz01", [], queryClient);
      expect(captured.options.videoId).toBe("abc123xyz01");
    });

    it("passes host: https://www.youtube-nocookie.com for privacy-enhanced mode", () => {
      renderHookWithContainer(VIDEO_ID, [], queryClient);
      expect(captured.options.host).toBe("https://www.youtube-nocookie.com");
    });

    it("passes playerVars with autoplay=0, rel=0, enablejsapi=1, modestbranding=1", () => {
      renderHookWithContainer(VIDEO_ID, [], queryClient);
      expect(captured.options.playerVars).toMatchObject({
        autoplay: 0,
        rel: 0,
        enablejsapi: 1,
        modestbranding: 1,
      });
    });

    it("registers onReady, onStateChange, and onError event callbacks", () => {
      renderHookWithContainer(VIDEO_ID, [], queryClient);
      expect(typeof captured.options.events?.onReady).toBe("function");
      expect(typeof captured.options.events?.onStateChange).toBe("function");
      expect(typeof captured.options.events?.onError).toBe("function");
    });

    it("passes the containerRef div as the first constructor argument", () => {
      renderHookWithContainer(VIDEO_ID, [], queryClient);
      const containerDiv = screen.getByTestId("player-container");
      expect(captured.element).toBe(containerDiv);
    });

    it("does not inject a script tag when the API is already loaded", () => {
      const appendSpy = vi.spyOn(document.head, "appendChild");
      renderHookWithContainer(VIDEO_ID, [], queryClient);

      const scripts = appendSpy.mock.calls
        .map((c) => c[0])
        .filter((n) => n instanceof HTMLScriptElement);
      expect(scripts.length).toBe(0);
    });
  });

  // =========================================================================
  // T011-3: Player creation via onYouTubeIframeAPIReady callback
  // =========================================================================

  describe("player creation via onYouTubeIframeAPIReady callback (T011-3)", () => {
    beforeEach(() => {
      // @ts-expect-error — intentionally removing the global
      delete window.YT;
      vi.spyOn(document.head, "appendChild").mockImplementation((n) => n);
    });

    it("does not create a player immediately when the API is not yet loaded", () => {
      renderHookWithContainer(VIDEO_ID, [], queryClient);
      expect(captured.options.videoId).toBeUndefined();
    });

    it("creates the player when onYouTubeIframeAPIReady fires with YT available", async () => {
      renderHookWithContainer(VIDEO_ID, [], queryClient);

      installYTGlobal();
      await act(async () => {
        window.onYouTubeIframeAPIReady?.();
      });

      expect(captured.options.videoId).toBe(VIDEO_ID);
    });

    it("passes the correct videoId when creating via the ready callback", async () => {
      renderHookWithContainer("custom_video_id", [], queryClient);

      installYTGlobal();
      await act(async () => {
        window.onYouTubeIframeAPIReady?.();
      });

      expect(captured.options.videoId).toBe("custom_video_id");
    });
  });

  // =========================================================================
  // T011-4: isReady state transitions
  // =========================================================================

  describe("isReady state transitions (T011-4)", () => {
    it("starts with isReady=false before the player fires onReady", () => {
      const { result } = renderHookWithContainer(VIDEO_ID, [], queryClient);
      expect(result.current?.isReady).toBe(false);
    });

    it("sets isReady=true when the player fires the onReady event", async () => {
      const { result } = renderHookWithContainer(VIDEO_ID, [], queryClient);

      await act(async () => {
        captured.options.events?.onReady?.({ target: mockPlayerInstance });
      });

      expect(result.current?.isReady).toBe(true);
    });

    it("keeps isPlaying=false after onReady fires (no autoplay)", async () => {
      const { result } = renderHookWithContainer(VIDEO_ID, [], queryClient);

      await act(async () => {
        captured.options.events?.onReady?.({ target: mockPlayerInstance });
      });

      expect(result.current?.isPlaying).toBe(false);
    });
  });

  // =========================================================================
  // T011-5: State polling start / stop
  // =========================================================================

  describe("state polling start and stop (T011-5)", () => {
    it("sets isPlaying=true when the player state changes to PLAYING (state=1)", async () => {
      const { result } = renderHookWithContainer(VIDEO_ID, [], queryClient);

      mockPlayerInstance.getPlayerState.mockReturnValue(1); // PLAYING

      await act(async () => {
        captured.options.events?.onStateChange?.({ target: mockPlayerInstance });
      });

      expect(result.current?.isPlaying).toBe(true);
    });

    it("sets isPlaying=false when the player state changes to PAUSED (state=2)", async () => {
      const { result } = renderHookWithContainer(VIDEO_ID, [], queryClient);

      // Start playing.
      mockPlayerInstance.getPlayerState.mockReturnValue(1);
      await act(async () => {
        captured.options.events?.onStateChange?.({ target: mockPlayerInstance });
      });
      expect(result.current?.isPlaying).toBe(true);

      // Pause.
      mockPlayerInstance.getPlayerState.mockReturnValue(2);
      await act(async () => {
        captured.options.events?.onStateChange?.({ target: mockPlayerInstance });
      });

      expect(result.current?.isPlaying).toBe(false);
    });

    it("sets isPlaying=false when the player state changes to ENDED (state=0)", async () => {
      const { result } = renderHookWithContainer(VIDEO_ID, [], queryClient);

      mockPlayerInstance.getPlayerState.mockReturnValue(1);
      await act(async () => {
        captured.options.events?.onStateChange?.({ target: mockPlayerInstance });
      });

      mockPlayerInstance.getPlayerState.mockReturnValue(0); // ENDED
      await act(async () => {
        captured.options.events?.onStateChange?.({ target: mockPlayerInstance });
      });

      expect(result.current?.isPlaying).toBe(false);
    });

    it("enqueues a rAF callback (requestAnimationFrame called) when PLAYING starts", async () => {
      renderHookWithContainer(VIDEO_ID, [], queryClient);

      const rafSpy = vi.mocked(globalThis.requestAnimationFrame);
      const callsBefore = rafSpy.mock.calls.length;

      mockPlayerInstance.getPlayerState.mockReturnValue(1);
      await act(async () => {
        captured.options.events?.onStateChange?.({ target: mockPlayerInstance });
      });

      expect(rafSpy.mock.calls.length).toBeGreaterThan(callsBefore);
    });

    it("does not start a second polling loop when already polling", async () => {
      renderHookWithContainer(VIDEO_ID, [], queryClient);

      mockPlayerInstance.getPlayerState.mockReturnValue(1);

      // First PLAYING event — starts the loop.
      await act(async () => {
        captured.options.events?.onStateChange?.({ target: mockPlayerInstance });
      });
      const rafCallsAfterFirst = vi.mocked(requestAnimationFrame).mock.calls.length;

      // Second PLAYING event — pollingActiveRef is already true, guard fires.
      await act(async () => {
        captured.options.events?.onStateChange?.({ target: mockPlayerInstance });
      });

      // Only one additional rAF call at most (from the ongoing loop itself).
      expect(vi.mocked(requestAnimationFrame).mock.calls.length).toBeLessThanOrEqual(
        rafCallsAfterFirst + 1
      );
    });
  });

  // =========================================================================
  // T011-6: currentTime state updates during polling
  // =========================================================================

  describe("currentTime state updates during polling (T011-6)", () => {
    it("starts with currentTime=0", () => {
      const { result } = renderHookWithContainer(VIDEO_ID, [], queryClient);
      expect(result.current?.currentTime).toBe(0);
    });

    it("calls player.getCurrentTime() when a rAF tick fires past the 250 ms threshold", async () => {
      renderHookWithContainer(VIDEO_ID, [], queryClient);

      mockPlayerInstance.getCurrentTime.mockReturnValue(30);
      mockPlayerInstance.getPlayerState.mockReturnValue(1);

      await act(async () => {
        captured.options.events?.onStateChange?.({ target: mockPlayerInstance });
      });

      // Flush one frame with 300 ms elapsed — exceeds the 250 ms threshold.
      await rafQueue.flushFrames(1, 300);

      expect(mockPlayerInstance.getCurrentTime).toHaveBeenCalled();
    });

    it("updates currentTime after the polling tick fires past 250 ms", async () => {
      const { result } = renderHookWithContainer(VIDEO_ID, [], queryClient);

      mockPlayerInstance.getCurrentTime.mockReturnValue(42.5);
      mockPlayerInstance.getPlayerState.mockReturnValue(1);

      await act(async () => {
        captured.options.events?.onStateChange?.({ target: mockPlayerInstance });
      });

      // Flush frames until currentTime updates.
      await rafQueue.flushFrames(2, 300);

      await waitFor(() => {
        expect(result.current?.currentTime).toBe(42.5);
      });
    });

    it("does not call getCurrentTime while paused (polling is not started)", async () => {
      renderHookWithContainer(VIDEO_ID, [], queryClient);

      mockPlayerInstance.getCurrentTime.mockReturnValue(99);

      // No state change to PLAYING — flush some frames anyway.
      await rafQueue.flushFrames(3, 100);

      expect(mockPlayerInstance.getCurrentTime).not.toHaveBeenCalled();
    });
  });

  // =========================================================================
  // T011-7: Error code handling
  // =========================================================================

  describe("error code handling (T011-7)", () => {
    it.each([
      [2, "The video ID is invalid."],
      [5, "The video cannot be played in an embedded player."],
      [100, "The video was not found. It may have been removed."],
      [101, "The video owner does not allow embedded playback."],
      [150, "The video owner does not allow embedded playback."],
    ] as const)(
      "sets error.code=%s and error.message=%s for known error code",
      async (code, expectedMessage) => {
        const { result } = renderHookWithContainer(VIDEO_ID, [], queryClient);

        await act(async () => {
          captured.options.events?.onError?.({
            data: code,
            target: mockPlayerInstance,
          });
        });

        expect(result.current?.error).toEqual({ code, message: expectedMessage });
      }
    );

    it("includes the error code in the fallback message for unknown codes", async () => {
      const { result } = renderHookWithContainer(VIDEO_ID, [], queryClient);

      await act(async () => {
        captured.options.events?.onError?.({
          data: 999,
          target: mockPlayerInstance,
        });
      });

      expect(result.current?.error?.code).toBe(999);
      expect(result.current?.error?.message).toContain("999");
    });

    it("sets isPlaying=false when an error event fires during playback", async () => {
      const { result } = renderHookWithContainer(VIDEO_ID, [], queryClient);

      mockPlayerInstance.getPlayerState.mockReturnValue(1);
      await act(async () => {
        captured.options.events?.onStateChange?.({ target: mockPlayerInstance });
      });
      expect(result.current?.isPlaying).toBe(true);

      await act(async () => {
        captured.options.events?.onError?.({
          data: 100,
          target: mockPlayerInstance,
        });
      });

      expect(result.current?.isPlaying).toBe(false);
      expect(result.current?.error?.code).toBe(100);
    });

    it("starts with error=null before any error event", () => {
      const { result } = renderHookWithContainer(VIDEO_ID, [], queryClient);
      expect(result.current?.error).toBeNull();
    });

    it("error.code and error.message are set simultaneously on the same object", async () => {
      const { result } = renderHookWithContainer(VIDEO_ID, [], queryClient);

      await act(async () => {
        captured.options.events?.onError?.({ data: 5, target: mockPlayerInstance });
      });

      expect(result.current?.error?.code).toBe(5);
      expect(result.current?.error?.message).toBeTruthy();
    });
  });

  // =========================================================================
  // T011-8: seekTo dispatch
  // =========================================================================

  describe("seekTo dispatch (T011-8)", () => {
    it("calls player.seekTo(seconds, true) with allowSeekAhead=true", async () => {
      const { result } = renderHookWithContainer(VIDEO_ID, [], queryClient);

      await act(async () => {
        result.current?.seekTo(120);
      });

      expect(mockPlayerInstance.seekTo).toHaveBeenCalledWith(120, true);
    });

    it("calls player.playVideo() after seeking so playback resumes immediately", async () => {
      const { result } = renderHookWithContainer(VIDEO_ID, [], queryClient);

      await act(async () => {
        result.current?.seekTo(60);
      });

      expect(mockPlayerInstance.playVideo).toHaveBeenCalledTimes(1);
    });

    it("passes the exact fractional seconds value to seekTo without rounding", async () => {
      const { result } = renderHookWithContainer(VIDEO_ID, [], queryClient);

      await act(async () => {
        result.current?.seekTo(3.75);
      });

      expect(mockPlayerInstance.seekTo).toHaveBeenCalledWith(3.75, true);
    });

    it("is a no-op (no throw) when the player is not yet created", () => {
      // @ts-expect-error — intentionally removing the global
      delete window.YT;
      vi.spyOn(document.head, "appendChild").mockImplementation((n) => n);

      const { result } = renderHookWithContainer(VIDEO_ID, [], queryClient);

      expect(() => result.current?.seekTo(30)).not.toThrow();
      expect(mockPlayerInstance.seekTo).not.toHaveBeenCalled();
    });
  });

  // =========================================================================
  // T011-9: togglePlayback
  // =========================================================================

  describe("togglePlayback (T011-9)", () => {
    it("calls player.pauseVideo() when getPlayerState() returns PLAYING (1)", async () => {
      const { result } = renderHookWithContainer(VIDEO_ID, [], queryClient);

      mockPlayerInstance.getPlayerState.mockReturnValue(1); // PLAYING

      await act(async () => {
        result.current?.togglePlayback();
      });

      expect(mockPlayerInstance.pauseVideo).toHaveBeenCalledTimes(1);
      expect(mockPlayerInstance.playVideo).not.toHaveBeenCalled();
    });

    it("calls player.playVideo() when getPlayerState() returns PAUSED (2)", async () => {
      const { result } = renderHookWithContainer(VIDEO_ID, [], queryClient);

      mockPlayerInstance.getPlayerState.mockReturnValue(2); // PAUSED

      await act(async () => {
        result.current?.togglePlayback();
      });

      expect(mockPlayerInstance.playVideo).toHaveBeenCalledTimes(1);
      expect(mockPlayerInstance.pauseVideo).not.toHaveBeenCalled();
    });

    it("calls player.playVideo() when getPlayerState() returns ENDED (0)", async () => {
      const { result } = renderHookWithContainer(VIDEO_ID, [], queryClient);

      mockPlayerInstance.getPlayerState.mockReturnValue(0); // ENDED

      await act(async () => {
        result.current?.togglePlayback();
      });

      expect(mockPlayerInstance.playVideo).toHaveBeenCalledTimes(1);
    });

    it("calls player.playVideo() when getPlayerState() returns UNSTARTED (-1)", async () => {
      const { result } = renderHookWithContainer(VIDEO_ID, [], queryClient);

      mockPlayerInstance.getPlayerState.mockReturnValue(-1); // UNSTARTED

      await act(async () => {
        result.current?.togglePlayback();
      });

      expect(mockPlayerInstance.playVideo).toHaveBeenCalledTimes(1);
    });

    it("is a no-op (no throw) when the player is not yet created", () => {
      // @ts-expect-error — intentionally removing the global
      delete window.YT;
      vi.spyOn(document.head, "appendChild").mockImplementation((n) => n);

      const { result } = renderHookWithContainer(VIDEO_ID, [], queryClient);

      expect(() => result.current?.togglePlayback()).not.toThrow();
      expect(mockPlayerInstance.pauseVideo).not.toHaveBeenCalled();
      expect(mockPlayerInstance.playVideo).not.toHaveBeenCalled();
    });
  });

  // =========================================================================
  // T011-10: toggleFollowPlayback
  // =========================================================================

  describe("toggleFollowPlayback (T011-10)", () => {
    it("starts with followPlayback=true (auto-scroll enabled by default)", () => {
      const { result } = renderHookWithContainer(VIDEO_ID, [], queryClient);
      expect(result.current?.followPlayback).toBe(true);
    });

    it("toggles followPlayback from true to false on the first call", async () => {
      const { result } = renderHookWithContainer(VIDEO_ID, [], queryClient);

      await act(async () => {
        result.current?.toggleFollowPlayback();
      });

      expect(result.current?.followPlayback).toBe(false);
    });

    it("toggles followPlayback back to true on the second consecutive call", async () => {
      const { result } = renderHookWithContainer(VIDEO_ID, [], queryClient);

      await act(async () => {
        result.current?.toggleFollowPlayback();
      });
      await act(async () => {
        result.current?.toggleFollowPlayback();
      });

      expect(result.current?.followPlayback).toBe(true);
    });
  });

  // =========================================================================
  // T011-11: Cleanup on unmount
  // =========================================================================

  describe("cleanup on unmount (T011-11)", () => {
    it("calls player.destroy() when the component unmounts", () => {
      const { unmount } = renderHookWithContainer(VIDEO_ID, [], queryClient);

      unmount();

      expect(mockPlayerInstance.destroy).toHaveBeenCalledTimes(1);
    });

    it("does not propagate exceptions thrown inside player.destroy()", () => {
      mockPlayerInstance.destroy.mockImplementationOnce(() => {
        throw new Error("iframe already removed from DOM");
      });

      const { unmount } = renderHookWithContainer(VIDEO_ID, [], queryClient);

      expect(() => unmount()).not.toThrow();
    });

    it("cancels the load timeout when unmounting before the API becomes ready", async () => {
      vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
      // @ts-expect-error — intentionally removing the global
      delete window.YT;
      vi.spyOn(document.head, "appendChild").mockImplementation((n) => n);

      const clearSpy = vi.spyOn(globalThis, "clearTimeout");

      const { unmount } = renderHookWithContainer(VIDEO_ID, [], queryClient);

      unmount();

      expect(clearSpy).toHaveBeenCalled();
    });

    it("removes pending rAF callbacks by cancelling the running polling loop", async () => {
      const { unmount } = renderHookWithContainer(VIDEO_ID, [], queryClient);

      // Start the polling loop.
      mockPlayerInstance.getPlayerState.mockReturnValue(1);
      await act(async () => {
        captured.options.events?.onStateChange?.({ target: mockPlayerInstance });
      });

      // There should be a pending rAF in the queue.
      expect(rafQueue.pendingCount).toBeGreaterThan(0);

      unmount();

      // After unmount, the player is destroyed.
      expect(mockPlayerInstance.destroy).toHaveBeenCalled();
      // The rAF queue is cancelled (cancelAnimationFrame called or loop exited).
      // Flushing remaining frames should not cause errors.
      await act(async () => {
        rafQueue.flushOnce(300);
      });
    });

    it("leaves seekTo as a safe no-op after unmount (playerRef set to null)", () => {
      const { result, unmount } = renderHookWithContainer(
        VIDEO_ID,
        [],
        queryClient
      );

      unmount();

      expect(() => result.current?.seekTo(10)).not.toThrow();
    });
  });

  // =========================================================================
  // T011-12: 10-second script load timeout fallback
  // =========================================================================

  describe("10-second script load timeout fallback (T011-12)", () => {
    beforeEach(() => {
      // @ts-expect-error — intentionally removing the global
      delete window.YT;
      vi.spyOn(document.head, "appendChild").mockImplementation((n) => n);
    });

    it("sets error with code=-1 after 10 seconds if the API never loads", async () => {
      vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });

      const { result } = renderHookWithContainer(VIDEO_ID, [], queryClient);

      expect(result.current?.error).toBeNull();

      await act(async () => {
        await vi.advanceTimersByTimeAsync(10_001);
      });

      expect(result.current?.error?.code).toBe(-1);
    });

    it("error message mentions '10 seconds' when the timeout fires", async () => {
      vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });

      const { result } = renderHookWithContainer(VIDEO_ID, [], queryClient);

      await act(async () => {
        await vi.advanceTimersByTimeAsync(10_001);
      });

      expect(result.current?.error?.message).toContain("10 seconds");
    });

    it("does not fire the timeout error if the API loads within 10 seconds", async () => {
      vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });

      const { result } = renderHookWithContainer(VIDEO_ID, [], queryClient);

      // API loads at 5 seconds — before the timeout.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(5_000);
        installYTGlobal();
        window.onYouTubeIframeAPIReady?.();
      });

      // Advance past the original 10 s deadline.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(6_000);
      });

      expect(result.current?.error).toBeNull();
    });

    it("does not fire the timeout error after the component unmounts", async () => {
      vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });

      const { result, unmount } = renderHookWithContainer(
        VIDEO_ID,
        [],
        queryClient
      );

      // Unmount before the 10 s timeout fires.
      unmount();

      await act(async () => {
        await vi.advanceTimersByTimeAsync(10_001);
      });

      // The `destroyed` flag inside the closure prevents the state update.
      expect(result.current?.error).toBeNull();
    });
  });

  // =========================================================================
  // T011-13: Binary search active segment matching
  // =========================================================================

  describe("binary search active segment matching (T011-13)", () => {
    /**
     * Drives the polling loop to emit a specific currentTime value.
     *
     * 1. Mocks getCurrentTime to return `currentTime`.
     * 2. Fires onStateChange with PLAYING so polling starts (rAF scheduled).
     * 3. Flushes rAF frames — first frame passes the 250 ms gate (lastPollTime=0,
     *    fakeNow=300, 300-0=300>=250) so getCurrentTime is called and
     *    setCurrentTime fires.
     */
    async function drivePollingToTime(currentTime: number): Promise<void> {
      mockPlayerInstance.getCurrentTime.mockReturnValue(currentTime);
      mockPlayerInstance.getPlayerState.mockReturnValue(1); // PLAYING
      await act(async () => {
        captured.options.events?.onStateChange?.({ target: mockPlayerInstance });
      });
      // Flush two frames: first frame at t=300ms triggers the poll (300>=250).
      // Second frame ensures the resulting re-render has settled.
      await rafQueue.flushFrames(2, 300);
    }

    it("returns activeSegmentId=null when the segments array is empty", async () => {
      const { result } = renderHookWithContainer(VIDEO_ID, [], queryClient);

      await drivePollingToTime(5);

      await waitFor(() => {
        expect(result.current?.currentTime).toBe(5);
      });
      expect(result.current?.activeSegmentId).toBeNull();
    });

    it("returns activeSegmentId=null when currentTime is before the first segment", async () => {
      const segments = [
        makeSegment(1, 10, 15), // starts at 10 s
        makeSegment(2, 15, 20),
      ];
      const { result } = renderHookWithContainer(VIDEO_ID, segments, queryClient);

      await drivePollingToTime(5); // before segment 1

      await waitFor(() => {
        expect(result.current?.currentTime).toBe(5);
      });
      expect(result.current?.activeSegmentId).toBeNull();
    });

    it("returns the matching segment id when currentTime falls inside a segment", async () => {
      const segments = [
        makeSegment(10, 0, 5),
        makeSegment(20, 5, 10),
        makeSegment(30, 10, 15),
      ];
      const { result } = renderHookWithContainer(VIDEO_ID, segments, queryClient);

      await drivePollingToTime(7); // inside segment 20 (start=5, end=10)

      await waitFor(() => {
        expect(result.current?.currentTime).toBe(7);
      });
      expect(result.current?.activeSegmentId).toBe(20);
    });

    it("returns activeSegmentId=null when currentTime falls in a gap between segments", async () => {
      const segments = [
        makeSegment(1, 0, 5),    // ends at 5
        makeSegment(2, 10, 15),  // gap: 5..10
      ];
      const { result } = renderHookWithContainer(VIDEO_ID, segments, queryClient);

      await drivePollingToTime(7); // in the gap

      await waitFor(() => {
        expect(result.current?.currentTime).toBe(7);
      });
      expect(result.current?.activeSegmentId).toBeNull();
    });

    it("returns the segment id when currentTime equals segment end_time (inclusive boundary)", async () => {
      const segments = [makeSegment(42, 0, 10)]; // end_time = 10
      const { result } = renderHookWithContainer(VIDEO_ID, segments, queryClient);

      await drivePollingToTime(10); // exactly at end_time

      await waitFor(() => {
        expect(result.current?.currentTime).toBe(10);
      });
      expect(result.current?.activeSegmentId).toBe(42);
    });

    it("returns activeSegmentId=null when currentTime is past the last segment's end_time", async () => {
      const segments = [makeSegment(1, 0, 10)]; // ends at 10
      const { result } = renderHookWithContainer(VIDEO_ID, segments, queryClient);

      await drivePollingToTime(15); // after end

      await waitFor(() => {
        expect(result.current?.currentTime).toBe(15);
      });
      expect(result.current?.activeSegmentId).toBeNull();
    });

    it("returns the first segment id when currentTime equals the segment's start_time", async () => {
      const segments = [
        makeSegment(7, 5, 10),
        makeSegment(8, 10, 15),
      ];
      const { result } = renderHookWithContainer(VIDEO_ID, segments, queryClient);

      await drivePollingToTime(5); // exactly at start_time of segment 7

      await waitFor(() => {
        expect(result.current?.currentTime).toBe(5);
      });
      expect(result.current?.activeSegmentId).toBe(7);
    });

    it("correctly selects among many segments via binary search", async () => {
      // 20 consecutive 5-second segments, ids 100..119.
      const segments = Array.from({ length: 20 }, (_, i) =>
        makeSegment(100 + i, i * 5, (i + 1) * 5)
      );
      const { result } = renderHookWithContainer(VIDEO_ID, segments, queryClient);

      // t=52 should land in segment 110 (start=50, end=55).
      await drivePollingToTime(52);

      await waitFor(() => {
        expect(result.current?.currentTime).toBe(52);
      });
      expect(result.current?.activeSegmentId).toBe(110);
    });

    it("updates activeSegmentId as currentTime advances through multiple segments", async () => {
      const segments = [
        makeSegment(1, 0, 5),
        makeSegment(2, 5, 10),
        makeSegment(3, 10, 15),
      ];
      const { result } = renderHookWithContainer(VIDEO_ID, segments, queryClient);

      // Drive polling: each drivePollingToTime call mocks a new currentTime,
      // fires onStateChange (startPolling no-ops if already polling), then
      // flushes frames.

      // t=2 → segment 1.
      await drivePollingToTime(2);
      await waitFor(() => {
        expect(result.current?.activeSegmentId).toBe(1);
      });

      // t=7 → segment 2.
      mockPlayerInstance.getCurrentTime.mockReturnValue(7);
      await rafQueue.flushFrames(2, 300);
      await waitFor(() => {
        expect(result.current?.activeSegmentId).toBe(2);
      });

      // t=12 → segment 3.
      mockPlayerInstance.getCurrentTime.mockReturnValue(12);
      await rafQueue.flushFrames(2, 300);
      await waitFor(() => {
        expect(result.current?.activeSegmentId).toBe(3);
      });
    });

    it("returns the first segment when currentTime=0 and the first segment starts at 0", async () => {
      const segments = [makeSegment(99, 0, 5)];
      const { result } = renderHookWithContainer(VIDEO_ID, segments, queryClient);

      await drivePollingToTime(0);

      await waitFor(() => {
        expect(result.current?.currentTime).toBe(0);
      });
      expect(result.current?.activeSegmentId).toBe(99);
    });
  });

  // =========================================================================
  // T011-14: Delayed container mounting (waitForContainer slow path)
  //
  // These tests cover the rAF-polling branch of waitForContainer, which fires
  // when containerRef.current is null at effect time (e.g. the host component
  // conditionally renders the <div> only after some async data resolves).
  //
  // Strategy
  // --------
  // We use a new test harness `renderHookWithoutContainer` that renders the
  // hook but initially omits the <div>, so `containerRef.current` is null when
  // the useEffect fires. Each test then uses `rerender` to mount the div on a
  // subsequent render and flushes rAF frames to drive the poll to completion.
  // =========================================================================

  describe("delayed container mounting — waitForContainer slow path (T011-14)", () => {
    // -----------------------------------------------------------------------
    // Harness that renders the hook without the container div initially.
    //
    // The `showContainer` prop controls whether the <div ref={containerRef}>
    // is rendered. Passing `false` initially means containerRef.current will
    // be null when useEffect fires, forcing the rAF polling slow path.
    // -----------------------------------------------------------------------

    interface DelayedHookHarness {
      result: MutableRefObject<UseYouTubePlayerResult | null>;
      /** Re-render with the container div present so the ref becomes non-null. */
      mountContainer: () => void;
      unmount: () => void;
    }

    function renderHookWithoutContainer(
      videoId: string,
      segments: TranscriptSegment[],
      queryClient: QueryClient
    ): DelayedHookHarness {
      const resultRef: MutableRefObject<UseYouTubePlayerResult | null> = {
        current: null,
      };

      // showContainerRef lets mountContainer trigger a rerender without
      // rebuilding the entire harness. We update it and call rerender() with
      // the same props so React re-runs the TestComponent body.
      const showContainerRef: MutableRefObject<boolean> = { current: false };

      function TestComponent({
        vid,
        segs,
        resultHolder,
        showContainerHolder,
      }: {
        vid: string;
        segs: TranscriptSegment[];
        resultHolder: MutableRefObject<UseYouTubePlayerResult | null>;
        showContainerHolder: MutableRefObject<boolean>;
      }) {
        const hookResult = useYouTubePlayer({ videoId: vid, segments: segs });
        resultHolder.current = hookResult;
        // Only render the container div when showContainerHolder.current is
        // true. On the initial render it is false, so containerRef.current
        // stays null when the effect fires.
        if (!showContainerHolder.current) {
          return null;
        }
        return React.createElement("div", {
          "data-testid": "player-container-delayed",
          ref: hookResult.containerRef as React.RefObject<HTMLDivElement>,
        });
      }

      const { unmount, rerender } = render(
        React.createElement(
          QueryClientProvider,
          { client: queryClient },
          React.createElement(TestComponent, {
            vid: videoId,
            segs: segments,
            resultHolder: resultRef,
            showContainerHolder: showContainerRef,
          })
        )
      );

      function mountContainer(): void {
        // Flip the flag before calling rerender so the next render body sees
        // showContainerHolder.current === true and attaches the ref.
        showContainerRef.current = true;
        rerender(
          React.createElement(
            QueryClientProvider,
            { client: queryClient },
            React.createElement(TestComponent, {
              vid: videoId,
              segs: segments,
              resultHolder: resultRef,
              showContainerHolder: showContainerRef,
            })
          )
        );
      }

      return { result: resultRef, mountContainer, unmount };
    }

    // -----------------------------------------------------------------------
    // T011-14-1: Player creation succeeds when the container becomes non-null
    //            after initial render (the canonical slow-path scenario).
    //
    // Timeline:
    //   Frame 0 (effect fires): containerRef.current === null → slow path
    //   rAF frame 1: containerRef still null → re-queues poll
    //   mountContainer(): React attaches the div → containerRef.current ≠ null
    //   rAF frame 2: containerRef.current !== null → createPlayer() called
    // -----------------------------------------------------------------------

    it("creates the player once the container ref becomes non-null after a few rAF frames", async () => {
      const { mountContainer } = renderHookWithoutContainer(
        VIDEO_ID,
        [],
        queryClient
      );

      // Verify the YT.Player constructor has not been called yet — the
      // container is null so the rAF loop is spinning but createPlayer() has
      // not fired.
      expect(captured.options.videoId).toBeUndefined();

      // Flush one rAF frame while the container is still absent. The poll
      // finds containerRef.current === null and reschedules.
      await act(async () => {
        rafQueue.flushOnce(16);
      });
      expect(captured.options.videoId).toBeUndefined();

      // Mount the container div so containerRef.current becomes non-null.
      await act(async () => {
        mountContainer();
      });

      // Flush the next rAF frame — the poll now finds containerRef.current
      // populated and calls createPlayer().
      await act(async () => {
        rafQueue.flushOnce(16);
      });

      // The YT.Player constructor must have been called with the correct videoId.
      expect(captured.options.videoId).toBe(VIDEO_ID);
    });

    // -----------------------------------------------------------------------
    // T011-14-2: The 10-second timeout is for script load failures only.
    //            Container polling delays (a few frames, ~16 ms each) must
    //            NOT trigger the timeout error.
    //
    // The hook only arms the setTimeout on the script-loading branch
    // (window.YT is undefined). In these slow-path tests window.YT IS
    // defined (installYTGlobal is called in beforeEach), so no timeout is
    // set and error must remain null regardless of how many rAF frames pass.
    // -----------------------------------------------------------------------

    it("does not set an error when the container takes a few frames to mount (timeout is for script load only)", async () => {
      const { result, mountContainer } = renderHookWithoutContainer(
        VIDEO_ID,
        [],
        queryClient
      );

      // Flush several frames without mounting the container.
      await act(async () => {
        rafQueue.flushOnce(16);
        rafQueue.flushOnce(16);
        rafQueue.flushOnce(16);
      });

      // No error should have appeared — the rAF poll is still running.
      expect(result.current?.error).toBeNull();

      // Now mount the container and let the player creation complete.
      await act(async () => {
        mountContainer();
      });
      await act(async () => {
        rafQueue.flushOnce(16);
      });

      // Error is still null after successful player creation.
      expect(result.current?.error).toBeNull();
    });

    // -----------------------------------------------------------------------
    // T011-14-3: Cleanup cancels the rAF poll before the container mounts.
    //
    // If the component unmounts while waitForContainer is still polling (i.e.
    // the container never appeared), the cleanup function must:
    //   a) call cancelAnimationFrame so no further frames fire, AND
    //   b) set destroyedRef.current = true so the poll guard exits even if a
    //      frame already in-flight was not cancelled in time.
    //
    // After unmount, flushing leftover rAF frames must not call createPlayer.
    // -----------------------------------------------------------------------

    it("cancels the rAF poll when unmounted before the container ever mounts, preventing player creation", async () => {
      const { unmount } = renderHookWithoutContainer(VIDEO_ID, [], queryClient);

      // Container never mounts — the poll is still running.
      await act(async () => {
        rafQueue.flushOnce(16);
      });

      // Confirm player has not been created yet.
      expect(captured.options.videoId).toBeUndefined();

      // Unmount — this sets destroyedRef.current = true and calls
      // cancelAnimationFrame via the cleanup returned by waitForContainer.
      unmount();

      // Flush any remaining rAF frames that may have been registered just
      // before the cancel fired. Because destroyedRef.current is now true the
      // poll() guard exits without calling createPlayer or re-queuing.
      await act(async () => {
        rafQueue.flushOnce(16);
        rafQueue.flushOnce(16);
      });

      // The player must never have been created.
      expect(captured.options.videoId).toBeUndefined();
    });

    // -----------------------------------------------------------------------
    // T011-14-4: cancelAnimationFrame is called on cleanup when the poll was
    //            in-flight.
    //
    // The cancel handle returned by waitForContainer must be invoked by the
    // effect cleanup, which delegates to cancelAnimationFrame. We verify this
    // by checking that cancelAnimationFrame was called after unmount.
    // -----------------------------------------------------------------------

    it("calls cancelAnimationFrame when the component unmounts while the container poll is running", async () => {
      const { unmount } = renderHookWithoutContainer(VIDEO_ID, [], queryClient);

      const cancelSpy = vi.mocked(globalThis.cancelAnimationFrame);
      const cancelCallsBefore = cancelSpy.mock.calls.length;

      // Let the poll register at least one rAF frame.
      await act(async () => {
        rafQueue.flushOnce(16);
      });

      // Unmount while the container is still absent.
      unmount();

      // cancelAnimationFrame must have been called at least once more than
      // before the unmount (the cleanup cancels the in-flight rAF).
      expect(cancelSpy.mock.calls.length).toBeGreaterThan(cancelCallsBefore);
    });
  });

  // =========================================================================
  // Return value shape
  // =========================================================================

  describe("return value shape", () => {
    it("exposes containerRef as a React ref object with a current property", () => {
      const { result } = renderHookWithContainer(VIDEO_ID, [], queryClient);
      expect(result.current?.containerRef).toBeDefined();
      expect("current" in (result.current?.containerRef ?? {})).toBe(true);
    });

    it("exposes seekTo, togglePlayback, toggleFollowPlayback as functions", () => {
      const { result } = renderHookWithContainer(VIDEO_ID, [], queryClient);
      expect(typeof result.current?.seekTo).toBe("function");
      expect(typeof result.current?.togglePlayback).toBe("function");
      expect(typeof result.current?.toggleFollowPlayback).toBe("function");
    });

    it("exposes all expected state fields with their correct initial values", () => {
      const { result } = renderHookWithContainer(VIDEO_ID, [], queryClient);
      expect(result.current?.isReady).toBe(false);
      expect(result.current?.isPlaying).toBe(false);
      expect(result.current?.currentTime).toBe(0);
      expect(result.current?.activeSegmentId).toBeNull();
      expect(result.current?.error).toBeNull();
      expect(result.current?.followPlayback).toBe(true);
    });
  });
});
