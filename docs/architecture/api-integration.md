# API Integration

YouTube Data API v3 integration details.

## Overview

chronovista integrates with the YouTube Data API v3 for real-time data access and enrichment of Google Takeout historical data.

## API Resources

### Video Resource

[YouTube Video Resource Documentation](https://developers.google.com/youtube/v3/docs/videos)

Key fields used:

| Field | Usage |
|-------|-------|
| `snippet.tags[]` | Video-level content tags |
| `snippet.defaultLanguage` | Primary video language (BCP-47) |
| `snippet.defaultAudioLanguage` | Audio track language |
| `snippet.localized` | Current language variant |
| `status.madeForKids` | COPPA compliance flag |
| `contentDetails.regionRestriction` | Geographic limitations |
| `contentDetails.contentRating` | Rating system values |
| `topicDetails.topicCategories[]` | Topic classification |
| `localizations` | Per-language content variants |

### Channel Resource

[YouTube Channel Resource Documentation](https://developers.google.com/youtube/v3/docs/channels)

Key fields used:

| Field | Usage |
|-------|-------|
| `snippet.defaultLanguage` | Channel's primary language |
| `snippet.country` | Channel's country/region |
| `brandingSettings.channel.keywords` | Channel topic keywords |
| `topicDetails.topicCategories[]` | Channel topics |
| `status.madeForKids` | Channel content restriction |

### Caption Resource

[YouTube Caption Resource Documentation](https://developers.google.com/youtube/v3/docs/captions)

Key fields used:

| Field | Usage |
|-------|-------|
| `snippet.language` | Caption language (BCP-47) |
| `snippet.trackKind` | Caption type (standard, ASR, forced) |
| `snippet.isCC` | Closed captions indicator |
| `snippet.isAutoSynced` | Auto-generated flag |
| `snippet.name` | Caption track name |

### Subscription Resource

[YouTube Subscription Resource Documentation](https://developers.google.com/youtube/v3/docs/subscriptions)

Key fields used:

| Field | Usage |
|-------|-------|
| `snippet.publishedAt` | Subscription date |
| `snippet.resourceId.channelId` | Subscribed channel |
| `contentDetails.newItemCount` | New content count |

## API Operations

### Read Operations (Current)

```python
# Channel metadata
youtube.channels().list(
    part="snippet,statistics,topicDetails,brandingSettings",
    id=channel_id
)

# Video metadata
youtube.videos().list(
    part="snippet,contentDetails,status,statistics,topicDetails,localizations",
    id=video_id
)

# Available captions
youtube.captions().list(
    part="snippet",
    videoId=video_id
)

# Download caption
youtube.captions().download(
    id=caption_id,
    tfmt="srt"
)

# User subscriptions
youtube.subscriptions().list(
    part="snippet,contentDetails",
    mine=True
)

# Playlist items
youtube.playlistItems().list(
    part="snippet,contentDetails",
    playlistId=playlist_id
)
```

### Write Operations (Phase 3)

```python
# Create playlist
youtube.playlists().insert(
    part="snippet,status",
    body={
        "snippet": {
            "title": "My Playlist",
            "description": "Created by chronovista"
        },
        "status": {"privacyStatus": "private"}
    }
)

# Add to playlist
youtube.playlistItems().insert(
    part="snippet",
    body={
        "snippet": {
            "playlistId": playlist_id,
            "resourceId": {"kind": "youtube#video", "videoId": video_id}
        }
    }
)

# Rate video
youtube.videos().rate(
    id=video_id,
    rating="like"  # like, dislike, none
)

# Subscribe to channel
youtube.subscriptions().insert(
    part="snippet",
    body={
        "snippet": {
            "resourceId": {"kind": "youtube#channel", "channelId": channel_id}
        }
    }
)
```

## Quota Management

### Quota Costs

| Operation | Quota Units |
|-----------|-------------|
| videos.list | 1 |
| channels.list | 1 |
| playlists.list | 1 |
| subscriptions.list | 1 |
| captions.list | 50 |
| captions.download | 200 |
| playlists.insert | 50 |
| subscriptions.insert | 50 |
| videos.rate | 50 |

### Daily Quota

- Default: 10,000 units/day
- Request increase via Google Cloud Console

### Quota Optimization

```python
# Batch multiple video IDs
youtube.videos().list(
    part="snippet,statistics",
    id=",".join(video_ids[:50])  # Max 50 per request
)

# Use minimal parts
youtube.videos().list(
    part="snippet",  # Only what's needed
    id=video_id
)

# Cache responses
@cached(ttl=3600)
async def get_channel(channel_id: str):
    return await youtube.channels().list(...)
```

## Rate Limiting

### Implementation

```python
class YouTubeAPIClient:
    def __init__(self):
        self.rate_limiter = AsyncLimiter(100, 60)  # 100/min
        self.daily_quota = 10000
        self.used_quota = 0

    async def call(self, operation: str, quota_cost: int = 1):
        async with self.rate_limiter:
            if self.used_quota + quota_cost > self.daily_quota:
                raise QuotaExceededError()
            self.used_quota += quota_cost
            return await self._execute(operation)
```

### Retry Strategy

```python
@retry(
    retry=retry_if_exception_type((
        HttpError,
        socket.timeout,
        ConnectionError
    )),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=4, max=60),
)
async def call_api(self, operation):
    ...
```

## OAuth Scopes

### Read Scopes (Default)

```python
READ_SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube.force-ssl"
]
```

### Write Scopes (Phase 3)

```python
WRITE_SCOPES = [
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl"
]
```

### Progressive Scope Management

```python
class AuthService:
    async def request_write_access(self):
        """Upgrade to write scopes when needed."""
        current_scopes = await self.get_current_scopes()
        if "youtube" not in current_scopes:
            await self.reauthenticate(WRITE_SCOPES)
```

## Error Handling

### Common Errors

| Error | Code | Handling |
|-------|------|----------|
| quotaExceeded | 403 | Wait 24h, request increase |
| rateLimitExceeded | 403 | Exponential backoff |
| videoNotFound | 404 | Mark as deleted |
| captionsNotFound | 404 | Mark no captions available |
| forbidden | 403 | Check scopes |

### Error Recovery

```python
async def fetch_video(self, video_id: str):
    try:
        return await self.youtube.videos().list(
            part="snippet,statistics",
            id=video_id
        ).execute()
    except HttpError as e:
        if e.resp.status == 404:
            await self.mark_video_deleted(video_id)
            return None
        elif e.resp.status == 403:
            if "quotaExceeded" in str(e):
                raise QuotaExceededError()
            elif "rateLimitExceeded" in str(e):
                await asyncio.sleep(60)
                return await self.fetch_video(video_id)
        raise
```

## Data Mapping

### Video API to Model

```python
def map_video_response(api_response: dict) -> Video:
    snippet = api_response["snippet"]
    content = api_response.get("contentDetails", {})
    status = api_response.get("status", {})

    return Video(
        video_id=api_response["id"],
        channel_id=snippet["channelId"],
        title=snippet["title"],
        description=snippet.get("description", ""),
        upload_date=datetime.fromisoformat(
            snippet["publishedAt"].replace("Z", "+00:00")
        ),
        duration=parse_duration(content.get("duration", "PT0S")),
        made_for_kids=status.get("madeForKids", False),
        default_language=snippet.get("defaultLanguage"),
        default_audio_language=snippet.get("defaultAudioLanguage"),
        region_restriction=content.get("regionRestriction"),
        content_rating=content.get("contentRating"),
    )
```

### Channel API to Model

```python
def map_channel_response(api_response: dict) -> Channel:
    snippet = api_response["snippet"]
    stats = api_response.get("statistics", {})
    branding = api_response.get("brandingSettings", {}).get("channel", {})

    return Channel(
        channel_id=api_response["id"],
        title=snippet["title"],
        description=snippet.get("description", ""),
        subscriber_count=int(stats.get("subscriberCount", 0)),
        video_count=int(stats.get("videoCount", 0)),
        default_language=snippet.get("defaultLanguage")
            or branding.get("defaultLanguage"),
        country=snippet.get("country") or branding.get("country"),
    )
```

## Recovery API Endpoints

chronovista exposes two REST API endpoints for triggering Wayback Machine recovery (v0.28.0). These are internal endpoints served by FastAPI, not YouTube Data API operations.

### POST /api/v1/videos/{video_id}/recover

Triggers recovery of a single deleted/unavailable video via the Wayback Machine.

**Parameters:**

| Parameter | Location | Type | Description |
|-----------|----------|------|-------------|
| `video_id` | path | string | YouTube video ID |
| `start_year` | query | int (optional) | Earliest snapshot year to search |
| `end_year` | query | int (optional) | Latest snapshot year to search |

**Behavior:**
- Returns cached result if `recovered_at` is within the 5-minute idempotency window
- Queries CDX API for archived snapshots, iterates up to 20 with 600s timeout
- Applies three-tier overwrite policy (immutable fill-if-NULL, mutable overwrite-if-newer, NULL protection)
- Auto-recovers channel metadata from video page when channel record is incomplete
- Creates stub channel records for unknown `channel_id` values (FK safety)

**Response:** `RecoveryResult` with recovered field names, snapshot timestamp, and recovery source.

### POST /api/v1/channels/{channel_id}/recover

Triggers batch recovery of all deleted/unavailable videos for a channel.

**Parameters:**

| Parameter | Location | Type | Description |
|-----------|----------|------|-------------|
| `channel_id` | path | string | YouTube channel ID |
| `start_year` | query | int (optional) | Earliest snapshot year to search |
| `end_year` | query | int (optional) | Latest snapshot year to search |

**Behavior:**
- Loads all non-available videos for the channel
- Iterates each through the video recovery orchestrator
- Extracts and applies channel-level metadata from video pages (two-tier overwrite)
- Returns per-video outcomes with summary statistics

**Response:** `ChannelRecoveryResult` with per-video results, total recovered count, and channel metadata updates.

### Dependency Injection

Both endpoints use `get_recovery_deps()` from `api/deps.py` to obtain a `RecoveryDeps` bundle containing the CDX client, page parser, and orchestrator, all sharing a single database session per request.

## See Also

- [Architecture Overview](overview.md) - System context
- [System Design](system-design.md) - Service layer
- [Data Model](data-model.md) - Database schema
