# Contributing

Thank you for your interest in contributing to chronovista!

## Quick Start

```bash
# Fork and clone
git clone https://github.com/YOUR_USERNAME/chronovista.git
cd chronovista

# Setup development environment
poetry install --with dev
poetry run pre-commit install

# Create feature branch
git checkout -b feature/your-feature

# Make changes, then reproduce CI locally before pushing
make pre-push

# Submit pull request
```

## Development Process

### 1. Find an Issue

- Check [GitHub Issues](https://github.com/chronovista/chronovista/issues)
- Look for `good first issue` label
- Comment to claim an issue

### 2. Setup Environment

See [Development Setup](development/setup.md) for detailed instructions.

### 3. Make Changes

- Follow [Code Style](development/code-style.md)
- Write tests for new features
- Update documentation

### 4. Test Your Changes

```bash
# Reproduce every CI job locally, in CI's order, stopping at the first failure
make pre-push
```

This mirrors `.github/workflows/test.yml` step for step: ruff, black, mypy
`--strict`, backend unit tests, frontend type check and tests, and backend
integration tests. A green run here is the closest thing to a guarantee that CI
will agree. It needs the development database running (`make dev-db-up`) and
fails rather than skipping if it is not — a skipped job cannot tell you anything.

Prefer it over running the individual targets by hand: a mistyped flag in a
hand-run `pytest` can report success having collected no tests at all.
`make quality` runs the same three static checks as CI, but not the test jobs.

While iterating, the narrower targets are still useful:

```bash
make format       # Apply black + ruff import sorting
make lint         # ruff only
make type-check   # mypy --strict on src, as CI runs it
make test-cov     # Full suite with the 90% coverage threshold
```

### 5. Submit Pull Request

- Create PR against `master` branch
- Fill out PR template
- Link related issues

## Code Standards

### Required

- 90%+ test coverage
- mypy strict compliance
- Black formatting
- NumPy docstrings

### Guidelines

- One feature per PR
- Descriptive commit messages
- Update changelog for user-facing changes

## Types of Contributions

### Bug Reports

- Use bug report template
- Include reproduction steps
- Provide environment details

### Feature Requests

- Use feature request template
- Explain use case
- Discuss before implementing large features

### Documentation

- Fix typos and unclear sections
- Add examples
- Improve API docs

### Code

- Bug fixes
- New features
- Performance improvements
- Test coverage

## Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add transcript download command
fix: handle missing channel gracefully
docs: update installation guide
refactor: simplify video repository
test: add integration tests for topics
```

## Pull Request Process

1. Create feature branch
2. Make changes
3. Run quality checks
4. Push and create PR
5. Address review feedback
6. Maintainer merges

## Code Review

All contributions require review:

- At least one approval needed
- All CI checks must pass
- Maintainer has final say

## License

By contributing, you agree that your contributions will be licensed under the AGPL-3.0 license.

## Questions?

- Open a [Discussion](https://github.com/chronovista/chronovista/discussions)
- Check existing documentation
- Ask in PR comments

## Thank You!

Every contribution helps make chronovista better.
