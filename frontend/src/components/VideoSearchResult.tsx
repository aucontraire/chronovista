import { Link } from 'react-router-dom';
import { HighlightedText } from './HighlightedText';
import type { TitleSearchResult, DescriptionSearchResult } from '../types/search';
import { AvailabilityBadge } from './AvailabilityBadge';
import { isVideoUnavailable } from '../utils/availability';

interface VideoSearchResultProps {
  /** The search result (title or description match) */
  result: TitleSearchResult | DescriptionSearchResult;
  /** Query terms for highlighting */
  queryTerms: string[];
}

/**
 * Checks if a result has a snippet field (is a description search result).
 */
function hasSnippet(result: TitleSearchResult | DescriptionSearchResult): result is DescriptionSearchResult {
  return 'snippet' in result;
}

/**
 * Formats an ISO 8601 date string to a human-readable format.
 */
function formatDate(isoDate: string): string {
  const date = new Date(isoDate);
  return date.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

export function VideoSearchResult({ result, queryTerms }: VideoSearchResultProps) {
  const isUnavailable = isVideoUnavailable(result.availability_status);
  const hasRecoveredData = isUnavailable && !!result.title;
  const cardOpacity = isUnavailable && !hasRecoveredData ? "opacity-50" : "";
  const titleDecoration = isUnavailable && !hasRecoveredData ? "line-through" : "";

  return (
    <article className={`rounded-lg border border-gray-200 bg-white p-4 hover:shadow-md transition-shadow ${cardOpacity}`}>
      {/* Title with highlighting, badge, and line clamp */}
      <div className="flex items-start justify-between gap-2 mb-1.5">
        <h3 className={`line-clamp-2 text-base font-medium flex-1 ${titleDecoration}`}>
          <Link
            to={`/videos/${result.video_id}`}
            className="text-blue-700 hover:underline"
          >
            {!result.title && isUnavailable ? (
              "Unavailable Video"
            ) : (
              <HighlightedText text={result.title} queryTerms={queryTerms} />
            )}
          </Link>
        </h3>
        <AvailabilityBadge status={result.availability_status} className="flex-shrink-0 mt-0.5" />
      </div>

      {/* Metadata row: channel + date */}
      <div className="flex items-center gap-2 text-sm text-gray-500">
        {result.channel_title && (
          <>
            <span>{result.channel_title}</span>
            <span aria-hidden="true">·</span>
          </>
        )}
        <time dateTime={result.upload_date}>{formatDate(result.upload_date)}</time>
      </div>

      {/* Description snippet (only for description search results) */}
      {hasSnippet(result) && !isUnavailable && (
        <p className="mt-2 text-sm text-gray-600 leading-relaxed">
          <HighlightedText text={result.snippet} queryTerms={queryTerms} />
        </p>
      )}
    </article>
  );
}
