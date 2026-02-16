# System Design

Detailed component design and service architecture.

## Service Architecture

```
                    Service Layer
+-------------------------------------------------------------------+
|                                                                    |
|  +---------------+  +---------------+  +---------------+           |
|  |   AuthService |  | ChannelService|  |SmartTranscript|           |
|  |               |  |               |  |   Service     |           |
|  +-------+-------+  +-------+-------+  +-------+-------+           |
|          |                  |                  |                    |
|  +---------------+  +---------------+  +---------------+           |
|  |GoogleTakeout  |  |LanguagePref   |  |  ExportService|           |
|  |   Parser      |  |   Service     |  |               |           |
|  +-------+-------+  +-------+-------+  +-------+-------+           |
|          |                  |                  |                    |
|  +---------------+  +---------------+  +---------------+           |
|  |  TagService   |  | UserAction    |  |  TopicService |           |
|  |               |  |   Service     |  |               |           |
|  +---------------+  +---------------+  +---------------+           |
|          |                  |                  |                    |
|  +---------------+  +---------------+  +---------------+           |
|  | Recovery      |  |  CDXClient   |  |  PageParser   |           |
|  | Orchestrator  |  |              |  |               |           |
|  +---------------+  +---------------+  +---------------+           |
|                                                                    |
+-------------------------------------------------------------------+
```

## Recovery Services

### RecoveryOrchestrator

Coordinates deleted video recovery via the Wayback Machine:

```
1. Check video eligibility (must exist, must not be AVAILABLE)
2. Query CDX API for archived snapshots
3. Iterate snapshots (max 20, 600s timeout)
4. Extract metadata via PageParser (JSON → meta tags → Selenium)
5. Apply three-tier overwrite policy
6. Create stub channels for unknown channel_ids (FK safety)
7. Update video record and persist recovered tags
```

### CDXClient

Async client for the Wayback Machine CDX API:

- File-based caching with 24-hour TTL
- Separate cache keys per year filter (`{video_id}_from2018.json`)
- Exponential backoff retry (3 retries, base 2s)
- Rate limit handling (60s pause on 429)
- Configurable date range filtering (`--start-year`/`--end-year`)
- Sort order: newest-first by default, oldest-first when `from_year` is set

### PageParser

Extracts metadata from archived YouTube video pages using three strategies:

1. **JSON extraction** — Parses `ytInitialPlayerResponse` embedded JavaScript for title, description, channel, tags, view count, upload date, category, thumbnail
2. **Meta tag fallback** — Parses Open Graph (`og:`) and `itemprop` HTML meta tags via BeautifulSoup (covers pre-2017 pages lacking JSON)
3. **Selenium fallback** — Optional rendering for pre-2017 pages requiring JavaScript (requires `selenium` + `webdriver-manager`)

Includes removal notice detection (playability status, title checks, body text patterns) to skip archived pages that show "Video unavailable" instead of real content.

## Core Services

### AuthService

Manages OAuth 2.0 authentication with YouTube:

```python
class AuthService(ABC):
    @abstractmethod
    async def authenticate(self) -> Credentials: ...

    @abstractmethod
    async def refresh_token(self) -> Credentials: ...

    @abstractmethod
    async def revoke_access(self) -> None: ...

    @abstractmethod
    async def get_current_user(self) -> User: ...
```

### ChannelService

Manages YouTube channels and subscriptions:

```python
class ChannelService(ABC):
    @abstractmethod
    async def sync_subscriptions(self) -> List[Channel]: ...

    @abstractmethod
    async def get_channel_details(self, channel_id: ChannelId) -> Channel: ...

    @abstractmethod
    async def get_videos_by_channel(self, channel_id: ChannelId) -> List[Video]: ...

    @abstractmethod
    async def get_watched_videos_by_channel(
        self, channel_id: ChannelId
    ) -> List[UserVideo]: ...

    @abstractmethod
    async def extract_and_store_keywords(
        self, channel_id: ChannelId
    ) -> List[ChannelKeyword]: ...
```

### SmartTranscriptService

Intelligent multi-language transcript management:

```python
class SmartTranscriptService(ABC):
    @abstractmethod
    async def download_intelligent_transcripts(
        self, video_id: VideoId
    ) -> List[VideoTranscript]: ...

    @abstractmethod
    async def get_available_languages(self, video_id: VideoId) -> List[str]: ...

    @abstractmethod
    async def should_download_transcript(
        self, video_id: VideoId, lang: str
    ) -> bool: ...

    @abstractmethod
    async def get_transcript_quality_score(
        self, video_id: VideoId, lang: str
    ) -> float: ...

    @abstractmethod
    async def prioritize_transcripts_by_quality(
        self, video_id: VideoId
    ) -> List[VideoTranscript]: ...
```

### LanguagePreferenceService

Manages user language preferences:

```python
class LanguagePreferenceService(ABC):
    @abstractmethod
    async def set_language_preference(
        self, lang: str, pref_type: LanguagePreferenceType
    ) -> None: ...

    @abstractmethod
    async def get_preferred_languages(self) -> List[UserLanguagePreference]: ...

    @abstractmethod
    async def get_download_strategy(
        self, video_id: VideoId
    ) -> TranscriptDownloadStrategy: ...
```

