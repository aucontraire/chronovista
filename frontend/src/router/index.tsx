/**
 * Router configuration for Chronovista application.
 *
 * FR-021: Implements scroll position restoration for improved navigation UX.
 */

import {
  createBrowserRouter,
  Navigate,
  ScrollRestoration,
} from "react-router-dom";

import { AppShell } from "../components/layout";
import { ChannelDetailPage } from "../pages/ChannelDetailPage";
import { ChannelsPage } from "../pages/ChannelsPage";
import { HomePage } from "../pages/HomePage";
import { NotFoundPage } from "../pages/NotFoundPage";
import { PlaylistDetailPage } from "../pages/PlaylistDetailPage";
import { PlaylistsPage } from "../pages/PlaylistsPage";
import { SearchPage } from "../pages/SearchPage";
import { VideoDetailPage } from "../pages/VideoDetailPage";

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
        element: <HomePage />,
      },
      {
        path: "videos/:videoId",
        element: <VideoDetailPage />,
      },
      {
        path: "search",
        element: <SearchPage />,
      },
      {
        path: "channels",
        element: <ChannelsPage />,
      },
      {
        path: "channels/:channelId",
        element: <ChannelDetailPage />,
      },
      {
        path: "playlists",
        element: <PlaylistsPage />,
      },
      {
        path: "playlists/:playlistId",
        element: <PlaylistDetailPage />,
      },
      {
        path: "*",
        element: <NotFoundPage />,
      },
    ],
  },
]);
