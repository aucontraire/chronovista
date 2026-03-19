# Makefile for chronovista development (Poetry-based)
.PHONY: help install install-dev clean test test-cov test-unit test-integration test-integration-reset lint format type-check quality pre-commit run build docs docs-serve docs-build docs-deploy dev dev-backend dev-frontend generate-api docker-build docker-up docker-down docker-logs docker-shell docker-db-shell docker-status docker-setup docker-clean docker-restart

# Default target
help:
	@echo "Available targets:"
	@echo "  help              - Show this help message"
	@echo "  check-poetry      - Verify Poetry installation and PATH"
	@echo ""
	@echo "Setup:"
	@echo "  install           - Install project dependencies"
	@echo "  install-dev       - Install development dependencies"
	@echo "  install-nlp       - Install NLP dependencies (spaCy, keyBERT, transformers)"
	@echo "  install-db        - Install database driver dependencies (psycopg2, pymysql)"
	@echo "  install-all       - Install all dependency groups (dev + nlp + database)"
	@echo "  install-docs      - Install documentation dependencies (MkDocs)"
	@echo "  clean             - Clean build artifacts and cache"
	@echo ""
	@echo "Testing:"
	@echo "  test              - Run all tests with verbose output"
	@echo "  test-cov          - Run tests with coverage report (90% threshold)"
	@echo "  test-cov-dev      - Run tests with coverage (no threshold)"
	@echo "  test-unit         - Run unit tests only"
	@echo "  test-integration  - Run integration tests only"
	@echo "  test-integration-reset - Reset integration test database"
	@echo "  test-fast         - Run tests without coverage (fastest)"
	@echo "  test-watch        - Run tests with stop-on-first-failure"
	@echo "  quick-test        - Minimal test run (no warnings, no headers)"
	@echo ""
	@echo "Code Quality:"
	@echo "  lint              - Run linting (ruff)"
	@echo "  format            - Format code (black + isort)"
	@echo "  format-check      - Check formatting without modifying files"
	@echo "  type-check        - Run type checking (mypy)"
	@echo "  quality           - Run all checks (format-check + lint + type-check)"
	@echo "  pre-commit        - Run pre-commit hooks on all files"
	@echo "  quick-check       - Quick format + lint check (src only)"
	@echo ""
	@echo "Development:"
	@echo "  run               - Show CLI help (chronovista --help)"
	@echo "  run-status        - Run chronovista status"
	@echo "  run-auth          - Show auth command help"
	@echo "  run-sync          - Show sync command help"
	@echo "  build             - Build the package"
	@echo "  shell             - Enter Poetry virtual environment shell"
	@echo "  dev               - Start backend (8765) and frontend (8766) dev servers"
	@echo "  dev-backend       - Start backend dev server only (port 8765)"
	@echo "  dev-frontend      - Start frontend dev server only (port 8766)"
	@echo ""
	@echo "Development Workflow:"
	@echo "  dev-setup         - Install dev dependencies + pre-commit hooks"
	@echo "  dev-check         - Run format + lint + type-check + test with coverage"
	@echo "  dev-clean         - Clean artifacts and remove Poetry virtual environment"
	@echo "  dev-full-setup    - Start dev DB + migrate + create integration test DB"
	@echo "  dev-full-reset    - Destroy everything and recreate from scratch"
	@echo ""
	@echo "Frontend API Generation:"
	@echo "  generate-api      - Export OpenAPI spec and generate TypeScript client"
	@echo "                      (requires backend running on port 8765)"
	@echo ""
	@echo "Documentation:"
	@echo "  docs-serve        - Serve documentation locally (http://localhost:8000)"
	@echo "  docs-build        - Build static documentation site"
	@echo "  docs-deploy       - Deploy docs to GitHub Pages (using mike)"
	@echo "  docs-clean        - Remove built documentation site"
	@echo ""
	@echo "Database (production - uses alembic.ini):"
	@echo "  db-upgrade        - Run all pending migrations"
	@echo "  db-downgrade      - Rollback the last migration"
	@echo "  db-revision       - Create new auto-generated migration"
	@echo "  db-reset          - Rollback all migrations and re-apply"
	@echo ""
	@echo "Docker Development Database (uses alembic-dev.ini, port 5434):"
	@echo "  dev-db-up         - Start development PostgreSQL container"
	@echo "  dev-db-down       - Stop development database container"
	@echo "  dev-db-reset      - Destroy and recreate dev database (all data lost)"
	@echo "  dev-db-status     - Check if dev database is running + migration state"
	@echo "  dev-db-logs       - Stream development database logs"
	@echo "  dev-db-shell      - Open psql shell to development database"
	@echo "  dev-db-admin      - Start pgAdmin web UI (http://localhost:8081)"
	@echo "  dev-db-admin-down - Stop pgAdmin"
	@echo "  dev-migrate       - Run migrations on development database"
	@echo "  dev-revision      - Create migration using development database"
	@echo ""
	@echo "Schema Validation:"
	@echo "  test-models       - Test database models (use DEVELOPMENT_MODE=true for dev DB)"
	@echo "  test-models-dev   - Test models using development database"
	@echo "  validate-schema   - Validate schema with real YouTube API data"
	@echo "  validate-schema-takeout - Validate using Takeout + API data"
	@echo ""
	@echo "CI/CD:"
	@echo "  ci                - Run full CI pipeline (quality + tests)"
	@echo "  ci-quality        - Run quality checks with CI-friendly output"
	@echo "  ci-test           - Run tests with XML coverage for CI"
	@echo ""
	@echo "Release:"
	@echo "  release-check     - Validate package (check + build + twine check)"
	@echo "  release-test      - Publish to TestPyPI"
	@echo "  release           - Publish to PyPI"
	@echo ""
	@echo "Docker (full-stack container):"
	@echo "  docker-setup      - First-time setup: validate prereqs, build, start, health check"
	@echo "  docker-build      - Build the Docker image (multi-stage: Poetry + Vite + runtime)"
	@echo "  docker-up         - Start the full stack (postgres + app) in background"
	@echo "  docker-down       - Stop the full stack"
	@echo "  docker-restart    - Restart the full stack"
	@echo "  docker-logs       - Stream app container logs"
	@echo "  docker-status     - Show container status and health"
	@echo "  docker-shell      - Open a bash shell in the app container"
	@echo "  docker-db-shell   - Open psql shell in the Docker postgres"
	@echo "  docker-clean      - Stop stack and remove volumes (destroys DB data)"
	@echo ""
	@echo "Environment:"
	@echo "  info              - Show project info (versions, paths, deps)"
	@echo "  env-info          - Show Poetry environment details"
	@echo "  env-list          - List all Poetry environments"
	@echo "  env-remove        - Remove current Poetry virtual environment"
	@echo ""
	@echo "Dependency Management:"
	@echo "  deps-show         - List all installed dependencies"
	@echo "  deps-show-tree    - Show dependency tree"
	@echo "  deps-outdated     - Check for outdated dependencies"
	@echo "  deps-update       - Update all dependencies"
	@echo "  deps-lock         - Regenerate the lock file"
	@echo "  export-requirements - Export requirements.txt files"

