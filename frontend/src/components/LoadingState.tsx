/**
 * LoadingState component displays skeleton cards with shimmer animation.
 */

/**
 * Single skeleton card matching VideoCard dimensions.
 */
function SkeletonCard() {
  return (
    <div
      className="bg-white rounded-xl shadow-md border border-gray-100 p-5 animate-pulse"
      aria-hidden="true"
    >
      {/* Title skeleton */}
      <div className="h-5 bg-gray-200 rounded-md w-3/4 mb-3" />
      <div className="h-5 bg-gray-200 rounded-md w-1/2 mb-3" />

      {/* Channel skeleton */}
      <div className="h-4 bg-gray-200 rounded-md w-2/5 mb-4" />

      {/* Metadata row skeleton */}
      <div className="flex flex-wrap gap-3">
        <div className="h-6 bg-gray-200 rounded-full w-16" />
        <div className="h-6 bg-gray-200 rounded-full w-24" />
        <div className="h-6 bg-gray-200 rounded-full w-20" />
      </div>

      {/* Transcript info skeleton */}
      <div className="mt-4 pt-4 border-t border-gray-100">
        <div className="flex gap-3">
          <div className="h-6 bg-gray-200 rounded-full w-20" />
          <div className="h-6 bg-gray-200 rounded-full w-28" />
        </div>
      </div>
    </div>
  );
}

interface LoadingStateProps {
  /** Number of skeleton cards to display (default: 3) */
  count?: number;
}

/**
 * LoadingState displays multiple skeleton cards to indicate loading.
 * Uses Tailwind's animate-pulse for shimmer effect.
 */
export function LoadingState({ count = 3 }: LoadingStateProps) {
  return (
    <div
      className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6"
      role="status"
      aria-label="Loading videos"
      aria-busy="true"
    >
      {Array.from({ length: count }, (_, index) => (
        <SkeletonCard key={index} />
      ))}
      <span className="sr-only">Loading videos...</span>
    </div>
  );
}
