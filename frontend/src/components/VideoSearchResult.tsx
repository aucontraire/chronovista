import { Link } from 'react-router-dom';
import { HighlightedText } from './HighlightedText';
import type { TitleSearchResult, DescriptionSearchResult } from '../types/search';

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
  return (
    <article className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-4 hover:shadow-md transition-shadow">
      {/* Title with highlighting and line clamp */}
      <h3 className="line-clamp-2 text-base font-medium">
        <Link
          to={`/videos/${result.video_id}`}
          className="text-blue-700 dark:text-blue-400 hover:underline"
        >
          <HighlightedText text={result.title} queryTerms={queryTerms} />
        </Link>
      </h3>

      {/* Metadata row: channel + date */}
      <div className="mt-1.5 flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
        {result.channel_title && (
          <>
            <span>{result.channel_title}</span>
            <span aria-hidden="true">·</span>
          </>
        )}
        <time dateTime={result.upload_date}>{formatDate(result.upload_date)}</time>
      </div>

      {/* Description snippet (only for description search results) */}
      {hasSnippet(result) && (
        <p className="mt-2 text-sm text-gray-600 dark:text-gray-300 leading-relaxed">
          <HighlightedText text={result.snippet} queryTerms={queryTerms} />
        </p>
      )}
    </article>
  );
}
