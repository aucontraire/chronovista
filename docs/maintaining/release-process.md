# Release Process

How to create and publish releases.

## Prerequisites

- Maintainer access to repository
- PyPI credentials configured
- All tests passing

## Release Checklist

### 1. Prepare Release

```bash
# Ensure all tests pass
make quality
make test-cov

# Update changelog
# Edit docs/changelog.md

# Update version
poetry version <major|minor|patch>
```

### 2. Create Release Branch

```bash
git checkout -b release/v$(poetry version -s)
git add pyproject.toml docs/changelog.md
git commit -m "Release v$(poetry version -s)"
```

### 3. Build and Test

```bash
# Build package
make build

# Test package
make release-check
```

### 4. Create Pull Request

```bash
gh pr create --title "Release v$(poetry version -s)"
```

### 5. Merge and Tag

After PR is approved:

```bash
git checkout main
git pull
git tag v$(poetry version -s)
git push origin v$(poetry version -s)
```

### 6. Publish

```bash
# Test PyPI first
make release-test

# Production PyPI
make release
```

## Version Numbering

See [Versioning](versioning.md) for the version scheme.

## Changelog Format

```markdown
## [0.2.0] - 2024-01-15

### Added
- New feature description

### Changed
- Changed behavior

### Fixed
- Bug fix description

### Removed
- Removed feature
```
