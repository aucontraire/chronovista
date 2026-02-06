/**
 * HomePage component - main landing page with video list.
 */

import { VideoList } from "../components/VideoList";

/**
 * HomePage displays the main video list.
 * This component is rendered within the AppShell layout which provides
 * the header, sidebar, and main content area.
 */
export function HomePage() {
  return (
    <div className="p-6 lg:p-8">
      {/* Page Header */}
      <div className="mb-8">
        <h2 className="text-2xl font-bold text-slate-900">Videos</h2>
        <p className="text-slate-600 mt-1">
          Your personal YouTube video library
        </p>
      </div>

      {/* Video List */}
      <section aria-labelledby="videos-heading">
        <h3 id="videos-heading" className="sr-only">
          My Videos
        </h3>
        <VideoList />
      </section>
    </div>
  );
}
