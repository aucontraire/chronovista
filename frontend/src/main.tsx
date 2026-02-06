/**
 * Application entry point.
 *
 * Provider hierarchy (outermost to innermost):
 * 1. StrictMode - React development checks
 * 2. QueryClientProvider - TanStack Query cache (persists across route changes)
 * 3. RouterProvider - React Router with browser history support
 *
 * This hierarchy ensures:
 * - FR-006: Browser back/forward buttons navigate correctly (via createBrowserRouter)
 * - FR-007: Page refresh reloads the current route correctly (via browser history API)
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router-dom";

import { router } from "./router";
import "./index.css";

/**
 * QueryClient configuration with sensible defaults.
 *
 * These settings optimize for a YouTube data management application:
 * - Retry failed requests with exponential backoff
 * - Keep data fresh for 5 minutes (YouTube data doesn't change frequently)
 * - Cache inactive data for 10 minutes
 * - Refetch on window focus to catch updates
 */
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Retry failed requests up to 3 times
      retry: 3,
      // Wait before retrying (exponential backoff)
      retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 30000),
      // Data is considered fresh for 5 minutes
      staleTime: 5 * 60 * 1000,
      // Keep inactive data in cache for 10 minutes
      gcTime: 10 * 60 * 1000,
      // Refetch on window focus (useful for stale data)
      refetchOnWindowFocus: true,
      // Refetch on network reconnect
      refetchOnReconnect: true,
    },
  },
});

const rootElement = document.getElementById("root");

if (!rootElement) {
  throw new Error(
    "Root element not found. Ensure index.html contains <div id='root'></div>"
  );
}

createRoot(rootElement).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>
);
