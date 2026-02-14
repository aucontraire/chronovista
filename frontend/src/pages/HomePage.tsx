/**
 * HomePage component - main landing page with video list.
 */

import { useEffect } from "react";
import { useSearchParams } from "react-router-dom";

import { VideoList } from "../components/VideoList";
import { VideoFilters } from "../components/VideoFilters";
import { useVideos } from "../hooks/useVideos";

/**
 * HomePage displays the main video list with filters.
 * This component is rendered within the AppShell layout which provides
 * the header, sidebar, and main content area.
 */
export function HomePage() {
  const [searchParams] = useSearchParams();

  // Read filter state from URL
  const tags = searchParams.getAll('tag');
  const category = searchParams.get('category');
  const topicIds = searchParams.getAll('topic_id');
  // T031: Read include_unavailable state from URL (FR-021)
  const includeUnavailable = searchParams.get('include_unavailable') === 'true';

  // Get total count for filters display (using the same hook with filters)
  const { total } = useVideos({ tags, category, topicIds, includeUnavailable });

  // Set page title
  useEffect(() => {
    document.title = "Videos - ChronoVista";
    return () => {
      document.title = "ChronoVista";
    };
  }, []);

  return (
    <div className="p-6 lg:p-8">
      {/* Page Header */}
      <div className="mb-8">
        <h2 className="text-2xl font-bold text-slate-900">Videos</h2>
        <p className="text-slate-600 mt-1">
          Your personal YouTube video library
        </p>
      </div>

      {/* Video Filters */}
      <section aria-labelledby="filters-heading" className="mb-6">
        <h3 id="filters-heading" className="sr-only">
          Video Filters
        </h3>
        <VideoFilters videoCount={total} />
      </section>

      {/* Video List */}
      <section aria-labelledby="videos-heading">
        <h3 id="videos-heading" className="sr-only">
          Filtered Videos
        </h3>
        <VideoList tags={tags} category={category} topicIds={topicIds} includeUnavailable={includeUnavailable} />
      </section>
    </div>
  );
}
