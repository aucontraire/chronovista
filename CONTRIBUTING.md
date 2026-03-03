# Contributing to chronovista

Thanks for your interest in contributing! This guide covers the basics.

## Getting Started

1. Fork the repository
2. Clone your fork and install dependencies:
   ```bash
   git clone https://github.com/<your-username>/chronovista.git
   cd chronovista && poetry install --with dev
   ```
3. Set up the development database:
   ```bash
   make dev-db-up
   cp .env.example .env  # configure credentials
   make dev-migrate
   ```

## Development Workflow

1. Create a feature branch from `master`:
   ```bash
   git checkout -b feature/your-feature master
   ```
2. Make your changes
3. Run quality checks before committing:
   ```bash
   make quality    # format (black + isort) + lint (ruff) + type-check (mypy)
   make test       # run backend tests
   ```
4. Commit using [conventional commits](https://www.conventionalcommits.org/):
   - `feat:` new feature
   - `fix:` bug fix
   - `docs:` documentation only
   - `refactor:` code change that neither fixes a bug nor adds a feature
   - `test:` adding or updating tests
5. Push your branch and open a pull request against `master`

## Code Standards

- **Python 3.11+** with strict mypy type checking
- **Pydantic V2** for all structured data (never dataclasses)
- **Async by default** for I/O operations
- **NumPy-style docstrings** for public functions and classes
- **90%+ test coverage** on new code
- **black** formatting, **isort** imports, **ruff** linting

## Running Tests

```bash
make test          # all backend tests
make test-cov      # with coverage report
cd frontend && npm test   # frontend tests
```

## Project Structure

See [Architecture Overview](docs/architecture/overview.md) for how the codebase is organized.

## License

By contributing, you agree that your contributions will be licensed under the [AGPL-3.0](LICENSE) license.
