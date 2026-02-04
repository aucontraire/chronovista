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

2. **API reads tokens automatically** from the CLI's OAuth cache (~/.chronovista/credentials/)

3. **All endpoints require authentication** except `/api/v1/health`

!!! note "Single User"
    The API currently operates in single-user mode. All requests use the authenticated CLI session.

### Authentication Errors

If not authenticated, protected endpoints return:

```json
{
  "detail": {
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
  "detail": {
    "code": "NOT_FOUND",
    "message": "Video 'xyz789' not found. Verify the video ID or run a sync."
  }
}
```

### Common Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `NOT_AUTHENTICATED` | 401 | OAuth token missing or invalid |
| `NOT_FOUND` | 404 | Resource not found |
| `VALIDATION_ERROR` | 400 | Invalid request parameters |
| `SYNC_IN_PROGRESS` | 409 | Another sync operation is running |
| `INVALID_LANGUAGE_CODE` | 400 | Invalid BCP-47 language code |
| `INVALID_PREFERENCE_TYPE` | 400 | Invalid preference type |

## Endpoints

### Health Check

Check application health status. No authentication required.

```
GET /api/v1/health
```

#### Response

```json
{
  "data": {
    "status": "healthy",
    "version": "1.0.0",
    "database": "connected",
    "authenticated": true,
    "timestamp": "2026-02-03T15:30:00Z",
    "checks": {
      "database_latency_ms": 5,
      "token_expiry_hours": null
    }
  }
}
```

#### Status Values

| Status | Description |
|--------|-------------|
| `healthy` | All systems operational |
| `degraded` | Some features may be impaired |
| `unhealthy` | Critical issues (database disconnected, high latency) |

---

### Videos

#### List Videos

Get paginated list of videos with optional filtering.

```
GET /api/v1/videos
```

##### Query Parameters

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `channel_id` | string | Filter by channel ID (24 characters) | - |
| `has_transcript` | boolean | Filter by transcript availability | - |
| `uploaded_after` | datetime | ISO 8601 date filter (inclusive) | - |
| `uploaded_before` | datetime | ISO 8601 date filter (inclusive) | - |
| `limit` | integer | Items per page (1-100) | 20 |
| `offset` | integer | Pagination offset | 0 |

##### Response

```json
{
  "data": [
    {
      "video_id": "dQw4w9WgXcQ",
      "title": "Rick Astley - Never Gonna Give You Up",
      "channel_id": "UCuAXFkgsw1L7xaCfnd5JJOw",
      "channel_title": "Rick Astley",
      "upload_date": "2009-10-25T06:57:33Z",
      "duration": 213,
      "view_count": 1500000000,
      "transcript_summary": {
        "count": 2,
        "languages": ["en", "es"],
        "has_manual": true
      }
    }
  ],
  "pagination": {
    "total": 500,
    "limit": 20,
    "offset": 0,
    "has_more": true
  }
}
```

#### Get Video Details

Get full details for a specific video.

```
GET /api/v1/videos/{video_id}
```

##### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `video_id` | string | YouTube video ID (11 characters) |

##### Response

```json
{
  "data": {
    "video_id": "dQw4w9WgXcQ",
    "title": "Rick Astley - Never Gonna Give You Up",
    "description": "The official video for...",
    "channel_id": "UCuAXFkgsw1L7xaCfnd5JJOw",
    "channel_title": "Rick Astley",
    "upload_date": "2009-10-25T06:57:33Z",
    "duration": 213,
    "view_count": 1500000000,
    "like_count": 15000000,
    "comment_count": 3000000,
    "tags": ["rick astley", "never gonna give you up", "80s music"],
    "category_id": "10",
    "default_language": "en",
    "made_for_kids": false,
    "transcript_summary": {
      "count": 2,
      "languages": ["en", "es"],
      "has_manual": true
    }
  }
}
```

---

### Transcripts

