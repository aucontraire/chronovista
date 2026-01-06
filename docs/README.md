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

## Directory Structure

```
docs/
|-- index.md                     # Homepage
|-- getting-started/             # Installation & setup
|   |-- quickstart.md
|   |-- installation.md
|   |-- configuration.md
|-- user-guide/                  # Usage documentation
|   |-- cli-overview.md
|   |-- authentication.md
|   |-- data-sync.md
|   |-- google-takeout.md
|   |-- topic-analytics.md
|   |-- transcripts.md
|   |-- exporting.md
|-- architecture/                # System design
|   |-- overview.md
|   |-- system-design.md
|   |-- data-model.md
|   |-- api-integration.md
|-- api/                         # API reference (auto-generated)
|   |-- index.md
|   |-- models/
|   |-- repositories/
|   |-- services/
|   |-- cli/
|-- development/                 # Contributing guide
|   |-- index.md
|   |-- setup.md
|   |-- testing.md
|   |-- database.md
|   |-- type-checking.md
|   |-- code-style.md
|   |-- documentation.md
|-- maintaining/                 # Maintainer guide
|   |-- index.md
|   |-- release-process.md
|   |-- versioning.md
|-- assets/                      # Images, logos
|-- stylesheets/                 # Custom CSS
|-- contributing.md              # Contribution guidelines
|-- changelog.md                 # Version history
```

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
