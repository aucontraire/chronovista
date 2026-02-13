/**
 * SearchResult Component
 *
 * Implements FR-003, FR-005, FR-006, FR-007, FR-008, FR-022, EC-007: Display a single transcript search result.
 *
 * Features:
 * - Video title and channel information
 * - Upload date and timestamp range
 * - Highlighted query terms in segment text
 * - Match count indicator
 * - Language code badge (FR-008)
 * - Clickable video title link (FR-006)
 * - Clickable timestamp link with time parameter (FR-005)
 * - Expandable context viewer (FR-007)
 * - Content truncation with ellipsis (FR-022, T058):
 *   - Video title: max 2 lines
 *   - Channel name: max 1 line
 *   - Transcript text: max 3 lines
 *
 * @see FR-003: Search result display
 * @see FR-005: Timestamp navigation to video page
 * @see FR-006: Video title navigation
 * @see FR-007: Expandable context display
 * @see FR-008: Language filter and display
 * @see FR-022: Content truncation
 * @see EC-007: Handle unknown channel names
 */

import { useState } from "react";
import { Link } from "react-router-dom";
import { SearchResultSegment } from "../types/search";
import { HighlightedText } from "./HighlightedText";
import { ContextExpander } from "./ContextExpander";
import { formatTimestamp } from "../utils/formatTimestamp";
import { formatDate } from "../utils/formatters";

interface SearchResultProps {
  /** Search result segment data */
  segment: SearchResultSegment;
  /** Query terms for highlighting */
  queryTerms: string[];
}

/**
 * Displays a single transcript search result with highlighted query terms.
 *
 * Each result shows the video context, timestamp, and relevant segment text
 * with query terms highlighted for easy scanning.
 *
 * @example
 * ```tsx
 * <SearchResult
 *   segment={resultSegment}
 *   queryTerms={["machine", "learning"]}
 * />
 * ```
 */
export function SearchResult({ segment, queryTerms }: SearchResultProps) {
  const {
    segment_id,
    video_id,
    video_title,
    channel_title,
    video_upload_date,
    start_time,
    end_time,
    text,
    context_before,
    context_after,
    match_count,
    language_code,
  } = segment;

  // Local state for context expansion
  const [isContextExpanded, setIsContextExpanded] = useState(false);

  // Format timestamp range
  const timestampRange = `${formatTimestamp(start_time)} - ${formatTimestamp(end_time)}`;

  // Handle null channel title
  const displayChannelTitle = channel_title ?? "Unknown Channel";

  // Generate deep link URL with language, segment, and timestamp (FR-005, Feature 022 FR-001)
  const videoDeepLinkUrl = `/videos/${video_id}?lang=${language_code}&seg=${segment_id}&t=${Math.floor(start_time)}`;

  return (
    <article
      className="p-4 border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 hover:border-blue-500 dark:hover:border-blue-400 transition-colors"
      aria-label={`Search result from ${video_title}`}
    >
      {/* Video metadata header */}
      <header className="mb-2">
        <div className="flex items-start justify-between gap-2 mb-1">
          {/* T058: Video title truncated to 2 lines (FR-022) */}
          <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 flex-1 line-clamp-2">
            <Link
              to={videoDeepLinkUrl}
              className="hover:text-blue-600 dark:hover:text-blue-400 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 dark:focus:ring-offset-gray-800 rounded"
            >
              {video_title}
            </Link>
          </h3>
          {/* Language code badge */}
          <span
            className="inline-block px-2 py-1 text-xs font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 rounded uppercase shrink-0"
            aria-label={`Language: ${language_code}`}
          >
            {language_code}
          </span>
        </div>
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-gray-600 dark:text-gray-400">
          {/* T058: Channel name truncated to 1 line (FR-022) */}
          <span className="line-clamp-1">{displayChannelTitle}</span>
          <span className="shrink-0">•</span>
          <time dateTime={video_upload_date} className="shrink-0">{formatDate(video_upload_date)}</time>
          <span className="shrink-0">•</span>
          <Link
            to={videoDeepLinkUrl}
            className="font-mono hover:text-blue-600 dark:hover:text-blue-400 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 dark:focus:ring-offset-gray-800 rounded shrink-0"
            aria-label={`Jump to ${timestampRange} in video`}
          >
            {timestampRange}
          </Link>
        </div>
      </header>

      {/* Segment text with highlighted query terms */}
      <div className="mt-3">
        {/* T058: Transcript text truncated to 3 lines (FR-022) */}
        <p className="text-base text-gray-700 dark:text-gray-300 leading-relaxed line-clamp-3">
          <HighlightedText text={text} queryTerms={queryTerms} />
        </p>
      </div>

      {/* Expandable context viewer (FR-007) */}
      <ContextExpander
        contextBefore={context_before}
        contextAfter={context_after}
        expanded={isContextExpanded}
        onToggle={() => setIsContextExpanded(!isContextExpanded)}
        resultId={`${segment_id}`}
        videoTitle={video_title}
      />

      {/* Match count indicator */}
      {match_count > 1 && (
        <footer className="mt-2">
          <span className="inline-block px-2 py-1 text-xs font-medium text-blue-700 dark:text-blue-300 bg-blue-100 dark:bg-blue-900/30 rounded">
            {match_count} {match_count === 1 ? "match" : "matches"}
          </span>
        </footer>
      )}
    </article>
  );
}
