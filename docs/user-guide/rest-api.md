# REST API

The REST API provides programmatic access to your chronovista data. This guide covers all available endpoints, authentication, request/response formats, and practical examples.

## Starting the Server

Start the API server using the CLI:

```bash
chronovista api start [OPTIONS]
```

### Options

| Option | Description | Default |
|--------|-------------|---------|
| `--port`, `-p` | Port to listen on | 8000 |
| `--production` | Run in production mode (multiple workers, warning-level logging) | false |

### Development Mode (Default)

```bash
# Start with auto-reload and debug logging
chronovista api start

# Start on custom port
chronovista api start --port 3000
chronovista api start -p 8080
```

### Production Mode

```bash
# Run with 2 workers and warning-level logging
chronovista api start --production

# Production on custom port
chronovista api start -p 8080 --production
```

## Authentication

The API shares authentication with the CLI:

1. **Authenticate first** via the CLI:
   ```bash
   chronovista auth login
   ```

2. **API reads tokens automatically** from the CLI's OAuth token file (`$DATA_DIR/youtube_token.json`, default `./data/`)

3. **All endpoints require authentication** except `/api/v1/health`

!!! note "Single User"
    The API currently operates in single-user mode. All requests use the authenticated CLI session.

### Authentication Errors

If not authenticated, protected endpoints return:

```json
{
  "error": {
    "code": "NOT_AUTHENTICATED",
    "message": "Not authenticated. Run: chronovista auth login"
  }
}
```

## API Documentation

Interactive documentation is available when the server is running:

