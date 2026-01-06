# Documentation Guide

Writing and maintaining chronovista documentation.

## Overview

chronovista uses [MkDocs](https://www.mkdocs.org/) with the [Material theme](https://squidfunk.github.io/mkdocs-material/) for documentation.

## Quick Start

```bash
# Install docs dependencies
poetry install --with docs

# Serve locally
make docs-serve

# Build static site
make docs-build
```

## Documentation Structure

```
docs/
|-- index.md                 # Homepage
|-- getting-started/         # Installation & setup
|-- user-guide/              # Usage documentation
|-- architecture/            # System design
|-- api/                     # API reference
|-- development/             # Contributing guide
|-- maintaining/             # Release process
|-- contributing.md          # How to contribute
|-- changelog.md             # Version history
```

## Writing Documentation

### Markdown Features

Standard markdown plus Material theme extensions:

#### Admonitions

```markdown
!!! note "Title"
    Note content here.

!!! warning
    Warning content.

!!! tip
    Helpful tip.

!!! danger
    Critical warning.
```

#### Code Blocks

```markdown
    ```python
    def example():
        return "code"
    ```

    ```bash
    make test
    ```
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

#### Tables

```markdown
| Column 1 | Column 2 |
|----------|----------|
| Value 1  | Value 2  |
```

### API Documentation

Use mkdocstrings for auto-generated API docs:

```markdown
::: chronovista.models.video
    options:
      show_source: true
      show_root_heading: true
```

### Internal Links

```markdown
[Link Text](../path/to/page.md)
[Section Link](page.md#section-id)
```

## Docstring Format

NumPy style for all public APIs:

```python
def function_name(param1: str, param2: int = 10) -> bool:
    """
    Short description of the function.

    Longer description if needed, explaining the purpose
    and behavior in more detail.

    Parameters
    ----------
    param1 : str
        Description of param1.
    param2 : int, optional
        Description of param2 (default is 10).

    Returns
    -------
    bool
        Description of return value.

    Raises
    ------
    ValueError
        When param1 is empty.

    Examples
    --------
    >>> function_name("test", 5)
    True
    """
```

## Building Documentation

### Local Development

```bash
# Start dev server with auto-reload
make docs-serve

# Open http://localhost:8000
```

### Production Build

```bash
# Build static files
make docs-build

# Output in site/ directory
```

## Configuration

From `mkdocs.yml`:

```yaml
site_name: chronovista
theme:
  name: material
  palette:
    - scheme: default
      primary: deep purple
      toggle:
        icon: material/brightness-7
    - scheme: slate
      toggle:
        icon: material/brightness-4

plugins:
  - search
  - mkdocstrings

markdown_extensions:
  - admonition
  - pymdownx.highlight
  - pymdownx.superfences
  - pymdownx.tabbed
```

## Best Practices

### Writing Style

- Use active voice
- Be concise
- Include examples
- Link to related docs

### Code Examples

- Use realistic examples
- Include expected output
- Test all code examples

### Maintenance

- Update docs with code changes
- Check links regularly
- Review before releases

## Contributing to Docs

1. Edit markdown files in `docs/`
2. Preview with `make docs-serve`
3. Submit pull request

## See Also

- [MkDocs Documentation](https://www.mkdocs.org/)
- [Material Theme](https://squidfunk.github.io/mkdocs-material/)
- [mkdocstrings](https://mkdocstrings.github.io/)
