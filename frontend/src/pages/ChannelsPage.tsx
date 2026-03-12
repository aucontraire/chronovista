/**
 * ChannelsPage component displays the list of channels with all states.
 *
 * Features (Feature 027, US-3):
 * - Sort dropdown (video_count/name) with URL state persistence
 * - Subscription filter tabs (All/Subscribed/Not Subscribed) with URL state
 * - Dynamic channel count header reflecting filtered results
 * - ARIA live region for count announcement
 * - Pagination reset on filter/sort change
 *
 * Feature 042, US6 (T030-T033):
 * - Client-side channel name search with case-insensitive substring matching
 * - "No channels match" empty state for zero filtered results (FR-018)
 * - Disabled search field with "Loading channels..." placeholder during load (FR-024)
 * - Escape key clears search field (FR-026)
 * - Auto-focus search on mount (FR-026)
 * - Search resets on page navigation (component-local state, natural unmount reset)
 *
 * Feature 042, US7 (T034, T037):
 * - SkipLink to main content area (FR-019, NFR-004, NFR-006)
 */

import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { ChannelCard } from "../components/ChannelCard";
import { SkipLink } from "../components/SkipLink";
import { SortDropdown } from "../components/SortDropdown";
import { useChannels } from "../hooks/useChannels";
import type { SubscriptionFilter } from "../hooks/useChannels";
import type { ChannelSortField, SortOrder, SortOption } from "../types/filters";

/**
 * Sort options for channels (Feature 027, FR-013).
 */
const CHANNEL_SORT_OPTIONS: SortOption<ChannelSortField>[] = [
  { field: "video_count", label: "Video Count", defaultOrder: "desc" },
  { field: "name", label: "Name", defaultOrder: "asc" },
];

/**
 * Valid subscription filter tab values.
 */
const SUBSCRIPTION_TABS: Array<{
  value: SubscriptionFilter;
  label: string;
}> = [
  { value: "all", label: "All" },
  { value: "subscribed", label: "Subscribed" },
  { value: "not_subscribed", label: "Not Subscribed" },
];

/** Stable ID used by SkipLink and main content container (T034, T037). */
const MAIN_CONTENT_ID = "channels-main-content";

/**
 * Skeleton card for channel loading state.
 * Matches ChannelCard dimensions with circular thumbnail placeholder.
 */
function ChannelSkeletonCard() {
  return (
    <div
      className="bg-white rounded-xl shadow-md border border-gray-100 p-5 animate-pulse"
      aria-hidden="true"
    >
      {/* Circular thumbnail skeleton */}
      <div className="mb-4 flex justify-center">
        <div className="w-22 h-22 bg-gray-200 rounded-full" />
      </div>

      {/* Channel name skeleton */}
      <div className="h-5 bg-gray-200 rounded-md w-3/4 mx-auto mb-3" />

      {/* Subscriber count skeleton */}
      <div className="h-4 bg-gray-200 rounded-md w-1/2 mx-auto mb-2" />

      {/* Video count skeleton */}
      <div className="h-4 bg-gray-200 rounded-md w-2/5 mx-auto" />
    </div>
  );
}

/**
 * Loading state specifically for channels with appropriate skeleton cards.
 */
function ChannelLoadingState({ count = 6 }: { count?: number }) {
  return (
    <div
      className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6"
      role="status"
      aria-label="Loading channels"
      aria-live="polite"
      aria-busy="true"
    >
      {Array.from({ length: count }, (_, index) => (
        <ChannelSkeletonCard key={index} />
      ))}
      <span className="sr-only">Loading channels...</span>
    </div>
  );
}

/**
 * Pagination status component showing "X of Y channels".
 */
interface PaginationStatusProps {
  loadedCount: number;
  total: number | null;
}

function PaginationStatus({ loadedCount, total }: PaginationStatusProps) {
  if (total === null) {
    return (
      <p className="text-sm text-gray-500 text-center py-2">
        Showing {loadedCount} channel{loadedCount !== 1 ? "s" : ""}
      </p>
    );
  }

  return (
    <p className="text-sm text-gray-500 text-center py-2">
      Showing {loadedCount} of {total} channel{total !== 1 ? "s" : ""}
    </p>
  );
}

