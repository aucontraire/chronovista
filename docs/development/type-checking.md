# Type Checking

mypy strict mode configuration and best practices.

## Overview

chronovista uses mypy in strict mode for complete type safety.

## Running Type Checks

```bash
# Full type check
make type-check

# Specific module
poetry run mypy src/chronovista/models/
```

## Configuration

From `pyproject.toml`:

```toml
[tool.mypy]
python_version = "3.11"
mypy_path = "src"
strict = true
plugins = ["pydantic.mypy"]

[tool.pydantic-mypy]
init_forbid_extra = true
init_typed = true
warn_required_dynamic_aliases = true
```

## Strict Mode Settings

| Setting | Description |
|---------|-------------|
| `disallow_untyped_defs` | All functions must have type hints |
| `disallow_any_generics` | No `List` without type parameter |
| `no_implicit_optional` | Explicit `Optional[T]` required |
| `warn_return_any` | Warn on returning `Any` |
| `strict_equality` | Strict equality checks |

## Common Patterns

### Function Signatures

```python
# Good
def get_video(video_id: str) -> Video | None:
    ...

# Bad - missing types
def get_video(video_id):
    ...
```

### Optional Values

```python
# Good
def process(value: str | None = None) -> None:
    if value is not None:
        print(value.upper())

# Bad - implicit optional
def process(value: str = None):
    ...
```

### Generic Types

```python
# Good
from typing import List, Dict

videos: List[Video] = []
cache: Dict[str, Video] = {}

# Bad - missing type parameters
videos: list = []
```

### Async Functions

```python
# Good
async def fetch_video(video_id: str) -> Video:
    ...

# Return type for coroutines
from typing import Coroutine

def get_coro() -> Coroutine[Any, Any, Video]:
    return fetch_video("abc")
```

## Pydantic Integration

### Model Definition

```python
from pydantic import BaseModel, Field

class Video(BaseModel):
    video_id: str
    title: str
    duration: int = Field(gt=0)
    tags: list[str] = Field(default_factory=list)
```

### Validation

```python
# mypy knows the types
video = Video(video_id="abc", title="Test", duration=100)
reveal_type(video.video_id)  # str
```

## Handling Third-Party Libraries

### Ignore Missing Imports

```toml
[[tool.mypy.overrides]]
module = ["google.auth.*", "youtube_transcript_api.*"]
ignore_missing_imports = true
```

### Type Stubs

```bash
# Install stubs
poetry run mypy --install-types

# Or manually
poetry add types-requests --group dev
```

## Test File Configuration

Less strict for test files:

```toml
[[tool.mypy.overrides]]
module = "tests.*"
disallow_untyped_defs = false
disallow_incomplete_defs = false
```

## Common Errors

### Missing Return Type

```
error: Function is missing a return type annotation
```

Fix:
```python
def my_function() -> None:
    ...
```

### Incompatible Types

```
error: Argument 1 has incompatible type "str"; expected "int"
```

Fix: Check the types match.

### Optional Access

```
error: Item "None" of "Optional[Video]" has no attribute "title"
```

Fix:
```python
if video is not None:
    print(video.title)
```

## Type Aliases

```python
from typing import TypeAlias

VideoId: TypeAlias = str
ChannelId: TypeAlias = str

def get_video(video_id: VideoId) -> Video:
    ...
```

## Protocol for Duck Typing

```python
from typing import Protocol

class Saveable(Protocol):
    async def save(self) -> None:
        ...

def persist(item: Saveable) -> None:
    await item.save()
```

## See Also

- [Code Style](code-style.md) - Formatting standards
- [Testing](testing.md) - Type checking in tests
- [Setup](setup.md) - mypy installation
