# Development Guide

Welcome to chronovista development!

## Quick Start

```bash
# Clone repository
git clone https://github.com/chronovista/chronovista.git
cd chronovista

# Install dependencies
poetry install --with dev

# Run tests
make test

# Start developing!
```

## Development Sections

| Section | Description |
|---------|-------------|
| [Setup](setup.md) | Development environment setup |
| [Testing](testing.md) | Test suite and coverage |
| [Database](database.md) | Database development workflow |
| [Type Checking](type-checking.md) | mypy strict mode |
| [Code Style](code-style.md) | Formatting and linting |
| [Documentation](documentation.md) | Writing docs |

## Architecture

chronovista follows these principles:

- **Domain-Driven Design** - Rich domain models
- **Layered Architecture** - Clear separation of concerns
- **Repository Pattern** - Abstracted data access
- **Async-First** - All I/O operations are async
- **Type Safety** - Strict mypy, Pydantic models

## Code Quality Standards

| Metric | Target |
|--------|--------|
| Test Coverage | >= 90% |
| mypy | Strict mode |
| Black | Formatted |
| isort | Sorted imports |
| ruff | No errors |

## Quick Commands

```bash
# Quality checks
make quality          # All checks
make format           # Format code
make lint             # Linting
make type-check       # mypy

# Testing
make test             # All tests
make test-cov         # With coverage
make test-fast        # Quick run
make test-integration # Integration tests

# Database
make dev-db-up        # Start dev database
make dev-migrate      # Run migrations
make dev-db-reset     # Reset database
```

## See Also

- [Contributing](../contributing.md) - Contribution guidelines
- [Architecture](../architecture/overview.md) - System design
- [API Reference](../api/index.md) - Code documentation