/**
 * Message shown when all channels have been loaded.
 */
interface AllLoadedMessageProps {
  total: number;
}

function AllLoadedMessage({ total }: AllLoadedMessageProps) {
  return (
    <p className="text-sm text-gray-500 text-center py-4 border-t border-gray-200">
      All {total} channel{total !== 1 ? "s" : ""} loaded
    </p>
  );
}

/**
 * Empty state specific to channels with filter-aware messaging.
 */
interface ChannelEmptyStateProps {
  subscriptionFilter: SubscriptionFilter;
}

function ChannelEmptyState({ subscriptionFilter }: ChannelEmptyStateProps) {
  const getEmptyStateContent = () => {
    switch (subscriptionFilter) {
      case "subscribed":
        return {
          heading: "No subscribed channels",
          message:
            "None of your synced channels are marked as subscribed. Subscription status is synced from your YouTube data.",
          showCommand: true,
        };
      case "not_subscribed":
        return {
          heading: "No unsubscribed channels",
          message:
            "All your synced channels are currently subscribed.",
          showCommand: false,
        };
      default: // "all"
        return {
          heading: "No channels yet",
          message:
            "You haven\u2019t synced any channels yet. Get started by syncing your YouTube data.",
          showCommand: true,
        };
    }
  };

  const { heading, message, showCommand } = getEmptyStateContent();

  return (
    <div
      className="bg-white border border-gray-200 rounded-xl shadow-lg p-12 text-center flex flex-col items-center justify-center min-h-[400px]"
      role="status"
      aria-label={heading}
    >
      {/* Channel Icon */}
      <div className="mx-auto w-20 h-20 mb-6 text-gray-400 bg-gray-100 rounded-full p-4">
        <svg
          xmlns="http://www.w3.org/2000/svg"
          fill="none"
          viewBox="0 0 24 24"
          strokeWidth={1.5}
          stroke="currentColor"
          aria-hidden="true"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M18 18.72a9.094 9.094 0 0 0 3.741-.479 3 3 0 0 0-4.682-2.72m.94 3.198.001.031c0 .225-.012.447-.037.666A11.944 11.944 0 0 1 12 21c-2.17 0-4.207-.576-5.963-1.584A6.062 6.062 0 0 1 6 18.719m12 0a5.971 5.971 0 0 0-.941-3.197m0 0A5.995 5.995 0 0 0 12 12.75a5.995 5.995 0 0 0-5.058 2.772m0 0a3 3 0 0 0-4.681 2.72 8.986 8.986 0 0 0 3.74.477m.94-3.197a5.971 5.971 0 0 0-.94 3.197M15 6.75a3 3 0 1 1-6 0 3 3 0 0 1 6 0Zm6 3a2.25 2.25 0 1 1-4.5 0 2.25 2.25 0 0 1 4.5 0Zm-13.5 0a2.25 2.25 0 1 1-4.5 0 2.25 2.25 0 0 1 4.5 0Z"
          />
        </svg>
      </div>

      {/* Heading */}
      <h3 className="text-xl font-semibold text-gray-900 mb-3">
        {heading}
      </h3>

      {/* Instructions */}
      <p className="text-gray-600 mb-6 max-w-sm">{message}</p>

      {/* CLI Command */}
      {showCommand && (
        <>
          <div className="inline-block mb-6">
            <code className="bg-gray-900 text-green-400 px-5 py-3 rounded-lg font-mono text-sm shadow-md block">
              $ chronovista sync
            </code>
          </div>

          {/* Additional Help */}
          <p className="text-sm text-gray-500 max-w-xs">
            This will fetch your YouTube channels, videos, and transcripts.
          </p>
        </>
      )}
    </div>
  );
}

/**
 * Empty state shown when the channel search filter returns zero results (FR-018).
 */
interface ChannelSearchEmptyStateProps {
  searchQuery: string;
}

