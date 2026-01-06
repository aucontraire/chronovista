# API Reference

Comprehensive API documentation for chronovista.

## Overview

This section contains detailed API documentation for all chronovista modules, generated from source code docstrings.

## Module Structure

```
chronovista/
|-- models/           # Pydantic data models
|-- repositories/     # Data access layer
|-- services/         # Business logic
|-- cli/              # Command-line interface
|-- config/           # Configuration
|-- auth/             # Authentication
```

## Quick Links

### Models

- [Channel](models/channel.md) - YouTube channel entities
- [Video](models/video.md) - Video metadata and content
- [Transcript](models/transcript.md) - Multi-language transcripts
- [Topic](models/topic.md) - Topic classification

### Repositories

- [Base Repository](repositories/base.md) - Abstract repository interface
- [Channel Repository](repositories/channel.md) - Channel data access
- [Video Repository](repositories/video.md) - Video data access

### Services

- [YouTube Service](services/youtube.md) - YouTube API integration
- [Takeout Service](services/takeout.md) - Google Takeout processing
- [Transcript Service](services/transcript.md) - Transcript management

### CLI

- [Commands](cli/commands.md) - CLI command modules

## Type Safety

All APIs use strict typing with Pydantic V2:

```python
from chronovista.models import Video, Channel
from chronovista.repositories import VideoRepository

# Full type hints
async def get_video(repo: VideoRepository, video_id: str) -> Video | None:
    return await repo.find_by_id(video_id)
```

## Async Support

chronovista is async-first:

```python
async with session_factory() as session:
    repo = VideoRepository(session)
    videos = await repo.find_all()
```

## Error Handling

All APIs use typed exceptions:

```python
from chronovista.exceptions import (
    ChronovistaError,
    AuthenticationError,
    QuotaExceededError,
)

try:
    await service.sync()
except QuotaExceededError:
    logger.warning("API quota exceeded")
```
