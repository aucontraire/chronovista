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

# Make changes and test
make quality
make test

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
# Run all quality checks
make quality

# Run tests with coverage
make test-cov
```

### 5. Submit Pull Request

- Create PR against `main` branch
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