### TagService

Manages tags and topic classification:

```python
class TagService(ABC):
    @abstractmethod
    async def extract_video_tags(self, video_id: VideoId) -> List[VideoTag]: ...

    @abstractmethod
    async def extract_channel_keywords(
        self, channel_id: ChannelId
    ) -> List[ChannelKeyword]: ...

    @abstractmethod
    async def sync_topic_categories(
        self, topic_ids: List[str]
    ) -> List[TopicCategory]: ...

    @abstractmethod
    async def get_related_videos_by_tags(self, tags: List[str]) -> List[str]: ...
```

### GoogleTakeoutService

Processes Google Takeout data:

```python
class GoogleTakeoutService:
    async def parse_watch_history(self, path: Path) -> List[WatchHistoryEntry]: ...

    async def parse_subscriptions(self, path: Path) -> List[Subscription]: ...

    async def parse_playlists(self, path: Path) -> List[Playlist]: ...

    async def enrich_with_api_data(
        self, entries: List[WatchHistoryEntry]
    ) -> List[Video]: ...
```

## Repository Layer

### Base Repository

```python
class BaseRepository(ABC, Generic[T]):
    @abstractmethod
    async def save(self, entity: T) -> None: ...

    @abstractmethod
    async def find_by_id(self, id: str) -> Optional[T]: ...

    @abstractmethod
    async def find_all(self) -> List[T]: ...

    @abstractmethod
    async def delete(self, id: str) -> bool: ...
```

### Specialized Repositories

| Repository | Entity | Key Features |
|------------|--------|--------------|
| ChannelRepository | Channel | Subscription tracking |
| VideoRepository | Video | Multi-language support |
| TranscriptRepository | Transcript | Quality scoring |
| TopicRepository | Topic | Hierarchical structure |
| UserVideoRepository | UserVideo | Watch history |

## Data Enrichment Pipeline

```
Google Takeout
     |
     v
+--------------------+
| Parse Takeout Files|
| - watch-history.json
| - subscriptions.csv
| - playlists.json
+--------+-----------+
         |
         v
+--------------------+
| Extract Identifiers|
| - Video IDs
| - Channel IDs
| - Playlist IDs
+--------+-----------+
         |
         v
+--------------------+
| Batch API Calls    |
| - videos.list()
| - channels.list()
| - Rate limited
+--------+-----------+
         |
         v
+--------------------+
| Apply Preferences  |
| - Language filter
| - Quality filter
| - Topic filter
+--------+-----------+
         |
         v
+--------------------+
| Store in Database  |
| - Upsert logic
| - FK integrity
| - Deduplication
+--------------------+
```

## Rate Limiting Strategy

### API Client

```python
class RateLimitedAPIClient:
    def __init__(
        self,
        requests_per_minute: int = 100,
        daily_quota: int = 10000,
    ):
        self.rate_limiter = AsyncLimiter(requests_per_minute, 60)
        self.quota_tracker = QuotaTracker(daily_quota)

    async def call_api(self, operation: str, cost: int = 1):
        await self.rate_limiter.acquire()
        if not self.quota_tracker.can_spend(cost):
            raise QuotaExceededException()
        self.quota_tracker.spend(cost)
        return await self._execute(operation)
```

### Retry Logic

```python
@retry(
    retry=retry_if_exception_type((APIError, NetworkError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=60),
    before_sleep=before_sleep_log(logger, logging.WARNING),
)
async def fetch_with_retry(self, video_id: str):
    ...
```

## Configuration Management

### Environment-Based

```python
class Settings(BaseSettings):
    youtube_api_key: str
    youtube_client_id: str
    youtube_client_secret: str
    database_url: str

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )
```

### Language Configuration

```yaml
# ~/.chronovista/language_config.yaml
language_preferences:
  fluent: [en-US, es-ES]
  learning: [it-IT]
  curious: [fr-FR]
  exclude: [zh-CN]

auto_download_rules:
  fluent_languages: true
  learning_languages: true
  max_transcripts_per_video: 3
```

## Error Handling

### Custom Exceptions

```python
class ChronovistaError(Exception):
    """Base exception for all chronovista errors."""
    pass

class AuthenticationError(ChronovistaError):
    """Authentication failed."""
    pass

class QuotaExceededError(ChronovistaError):
    """API quota exceeded."""
    pass

class TranscriptNotFoundError(ChronovistaError):
    """Transcript not available."""
    pass
```

### Error Recovery

```python
async def sync_with_recovery(self, items: List[str]):
    failed = []
    for item in items:
        try:
            await self.sync_item(item)
        except TransientError:
            await asyncio.sleep(5)
            failed.append(item)
        except PermanentError as e:
            logger.error(f"Permanent error for {item}: {e}")

    # Retry failed items
    if failed:
        await self.sync_with_recovery(failed)
```

## See Also

- [Architecture Overview](overview.md) - High-level design
- [Data Model](data-model.md) - Database schema
- [API Integration](api-integration.md) - YouTube API details
