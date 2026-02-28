# Frontend Development

Guide to developing the chronovista web frontend.

## Overview

The frontend is a React single-page application located in the `frontend/` directory. It communicates with the chronovista backend API.

| Technology | Version | Purpose |
|------------|---------|---------|
| React | 19.x | UI framework |
| TypeScript | 5.x (strict mode) | Type-safe JavaScript |
| Vite | 6.x | Build tool and dev server |
| Tailwind CSS | 4.x | Utility-first styling |
| TanStack Query | 5.x | Async state management and caching |
| TanStack Virtual | 3.x | Virtualized list rendering |
| React Router | 6.x | Client-side routing |
| Orval | 7.x | API client generation from OpenAPI |

## Getting Started

### Prerequisites

- Node.js 22.x LTS (or 20.x LTS)
- npm 10.x+
- Backend API running on port 8765

### Setup

```bash
cd frontend
npm install
```

### Development Servers

```bash
# From project root - start both backend and frontend
make dev

# Or start individually
make dev-backend   # Backend on port 8765
make dev-frontend  # Frontend on port 8766
```

Open http://localhost:8766 to access the web interface.

## Available Scripts

Run these from the `frontend/` directory:

| Script | Description |
|--------|-------------|
| `npm run dev` | Start Vite dev server with hot module replacement |
| `npm run build` | TypeScript check + production build |
| `npm run preview` | Preview the production build locally |
| `npm run typecheck` | Run TypeScript type checking (no emit) |
| `npm run generate-api` | Generate API client from OpenAPI spec |
| `npm test` | Run all tests with vitest |
| `npm run test:ui` | Run tests with vitest's browser UI |
| `npm run test:coverage` | Run tests with V8 coverage report |

## Running Tests

The frontend has 2,100+ tests using [vitest](https://vitest.dev/) and [React Testing Library](https://testing-library.com/docs/react-testing-library/intro/).

```bash
cd frontend

# Run all tests
npm test

# Run tests in watch mode (default behavior)
npm test

# Run tests with coverage
npm run test:coverage

# Run a specific test file
npx vitest run src/components/transcript/__tests__/TranscriptSegments.test.tsx

# Run tests matching a pattern
npx vitest run --grep "deep link"
```

### Test Organization

```
frontend/src/
├── components/
│   ├── transcript/
│   │   └── __tests__/          # Transcript component tests
│   ├── search/
│   │   └── __tests__/          # Search component tests
│   └── video/
│       └── __tests__/          # Video component tests
├── hooks/
│   └── __tests__/              # Custom hook tests
└── pages/
    └── __tests__/              # Page-level tests
```

Tests are co-located with their source files in `__tests__/` directories.

### Testing Patterns

- **Component tests** use `@testing-library/react` with `render`, `screen`, and `userEvent`
- **Hook tests** use `renderHook` from `@testing-library/react`
- **API mocking** is done by mocking the `apiFetch` function
- **Query client** is wrapped in test providers for TanStack Query

## API Client Generation

The frontend generates typed API clients from the backend's OpenAPI specification using [Orval](https://orval.dev/).

### Regenerating After Backend Changes

When you modify backend Pydantic models or API endpoints:

1. Start the backend: `make dev-backend` (in a separate terminal)
2. Run: `make generate-api`

This:
1. Fetches `http://localhost:8765/openapi.json` and saves it to `contracts/openapi.json`
2. Runs Orval to generate TypeScript types and React Query hooks

### Manual API Client

For endpoints not yet in the generated client, use the `apiFetch` utility:

```typescript
import { apiFetch } from "../api/config";

const data = await apiFetch<ResponseType>("/videos/abc123");
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `VITE_API_BASE_URL` | Backend API base URL | `http://localhost:8765/api/v1` |

Configure in `frontend/.env` (create from `frontend/.env.example`).

## Styling Conventions

- Use [Tailwind CSS](https://tailwindcss.com/) utility classes
- Design tokens are defined in `frontend/src/styles/tokens.ts`
- The app uses a light theme only (`bg-slate-50` main content)
- Avoid `dark:` variants in components since the app shell has no dark mode

## Component Patterns

- Components use TypeScript with explicit prop interfaces
- State management via TanStack Query for server state
- URL state via React Router's `useSearchParams`
- Virtualized lists via `@tanstack/react-virtual` for large datasets

## See Also

- [Frontend Architecture](../architecture/frontend-architecture.md) - Component hierarchy and routing
- [Makefile Reference](makefile-reference.md) - All development commands
- [Testing Guide](testing.md) - Backend testing
