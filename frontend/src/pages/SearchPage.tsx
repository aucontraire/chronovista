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
import { useSearchTitles } from "../hooks/useSearchTitles";
import { useSearchDescriptions } from "../hooks/useSearchDescriptions";
import { SearchInput } from "../components/SearchInput";
import { SearchResultList } from "../components/SearchResultList";
import { SearchEmptyState } from "../components/SearchEmptyState";
import { SearchFilters } from "../components/SearchFilters";
import { SearchSection } from "../components/SearchSection";
import { VideoSearchResult } from "../components/VideoSearchResult";
import type { EnabledSearchTypes } from "../types/search";

/**
 * Parse enabled types from URL parameter.
 * Format: types=titles,descriptions,transcripts (comma-separated)
 * If not present, default to all three enabled.
 */
function parseEnabledTypes(typesParam: string | null): EnabledSearchTypes {
  if (!typesParam) {
    return { titles: true, descriptions: true, transcripts: true };
  }
  const parts = typesParam.split(',');
  return {
    titles: parts.includes('titles'),
    descriptions: parts.includes('descriptions'),
    transcripts: parts.includes('transcripts'),
  };
}

export function SearchPage() {
  const [searchParams, setSearchParams] = useSearchParams();

  // Initialize state from URL params (FR-012: URL state restoration)
  const initialQuery = searchParams.get("q") || "";
  const initialLanguage = searchParams.get("language") || "";
  const initialTypes = parseEnabledTypes(searchParams.get("types"));
  // T031: Read include_unavailable from URL (FR-021)
  const initialIncludeUnavailable = searchParams.get("include_unavailable") === "true";

  const [query, setQuery] = useState(initialQuery);
  const [debouncedQuery, setDebouncedQuery] = useState(initialQuery);
  const [selectedLanguage, setSelectedLanguage] = useState(initialLanguage);
  const [enabledTypes, setEnabledTypes] = useState<EnabledSearchTypes>(initialTypes);
  const [includeUnavailable, setIncludeUnavailable] = useState(initialIncludeUnavailable);
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
    includeUnavailable,
  });

  const {
    data: titleResults,
    totalCount: titleTotalCount,
    isLoading: isTitleLoading,
    isError: isTitleError,
    error: titleError,
    refetch: refetchTitles,
  } = useSearchTitles({
    query: debouncedQuery,
    enabled: enabledTypes.titles,
    includeUnavailable,
  });

  const {
    data: descriptionResults,
    totalCount: descriptionTotalCount,
    isLoading: isDescriptionLoading,
    isError: isDescriptionError,
    error: descriptionError,
    refetch: refetchDescriptions,
  } = useSearchDescriptions({
    query: debouncedQuery,
    enabled: enabledTypes.descriptions,
    includeUnavailable,
  });

  const queryTerms = debouncedQuery.trim().split(/\s+/).filter(Boolean);

  // Toggle handler with at-least-one enforcement
  const handleToggleType = (type: keyof EnabledSearchTypes) => {
    setEnabledTypes(prev => {
      const next = { ...prev, [type]: !prev[type] };
      // Enforce at-least-one: if all would be false, don't change
      if (!next.titles && !next.descriptions && !next.transcripts) {
        return prev;
      }
      return next;
    });
  };

  // FR-011: Sync search state to URL parameters
  useEffect(() => {
    const params = new URLSearchParams();

    if (debouncedQuery) {
      params.set("q", debouncedQuery);
    }

    if (selectedLanguage) {
      params.set("language", selectedLanguage);
    }

    // Add types param only if not all enabled (default state)
    const allEnabled = enabledTypes.titles && enabledTypes.descriptions && enabledTypes.transcripts;
    if (!allEnabled) {
      const types = [];
      if (enabledTypes.titles) types.push('titles');
      if (enabledTypes.descriptions) types.push('descriptions');
      if (enabledTypes.transcripts) types.push('transcripts');
      params.set("types", types.join(','));
    }

    // T031: Add include_unavailable param (FR-021)
    if (includeUnavailable) {
      params.set("include_unavailable", "true");
    }

    // Only update URL if params changed (replace: true prevents history entries)
    const newSearch = params.toString();
    const currentSearch = searchParams.toString();

    if (newSearch !== currentSearch) {
      setSearchParams(params, { replace: true });
    }
  }, [debouncedQuery, selectedLanguage, enabledTypes, includeUnavailable, searchParams, setSearchParams]);

  // T049: ARIA live region announcements (FR-026) - Only count enabled types
  const announceText = useMemo(() => {
    if (!debouncedQuery) {
      return "";
    }

    const anyLoading =
      (enabledTypes.transcripts && isLoading && !isFetchingNextPage) ||
      (enabledTypes.titles && isTitleLoading) ||
      (enabledTypes.descriptions && isDescriptionLoading);

    if (anyLoading) {
      return "Searching...";
    }

    const allEnabledErrored =
      (enabledTypes.transcripts ? isError : true) &&
      (enabledTypes.titles ? isTitleError : true) &&
      (enabledTypes.descriptions ? isDescriptionError : true);

    if (allEnabledErrored) {
      return "Search failed. Please try again.";
    }

    const transcriptEmpty = !enabledTypes.transcripts || segments.length === 0;
    const titleEmpty = !enabledTypes.titles || titleTotalCount === 0;
    const descriptionEmpty = !enabledTypes.descriptions || descriptionTotalCount === 0;

    if (transcriptEmpty && titleEmpty && descriptionEmpty && !anyLoading) {
      return `No results found for '${debouncedQuery}'`;
    }

    if (!anyLoading && (segments.length > 0 || titleTotalCount > 0 || descriptionTotalCount > 0)) {
      const transcriptCount = enabledTypes.transcripts ? (total ?? segments.length) : 0;
      const titleCount = enabledTypes.titles ? titleTotalCount : 0;
      const descriptionCount = enabledTypes.descriptions ? descriptionTotalCount : 0;

      // FR-018: Combined per-type announcement
      const parts: string[] = [];
      if (enabledTypes.titles && titleCount > 0) parts.push(`${titleCount} title`);
      if (enabledTypes.descriptions && descriptionCount > 0) parts.push(`${descriptionCount} description`);
      if (enabledTypes.transcripts && transcriptCount > 0) parts.push(`${transcriptCount} transcript`);

      if (parts.length === 0) {
        return `No results found for '${debouncedQuery}'`;
      }

      const matchText = parts.length === 1
        ? parts[0]
        : parts.length === 2
          ? `${parts[0]} and ${parts[1]}`
          : `${parts.slice(0, -1).join(', ')}, and ${parts[parts.length - 1]}`;

      return `Found ${matchText} matches for '${debouncedQuery}'`;
    }

    return "";
  }, [debouncedQuery, isLoading, isError, segments.length, total, isFetchingNextPage, isTitleLoading, titleTotalCount, isTitleError, isDescriptionLoading, descriptionTotalCount, isDescriptionError, enabledTypes]);

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

    // Check if ALL enabled sections are done and ALL returned zero results
    const titleEmpty = !enabledTypes.titles || (!isTitleLoading && !isTitleError && titleTotalCount === 0);
    const descEmpty = !enabledTypes.descriptions || (!isDescriptionLoading && !isDescriptionError && descriptionTotalCount === 0);
    const transcriptEmpty = !enabledTypes.transcripts || (!isLoading && !isError && segments.length === 0);
    const anyStillLoading =
      (enabledTypes.titles && isTitleLoading) ||
      (enabledTypes.descriptions && isDescriptionLoading) ||
      (enabledTypes.transcripts && isLoading && !isFetchingNextPage);
    const allSectionsEmpty = titleEmpty && descEmpty && transcriptEmpty && !anyStillLoading;

    if (allSectionsEmpty) {
      // Show no-results with filter panel (same as existing no-results state)
      return (
        <div className="space-y-6">
          <div className="lg:grid lg:grid-cols-[280px_1fr] lg:gap-6">
            <div className="hidden lg:block lg:sticky lg:top-4 lg:self-start">
              <SearchFilters
                availableLanguages={availableLanguages}
                selectedLanguage={selectedLanguage}
                onLanguageChange={setSelectedLanguage}
                totalResults={0}
                titleCount={0}
                descriptionCount={0}
                enabledTypes={enabledTypes}
                onToggleType={handleToggleType}
                includeUnavailable={includeUnavailable}
                onToggleIncludeUnavailable={() => setIncludeUnavailable(!includeUnavailable)}
              />
            </div>
            <div>
              <SearchEmptyState mode="no-results" query={debouncedQuery} />
            </div>
          </div>
        </div>
      );
    }

    // Render stacked sections layout
    return (
      <div className="space-y-6">
        <div className="lg:grid lg:grid-cols-[280px_1fr] lg:gap-6">
          {/* Filter Panel - Desktop sidebar */}
          <div className="hidden lg:block lg:sticky lg:top-4 lg:self-start">
            <SearchFilters
              availableLanguages={availableLanguages}
              selectedLanguage={selectedLanguage}
              onLanguageChange={setSelectedLanguage}
              totalResults={total ?? 0}
              titleCount={titleTotalCount}
              descriptionCount={descriptionTotalCount}
              enabledTypes={enabledTypes}
              onToggleType={handleToggleType}
            />
          </div>

          {/* Stacked search sections - only render enabled types */}
          <div className="space-y-6">
            {/* Video Titles section (top) */}
            {enabledTypes.titles && (
              <SearchSection
                title="Video Titles"
                totalCount={titleTotalCount}
                displayedCount={titleResults.length}
                isLoading={isTitleLoading}
                error={isTitleError ? titleError : null}
                onRetry={refetchTitles}
                loadingText="Searching titles..."
              >
                <div className="space-y-3">
                  {titleResults.map((result) => (
                    <VideoSearchResult
                      key={result.video_id}
                      result={result}
                      queryTerms={queryTerms}
                    />
                  ))}
                </div>
              </SearchSection>
            )}

            {/* Descriptions section (middle) */}
            {enabledTypes.descriptions && (
              <SearchSection
                title="Descriptions"
                totalCount={descriptionTotalCount}
                displayedCount={descriptionResults.length}
                isLoading={isDescriptionLoading}
                error={isDescriptionError ? descriptionError : null}
                onRetry={refetchDescriptions}
                loadingText="Searching descriptions..."
              >
                <div className="space-y-3">
                  {descriptionResults.map((result) => (
                    <VideoSearchResult
                      key={result.video_id}
                      result={result}
                      queryTerms={queryTerms}
                    />
                  ))}
                </div>
              </SearchSection>
            )}

            {/* Transcripts section (bottom) - uses existing SearchResultList */}
            {enabledTypes.transcripts && (
              <SearchSection
                title="Transcripts"
                totalCount={total ?? 0}
                displayedCount={segments.length}
                isLoading={isLoading && !isFetchingNextPage}
                error={isError ? error : null}
                onRetry={() => fetchNextPage()}
                loadingText="Searching transcripts..."
              >
                <SearchResultList
                  results={segments}
                  queryTerms={queryTerms}
                  isLoading={isLoading}
                  isFetchingNextPage={isFetchingNextPage}
                  hasNextPage={hasNextPage}
                  fetchNextPage={fetchNextPage}
                />
              </SearchSection>
            )}
          </div>
        </div>
      </div>
    );
  };

  return (
    <div>
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
