/**
 * HomePage component - main landing page with video list.
 */

import { VideoList } from "../components/VideoList";

/**
 * HomePage displays the main video list with a page title.
 */
export function HomePage() {
  return (
    <main className="min-h-screen bg-gradient-to-b from-gray-50 to-gray-100">
      {/* Header */}
      <header className="bg-white shadow-md border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <h1 className="text-3xl font-bold text-gray-900 tracking-tight">Chronovista</h1>
          <p className="text-base text-gray-600 mt-2">
            Your personal YouTube video library
          </p>
        </div>
      </header>

      {/* Main Content */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
        <section aria-labelledby="videos-heading">
          <h2 id="videos-heading" className="sr-only">
            My Videos
          </h2>
          <VideoList />
        </section>
      </div>

      {/* Footer */}
      <footer className="bg-white border-t border-gray-200 mt-auto shadow-inner">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 text-center text-sm text-gray-500">
          Chronovista - Manage your YouTube data locally
        </div>
      </footer>
    </main>
  );
}
