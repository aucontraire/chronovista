/**
 * Router configuration for Chronovista application.
 */

import { createBrowserRouter, Navigate } from "react-router-dom";

import { AppShell } from "../components/layout";
import { ChannelsPage } from "../pages/ChannelsPage";
import { HomePage } from "../pages/HomePage";
import { NotFoundPage } from "../pages/NotFoundPage";
import { SearchPage } from "../pages/SearchPage";

/**
 * Router configuration with AppShell as the root layout.
 *
 * Routes:
 * - / redirects to /videos
 * - /videos displays the HomePage (video list)
 * - /search displays the SearchPage placeholder
 * - /channels displays the ChannelsPage placeholder
 * - * catches all other routes and shows NotFoundPage
 */
export const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
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
        path: "search",
        element: <SearchPage />,
      },
      {
        path: "channels",
        element: <ChannelsPage />,
      },
      {
        path: "*",
        element: <NotFoundPage />,
      },
    ],
  },
]);
