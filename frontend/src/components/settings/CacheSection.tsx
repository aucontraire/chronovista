/**
 * CacheSection — displays local image cache statistics and provides a
 * "Clear Cache" action within the Settings page.
 *
 * Implements Feature 049 requirements:
 * - FR-016: Show number of cached images and total disk space used
 * - FR-017: "Clear Cache" button with confirmation dialog
 * - FR-021: Loading skeleton while fetching
 * - FR-022: Inline error with retry button on API failure
 * - FR-029: ARIA labels for cache statistics area and clear button
 * - US3-AS3: Empty state when total_count is 0
 *
 * @module components/settings/CacheSection
 */

import { useState, useRef, useEffect } from "react";

import { useCacheStatus } from "../../hooks/useCacheStatus";

// ---------------------------------------------------------------------------
// Icons (inline SVG — no icon library dependency)
// ---------------------------------------------------------------------------

function ExclamationTriangleIcon({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      fill="currentColor"
      viewBox="0 0 24 24"
      className={className}
      aria-hidden="true"
    >
      <path
        fillRule="evenodd"
        d="M9.401 3.003c1.155-2 4.043-2 5.197 0l7.355 12.748c1.154 2-.29 4.5-2.599 4.5H4.645c-2.309 0-3.752-2.5-2.598-4.5L9.4 3.003ZM12 8.25a.75.75 0 0 1 .75.75v3.75a.75.75 0 0 1-1.5 0V9a.75.75 0 0 1 .75-.75Zm0 8.25a.75.75 0 1 0 0-1.5.75.75 0 0 0 0 1.5Z"
        clipRule="evenodd"
      />
    </svg>
  );
}

function SpinnerIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      aria-hidden="true"
    >
      <circle
        className="opacity-25"
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="4"
      />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
      />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Loading skeleton
// ---------------------------------------------------------------------------

