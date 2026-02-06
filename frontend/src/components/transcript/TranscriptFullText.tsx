/**
 * TranscriptFullText component displays transcript as continuous prose.
 *
 * Shows the complete transcript text without timestamps, optimized for
 * reading and searching through content.
 *
 * Implements:
 * - FR-019: Full text view as continuous prose
 * - Loading state with skeleton placeholder
 * - Error state with retry option
 *
 * @module components/transcript/TranscriptFullText
 */

import { useCallback } from "react";

import { useTranscript } from "../../hooks/useTranscript";

/**
 * Props for the TranscriptFullText component.
 */
export interface TranscriptFullTextProps {
  /** The YouTube video ID to fetch transcript for */
  videoId: string;
  /** The BCP-47 language code for the transcript */
  languageCode: string;
}

/**
 * Skeleton component for loading state.
 * Displays animated placeholder lines mimicking transcript text.
 */
function TranscriptSkeleton() {
  return (
    <div
      className="space-y-3 animate-pulse"
      role="status"
      aria-label="Loading transcript"
    >
      {/* Multiple lines of varying widths to simulate text */}
      <div className="h-4 bg-gray-200 rounded w-full" />
      <div className="h-4 bg-gray-200 rounded w-11/12" />
      <div className="h-4 bg-gray-200 rounded w-full" />
      <div className="h-4 bg-gray-200 rounded w-10/12" />
      <div className="h-4 bg-gray-200 rounded w-full" />
      <div className="h-4 bg-gray-200 rounded w-9/12" />
      <div className="h-4 bg-gray-200 rounded w-full" />
      <div className="h-4 bg-gray-200 rounded w-11/12" />
      <span className="sr-only">Loading transcript content...</span>
    </div>
  );
}

/**
 * Error display component with retry button.
 */
interface ErrorDisplayProps {
  /** Error message to display */
  message: string;
  /** Callback to retry the fetch */
  onRetry: () => void;
}

function ErrorDisplay({ message, onRetry }: ErrorDisplayProps) {
  return (
    <div
      className="rounded-lg border border-red-200 bg-red-50 p-4"
      role="alert"
      aria-live="polite"
    >
      <div className="flex flex-col items-start gap-3">
        <div className="flex items-start gap-2">
          {/* Error icon */}
          <svg
            className="h-5 w-5 text-red-600 flex-shrink-0 mt-0.5"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
          <div>
            <h3 className="text-sm font-medium text-red-800">
              Failed to load transcript
            </h3>
            <p className="text-sm text-red-700 mt-1">{message}</p>
          </div>
        </div>

        <button
          type="button"
          onClick={onRetry}
          className="
            inline-flex items-center gap-2 px-3 py-1.5
            text-sm font-medium text-red-700
            bg-white border border-red-300 rounded-md
            hover:bg-red-50 hover:border-red-400
            focus:outline-none focus-visible:ring-2 focus-visible:ring-red-500 focus-visible:ring-offset-2
            transition-colors duration-150
          "
        >
          {/* Retry icon */}
          <svg
            className="h-4 w-4"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
            />
          </svg>
          Try again
        </button>
      </div>
    </div>
  );
}

/**
 * TranscriptFullText displays transcript as continuous prose text.
 *
 * Features:
 * - Displays full transcript text without timestamps (FR-019)
 * - Loading state with skeleton placeholder
 * - Error state with retry option
 * - Proper text formatting and line height for readability
 * - WCAG AA compliant text contrast (NFR-A18)
 *
 * @example
 * ```tsx
 * <TranscriptFullText
 *   videoId="dQw4w9WgXcQ"
 *   languageCode="en"
 * />
 * ```
 */
export function TranscriptFullText({
  videoId,
  languageCode,
}: TranscriptFullTextProps) {
  const { data: transcript, isLoading, isError, error, refetch } = useTranscript(
    videoId,
    languageCode
  );

  /**
   * Handles retry button click.
   */
  const handleRetry = useCallback(() => {
    void refetch();
  }, [refetch]);

  // Loading state
  if (isLoading) {
    return <TranscriptSkeleton />;
  }

  // Error state
  if (isError) {
    return (
      <ErrorDisplay
        message={error?.message ?? "An unexpected error occurred"}
        onRetry={handleRetry}
      />
    );
  }

  // No transcript data
  if (!transcript) {
    return (
      <div className="text-sm text-gray-500" role="status">
        No transcript available for this language.
      </div>
    );
  }

  // Empty transcript
  if (!transcript.full_text || transcript.full_text.trim().length === 0) {
    return (
      <div className="text-sm text-gray-500" role="status">
        Transcript is empty.
      </div>
    );
  }

  return (
    <div
      className="prose prose-sm max-w-none"
      role="region"
      aria-label="Full transcript text"
    >
      {/*
        Render full text as paragraphs, preserving line breaks.
        Using text-gray-900 for WCAG AA compliance (NFR-A18).
        Line height of 1.75 for readability.
      */}
      <p className="text-sm text-gray-900 leading-7 whitespace-pre-wrap">
        {transcript.full_text}
      </p>
    </div>
  );
}
