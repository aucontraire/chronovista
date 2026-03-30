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
| `CONFLICT` | 409 | Resource conflict (e.g., recovery on available entity) |
| `INVALID_LANGUAGE_CODE` | 400 | Invalid BCP-47 language code |
| `INVALID_PREFERENCE_TYPE` | 400 | Invalid preference type |
| `SERVICE_UNAVAILABLE` | 503 | External service unavailable (e.g., Wayback Machine CDX API) |
| `SEGMENT_NOT_FOUND` | 422 | Transcript segment not found for video/language |
| `NO_CHANGE_DETECTED` | 422 | Corrected text identical to current text |
| `INVALID_CORRECTION_TYPE` | 422 | Invalid correction type (e.g., `revert` on submit endpoint) |
| `NO_ACTIVE_CORRECTION` | 422 | No active correction to revert |

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
| `canonical_tag` | string[] | Filter by canonical tag group (AND semantics, max 10) | - |
| `limit` | integer | Items per page (1-100) | 20 |
| `offset` | integer | Pagination offset | 0 |

!!! tip "Canonical Tag vs Raw Tag Filtering"
    The `tag` parameter matches exact raw tag strings (case-sensitive). The `canonical_tag` parameter matches normalized tag groups — e.g., `canonical_tag=mexico` returns videos tagged with "mexico", "Mexico", "méxico", "México", "#mexico", etc. Multiple `canonical_tag` values use AND semantics (videos must match all specified groups).

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
    },
    "availability_status": "available",
    "alternative_url": null,
    "recovered_at": null,
    "recovery_source": null
  }
}
```

!!! note "Recovery Fields"
    The `recovered_at` and `recovery_source` fields are populated when a video's metadata has been recovered from the Wayback Machine. See [Recovery Endpoints](#recovery) below.

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
    "published_at": "2006-09-23T00:00:00Z",
    "availability_status": "available",
    "recovered_at": null,
    "recovery_source": null
  }
}
```

!!! note "Recovery Fields"
    The `recovered_at` and `recovery_source` fields are populated when a channel's metadata has been recovered from the Wayback Machine. See [Recovery Endpoints](#recovery) below.

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

### Canonical Tags

Canonical tags group raw tag variations (case, accents, hashtags) into unified concepts. For example, the canonical tag "mexico" groups "mexico", "Mexico", "méxico", "México", "#mexico", and more. Built by the tag normalization pipeline (ADR-003).

#### List Canonical Tags

Get paginated list of canonical tags with optional prefix search and fuzzy suggestions.

```
GET /api/v1/canonical-tags
```

##### Query Parameters

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `q` | string | Prefix search query (1-500 characters) | - |
| `limit` | integer | Items per page (1-100) | 20 |
| `offset` | integer | Pagination offset | 0 |

##### Response

```json
{
  "data": [
    {
      "canonical_form": "Mexico",
      "normalized_form": "mexico",
      "alias_count": 9,
      "video_count": 910
    },
    {
      "canonical_form": "Mexico City",
      "normalized_form": "mexico city",
      "alias_count": 4,
      "video_count": 64
    }
  ],
  "pagination": {
    "total": 124686,
    "limit": 20,
    "offset": 0,
    "has_more": true
  },
  "suggestions": null
}
```

!!! note "Fuzzy Suggestions"
    When `q` is provided (2+ characters) and no prefix matches are found, the response includes a `suggestions` array with up to 10 similar canonical tags using Levenshtein distance matching. Each suggestion includes both `canonical_form` (for display) and `normalized_form` (for URL navigation).

!!! note "Rate Limiting"
    When `q` is provided, the endpoint enforces a rate limit of 50 requests per minute per client IP. Exceeding this returns a 429 response with a `Retry-After` header.

#### Get Canonical Tag Detail

Get details for a canonical tag including its top raw-form aliases.

```
GET /api/v1/canonical-tags/{normalized_form}
```

##### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `normalized_form` | string | Normalized tag form (URL-encoded if contains spaces) |

##### Query Parameters

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `alias_limit` | integer | Maximum aliases to return (1-50) | 5 |

##### Response

```json
{
  "data": {
    "canonical_form": "Mexico",
    "normalized_form": "mexico",
    "alias_count": 9,
    "video_count": 910,
    "top_aliases": [
      { "raw_form": "mexico", "occurrence_count": 651 },
      { "raw_form": "Mexico", "occurrence_count": 176 },
      { "raw_form": "méxico", "occurrence_count": 109 },
      { "raw_form": "México", "occurrence_count": 76 },
      { "raw_form": "#mexico", "occurrence_count": 8 }
    ],
    "created_at": "2026-02-23T19:39:36Z",
    "updated_at": "2026-02-23T19:41:12Z"
  }
}
```

#### Get Canonical Tag Videos

Get paginated videos across all raw tag variations for a canonical tag.

```
GET /api/v1/canonical-tags/{normalized_form}/videos
```

##### Query Parameters

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `include_unavailable` | boolean | Include deleted/private videos | false |
| `limit` | integer | Items per page (1-100) | 20 |
| `offset` | integer | Pagination offset | 0 |

##### Response

Returns the same format as the videos list endpoint, filtered to videos matching any raw form alias of the canonical tag, sorted by upload date (most recent first).

