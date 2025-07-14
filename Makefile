# Makefile for chronovista development (Poetry-based)
.PHONY: help install install-dev clean test test-cov test-unit test-integration lint format type-check quality pre-commit run build docs serve-docs

# Default target
help:
	@echo "Available targets:"
	@echo "  help           - Show this help message"
	@echo "  check-poetry   - Verify Poetry installation and PATH"
	@echo ""
	@echo "Setup:"
	@echo "  install        - Install project in development mode"
	@echo "  install-dev    - Install development dependencies"
	@echo "  install-nlp    - Install NLP dependencies"
	@echo "  install-db     - Install database dependencies"
	@echo "  clean          - Clean build artifacts and cache"
	@echo ""
	@echo "Testing:"
	@echo "  test           - Run all tests"
	@echo "  test-cov       - Run tests with coverage report"
	@echo "  test-unit      - Run unit tests only"
	@echo "  test-integration - Run integration tests only"
	@echo "  test-watch     - Run tests in watch mode"
	@echo ""
	@echo "Code Quality:"
	@echo "  lint           - Run linting (ruff)"
	@echo "  format         - Format code (black + isort)"
	@echo "  type-check     - Run type checking (mypy)"
	@echo "  quality        - Run all quality checks"
	@echo "  pre-commit     - Run pre-commit hooks"
	@echo ""
	@echo "Development:"
	@echo "  run            - Run the CLI application"
	@echo "  build          - Build the package"
	@echo "  serve-docs     - Serve documentation locally"
	@echo "  shell          - Enter Poetry shell"
	@echo ""
	@echo "Database:"
	@echo "  db-upgrade     - Run database migrations"
	@echo "  db-downgrade   - Rollback database migrations"
	@echo "  db-revision    - Create new database migration"

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
	$(POETRY_RUN) mypy $(SRC_DIR)

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

# Documentation targets
docs:
	@echo "📚 Documentation targets not yet implemented"

serve-docs:
	@echo "📚 Documentation server not yet implemented"

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