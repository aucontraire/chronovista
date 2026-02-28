/**
 * ClassificationSection component displays video classification metadata.
 *
 * Features:
 * - T038: Organized subsections for tags, category, and topics
 * - T039: Clickable tag links that navigate to filtered video lists
 * - T040: URL encoding for special characters in tags (C++, music & arts, etc.)
 * - T041: Hover styling to indicate tags are clickable
 * - T042: Browser back button returns to video detail after tag navigation
 * - T064: Clickable topic links to navigate to filtered video lists
 * - T065: Multiple topics as individually clickable elements
 * - T066: Topic display with parent path context ("Arts > Music > Pop Music")
 * - T067: "Classification & Context" section header
 * - T068: Playlists subsection with clickable playlist links
 * - T069: Graceful empty state for all subsections (FR-006, FR-032)
 * - T070: Labeled subsections for Tags, Categories, Topics, Playlists
 * - T021: Tags grouped by canonical form (US-4)
 * - T022: Tag resolution logic via useQueries batching (US-4)
 * - T023: Canonical tag group rendering with alias display (FR-012, R7)
 * - T024: Unresolved Tags subsection for orphaned tags (FR-013)
 * - T025: Zero-tag and skeleton loading states (AS-6)
 * - FR-ACC-003: WCAG AA compliant color contrast (7.0:1+ ratio)
 *
 * Accessibility:
 * - Semantic HTML with proper heading hierarchy
 * - Labeled subsections with descriptive headings
 * - Link elements for keyboard navigation
 * - Visible focus indicators
 * - Empty state messaging
 */

import React, { useMemo } from "react";
import { Link } from "react-router-dom";
import { useQueries } from "@tanstack/react-query";
import { filterColors } from "../styles/tokens";
import { useCanonicalTagDetail } from "../hooks/useCanonicalTagDetail";
import type { TopicSummary } from "../types/video";
import type { VideoPlaylistMembership } from "../types/playlist";
import type { CanonicalTagListItem, CanonicalTagDetailResponse } from "../types/canonical-tags";
import { API_BASE_URL } from "../api/config";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/**
 * Props for ClassificationSection component.
 */
export interface ClassificationSectionProps {
  /** Array of tag strings */
  tags: string[];
  /** YouTube category ID (may be null) */
  categoryId: string | null;
  /** Human-readable category name (may be null) */
  categoryName: string | null;
  /** Array of topic summaries with hierarchy */
  topics: TopicSummary[];
  /** Array of playlists containing this video (T068) */
  playlists?: VideoPlaylistMembership[];
}

/**
 * Resolved tag entry: maps a raw tag to its canonical resolution.
 */
interface ResolvedTagEntry {
  rawTag: string;
  canonical: CanonicalTagListItem | null;
  isLoading: boolean;
}

/**
 * A group of raw tags sharing the same canonical form.
 */