#### List Available Languages

Get available transcript languages for a video.

```
GET /api/v1/videos/{video_id}/transcript/languages
```

##### Response

```json
{
  "data": [
    {
      "language_code": "en",
      "language_name": "English",
      "transcript_type": "manual",
      "is_translatable": true,
      "downloaded_at": "2026-02-01T10:30:00Z"
    },
    {
      "language_code": "es",
      "language_name": "Spanish",
      "transcript_type": "auto_generated",
      "is_translatable": true,
      "downloaded_at": "2026-02-01T10:30:05Z"
    }
  ]
}
```

#### Get Full Transcript

Get the complete transcript text for a video.

```
GET /api/v1/videos/{video_id}/transcript
```

##### Query Parameters

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `language` | string | BCP-47 language code | First available (prefers manual) |

##### Response

```json
{
  "data": {
    "video_id": "dQw4w9WgXcQ",
    "language_code": "en",
    "transcript_type": "manual",
    "full_text": "We're no strangers to love...",
    "segment_count": 45,
    "downloaded_at": "2026-02-01T10:30:00Z"
  }
}
```

#### Get Transcript Segments

Get paginated transcript segments with timestamps.

```
GET /api/v1/videos/{video_id}/transcript/segments
```

##### Query Parameters

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `language` | string | BCP-47 language code | First available |
| `start_time` | float | Filter segments starting at/after (seconds) | - |
| `end_time` | float | Filter segments ending before (seconds) | - |
| `limit` | integer | Items per page (1-200) | 50 |
| `offset` | integer | Pagination offset | 0 |

##### Response

```json
{
  "data": [
    {
      "id": 1234,
      "text": "We're no strangers to love",
      "start_time": 18.5,
      "end_time": 21.3,
      "duration": 2.8
    },
    {
      "id": 1235,
      "text": "You know the rules and so do I",
      "start_time": 21.3,
      "end_time": 24.1,
      "duration": 2.8
    }
  ],
  "pagination": {
    "total": 45,
    "limit": 50,
    "offset": 0,
    "has_more": false
  }
}
```

---

### Search

#### Search Transcript Segments

Full-text search across all transcript segments.

```
GET /api/v1/search/segments
```

##### Query Parameters

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `q` | string | Search query (2-500 characters, required) | - |
| `video_id` | string | Limit to specific video | - |
| `language` | string | Limit to specific language | - |
| `limit` | integer | Results per page (1-100) | 20 |
| `offset` | integer | Pagination offset | 0 |

##### Search Behavior

- Case-insensitive substring matching (ILIKE)
- Multi-word queries use implicit AND (all terms must match)
- Results ordered by video upload date (desc), then segment time (asc)
- Context from adjacent segments included automatically

##### Response

```json
{
  "data": [
    {
      "segment_id": 5678,
      "video_id": "dQw4w9WgXcQ",
      "video_title": "Rick Astley - Never Gonna Give You Up",
      "channel_title": "Rick Astley",
      "language_code": "en",
      "text": "Never gonna give you up",
      "start_time": 43.2,
      "end_time": 45.8,
      "context_before": "You know the rules and so do I",
      "context_after": "Never gonna let you down",
      "match_count": 1,
      "video_upload_date": "2009-10-25T06:57:33Z"
    }
  ],
  "pagination": {
    "total": 15,
    "limit": 20,
    "offset": 0,
    "has_more": false
  }
}
```

---

### Preferences

#### Get Language Preferences

Get current language preferences.

```
GET /api/v1/preferences/languages
```

##### Response

```json
{
  "data": [
    {
      "language_code": "en",
      "preference_type": "fluent",
      "priority": 1,
      "learning_goal": null
    },
    {
      "language_code": "es",
      "preference_type": "learning",
      "priority": 1,
      "learning_goal": "Conversational Spanish by 2027"
    },
    {
      "language_code": "ja",
      "preference_type": "curious",
      "priority": 1,
      "learning_goal": null
    }
  ]
}
```