# Variables with fallback Poetry detection
POETRY := $(shell command -v poetry 2> /dev/null || echo "$(HOME)/.local/bin/poetry")
POETRY_RUN := $(POETRY) run
PACKAGE_NAME := chronovista
SRC_DIR := src
TEST_DIR := tests
DOCS_DIR := docs

# Poetry verification target
check-poetry:
	@echo "🔍 Checking Poetry installation..."
	@if ! command -v "$(POETRY)" >/dev/null 2>&1; then \
		echo "❌ ERROR: Poetry not found at $(POETRY)"; \
		echo "💡 Solutions:"; \
		echo "   1. Run: ./scripts/dev_setup.sh"; \
		echo "   2. Install Poetry: curl -sSL https://install.python-poetry.org | python3 -"; \
		echo "   3. Add to PATH: export PATH=\"\$$HOME/.local/bin:\$$PATH\""; \
		echo "   4. Restart your terminal"; \
		exit 1; \
	else \
		echo "✅ Poetry found: $$($(POETRY) --version)"; \
		echo "📍 Location: $$(command -v $(POETRY))"; \
	fi

# Setup targets
install: check-poetry
	$(POETRY) install

install-dev:
	$(POETRY) install --with dev

install-nlp:
	$(POETRY) install --with nlp

