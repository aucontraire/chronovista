# Chronovista Frontend

A modern React frontend for the Chronovista YouTube analytics platform.

## Development Status

**MVP / In Development**

This frontend is part of the Chronovista monorepo and provides a web interface for browsing and analyzing YouTube video data. It communicates with the Chronovista backend API.

## Prerequisites

- **Node.js**: 22.x LTS or 20.x LTS (22.x recommended for full Orval compatibility)
- **npm**: 10.x or higher
- **Backend API**: Chronovista backend running on `http://localhost:8765` (for local development)

## Quick Start

```bash
# Install dependencies
npm install

# Copy environment configuration (if customization needed)
cp .env.example .env

# Start development server
npm run dev
```

The development server will start at `http://localhost:8766`.

## Available Scripts

| Script | Description |
|--------|-------------|
| `npm run dev` | Start Vite development server with hot reload |
| `npm run build` | Type-check and build for production |
| `npm run preview` | Preview production build locally |
| `npm run typecheck` | Run TypeScript type checking without emitting files |
| `npm run generate-api` | Generate API client from OpenAPI specification using Orval |

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `VITE_API_BASE_URL` | Base URL for the backend API | `http://localhost:8765/api/v1` |

### Configuring for Production

For production deployment, set the `VITE_API_BASE_URL` environment variable to point to your production API:

```bash
# Example: Production deployment
VITE_API_BASE_URL=https://api.example.com/api/v1

# Example: Staging environment
VITE_API_BASE_URL=https://staging-api.example.com/api/v1
```

This is the **only configuration** needed to point the frontend to a different backend.

## Tech Stack

| Technology | Purpose |
|------------|---------|
| [Vite](https://vitejs.dev/) | Build tool and dev server |
| [React 19](https://react.dev/) | UI framework |
| [TypeScript 5](https://www.typescriptlang.org/) | Type-safe JavaScript |
| [Tailwind CSS 4](https://tailwindcss.com/) | Utility-first CSS |
| [TanStack Query](https://tanstack.com/query) | Async state management and caching |
| [Orval](https://orval.dev/) | API client generation from OpenAPI |

## API Dependency

This frontend requires the Chronovista backend API to function. The backend provides:

- Video listing and details
- Channel information
- Transcript data
- Language preferences
- Tag analytics

### Local Development

For local development, ensure the backend is running:

```bash
# From the monorepo root
chronovista api start
# or
uvicorn chronovista.api.main:app --port 8765
```

The Vite dev server is configured to proxy `/api` requests to `http://localhost:8765`.

### API Client Generation

API types and hooks are generated from the OpenAPI specification:

```bash
# Regenerate API client after backend changes
npm run generate-api
```

This reads from `../contracts/openapi.json` and generates typed React Query hooks.

## Project Structure

```
frontend/
├── src/
│   ├── api/          # API configuration and generated clients
│   ├── components/   # Reusable UI components
│   ├── hooks/        # Custom React hooks
│   ├── pages/        # Page components
│   ├── types/        # TypeScript type definitions
│   ├── App.tsx       # Root application component
│   └── main.tsx      # Application entry point
├── index.html        # HTML template
├── vite.config.ts    # Vite configuration
├── tailwind.config.ts # Tailwind CSS configuration
├── tsconfig.json     # TypeScript configuration
├── orval.config.ts   # Orval API generation config
└── package.json      # Dependencies and scripts
```

## Standalone Extraction

This frontend can be extracted to a separate repository:

```bash
# From the monorepo root
git subtree split -P frontend -b frontend-standalone

# Push to new remote
git push <new-remote> frontend-standalone:main
```

After extraction:

1. Update `orval.config.ts` to point to the hosted OpenAPI specification
2. Set `VITE_API_BASE_URL` to the production API endpoint
3. Remove the `../contracts/openapi.json` reference or host the spec separately

## Development Notes

- The development server runs on port 8766 to avoid conflicts with the backend (8765)
- Hot Module Replacement (HMR) is enabled for fast development
- TypeScript strict mode is enabled for maximum type safety
- All components use TypeScript with explicit type annotations

## CI/CD Integration

### TypeScript Type Checking

For CI pipelines, run type checking with:

```bash
npm run typecheck
```

This runs `tsc --noEmit` to verify all types are correct without generating output files.

### Future Enhancements (Planned)

The following CI/CD integrations are planned for future iterations:

- **Vitest Component Tests**: Unit and integration tests for React components
- **OpenAPI Automation**: Pre-commit hooks and CI workflows to auto-regenerate API client when backend models change
- **E2E Testing**: Playwright or Cypress end-to-end tests

## License

Part of the Chronovista project.