| Documentation | URL |
|---------------|-----|
| Swagger UI | [http://localhost:8000/docs](http://localhost:8000/docs) |
| ReDoc | [http://localhost:8000/redoc](http://localhost:8000/redoc) |
| OpenAPI JSON | [http://localhost:8000/openapi.json](http://localhost:8000/openapi.json) |

## Response Format

All responses use a consistent envelope structure.

### Success Response (Single Item)

```json
{
  "data": {
    "video_id": "dQw4w9WgXcQ",
    "title": "Rick Astley - Never Gonna Give You Up",
    "channel_id": "UCuAXFkgsw1L7xaCfnd5JJOw",
    "...": "..."
  }
}
```

### Success Response (List with Pagination)

```json
{
  "data": [
    { "video_id": "abc123", "title": "Video 1" },
    { "video_id": "def456", "title": "Video 2" }
  ],
  "pagination": {
    "total": 150,
    "limit": 20,
    "offset": 0,
    "has_more": true
  }
}
```

### Error Response

```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "Video 'xyz789' not found. Verify the video ID or run a sync.",
    "details": {
      "resource_type": "Video",
      "identifier": "xyz789"
    }
  }
}
```

### Common Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `NOT_AUTHENTICATED` | 401 | OAuth token missing or invalid |
| `NOT_FOUND` | 404 | Resource not found |
| `VALIDATION_ERROR` | 400 | Invalid request parameters |
| `BAD_REQUEST` | 400 | Invalid request parameters |
| `MUTUALLY_EXCLUSIVE` | 400 | Both linked and unlinked filters set to true |
| `SYNC_IN_PROGRESS` | 409 | Another sync operation is running |
| `CONFLICT` | 409 | Resource conflict (e.g., recovery on available entity) |
| `INVALID_LANGUAGE_CODE` | 400 | Invalid BCP-47 language code |
| `INVALID_PREFERENCE_TYPE` | 400 | Invalid preference type |
| `SERVICE_UNAVAILABLE` | 503 | External service unavailable (e.g., Wayback Machine CDX API) |
| `SEGMENT_NOT_FOUND` | 422 | Transcript segment not found for video/language |
| `NO_CHANGE_DETECTED` | 422 | Corrected text identical to current text |
| `INVALID_CORRECTION_TYPE` | 422 | Invalid correction type (e.g., `revert` on submit endpoint) |
| `NO_ACTIVE_CORRECTION` | 422 | No active correction to revert |

## Endpoints

The full, authoritative endpoint list — every path, query/body parameter,
request and response schema, and status code — is generated from the live
OpenAPI schema rather than hand-maintained here, so it can never drift from the
running API:

- **[REST API reference](../reference/api/index.md)** — generated per-tag endpoint documentation
- **Swagger UI** at `/docs` and **ReDoc** at `/redoc` on a running server
- **OpenAPI JSON** at `/openapi.json`

Authentication and response conventions are covered above; the sections below
show worked examples (curl, Python, JavaScript) that apply across endpoints.

## Examples

### Using curl

#### Check Health

```bash
curl http://localhost:8000/api/v1/health
```

#### List Videos

```bash
# Basic list
curl http://localhost:8000/api/v1/videos

# With pagination
curl "http://localhost:8000/api/v1/videos?limit=50&offset=100"

# Filter by channel
curl "http://localhost:8000/api/v1/videos?channel_id=UCuAXFkgsw1L7xaCfnd5JJOw"

# Filter by date range
curl "http://localhost:8000/api/v1/videos?uploaded_after=2024-01-01T00:00:00Z&uploaded_before=2024-12-31T23:59:59Z"

# Only videos with transcripts
curl "http://localhost:8000/api/v1/videos?has_transcript=true"
```

#### Get Video Details

```bash
curl http://localhost:8000/api/v1/videos/dQw4w9WgXcQ
```

#### Get Transcript

```bash
# Default language (first available)
curl http://localhost:8000/api/v1/videos/dQw4w9WgXcQ/transcript

# Specific language
curl "http://localhost:8000/api/v1/videos/dQw4w9WgXcQ/transcript?language=es"
```

#### Get Transcript Segments

```bash
# All segments
curl http://localhost:8000/api/v1/videos/dQw4w9WgXcQ/transcript/segments

# Segments from 30s to 60s
curl "http://localhost:8000/api/v1/videos/dQw4w9WgXcQ/transcript/segments?start_time=30&end_time=60"
```

#### Search Transcripts

```bash
# Basic search
curl "http://localhost:8000/api/v1/search/segments?q=never%20gonna"

# Search within specific video
curl "http://localhost:8000/api/v1/search/segments?q=love&video_id=dQw4w9WgXcQ"
```

#### Get Language Preferences

```bash
curl http://localhost:8000/api/v1/preferences/languages
```

#### Update Language Preferences

```bash
curl -X PUT http://localhost:8000/api/v1/preferences/languages \
  -H "Content-Type: application/json" \
  -d '{
    "preferences": [
      {"language_code": "en", "preference_type": "fluent"},
      {"language_code": "es", "preference_type": "learning", "learning_goal": "B2 by 2027"},
      {"language_code": "ja", "preference_type": "curious"}
    ]
  }'
```

#### Trigger Sync

```bash
# Sync subscriptions
curl -X POST http://localhost:8000/api/v1/sync/subscriptions

# Sync transcripts with options
curl -X POST http://localhost:8000/api/v1/sync/transcripts \
  -H "Content-Type: application/json" \
  -d '{
    "video_ids": ["dQw4w9WgXcQ"],
    "languages": ["en", "es"],
    "force": true
  }'
```

#### Check Sync Status

```bash
curl http://localhost:8000/api/v1/sync/status
```

#### List Channels

```bash
# All channels
curl http://localhost:8000/api/v1/channels

# Only channels with videos
curl "http://localhost:8000/api/v1/channels?has_videos=true"
```

#### Get Channel Details

```bash
curl http://localhost:8000/api/v1/channels/UCuAXFkgsw1L7xaCfnd5JJOw
```

#### Get Channel Videos

```bash
curl http://localhost:8000/api/v1/channels/UCuAXFkgsw1L7xaCfnd5JJOw/videos
```

#### List Playlists

```bash
# All playlists
curl http://localhost:8000/api/v1/playlists

# Only YouTube-linked playlists
curl "http://localhost:8000/api/v1/playlists?linked=true"

# Only internal playlists
curl "http://localhost:8000/api/v1/playlists?unlinked=true"
```

#### Get Playlist Videos

```bash
curl http://localhost:8000/api/v1/playlists/PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf/videos
```

#### List Topics

```bash
curl http://localhost:8000/api/v1/topics
```

#### Get Topic Details

```bash
# Topic with slash in ID
curl http://localhost:8000/api/v1/topics//m/098wr

# Topic with alphanumeric ID
curl http://localhost:8000/api/v1/topics/wiki_Military
```

#### Get Topic Videos

```bash
curl http://localhost:8000/api/v1/topics//m/098wr/videos
```

#### List Categories

```bash
# All categories sorted by video count
curl http://localhost:8000/api/v1/categories

# With pagination
curl "http://localhost:8000/api/v1/categories?limit=10&offset=10"
```

#### Get Category Details

```bash
curl http://localhost:8000/api/v1/categories/25
```

#### Get Category Videos

```bash
curl http://localhost:8000/api/v1/categories/25/videos
```

#### List Tags

```bash
# All tags sorted by video count
curl http://localhost:8000/api/v1/tags

# With pagination
curl "http://localhost:8000/api/v1/tags?limit=50&offset=100"
```

#### Get Tag Details

```bash
# Simple tag
curl http://localhost:8000/api/v1/tags/politics

# Tag with space (URL-encoded)
curl "http://localhost:8000/api/v1/tags/hip%20hop"
```

#### Get Tag Videos

```bash
curl http://localhost:8000/api/v1/tags/news/videos
```

#### List Canonical Tags

```bash
# All canonical tags sorted by video count
curl http://localhost:8000/api/v1/canonical-tags

# Prefix search
curl "http://localhost:8000/api/v1/canonical-tags?q=mex&limit=10"

# Fuzzy suggestions (when no prefix match)
curl "http://localhost:8000/api/v1/canonical-tags?q=mexco"
```

#### Get Canonical Tag Detail

```bash
# Simple tag
curl http://localhost:8000/api/v1/canonical-tags/mexico

# Tag with spaces (URL-encoded)
curl "http://localhost:8000/api/v1/canonical-tags/new%20york"

# Limit aliases returned
curl "http://localhost:8000/api/v1/canonical-tags/mexico?alias_limit=3"
```

#### Get Canonical Tag Videos

```bash
curl http://localhost:8000/api/v1/canonical-tags/mexico/videos
```

#### Filter Videos by Canonical Tag

```bash
# Single canonical tag (returns all raw variations)
curl "http://localhost:8000/api/v1/videos?canonical_tag=mexico"

# Multiple canonical tags (AND semantics)
curl "http://localhost:8000/api/v1/videos?canonical_tag=mexico&canonical_tag=travel"

# Combined with raw tag filter
curl "http://localhost:8000/api/v1/videos?canonical_tag=gaming&tag=python"
```

#### Submit a Transcript Correction

```bash
# Submit a spelling correction
curl -X POST "http://localhost:8000/api/v1/videos/dQw4w9WgXcQ/transcript/segments/1234/corrections?language_code=en" \
  -H "Content-Type: application/json" \
  -d '{
    "corrected_text": "We'\''re no strangers to love",
    "correction_type": "spelling",
    "correction_note": "Fixed ASR typo"
  }'
```

#### Revert a Correction

```bash
# Revert the latest correction
curl -X POST "http://localhost:8000/api/v1/videos/dQw4w9WgXcQ/transcript/segments/1234/corrections/revert?language_code=en"
```

#### Get Correction History

```bash
# View correction history for a segment
curl "http://localhost:8000/api/v1/videos/dQw4w9WgXcQ/transcript/segments/1234/corrections?language_code=en"

# With pagination
curl "http://localhost:8000/api/v1/videos/dQw4w9WgXcQ/transcript/segments/1234/corrections?language_code=en&limit=10&offset=0"
```

#### Batch Find-Replace

```bash
# Preview batch corrections
curl -X POST "http://localhost:8000/api/v1/corrections/batch/preview" \
  -H "Content-Type: application/json" \
  -d '{"pattern": "amlo", "replacement": "AMLO", "is_regex": false, "case_insensitive": true}'

# Apply to selected segments
curl -X POST "http://localhost:8000/api/v1/corrections/batch/apply" \
  -H "Content-Type: application/json" \
  -d '{"pattern": "amlo", "replacement": "AMLO", "segment_ids": [1234, 1235], "correction_type": "proper_noun", "auto_rebuild": true}'

# Rebuild transcript text for affected videos
curl -X POST "http://localhost:8000/api/v1/corrections/batch/rebuild-text" \
  -H "Content-Type: application/json" \
  -d '{"video_ids": ["dQw4w9WgXcQ"]}'

# List batch history
curl "http://localhost:8000/api/v1/corrections/batch/batches?limit=10"

# Revert an entire batch
curl -X DELETE "http://localhost:8000/api/v1/corrections/batch/01936c8a-1234-7000-8000-000000000001"

# Get ASR error patterns (diff analysis)
curl "http://localhost:8000/api/v1/corrections/batch/diff-analysis?show_completed=false"

# Filter error patterns by entity name
curl "http://localhost:8000/api/v1/corrections/batch/diff-analysis?entity_name=Sheinbaum"

# Get cross-segment correction candidates
curl "http://localhost:8000/api/v1/corrections/batch/cross-segment/candidates?min_corrections=3"

# Get phonetic ASR variants for an entity
curl "http://localhost:8000/api/v1/entities/01936c8a-1234-7000-8000-000000000001/phonetic-matches?threshold=0.5"
```

#### Manual Entity-Video Associations

```bash
# Search entities with link status for a specific video
curl "http://localhost:8000/api/v1/entities/search?q=chomsky&video_id=dQw4w9WgXcQ"

# Create a manual entity-video association
curl -X POST http://localhost:8000/api/v1/videos/dQw4w9WgXcQ/entities/01936c8a-1234-7000-8000-000000000001/manual

# Remove a manual entity-video association
curl -X DELETE http://localhost:8000/api/v1/videos/dQw4w9WgXcQ/entities/01936c8a-1234-7000-8000-000000000001/manual
```

#### Entity Creation

```bash
# Check for duplicate entity before creating
curl "http://localhost:8000/api/v1/entities/check-duplicate?name=Noam%20Chomsky&type=person"

# Classify a canonical tag as an entity
curl -X POST http://localhost:8000/api/v1/entities/classify \
  -H "Content-Type: application/json" \
  -d '{"normalized_form": "noam chomsky", "entity_type": "person", "description": "American linguist"}'

# Create a standalone entity with aliases
curl -X POST http://localhost:8000/api/v1/entities \
  -H "Content-Type: application/json" \
  -d '{"name": "Noam Chomsky", "entity_type": "person", "aliases": ["Chomsky", "N. Chomsky"]}'
```

#### Recover Video Metadata

```bash
# Recover a specific unavailable video
curl -X POST http://localhost:8000/api/v1/videos/dQw4w9WgXcQ/recover

# Recover with year range filter
curl -X POST "http://localhost:8000/api/v1/videos/dQw4w9WgXcQ/recover?start_year=2018&end_year=2022"
```

#### Recover Channel Metadata

```bash
# Recover a specific unavailable channel
curl -X POST http://localhost:8000/api/v1/channels/UCuAXFkgsw1L7xaCfnd5JJOw/recover

# Recover with year range filter
curl -X POST "http://localhost:8000/api/v1/channels/UCuAXFkgsw1L7xaCfnd5JJOw/recover?start_year=2015"
```

### Using Python

```python
import httpx

BASE_URL = "http://localhost:8000/api/v1"

async def main():
    async with httpx.AsyncClient() as client:
        # Check health
        response = await client.get(f"{BASE_URL}/health")
        health = response.json()
        print(f"Status: {health['data']['status']}")

        # List videos with transcripts
        response = await client.get(
            f"{BASE_URL}/videos",
            params={"has_transcript": True, "limit": 10}
        )
        videos = response.json()
        for video in videos["data"]:
            print(f"- {video['title']} ({video['video_id']})")

        # Search transcripts
        response = await client.get(
            f"{BASE_URL}/search/segments",
            params={"q": "machine learning", "limit": 5}
        )
        results = response.json()
        for result in results["data"]:
            print(f"[{result['video_title']}] {result['text']}")

        # Update preferences
        response = await client.put(
            f"{BASE_URL}/preferences/languages",
            json={
                "preferences": [
                    {"language_code": "en", "preference_type": "fluent"},
                    {"language_code": "es", "preference_type": "learning"}
                ]
            }
        )

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

### Using JavaScript/Fetch

```javascript
const BASE_URL = 'http://localhost:8000/api/v1';

// List videos
async function listVideos(params = {}) {
  const url = new URL(`${BASE_URL}/videos`);
  Object.entries(params).forEach(([key, value]) =>
    url.searchParams.append(key, value)
  );

  const response = await fetch(url);
  return response.json();
}

// Search transcripts
async function searchTranscripts(query, options = {}) {
  const url = new URL(`${BASE_URL}/search/segments`);
  url.searchParams.append('q', query);
  Object.entries(options).forEach(([key, value]) =>
    url.searchParams.append(key, value)
  );

  const response = await fetch(url);
  return response.json();
}

// Update preferences
async function updatePreferences(preferences) {
  const response = await fetch(`${BASE_URL}/preferences/languages`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ preferences })
  });
  return response.json();
}