install-db:
	$(POETRY) install --with database

install-all:
	$(POETRY) install --with dev,nlp,database

clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf .ruff_cache/
	rm -rf .coverage
	rm -rf htmlcov/
	rm -rf .tox/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete

# Testing targets
test:
	$(POETRY_RUN) pytest $(TEST_DIR) -v

test-cov:
	$(POETRY_RUN) pytest $(TEST_DIR) \
		--cov=$(PACKAGE_NAME) \
		--cov-report=term-missing \
		--cov-report=html \
		--cov-report=xml \
		--cov-fail-under=90

test-cov-dev:
	$(POETRY_RUN) pytest $(TEST_DIR) \
		--cov=$(PACKAGE_NAME) \
		--cov-report=term-missing \
		--cov-report=html

test-unit:
	$(POETRY_RUN) pytest $(TEST_DIR) -v -m "unit"

test-integration:
	$(POETRY_RUN) pytest $(TEST_DIR) -v -m "integration"

test-integration-reset:
	@echo "🔄 Resetting integration test database..."
	@echo "🗑️  Dropping existing integration test database..."
	@docker exec chronovista-postgres-dev psql -U dev_user -d chronovista_dev -c "DROP DATABASE IF EXISTS chronovista_integration_test;" || \
		(echo "❌ Could not connect to development database. Make sure it's running with 'make dev-db-up'" && exit 1)
	@echo "🆕 Creating fresh integration test database..."
	@docker exec chronovista-postgres-dev psql -U dev_user -d chronovista_dev -c "CREATE DATABASE chronovista_integration_test;"
	@echo "📋 Running migrations on integration test database..."
	@$(POETRY_RUN) alembic -x database_url="postgresql://dev_user:dev_password@localhost:5434/chronovista_integration_test" upgrade head
	@echo "✅ Integration test database reset complete!"
	@echo "🔗 Database: chronovista_integration_test"
	@echo "💡 Run 'make test-integration' to run integration tests"

test-watch:
	$(POETRY_RUN) pytest $(TEST_DIR) -v --tb=short -x -q --disable-warnings --no-header

test-fast:
	$(POETRY_RUN) pytest $(TEST_DIR) -v --tb=short -x -q --disable-warnings --no-header --no-cov

# Code quality targets
lint:
	$(POETRY_RUN) ruff check $(SRC_DIR) $(TEST_DIR)

format:
	$(POETRY_RUN) black $(SRC_DIR) $(TEST_DIR)
	$(POETRY_RUN) isort $(SRC_DIR) $(TEST_DIR)

format-check:
	$(POETRY_RUN) black --check $(SRC_DIR) $(TEST_DIR)
	$(POETRY_RUN) isort --check-only $(SRC_DIR) $(TEST_DIR)

type-check:
	$(POETRY_RUN) mypy $(SRC_DIR)/ $(TEST_DIR)/

quality: format-check lint type-check
	@echo "✅ All quality checks passed!"

pre-commit:
	$(POETRY_RUN) pre-commit run --all-files

# Development targets
run:
	$(POETRY_RUN) $(PACKAGE_NAME) --help

run-status:
	$(POETRY_RUN) $(PACKAGE_NAME) status

