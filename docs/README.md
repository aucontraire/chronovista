# Documentation Guide

This directory contains the chronovista documentation, built with MkDocs and the Material theme.

## Quick Start

```bash
# Install documentation dependencies
make install-docs

# Serve documentation locally
make docs-serve
# Open http://localhost:8000

# Build static site
make docs-build
# Output in site/
```

## Prerequisites

Documentation dependencies are installed via Poetry:

```bash
poetry install --with docs
```

Or use the Makefile target:

```bash
make install-docs
```

## Site Map

### Getting Started

- [Prerequisites](getting-started/prerequisites.md) - Python, Poetry, Docker, Node.js, Google Cloud account
- [YouTube API Setup](getting-started/youtube-api-setup.md) - Google Cloud project, OAuth consent screen, API key, credentials
- [Installation](getting-started/installation.md) - Install chronovista from source
- [Quick Start](getting-started/quickstart.md) - Get running in minutes with a smoke test
- [Configuration](getting-started/configuration.md) - All environment variables and config options

### User Guide

- [CLI Overview](user-guide/cli-overview.md) - Complete CLI command reference
- [Authentication](user-guide/authentication.md) - OAuth 2.0 flow and token management
- [Data Population](user-guide/data-population.md) - Recommended sync order (topics, takeout, sync, transcripts)
- [Data Synchronization](user-guide/data-sync.md) - Sync commands, strategies, rate limiting
- [Google Takeout](user-guide/google-takeout.md) - Import historical YouTube data
- [Topic Analytics](user-guide/topic-analytics.md) - 17 topic commands for content discovery
- [Transcripts](user-guide/transcripts.md) - Multi-language transcript management
- [Exporting Data](user-guide/exporting.md) - CSV/JSON export with filtering
- [REST API](user-guide/rest-api.md) - FastAPI endpoints and usage examples

Recovery commands are documented in the [CLI Overview](user-guide/cli-overview.md#recover-commands) under the Recover Commands section.

### Architecture

- [Overview](architecture/overview.md) - High-level system architecture
- [System Design](architecture/system-design.md) - Service layer, rate limiting, error handling
- [Data Model](architecture/data-model.md) - Database schema, ER diagram, indexes
- [API Integration](architecture/api-integration.md) - YouTube API integration details
- [Frontend Architecture](architecture/frontend-architecture.md) - React components, routing, state management

### API Reference

- [Overview](api/index.md) - Auto-generated API reference
- Models: [Channel](api/models/channel.md), [Video](api/models/video.md), [Transcript](api/models/transcript.md), [Topic](api/models/topic.md)
- Repositories: [Base](api/repositories/base.md), [Channel](api/repositories/channel.md), [Video](api/repositories/video.md)
- Services: [YouTube](api/services/youtube.md), [Takeout](api/services/takeout.md), [Transcript](api/services/transcript.md)
- CLI: [Commands](api/cli/commands.md)

### Development

- [Setup](development/setup.md) - Development environment setup
- [Testing](development/testing.md) - Backend test suite (pytest, Hypothesis, factories)
- [Database](development/database.md) - Docker dev database, migrations, pgAdmin
- [Frontend Development](development/frontend-development.md) - Frontend tests (vitest), scripts, patterns
- [Makefile Reference](development/makefile-reference.md) - All 67 Makefile targets
- [Type Checking](development/type-checking.md) - mypy strict mode guide
- [Code Style](development/code-style.md) - Black, isort, ruff conventions
- [Documentation](development/documentation.md) - Writing and building docs

### Maintaining

- [Release Process](maintaining/release-process.md) - How to cut a release
- [Versioning](maintaining/versioning.md) - Versioning policy

### Reference

- [Troubleshooting](troubleshooting.md) - Common issues and fixes across all subsystems
- [Glossary](glossary.md) - Project-specific terminology
- [Contributing](contributing.md) - Contribution guidelines
- [Changelog](changelog.md) - Version history

## Available Commands

| Command | Description |
|---------|-------------|
| `make docs-serve` | Start local dev server with auto-reload |
| `make docs-build` | Build static site to `site/` |
| `make docs-deploy` | Deploy to GitHub Pages via mike |
| `make docs-clean` | Remove built files |
| `make install-docs` | Install documentation dependencies |

## Writing Documentation

### Markdown Extensions

The documentation supports these extensions:

- **Admonitions** - Note, warning, tip, danger blocks
- **Code blocks** - Syntax highlighting with copy button
- **Tabs** - Content tabs for multiple examples
- **Tables** - GitHub-flavored tables
- **Task lists** - Checkbox lists
- **Mermaid** - Diagrams in markdown

### Examples

#### Admonitions

```markdown
!!! note "Title"
    Note content

!!! warning
    Warning content

!!! tip
    Helpful tip
```

#### Tabs

```markdown
=== "Python"
    ```python
    print("Hello")
    ```

=== "Bash"
    ```bash
    echo "Hello"
    ```
```

#### API Documentation

Auto-generated from docstrings:

```markdown
::: chronovista.models.video
    options:
      show_source: true
```

## Configuration

The documentation is configured in `mkdocs.yml` at the project root.

Key settings:

- **Theme**: Material for MkDocs with dark/light toggle
- **Plugins**: search, mkdocstrings for API docs
- **Navigation**: Defined in nav section

## Building for Production

```bash
# Build with strict mode (fails on warnings)
make docs-build

# Output is in site/
ls site/
```

## Deploying

Using mike for versioned documentation:

```bash
# Deploy current version
make docs-deploy

# This pushes to gh-pages branch
```

## Troubleshooting

### Missing Dependencies

```bash
make install-docs
# or
poetry install --with docs
```

### Build Errors

```bash
# Check for issues
poetry run mkdocs build --strict

# Common issues:
# - Broken internal links
# - Missing files referenced in nav
# - Invalid markdown syntax
```

### API Docs Not Generating

Ensure the Python package is installed:

```bash
poetry install
```

## Contributing to Docs

1. Edit files in `docs/`
2. Preview with `make docs-serve`
3. Check links work
4. Submit PR

## Resources

- [MkDocs Documentation](https://www.mkdocs.org/)
- [Material Theme](https://squidfunk.github.io/mkdocs-material/)
- [mkdocstrings](https://mkdocstrings.github.io/)
