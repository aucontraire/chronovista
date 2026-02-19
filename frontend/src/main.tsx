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

import { QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router-dom";

import { queryClient } from "./lib/queryClient";
import { router } from "./router";
import "./index.css";

const rootElement = document.getElementById("root");

if (!rootElement) {
  throw new Error(
    "Root element not found. Ensure index.html contains <div id='root'></div>"
  );
}

createRoot(rootElement).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} future={{ v7_startTransition: true }} />
    </QueryClientProvider>
  </StrictMode>
);