function CacheSkeleton() {
  return (
    <div
      role="status"
      aria-label="Loading cache statistics"
      aria-busy="true"
      className="animate-pulse"
    >
      <div className="flex items-center justify-between">
        <div className="space-y-2">
          <div className="h-4 bg-slate-200 rounded w-48" />
          <div className="h-3 bg-slate-100 rounded w-32" />
        </div>
        <div className="h-9 bg-slate-200 rounded-md w-28" />
      </div>
      <span className="sr-only">Loading cache statistics…</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Clear cache confirmation dialog (inline, matching LanguagePreferencesSection)
// ---------------------------------------------------------------------------

interface ClearConfirmationProps {
  isPurging: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

function ClearConfirmation({
  isPurging,
  onConfirm,
  onCancel,
}: ClearConfirmationProps) {
  const confirmRef = useRef<HTMLButtonElement>(null);

  // WCAG 2.4.3: Focus the Confirm button on mount
  useEffect(() => {
    confirmRef.current?.focus();
  }, []);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "Escape") {
      onCancel();
    }
  };

  return (
    <div
      role="alertdialog"
      aria-modal="false"
      aria-labelledby="cache-clear-confirm-label"
      aria-describedby="cache-clear-confirm-desc"
      className="flex flex-wrap items-center gap-3 bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 mt-4"
      onKeyDown={handleKeyDown}
    >
      <ExclamationTriangleIcon className="w-5 h-5 text-amber-600 flex-shrink-0" />
      <div className="flex-1 min-w-0">
        <p
          id="cache-clear-confirm-label"
          className="text-sm font-semibold text-amber-900"
        >
          Clear all cached images?
        </p>
        <p
          id="cache-clear-confirm-desc"
          className="text-xs text-amber-700 mt-0.5"
        >
          Cached images will need to be re-downloaded on next access.
        </p>
      </div>
      <div className="flex gap-2 flex-shrink-0">
        <button
          ref={confirmRef}
          type="button"
          onClick={onConfirm}
          disabled={isPurging}
          aria-busy={isPurging}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-white bg-rose-600 hover:bg-rose-700 disabled:bg-rose-400 rounded-md focus:outline-none focus-visible:ring-2 focus-visible:ring-rose-500 focus-visible:ring-offset-2 transition-colors"
        >
          {isPurging && <SpinnerIcon className="w-3.5 h-3.5 animate-spin" />}
          {isPurging ? "Clearing…" : "Yes, clear cache"}
        </button>
        <button
          type="button"
          onClick={onCancel}
          disabled={isPurging}
          className="inline-flex items-center px-3 py-1.5 text-sm font-medium text-slate-700 bg-white hover:bg-slate-50 border border-slate-300 rounded-md focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-500 focus-visible:ring-offset-2 disabled:opacity-50 transition-colors"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

/**
 * CacheSection renders the image cache card within the Settings page.
 * It is fully self-contained — all data and mutations come from the
 * `useCacheStatus` hook.
 *
 * @example
 * ```tsx
 * <CacheSection />
 * ```
 */
export function CacheSection() {
  const { cacheStatus, isLoading, error, purgeCache, isPurging } =
    useCacheStatus();

  const [showClearConfirm, setShowClearConfirm] = useState(false);

  // Ref to the "Clear Cache" button so focus can be restored after the
  // confirmation dialog is dismissed (WCAG 2.4.3).
  const clearButtonRef = useRef<HTMLButtonElement>(null);

  // aria-live announcement after a successful purge
  const [announcement, setAnnouncement] = useState("");

  // Announce when isPurging transitions from true → false (purge completed)
  const wasPurgingRef = useRef(false);
  useEffect(() => {
    if (wasPurgingRef.current && !isPurging) {
      setAnnouncement("Image cache cleared.");
      const t = setTimeout(() => setAnnouncement(""), 3000);
      return () => clearTimeout(t);
    }
    wasPurgingRef.current = isPurging;
  }, [isPurging]);

  function handleConfirmClear() {
    purgeCache();
    setShowClearConfirm(false);
  }

  function handleCancelClear() {
    setShowClearConfirm(false);
    // WCAG 2.4.3: Return focus to the button that opened the confirmation.
    clearButtonRef.current?.focus();
  }

  // Derive cache statistics display text
  const hasImages = cacheStatus !== undefined && cacheStatus.total_count > 0;
  const statisticsText =
    cacheStatus === undefined
      ? null
      : cacheStatus.total_count === 0
      ? "No cached images"
      : `${cacheStatus.total_count.toLocaleString()} ${
          cacheStatus.total_count === 1 ? "image" : "images"
        }, ${cacheStatus.total_size_display}`;

  return (
    <section aria-labelledby="cache-heading">
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6">
        {/* ---------------------------------------------------------------- */}
        {/* Section header                                                   */}
        {/* ---------------------------------------------------------------- */}
        <div className="mb-6">
          <h3
            id="cache-heading"
            className="text-lg font-semibold text-slate-900"
          >
            Cache
          </h3>
          <p className="text-sm text-slate-500 mt-1">
            Locally cached thumbnail images used to reduce network requests.
          </p>
        </div>

        {/* ---------------------------------------------------------------- */}
        {/* aria-live region for purge completion announcements (FR-029)    */}
        {/* ---------------------------------------------------------------- */}
        <div
          role="status"
          aria-live="polite"
          aria-atomic="true"
          className="sr-only"
        >
          {announcement}
        </div>

        {/* ---------------------------------------------------------------- */}
        {/* Loading state (FR-021)                                           */}
        {/* ---------------------------------------------------------------- */}
        {isLoading && <CacheSkeleton />}

        {/* ---------------------------------------------------------------- */}
        {/* Error state (FR-022)                                             */}
        {/* ---------------------------------------------------------------- */}
        {!isLoading && error !== null && (
          <div
            role="alert"
            className="flex items-start gap-3 bg-rose-50 border border-rose-200 rounded-lg px-4 py-3"
          >
            <ExclamationTriangleIcon className="w-5 h-5 text-rose-600 flex-shrink-0 mt-0.5" />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-rose-800">
                Failed to load cache statistics
              </p>
              <p className="text-xs text-rose-700 mt-1">{error.message}</p>
            </div>
            <button
              type="button"
              onClick={() => window.location.reload()}
              className="flex-shrink-0 text-sm font-medium text-rose-700 hover:text-rose-900 underline focus:outline-none focus-visible:ring-2 focus-visible:ring-rose-500 focus-visible:ring-offset-2 transition-colors"
            >
              Retry
            </button>
          </div>
        )}

        {/* ---------------------------------------------------------------- */}
        {/* Main content (once loaded and no error)                         */}
        {/* ---------------------------------------------------------------- */}
        {!isLoading && error === null && cacheStatus !== undefined && (
          <>
            {/* Statistics row + Clear Cache button (FR-016, FR-017) */}
            <div className="flex items-center justify-between gap-4">
              {/* Cache statistics display (FR-016, US3-AS3) */}
              <dl aria-label="Cache statistics">
                <div>
                  <dt className="sr-only">Cached images</dt>
                  <dd
                    className={`text-sm font-medium ${
                      hasImages ? "text-slate-800" : "text-slate-500 italic"
                    }`}
                  >
                    {statisticsText}
                  </dd>
                </div>
              </dl>

              {/* Clear Cache button — only shown when images are cached (FR-017) */}
              {hasImages && !showClearConfirm && (
                <button
                  ref={clearButtonRef}
                  type="button"
                  onClick={() => setShowClearConfirm(true)}
                  disabled={isPurging}
                  aria-label="Clear all cached images"
                  className="flex-shrink-0 inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-slate-700 bg-white hover:bg-slate-50 border border-slate-300 disabled:opacity-50 disabled:cursor-not-allowed rounded-md focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-500 focus-visible:ring-offset-2 transition-colors"
                >
                  {isPurging && (
                    <SpinnerIcon className="w-3.5 h-3.5 animate-spin" />
                  )}
                  {isPurging ? "Clearing…" : "Clear Cache"}
                </button>
              )}
            </div>

            {/* Confirmation dialog (FR-017) */}
            {showClearConfirm && (
              <ClearConfirmation
                isPurging={isPurging}
                onConfirm={handleConfirmClear}
                onCancel={handleCancelClear}
              />
            )}
          </>
        )}
      </div>
    </section>
  );
}
