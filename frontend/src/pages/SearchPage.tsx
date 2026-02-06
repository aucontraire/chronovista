/**
 * SearchPage component - placeholder for search functionality.
 */

import { SearchIcon } from "../components/icons";

/**
 * SearchPage displays a placeholder message for the upcoming search feature.
 */
export function SearchPage() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[calc(100vh-4rem)] p-8">
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-12 text-center max-w-md">
        <div className="mx-auto w-16 h-16 mb-6 text-slate-400 bg-slate-100 rounded-full p-4">
          <SearchIcon className="w-full h-full" aria-hidden="true" />
        </div>
        <h2 className="text-2xl font-bold text-slate-900 mb-3">Search</h2>
        <p className="text-slate-600">Coming Soon</p>
        <p className="text-sm text-slate-500 mt-4">
          Search across all your videos, channels, and transcripts.
        </p>
      </div>
    </div>
  );
}
