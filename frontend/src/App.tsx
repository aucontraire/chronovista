/**
 * App component - root component with providers.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { HomePage } from "./pages/HomePage";

/**
 * QueryClient configuration with sensible defaults.
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
      // Don't refetch on reconnect automatically
      refetchOnReconnect: true,
    },
  },
});

/**
 * App is the root component that provides global context.
 */
function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <HomePage />
    </QueryClientProvider>
  );
}

export default App;