// Usage
const videos = await listVideos({ has_transcript: true, limit: 20 });
const results = await searchTranscripts('python tutorial');
await updatePreferences([
  { language_code: 'en', preference_type: 'fluent' },
  { language_code: 'es', preference_type: 'learning' }
]);
```

## Rate Limiting

The canonical tag search endpoint (`GET /api/v1/canonical-tags?q=...`), tag search endpoint (`GET /api/v1/tags?q=...`), and entity duplicate-check endpoint (`GET /api/v1/entities/check-duplicate`) enforce rate limiting at **50 requests per minute per client IP**. Exceeding this limit returns a `429 Too Many Requests` response with a `Retry-After` header indicating how many seconds to wait.

Other endpoints do not implement rate limiting directly, but be aware of YouTube API quotas when triggering sync operations. See the [Authentication](authentication.md) guide for quota information.

## Troubleshooting

### 401 Not Authenticated

```bash
# Authenticate via CLI first
chronovista auth login

# Verify authentication
chronovista auth status
```

### 404 Not Found

- Verify the video/resource ID is correct
- Run a sync to populate the database:
  ```bash
  chronovista sync videos
  chronovista sync transcripts
  ```

### 409 Sync In Progress

Wait for the current sync to complete or check status:

```bash
curl http://localhost:8000/api/v1/sync/status
```

### Server Won't Start

Check if port is in use:

```bash
# Find process using port 8000
lsof -i :8000

# Use different port
chronovista api start --port 3000
```

## See Also

- [CLI Overview](cli-overview.md) - Command-line interface reference
- [Authentication](authentication.md) - OAuth setup and troubleshooting
- [Data Synchronization](data-sync.md) - Sync operations and strategies
- [Transcripts](transcripts.md) - Transcript management details