function ChannelSearchEmptyState({ searchQuery }: ChannelSearchEmptyStateProps) {
  return (
    <div
      className="bg-white border border-gray-200 rounded-xl shadow-lg p-12 text-center flex flex-col items-center justify-center min-h-[300px]"
      role="status"
      aria-label="No channels match search"
    >
      <div className="mx-auto w-16 h-16 mb-5 text-gray-400 bg-gray-100 rounded-full p-4">
        <svg
          xmlns="http://www.w3.org/2000/svg"
          fill="none"
          viewBox="0 0 24 24"
          strokeWidth={1.5}
          stroke="currentColor"
          aria-hidden="true"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z"
          />
        </svg>
      </div>
      <h3 className="text-lg font-semibold text-gray-900 mb-2">
        No channels match
      </h3>
      <p className="text-gray-600 max-w-xs">
        No channels found matching{" "}
        <strong className="font-medium">&ldquo;{searchQuery}&rdquo;</strong>.
        Try a different search term.
      </p>
    </div>
  );
}

/**
 * Subscription filter tabs component (page-specific, NOT shared per Rule of Three).
 */
interface SubscriptionFilterTabsProps {
  currentFilter: SubscriptionFilter;
  onFilterChange: (filter: SubscriptionFilter) => void;
}

function SubscriptionFilterTabs({
  currentFilter,
  onFilterChange,
}: SubscriptionFilterTabsProps) {
  return (
    <nav aria-label="Subscription filter" role="tablist">
      <div className="flex gap-1 rounded-lg bg-gray-100 p-1">
        {SUBSCRIPTION_TABS.map((tab) => {
          const isActive = currentFilter === tab.value;
          return (
            <button
              key={tab.value}
              type="button"
              role="tab"
              aria-selected={isActive}
              onClick={() => onFilterChange(tab.value)}
              className={`min-h-[44px] px-4 py-2 rounded-md text-sm font-medium transition-colors whitespace-nowrap ${
                isActive
                  ? "bg-white text-gray-900 shadow-sm"
                  : "text-gray-600 hover:text-gray-900 hover:bg-gray-50"
              }`}
            >
              {tab.label}
            </button>
          );
        })}
      </div>
    </nav>
  );
}

/**
 * Channel search input above the channel grid (T030, T031, T032).
 *
 * - Accessible label via sr-only <label> (NFR-002)
 * - Disabled with "Loading channels..." placeholder while data loads (FR-024)
 * - Clear (×) button resets the filter
 * - Escape key handler clears the field (FR-026)
 */
interface ChannelSearchInputProps {
  value: string;
  onChange: (value: string) => void;
  onClear: () => void;
  disabled: boolean;
  inputRef: React.RefObject<HTMLInputElement | null>;
}

function ChannelSearchInput({
  value,
  onChange,
  onClear,
  disabled,
  inputRef,
}: ChannelSearchInputProps) {
  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Escape") {
      onClear();
    }
  };

  return (
    <div className="relative mb-4">
      <label htmlFor="channel-search" className="sr-only">
        Search channels by name
      </label>
      {/* Search icon */}
      <div className="pointer-events-none absolute inset-y-0 left-3 flex items-center">
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 20 20"
          fill="currentColor"
          className="w-4 h-4 text-gray-400"
          aria-hidden="true"
        >
          <path
            fillRule="evenodd"
            d="M9 3.5a5.5 5.5 0 1 0 0 11 5.5 5.5 0 0 0 0-11ZM2 9a7 7 0 1 1 12.452 4.391l3.328 3.329a.75.75 0 1 1-1.06 1.06l-3.329-3.328A7 7 0 0 1 2 9Z"
            clipRule="evenodd"
          />
        </svg>
      </div>

      <input
        ref={inputRef}
        id="channel-search"
        type="search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        placeholder={disabled ? "Loading channels..." : "Search channels by name..."}
        aria-label="Search channels by name"
        className={`w-full pl-9 pr-10 py-2.5 text-sm border rounded-lg bg-white text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors ${
          disabled
            ? "border-gray-200 bg-gray-50 text-gray-400 cursor-not-allowed"
            : "border-gray-300 hover:border-gray-400"
        }`}
      />

      {/* Clear button — shown only when there is a value and input is enabled */}
      {/* NFR-001: min 44×44px touch target via min-w/min-h */}
      {value && !disabled && (
        <button
          type="button"
          onClick={onClear}
          aria-label="Clear channel search"
          className="absolute inset-y-0 right-0 flex items-center justify-center min-w-[44px] min-h-[44px] text-gray-400 hover:text-gray-600 focus:outline-none focus:text-gray-600"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 20 20"
            fill="currentColor"
            className="w-4 h-4"
            aria-hidden="true"
          >
            <path d="M6.28 5.22a.75.75 0 0 0-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 1 0 1.06 1.06L10 11.06l3.72 3.72a.75.75 0 1 0 1.06-1.06L11.06 10l3.72-3.72a.75.75 0 0 0-1.06-1.06L10 8.94 6.28 5.22Z" />
          </svg>
        </button>
      )}
    </div>
  );
}

