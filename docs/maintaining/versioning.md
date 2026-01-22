# Versioning

Version numbering scheme for chronovista.

## Semantic Versioning

chronovista follows [Semantic Versioning 2.0.0](https://semver.org/):

```
MAJOR.MINOR.PATCH
```

### Version Components

| Component | When to Increment |
|-----------|------------------|
| MAJOR | Breaking API changes |
| MINOR | New features (backward compatible) |
| PATCH | Bug fixes (backward compatible) |

## Pre-release Versions

For pre-release versions:

```
0.9.0-alpha.1
0.9.0-beta.1
0.9.0-rc.1
```

## Current Status

chronovista is currently at version **0.8.0** (pre-1.0), which means:

- API may change between minor versions
- Suitable for personal use and testing
- Feedback welcome

## Version Commands

```bash
# Show current version
poetry version

# Bump patch (0.8.0 -> 0.8.1)
poetry version patch

# Bump minor (0.8.0 -> 0.9.0)
poetry version minor

# Bump major (0.9.0 -> 1.0.0)
poetry version major

# Set specific version
poetry version 1.0.0
```

## Compatibility Policy

When 1.0.0 is released:

- PATCH updates are always compatible
- MINOR updates add features without breaking
- MAJOR updates may break compatibility

## Deprecation Policy

Before removing features:

1. Mark as deprecated in MINOR release
2. Document migration path
3. Remove in next MAJOR release