run-auth:
	$(POETRY_RUN) $(PACKAGE_NAME) auth --help

run-sync:
	$(POETRY_RUN) $(PACKAGE_NAME) sync --help

shell:
	$(POETRY) shell

build:
	$(POETRY) build

# Database targets
db-upgrade:
	$(POETRY_RUN) alembic upgrade head

db-downgrade:
	$(POETRY_RUN) alembic downgrade -1

db-revision:
	@read -p "Enter migration message: " msg; \
	$(POETRY_RUN) alembic revision --autogenerate -m "$$msg"

db-reset:
	$(POETRY_RUN) alembic downgrade base
	$(POETRY_RUN) alembic upgrade head

# Docker Development Database targets
dev-db-up:
	@echo "🐳 Starting development database..."
	docker compose -f docker-compose.dev.yml up -d postgres-dev
	@echo "⏳ Waiting for database to be ready..."
	@until docker compose -f docker-compose.dev.yml exec postgres-dev pg_isready -U dev_user -d chronovista_dev; do \
		echo "Database is starting..."; \
		sleep 2; \
	done
	@echo "✅ Development database is ready!"
	@echo "🔗 Connection: postgresql://dev_user:dev_password@localhost:5434/chronovista_dev"

dev-db-down:
	@echo "🛑 Stopping development database..."
	docker compose -f docker-compose.dev.yml down
	@echo "✅ Development database stopped!"

dev-db-reset:
	@echo "🔄 Resetting development database (destroying all data)..."
	docker compose -f docker-compose.dev.yml down -v
	docker compose -f docker-compose.dev.yml up -d postgres-dev
	@echo "⏳ Waiting for database to be ready..."
	@until docker compose -f docker-compose.dev.yml exec postgres-dev pg_isready -U dev_user -d chronovista_dev; do \
		echo "Database is resetting..."; \
		sleep 2; \
	done
	@echo "🗄️ Running database migrations..."
	alembic upgrade head
	@echo "✅ Development database reset complete!"

dev-db-logs:
	@echo "📋 Development database logs:"
	docker compose -f docker-compose.dev.yml logs -f postgres-dev

dev-db-shell:
	@echo "🔗 Opening development database shell..."
	docker compose -f docker-compose.dev.yml exec postgres-dev psql -U dev_user -d chronovista_dev

dev-db-admin:
	@echo "🐳 Starting pgAdmin for development database..."
	docker compose -f docker-compose.dev.yml --profile admin up -d
	@echo "⏳ Waiting for pgAdmin to be ready..."
	@sleep 5
	@echo "✅ pgAdmin is ready!"
	@echo "🌐 Open: http://localhost:8081"
	@echo "📧 Email: dev@example.com"
	@echo "🔑 Password: dev_password"

dev-db-admin-down:
	@echo "🛑 Stopping pgAdmin..."
	docker compose -f docker-compose.dev.yml --profile admin down

# Development database migrations (using alembic-dev.ini)
dev-migrate:
	@echo "📦 Running migrations on development database..."
	$(POETRY_RUN) alembic -c alembic-dev.ini upgrade head
	@echo "✅ Development database migrations complete!"

dev-revision:
	@echo "📝 Creating new migration using development database..."
	@read -p "Enter migration message: " msg; \
	$(POETRY_RUN) alembic -c alembic-dev.ini revision --autogenerate -m "$$msg"
	@echo "✅ Migration created! Review the generated file before committing."

dev-db-status:
	@echo "📊 Development database status:"
	@if docker compose -f docker-compose.dev.yml ps postgres-dev | grep -q "Up"; then \
		echo "✅ Development database is running"; \
		echo "🔗 Connection: postgresql://dev_user:dev_password@localhost:5434/chronovista_dev"; \
		$(POETRY_RUN) alembic -c alembic-dev.ini current; \
	else \
		echo "❌ Development database is not running"; \
		echo "💡 Run 'make dev-db-up' to start it"; \
	fi

