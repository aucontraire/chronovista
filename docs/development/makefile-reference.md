# Makefile Reference

Complete reference for all Makefile targets. Run `make help` for a quick summary.

## Setup

| Target | Description |
|--------|-------------|
| `make install` | Install project dependencies (verifies Poetry first) |
| `make install-dev` | Install development dependencies |
| `make install-nlp` | Install NLP dependencies (spaCy, keyBERT, transformers) |
| `make install-db` | Install database driver dependencies (psycopg2, pymysql) |
| `make install-all` | Install all dependency groups (dev + nlp + database) |
| `make install-docs` | Install documentation dependencies (MkDocs, mkdocstrings) |
| `make clean` | Remove build artifacts, caches, and compiled files |
| `make check-poetry` | Verify Poetry installation and show version/path |

## Testing

| Target | Description |
|--------|-------------|
| `make test` | Run all tests with verbose output |
| `make test-cov` | Run tests with coverage report (90% threshold enforced) |
| `make test-cov-dev` | Run tests with coverage (no threshold, for development) |
| `make test-unit` | Run only unit tests (marked with `@pytest.mark.unit`) |
| `make test-integration` | Run only integration tests (marked with `@pytest.mark.integration`) |
| `make test-integration-reset` | Drop and recreate the integration test database |
| `make test-watch` | Run tests in quick-feedback mode (stop on first failure) |
| `make test-fast` | Run tests without coverage (fastest feedback) |
| `make quick-test` | Minimal test run (no warnings, no headers) |

!!! note "Frontend Tests"
    Frontend tests use vitest, not pytest. See [Frontend Development](frontend-development.md) for frontend test commands.

## Code Quality

| Target | Description |
|--------|-------------|
| `make lint` | Run ruff linter on src and tests |
| `make format` | Format code with Black and sort imports with isort |
| `make format-check` | Check formatting without modifying files |
| `make type-check` | Run mypy type checker on src and tests |
| `make quality` | Run all quality checks (format-check + lint + type-check) |
| `make pre-commit` | Run all pre-commit hooks on all files |
| `make quick-check` | Quick formatting and lint check (src only) |

## Development Servers

| Target | Description |
|--------|-------------|
| `make dev` | Start both backend (port 8765) and frontend (port 8766) |
| `make dev-backend` | Start backend API server only (uvicorn with hot reload) |
| `make dev-frontend` | Start frontend Vite dev server only |
| `make run` | Show CLI help (`chronovista --help`) |
| `make run-status` | Run `chronovista status` |
| `make run-auth` | Show auth command help |
| `make run-sync` | Show sync command help |
| `make shell` | Enter Poetry virtual environment shell |
| `make build` | Build the Python package |

## Frontend API Generation

| Target | Description |
|--------|-------------|
| `make generate-api` | Export OpenAPI spec and generate TypeScript client |

!!! warning "Backend Must Be Running"
    `make generate-api` fetches the OpenAPI spec from `http://localhost:8765/openapi.json`. Start the backend first with `make dev-backend` in a separate terminal.

## Database (Production/Default)

These targets use `alembic.ini` (default config pointing to `DATABASE_URL`):

| Target | Description |
|--------|-------------|
| `make db-upgrade` | Run all pending migrations |
| `make db-downgrade` | Rollback the last migration |
| `make db-revision` | Create a new auto-generated migration (prompts for message) |
| `make db-reset` | Rollback all migrations and re-apply from scratch |

## Docker Development Database

These targets use `docker-compose.dev.yml` and `alembic-dev.ini`:

| Target | Description |
|--------|-------------|
| `make dev-db-up` | Start the development PostgreSQL container (port 5434) |
| `make dev-db-down` | Stop the development database container |
| `make dev-db-reset` | Destroy and recreate the development database (all data lost) |
| `make dev-db-logs` | Stream development database logs |
| `make dev-db-shell` | Open a psql shell to the development database |
| `make dev-db-status` | Check if the dev database is running and show migration state |
| `make dev-db-admin` | Start pgAdmin web UI (http://localhost:8081) |
| `make dev-db-admin-down` | Stop pgAdmin |
| `make dev-migrate` | Run migrations on the development database |
| `make dev-revision` | Create a new migration using the development database |

### Development Database Connection

```
Host: localhost
Port: 5434
Database: chronovista_dev
Username: dev_user
Password: dev_password
```

### Alembic Configuration

The project has two Alembic configuration files:

| File | Used by | Points to |
|------|---------|-----------|
| `alembic.ini` | `make db-upgrade`, `make db-revision` | `DATABASE_URL` (production/local, port 5432) |
| `alembic-dev.ini` | `make dev-migrate`, `make dev-revision` | `DATABASE_DEV_URL` (Docker, port 5434) |

Always use `make dev-migrate` and `make dev-revision` when working with the Docker development database to avoid accidentally running migrations against the wrong database.

## Full Setup & Reset

| Target | Description |
|--------|-------------|
| `make dev-full-setup` | Start dev DB + run migrations + create integration test DB |
| `make dev-full-reset` | Destroy everything and recreate from scratch |
| `make dev-setup` | Install dev dependencies + install pre-commit hooks |
| `make dev-check` | Run format + lint + type-check + test with coverage |
| `make dev-clean` | Clean artifacts and remove Poetry virtual environment |

## Schema Validation

| Target | Description |
|--------|-------------|
| `make test-models` | Test database models against the current schema |
| `make test-models-dev` | Test models using the development database |
| `make validate-schema` | Validate schema with real YouTube API data |
| `make validate-schema-takeout` | Validate using Takeout + API data combined |

## Documentation

| Target | Description |
|--------|-------------|
| `make docs-serve` | Start MkDocs development server (http://localhost:8000) |
| `make docs-build` | Build static documentation site |
| `make docs-deploy` | Deploy docs to GitHub Pages using mike |
| `make docs-clean` | Remove the built documentation site |
| `make docs` | Alias for `docs-serve` |
| `make serve-docs` | Alias for `docs-serve` |

## CI/CD

| Target | Description |
|--------|-------------|
| `make ci` | Run full CI pipeline (quality + tests) |
| `make ci-quality` | Run quality checks with CI-friendly output |
| `make ci-test` | Run tests with XML coverage output for CI |

## Release

| Target | Description |
|--------|-------------|
| `make release-check` | Validate package (Poetry check + build + twine check) |
| `make release-test` | Publish to TestPyPI |
| `make release` | Publish to PyPI |

## Dependency Management

| Target | Description |
|--------|-------------|
| `make deps-show` | List all installed dependencies |
| `make deps-show-tree` | Show dependency tree |
| `make deps-outdated` | Check for outdated dependencies |
| `make deps-update` | Update all dependencies |
| `make deps-lock` | Regenerate the lock file |
| `make export-requirements` | Export requirements.txt and requirements-dev.txt |

## Environment

| Target | Description |
|--------|-------------|
| `make info` | Show project info (versions, paths, dependency tree) |
| `make env-info` | Show Poetry environment details |
| `make env-list` | List all Poetry environments |
| `make env-remove` | Remove the current Poetry virtual environment |
