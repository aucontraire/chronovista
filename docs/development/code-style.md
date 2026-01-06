# Code Style

Formatting, linting, and code style guidelines.

## Tools

| Tool | Purpose |
|------|---------|
| Black | Code formatting |
| isort | Import sorting |
| ruff | Linting |
| mypy | Type checking |

## Quick Commands

```bash
# Format code
make format

# Check formatting
make format-check

# Lint
make lint

# All quality checks
make quality
```

## Black Configuration

```toml
[tool.black]
line-length = 88
target-version = ['py311']
```

### Usage

```bash
# Format all
poetry run black src/ tests/

# Check only
poetry run black --check src/
```

## isort Configuration

```toml
[tool.isort]
profile = "black"
multi_line_output = 3
line_length = 88
known_first_party = ["chronovista"]
```

### Import Order

```python
# Standard library
import os
import sys

# Third party
import pydantic
import sqlalchemy

# First party
from chronovista.models import Video
from chronovista.services import SyncService

# Local
from .utils import helper
```

## ruff Configuration

```toml
[tool.ruff]
target-version = "py311"
line-length = 88

[tool.ruff.lint]
select = [
    "E",   # pycodestyle errors
    "W",   # pycodestyle warnings
    "F",   # pyflakes
    "I",   # isort
    "B",   # flake8-bugbear
    "C4",  # flake8-comprehensions
    "UP",  # pyupgrade
    "N",   # pep8-naming
    "S",   # bandit
]
```

## Naming Conventions

### Files and Modules

```
# snake_case
video_repository.py
youtube_service.py
```

### Classes

```python
# PascalCase
class VideoRepository:
    ...

class YouTubeService:
    ...
```

### Functions and Variables

```python
# snake_case
def get_video_by_id(video_id: str) -> Video:
    channel_name = "example"
```

### Constants

```python
# UPPER_SNAKE_CASE
MAX_RETRIES = 3
DEFAULT_TIMEOUT = 30
```

## Docstrings

NumPy style docstrings:

```python
def extract_tags(text: str, top_k: int = 5) -> list[str]:
    """
    Extract tags from the input transcript text.

    Parameters
    ----------
    text : str
        The transcript content.
    top_k : int, optional
        The number of top tags to return (default is 5).

    Returns
    -------
    list[str]
        A list of tags extracted using NLP techniques.

    Examples
    --------
    >>> extract_tags("machine learning tutorial", top_k=3)
    ['machine learning', 'tutorial', 'ml']
    """
```

## Line Length

Maximum 88 characters (Black default).

Exception for strings that shouldn't be broken:

```python
# noqa: E501
url = "https://www.googleapis.com/youtube/v3/videos?part=snippet,contentDetails"
```

## Imports

### Absolute Imports

```python
# Good
from chronovista.models.video import Video

# Avoid
from ..models.video import Video
```

### Import What You Need

```python
# Good
from typing import Optional, List

# Avoid
from typing import *
```

## Type Hints

Always use type hints:

```python
def process_videos(
    videos: list[Video],
    filter_func: Callable[[Video], bool] | None = None,
) -> list[Video]:
    ...
```

## Error Handling

```python
# Custom exceptions with context
class VideoNotFoundError(ChronovistaError):
    def __init__(self, video_id: str):
        self.video_id = video_id
        super().__init__(f"Video not found: {video_id}")
```

## Comments

```python
# Good: Explain why
# We need to retry because the API is rate-limited
await retry_with_backoff(fetch_video)

# Bad: Explain what (code should be self-documenting)
# Increment counter by one
counter += 1
```

## Pre-commit Hooks

Automatic formatting on commit:

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/psf/black
    rev: 23.9.1
    hooks:
      - id: black

  - repo: https://github.com/pycqa/isort
    rev: 5.12.0
    hooks:
      - id: isort

  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.0.292
    hooks:
      - id: ruff
```

Install:
```bash
poetry run pre-commit install
```

## See Also

- [Type Checking](type-checking.md) - mypy configuration
- [Testing](testing.md) - Test code style
- [Setup](setup.md) - Tool installation