#### Update Language Preferences

Replace all language preferences.

```
PUT /api/v1/preferences/languages
```

##### Request Body

```json
{
  "preferences": [
    {
      "language_code": "en",
      "preference_type": "fluent",
      "priority": 1
    },
    {
      "language_code": "es",
      "preference_type": "learning",
      "priority": 1,
      "learning_goal": "Conversational Spanish by 2027"
    },
    {
      "language_code": "fr",
      "preference_type": "curious"
    }
  ]
}
```

##### Preference Types

| Type | Description |
|------|-------------|
| `fluent` | Languages you speak fluently |
| `learning` | Languages you're actively learning |
| `curious` | Languages you're interested in exploring |
| `exclude` | Languages to exclude from transcript downloads |

##### Notes

- Priority is auto-assigned if not provided
- Duplicate language codes: last occurrence wins
- This replaces all existing preferences

##### Response

Returns the updated preferences in the same format as GET.

---

### Sync Operations

#### Trigger Sync Operation

Start a new synchronization operation.

```
POST /api/v1/sync/{operation}
```

##### Path Parameters

| Operation | Description |
|-----------|-------------|
| `subscriptions` | Sync user's YouTube subscriptions |
| `videos` | Sync videos from subscribed channels |
| `transcripts` | Sync transcripts for videos |
| `playlists` | Sync user's playlists |
| `topics` | Sync channel topics |
| `channel` | Sync channel metadata |
| `liked` | Sync liked videos |

##### Request Body (Transcripts Only)

For transcript sync, you can optionally specify parameters:

```json
{
  "video_ids": ["dQw4w9WgXcQ", "abc123def45"],
  "languages": ["en", "es"],
  "force": false
}
```

| Field | Type | Description | Default |
|-------|------|-------------|---------|
| `video_ids` | array | Specific video IDs to sync (null = all without transcripts) | null |
| `languages` | array | BCP-47 language codes to prioritize | ["en"] |
| `force` | boolean | Re-download existing transcripts | false |

##### Response (202 Accepted)

```json
{
  "data": {
    "operation_id": "subscriptions_20260203T143052Z_a7b3c9",
    "operation_type": "subscriptions",
    "started_at": "2026-02-03T14:30:52Z",
    "message": "Sync operation started"
  }
}
```

##### Conflict Response (409)

Only one sync operation can run at a time:

```json
{
  "detail": {
    "code": "SYNC_IN_PROGRESS",
    "message": "Sync already in progress (operation: videos_20260203T143000Z_x1y2z3). Wait for completion or check status.",
    "details": {
      "operation_id": "videos_20260203T143000Z_x1y2z3",
      "operation_type": "videos",
      "started_at": "2026-02-03T14:30:00Z"
    }
  }
}
```

#### Get Sync Status

Get the current or most recent sync operation status.

```
GET /api/v1/sync/status
```

##### Response

```json
{
  "data": {
    "status": "running",
    "operation_type": "videos",
    "operation_id": "videos_20260203T143000Z_x1y2z3",
    "progress": {
      "total_items": 500,
      "processed_items": 125,
      "current_item": "UCuAXFkgsw1L7xaCfnd5JJOw",
      "estimated_remaining": 180
    },
    "last_successful_sync": "2026-02-02T10:00:00Z",
    "error_message": null,
    "started_at": "2026-02-03T14:30:00Z",
    "completed_at": null
  }
}
```

##### Status Values

| Status | Description |
|--------|-------------|
| `idle` | No sync running |
| `running` | Sync in progress |
| `completed` | Last sync completed successfully |
| `failed` | Last sync failed (check error_message) |

---

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

The API does not implement rate limiting directly, but be aware of YouTube API quotas when triggering sync operations. See the [Authentication](authentication.md) guide for quota information.

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
