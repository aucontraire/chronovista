# Testing Guide

Comprehensive testing documentation for chronovista.

## Overview

chronovista maintains **90%+ test coverage** with:

- Unit tests for all modules
- Integration tests with real YouTube API
- Property-based testing with Hypothesis
- Factory-based test data generation

## Running Tests

### Quick Commands

```bash
# All tests
make test

# With coverage report
make test-cov

# Fast run (no coverage)
make test-fast

# Watch mode
make test-watch
```

### Specific Tests

```bash
# Unit tests only
make test-unit

# Integration tests only
make test-integration

# Single file
poetry run pytest tests/unit/test_video.py -v

# Single test
poetry run pytest tests/unit/test_video.py::TestVideo::test_create -v
```

## Test Organization

```
tests/
|-- unit/                    # Unit tests
|   |-- models/             # Model tests
|   |-- repositories/       # Repository tests
|   |-- services/           # Service tests
|   |-- cli/                # CLI tests
|-- integration/             # Integration tests
|   |-- api/                # API integration
|       |-- test_tier1_independent.py
|       |-- test_tier2_channel_deps.py
|       |-- test_tier3_video_core.py
|       |-- test_tier4_video_deps.py
|-- conftest.py              # Shared fixtures
```

## Writing Tests

### Unit Test Example

```python
import pytest
from chronovista.models import Video

class TestVideo:
    def test_create_valid_video(self):
        video = Video(
            video_id="dQw4w9WgXcQ",
            channel_id="UCuAXFkgsw1L7xaCfnd5JJOw",
            title="Test Video",
            duration=213,
        )
        assert video.video_id == "dQw4w9WgXcQ"

    def test_invalid_video_id_raises(self):
        with pytest.raises(ValidationError):
            Video(video_id="", ...)
```

### Async Test Example

```python
import pytest

pytestmark = pytest.mark.asyncio

class TestVideoRepository:
    async def test_save_and_find(self, session):
        repo = VideoRepository(session)
        video = VideoFactory.build()

        await repo.save(video)
        found = await repo.find_by_id(video.video_id)

        assert found is not None
        assert found.title == video.title
```

### Factory Usage

```python
from tests.factories import VideoFactory, ChannelFactory

# Create single instance
video = VideoFactory.build()

# Create with overrides
video = VideoFactory.build(title="Custom Title")

# Create batch
videos = VideoFactory.build_batch(10)
```

## Integration Tests

### Tier Architecture

Integration tests follow dependency tiers:

| Tier | Models | Dependencies |
|------|--------|--------------|
| 1 | Channel, UserLanguagePreference, TopicCategory | None |
| 2 | ChannelKeyword, Playlist | Channel |
| 3 | Video, VideoStatistics | Channel |
| 4 | VideoTranscript, VideoTag, UserVideo | Video |

### Integration Test Setup Checklist

Before running integration tests, ensure all prerequisites are met:

- [ ] Docker is running (`docker ps`)
- [ ] Development database is up (`make dev-db-up`)
- [ ] Full setup has been run (`make dev-full-setup`) — this creates both the dev and integration test databases
- [ ] YouTube API authentication is complete (`poetry run chronovista auth login`)

### Running Integration Tests

```bash
# One-time setup (creates dev + integration databases, runs migrations)
make dev-full-setup

# Authenticate (one-time, tokens persist)
poetry run chronovista auth login

# Run integration tests
make test-integration

# Reset integration database if needed
make test-integration-reset
```

## Coverage

### Viewing Coverage

```bash
# Terminal report
make test-cov

# HTML report
open htmlcov/index.html
```

### Coverage Requirements

- Minimum: 90%
- Excluded:
  - `__main__.py`
  - `conftest.py`
  - Abstract methods
  - Type hints

## Property-Based Testing

Using Hypothesis for edge cases:

```python
from hypothesis import given, strategies as st

class TestVideoId:
    @given(st.text(min_size=11, max_size=11))
    def test_valid_length_video_ids(self, video_id):
        # Property: all 11-char strings should be processable
        result = validate_video_id(video_id)
        assert isinstance(result, bool)
```

## Mocking

### Mock YouTube API

```python
from unittest.mock import AsyncMock, patch

async def test_sync_with_mock():
    mock_api = AsyncMock()
    mock_api.get_video.return_value = VideoFactory.build()

    service = SyncService(youtube_api=mock_api)
    result = await service.sync_video("abc123")

    mock_api.get_video.assert_called_once_with("abc123")
```

### Mock Database

```python
@pytest.fixture
async def mock_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSession(engine) as session:
        yield session
```

## Best Practices

### Test Naming

```python
def test_<method>_<scenario>_<expected_result>():
    ...

# Examples:
def test_save_valid_video_succeeds():
def test_save_duplicate_raises_error():
def test_find_nonexistent_returns_none():
```

### Arrange-Act-Assert

```python
def test_example():
    # Arrange
    video = VideoFactory.build()
    repo = VideoRepository()

    # Act
    result = repo.validate(video)

    # Assert
    assert result is True
```

### Isolation

Each test should be independent:

```python
@pytest.fixture
async def clean_database(session):
    yield session
    # Cleanup after test
    await session.execute("TRUNCATE videos CASCADE")
```

## Debugging Tests

### Verbose Output

```bash
poetry run pytest -vvv tests/unit/test_video.py
```

### Drop into Debugger

```bash
poetry run pytest --pdb tests/unit/test_video.py
```

### Show Print Statements

```bash
poetry run pytest -s tests/unit/test_video.py
```

## Frontend Tests

The frontend has 1,400+ tests using vitest and React Testing Library. See [Frontend Development](frontend-development.md) for details.

```bash
cd frontend
npm test              # Run all tests
npm run test:coverage # Run with coverage report
```

## See Also

- [Setup](setup.md) - Development environment
- [Database](database.md) - Test database setup
- [Code Style](code-style.md) - Test code style
- [Frontend Development](frontend-development.md) - Frontend testing
