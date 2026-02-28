/**
 * HomePage component - main landing page with video list.
 *
 * Feature 027: Added SortDropdown (upload_date/title) and FilterToggles
 * (liked_only, has_transcript) with ARIA live region for count announcements.
 */

import { useEffect } from "react";
import { useSearchParams } from "react-router-dom";

import { VideoList } from "../components/VideoList";
import { VideoFilters } from "../components/VideoFilters";
import { SortDropdown } from "../components/SortDropdown";
import { FilterToggle } from "../components/FilterToggle";
import { useVideos } from "../hooks/useVideos";
import type { VideoSortField, SortOrder, SortOption } from "../types/filters";

/**
 * Sort options for the Videos page.
 * Display label "Date Added" maps to upload_date per FR-017.
 */
const VIDEO_SORT_OPTIONS: SortOption<VideoSortField>[] = [
  { field: "upload_date", label: "Date Added", defaultOrder: "desc" },
  { field: "title", label: "Title", defaultOrder: "asc" },
];

/**
 * HomePage displays the main video list with filters.
 * This component is rendered within the AppShell layout which provides
 * the header, sidebar, and main content area.
 */
export function HomePage() {
  const [searchParams] = useSearchParams();

  // Read filter state from URL
  // Legacy raw tag params (backward compatibility with old bookmarks)
  const tags = searchParams.getAll("tag");
  // Canonical tag params (Feature 030 — normalized_form values)
  const canonicalTags = searchParams.getAll("canonical_tag");
  const category = searchParams.get("category");
  const topicIds = searchParams.getAll("topic_id");
  // T010: Read include_unavailable from URL (FR-027 - snake_case param)
  // Default: false (unchecked) - only "true" string enables unavailable content
  const includeUnavailable =
    searchParams.get("include_unavailable") === "true";

  // Feature 027: Read sort and boolean filter state from URL
  const sortBy = (searchParams.get("sort_by") as VideoSortField) || undefined;
  const sortOrder = (searchParams.get("sort_order") as SortOrder) || undefined;
  const likedOnly = searchParams.get("liked_only") === "true";
  const hasTranscript = searchParams.get("has_transcript") === "true";

  // Get total count for filters display (using the same hook with all filters)
  const { total } = useVideos({
    tags,
    canonicalTags,
    category,
    topicIds,
    includeUnavailable,
    sortBy,
    sortOrder,
    likedOnly,
  });

  // Set page title
  useEffect(() => {
    document.title = "Videos - ChronoVista";
    return () => {
      document.title = "ChronoVista";
    };
  }, []);

  // Scroll to top when filter or sort changes (FR-031)
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, [tags, canonicalTags, category, topicIds, includeUnavailable, sortBy, sortOrder, likedOnly, hasTranscript]);

  return (
    <div className="p-6 lg:p-8">
      {/* Page Header */}
      <div className="mb-8">
        <h2 className="text-2xl font-bold text-slate-900">Videos</h2>
        <p className="text-slate-600 mt-1">
          Your personal YouTube video library
        </p>
      </div>

      {/* Sort & Filter Controls Toolbar (Feature 027) */}
      <section aria-labelledby="controls-heading" className="mb-4">
        <h3 id="controls-heading" className="sr-only">
          Sort and filter controls
        </h3>
        <div className="flex flex-wrap items-center gap-4">
          {/* Sort Dropdown */}
          <SortDropdown<VideoSortField>
            options={VIDEO_SORT_OPTIONS}
            defaultField="upload_date"
            defaultOrder="desc"
            label="Sort videos by"
          />

          {/* Boolean Filter Toggles */}
          <FilterToggle paramKey="liked_only" label="Liked only" />
          <FilterToggle paramKey="has_transcript" label="Has transcripts" />
        </div>
      </section>

      {/* Video Classification Filters (tags, category, topic, include_unavailable) */}
      <section aria-labelledby="filters-heading" className="mb-6">
        <h3 id="filters-heading" className="sr-only">
          Video Filters
        </h3>
        <VideoFilters videoCount={total} />
      </section>

      {/* ARIA live region for count announcement (FR-005) */}
      <div role="status" aria-live="polite" className="sr-only">
        {total !== null && `Showing ${total} video${total !== 1 ? "s" : ""}`}
      </div>

      {/* Video List */}
      <section aria-labelledby="videos-heading">
        <h3 id="videos-heading" className="sr-only">
          Filtered Videos
        </h3>
        <VideoList
          tags={tags}
          canonicalTags={canonicalTags}
          category={category}
          topicIds={topicIds}
          includeUnavailable={includeUnavailable}
          sortBy={sortBy}
          sortOrder={sortOrder}
          likedOnly={likedOnly}
          hasTranscript={hasTranscript}
        />
      </section>
    </div>
  );
}
