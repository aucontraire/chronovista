/**
 * SearchPage Component
 *
 * Main container for transcript search functionality with WCAG 2.1 AA compliance.
 *
 * Accessibility features:
 * - ARIA live region for search status announcements (T049, FR-026)
 * - aria-busy for loading states (T050, FR-027)
 * - Keyboard navigation support (T051, FR-029)
 * - Semantic landmark structure (T052, FR-030)
 * - Skip link to main content (T053, FR-029)
 * - Focus management (T054, FR-031)
 */

import { useState, useMemo, useRef, useEffect } from "react";
import { useSearchParams } from "react-router-dom";

import { useSearchSegments } from "../hooks/useSearchSegments";
import { SearchInput } from "../components/SearchInput";
import { SearchResultList } from "../components/SearchResultList";
import { SearchEmptyState } from "../components/SearchEmptyState";
import { SearchErrorState } from "../components/SearchErrorState";
import { SearchResultSkeleton } from "../components/SearchResultSkeleton";
import { SearchFilters } from "../components/SearchFilters";

export function SearchPage() {
  const [searchParams, setSearchParams] = useSearchParams();

  // Initialize state from URL params (FR-012: URL state restoration)
  const initialQuery = searchParams.get("q") || "";
  const initialLanguage = searchParams.get("language") || "";

  const [query, setQuery] = useState(initialQuery);
  const [debouncedQuery, setDebouncedQuery] = useState(initialQuery);
  const [selectedLanguage, setSelectedLanguage] = useState(initialLanguage);
  const mainContentRef = useRef<HTMLElement>(null);

  // Set page title
  useEffect(() => {
    document.title = "Search - ChronoVista";
    return () => {
      document.title = "ChronoVista";
    };
  }, []);

  const {
    segments,
    total,
    availableLanguages,
    isLoading,
    isError,
    error,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useSearchSegments({
    query: debouncedQuery,
    language: selectedLanguage || null,
  });

  const queryTerms = debouncedQuery.trim().split(/\s+/).filter(Boolean);

  // FR-011: Sync search state to URL parameters
  useEffect(() => {
    const params = new URLSearchParams();

    if (debouncedQuery) {
      params.set("q", debouncedQuery);
    }

    if (selectedLanguage) {
      params.set("language", selectedLanguage);
    }

    // Only update URL if params changed (replace: true prevents history entries)
    const newSearch = params.toString();
    const currentSearch = searchParams.toString();

    if (newSearch !== currentSearch) {
      setSearchParams(params, { replace: true });
    }
  }, [debouncedQuery, selectedLanguage, searchParams, setSearchParams]);

  // T049: ARIA live region announcements (FR-026)
  const announceText = useMemo(() => {
    if (!debouncedQuery) {
      return "";
    }

    if (isLoading && !isFetchingNextPage) {
      return "Searching...";
    }

    if (isError) {
      return "Search failed. Please try again.";
    }

    if (segments.length === 0 && !isLoading) {
      return `No results found for '${debouncedQuery}'`;
    }

    if (segments.length > 0 && !isLoading) {
      return `Found ${total ?? segments.length} results for '${debouncedQuery}'`;
    }

    return "";
  }, [debouncedQuery, isLoading, isError, segments.length, total, isFetchingNextPage]);

  const renderContent = () => {
    if (!debouncedQuery) {
      return (
        <SearchEmptyState
          mode="initial"
          onExampleClick={(example) => {
            setQuery(example);
            setDebouncedQuery(example);
          }}
        />
      );
    }

    if (isLoading) {
      return <SearchResultSkeleton />;
    }

    if (isError) {
      // T056: Extract status from ApiError for authentication detection (EC-011-EC-016)
      const apiError = error as { status?: number } | undefined;
      const errorStatus = apiError?.status;
      const errorProps = {
        message: error instanceof Error
          ? error.message
          : "Something went wrong. Please try again.",
        onRetry: () => fetchNextPage(),
        error,
        // Only include status if it's defined (exactOptionalPropertyTypes compliance)
        ...(errorStatus !== undefined && { status: errorStatus }),
      };
      return <SearchErrorState {...errorProps} />;
    }

    if (segments.length === 0) {
      // CRITICAL FIX: Show filter panel even when no results, so users can change/clear filters
      return (
        <div className="space-y-6">
          {/* Desktop: Show filters in sidebar layout */}
          <div className="lg:grid lg:grid-cols-[280px_1fr] lg:gap-6">
            {/* Filter Panel - Desktop (permanent sidebar) - T052: complementary landmark */}
            <div className="hidden lg:block lg:sticky lg:top-4 lg:self-start">
              <SearchFilters
                availableLanguages={availableLanguages}
                selectedLanguage={selectedLanguage}
                onLanguageChange={setSelectedLanguage}
                totalResults={total ?? 0}
              />
            </div>

            {/* Empty State */}
            <div>
              <SearchEmptyState mode="no-results" query={debouncedQuery} />
            </div>
          </div>

          {/* TODO: Mobile/Tablet filter trigger button will be added in future iteration */}
          {/* For now, filters are only available on desktop (lg:) breakpoint */}
        </div>
      );
    }

    return (
      <div className="space-y-6">
        {/* Desktop: Show filters in sidebar layout */}
        <div className="lg:grid lg:grid-cols-[280px_1fr] lg:gap-6">
          {/* Filter Panel - Desktop (permanent sidebar) - T052: complementary landmark */}
          <div className="hidden lg:block lg:sticky lg:top-4 lg:self-start">
            <SearchFilters
              availableLanguages={availableLanguages}
              selectedLanguage={selectedLanguage}
              onLanguageChange={setSelectedLanguage}
              totalResults={total ?? 0}
            />
          </div>

          {/* Search Results */}
          <div>
            <SearchResultList
              results={segments}
              queryTerms={queryTerms}
              isLoading={isLoading}
              isFetchingNextPage={isFetchingNextPage}
              hasNextPage={hasNextPage}
              fetchNextPage={fetchNextPage}
            />
          </div>
        </div>

        {/* TODO: Mobile/Tablet filter trigger button will be added in future iteration */}
        {/* For now, filters are only available on desktop (lg:) breakpoint */}
      </div>
    );
  };

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      {/* T053: Skip link (FR-029) - WCAG 2.4.1 Bypass Blocks */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:top-4 focus:left-4 focus:z-50 focus:bg-white dark:focus:bg-gray-800 focus:text-gray-900 dark:focus:text-gray-100 focus:px-4 focus:py-2 focus:rounded-lg focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
      >
        Skip to search results
      </a>

      <div className="max-w-4xl mx-auto px-4 py-8">
        {/* T052: Header landmark with search form (FR-030) - WCAG 1.3.1 */}
        <header role="banner" className="mb-8">
          <SearchInput
            value={query}
            onChange={setQuery}
            onDebouncedChange={setDebouncedQuery}
            autoFocus
          />
        </header>

        {/* T049: ARIA live region for announcements (FR-026) - WCAG 4.1.3 Status Messages */}
        <div
          aria-live="polite"
          aria-atomic="true"
          className="sr-only"
        >
          {announceText}
        </div>

        {/* T052: Main landmark (FR-030) - WCAG 1.3.1 */}
        <main
          role="main"
          id="main-content"
          ref={mainContentRef}
          tabIndex={-1}
          className="outline-none"
        >
          {/* Search results region - always present for accessibility */}
          <div
            id="search-results"
            role="region"
            aria-label="Search results"
            aria-busy={isLoading && !isFetchingNextPage}
          >
            {renderContent()}
          </div>
        </main>
      </div>
    </div>
  );
}