# Development workflow combining database and application
dev-full-setup: dev-db-up dev-migrate
	@echo "📦 Setting up integration test database..."
	@$(POETRY_RUN) alembic -x database_url="postgresql://dev_user:dev_password@localhost:5434/chronovista_integration_test" upgrade head
	@echo ""
	@echo "🚀 Full development environment ready!"
	@echo "🔗 Dev database: postgresql://dev_user:dev_password@localhost:5434/chronovista_dev"
	@echo "🧪 Test database: postgresql://dev_user:dev_password@localhost:5434/chronovista_integration_test"
	@echo "💡 Run 'make test' to run all tests including integration tests"
	@echo "💡 Run 'make dev-db-admin' to open pgAdmin"

dev-full-reset: dev-db-reset dev-migrate
	@echo "📦 Resetting integration test database..."
	@docker exec chronovista-postgres-dev psql -U dev_user -d postgres -c "DROP DATABASE IF EXISTS chronovista_integration_test;" 2>/dev/null || true
	@docker exec chronovista-postgres-dev psql -U dev_user -d postgres -c "CREATE DATABASE chronovista_integration_test;" 2>/dev/null || true
	@$(POETRY_RUN) alembic -x database_url="postgresql://dev_user:dev_password@localhost:5434/chronovista_integration_test" upgrade head
	@echo "🔄 Full development environment reset complete!"
	@echo "🔗 Dev database: postgresql://dev_user:dev_password@localhost:5434/chronovista_dev"
	@echo "🧪 Test database: postgresql://dev_user:dev_password@localhost:5434/chronovista_integration_test"

# Test database models
test-models:
	@echo "🧪 Testing database models..."
	@echo "💡 Use: DEVELOPMENT_MODE=true make test-models (for development database)"
	python scripts/test_models.py

test-models-dev:
	@echo "🧪 Testing database models with development database..."
	DEVELOPMENT_MODE=true python scripts/test_models.py

validate-schema:
	@echo "🔍 Validating database schema with real YouTube API data..."
	@echo "💡 This will use your development database and real YouTube API data"
	@echo "📋 Make sure you're authenticated: poetry run chronovista auth login"
	@echo ""
	DEVELOPMENT_MODE=true $(POETRY_RUN) python scripts/validate_database_schema.py

validate-schema-takeout:
	@echo "🔍 Enhanced validation using Takeout data + YouTube API..."
	@echo "💡 This combines your Google Takeout data with YouTube API data"
	@echo "📋 Make sure you're authenticated: poetry run chronovista auth login"
	@echo "📊 Using recommended channels from Takeout analysis"
	@echo ""
	DEVELOPMENT_MODE=true $(POETRY_RUN) python scripts/validate_schema_with_takeout.py

# Documentation targets
install-docs:
	@echo "📚 Installing documentation dependencies..."
	$(POETRY) install --with docs
	@echo "✅ Documentation dependencies installed!"

docs-serve:
	@echo "📚 Starting documentation server..."
	@echo "🌐 Open http://localhost:8000 in your browser"
	$(POETRY_RUN) mkdocs serve

docs-build:
	@echo "📚 Building documentation..."
	$(POETRY_RUN) mkdocs build --strict
	@echo "✅ Documentation built in site/ directory"

docs-deploy:
	@echo "📚 Deploying documentation to GitHub Pages..."
	$(POETRY_RUN) mike deploy --push --update-aliases $$($(POETRY) version -s) latest
	@echo "✅ Documentation deployed!"

docs-clean:
	@echo "🧹 Cleaning documentation build..."
	rm -rf site/
	@echo "✅ Documentation build cleaned!"

# Alias for backward compatibility
docs: docs-serve
serve-docs: docs-serve

# Development workflow targets
dev-setup: install-dev
	$(POETRY_RUN) pre-commit install
	@echo "🚀 Development environment setup complete!"

