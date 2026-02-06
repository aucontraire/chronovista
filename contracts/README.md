# API Contracts

This directory contains the OpenAPI specification exported from the Chronovista backend API.

## Files

- `openapi.json` - OpenAPI 3.x specification (auto-generated)

## Exporting the OpenAPI Specification

The backend must be running to export the specification:

```bash
# Start the backend (if not already running)
chronovista api start

# Export the OpenAPI specification
curl -s http://localhost:8765/openapi.json > contracts/openapi.json
```

## When to Regenerate

Regenerate the OpenAPI specification whenever:

- Pydantic request/response models are added or modified
- API endpoints are added, removed, or changed
- Query parameters or path parameters are updated
- Response status codes or error schemas change

## Automation

The `make generate-api` command automates the export and client generation process (coming in Phase 4).

This will:
1. Export the OpenAPI spec from the running backend
2. Run Orval to generate TypeScript API client code
3. Place generated code in `frontend/src/api/`

## Usage with Orval

The `frontend/orval.config.ts` configuration uses this specification to generate type-safe API clients for the frontend.

```bash
# From the frontend directory
cd frontend
pnpm run generate:api
```
