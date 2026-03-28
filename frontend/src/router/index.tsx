/**
 * Router configuration for Chronovista application.
 *
 * FR-021: Implements scroll position restoration for improved navigation UX.
 *
 * Route-level code splitting: each page component is loaded on-demand via
 * React.lazy() so the initial bundle only contains the shell and the page
 * the user is navigating to.  Other pages are fetched in the background
 * when their route is first visited.
 */

import { lazy, Suspense } from "react";
import {
  createBrowserRouter,
  Navigate,
  ScrollRestoration,
} from "react-router-dom";

import { AppShell } from "../components/layout";
import { NotFoundPage } from "../pages/NotFoundPage";

// Lazy-loaded page components (downloaded on first navigation)
const HomePage = lazy(() =>
  import("../pages/HomePage").then((m) => ({ default: m.HomePage })),
);
const VideoDetailPage = lazy(() =>
  import("../pages/VideoDetailPage").then((m) => ({
    default: m.VideoDetailPage,
  })),
);
const SearchPage = lazy(() =>
  import("../pages/SearchPage").then((m) => ({ default: m.SearchPage })),
);
const ChannelsPage = lazy(() =>
  import("../pages/ChannelsPage").then((m) => ({ default: m.ChannelsPage })),
);
const ChannelDetailPage = lazy(() =>
  import("../pages/ChannelDetailPage").then((m) => ({
    default: m.ChannelDetailPage,
  })),
);
const PlaylistsPage = lazy(() =>
  import("../pages/PlaylistsPage").then((m) => ({
    default: m.PlaylistsPage,
  })),
);
const PlaylistDetailPage = lazy(() =>
  import("../pages/PlaylistDetailPage").then((m) => ({
    default: m.PlaylistDetailPage,
  })),
);
const EntitiesPage = lazy(() =>
  import("../pages/EntitiesPage").then((m) => ({
    default: m.EntitiesPage,
  })),
);
const EntityDetailPage = lazy(() =>
  import("../pages/EntityDetailPage").then((m) => ({
    default: m.EntityDetailPage,
  })),
);
const BatchCorrectionsPage = lazy(() =>
  import("../pages/BatchCorrectionsPage").then((m) => ({
    default: m.BatchCorrectionsPage,
  })),
);
const BatchHistoryPage = lazy(() =>
  import("../pages/BatchHistoryPage").then((m) => ({
    default: m.BatchHistoryPage,
  })),
);
const DiffAnalysisPage = lazy(() =>
  import("../pages/DiffAnalysisPage").then((m) => ({
    default: m.DiffAnalysisPage,
  })),
);
const OnboardingPage = lazy(() =>
  import("../pages/OnboardingPage").then((m) => ({
    default: m.OnboardingPage,
  })),
);
const SettingsPage = lazy(() =>
  import("../pages/SettingsPage").then((m) => ({
    default: m.SettingsPage,
  })),
);

/**
 * Loading fallback shown while a lazy-loaded page chunk is being fetched.
 */
function PageLoadingFallback() {
  return (
    <div className="flex items-center justify-center min-h-[50vh]">
      <div className="text-slate-500 text-sm">Loading...</div>
    </div>
  );
}

/**
 * Wrap a lazy-loaded page element in Suspense with the shared fallback.
 */
function lazySuspense(element: React.ReactNode) {
  return <Suspense fallback={<PageLoadingFallback />}>{element}</Suspense>;
}

/**
 * Root layout wrapper with scroll restoration.
 *
 * FR-021: ScrollRestoration component automatically:
 * - Saves scroll position when navigating away from a page
 * - Restores scroll position when navigating back (browser back button)
 * - Scrolls to top when navigating to a new page (forward navigation)
 */
function RootLayout() {
  return (
    <>
      <AppShell />
      <ScrollRestoration />
    </>
  );
}

/**
 * Router configuration with AppShell as the root layout.
 *
 * Routes:
 * - / redirects to /videos
 * - /videos displays the HomePage (video list)
 * - /videos/:videoId displays the VideoDetailPage (FR-001)
 * - /search displays the SearchPage placeholder
 * - /channels displays the ChannelsPage placeholder
 * - /channels/:channelId displays the ChannelDetailPage
 * - /playlists displays the PlaylistsPage (grid view with filters)
 * - /playlists/:playlistId displays the PlaylistDetailPage
 * - * catches all other routes and shows NotFoundPage
 *
 * FR-021: Scroll restoration enabled for all routes via ScrollRestoration component.
 */
export const router = createBrowserRouter([
  {
    path: "/",
    element: <RootLayout />,
    children: [
      {
        index: true,
        element: <Navigate to="/videos" replace />,
      },
      {
        path: "videos",
        element: lazySuspense(<HomePage />),
      },
      {
        path: "videos/:videoId",
        element: lazySuspense(<VideoDetailPage />),
      },
      {
        path: "search",
        element: lazySuspense(<SearchPage />),
      },
      {
        path: "channels",
        element: lazySuspense(<ChannelsPage />),
      },
      {
        path: "channels/:channelId",
        element: lazySuspense(<ChannelDetailPage />),
      },
      {
        path: "playlists",
        element: lazySuspense(<PlaylistsPage />),
      },
      {
        path: "playlists/:playlistId",
        element: lazySuspense(<PlaylistDetailPage />),
      },
      {
        path: "entities",
        element: lazySuspense(<EntitiesPage />),
      },
      {
        path: "entities/:entityId",
        element: lazySuspense(<EntityDetailPage />),
      },
      {
        path: "corrections/batch",
        element: lazySuspense(<BatchCorrectionsPage />),
      },
      {
        path: "corrections/batch/history",
        element: lazySuspense(<BatchHistoryPage />),
      },
      {
        path: "corrections/diff-analysis",
        element: lazySuspense(<DiffAnalysisPage />),
      },
      {
        path: "onboarding",
        element: lazySuspense(<OnboardingPage />),
      },
      {
        path: "settings",
        element: lazySuspense(<SettingsPage />),
      },
      {
        path: "*",
        element: <NotFoundPage />,
      },
    ],
  },
]);