dev-check: format lint type-check test-cov
	@echo "✅ Development checks complete!"

dev-clean: clean
	$(POETRY) env remove python
	@echo "🧹 Development environment cleaned!"

# CI/CD targets
ci-test:
	$(POETRY_RUN) pytest $(TEST_DIR) \
		--cov=$(PACKAGE_NAME) \
		--cov-report=xml \
		--cov-report=term \
		--cov-fail-under=90 \
		--tb=short

ci-quality:
	$(POETRY_RUN) ruff check $(SRC_DIR) $(TEST_DIR) --output-format=github
	$(POETRY_RUN) black --check $(SRC_DIR) $(TEST_DIR)
	$(POETRY_RUN) isort --check-only $(SRC_DIR) $(TEST_DIR)
	$(POETRY_RUN) mypy $(SRC_DIR)

ci: ci-quality ci-test
	@echo "✅ CI checks complete!"

# Release targets
release-check:
	$(POETRY) check
	$(POETRY) build
	$(POETRY_RUN) twine check dist/*

release-test:
	$(POETRY) publish --repository testpypi

release:
	$(POETRY) publish

# Quick development commands
quick-test:
	$(POETRY_RUN) pytest $(TEST_DIR) -x -q --disable-warnings --no-header

quick-check:
	$(POETRY_RUN) black --check $(SRC_DIR)
	$(POETRY_RUN) ruff check $(SRC_DIR) --quiet

# Show project info
info:
	@echo "Project: $(PACKAGE_NAME)"
	@echo "Poetry version: $(shell $(POETRY) --version)"
	@echo "Python version: $(shell $(POETRY_RUN) python --version)"
	@echo "Virtual environment: $(shell $(POETRY) env info --path)"
	@echo "Source: $(SRC_DIR)"
	@echo "Tests: $(TEST_DIR)"
	@echo "Dependencies status:"
	@$(POETRY) show --tree --only main
	@echo "Coverage threshold: 90%"

# Environment management
env-info:
	$(POETRY) env info

env-list:
	$(POETRY) env list

env-remove:
	$(POETRY) env remove python

# Dependency management
deps-show:
	$(POETRY) show

deps-show-tree:
	$(POETRY) show --tree

deps-outdated:
	$(POETRY) show --outdated

deps-update:
	$(POETRY) update

deps-lock:
	$(POETRY) lock

# Export for compatibility
export-requirements:
	$(POETRY) export -f requirements.txt --output requirements.txt
	$(POETRY) export -f requirements.txt --with dev --output requirements-dev.txt

# =============================================================================
# Frontend Development (Feature 014)
# =============================================================================

# Frontend API Generation
# NOTE: Requires backend to be running on port 8765 before execution
# Start with: make dev-backend (in separate terminal) OR make dev
generate-api:
	@echo "Exporting OpenAPI spec..."
	@echo "NOTE: Backend must be running on port 8765"
	curl -s http://localhost:8765/openapi.json > contracts/openapi.json
	@echo "Generating TypeScript client..."
	cd frontend && npm run generate-api
	@echo "API client generated successfully!"

# Development Servers
# Starts both backend (8765) and frontend (8766) with hot reload
# Press Ctrl+C to stop both servers gracefully
dev:
	@echo "Starting backend and frontend development servers..."
	@echo "Backend: http://localhost:8765"
	@echo "Frontend: http://localhost:8766"
	@echo "Press Ctrl+C to stop both servers"
	@trap 'kill 0' EXIT; \
	$(MAKE) dev-backend & \
	$(MAKE) dev-frontend & \
	wait

# Backend development server (port 8765)
# Supports hot reload via uvicorn --reload
dev-backend:
	CHRONOVISTA_API_PORT=8765 $(POETRY_RUN) uvicorn chronovista.api.main:app --host localhost --port 8765 --reload

# Frontend development server (port 8766)
# Uses Vite dev server with hot module replacement
dev-frontend:
	cd frontend && npm run dev

# Verification Commands (for manual testing)
# - TypeScript type check: cd frontend && npm run typecheck
# - Hot reload: Modify a .tsx file and observe browser auto-refresh
# - Graceful shutdown: Press Ctrl+C when running 'make dev'

# =============================================================================
# Docker Full-Stack (Feature 047)
# =============================================================================
# Uses docker-compose.yml (production-like: app + postgres)
# Separate from docker-compose.dev.yml (dev postgres only)

APP_PORT ?= 8765
HEALTH_URL = http://localhost:$(APP_PORT)/api/v1/health

# First-time setup: validate, build, start, health check
docker-setup:
	@echo "=== Chronovista Docker Setup ==="
	@echo ""
	@# Check Docker
	@command -v docker >/dev/null 2>&1 || { echo "Docker is not installed. Install from https://docker.com"; exit 1; }
	@echo "[OK] Docker is installed ($$(docker --version))"
	@# Check Docker Compose
	@docker compose version >/dev/null 2>&1 || { echo "Docker Compose is not available."; exit 1; }
	@echo "[OK] Docker Compose is available"
	@# Check daemon
	@docker info >/dev/null 2>&1 || { echo "Docker daemon is not running. Start Docker Desktop."; exit 1; }
	@echo "[OK] Docker daemon is running"
	@# Check .env
	@test -f .env || { echo ".env file not found. Copy from .env.example and fill in credentials."; exit 1; }
	@echo "[OK] .env file found"
	@# Check OAuth token
	@if [ -f data/youtube_token.json ]; then \
		echo "[OK] OAuth token found"; \
	else \
		echo "[WARN] No OAuth token in ./data/youtube_token.json"; \
		echo "       Run: chronovista auth login"; \
		echo "       (required for Enrich Metadata step)"; \
	fi
	@echo ""
	@echo "Building image..."
	docker compose build
	@echo ""
	@echo "Starting stack..."
	docker compose up -d
	@echo ""
	@echo "Waiting for health check..."
	@for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30; do \
		if curl -sf $(HEALTH_URL) >/dev/null 2>&1; then \
			echo "[OK] Chronovista is running at http://localhost:$(APP_PORT)"; \
			echo ""; \
			echo "Open http://localhost:$(APP_PORT)/onboarding to begin."; \
			exit 0; \
		fi; \
		sleep 2; \
	done; \
	echo "Health check timed out. Check logs: make docker-logs"; \
	exit 1

# Build the Docker image
docker-build:
	docker compose build

# Start the full stack
docker-up:
	docker compose up -d
	@echo "Stack started. Open http://localhost:$(APP_PORT)/onboarding"

# Stop the full stack
docker-down:
	docker compose down

# Restart the full stack
docker-restart:
	docker compose down
	docker compose up -d
	@echo "Stack restarted. Open http://localhost:$(APP_PORT)/onboarding"

# Stream app container logs
docker-logs:
	docker compose logs -f app

# Show container status
docker-status:
	@docker compose ps
	@echo ""
	@if curl -sf $(HEALTH_URL) >/dev/null 2>&1; then \
		echo "Health: OK"; \
	else \
		echo "Health: UNREACHABLE"; \
	fi

# Open bash shell in app container
docker-shell:
	docker compose exec app bash

# Open psql shell in Docker postgres
docker-db-shell:
	docker compose exec postgres psql -U $${DB_USER:-chronovista} -d chronovista

# Stop stack and remove volumes (DESTROYS database data)
docker-clean:
	@echo "This will destroy all Docker database data."
	@read -p "Are you sure? [y/N] " confirm; \
	if [ "$$confirm" = "y" ] || [ "$$confirm" = "Y" ]; then \
		docker compose down -v; \
		echo "Stack stopped and volumes removed."; \
	else \
		echo "Cancelled."; \
	fi