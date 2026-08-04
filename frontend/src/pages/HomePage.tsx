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
import { SkipLink } from "../components/SkipLink";
import { useVideos } from "../hooks/useVideos";
import type { VideoSortField, SortOrder, SortOption } from "../types/filters";
import { FILTER_LIMITS } from "../types/filters";

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
  // Feature 061 (FR-018d): URL-backed, using the same name as the API query
  // parameter so the address and the request cannot drift. This is also what
  // makes the dashboard's pre-filtered deep link possible (FR-018, FR-025) —
  // component state would leave that link with nothing to target.
  const savedUnwatched = searchParams.get("saved_unwatched") === "true";

  // Entity intersection (Feature 062). Repeated keys, matching tag/topic.
  //
  // FR-002c: an address carrying more entities than the ceiling is trimmed to
  // the ceiling rather than silently truncated server-side or failing the whole
  // restoration. The client never issues an over-ceiling request; the API
  // rejects rather than clamps, because clamping would answer a different
  // question than the one asked.
  const rawEntityIds = searchParams.getAll("entity_id");
  const rawExcludedEntityIds = searchParams.getAll("exclude_entity_id");
  const entityIds = rawEntityIds.slice(0, FILTER_LIMITS.MAX_ENTITIES);
  const excludedEntityIds = rawExcludedEntityIds.slice(
    0,
    FILTER_LIMITS.MAX_ENTITIES
  );
  const droppedEntityCount =
    rawEntityIds.length -
    entityIds.length +
    (rawExcludedEntityIds.length - excludedEntityIds.length);
  const minEvidence =
    searchParams.get("min_evidence") === "transcript" ? "transcript" : undefined;

  // Get total count for filters display (using the same hook with all filters)
  // Same filter set as the list below — this call drives the panel's count,
  // and a count computed under different filters than the rows it describes is
  // the exact internal inconsistency FR-007 forbids.
  const { total } = useVideos({
    tags,
    canonicalTags,
    category,
    topicIds,
    includeUnavailable,
    sortBy,
    sortOrder,
    likedOnly,
    hasTranscript,
    savedUnwatched,
    entityIds,
    excludedEntityIds,
    ...(minEvidence !== undefined && { minEvidence }),
  });

  // Set page title
  useEffect(() => {
    document.title = "Videos - ChronoVista";
    return () => {
      document.title = "ChronoVista";
    };
  }, []);

  // Scroll to top when filter or sort changes (FR-031)
  //
  // These must be JOINED, not listed as arrays. `searchParams.getAll()` returns
  // a fresh array on every render, and React compares deps by identity — so
  // depending on the arrays directly made this effect run on EVERY render, not
  // only when a filter changed. The re-render that an infinite-scroll page
  // triggers was enough to fire it, yanking the reader from wherever they had
  // scrolled back up to the top. NUL is the separator because it cannot occur
  // in a tag or an id, so ["a,b"] and ["a","b"] stay distinguishable.
  const tagKey = tags.join("\0");
  const canonicalTagKey = canonicalTags.join("\0");
  const topicIdKey = topicIds.join("\0");
  const entityKey = entityIds.join("\0");
  const excludedEntityKey = excludedEntityIds.join("\0");

  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, [tagKey, canonicalTagKey, category, topicIdKey, includeUnavailable, sortBy, sortOrder, likedOnly, hasTranscript, savedUnwatched, entityKey, excludedEntityKey, minEvidence]);

  return (
    <div className="p-6 lg:p-8">
      {/* NFR-006: Skip link targeting the main content area */}
      <SkipLink targetId="main-content" label="Skip to content" />

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
          <FilterToggle
            paramKey="saved_unwatched"
            label="Saved but never watched"
          />
        </div>
      </section>

      {/* Video Classification Filters (tags, category, topic, include_unavailable) */}
      <section aria-labelledby="filters-heading" className="mb-6">
        <h3 id="filters-heading" className="sr-only">
          Video Filters
        </h3>
        <VideoFilters videoCount={total} />
      </section>

      {/*
        FR-002c: a restored address over the ceiling is trimmed rather than
        silently truncated. Reporting what was dropped is the difference
        between a filter the user can reason about and one that quietly
        answers a different question.
      */}
      {droppedEntityCount > 0 && (
        <div
          role="status"
          className="mb-4 rounded border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800"
        >
          {`Showing the first ${FILTER_LIMITS.MAX_ENTITIES} entities per set — `}
          {`${droppedEntityCount} more from the link ${
            droppedEntityCount === 1 ? "was" : "were"
          } not applied.`}
        </div>
      )}

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
          savedUnwatched={savedUnwatched}
          entityIds={entityIds}
          excludedEntityIds={excludedEntityIds}
          {...(minEvidence !== undefined && { minEvidence })}
        />
      </section>
    </div>
  );
}