!!! note "Query Timeout"
    This endpoint has a 10-second query timeout. If exceeded, a 504 Gateway Timeout response is returned.

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
      "duration": 2.8,
      "has_correction": false,
      "corrected_at": null,
      "correction_count": 0
    },
    {
      "id": 1235,
      "text": "You know the rules and so do I",
      "start_time": 21.3,
      "end_time": 24.1,
      "duration": 2.8,
      "has_correction": true,
      "corrected_at": "2026-03-03T10:15:00Z",
      "correction_count": 2
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

##### Correction Metadata Fields

| Field | Type | Description |
|-------|------|-------------|
| `has_correction` | boolean | Whether the segment has an active correction |
| `corrected_at` | datetime \| null | Timestamp of the most recent correction (null if uncorrected) |
| `correction_count` | integer | Total number of correction audit records for this segment |

!!! note "Effective Text"
    The `text` field returns the effective text — corrected text if `has_correction` is true, original text otherwise. Use the correction history endpoint to see previous versions.

#### Download Transcript

Download a transcript from YouTube for a single video. Requires authentication.

```
POST /api/v1/videos/{video_id}/transcript/download
```

##### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `video_id` | string | 11-character YouTube video ID (regex: `[A-Za-z0-9_-]{11}`) |

##### Query Parameters

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `language` | string | BCP-47 language code to download | Auto-detected |

##### Responses

| Status | Description |
|--------|-------------|
| 200 | Transcript downloaded successfully; returns transcript metadata |
| 401 | Not authenticated |
| 404 | No transcript available on YouTube for this video |
| 409 | Transcript already exists in the database |
| 422 | Invalid video_id format (must be 11 characters) |
| 429 | Download already in progress for this video |
| 503 | Rate limited by YouTube — wait and retry |

##### Response (200)

```json
{
  "data": {
    "video_id": "dQw4w9WgXcQ",
    "language_code": "en",
    "transcript_type": "auto_generated",
    "segment_count": 45,
    "downloaded_at": "2026-03-20T14:30:00Z"
  }
}
```

!!! note "In-Flight Guard"
    Only one download per video_id can run at a time. If a download is already in progress (e.g., from another browser tab), the server returns 429. Wait for the existing download to complete before retrying.

---

### Transcript Corrections

Submit, revert, and view correction history for transcript segments. All correction endpoints require authentication and a `language_code` query parameter.

#### Submit a Correction

Apply a correction to a specific transcript segment.

```
POST /api/v1/videos/{video_id}/transcript/segments/{segment_id}/corrections
```

##### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `video_id` | string | YouTube video ID (11 characters) |
| `segment_id` | integer | Transcript segment ID |

##### Query Parameters

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `language_code` | string | BCP-47 language code (required) | - |

##### Request Body

```json
{
  "corrected_text": "The corrected segment text",
  "correction_type": "spelling",
  "correction_note": "Fixed typo in speaker name",
  "corrected_by_user_id": "user123"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `corrected_text` | string | Yes | Corrected text (min 1 character after whitespace stripping) |
| `correction_type` | string | Yes | One of: `spelling`, `proper_noun`, `context_correction`, `word_boundary`, `formatting`, `profanity_fix`, `other` |
| `correction_note` | string | No | Optional explanation for the correction |
| `corrected_by_user_id` | string | No | Optional user identifier (max 100 chars) |

!!! warning "Revert Type Not Allowed"
    The `correction_type` value `revert` is rejected by this endpoint. Use the dedicated revert endpoint instead.

##### Response (201 Created)

```json
{
  "data": {
    "correction": {
      "id": "019576a1-2b3c-7def-8901-234567890abc",
      "video_id": "dQw4w9WgXcQ",
      "language_code": "en",
      "segment_id": 1234,
      "correction_type": "spelling",
      "original_text": "We're no strangers to lvoe",
      "corrected_text": "We're no strangers to love",
      "correction_note": "Fixed typo in speaker name",
      "corrected_by_user_id": "user123",
      "corrected_at": "2026-03-03T10:15:00Z",
      "version_number": 1
    },
    "segment_state": {
      "has_correction": true,
      "effective_text": "We're no strangers to love"
    }
  }
}
```

##### Error Responses

| HTTP Status | Code | Description |
|-------------|------|-------------|
| 404 | `NOT_FOUND` | Video not found |
| 422 | `SEGMENT_NOT_FOUND` | Segment not found for the given video/language |
| 422 | `NO_CHANGE_DETECTED` | Corrected text is identical to current text |
| 422 | `INVALID_CORRECTION_TYPE` | `correction_type=revert` is not allowed |

---

#### Revert a Correction

Revert the latest correction on a segment, restoring it to the previous state.

```
POST /api/v1/videos/{video_id}/transcript/segments/{segment_id}/corrections/revert
```

##### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `video_id` | string | YouTube video ID (11 characters) |
| `segment_id` | integer | Transcript segment ID |

##### Query Parameters

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `language_code` | string | BCP-47 language code (required) | - |

##### Request Body

No request body. The revert target is always the latest correction.

##### Response (200 OK)

```json
{
  "data": {
    "correction": {
      "id": "019576b2-3c4d-7ef0-1234-567890abcdef",
      "video_id": "dQw4w9WgXcQ",
      "language_code": "en",
      "segment_id": 1234,
      "correction_type": "revert",
      "original_text": "We're no strangers to love",
      "corrected_text": "We're no strangers to lvoe",
      "correction_note": null,
      "corrected_by_user_id": null,
      "corrected_at": "2026-03-03T10:20:00Z",
      "version_number": 2
    },
    "segment_state": {
      "has_correction": false,
      "effective_text": "We're no strangers to lvoe"
    }
  }
}
```

!!! note "Revert Behavior"
    - **Single correction**: Reverts to original text (`has_correction` becomes `false`)
    - **Stacked corrections**: Reverts to the previous correction's text (`has_correction` stays `true`)

##### Error Responses

| HTTP Status | Code | Description |
|-------------|------|-------------|
| 404 | `NOT_FOUND` | Video not found |
| 422 | `SEGMENT_NOT_FOUND` | Segment not found for the given video/language |
| 422 | `NO_ACTIVE_CORRECTION` | Segment has no active correction to revert |

---

#### Get Correction History

Retrieve paginated correction history for a segment.

```
GET /api/v1/videos/{video_id}/transcript/segments/{segment_id}/corrections
```

##### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `video_id` | string | YouTube video ID (11 characters) |
| `segment_id` | integer | Transcript segment ID |

##### Query Parameters

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `language_code` | string | BCP-47 language code (required) | - |
| `limit` | integer | Items per page (1-100) | 50 |
| `offset` | integer | Pagination offset | 0 |

##### Response (200 OK)

```json
{
  "data": [
    {
      "id": "019576b2-3c4d-7ef0-1234-567890abcdef",
      "video_id": "dQw4w9WgXcQ",
      "language_code": "en",
      "segment_id": 1234,
      "correction_type": "revert",
      "original_text": "We're no strangers to love",
      "corrected_text": "We're no strangers to lvoe",
      "correction_note": null,
      "corrected_by_user_id": null,
      "corrected_at": "2026-03-03T10:20:00Z",
      "version_number": 2
    },
    {
      "id": "019576a1-2b3c-7def-8901-234567890abc",
      "video_id": "dQw4w9WgXcQ",
      "language_code": "en",
      "segment_id": 1234,
      "correction_type": "spelling",
      "original_text": "We're no strangers to lvoe",
      "corrected_text": "We're no strangers to love",
      "correction_note": "Fixed typo",
      "corrected_by_user_id": "user123",
      "corrected_at": "2026-03-03T10:15:00Z",
      "version_number": 1
    }
  ],
  "pagination": {
    "total": 2,
    "limit": 50,
    "offset": 0,
    "has_more": false
  }
}
```

!!! note "Empty History"
    Returns an empty `data` array (not 404) when a segment has no corrections or when the segment ID doesn't exist.

---

### Batch Corrections

Bulk find-and-replace operations across transcript segments. These endpoints power both the CLI `corrections find-replace` command and the web UI batch corrections page. All batch endpoints require authentication.

#### Preview Batch Matches

Search for segments matching a pattern and preview proposed replacements without applying changes.

```
POST /api/v1/corrections/batch/preview
```

##### Request Body

```json
{
  "pattern": "amlo",
  "replacement": "AMLO",
  "is_regex": false,
  "case_insensitive": true,
  "cross_segment": false,
  "language": "es",
  "channel_id": null,
  "video_ids": null
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `pattern` | string | Yes | Search pattern (max 500 chars) |
| `replacement` | string | Yes | Replacement text |
| `is_regex` | boolean | No | Treat pattern as regex (default: false) |
| `case_insensitive` | boolean | No | Case-insensitive matching (default: false) |
| `cross_segment` | boolean | No | Match across adjacent segment pairs (default: false) |
| `language` | string | No | Filter by language code |
| `channel_id` | string | No | Filter by channel ID |
| `video_ids` | string[] | No | Filter by video IDs (max 50) |

##### Response (200 OK)

```json
{
  "data": {
    "matches": [
      {
        "segment_id": 1234,
        "video_id": "dQw4w9WgXcQ",
        "video_title": "Example Video",
        "channel_title": "Example Channel",
        "language_code": "es",
        "start_time": 245.6,
        "current_text": "el presidente amlo dijo",
        "proposed_text": "el presidente AMLO dijo",
        "context_before": "en la conferencia matutina",
        "context_after": "que las reformas son necesarias",
        "has_existing_correction": false,
        "is_cross_segment": false
      }
    ],
    "total_count": 42,
    "pattern": "amlo",
    "replacement": "AMLO",
    "is_regex": false,
    "case_insensitive": true,
    "cross_segment": false
  }
}
```

!!! note "Match Cap"
    The preview endpoint returns at most 100 matches. The `total_count` field reflects the true count, allowing the UI to display "Showing 100 of 42 matches — refine your pattern to narrow results."

#### Apply Batch Corrections

Apply corrections to a specific set of segment IDs previously identified through the preview endpoint.

```
POST /api/v1/corrections/batch/apply
```

##### Request Body

```json
{
  "pattern": "amlo",
  "replacement": "AMLO",
  "is_regex": false,
  "case_insensitive": true,
  "cross_segment": false,
  "segment_ids": [1234, 1235, 1240],
  "correction_type": "proper_noun",
  "correction_note": "Fixed ASR misrecognition of AMLO",
  "auto_rebuild": true
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `pattern` | string | Yes | Original search pattern (max 500 chars) |
| `replacement` | string | Yes | Replacement text |
| `is_regex` | boolean | No | Treat pattern as regex (default: false) |
| `case_insensitive` | boolean | No | Case-insensitive matching (default: false) |
| `cross_segment` | boolean | No | Cross-segment matching (default: false) |
| `segment_ids` | integer[] | Yes | Segment IDs to apply corrections to (1–200) |
| `correction_type` | string | Yes | One of: `spelling`, `proper_noun`, `context_correction`, `word_boundary`, `formatting`, `profanity_fix`, `other` |
| `correction_note` | string | No | Optional correction note (max 500 chars) |
| `auto_rebuild` | boolean | No | Auto-rebuild full transcript text after apply (default: true) |

##### Response (200 OK)

```json
{
  "data": {
    "total_applied": 3,
    "total_skipped": 0,
    "total_failed": 0,
    "failed_segment_ids": [],
    "affected_video_ids": ["dQw4w9WgXcQ"],
    "rebuild_triggered": true
  }
}
```

!!! info "Explicit Inclusion List"
    The apply endpoint accepts an explicit `segment_ids` inclusion list (not an exclusion list). This ensures the user confirms exactly what gets corrected, even if database state changed between preview and apply.

#### List Batch Groups

Retrieve a paginated list of past batch correction operations, sorted by most recent first.

```
GET /api/v1/corrections/batch/batches
```

##### Query Parameters

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `offset` | integer | Number of rows to skip | 0 |
| `limit` | integer | Maximum rows to return (1-100) | 20 |
| `corrected_by_user_id` | string | Filter by user/actor ID | - |

##### Response (200 OK)

```json
{
  "data": [
    {
      "batch_id": "01936c8a-...",
      "correction_count": 12,
      "corrected_by_user_id": "user:batch",
      "pattern": "amlo",
      "replacement": "AMLO",
      "batch_timestamp": "2026-03-15T10:30:00Z"
    }
  ],
  "pagination": {
    "total": 45,
    "limit": 20,
    "offset": 0,
    "has_more": true
  }
}
```

#### Revert a Batch

Atomically revert all corrections belonging to a specific batch.

```
DELETE /api/v1/corrections/batch/{batch_id}
```

##### Response (200 OK)

```json
{
  "data": {
    "reverted_count": 12,
    "skipped_count": 0
  }
}
```

| Status | Description |
|--------|-------------|
| 404 | No corrections exist for the given batch ID |
| 409 | All corrections in the batch have already been reverted |

#### Get ASR Error Patterns (Diff Analysis)

Retrieve recurring word-level ASR error patterns extracted from past corrections, enriched with entity associations.

```
GET /api/v1/corrections/batch/diff-analysis
```

##### Query Parameters

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `min_occurrences` | integer | Minimum occurrences for a pattern to appear (1-50) | 2 |
| `limit` | integer | Maximum patterns to return (1-500) | 100 |
| `show_completed` | boolean | Include patterns with no remaining un-corrected matches | true |
| `entity_name` | string | Filter to patterns whose matched entity name contains this string (case-insensitive) | - |

##### Response (200 OK)

```json
{
  "data": [
    {
      "error_token": "Shane Baum",
      "canonical_form": "Sheinbaum",
      "frequency": 14,
      "remaining_matches": 23,
      "entity_id": "01936c8a-...",
      "entity_name": "Claudia Sheinbaum"
    }
  ]
}
```

Results are sorted by `remaining_matches` descending so actionable patterns appear first. The `entity_id` and `entity_name` fields are `null` when no named entity matches the canonical form.

#### Get Cross-Segment Candidates

Discover adjacent segment pairs where a known ASR error is split across a boundary, based on recurring correction patterns.

```
GET /api/v1/corrections/batch/cross-segment/candidates
```

##### Query Parameters

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `min_corrections` | integer | Minimum correction occurrences for a pattern to be considered (1-20) | 3 |
| `entity_name` | string | Only consider patterns related to this entity name | - |

##### Response (200 OK)

```json
{
  "data": [
    {
      "segment_n_id": 934,
      "segment_n_text": "...una entrevista, Claudia Shane",
      "segment_n1_id": 935,
      "segment_n1_text": "Bound también siendo candidata...",
      "proposed_correction": "Sheinbaum",
      "source_pattern": "Shane Bound",
      "confidence": 0.85,
      "is_partially_corrected": false,
      "video_id": "JIMXfrMtHas",
      "discovery_source": "correction_pattern"
    }
  ]
}
```

Each candidate includes the text of both segments, the proposed corrected form, the original error pattern, and a confidence score between 0.0 and 1.0.

#### Rebuild Transcript Text

Re-concatenate segment text to rebuild the full `transcript_text` for specified videos.

```
POST /api/v1/corrections/batch/rebuild-text
```

##### Request Body

```json
{
  "video_ids": ["dQw4w9WgXcQ", "abc123def45"]
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `video_ids` | string[] | Yes | Video IDs to rebuild (1–50) |

##### Response (200 OK)

```json
{
  "data": {
    "videos_rebuilt": 2,
    "video_ids": ["dQw4w9WgXcQ", "abc123def45"],
    "failed_video_ids": []
  }
}
```

---

### Entities

#### List Named Entities

Retrieve a paginated list of named entities.

```
GET /api/v1/entities
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `type` | string | Filter by entity type |
| `has_mentions` | boolean | Filter to entities with/without mentions |
| `search` | string | Search canonical_name |
| `search_aliases` | boolean | Also search alias names |
| `exclude_alias_types` | string | Comma-separated alias types to exclude (e.g., `asr_error`) |
| `sort` | string | Sort order: `name` or `mentions` |
| `status` | string | Entity status: `active`, `merged`, `deprecated` (default `active`) |
| `limit` | integer | Results per page, 1–100 (default 20) |
| `offset` | integer | Pagination offset (default 0) |

**Response (200):**

```json
{
  "data": [
    {
      "entity_id": "01936c8a-...",
      "canonical_name": "Andrés Manuel López Obrador",
      "entity_type": "person",
      "description": "Former President of Mexico (2018–2024)",
      "status": "active",
      "mention_count": 342,
      "video_count": 87
    }
  ],
  "pagination": { "total": 1234, "limit": 20, "offset": 0, "has_more": true }
}
```

---

#### Get Entity Detail

Retrieve full details for a single entity, including its aliases.

```
GET /api/v1/entities/{entity_id}
```

**Response (200):**

```json
{
  "data": {
    "entity_id": "01936c8a-...",
    "canonical_name": "Andrés Manuel López Obrador",
    "entity_type": "person",
    "description": "Former President of Mexico (2018–2024)",
    "status": "active",
    "mention_count": 342,
    "video_count": 87,
    "aliases": [
      { "alias_name": "AMLO", "alias_type": "abbreviation", "occurrence_count": 156 },
      { "alias_name": "López Obrador", "alias_type": "name_variant", "occurrence_count": 89 }
    ]
  }
}
```

> **Note:** Aliases with type `asr_error` are excluded from the detail response. These are auto-registered misspelling forms from the ASR correction pipeline.

---

#### Get Entity Videos

Retrieve a paginated list of videos associated with a given entity from five sources: transcript mentions, title mentions, description mentions, canonical tag associations, and manual links. Results are deduplicated by video and sorted with transcript-mention videos first.

```
GET /api/v1/entities/{entity_id}/videos
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `language_code` | string | BCP-47 language code filter |
| `source` | string | Filter by source type: `title`, `transcript`, `tag`, `description`, `manual`. Omit for all sources. |
| `limit` | integer | Results per page, 1–100 (default 20) |
| `offset` | integer | Pagination offset (default 0) |

**Response (200):**

```json
{
  "data": [
    {
      "video_id": "abc123",
      "video_title": "Interview with AMLO",
      "channel_name": "News Channel",
      "mention_count": 12,
      "mentions": [
        { "segment_id": 456, "start_time": 123.5, "mention_text": "AMLO" }
      ],
      "sources": ["transcript", "tag"],
      "has_manual": false,
      "first_mention_time": 123.5,
      "upload_date": "2025-06-15T00:00:00Z"
    },
    {
      "video_id": "xyz789",
      "video_title": "Tagged but no transcript mention",
      "channel_name": "Another Channel",
      "mention_count": 0,
      "mentions": [],
      "sources": ["tag"],
      "has_manual": false,
      "first_mention_time": null,
      "upload_date": "2024-11-20T00:00:00Z"
    }
  ],
  "pagination": { "total": 87, "limit": 20, "offset": 0, "has_more": true }
}
```

**Video Sources** (Feature 053):

| Source | Meaning | `mention_count` | `mentions` | `first_mention_time` |
|--------|---------|-----------------|------------|---------------------|
| `title` | Entity name found in video title | 0 | `[]` | `null` |
| `transcript` | Entity name found in transcript text | > 0 | Up to 5 previews | Timestamp (seconds) |
| `tag` | Video tagged with entity's canonical tag or alias-matched tag | 0 | `[]` | `null` |
| `description` | Entity name found in video description | 0 | `[]` | `null` |
| `manual` | User manually linked entity to video | 0 | `[]` | `null` |

Videos may have multiple sources (e.g., `["title", "transcript", "tag"]`). Badge display order follows quality hierarchy: TITLE → TRANSCRIPT → TAG → DESC → MANUAL. Description-sourced videos include a `description_context` field with a ~150 char context snippet. ASR error aliases are excluded from tag matching to prevent false positives.

---

#### Scan Entity Mentions

Trigger an entity mention scan for a single entity. Scans transcript segments by default; optionally scans video titles and descriptions when `sources` parameter is provided. The entity must exist and be in `active` status.

```
POST /api/v1/entities/{entity_id}/scan
```

| Query Parameter | Type | Default | Description |
|----------------|------|---------|-------------|
| `sources` | list[string] | `["transcript"]` | Text sources to scan: `transcript`, `title`, `description`. Multiple values accepted (e.g., `?sources=title&sources=description`). Value `tag` is rejected (422). |

**Request body (all fields optional):**

```json
{
  "language_code": "en",
  "dry_run": false,
  "full_rescan": false
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `language_code` | string | null | BCP-47 language filter |
| `dry_run` | boolean | false | Preview mode — no writes, no counter updates |
| `full_rescan` | boolean | false | Delete existing `rule_match` mentions for this entity before scanning |

**Response (200):**

```json
{
  "data": {
    "segments_scanned": 12450,
    "mentions_found": 42,
    "mentions_skipped": 3,
    "unique_entities": 1,
    "unique_videos": 12,
    "duration_seconds": 8.2,
    "dry_run": false
  }
}
```

| Status | Description |
|--------|-------------|
| 400 | Entity is not in an active state (status: merged/deprecated) |
| 404 | Entity not found |
| 409 | A scan is already in progress for this entity |

---

#### Scan Video for Entity Mentions

Trigger an entity mention scan for a single video, checking all active entity patterns against that video's transcript segments.

```
POST /api/v1/videos/{video_id}/scan-entities
```

**Request body (all fields optional):**

```json
{
  "entity_type": "person",
  "language_code": "en",
  "dry_run": false,
  "full_rescan": false
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `entity_type` | string | null | Filter to specific entity type (person, organization, place, etc.) |
| `language_code` | string | null | BCP-47 language filter |
| `dry_run` | boolean | false | Preview mode — no writes, no counter updates |
| `full_rescan` | boolean | false | Delete existing `rule_match` mentions in scope before scanning |

**Response (200):**

```json
{
  "data": {
    "segments_scanned": 156,
    "mentions_found": 23,
    "mentions_skipped": 0,
    "unique_entities": 8,
    "unique_videos": 1,
    "duration_seconds": 1.4,
    "dry_run": false
  }
}
```

A video with no transcripts returns 200 with all counts at zero.

| Status | Description |
|--------|-------------|
| 404 | Video not found |
| 409 | A scan is already in progress for this video |

---

#### Get Video Entities

Retrieve all entities mentioned in a specific video, sorted by mention count descending.

```
GET /api/v1/videos/{video_id}/entities
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `language_code` | string | Optional BCP-47 language code filter |

**Response (200):**

```json
{
  "data": [
    {
      "entity_id": "01936c8a-...",
      "canonical_name": "Andrés Manuel López Obrador",
      "entity_type": "person",
      "description": "Former President of Mexico (2018–2024)",
      "mention_count": 12,
      "first_mention_time": 45.2,
      "has_manual": false,
      "sources": ["transcript"]
    }
  ]
}
```

- `has_manual` — `true` when a manual association exists for this entity+video
- `sources` — list of source categories present (e.g., `["transcript"]`, `["manual"]`, `["transcript", "manual"]`)

---

#### Create Entity Alias

Add a new alias to an existing entity.

```
POST /api/v1/entities/{entity_id}/aliases
```

**Request body:**

```json
{
  "alias_name": "AMLO",
  "alias_type": "abbreviation"
}
```

Valid alias types: `name_variant`, `abbreviation`, `nickname`, `translated_name`, `former_name`.

**Response (201):**

```json
{
  "data": {
    "alias_name": "AMLO",
    "alias_type": "abbreviation",
    "occurrence_count": 0
  }
}
```

| Status | Description |
|--------|-------------|
| 404 | Entity not found |
| 409 | Alias already exists |

---

#### Search Entities (with Link Status)

Search named entities with optional video-level link status. Used by the `EntityMentionsPanel` autocomplete to indicate which entities are already associated with a video.

```
GET /api/v1/entities/search
```

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `q` | string | Search query (2+ characters, required) | - |
| `video_id` | string | YouTube video ID — when provided, response includes `is_linked` and `link_sources` | - |
| `limit` | integer | Results per page (1–50) | 10 |

**Response (200):**

```json
{
  "data": [
    {
      "entity_id": "01936c8a-...",
      "canonical_name": "Noam Chomsky",
      "entity_type": "person",
      "status": "active",
      "is_linked": true,
      "link_sources": ["transcript", "manual"]
    }
  ]
}
```

- `is_linked` is `true` when the entity has any association with the given `video_id` (transcript mention, manual link, etc.)
- `link_sources` lists the source categories of existing associations (e.g., `["transcript"]`, `["manual"]`, `["transcript", "manual"]`)
- Both fields are `null` when `video_id` is not provided

---

#### Create Manual Entity-Video Association

Manually associate a named entity with a video. Creates an `entity_mentions` row with `detection_method='manual'` and no segment reference.

```
POST /api/v1/videos/{video_id}/entities/{entity_id}/manual
```

**Response (201):**

```json
{
  "data": {
    "mention_id": "019...",
    "entity_id": "01936c8a-...",
    "video_id": "dQw4w9WgXcQ",
    "detection_method": "manual"
  }
}
```

| Status | Description |
|--------|-------------|
| 404 | Entity or video not found |
| 409 | Manual association already exists for this entity+video |

---

#### Delete Manual Entity-Video Association

Remove a manual entity-video association. Only manual associations can be deleted; transcript-derived mentions cannot be removed via this endpoint.

```
DELETE /api/v1/videos/{video_id}/entities/{entity_id}/manual
```

**Response:** `204 No Content`

| Status | Description |
|--------|-------------|
| 404 | No manual association found for this entity+video |

---

#### Get Phonetic ASR Variants

Find suspected phonetic ASR misrecognitions of an entity's name by scanning transcript segments from videos where the entity is mentioned.

```
GET /api/v1/entities/{entity_id}/phonetic-matches
```

##### Query Parameters

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `threshold` | float | Minimum confidence score to include a match (0.0-1.0) | 0.5 |

##### Response (200 OK)

```json
{
  "data": [
    {
      "original_text": "Shane Baum",
      "proposed_correction": "Sheinbaum",
      "confidence": 0.78,
      "evidence_description": "Phonetic similarity via Soundex + Metaphone",
      "video_id": "JIMXfrMtHas",
      "segment_id": 934,
      "video_title": "Interview with President Sheinbaum"
    }
  ]
}
```

Each match includes the original transcript N-gram, the entity name it likely represents, a confidence score, and the video/segment location. The `video_title` field is enriched from the videos table.

| Status | Description |
|--------|-------------|
| 404 | Entity not found |

---

#### Check Duplicate Entity

Check whether an entity with the same normalized name and type already exists before creating one. Rate-limited to 50 requests per minute per client IP.

```
GET /api/v1/entities/check-duplicate
```

##### Query Parameters

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `name` | string | Entity name to check (required) | - |
| `type` | string | Entity type to filter by (required) | - |

##### Response (200 OK)

```json
{
  "is_duplicate": true,
  "existing_entity": {
    "entity_id": "01936c8a-1234-7000-8000-000000000001",
    "canonical_name": "Noam Chomsky",
    "entity_type": "person",
    "description": "American linguist and political commentator"
  }
}
```

When no duplicate is found, `is_duplicate` is `false` and `existing_entity` is `null`.

| Status | Description |
|--------|-------------|
| 429 | Rate limit exceeded (50 req/min per client IP). Includes `Retry-After` header. |

---

#### Classify Tag as Entity

Create a named entity from an existing canonical tag. Delegates to the tag management service which handles entity creation/linking and alias registration.

```
POST /api/v1/entities/classify
```

**Request body:**

```json
{
  "normalized_form": "noam chomsky",
  "entity_type": "person",
  "description": "American linguist and political commentator"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `normalized_form` | string | yes | Normalized form of the canonical tag (1-500 chars) |
| `entity_type` | string | yes | Entity type: `person`, `organization`, `place`, `event`, `work`, `technical_term`, `concept`, `other` |
| `description` | string | no | Entity description (max 5000 chars) |

**Response (201 Created):**

```json
{
  "entity_id": "01936c8a-1234-7000-8000-000000000001",
  "canonical_name": "Noam Chomsky",
  "entity_type": "person",
  "description": "American linguist and political commentator",
  "alias_count": 2,
  "entity_created": true,
  "operation_id": "01936c8b-5678-7000-8000-000000000002"
}
```

| Status | Description |
|--------|-------------|
| 400 | Invalid entity_type or other validation error |
| 404 | Canonical tag not found or inactive |
| 409 | Tag is already classified as an entity. Response includes `existing_entity` details. |

---

#### Create Standalone Entity

Create a new named entity without linking to a canonical tag. The entity name is auto-title-cased and normalized for duplicate detection.

```
POST /api/v1/entities
```

**Request body:**

```json
{
  "name": "Noam Chomsky",
  "entity_type": "person",
  "description": "American linguist and political commentator",
  "aliases": ["Chomsky", "N. Chomsky"]
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | yes | Entity display name (1-500 chars) |
| `entity_type` | string | yes | Entity type: `person`, `organization`, `place`, `event`, `work`, `technical_term`, `concept`, `other` |
| `description` | string | no | Entity description (max 5000 chars) |
| `aliases` | string[] | no | Additional alias names (max 20). Duplicates by normalized form are skipped. |

**Response (201 Created):**

```json
{
  "entity_id": "01936c8a-1234-7000-8000-000000000001",
  "canonical_name": "Noam Chomsky",
  "entity_type": "person",
  "description": "American linguist and political commentator",
  "alias_count": 3
}
```

The `alias_count` includes the canonical name plus any unique aliases provided.

| Status | Description |
|--------|-------------|
| 409 | An active entity with the same normalized name and type already exists. Response includes `existing_entity` details. |
| 422 | Entity name normalizes to an empty string |

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
- Multi-word queries are treated as contiguous phrase searches (the entire query is matched as a single phrase, not split into independent terms)
- Special characters (`_`, `%`, `\`) in search queries are escaped and matched literally
- Queries containing NULL bytes (`\x00`) are rejected with `400 Bad Request`
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

### Settings

#### Get Supported Languages

Get all supported BCP-47 language codes with human-readable display names. No authentication required.

```
GET /api/v1/settings/supported-languages
```

##### Response

```json
{
  "data": [
    { "code": "af", "display_name": "Afrikaans" },
    { "code": "ar", "display_name": "Arabic" },
    { "code": "en", "display_name": "English" },
    { "code": "es", "display_name": "Spanish" },
    { "code": "fr", "display_name": "French" },
    "..."
  ]
}
```

#### Get Cache Status

Get the current image cache status including file count and disk usage.

```
GET /api/v1/settings/cache-status
```

##### Response

```json
{
  "data": {
    "total_files": 342,
    "total_size_bytes": 24576000,
    "total_size_display": "23.4 MB",
    "last_modified": "2026-03-21T10:30:00Z"
  }
}
```

##### Notes

- Returns `total_files: 0` and `total_size_bytes: 0` when the cache directory is empty or does not exist
- `last_modified` is `null` when no cached files exist

#### Clear Cache

Purge all cached images (channel avatars and video thumbnails).

```
DELETE /api/v1/settings/cache
```

##### Response

```json
{
  "data": {
    "files_deleted": 342,
    "space_freed_bytes": 24576000,
    "space_freed_display": "23.4 MB"
  }
}
```

##### Errors

| Status | Code | Description |
|--------|------|-------------|
| 500 | `INTERNAL_ERROR` | Cache directory could not be purged |

#### Get Application Info

Get application version, database statistics, and last sync timestamps.

```
GET /api/v1/settings/app-info
```

##### Response

```json
{
  "data": {
    "backend_version": "0.50.0",
    "frontend_version": "0.19.0",
    "database_stats": {
      "videos": 1523,
      "channels": 87,
      "playlists": 12,
      "transcripts": 943,
      "corrections": 156,
      "canonical_tags": 124686
    },
    "sync_timestamps": {
      "subscriptions": null,
      "videos": "2026-03-20T15:30:00Z",
      "transcripts": null,
      "playlists": null,
      "topics": null
    }
  }
}
```

##### Notes

- `sync_timestamps` values are `null` when a data type has never been synced (displayed as "Never synced" in the UI)
- Sync timestamps are currently stored in-memory only and reset on server restart (see [GitHub #102](https://github.com/aucontraire/chronovista/issues/102))
- `frontend_version` is read from the compiled frontend build; returns `"unknown"` if the build metadata file is not found

---

### Recovery

Recover metadata for unavailable (deleted, private, or terminated) videos and channels using the Internet Archive's Wayback Machine.

#### Recover Video Metadata

Trigger a Wayback Machine recovery for an unavailable video.

```
POST /api/v1/videos/{video_id}/recover
```

##### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `video_id` | string | YouTube video ID (11 characters) |

##### Query Parameters

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `start_year` | integer | Only search snapshots from this year onward (2005-2026) | - |
| `end_year` | integer | Only search snapshots up to this year (2005-2026) | - |

##### Response (200 OK)

```json
{
  "data": {
    "video_id": "dQw4w9WgXcQ",
    "success": true,
    "snapshot_used": "20210315142030",
    "fields_recovered": ["title", "description", "channel_id", "tags"],
    "fields_skipped": ["view_count"],
    "snapshots_available": 45,
    "snapshots_tried": 2,
    "failure_reason": null,
    "duration_seconds": 3.42,
    "channel_recovery_candidates": ["UCuAXFkgsw1L7xaCfnd5JJOw"],
    "channel_recovered": true,
    "channel_fields_recovered": ["title", "description"],
    "channel_fields_skipped": [],
    "channel_failure_reason": null
  }
}
```

##### Error Responses

| HTTP Status | Code | Description |
|-------------|------|-------------|
| 404 | `NOT_FOUND` | Video not found in the database |
| 409 | `CONFLICT` | Video is currently available (recovery only applies to unavailable videos) |
| 503 | - | Wayback Machine CDX API unavailable (includes `Retry-After: 60` header) |

##### Idempotency Guard

If the video was already recovered within the last 5 minutes, the endpoint returns a cached success response without contacting the Wayback Machine, with `fields_recovered: []` and `duration_seconds: 0.0`.

---

#### Recover Channel Metadata

Trigger a Wayback Machine recovery for an unavailable channel.

```
POST /api/v1/channels/{channel_id}/recover
```

##### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `channel_id` | string | YouTube channel ID (24 characters) |

##### Query Parameters

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `start_year` | integer | Only search snapshots from this year onward (2005-2026) | - |
| `end_year` | integer | Only search snapshots up to this year (2005-2026) | - |

##### Response (200 OK)

```json
{
  "data": {
    "channel_id": "UCuAXFkgsw1L7xaCfnd5JJOw",
    "success": true,
    "snapshot_used": "20220801120000",
    "fields_recovered": ["title", "description"],
    "fields_skipped": [],
    "snapshots_available": 12,
    "snapshots_tried": 1,
    "failure_reason": null,
    "duration_seconds": 2.15
  }
}
```

##### Error Responses

| HTTP Status | Code | Description |
|-------------|------|-------------|
| 404 | `NOT_FOUND` | Channel not found in the database |
| 409 | `CONFLICT` | Channel is currently available (recovery only applies to unavailable channels) |
| 503 | - | Wayback Machine CDX API unavailable (includes `Retry-After: 60` header) |

##### Idempotency Guard

If the channel was already recovered within the last 5 minutes, the endpoint returns a cached success response without contacting the Wayback Machine.

##### Recovery Dependency Injection

Both recovery endpoints share a module-level rate limiter (`get_recovery_deps()` in `deps.py`) configured at 40 requests per second. CDXClient and PageParser instances are created per-call as they hold no request-scoped state.

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