interface CanonicalGroup {
  normalizedForm: string;
  canonicalForm: string;
  aliasCount: number;
  videoCount: number;
  rawTags: string[];
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/**
 * Renders a subsection with a label and content.
 */
function Subsection({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <h4 className="text-sm font-medium text-gray-700 mb-2">{label}</h4>
      {children}
    </div>
  );
}

/**
 * Renders a single canonical tag badge with an inline "+N" count badge and
 * a hover/focus tooltip listing the aliases.
 *
 * Approach 1 (count badge + tooltip):
 * - The pill gets a "+N" span appended when filteredAliases.length > 0
 * - A tooltip positioned absolutely below the pill reveals the full alias list
 *   on hover (group hover) and on focus-within (keyboard / tap users)
 * - The old "Also:" <p> line is removed; layout no longer stretches pill width
 * - For tags with 0 or 1 alias after filtering (showAliases=false), the pill
 *   looks identical to Category / Topics pills — no badge, no tooltip
 *
 * Hides alias UI per R7 (excludes canonical_form) and FR-012 (alias_count=1).
 */
function CanonicalTagBadge({ group }: { group: CanonicalGroup }) {
  const { data: detail } = useCanonicalTagDetail(group.normalizedForm);

  // Stable tooltip id for aria-describedby association
  const tooltipId = `tooltip-${group.normalizedForm}`;

  // Filter aliases: exclude the canonical_form itself (R7)
  const filteredAliases = useMemo(() => {
    if (!detail?.top_aliases) return [];
    return detail.top_aliases
      .map((a) => a.raw_form)
      .filter((raw) => raw !== group.canonicalForm);
  }, [detail?.top_aliases, group.canonicalForm]);

  // Hide badge + tooltip when alias_count=1 (only one variation = canonical itself)
  // or when no aliases remain after filtering (R7)
  const showAliases = group.aliasCount > 1 && filteredAliases.length > 0;

  // FR-024 aria-label: variations clause only when alias_count > 1
  const variationCount = group.aliasCount - 1;
  const ariaLabel = [
    `Filter videos by canonical tag: ${group.canonicalForm}.`,
    `${group.videoCount} videos${variationCount > 0 ? `, ${variationCount} variation${variationCount === 1 ? "" : "s"}` : ""}.`,
  ].join(" ");

  return (
    // relative + group/pill enables the CSS group-hover and group-focus-within
    // selectors on the tooltip below. No flex-col wrapper — avoids width stretch.
    <div className="relative group/pill">
      {/* Canonical badge pill */}
      <Link
        to={`/videos?canonical_tag=${encodeURIComponent(group.normalizedForm)}`}
        className="inline-flex items-center self-start px-3 py-1 text-sm font-medium rounded-full transition-all duration-200 hover:underline hover:brightness-95 focus:outline-none focus:ring-2 focus:ring-offset-2 min-h-[44px]"
        style={{
          backgroundColor: filterColors.canonical_tag.background,
          color: filterColors.canonical_tag.text,
          borderWidth: "1px",
          borderStyle: "solid",
          borderColor: filterColors.canonical_tag.border,
        }}
        aria-label={ariaLabel}
        aria-describedby={showAliases ? tooltipId : undefined}
      >
        {group.canonicalForm}

        {/* +N count badge — uses true alias count (minus canonical form itself) */}
        {showAliases && (
          <span
            className="ml-1.5 text-xs font-normal opacity-60"
            aria-label={`${variationCount} aliases`}
          >
            +{variationCount}
          </span>
        )}
      </Link>

      {/* Tooltip — shown on hover or focus-within of the wrapper div */}
      {showAliases && (
        <div
          id={tooltipId}
          role="tooltip"
          className="absolute left-0 top-full mt-1 z-10 w-max max-w-[220px] bg-white border border-gray-200 rounded-md shadow-md p-2 text-xs opacity-0 pointer-events-none group-hover/pill:opacity-100 group-hover/pill:pointer-events-auto group-focus-within/pill:opacity-100 group-focus-within/pill:pointer-events-auto transition-opacity duration-150"
        >
          <p className="font-medium text-gray-700 mb-1">Also known as:</p>
          <ul className="space-y-0.5">
            {filteredAliases.map((alias) => (
              <li key={alias} className="text-gray-600 truncate">
                {alias}
              </li>
            ))}
          </ul>
          {variationCount > filteredAliases.length && (
            <p className="text-gray-400 mt-1">
              and {variationCount - filteredAliases.length} more
            </p>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * Skeleton placeholder for a loading tag badge.
 */
function TagSkeleton() {
  return (
    <div
      data-testid="tag-skeleton"
      className="h-[44px] w-24 rounded-full bg-gray-200 animate-pulse"
      aria-hidden="true"
    />
  );
}

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

/**
 * ClassificationSection component.
 *
 * Displays tags (with canonical grouping), category, topics, and playlists
 * in organized subsections. All elements are clickable and navigate to
 * filtered video lists or playlist details.
 *
 * @param props - Component props
 * @returns Classification section UI
 */
export function ClassificationSection({
  tags,
  categoryId,
  categoryName,
  topics,
  playlists = [],
}: ClassificationSectionProps) {
  // ---------------------------------------------------------------------------
  // T022: Batch-resolve all raw tags using useQueries (avoids hooks-in-loops)
  // ---------------------------------------------------------------------------
  const resolveQueries = useQueries({
    queries: tags.map((rawTag) => ({
      queryKey: ["canonical-tag-resolve", rawTag],
      queryFn: async ({
        signal,
      }: {
        signal: AbortSignal;
      }): Promise<CanonicalTagListItem | null> => {
        const url = `${API_BASE_URL}/canonical-tags/resolve?raw_form=${encodeURIComponent(rawTag)}`;
        const response = await fetch(url, {
          signal,
          headers: { "Content-Type": "application/json" },
        });
        if (response.status === 404) {
          return null; // No canonical tag for this raw tag — will become orphan
        }
        if (!response.ok) {
          throw new Error(
            `Failed to resolve raw tag: ${response.status} ${response.statusText}`
          );
        }
        const json = (await response.json()) as CanonicalTagDetailResponse;
        return {
          canonical_form: json.data.canonical_form,
          normalized_form: json.data.normalized_form,
          alias_count: json.data.alias_count,
          video_count: json.data.video_count,
        };
      },
      enabled: rawTag.length > 0,
      staleTime: 5 * 60 * 1000,
      gcTime: 10 * 60 * 1000,
    })),
  });

  // Build resolved entries per raw tag
  const resolvedEntries: ResolvedTagEntry[] = useMemo(() => {
    return tags.map((rawTag, idx) => {
      const q = resolveQueries[idx];
      return {
        rawTag,
        canonical: (q?.data as CanonicalTagListItem | null | undefined) ?? null,
        isLoading: q?.isLoading ?? false,
      };
    });
  }, [tags, resolveQueries]);

  // Is any tag still loading?
  const anyLoading = resolvedEntries.some((e) => e.isLoading);

  // T022: Group resolved tags by normalized_form
  const { canonicalGroups, orphanedTags } = useMemo(() => {
    const groupMap = new Map<string, CanonicalGroup>();
    const orphans: string[] = [];

    for (const entry of resolvedEntries) {
      if (entry.isLoading) continue; // skip while loading

      if (entry.canonical) {
        const key = entry.canonical.normalized_form;
        const existing = groupMap.get(key);
        if (existing) {
          existing.rawTags.push(entry.rawTag);
        } else {
          groupMap.set(key, {
            normalizedForm: entry.canonical.normalized_form,
            canonicalForm: entry.canonical.canonical_form,
            aliasCount: entry.canonical.alias_count,
            videoCount: entry.canonical.video_count,
            rawTags: [entry.rawTag],
          });
        }
      } else {
        orphans.push(entry.rawTag);
      }
    }

    return {
      canonicalGroups: Array.from(groupMap.values()),
      orphanedTags: orphans,
    };
  }, [resolvedEntries]);

  // Number of skeleton placeholders (one per tag, max 10) — shown while loading
  const skeletonCount = Math.min(tags.length, 10);

  // Unresolved Tags description id
  const unresolvedDescId = "unresolved-tags-desc";

  return (
    <section
      aria-labelledby="classification-heading"
      className="bg-white rounded-xl shadow-md border border-gray-100 p-6 lg:p-8 space-y-6"
    >
      {/* T067: Section Header */}
      <h3
        id="classification-heading"
        className="text-lg font-semibold text-gray-900"
      >
        Classification & Context
      </h3>

      {/* T070: Tags Subsection — canonical groups + unresolved */}
      <Subsection label="Tags">
        {/* T025: Zero-tag state */}
        {tags.length === 0 ? (
          <span className="text-gray-400 text-sm">None</span>
        ) : anyLoading ? (
          /* T025: Skeleton loading state (AS-6) */
          <div className="flex flex-wrap gap-2">
            {Array.from({ length: skeletonCount }).map((_, i) => (
              <TagSkeleton key={i} />
            ))}
          </div>
        ) : (
          <>
            {/* T023: Canonical tag groups */}
            {canonicalGroups.length > 0 && (
              <div className="flex flex-wrap gap-2 min-h-[44px] mb-3">
                {canonicalGroups.map((group) => (
                  <CanonicalTagBadge key={group.normalizedForm} group={group} />
                ))}
              </div>
            )}

            {/* T024: Unresolved Tags subsection */}
            {orphanedTags.length > 0 && (
              <div>
                <h4
                  className="text-sm font-medium text-gray-700 mb-2"
                  aria-describedby={unresolvedDescId}
                >
                  Unresolved Tags
                </h4>
                {/* Hidden screen-reader description (FR-013) */}
                <span id={unresolvedDescId} className="sr-only">
                  These tags have not yet been mapped to a canonical group and
                  may return fewer results.
                </span>
                <div className="flex flex-wrap gap-2">
                  {orphanedTags.map((rawTag) => (
                    <Link
                      key={rawTag}
                      to={`/videos?tag=${encodeURIComponent(rawTag)}`}
                      className="inline-flex items-center px-3 py-1 text-sm font-medium rounded-full italic transition-all duration-200 hover:underline hover:brightness-95 focus:outline-none focus:ring-2 focus:ring-offset-2"
                      style={{
                        backgroundColor: filterColors.boolean.background,
                        color: filterColors.boolean.text,
                        borderWidth: "1px",
                        borderStyle: "solid",
                        borderColor: filterColors.boolean.border,
                      }}
                      aria-label={`Filter videos by tag: ${rawTag} (unresolved)`}
                    >
                      {rawTag}
                    </Link>
                  ))}
                </div>
              </div>
            )}

            {/* Fallback if all tags resolved but empty groups (edge case) */}
            {canonicalGroups.length === 0 && orphanedTags.length === 0 && (
              <span className="text-gray-400 text-sm">None</span>
            )}
          </>
        )}
      </Subsection>

      {/* T070: Category Subsection - T038 */}
      <Subsection label="Category">
        {categoryName && categoryId ? (
          <Link
            to={`/videos?category=${encodeURIComponent(categoryId)}`}
            className="inline-flex px-3 py-1 text-sm font-medium rounded-full transition-all duration-200 hover:underline hover:brightness-95 focus:outline-none focus:ring-2 focus:ring-offset-2"
            style={{
              backgroundColor: filterColors.category.background,
              color: filterColors.category.text,
              borderWidth: "1px",
              borderStyle: "solid",
              borderColor: filterColors.category.border,
            }}
            aria-label={`Filter videos by category: ${categoryName}`}
          >
            {categoryName}
          </Link>
        ) : (
          <span className="text-gray-400 text-sm">None</span>
        )}
      </Subsection>

      {/* T070: Topics Subsection - T038, T064, T065, T066 */}
      <Subsection label="Topics">
        {topics.length > 0 ? (
          <div className="flex flex-wrap gap-2">
            {topics.map((topic) => (
              <Link
                key={topic.topic_id}
                to={`/videos?topic_id=${encodeURIComponent(topic.topic_id)}`}
                className="px-3 py-1 text-sm font-medium rounded-full transition-all duration-200 hover:underline hover:brightness-95 focus:outline-none focus:ring-2 focus:ring-offset-2"
                style={{
                  backgroundColor: filterColors.topic.background,
                  color: filterColors.topic.text,
                  borderWidth: "1px",
                  borderStyle: "solid",
                  borderColor: filterColors.topic.border,
                }}
                aria-label={`Filter videos by topic: ${topic.name}${topic.parent_path ? ` (${topic.parent_path})` : ""}`}
              >
                {topic.parent_path
                  ? `${topic.parent_path} > ${topic.name}`
                  : topic.name}
              </Link>
            ))}
          </div>
        ) : (
          <span className="text-gray-400 text-sm">None</span>
        )}
      </Subsection>

      {/* T068, T070: Playlists Subsection - NEW */}
      <Subsection label="Playlists">
        {playlists.length > 0 ? (
          <div className="flex flex-wrap gap-2">
            {playlists.map((playlist) => (
              <Link
                key={playlist.playlist_id}
                to={`/playlists/${playlist.playlist_id}`}
                className="px-3 py-1 text-sm font-medium rounded-full transition-all duration-200 hover:underline hover:brightness-95 focus:outline-none focus:ring-2 focus:ring-offset-2"
                style={{
                  backgroundColor: filterColors.playlist.background,
                  color: filterColors.playlist.text,
                  borderWidth: "1px",
                  borderStyle: "solid",
                  borderColor: filterColors.playlist.border,
                }}
                aria-label={`View playlist: ${playlist.title}`}
              >
                {playlist.title}
              </Link>
            ))}
          </div>
        ) : (
          <span className="text-gray-400 text-sm">None</span>
        )}
      </Subsection>
    </section>
  );
}
