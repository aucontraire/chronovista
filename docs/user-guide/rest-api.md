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
| `CONFLICT` | 409 | Resource conflict (e.g., sync in progress) |
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

### Channels

#### List Channels

Get paginated list of channels sorted by video count.

```
GET /api/v1/channels
```

##### Query Parameters

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `has_videos` | boolean | Filter to channels with videos | - |
| `limit` | integer | Items per page (1-100) | 20 |
| `offset` | integer | Pagination offset | 0 |

##### Response

```json
{
  "data": [
    {
      "channel_id": "UCuAXFkgsw1L7xaCfnd5JJOw",
      "title": "Rick Astley",
      "description": "Official channel...",
      "subscriber_count": 5000000,
      "video_count": 150,
      "thumbnail_url": "https://yt3.ggpht.com/..."
    }
  ],
  "pagination": {
    "total": 50,
    "limit": 20,
    "offset": 0,
    "has_more": true
  }
}
```

#### Get Channel Details

Get full details for a specific channel.

```
GET /api/v1/channels/{channel_id}
```

##### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `channel_id` | string | YouTube channel ID (24 characters) |

##### Response

```json
{
  "data": {
    "channel_id": "UCuAXFkgsw1L7xaCfnd5JJOw",
    "title": "Rick Astley",
    "description": "Official channel for Rick Astley...",
    "subscriber_count": 5000000,
    "video_count": 150,
    "thumbnail_url": "https://yt3.ggpht.com/...",
    "custom_url": "@RickAstley",
    "published_at": "2006-09-23T00:00:00Z"
  }
}
```

#### Get Channel Videos

Get paginated list of videos from a specific channel.

```
GET /api/v1/channels/{channel_id}/videos
```

##### Query Parameters

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `limit` | integer | Items per page (1-100) | 20 |
| `offset` | integer | Pagination offset | 0 |

##### Response

Returns the same format as the videos list endpoint, filtered to the specified channel.

---

### Playlists

#### List Playlists

Get paginated list of playlists sorted by last updated.

```
GET /api/v1/playlists
```

##### Query Parameters

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `linked` | boolean | Filter to YouTube-linked playlists (PL/LL/WL/HL prefix) | - |
| `unlinked` | boolean | Filter to internal playlists (int_ prefix) | - |
| `limit` | integer | Items per page (1-100) | 20 |
| `offset` | integer | Pagination offset | 0 |

!!! warning "Mutually Exclusive Filters"
    Setting both `linked=true` and `unlinked=true` returns a 400 Bad Request error.

##### Response

```json
{
  "data": [
    {
      "playlist_id": "PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf",
      "title": "My Favorites",
      "description": "Collection of favorite videos",
      "video_count": 42,
      "privacy_status": "private",
      "is_linked": true
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

#### Get Playlist Details

Get full details for a specific playlist.

```
GET /api/v1/playlists/{playlist_id}
```

##### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `playlist_id` | string | Playlist ID (YouTube: PL/LL/WL/HL prefix, Internal: int_ prefix) |

##### Response

```json
{
  "data": {
    "playlist_id": "PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf",
    "title": "My Favorites",
    "description": "Collection of favorite videos",
    "video_count": 42,
    "privacy_status": "private",
    "is_linked": true,
    "channel_id": "UCuAXFkgsw1L7xaCfnd5JJOw",
    "published_at": "2020-01-15T10:30:00Z"
  }
}
```

#### Get Playlist Videos

Get paginated list of videos in a playlist with position ordering preserved.

```
GET /api/v1/playlists/{playlist_id}/videos
```

##### Query Parameters

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `limit` | integer | Items per page (1-100) | 20 |
| `offset` | integer | Pagination offset | 0 |

##### Response

```json
{
  "data": [
    {
      "video_id": "dQw4w9WgXcQ",
      "title": "Rick Astley - Never Gonna Give You Up",
      "position": 0,
      "channel_title": "Rick Astley",
      "upload_date": "2009-10-25T06:57:33Z",
      "duration": 213
    }
  ],
  "pagination": {
    "total": 42,
    "limit": 20,
    "offset": 0,
    "has_more": true
  }
}
```

---

### Topics

Topics are YouTube's Knowledge Graph classifications for video content.

#### List Topics

Get all topics with aggregated video and channel counts, sorted by video count.

```
GET /api/v1/topics
```

##### Query Parameters

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `limit` | integer | Items per page (1-100) | 20 |
| `offset` | integer | Pagination offset | 0 |

##### Response

```json
{
  "data": [
    {
      "topic_id": "/m/098wr",
      "name": "Society",
      "video_count": 27099,
      "channel_count": 156
    },
    {
      "topic_id": "/m/04rlf",
      "name": "Music",
      "video_count": 2736,
      "channel_count": 89
    }
  ],
  "pagination": {
    "total": 62,
    "limit": 20,
    "offset": 0,
    "has_more": true
  }
}
```

#### Get Topic Details

Get full details for a specific topic.

```
GET /api/v1/topics/{topic_id}
```

##### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `topic_id` | string | Topic ID (Knowledge Graph format like `/m/098wr` or alphanumeric like `wiki_Military`) |

!!! note "Topic IDs with Slashes"
    Topic IDs containing slashes (e.g., `/m/098wr`) are supported directly in the URL path without encoding.

##### Response

```json
{
  "data": {
    "topic_id": "/m/098wr",
    "name": "Society",
    "video_count": 27099,
    "channel_count": 156,
    "parent_topic_id": null,
    "topic_type": "youtube",
    "wikipedia_url": "https://en.wikipedia.org/wiki/Society",
    "normalized_name": "society",
    "source": "seeded",
    "created_at": "2026-01-25T14:31:31Z"
  }
}
```

#### Get Topic Videos

Get paginated list of videos classified with a specific topic.

```
GET /api/v1/topics/{topic_id}/videos
```

##### Query Parameters

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `limit` | integer | Items per page (1-100) | 20 |
| `offset` | integer | Pagination offset | 0 |

!!! note "Topic IDs with Slashes for Videos Endpoint"
    For topic IDs with slashes (e.g., `/m/098wr`), you can use the ID directly: `/api/v1/topics//m/098wr/videos`

