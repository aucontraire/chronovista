/**
 * Test utilities for setting up React Query and React Router.
 *
 * Provides wrapper components and helper functions for testing components
 * that use TanStack Query, React Router, and other context providers.
 */

import { ReactElement, ReactNode } from 'react';
import { render, RenderOptions } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

/**
 * Creates a new QueryClient for testing with disabled retries and cache.
 */
export function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
        staleTime: 0,
      },
      mutations: {
        retry: false,
      },
    },
    logger: {
      log: () => {},
      warn: () => {},
      error: () => {},
    },
  });
}

/**
 * Props for AllProviders wrapper component.
 */
interface AllProvidersProps {
  children: ReactNode;
  queryClient?: QueryClient;
  initialEntries?: string[];
  path?: string;
}

/**
 * Wrapper component that provides all necessary context providers for testing.
 */
function AllProviders({
  children,
  queryClient = createTestQueryClient(),
  initialEntries = ['/'],
  path = '*',
}: AllProvidersProps) {
  return (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={initialEntries}>
        <Routes>
          <Route path={path} element={<>{children}</>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

/**
 * Custom render options extending RTL's RenderOptions.
 */
export interface CustomRenderOptions extends Omit<RenderOptions, 'wrapper'> {
  queryClient?: QueryClient;
  initialEntries?: string[];
  path?: string;
}

/**
 * Custom render function that wraps components with all providers.
 *
 * @param ui - The component to render
 * @param options - Render options including query client and router config
 * @returns Render result with query client and rerender helper
 */
export function renderWithProviders(
  ui: ReactElement,
  {
    queryClient,
    initialEntries,
    path,
    ...renderOptions
  }: CustomRenderOptions = {}
) {
  const testQueryClient = queryClient ?? createTestQueryClient();

  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <AllProviders
        queryClient={testQueryClient}
        initialEntries={initialEntries}
        path={path}
      >
        {children}
      </AllProviders>
    );
  }

  const result = render(ui, { wrapper: Wrapper, ...renderOptions });

  return {
    ...result,
    queryClient: testQueryClient,
    user: userEvent.setup(),
  };
}

/**
 * Re-export everything from React Testing Library.
 */
export * from '@testing-library/react';
import { userEvent } from '@testing-library/user-event';

// Export userEvent separately for backwards compatibility
export { userEvent };