/**
 * ChannelsPage displays channels with loading, error, and empty states.
 * Includes sort dropdown, subscription filter tabs, channel name search,
 * and infinite scroll.
 */
export function ChannelsPage() {
  // URL params for filter and sort
  const [searchParams, setSearchParams] = useSearchParams();

  // Parse subscription filter from URL
  const subParam = searchParams.get("subscription") || "all";
  const subscriptionFilter = (
    ["all", "subscribed", "not_subscribed"].includes(subParam) ? subParam : "all"
  ) as SubscriptionFilter;

  // Parse sort from URL (default: video_count desc)
  const sortByParam = searchParams.get("sort_by") || "video_count";
  const sortOrderParam = searchParams.get("sort_order") || "desc";
  const sortBy = (
    ["video_count", "name"].includes(sortByParam) ? sortByParam : "video_count"
  ) as ChannelSortField;
  const sortOrder = (
    ["asc", "desc"].includes(sortOrderParam) ? sortOrderParam : "desc"
  ) as SortOrder;

  // Client-side channel name search (T031, T033).
  // Component-local state: automatically resets on unmount/remount (page navigation).
  const [channelSearch, setChannelSearch] = useState("");

  // Ref for auto-focusing the search input on page load (T032).
  const searchInputRef = useRef<HTMLInputElement | null>(null);

  // Fetch channels with current sort and filter
  const {
    channels,
    total,
    loadedCount,
    isLoading,
    isError,
    error,
    hasNextPage,
    isFetchingNextPage,
    fetchNextPage,
    retry,
    loadMoreRef,
  } = useChannels({ sortBy, sortOrder, isSubscribed: subscriptionFilter });

  // Eagerly fetch all remaining pages when the user is actively searching (FR-017 fix).
  // Client-side filtering can only work against loaded data, so we must ensure the full
  // dataset is in memory before declaring "no results found".
  useEffect(() => {
    if (channelSearch.trim() && hasNextPage && !isFetchingNextPage) {
      fetchNextPage();
    }
  }, [channelSearch, hasNextPage, isFetchingNextPage, fetchNextPage]);

  // Set page title
  useEffect(() => {
    document.title = "Channels - ChronoVista";
    return () => {
      document.title = "ChronoVista";
    };
  }, []);

  // Auto-focus search input on mount (T032, FR-026).
  useEffect(() => {
    searchInputRef.current?.focus();
  }, []);

  // Scroll to top when filter or sort changes (FR-031)
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, [subscriptionFilter, sortBy, sortOrder]);

  // Handle subscription filter change (update URL param, reset pagination)
  const handleSubscriptionChange = (newFilter: SubscriptionFilter) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      if (newFilter === "all") {
        next.delete("subscription");
      } else {
        next.set("subscription", newFilter);
      }
      return next;
    });
  };

  // Client-side filter: case-insensitive substring match on channel name (FR-017, T031).
  const filteredChannels = channelSearch.trim()
    ? channels.filter((ch) =>
        ch.title.toLowerCase().includes(channelSearch.toLowerCase())
      )
    : channels;

  // Channel count header text (reflects server total, not client-filtered count)
  const countText =
    total !== null
      ? `${total} channel${total !== 1 ? "s" : ""}`
      : null;

  // Toolbar with filter tabs and sort dropdown (shown in all states)
  const toolbar = (
    <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
      <SubscriptionFilterTabs
        currentFilter={subscriptionFilter}
        onFilterChange={handleSubscriptionChange}
      />
      <SortDropdown
        options={CHANNEL_SORT_OPTIONS}
        defaultField="video_count"
        defaultOrder="desc"
        label="Sort by"
      />
    </div>
  );

  // Initial loading state
  if (isLoading) {
    return (
      <>
        <SkipLink targetId={MAIN_CONTENT_ID} label="Skip to content" />
        <main
          id={MAIN_CONTENT_ID}
          tabIndex={-1}
          className="container mx-auto px-4 py-8"
        >
          <h1 className="text-3xl font-bold text-gray-900 mb-6">Channels</h1>
          {toolbar}
          {/* Disabled search field with "Loading channels..." placeholder (FR-024) */}
          <ChannelSearchInput
            value={channelSearch}
            onChange={setChannelSearch}
            onClear={() => setChannelSearch("")}
            disabled={true}
            inputRef={searchInputRef}
          />
          <ChannelLoadingState count={8} />
        </main>
      </>
    );
  }

  // Error state (only if no channels loaded)
  if (isError && channels.length === 0) {
    // Extract error message if it's an API error object
    const errorMessage = typeof error === 'object' && error !== null && 'message' in error
      ? (error as { message: string }).message
      : 'An error occurred while loading channels';

    return (
      <>
        <SkipLink targetId={MAIN_CONTENT_ID} label="Skip to content" />
        <main
          id={MAIN_CONTENT_ID}
          tabIndex={-1}
          className="container mx-auto px-4 py-8"
        >
          <h1 className="text-3xl font-bold text-gray-900 mb-6">Channels</h1>
          {toolbar}
          <ChannelSearchInput
            value={channelSearch}
            onChange={setChannelSearch}
            onClear={() => setChannelSearch("")}
            disabled={true}
            inputRef={searchInputRef}
          />
          <div
            className="bg-gradient-to-br from-red-50 to-amber-50 border border-red-200 rounded-xl shadow-lg p-8 text-center"
            role="alert"
            aria-live="polite"
          >
            {/* Error Icon */}
            <div className="mx-auto w-16 h-16 mb-5 text-red-500 bg-red-100 rounded-full p-3">
              <svg
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth={1.5}
                stroke="currentColor"
                aria-hidden="true"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z"
                />
              </svg>
            </div>

            {/* Error Title */}
            <p className="text-sm font-semibold text-red-800 uppercase tracking-wider mb-2">
              Could not load channels
            </p>

            {/* Error Message */}
            <p className="text-red-700 mb-8 max-w-md mx-auto">{errorMessage}</p>

            {/* Retry Button */}
            <button
              type="button"
              onClick={retry}
              className="inline-flex items-center px-6 py-3 bg-red-600 text-white font-semibold rounded-lg shadow-md hover:bg-red-700 hover:shadow-lg focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2 transition-all duration-200"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth={1.5}
                stroke="currentColor"
                className="w-5 h-5 mr-2"
                aria-hidden="true"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182m0-4.991v4.99"
                />
              </svg>
              Retry
            </button>
          </div>
        </main>
      </>
    );
  }

  // Empty state (no channels at all from server)
  if (channels.length === 0) {
    return (
      <>
        <SkipLink targetId={MAIN_CONTENT_ID} label="Skip to content" />
        <main
          id={MAIN_CONTENT_ID}
          tabIndex={-1}
          className="container mx-auto px-4 py-8"
        >
          <h1 className="text-3xl font-bold text-gray-900 mb-6">Channels</h1>
          {toolbar}
          <ChannelSearchInput
            value={channelSearch}
            onChange={setChannelSearch}
            onClear={() => setChannelSearch("")}
            disabled={false}
            inputRef={searchInputRef}
          />
          <ChannelEmptyState subscriptionFilter={subscriptionFilter} />
        </main>
      </>
    );
  }

  // Channels list with pagination
  return (
    <>
      <SkipLink targetId={MAIN_CONTENT_ID} label="Skip to content" />
      <main
        id={MAIN_CONTENT_ID}
        tabIndex={-1}
        className="container mx-auto px-4 py-8"
      >
        <div className="flex items-baseline justify-between mb-6">
          <h1 className="text-3xl font-bold text-gray-900">Channels</h1>
          {/* Dynamic channel count header (FR-030) - visible only */}
          {countText && (
            <span className="text-sm text-gray-500 ml-3" aria-hidden="true">
              {countText}
            </span>
          )}
        </div>

        {/* Toolbar: filter tabs + sort dropdown */}
        {toolbar}

        {/* Channel name search input (T030, T031, T032) */}
        <ChannelSearchInput
          value={channelSearch}
          onChange={setChannelSearch}
          onClear={() => setChannelSearch("")}
          disabled={false}
          inputRef={searchInputRef}
        />

        {/* ARIA live region announcing filtered count (FR-005) */}
        {total !== null && (
          <div role="status" aria-live="polite" className="sr-only">
            Showing {total} channel{total !== 1 ? "s" : ""}
          </div>
        )}

        {/* Search-filtered empty state (FR-018).
            Only shown once ALL pages have been fetched — prevents a false "no results"
            flash while background pages are still loading in during a fast search. */}
        {channelSearch.trim() && filteredChannels.length === 0 && !hasNextPage && !isFetchingNextPage ? (
          <ChannelSearchEmptyState searchQuery={channelSearch} />
        ) : (
          <div className="space-y-4">
            {/* While search is active and we're still fetching pages, show a brief
                banner so the user knows the result list will grow. This prevents the
                confusing experience of flickering results as pages arrive. */}
            {channelSearch.trim() && (hasNextPage || isFetchingNextPage) && (
              <p
                role="status"
                aria-live="polite"
                className="text-sm text-gray-500 text-center py-1"
              >
                Searching all channels&hellip;
              </p>
            )}

            {/* Pagination Status - Top (only show if more to load and search is inactive) */}
            {hasNextPage && !channelSearch.trim() && <PaginationStatus loadedCount={loadedCount} total={total} />}

            {/* Channel Cards Grid */}
            <div
              className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6"
              role="list"
              aria-label="Channel list"
            >
              {filteredChannels.map((channel) => (
                <div key={channel.channel_id} role="listitem">
                  <ChannelCard channel={channel} />
                </div>
              ))}
            </div>

            {/* Loading more indicator */}
            {isFetchingNextPage && (
              <div aria-live="polite">
                <p className="text-sm text-gray-500 text-center py-2">Loading more channels...</p>
                <ChannelLoadingState count={4} />
              </div>
            )}

            {/* Inline error when channels are loaded but next page fails */}
            {isError && channels.length > 0 && (
              <div
                className="bg-red-50 border border-red-200 rounded-lg p-4 text-center"
                role="alert"
              >
                <p className="text-red-800 font-medium mb-2">
                  {typeof error === 'object' && error !== null && 'message' in error
                    ? (error as { message: string }).message
                    : 'Failed to load more channels'}
                </p>
                <button
                  type="button"
                  onClick={retry}
                  className="inline-flex items-center px-4 py-2 bg-red-600 text-white font-medium rounded-md hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2 transition-colors"
                >
                  Retry
                </button>
              </div>
            )}

            {/* Intersection Observer Trigger Element */}
            {!isError && (
              <div
                ref={loadMoreRef}
                className="h-4"
                aria-hidden="true"
              />
            )}

            {/* All Loaded Message */}
            {!hasNextPage && !isError && total !== null && total > 0 && (
              <AllLoadedMessage total={total} />
            )}
          </div>
        )}
      </main>
    </>
  );
}