##### Response

Returns the same format as the videos list endpoint, filtered to videos with the specified topic.

---

### Categories

YouTube's 31 predefined content categories (e.g., "Music", "Gaming", "Education").

#### List Categories

Get all categories sorted by video count (most popular first).

```
GET /api/v1/categories
```

##### Query Parameters

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `limit` | integer | Items per page (1-100) | 20 |
| `offset` | integer | Pagination offset | 0 |

##### Response

```json
{
  "data": [
    {
      "category_id": "25",
      "name": "News & Politics",
      "assignable": true,
      "video_count": 19063
    },
    {
      "category_id": "24",
      "name": "Entertainment",
      "assignable": true,
      "video_count": 6871
    }
  ],
  "pagination": {
    "total": 32,
    "limit": 20,
    "offset": 0,
    "has_more": true
  }
}
```

##### Field Descriptions

| Field | Description |
|-------|-------------|
| `category_id` | YouTube's numeric category ID (as string) |
| `name` | Human-readable category name |
| `assignable` | Whether videos can be assigned to this category (some like "Movies" are YouTube-managed only) |
| `video_count` | Number of videos in your library with this category |

#### Get Category Details

Get full details for a specific category.

```
GET /api/v1/categories/{category_id}
```

##### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `category_id` | string | YouTube category ID (numeric string like "10", "25") |

##### Response

```json
{
  "data": {
    "category_id": "25",
    "name": "News & Politics",
    "assignable": true,
    "video_count": 19063,
    "created_at": "2026-01-25T14:31:39Z"
  }
}
```

#### Get Category Videos

Get paginated list of videos in a specific category.

```
GET /api/v1/categories/{category_id}/videos
```

##### Query Parameters

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `limit` | integer | Items per page (1-100) | 20 |
| `offset` | integer | Pagination offset | 0 |

##### Response

Returns the same format as the videos list endpoint, filtered to videos in the specified category, sorted by upload date (most recent first).

---

### Tags

Free-form keywords associated with videos by their creators.

#### List Tags

Get all tags sorted by video count (most popular first).

```
GET /api/v1/tags
```

##### Query Parameters

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `limit` | integer | Items per page (1-100) | 20 |
| `offset` | integer | Pagination offset | 0 |

##### Response

```json
{
  "data": [
    {
      "tag": "politics",
      "video_count": 5392
    },
    {
      "tag": "news",
      "video_count": 5371
    },
    {
      "tag": "comedy",
      "video_count": 1860
    }
  ],
  "pagination": {
    "total": 139763,
    "limit": 20,
    "offset": 0,
    "has_more": true
  }
}
```

!!! note "Case Sensitivity"
    Tags are case-sensitive. "Politics" and "politics" are treated as separate tags.

#### Get Tag Details

Get details for a specific tag.

```
GET /api/v1/tags/{tag}
```

##### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `tag` | string | Tag name (URL-encoded if contains special characters) |

##### URL Encoding

Tags with special characters must be URL-encoded:

| Character | Encoded |
|-----------|---------|
| Space | `%20` |
| Hash (#) | `%23` |
| Forward slash (/) | `%2F` |

Examples:
- `hip hop` → `/api/v1/tags/hip%20hop`
- `#music` → `/api/v1/tags/%23music`

##### Response

```json
{
  "data": {
    "tag": "hip hop",
    "video_count": 25
  }
}
```

#### Get Tag Videos

Get paginated list of videos with a specific tag.

```
GET /api/v1/tags/{tag}/videos
```

##### Query Parameters

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `limit` | integer | Items per page (1-100) | 20 |
| `offset` | integer | Pagination offset | 0 |

##### Response

Returns the same format as the videos list endpoint, filtered to videos with the specified tag, sorted by upload date (most recent first).

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
