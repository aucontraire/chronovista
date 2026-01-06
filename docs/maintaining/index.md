# Maintaining

Guide for project maintainers.

## Overview

This section covers maintenance tasks for chronovista maintainers.

## Sections

| Section | Description |
|---------|-------------|
| [Release Process](release-process.md) | How to create releases |
| [Versioning](versioning.md) | Version numbering scheme |

## Maintainer Responsibilities

- Review and merge pull requests
- Manage releases
- Update dependencies
- Monitor issues
- Maintain documentation

## Quick Commands

```bash
# Check for outdated dependencies
make deps-outdated

# Update dependencies
make deps-update

# Run full quality check
make quality

# Build package
make build
```
