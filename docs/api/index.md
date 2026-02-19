# API Reference

Comprehensive API documentation for chronovista.

## Overview

This section contains detailed API documentation for all chronovista modules, generated from source code docstrings.

## REST API

chronovista provides a RESTful HTTP API for programmatic access.

### Starting the Server

```bash
chronovista api start --port 8000
```

### Base URL

```
http://localhost:8000/api/v1/
```

### Authentication

All endpoints except `/health` require authentication. The API shares OAuth tokens with the CLI.

### Endpoints Overview

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check (no auth) |
| `/videos` | GET | List videos |
| `/videos/{id}` | GET | Get video details |
| `/videos/{id}/transcript` | GET | Get transcript |
| `/videos/{id}/transcript/segments` | GET | Paginated segments |
| `/videos/{id}/transcript/languages` | GET | Available languages |
| `/channels` | GET | List channels |
| `/channels/{id}` | GET | Get channel details |
| `/channels/{id}/videos` | GET | Videos by channel |
| `/playlists` | GET | List playlists |
| `/playlists/{id}` | GET | Get playlist details |
| `/playlists/{id}/videos` | GET | Videos in playlist |
| `/topics` | GET | List topics |
| `/topics/{id}` | GET | Get topic details |
| `/topics/{id}/videos` | GET | Videos by topic |
| `/categories` | GET | List categories |
| `/categories/{id}` | GET | Get category details |
| `/categories/{id}/videos` | GET | Videos in category |
| `/tags` | GET | List tags |
| `/tags/{tag}` | GET | Get tag details |
| `/tags/{tag}/videos` | GET | Videos with tag |
| `/search/segments` | GET | Search transcripts |
| `/preferences/languages` | GET, PUT | Language preferences |
| `/sync/{operation}` | POST | Trigger sync |
| `/sync/status` | GET | Sync status |
| `/videos/{id}/recover` | POST | Recover video metadata via Wayback Machine |
| `/channels/{id}/recover` | POST | Recover channel metadata via Wayback Machine |

### Interactive Documentation

- Swagger UI: `/docs`
- ReDoc: `/redoc`
- OpenAPI JSON: `/openapi.json`

For detailed usage, see [REST API User Guide](../user-guide/rest-api.md).

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

The API uses [RFC 7807 Problem Details](https://www.rfc-editor.org/rfc/rfc7807) for all error responses:

- [Error Responses](error-responses.md) - Complete RFC 7807 format reference
- [Migration Guide](rfc7807-migration.md) - Migrating from legacy error format

All error responses include:

- `Content-Type: application/problem+json`
- `X-Request-ID` header for request correlation
- Structured error body with `type`, `title`, `status`, `detail`, `code`, and `request_id`

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
